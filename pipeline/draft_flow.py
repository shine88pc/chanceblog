"""Chance 승인 흐름의 실행부 — 초안 브랜치 올리기·승인 PR 열기·남은 초안 정리. 규칙과 이름은 pipeline/drafts.py, 설명은 docs/ARCHITECTURE.md §4-4.

CLI(워크플로 chanceblog.yml 이 부른다):
  python -m pipeline.draft_flow flow      레지스트리의 chance 발행 흐름(direct|pr)을 한 줄로 출력한다. 읽지 못하면 종료 1.
  python -m pipeline.draft_flow deliver   이번 실행이 만든 초안을 올리고 PR 을 연 뒤, 남은 초안(PR 없는 브랜치·오래된 브랜치)을 정리한다.

deliver 가 하는 일(publish_flow 가 pr 이고 연습 실행이 아닐 때만):
  1. generator.py 가 작업 트리에 쓴 새 글 두 개와 이력 항목(flow=pr)을 찾는다. 없으면(건너뜀) 할 일이 없다.
  2. 글 두 개만 담은 커밋을 초안 브랜치(ai/draft/…)에 만들고, 기준 브랜치(main)로 돌아와 이력 파일만 담은 커밋을 만든다.
  3. 초안 브랜치를 push 한다(실패하면 인프라 실패). 이어서 이력 커밋을 main 에 push 한다(pull --rebase 로 3회까지). 이력 push 가 끝내 실패하면
     방금 올린 초안 브랜치를 지우고(롤백) 실패로 끝낸다 — 이력 없는 초안이 남아 같은 슬롯을 또 만들지 않게.
  4. PR 을 연다(5xx·네트워크 오류는 재시도). 저장소 설정이 꺼져 있어 거부(403)되거나 API 오류가 나도 초안 브랜치와 이력은 그대로 남고,
     실행 요약에 안내를 남기며 종료 1(빨강)이다 — 운영자에게 Actions 실패 알림이 가게 한다. 슬롯은 처리된 것이라 다시 만들지 않고,
     다음 실행의 정리 단계가 PR 열기를 다시 시도한다(경고만, 빨강 아님).
  5. 라벨(초안·채널:Chance)을 붙인다. 실패해도 PR·종료 코드는 그대로지만 조용히 넘기지 않는다(R2 수정 P1): 모음은 라벨 `초안` 으로만 초안 PR 을 알아보므로 라벨이 없으면
     '발행 대기' 알림이 가지 않는다. 그래서 사유 한 줄에 이어 고정 문장 ::warning::, 실행 요약의 쉬운 말 한 줄을 남기고 아래 6 의 모음 요청은 하지 않는다. 다음 실행의 정리가 다시 붙인다(아래).
  6. PR 을 열었거나(정리가 PR 을 다시 연 경우 포함) 확인 필요 모음의 '초안 대기'가 새로 생길 때, 모음(ops-inbox.yml)을 수동 실행 이벤트로 바로 돌린다(R2-4, 2026-11-09).
     저장소 기본 토큰이 연 PR 은 이벤트로 그 워크플로를 시작시키지 못해 정기 갱신(보통 3–6시간)을 기다려야 했다. 모음의 점검이 코멘트(@멘션)와 휴대폰 텔레그램 '발행 대기' 알림을 만든다.
     이 요청이 실패해도 초안·PR·종료 코드는 그대로고 경고만 남는다(다음 정기 갱신이 같은 것을 보여 준다). 워크플로 파일은 바꾸지 않았다 — 이 모듈이 REST 로 부른다.
     라벨이 붙은 PR 이 새로 생겼을 때만 부른다(라벨이 없으면 모음이 알아보지 못해 부를 까닭이 없다).
정리: PR 이 없는 초안 브랜치(최근 ORPHAN_RETRY_DAYS일)는 PR 을 다시 열고, 병합됐거나 닫힌 브랜치와 오래된(RETENTION_DAYS일) PR 없는 브랜치는 지운다.
열린 PR 이 있는 브랜치는 오래돼도 지우지 않는다. 열린 PR 인데 우리 라벨(초안·채널:…·폐기)이 하나도 없으면 라벨을 다시 붙인다(R2 수정 P1 — 라벨 붙이기가 한 번 실패한 PR 이 영영
무라벨로 남지 않게. PR 목록이 라벨을 알려 주지 않았거나 운영자가 일부러 `초안` 만 뗀 PR 은 건드리지 않는다). 정리 단계의 실패는 경고일 뿐 실행을 실패시키지 않는다.

로컬 실행에서는 아무것도 push 하지 않는다: GITHUB_TOKEN·GITHUB_REPOSITORY 가 없으면 '로컬'이라고 알리고 끝낸다.
종료 코드: 0 정상 / 1 실패(브랜치·이력 push 실패, PR 을 열지 못함, 레지스트리 오류).
"""
import json
import os
import re
import subprocess
import sys
import time
from collections import namedtuple
from datetime import datetime
from pathlib import Path

from pipeline import draft_labels, drafts
from pipeline.console import one_line, safe_output
from pipeline.llm import scrub
from pipeline.state import KST, StateError, read_json_list

BOT_NAME = "github-actions[bot]"
BOT_EMAIL = "41898282+github-actions[bot]@users.noreply.github.com"
HISTORY_PATH = "history.json"
GIT_TIMEOUT = 180
PUSH_ATTEMPTS = 3
# ::error::·::warning:: 주석에는 입력 유래 문자열 없이 이 고정 문장만 쓴다(자세한 사유는 일반 로그 줄과 실행 요약에 접어서 남긴다)
ERROR_PR_FAILED = "::error::초안 브랜치와 이력은 올라갔지만 승인 PR 을 열지 못했습니다. 실행 요약의 안내를 따르세요."
WARN_HOUSEKEEPING = "::warning::초안 정리 단계에서 일부 작업을 하지 못했습니다(발행에는 영향 없음). 이유는 로그의 바로 앞 줄에 있습니다."
WARN_INBOX = "::warning::확인 필요 모음을 바로 갱신하도록 요청하지 못했습니다(초안 대기는 다음 정기 갱신 때 모음에 나타납니다). 이유는 로그의 바로 앞 줄에 있습니다."
# 라벨 붙이기 실패(R2 수정 P1): 모음은 라벨 `초안` 으로만 초안 PR 을 알아본다 — 라벨이 없으면 PR 은 열렸는데 '발행 대기' 알림이 조용히 사라진다. 고정 문장(외부 글 없음)
WARN_LABELS = ("::warning::초안 PR 에 라벨을 붙이지 못했습니다 — 라벨이 없으면 확인 필요 모음이 그 PR 을 초안으로 알아보지 못해 발행 대기 알림이 가지 않을 수 있습니다. "
               "다음 실행이 라벨을 다시 붙여 봅니다. 이유는 로그의 바로 앞 줄에 있습니다.")
SUMMARY_LABELS = ("- 라벨: 라벨을 붙이지 못해 발행 대기 알림이 가지 않을 수 있습니다(다음 실행이 라벨을 다시 붙여 봅니다. "
                  "급하면 PR 화면에서 라벨 `초안`·`채널:Chance` 를 직접 붙이세요)")
INBOX_WORKFLOW = "ops-inbox.yml"          # 확인 필요 모음을 만드는 워크플로 파일(.github/workflows/ops-inbox.yml)
PR_SETTING_HINT = ("저장소 Settings → Actions → General 의 'Allow GitHub Actions to create and approve pull requests' 를 켜거나, "
                   "GitHub 화면에서 직접 PR 을 여세요(브랜치 화면의 'Compare & pull request'). 설정을 켜 두면 다음 실행(30분 안)이 PR 을 다시 열어 봅니다.")

# labeled: 열린 PR 의 라벨(초안·채널:Chance)이 붙었는가(R2 수정 P1). PR 을 열지 않은 결과에서는 뜻이 없어 True 로 둔다.
Result = namedtuple("Result", "status branch number detail code title labeled", defaults=(True,))


class DeliveryError(RuntimeError):
    """초안을 올리는 도중의 인프라 실패(글 파일 없음·push 실패 등). 종료 1."""


class GitError(RuntimeError):
    def __init__(self, args, returncode, detail):
        super().__init__(f"git {args[0] if args else ''} 실패(종료 {returncode}): {detail}")
        self.returncode, self.detail = returncode, detail


def truthy(value):
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


class Git:
    """git 하위 프로세스 래퍼. 프롬프트를 막고(GIT_TERMINAL_PROMPT=0), 출력의 비밀 값을 가리며, 커밋 작성자는 봇으로 둔다."""

    def __init__(self, cwd=None, env=None, secrets=()):
        self.cwd = str(cwd) if cwd else None
        # 경로 인자는 글 그대로 읽는다(GIT_LITERAL_PATHSPECS): AI 가 정한 분야 이름에 * ? [ 가 있어도 다른 파일과 맞춰 보지 않는다
        self.env = {**os.environ, **(env or {}), "GIT_TERMINAL_PROMPT": "0", "GIT_LITERAL_PATHSPECS": "1"}
        self.secrets = tuple(secrets)

    def run(self, *args, check=True):
        cmd = ["git", "-c", f"user.name={BOT_NAME}", "-c", f"user.email={BOT_EMAIL}", "-c", "commit.gpgsign=false", *args]
        try:
            proc = subprocess.run(cmd, cwd=self.cwd, env=self.env, capture_output=True, text=True, encoding="utf-8",
                                  errors="replace", timeout=GIT_TIMEOUT)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise GitError(args, None, type(exc).__name__) from None
        if check and proc.returncode != 0:
            raise GitError(args, proc.returncode, scrub(one_line(proc.stderr or proc.stdout, 300), self.secrets))
        return proc

    def path(self, rel):
        return Path(self.cwd or ".") / rel


# ----------------------------------------------------------------------------
# 원격 초안 브랜치
# ----------------------------------------------------------------------------
def ls_remote_drafts(git):
    """원격의 초안 브랜치 {이름: 커밋 해시}(ai/draft/ 아래 전부, 모르는 이름도 포함). 못 읽으면 GitError."""
    proc = git.run("ls-remote", "--heads", "origin", f"refs/heads/{drafts.BRANCH_PREFIX}*")
    found = {}
    for line in proc.stdout.splitlines():
        sha, _, ref = line.strip().partition("\t")
        if ref.startswith("refs/heads/") and re.fullmatch(r"[0-9a-f]{40,64}", sha):
            found[ref[len("refs/heads/"):]] = sha
    return found


def remote_branch_exists(name, git=None, out=print):
    """원격에 그 브랜치가 있나. True/False, 확인하지 못했으면 None(경고만 남기고 호출한 쪽이 이번 실행을 건너뛴다)."""
    git = git or Git()
    try:
        proc = git.run("ls-remote", "--heads", "origin", f"refs/heads/{name}")
    except GitError as exc:
        out("::warning::초안 브랜치를 확인하지 못했습니다(이번 실행은 건너뛰고 다음 실행에서 다시 확인합니다).")
        out(f"[초안] 브랜치 확인 실패: {one_line(exc, 300)}")
        return None
    return any(line.strip().partition("\t")[2] == f"refs/heads/{name}" for line in proc.stdout.splitlines())


# ----------------------------------------------------------------------------
# 이번 실행의 초안 찾기
# ----------------------------------------------------------------------------
def new_draft_entry(git):
    """이번 실행이 이력(history.json)에 더한 승인 흐름 항목(flow=pr) 중 마지막. 작업 트리의 이력에는 있고 HEAD 의 이력에는 없는 항목이다. 없으면 None."""
    work = read_json_list(git.path(HISTORY_PATH))
    proc = git.run("show", f"HEAD:{HISTORY_PATH}", check=False)
    try:
        head = json.loads(proc.stdout) if proc.returncode == 0 else []
    except ValueError:
        head = []
    head = head if isinstance(head, list) else []
    fresh = [e for e in work if isinstance(e, dict) and e.get("flow") == drafts.FLOW_PR and e not in head]
    return fresh[-1] if fresh else None


def check_entry(entry):
    """이력 항목이 승인 흐름 항목답게 생겼는지(브랜치 이름·글 파일 경로 둘). 아니면 DeliveryError."""
    paths = entry.get("paths")
    if drafts.parse_branch(entry.get("branch")) is None:
        raise DeliveryError("이력 항목의 초안 브랜치 이름이 올바르지 않습니다.")
    if not (isinstance(paths, list) and len(paths) == 2 and all(drafts.valid_post_path(p) for p in paths)):
        raise DeliveryError("이력 항목의 글 파일 경로가 올바르지 않습니다.")


def commit_title(entry, what):
    return f"🤖 {what}: {drafts.neutralize(entry.get('kr_title'), 60) or '제목 없음'} (승인 대기)"


# ----------------------------------------------------------------------------
# 요약
# ----------------------------------------------------------------------------
def write_summary(markdown, env=None, out=print):
    target = (os.environ if env is None else env).get("GITHUB_STEP_SUMMARY")
    if not target:
        return
    try:
        with open(target, "a", encoding="utf-8") as fh:
            fh.write(markdown.rstrip() + "\n\n")
    except OSError as exc:
        out(f"실행 요약 쓰기 실패(발행에는 영향 없음): {one_line(exc, 150)}")


def summary_lines(result, repo, titles=None, housekeeping=None, inbox=None):
    lines = ["### Chance 초안 승인 흐름"]
    if result.status == "opened":
        lines.append("- 결과: **DRAFT_OPENED** — 승인 PR 을 열었습니다. **병합하면 공개, 닫으면 폐기**입니다.")
        lines.append(f"- PR: {drafts.pull_url(repo, result.number)} · 브랜치 `{result.branch}`")
    elif result.status == "branch_only":
        lines.append(f"- 결과: **DRAFT_BRANCH_ONLY** — 브랜치 `{result.branch}` 가 push 됐고 PR 은 만들지 못했습니다({result.detail}).")
        lines.append(f"- 할 일: {PR_SETTING_HINT}")
        lines.append("- 만든 글은 잃지 않았습니다(초안 브랜치와 이력이 main 에 남아 있고, 같은 슬롯을 다시 만들지 않습니다).")
    elif result.status == "no_draft":
        lines.append("- 결과: **NO_DRAFT** — 이번 실행에서 만든 초안이 없습니다(건너뜀·후보 없음 등. 위 실행 요약의 결과 코드를 보세요).")
    else:
        lines.append(f"- 결과: **{result.status.upper()}** — {result.detail}")
    if titles:
        lines.append(f"- 제목: {titles}")
    if result.status == "opened" and not getattr(result, "labeled", True):      # R2 수정 P1: 라벨이 없으면 발행 대기 알림이 가지 않을 수 있다 — 성공처럼 보이지 않게 쉬운 말로 알린다
        lines.append(SUMMARY_LABELS)
    if housekeeping:
        lines.append("- 정리: " + " · ".join(housekeeping))
    if inbox is not None:      # R2-4: 모음 즉시 갱신 요청 결과(요청하지 않은 실행에서는 줄이 없다)
        lines.append("- 확인 필요 모음: " + ("바로 갱신하도록 요청했습니다(모음 이슈에 '초안 대기'가 곧 나타납니다)" if inbox else
                                       "바로 갱신하도록 요청하지 못했습니다(다음 정기 갱신 때 나타납니다)"))
    return "\n".join(lines)


# ----------------------------------------------------------------------------
# 초안 올리기
# ----------------------------------------------------------------------------
def current_branch(git):
    name = git.run("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    if not name or name == "HEAD":
        raise DeliveryError("현재 브랜치를 알 수 없습니다(detached HEAD). 기준 브랜치에 있어야 초안을 올릴 수 있습니다.")
    return name


def push_history(git, base, sleep, out):
    """이력 커밋을 기준 브랜치에 올린다. 거절되면 pull --rebase 후 다시(최대 PUSH_ATTEMPTS번). 끝내 안 되면 GitError."""
    for attempt in range(1, PUSH_ATTEMPTS + 1):
        proc = git.run("push", "origin", f"HEAD:refs/heads/{base}", check=False)
        if proc.returncode == 0:
            return
        detail = scrub(one_line(proc.stderr or proc.stdout, 300), git.secrets)
        if attempt == PUSH_ATTEMPTS:
            raise GitError(("push",), proc.returncode, detail)
        out(f"[초안] 이력 push 가 거절돼 최신 {base} 위로 다시 쌓습니다({attempt}/{PUSH_ATTEMPTS}): {detail}")
        pull = git.run("pull", "--rebase", "origin", base, check=False)
        if pull.returncode != 0:
            git.run("rebase", "--abort", check=False)
            raise GitError(("pull", "--rebase"), pull.returncode, scrub(one_line(pull.stderr or pull.stdout, 300), git.secrets))
        sleep(attempt * 5)


def open_pull_request(client, branch, base, title, body, sleep):
    """PR 을 연다(5xx·네트워크 오류는 재시도). 이미 같은 브랜치의 PR 이 있으면 그 번호를 돌려준다. 돌려주는 값: 번호."""
    try:
        return drafts.retry(lambda: client.create_pull_request(title, branch, base, body), sleep=sleep)
    except drafts.GitHubError as exc:
        if exc.already_exists:
            found = client.find_pull_request(branch)
            if found and isinstance(found.get("number"), int):
                return found["number"]
        raise


def attach_labels(client, number, out):
    """라벨 만들기·붙이기. 돌려주는 값: 붙였으면 True, 못 붙였으면 False(예외를 올리지 않는다).

    실패해도 PR 은 이미 열렸으니 발행에는 영향이 없다. 하지만 확인 필요 모음은 라벨 `초안` 으로만 초안 PR 을 알아보므로 라벨이 없으면 '발행 대기' 알림이 조용히 사라진다(R2 수정 P1).
    그래서 사유 한 줄(일반 로그)에 이어 고정 문장 ::warning:: 도 남기고(WARN_LABELS), 호출한 쪽이 결과를 받아 성공 문구와 모음 요청 여부를 정한다.
    다음 실행의 정리 단계(housekeeping)가 우리 라벨이 하나도 없는 열린 초안 PR 에 다시 붙인다."""
    try:
        for name, color, description in drafts.LABELS:
            client.ensure_label(name, color, description)
        client.add_labels(number, [name for name, _color, _desc in drafts.LABELS])
    except drafts.GitHubError as exc:
        out(f"[초안] 라벨을 붙이지 못했습니다(PR 은 열렸습니다): {one_line(exc, 200)}")
        out(WARN_LABELS)
        return False
    return True


def request_inbox_refresh(client, ref, out=print):
    """확인 필요 모음(ops-inbox.yml)을 지정한 브랜치에서 수동 실행 이벤트로 바로 돌린다. 돌려주는 값: 요청했으면 True, 못 했으면 False(예외를 올리지 않는다).

    승인 PR 을 연 직후에 부른다 — 저장소 기본 토큰이 연 PR·붙인 라벨은 모음 워크플로를 이벤트로 시작시키지 못해서, 부르지 않으면 '초안 대기'가 정기 갱신(보통 3–6시간)에야
    뜬다. 권한은 워크플로의 `actions: write`(Pages 배포 요청과 같은 권한)다. 실패해도(권한·설정·네트워크) 초안·PR 은 이미 올라갔으므로 경고만 남기고 다음 정기 갱신에 맡긴다."""
    try:
        client.dispatch_workflow(INBOX_WORKFLOW, ref)
    except drafts.GitHubError as exc:
        out(f"[초안] 확인 필요 모음을 바로 갱신하도록 요청하지 못했습니다: {failure_detail(exc)}")
        out(WARN_INBOX)
        return False
    out("[초안] 확인 필요 모음을 바로 갱신하도록 요청했습니다(초안 대기가 모음에 곧 나타납니다).")
    return True


def failure_detail(exc):
    """PR 열기 실패를 요약 한 줄로(상태 코드와 소독한 사유)."""
    return one_line(exc.message if isinstance(exc, drafts.GitHubError) else exc, 160)


def deliver(git, client, env, out=print, sleep=time.sleep):
    """이번 실행의 초안을 올리고 PR 을 연다. 돌려주는 값: Result. 인프라 실패는 DeliveryError·GitError 로 올린다."""
    entry = new_draft_entry(git)
    if entry is None:
        out("[초안] 이번 실행에서 만든 초안이 없습니다.")
        return Result("no_draft", None, None, "", 0, None)
    check_entry(entry)
    branch, paths = entry["branch"], entry["paths"]
    if not all(git.path(p).is_file() for p in paths):
        raise DeliveryError("이번 실행이 만든 글 파일을 작업 트리에서 찾지 못했습니다.")
    texts = [git.path(p).read_text(encoding="utf-8") for p in paths]      # 기준 브랜치로 돌아가면 작업 트리에서 사라지므로 먼저 읽는다
    base = current_branch(git)
    out(f"[초안] 초안 브랜치 {branch} 를 {base} 에서 만듭니다.")
    git.run("checkout", "-q", "-b", branch)
    git.run("add", "--", *paths)
    git.run("commit", "-q", "-m", commit_title(entry, "초안"))
    git.run("checkout", "-q", base)                                       # 이력 파일의 변경은 그대로 따라온다(글 파일은 초안 브랜치에만 있다)
    git.run("commit", "-q", "-m", commit_title(entry, "이력"), "--", HISTORY_PATH)
    git.run("push", "origin", f"refs/heads/{branch}:refs/heads/{branch}")
    out(f"[초안] 초안 브랜치 {branch} 를 올렸습니다.")
    try:
        push_history(git, base, sleep, out)
    except GitError:
        out("[초안] 이력을 올리지 못해 방금 올린 초안 브랜치를 지웁니다(이력 없는 초안이 남지 않게).")
        rollback = git.run("push", "origin", "--delete", branch, check=False)
        if rollback.returncode != 0:
            out(f"[초안] 초안 브랜치를 지우지 못했습니다(다음 실행이 같은 슬롯을 건너뜁니다): {scrub(one_line(rollback.stderr, 200), git.secrets)}")
        raise
    out(f"[초안] 이력을 {base} 에 올렸습니다.")
    owner = env.get("GITHUB_REPOSITORY_OWNER") or str(env.get("GITHUB_REPOSITORY", "")).split("/", 1)[0]
    title = drafts.build_pr_title(entry.get("kr_title"), entry.get("en_title"))
    body = drafts.build_pr_body(entry, texts[0], texts[1], owner=owner)
    shown = drafts.neutralize(entry.get("kr_title"), 120)
    try:
        number = open_pull_request(client, branch, base, title, body, sleep)
    except drafts.GitHubError as exc:
        out(f"[초안] PR 을 열지 못했습니다: {failure_detail(exc)}")
        return Result("branch_only", branch, None, failure_detail(exc), 1, shown)
    out(f"[초안] PR 을 열었습니다: {drafts.pull_url(client.repo, number)}")
    labeled = attach_labels(client, number, out)
    return Result("opened", branch, number, "", 0, shown, labeled)


# ----------------------------------------------------------------------------
# 남은 초안 정리
# ----------------------------------------------------------------------------
def history_entry_for(history, branch):
    for item in history:
        if isinstance(item, dict) and item.get("branch") == branch and item.get("flow") == drafts.FLOW_PR:
            return item
    return None


def reopen_pull_request(git, client, branch, entry, env, sleep, out):
    """PR 이 없는 초안 브랜치에 PR 을 다시 연다(글은 원격 브랜치에서 읽는다). 돌려주는 값: PR 번호."""
    paths = entry.get("paths")
    if not (isinstance(paths, list) and len(paths) == 2 and all(drafts.valid_post_path(p) for p in paths)):
        raise DeliveryError("이력 항목의 글 파일 경로가 올바르지 않습니다.")
    shallow = git.run("rev-parse", "--is-shallow-repository").stdout.strip() == "true"
    git.run("fetch", *(["--depth=1"] if shallow else []), "origin", f"refs/heads/{branch}")    # 얕은 복제(Actions)에서만 깊이를 제한한다
    texts = [git.run("show", f"FETCH_HEAD:{p}").stdout for p in paths]
    owner = env.get("GITHUB_REPOSITORY_OWNER") or str(env.get("GITHUB_REPOSITORY", "")).split("/", 1)[0]
    base = current_branch(git)
    number = open_pull_request(client, branch, base, drafts.build_pr_title(entry.get("kr_title"), entry.get("en_title")),
                               drafts.build_pr_body(entry, texts[0], texts[1], owner=owner), sleep)
    attach_labels(client, number, out)
    return number


def lacks_labels(pr):
    """열린 초안 PR 이 우리 라벨(초안·폐기·채널:…)을 하나도 달고 있지 않은가(R2 수정 P1). attach_labels 는 라벨 둘을 한 번에 붙이므로 '하나도 없음'이 붙이기 실패의 흔적이다.
    PR 목록이 라벨을 알려 주지 않았으면(labels 가 목록이 아님) 알 수 없으니 False — 모르는 채로 손대지 않는다. 운영자가 일부러 `초안` 만 떼고 `채널:…`·`폐기` 를 남긴 PR 도
    False 다(다시 붙이면 운영자가 한 일을 되돌린다). 열린 PR 이 아니거나 번호를 읽을 수 없어도 False."""
    number, labels = pr.get("number"), pr.get("labels")
    if pr.get("state") != "open" or isinstance(number, bool) or not isinstance(number, int) or not isinstance(labels, (list, tuple)):
        return False
    ours = (draft_labels.DRAFT_LABEL, draft_labels.DISCARD_LABEL)
    return not any(name in ours or str(name).startswith(draft_labels.CHANNEL_LABEL_PREFIX) for name in labels)


class _Tally:
    """out 으로 가는 줄을 그대로 넘기면서 라벨 경고(WARN_LABELS)가 몇 번 나갔는지 센다. reopen_pull_request 가 라벨 결과를 돌려주지 않아도 정리 단계가 그 실패를 알 수 있게 한다."""

    def __init__(self, out):
        self.out, self.label_failures = out, 0

    def __call__(self, text):
        if text == WARN_LABELS:
            self.label_failures += 1
        self.out(text)


def housekeeping(git, client, env, today, skip=(), out=print, sleep=time.sleep, stats=None):
    """남은 초안 정리. 돌려주는 값: (설명 문구 목록, 실패한 작업 수). 어떤 실패도 예외로 올리지 않는다.
    stats 가 사전이면 다시 연 PR 수를 stats['reopened'] 로, 이번 정리로 라벨이 붙어 모음이 알아볼 수 있게 된 PR 수(다시 연 PR 중 라벨이 붙은 것 + 라벨을 다시 붙인 것)를
    stats['labeled'] 로 알려 준다(호출한 쪽이 모음 즉시 갱신 여부를 정한다)."""
    notes, failures = [], 0
    try:
        remote = ls_remote_drafts(git)
        names = sorted(n for n in remote if n not in skip and drafts.parse_branch(n) is not None)
        if not names:
            return notes, failures
        prs = client.list_draft_pull_requests(state="all")
        history = read_json_list(git.path(HISTORY_PATH))
    except (GitError, drafts.GitHubError, StateError, OSError) as exc:
        out(f"[초안] 정리를 시작하지 못했습니다: {one_line(exc, 300)}")
        return ["정리 시작 실패(다음 실행에서 다시 시도)"], 1
    by_head = {}
    for pr in prs:                      # 최신순: 같은 브랜치의 PR 이 여럿이면 열린 것을 우선, 없으면 가장 최근 것
        head = pr["head_ref"]
        if head not in by_head or (pr["state"] == "open" and by_head[head]["state"] != "open"):
            by_head[head] = pr
    complete = bool(getattr(prs, "complete", False))   # 목록이 끝까지 다 읽히지 않았으면 'PR 이 안 보임'이 '없음'이라는 뜻이 아니다(PR 이 없다고 믿고 지우지 않는다)
    reopened = reopen_unlabeled = relabeled = relabel_failed = deleted = 0
    say = _Tally(out)                                  # 다시 연 PR 의 라벨 붙이기 실패를 세려고 reopen_pull_request 에만 넘긴다
    for name in names:
        age = (today - drafts.parse_branch(name).day).days
        pr = by_head.get(name)
        try:
            if pr is None and age <= drafts.ORPHAN_RETRY_DAYS:
                entry = history_entry_for(history, name)
                if entry is None:
                    out(f"[초안] {name}: PR 이 없지만 이력 항목이 없어 다시 열지 못합니다.")
                    continue
                failed_before = say.label_failures
                number = reopen_pull_request(git, client, name, entry, env, sleep, say)
                out(f"[초안] {name}: PR 을 다시 열었습니다: {drafts.pull_url(client.repo, number)}")
                reopened += 1
                if say.label_failures > failed_before:      # PR 은 다시 열렸지만 라벨이 안 붙었다 — 모음이 알아보지 못하니 실패로 센다(다음 실행의 아래 단계가 다시 붙인다)
                    failures += 1
                    reopen_unlabeled += 1
            elif age >= drafts.RETENTION_DAYS and (pr["state"] != "open" if pr is not None else complete):
                git.run("push", "origin", "--delete", name)
                out(f"[초안] {name}: {drafts.RETENTION_DAYS}일이 지나 지웠습니다({'PR 없음' if pr is None else '병합됨' if pr['merged'] else '닫힘'}).")
                deleted += 1
            elif pr is not None and lacks_labels(pr):        # 열린 PR 인데 우리 라벨이 하나도 없다: 라벨 붙이기가 한 번 실패한 PR 이 영영 무라벨로 남지 않게 다시 붙인다(R2 수정 P1)
                if attach_labels(client, pr["number"], out):
                    out(f"[초안] {name}: PR #{pr['number']} 에 라벨이 없어 다시 붙였습니다.")
                    relabeled += 1
                else:
                    failures += 1
                    relabel_failed += 1
        except (GitError, drafts.GitHubError, DeliveryError, OSError) as exc:
            failures += 1
            out(f"[초안] {name}: 정리 작업 실패: {one_line(exc, 300)}")
    if isinstance(stats, dict):
        stats["reopened"] = reopened
        stats["labeled"] = (reopened - reopen_unlabeled) + relabeled
    if reopened:
        notes.append(f"PR 다시 열기 {reopened}건")
    if relabeled:
        notes.append(f"라벨 다시 붙이기 {relabeled}건")
    if reopen_unlabeled + relabel_failed:
        notes.append(f"라벨을 붙이지 못한 PR {reopen_unlabeled + relabel_failed}건(발행 대기 알림이 가지 않을 수 있음)")
    if deleted:
        notes.append(f"오래된 브랜치 삭제 {deleted}건")
    if failures:
        notes.append(f"정리 실패 {failures}건(다음 실행에서 다시 시도)")
    return notes, failures


def request_inbox_refresh_safely(git, client, env, out=print):
    """모음 즉시 갱신 요청(request_inbox_refresh)을 부른다. 요청할 브랜치는 이번 실행이 초안을 올린 기준 브랜치(현재 브랜치, 못 읽으면 GITHUB_REF_NAME)다.
    어떤 오류도 이미 끝난 초안 올리기의 결과·종료 코드를 바꾸지 않는다(예상 밖 오류는 종류만 로그에 남긴다)."""
    try:
        try:
            ref = current_branch(git)
        except (GitError, DeliveryError):
            ref = str(env.get("GITHUB_REF_NAME", "")).strip()
            if not ref:
                out("[초안] 확인 필요 모음을 부를 브랜치를 알 수 없어 건너뜁니다(다음 정기 갱신 때 모음에 나타납니다).")
                return False
        return request_inbox_refresh(client, ref, out)
    except Exception as exc:  # noqa: BLE001 - 모음 즉시 갱신은 덤이다: 예상 밖 오류가 초안 올리기의 결과를 가리면 안 된다(오류 종류만 남긴다)
        out(f"[초안] 확인 필요 모음 즉시 갱신 중 예상 밖 오류: {type(exc).__name__}")
        out(WARN_INBOX)
        return False


# ----------------------------------------------------------------------------
# 진입점
# ----------------------------------------------------------------------------
def run(env=None, git=None, client=None, out=print, sleep=time.sleep, now=None):
    """deliver 의 전체 순서. 돌려주는 값: 종료 코드."""
    env = os.environ if env is None else env
    if str(env.get("PIPELINE_PAUSE", "")).strip().lower() in {"1", "true", "yes", "on"}:
        out("[일시정지] PIPELINE_PAUSE 가 켜져 있어 초안 올리기·정리를 하지 않습니다.")
        return 0
    flow = drafts.chance_flow()
    if flow != drafts.FLOW_PR:
        out("[초안] 발행 흐름이 direct 라 할 일이 없습니다.")
        return 0
    if truthy(env.get("DRY_RUN")):
        out("[DRY_RUN] 승인 흐름: 연습 실행이라 브랜치·PR 을 만들지 않습니다.")
        return 0
    token, repo = str(env.get("GITHUB_TOKEN", "")).strip(), str(env.get("GITHUB_REPOSITORY", "")).strip()
    if client is None and not (token and drafts.valid_repo(repo)):
        out("[로컬] GITHUB_TOKEN·GITHUB_REPOSITORY 가 없어 브랜치·PR 을 만들지 않습니다(Actions 에서만 올립니다).")
        return 0
    git = git or Git(secrets=(token,))
    client = client or drafts.GitHubClient(repo, token)
    now = now or datetime.now(KST)
    summary_env = env
    try:
        result = deliver(git, client, env, out, sleep)
    except (GitError, DeliveryError, StateError, OSError) as exc:
        out(f"작업 실패: {type(exc).__name__}: {one_line(exc, 400)}")
        write_summary("### Chance 초안 승인 흐름\n- 결과: **실패** — 초안을 올리지 못했습니다(원인은 이 단계의 로그를 보세요).", summary_env, out)
        return 1
    stats = {}
    try:
        notes, failures = housekeeping(git, client, env, now.astimezone(KST).date(), skip=(result.branch,) if result.branch else (), out=out,
                                       sleep=sleep, stats=stats)
    except Exception as exc:  # noqa: BLE001 - 정리는 부가 작업이다: 예상 밖 오류가 이미 끝난 초안 올리기의 결과를 가리면 안 된다(오류 종류는 로그에 남긴다)
        out(f"[초안] 정리 중 예상 밖 오류: {type(exc).__name__}: {one_line(exc, 300)}")
        notes, failures = ["정리 중 예상 밖 오류(다음 실행에서 다시 시도)"], 1
    inbox_refreshed = None
    delivered_visible = result.status == "opened" and getattr(result, "labeled", True)
    if delivered_visible or stats.get("labeled"):               # 라벨이 붙은 새 초안 PR 이 생겼을 때만(R2-4). PR 을 열지 못했거나(branch_only) 만든 초안이 없는 실행에서는 요청하지 않는다
        inbox_refreshed = request_inbox_refresh_safely(git, client, env, out)
    elif result.status == "opened" or stats.get("reopened"):    # R2 수정 P1: PR 은 열렸는데 라벨이 안 붙었다 — 모음은 라벨로 초안을 알아보니 지금 갱신해도 나타나지 않는다. 성공 문구 없이 이유만 남긴다
        out("[초안] 라벨이 붙지 않아 확인 필요 모음을 바로 갱신하도록 요청하지 않았습니다(라벨이 붙은 뒤의 점검에 나타납니다).")
    write_summary(summary_lines(result, client.repo, result.title, notes, inbox=inbox_refreshed), summary_env, out)
    if result.status == "branch_only":
        out(ERROR_PR_FAILED)
    if failures:
        out(WARN_HOUSEKEEPING)
    return result.code


def main(argv=None):
    safe_output()
    args = list(sys.argv[1:] if argv is None else argv)
    command = args[0] if args else ""
    if command == "flow":
        try:
            print(drafts.chance_flow())
        except drafts.DraftFlowError as exc:
            print(f"[오류] {exc}", file=sys.stderr)
            return 1
        return 0
    if command == "deliver":
        try:
            return run()
        except drafts.DraftFlowError as exc:
            print(f"[오류] {one_line(exc, 300)}")
            return 1
    print("사용법: python -m pipeline.draft_flow {flow|deliver}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
