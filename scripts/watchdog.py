"""워치독: 발행 중단·반복 실패를 감지해 GitHub 이슈로 알린다.

사람은 평소에 아무 것도 하지 않는다. 문제가 생기면 이슈([Watchdog] ...)가 열려 알림이 가고,
해소되면 자동으로 닫힌다. 판단 규칙은 pipeline/health.py(순수 함수), 이 스크립트는 I/O만 맡는다.

필요 환경변수: GITHUB_TOKEN, GITHUB_REPOSITORY  (권한: contents:read, actions:read, issues:write)
옵션: WATCHDOG_DRY_RUN=1 이면 이슈를 만들지 않고 결과만 출력한다. 토큰이 없어도 dry-run 으로 동작한다.
      PIPELINE_PAUSE=true 이면 알림을 만들지 않는다(운영자가 일부러 멈춘 동안의 소음 방지).

알림 방식: (블로그, 코드)마다 이슈 하나를 유지한다. 저장소 소유자에게 담당자 지정과 @멘션을 붙이고,
열려 있는 동안 본문을 최신 내용으로 갱신하며, 심각 건은 며칠이 지나도 풀리지 않으면 코멘트로 다시 알린다.
이 실행(워크플로)은 '새로 생긴 심각 건'이 있을 때만 실패(빨강)로 끝나 Actions 실패 알림도 간다.
"""
import json
import os
import re
import subprocess
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.console import safe_output  # noqa: E402
from pipeline.health import Finding, entry_time, evaluate  # noqa: E402
from pipeline.registry import ROOT, enabled_blogs, load_registry, validate_registry  # noqa: E402
from pipeline.state import KST, StateError, read_json_list  # noqa: E402

LABEL = "watchdog"
TITLE_PREFIX = "[Watchdog]"
RENOTIFY_HOURS = 48          # 심각 건이 이만큼 지나도 열려 있으면 코멘트로 다시 알린다
MAX_NEW_ISSUES_PER_RUN = 5   # 한 번에 이슈가 쏟아지는 것을 막는다(나머지는 다음 실행에서)
PAGES_WORKFLOW = "pages.yml"
_NOTIFIED_RX = re.compile(r"<!--\s*watchdog:notified=(\S+?)\s*-->")


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

    def create_issue(self, title, body, assignees=None):
        payload = {"title": title, "body": body, "labels": [LABEL]}
        if assignees:
            payload["assignees"] = list(assignees)
        return self._request("POST", f"/repos/{self.repo}/issues", payload)

    def update_body(self, number, body):
        return self._request("PATCH", f"/repos/{self.repo}/issues/{number}", {"body": body})

    def comment(self, number, body):
        return self._request("POST", f"/repos/{self.repo}/issues/{number}/comments", {"body": body})

    def close(self, number):
        return self._request("PATCH", f"/repos/{self.repo}/issues/{number}", {"state": "closed"})

    def workflow_runs(self, workflow_file):
        res = self._request(
            "GET", f"/repos/{self.repo}/actions/workflows/{workflow_file}/runs?per_page=10&status=completed")
        return (res or {}).get("workflow_runs", [])


def issue_body(finding, owner=None, notified=None):
    """이슈 본문. owner 가 있으면 @멘션(알림이 가도록), notified 는 마지막으로 알린 시각(재알림 판단용 표식)."""
    mention = f"@{owner} " if owner else ""
    lines = [f"{mention}**블로그**: `{finding.blog}` / **코드**: `{finding.code}` / **심각도**: {finding.severity}", "",
             finding.message, "",
             "이 이슈는 워치독(`scripts/watchdog.py`)이 자동으로 만들었고, 열려 있는 동안 내용을 갱신하며 "
             "문제가 해소되면 자동으로 닫힙니다.",
             "대응 절차: `HANDLER.md` §10, `docs/SECURITY_GUARDRAILS.md` 사고 대응 플레이북.",
             "일시 정지(Chance·Blogger 모두): 저장소 Settings → Secrets and variables → Actions → Variables 에 "
             "`PIPELINE_PAUSE=true` 를 추가하세요. 정지 중에는 워치독도 알리지 않습니다."]
    if notified:
        lines += ["", f"<!-- watchdog:notified={notified} -->"]
    return "\n".join(lines)


def _notified_at(issue):
    """본문 표식에서 마지막 알림 시각을 읽는다. 없으면 이슈를 연 시각."""
    match = _NOTIFIED_RX.search(str(issue.get("body") or ""))
    for value in ((match.group(1) if match else None), issue.get("created_at")):
        if not value:
            continue
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def sync_issues(findings, open_issues, client, dry=False, out=print, owner=None, now=None,
                renotify_hours=RENOTIFY_HOURS, max_new=MAX_NEW_ISSUES_PER_RUN):
    """열려야 할 이슈는 만들고(담당자·@멘션), 열린 이슈는 본문을 갱신하며, 해소된 이슈는 닫는다.
    같은 제목의 이슈는 중복 생성하지 않는다. 돌려주는 값: (created, closed, renotified, new_critical).
    new_critical 은 이번 실행에서 처음 만든 심각 건의 제목 — 워크플로를 빨갛게 만드는 기준이다."""
    now = now or datetime.now(timezone.utc)
    want = {f.title: f for f in findings}
    have = {i["title"]: i for i in open_issues if str(i.get("title", "")).startswith(TITLE_PREFIX)}
    created, closed, renotified, new_critical, deferred = [], [], [], [], []
    for title, finding in want.items():
        issue = have.get(title)
        if issue is None:
            if len(created) >= max_new:
                deferred.append(title)
                continue
            out(f"[알림 생성] {title}")
            if not dry:
                client.create_issue(title, issue_body(finding, owner, now.isoformat(timespec="seconds")),
                                    assignees=[owner] if owner else None)
            created.append(title)
            if finding.severity == "critical":
                new_critical.append(title)
            continue
        # 이미 열려 있음: 오래 풀리지 않은 심각 건은 다시 알리고, 아니면 내용이 바뀐 경우에만 본문을 갱신한다.
        last = _notified_at(issue)
        due = (finding.severity == "critical" and last is not None
               and now - last >= timedelta(hours=renotify_hours))
        stamp = now.isoformat(timespec="seconds") if due else (last.isoformat(timespec="seconds") if last else None)
        body = issue_body(finding, owner, stamp)
        if due:
            out(f"[재알림] {title}")
            if not dry:
                days = max(1, int((now - last).total_seconds() // 86400))
                mention = f"@{owner} " if owner else ""
                client.comment(issue["number"], f"{mention}아직 해결되지 않았습니다(마지막 알림 {days}일 전). {finding.message}")
            renotified.append(title)
        if due or str(issue.get("body") or "").strip() != body.strip():
            if not dry and hasattr(client, "update_body"):
                client.update_body(issue["number"], body)
    for title, issue in have.items():
        if title in want:
            continue
        out(f"[알림 해소] {title}")
        if not dry:
            client.comment(issue["number"], "조건이 해소되어 자동으로 닫습니다.")
            client.close(issue["number"])
        closed.append(title)
    for title in deferred:
        out(f"::warning::새 이슈가 한 번에 너무 많아 다음 실행으로 미룹니다: {title}")
    return created, closed, renotified, new_critical


def last_commit_time(root, path, added_only=False):
    """path 를 건드린 마지막 커밋 시각. added_only 면 '파일이 새로 추가된' 커밋만 센다
    (이미지 교체처럼 기존 글만 고친 커밋을 '새 글'로 오해하지 않기 위해)."""
    times = commit_times(root, path, added_only=added_only, limit=1)
    return times[0] if times else None


def commit_times(root, path, added_only=False, limit=None, since="30 days ago"):
    """path 를 건드린 커밋 시각 목록(최신순). git 을 못 쓰면 빈 목록."""
    cmd = ["git", "log", f"--since={since}", "--format=%cI"]
    if added_only:
        cmd.append("--diff-filter=A")
    if limit:
        cmd.append(f"-{int(limit)}")
    try:
        res = subprocess.run(cmd + ["--", path], cwd=root, capture_output=True, text=True, check=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return []
    out = []
    for line in res.stdout.splitlines():
        try:
            out.append(datetime.fromisoformat(line.strip()))
        except ValueError:
            continue
    return out


def collect(reg, root, now, client=None):
    """(문제 목록, 블로그별 현황). 현황은 실행 요약 표에 쓴다(마지막 글 시각, 최근 7일 글 수)."""
    findings, stats = [], []
    pages_runs = None
    if client is not None:
        try:
            pages_runs = client.workflow_runs(PAGES_WORKFLOW)
        except Exception as exc:  # noqa: BLE001 - 조회 실패는 배포 검사만 건너뛰고 다른 검사를 막지 않는다
            print(f"[참고] Pages 워크플로 실행 이력 조회 실패(배포 검사 건너뜀): {exc}")
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
        content_dir = blog["state"]["content_dir"]
        if blog.get("platform") == "jekyll-git":
            # 글 파일이 '추가된' 커밋만 새 글로 센다(이미지 교체 커밋은 새 글이 아니다).
            added = commit_times(root, content_dir, added_only=True)
            last_content = max(added) if added else None
            post_days = {t.astimezone(KST).date() for t in added}
            posts_7d = sum(1 for t in added if now - t <= timedelta(days=7))
            last_post = last_content
            pages = pages_runs
        else:
            last_content = last_commit_time(root, content_dir)
            post_days = None
            real = [h for h in history if isinstance(h, dict) and h.get("status", "posted") in ("posted", "draft_uploaded")]
            times = [e for e in (entry_time(h) for h in real) if e]
            posts_7d = sum(1 for t in times if now - t <= timedelta(days=7))
            last_post = max(times) if times else None
            pages = None
        blog_findings = evaluate(blog, history, now, last_content_commit=last_content, recent_runs=runs,
                                 post_days=post_days, pages_runs=pages)
        findings.extend(blog_findings)
        stats.append({"key": blog["key"], "mode": blog.get("mode"), "last_post": last_post, "posts_7d": posts_7d,
                      "codes": [f.code for f in blog_findings]})
    return findings, stats


def collect_findings(reg, root, now, client=None):
    return collect(reg, root, now, client)[0]


def render_summary(stats, findings, created, closed, renotified, open_issues=()):
    """Actions 실행 요약(마크다운). 건수·시각·코드만 쓴다(수익·방문 수치와 비밀은 쓰지 않는다, G-O7)."""
    lines = ["### 워치독 점검 결과", ""]
    if not findings:
        lines.append("- 이상 없음")
    for f in findings:
        lines.append(f"- **{f.severity.upper()}** `{f.title}` — {' '.join(f.message.split())[:300]}")
    lines += ["", "| 블로그 | 모드 | 마지막 글(KST) | 최근 7일 글 수 | 이번 점검 결과 |", "|---|---|---|---|---|"]
    for s in stats:
        last = s["last_post"].astimezone(KST).strftime("%Y-%m-%d %H:%M") if s["last_post"] else "없음"
        lines.append(f"| {s['key']} | {s['mode']} | {last} | {s['posts_7d']} | {', '.join(s['codes']) or '정상'} |")
    if created or closed or renotified:
        lines.append("")
        lines += [f"- 이슈 생성: {title}" for title in created]
        lines += [f"- 이슈 재알림: {title}" for title in renotified]
        lines += [f"- 이슈 해소: {title}" for title in closed]
    opened = [f"#{i.get('number')} {i.get('title')}" for i in open_issues]
    if opened:
        lines += ["", "열려 있는 워치독 이슈: " + "; ".join(opened)]
    return "\n".join(lines)


def _write_summary(markdown):
    target = os.environ.get("GITHUB_STEP_SUMMARY")
    if not target:
        return
    try:
        with open(target, "a", encoding="utf-8") as fh:
            fh.write(markdown.rstrip() + "\n\n")
    except OSError as exc:
        print(f"실행 요약 쓰기 실패(점검 결과에는 영향 없음): {exc}")


def main():
    safe_output()
    reg = load_registry()
    errors = validate_registry(reg, ROOT)
    if errors:
        print("[오류] 레지스트리 검증 실패:\n  - " + "\n  - ".join(errors))
        return 1
    if os.environ.get("PIPELINE_PAUSE", "").strip().lower() in ("1", "true", "yes", "on"):
        print("[일시정지] PIPELINE_PAUSE 가 켜져 있어 점검 알림을 만들지 않습니다.")
        _write_summary("### 워치독 점검 결과\n- **일시정지** — 저장소 변수 PIPELINE_PAUSE 가 켜져 있어 알림을 만들지 않았습니다.")
        return 0
    token, repo = os.environ.get("GITHUB_TOKEN"), os.environ.get("GITHUB_REPOSITORY")
    dry = os.environ.get("WATCHDOG_DRY_RUN", "").lower() in ("1", "true", "yes") or not (token and repo)
    client = GitHubClient(token, repo) if token and repo else None
    owner = os.environ.get("GITHUB_REPOSITORY_OWNER") or (repo.split("/")[0] if repo and "/" in repo else None)
    now = datetime.now(timezone.utc)
    findings, stats = collect(reg, ROOT, now, client)
    for f in findings:
        print(f"- {f.severity.upper():<8} {f.title} — {f.message}")
    if not findings:
        print("이상 없음")
    if client is None:
        print("(토큰/저장소 정보가 없어 dry-run 으로 종료)")
        _write_summary(render_summary(stats, findings, [], [], []))
        return 0
    open_issues = client.list_open_issues()
    created, closed, renotified, new_critical = sync_issues(findings, open_issues, client, dry=dry,
                                                            owner=owner, now=now)
    _write_summary(render_summary(stats, findings, created, closed, renotified, open_issues))
    for f in findings:
        if f.severity == "warning":
            print(f"::warning::{f.title}: {' '.join(f.message.split())[:200]}")
    if new_critical and not dry:
        # 감시 실행이 항상 초록이면 Actions 실패 알림이 가지 않는다. 새로 생긴 심각 건만 빨갛게 한다(지속 중인 건은 초록).
        print("::error::새로 생긴 심각 건: " + ", ".join(new_critical))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
