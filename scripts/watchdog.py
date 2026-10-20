"""워치독: 발행 중단·반복 실패를 감지해 GitHub 이슈로 알린다.

사람은 평소에 아무 것도 하지 않는다. 문제가 생기면 이슈([Watchdog] ...)가 열려 알림이 가고,
해소되면 자동으로 닫힌다. 판단 규칙은 pipeline/health.py(순수 함수), 이 스크립트는 I/O만 맡는다.

필요 환경변수: GITHUB_TOKEN, GITHUB_REPOSITORY  (권한: contents:read, actions:read, issues:write)
옵션: WATCHDOG_DRY_RUN=1 이면 이슈를 만들지 않고 결과만 출력한다. 토큰이 없어도 dry-run 으로 동작한다.
"""
import json
import os
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.console import safe_output  # noqa: E402
from pipeline.health import Finding, evaluate  # noqa: E402
from pipeline.registry import ROOT, enabled_blogs, load_registry, validate_registry  # noqa: E402
from pipeline.state import StateError, read_json_list  # noqa: E402

LABEL = "watchdog"
TITLE_PREFIX = "[Watchdog]"


class GitHubClient:
    def __init__(self, token, repo, opener=urllib.request.urlopen):
        self.token, self.repo, self._open = token, repo, opener

    def _request(self, method, path, payload=None):
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(
            f"https://api.github.com{path}", data=data, method=method,
            headers={"Authorization": f"Bearer {self.token}", "Accept": "application/vnd.github+json",
                     "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "chanceblog-watchdog",
                     "Content-Type": "application/json"})
        with self._open(req, timeout=20) as resp:
            body = resp.read().decode("utf-8")
        return json.loads(body) if body else None

    def list_open_issues(self):
        items = self._request("GET", f"/repos/{self.repo}/issues?labels={LABEL}&state=open&per_page=50") or []
        return [i for i in items if "pull_request" not in i]

    def create_issue(self, title, body):
        return self._request("POST", f"/repos/{self.repo}/issues", {"title": title, "body": body, "labels": [LABEL]})

    def comment(self, number, body):
        return self._request("POST", f"/repos/{self.repo}/issues/{number}/comments", {"body": body})

    def close(self, number):
        return self._request("PATCH", f"/repos/{self.repo}/issues/{number}", {"state": "closed"})

    def workflow_runs(self, workflow_file):
        res = self._request(
            "GET", f"/repos/{self.repo}/actions/workflows/{workflow_file}/runs?per_page=10&status=completed")
        return (res or {}).get("workflow_runs", [])


def issue_body(finding):
    return (f"**블로그**: `{finding.blog}` / **코드**: `{finding.code}` / **심각도**: {finding.severity}\n\n"
            f"{finding.message}\n\n"
            "이 이슈는 워치독(`scripts/watchdog.py`)이 자동으로 만들었고, 문제가 해소되면 자동으로 닫힙니다.\n"
            "대응 절차: `HANDLER.md` §10, `docs/SECURITY_GUARDRAILS.md` 사고 대응 플레이북.\n"
            "일시 정지: 저장소 Settings → Variables 에 `PIPELINE_PAUSE=true` 를 추가하세요.")


def sync_issues(findings, open_issues, client, dry=False, out=print):
    """열려야 할 이슈는 만들고, 해소된 이슈는 닫는다. 같은 제목의 이슈는 중복 생성하지 않는다."""
    want = {f.title: f for f in findings}
    have = {i["title"]: i for i in open_issues if str(i.get("title", "")).startswith(TITLE_PREFIX)}
    created, closed = [], []
    for title, finding in want.items():
        if title in have:
            continue
        out(f"[알림 생성] {title}")
        if not dry:
            client.create_issue(title, issue_body(finding))
        created.append(title)
    for title, issue in have.items():
        if title in want:
            continue
        out(f"[알림 해소] {title}")
        if not dry:
            client.comment(issue["number"], "조건이 해소되어 자동으로 닫습니다.")
            client.close(issue["number"])
        closed.append(title)
    return created, closed


def last_commit_time(root, path):
    try:
        res = subprocess.run(["git", "log", "-1", "--format=%cI", "--", path], cwd=root,
                             capture_output=True, text=True, check=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    value = res.stdout.strip()
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def collect_findings(reg, root, now, client=None):
    findings = []
    for blog in enabled_blogs(reg):
        try:
            history = read_json_list(Path(root) / blog["state"]["history"])
        except StateError as exc:
            findings.append(Finding(blog["key"], "STATE_CORRUPT", "critical", str(exc)))
            continue
        runs = []
        if client is not None:
            try:
                runs = client.workflow_runs(Path(blog["workflow"]).name)
            except Exception as exc:  # noqa: BLE001 - 실행 이력 조회 실패는 다른 검사를 막지 않는다
                print(f"[참고] {blog['key']} 워크플로 실행 이력 조회 실패: {exc}")
        findings.extend(evaluate(blog, history, now,
                                 last_content_commit=last_commit_time(root, blog["state"]["content_dir"]),
                                 recent_runs=runs))
    return findings


def main():
    safe_output()
    reg = load_registry()
    errors = validate_registry(reg, ROOT)
    if errors:
        print("[오류] 레지스트리 검증 실패:\n  - " + "\n  - ".join(errors))
        return 1
    token, repo = os.environ.get("GITHUB_TOKEN"), os.environ.get("GITHUB_REPOSITORY")
    dry = os.environ.get("WATCHDOG_DRY_RUN", "").lower() in ("1", "true", "yes") or not (token and repo)
    client = GitHubClient(token, repo) if token and repo else None
    findings = collect_findings(reg, ROOT, datetime.now(timezone.utc), client)
    for f in findings:
        print(f"- {f.severity.upper():<8} {f.title} — {f.message}")
    if not findings:
        print("이상 없음")
    if client is None:
        print("(토큰/저장소 정보가 없어 dry-run 으로 종료)")
        return 0
    sync_issues(findings, client.list_open_issues(), client, dry=dry)
    return 0


if __name__ == "__main__":
    sys.exit(main())
