"""워치독 테스트 공용 도구: 임시 git 저장소, 가짜 GitHub(이슈·워크플로 실행), KST 시각 만들기.

네트워크·실제 시크릿 없이 돈다. git 은 임시 디렉터리 안에서만 쓰고, 서명·사용자 설정은 명령행으로 넣어
이 PC의 git 설정에 기대지 않는다. git 프로세스 하나를 띄우는 데 0.3초 넘게 걸리는 PC가 있어서, 여러 커밋이 필요한
저장소는 add/commit 을 되풀이하지 않고 `git fast-import` 한 번으로 만든다(build_repo).
"""
import io
import subprocess
import urllib.error
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

import _bootstrap
from pipeline.state import KST

WORKFLOW_DIR = _bootstrap.ROOT / ".github" / "workflows"


def kst_time(day, hour=0, minute=0):
    """KST 달력 날짜 day 의 hour:minute 를 UTC aware 시각으로 돌려준다."""
    return datetime.combine(day, time(hour, minute), tzinfo=KST).astimezone(timezone.utc)


def today_kst():
    return datetime.now(KST).date()


def iso_z(when):
    """GitHub API 가 주는 모양('2026-10-24T01:02:03Z')의 시각 문자열."""
    return when.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_record(conclusion, created, head_branch="main"):
    """워크플로 실행 한 건(GitHub API 응답에서 워치독이 읽는 필드만)."""
    return {"conclusion": conclusion, "created_at": iso_z(created), "head_branch": head_branch}


# ---- 임시 git 저장소 -----------------------------------------------------------------------

def git(root, *args):
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", "-c", "commit.gpgsign=false", *args],
        cwd=root, check=True, capture_output=True, text=True, encoding="utf-8", errors="replace")


def raw_date(when):
    """git 의 raw 날짜 모양 '<epoch> <±HHMM>'. when 은 aware datetime(오프셋 보존) 또는 이미 그 모양의 문자열."""
    if isinstance(when, str):
        return when
    minutes = int((when.utcoffset() or timedelta(0)).total_seconds() // 60)
    sign = "-" if minutes < 0 else "+"
    return f"{int(when.timestamp())} {sign}{abs(minutes) // 60:02d}{abs(minutes) % 60:02d}"


def build_repo(root, commits):
    """root 에 git 저장소(브랜치 main)를 만들고 commits 를 오래된 순으로 쌓는다. 프로세스는 init 과 fast-import 둘뿐이다.

    commits: [(시각, {상대경로: 내용}, 메시지), ...]. 시각은 raw_date 가 받는 값(커밋 시각과 작성 시각에 같이 쓴다).
    파일은 커밋에만 들어가고 작업 트리에는 나오지 않는다(이력만 읽는 테스트용) — 작업 트리가 필요하면 직접 쓴다.
    """
    git(root, "init", "-q", "-b", "main")
    stream = bytearray()
    for when, files, message in commits:
        who = f"t <t@example.com> {raw_date(when)}".encode("utf-8")
        msg = message.encode("utf-8")
        stream += b"commit refs/heads/main\nauthor " + who + b"\ncommitter " + who + b"\n"
        stream += f"data {len(msg)}\n".encode("ascii") + msg + b"\n"
        for path, content in files.items():
            body = content.encode("utf-8")
            stream += f"M 100644 inline {path}\ndata {len(body)}\n".encode("utf-8") + body + b"\n"
        stream += b"\n"
    subprocess.run(["git", "fast-import", "--quiet", "--date-format=raw"], cwd=root, input=bytes(stream),
                   check=True, capture_output=True)


def shallow_clone(source, dest, depth=1):
    """source 저장소의 얕은 복제를 dest 에 만든다(file:// 주소여야 --depth 가 적용된다)."""
    subprocess.run(["git", "clone", "-q", f"--depth={depth}", Path(source).resolve().as_uri(), str(dest)],
                   check=True, capture_output=True, text=True, encoding="utf-8", errors="replace")


def canned_commit_times(times):
    """git 대신 정해 둔 글 커밋 시각(최신순)을 돌려주는 commit_times 대체품 — GitHub 쪽 동작을 보는 테스트가
    git 프로세스를 띄우지 않게 한다. times 목록은 호출할 때마다 읽으므로 테스트가 중간에 바꿔도 된다."""
    def fake(root, path, added_only=False, limit=None, since="30 days ago"):
        ordered = sorted(times, reverse=True)
        return ordered[:limit] if limit else ordered
    return fake


# ---- 가짜 GitHub -----------------------------------------------------------------------------

def http_error(code):
    return urllib.error.HTTPError("https://api.github.com/x", code, "error", {}, io.BytesIO(b"{}"))


class FakeGitHub:
    """scripts/watchdog.py 의 GitHubClient 를 흉내 내는 메모리 속 가짜. 모든 호출을 calls 에 기록한다.

    - runs: {워크플로 파일명: [실행, ...]}(최신순, run_record 모양). workflow_runs(branch=...) 를 주면
      head_branch 가 같은 실행만 돌려준다(head_branch 가 없으면 main 으로 본다).
    - 저장소 .github/workflows 에 없는 워크플로 파일명을 물으면 실제 GitHub 처럼 404 를 낸다(이름 오타 방지).
    - crlf=True 면 이슈 본문을 CRLF 로 저장한다(사람이 웹에서 고치면 그렇게 저장된다).
    - reject_assignees=True 면 담당자가 있는 이슈 생성을 HTTP 422 로 거절한다.
    - now: 새 이슈의 created_at 으로 쓰는 시각.
    """

    def __init__(self, runs=None, crlf=False, reject_assignees=False, now=None):
        self.runs = dict(runs or {})
        self.crlf, self.reject_assignees = crlf, reject_assignees
        self.now = now or datetime.now(timezone.utc)
        self.issues, self.calls, self.runs_asked = {}, [], []
        self._next = 100

    def _store(self, body):
        return body.replace("\r\n", "\n").replace("\n", "\r\n") if self.crlf else body

    def add_issue(self, title, body, created_at=None, number=None):
        """이미 열려 있는 이슈를 미리 넣어 둔다(번호를 돌려준다)."""
        if number is None:
            self._next += 1
            number = self._next
        self.issues[number] = {"number": number, "title": title, "body": self._store(body), "state": "open",
                               "created_at": iso_z(created_at or self.now), "assignees": [], "comments": []}
        return number

    # ---- GitHubClient 와 같은 메서드 ----
    def list_open_issues(self):
        self.calls.append(("list",))
        return [dict(i) for i in self.issues.values() if i["state"] == "open"]

    def create_issue(self, title, body, assignees=None):
        if assignees and self.reject_assignees:
            self.calls.append(("create-rejected", title))
            raise http_error(422)
        number = self.add_issue(title, body, created_at=self.now)
        self.issues[number]["assignees"] = list(assignees or [])
        self.calls.append(("create", title))
        return dict(self.issues[number])

    def update_body(self, number, body):
        self.issues[number]["body"] = self._store(body)
        self.calls.append(("patch", number))

    def comment(self, number, body):
        self.issues[number]["comments"].append(body)
        self.calls.append(("comment", number))

    def close(self, number):
        self.issues[number]["state"] = "closed"
        self.calls.append(("close", number))

    def workflow_runs(self, workflow_file, branch=None):
        self.runs_asked.append((workflow_file, branch))
        if not (WORKFLOW_DIR / workflow_file).is_file():
            raise http_error(404)
        runs = self.runs.get(workflow_file, [])
        if branch:
            runs = [r for r in runs if r.get("head_branch", "main") == branch]
        return list(runs)

    # ---- 테스트 편의 ----
    def verbs(self):
        """읽기(list)를 뺀, 이슈를 바꾼 호출의 동작 이름 목록."""
        return [c[0] for c in self.calls if c[0] != "list"]

    def open_issue_titles(self):
        return sorted(i["title"] for i in self.issues.values() if i["state"] == "open")
