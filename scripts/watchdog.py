"""워치독: 발행 중단·반복 실패를 감지해 GitHub 이슈로 알린다.

사람은 평소에 아무 것도 하지 않는다. 문제가 생기면 이슈([Watchdog] ...)가 열려 알림이 가고,
해소되면 자동으로 닫힌다. 판단 규칙은 pipeline/health.py(순수 함수), 이 스크립트는 I/O만 맡는다.

필요 환경변수: GITHUB_TOKEN, GITHUB_REPOSITORY  (권한: contents:read, actions:read, pull-requests:read, issues:write)
옵션: WATCHDOG_DRY_RUN=1 이면 이슈를 만들지 않고 결과만 출력한다. 토큰이 없어도 dry-run 으로 동작한다.
      PIPELINE_PAUSE=true 이면 알림을 만들지 않는다(운영자가 일부러 멈춘 동안의 소음 방지).

알림 방식: (블로그, 코드)마다 이슈 하나를 유지한다. 저장소 소유자에게 담당자 지정과 @멘션을 붙이고,
열려 있는 동안 본문을 최신 내용으로 갱신하며, 심각 건은 며칠이 지나도 풀리지 않으면 코멘트로 다시 알린다.
이 실행(워크플로)은 '새로 생긴 심각 건'이 있을 때만 실패(빨강)로 끝나 Actions 실패 알림도 간다.

글 커밋 시각은 git 이력에서 읽으므로 워크플로의 checkout 은 fetch-depth: 0 이어야 한다. 얕은 복제면 가장 위 커밋이
모든 파일을 '새로 추가'한 것처럼 보이므로, ::warning:: 을 내고 git 기반 판정은 건너뛴다(이력 파일 기반 판정만 한다).
"""
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
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
PAGES_BRANCH = "main"        # 다른 ref 에서 workflow_dispatch 로 돌린 성공 실행은 '사이트 배포됨'이 아니다
_NOTIFIED_RX = re.compile(r"<!--\s*watchdog:notified=(\S+?)\s*-->")
_SEVERITY_RANK = {"critical": 0, "warning": 1}   # 새 이슈를 만드는 순서(작을수록 먼저)


def _oneline(text):
    """줄바꿈·연속 공백(유니코드 줄 구분자 포함)을 한 칸 공백으로 접는다.
    로그 줄이 '::' 로 시작해 Actions 워크플로 명령으로 해석되는 것을 막는다(외부·이력 텍스트는 접어서 출력)."""
    return " ".join(str(text).split())


def _inert(text):
    """이슈 본문·코멘트에 인용하는 자유 텍스트(사유·오류 메시지 등)를 무해하게 만든다.
    '@' 는 전각 '＠'(U+FF20)로 바꿔 다른 사람에게 멘션 알림이 가지 않게 하고, '<' 는 전각 '＜'(U+FF1C)로 바꿔
    HTML 주석(<!--)으로 재알림 표식(watchdog:notified)을 위조하는 것을 막는다. 멘션·표식은 이 모듈이 직접 붙인다."""
    return str(text).replace("@", "\N{FULLWIDTH COMMERCIAL AT}").replace("<", "\N{FULLWIDTH LESS-THAN SIGN}")


def _same_text(text):
    """본문 비교용: 줄 끝을 \\n 으로 통일하고 앞뒤 공백을 뗀다(웹에서 고치면 CRLF 로 저장된다)."""
    return re.sub(r"\r\n?", "\n", str(text or "")).strip()


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

    def list_open_draft_pulls(self):
        """승인 흐름(publish_flow: pr)에서 열려 있는 초안 PR(이 저장소의 ai/draft/… 브랜치에서 연 것): [{'number', 'created_at'}, ...].
        포크의 PR 은 뺀다. 읽기 전용(권한 pull-requests: read)."""
        items = self._request("GET", f"/repos/{self.repo}/pulls?state=open&per_page=100") or []
        found = []
        for pr in items:
            head = pr.get("head") if isinstance(pr, dict) and isinstance(pr.get("head"), dict) else {}
            repo = head.get("repo") if isinstance(head.get("repo"), dict) else {}
            if (str(head.get("ref") or "").startswith("ai/draft/")
                    and str(repo.get("full_name") or "").lower() == str(self.repo).lower()):
                found.append({"number": pr.get("number"), "created_at": pr.get("created_at")})
        return found

    def workflow_runs(self, workflow_file, branch=None):
        """워크플로의 최근 완료 실행(최신순). branch 를 주면 그 브랜치에서 돈 실행만 받는다."""
        path = f"/repos/{self.repo}/actions/workflows/{workflow_file}/runs?per_page=10&status=completed"
        if branch:
            path += f"&branch={urllib.parse.quote(branch, safe='')}"
        res = self._request("GET", path)
        return (res or {}).get("workflow_runs", [])


def issue_body(finding, owner=None, notified=None):
    """이슈 본문. owner 가 있으면 @멘션(알림이 가도록), notified 는 마지막으로 알린 시각(재알림 판단용 표식).
    표식은 본문 맨 끝에 붙인다. 문제 설명(finding.message)에는 이력에서 인용한 자유 텍스트가 들어갈 수 있어
    @멘션과 HTML 주석을 무력화해서 싣는다(_inert)."""
    mention = f"@{owner} " if owner else ""
    lines = [f"{mention}**블로그**: `{finding.blog}` / **코드**: `{finding.code}` / **심각도**: {finding.severity}", "",
             _inert(finding.message), "",
             "이 이슈는 워치독(`scripts/watchdog.py`)이 자동으로 만들었고, 열려 있는 동안 내용을 갱신하며 "
             "문제가 해소되면 자동으로 닫힙니다.",
             "대응 절차: `HANDLER.md` §10, `docs/SECURITY_GUARDRAILS.md` 사고 대응 플레이북.",
             "일시 정지(Chance·Blogger 모두): 저장소 Settings → Secrets and variables → Actions → Variables 에 "
             "`PIPELINE_PAUSE=true` 를 추가하세요. 정지 중에는 워치독도 알리지 않습니다."]
    if notified:
        lines += ["", f"<!-- watchdog:notified={notified} -->"]
    return "\n".join(lines)


def _notified_at(issue):
    """본문 표식에서 마지막 알림 시각을 읽는다. 없으면 이슈를 연 시각, 그것도 없으면 None.
    표식은 본문 맨 끝에 붙으므로 '마지막' 일치를 쓴다(앞쪽 같은 모양은 인용된 텍스트일 수 있다)."""
    marks = _NOTIFIED_RX.findall(str(issue.get("body") or ""))
    for value in ((marks[-1] if marks else None), issue.get("created_at")):
        if not value:
            continue
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _create_issue(client, title, body, owner, out):
    """이슈를 만든다. 담당자 지정이 거부되면(HTTP 422) 담당자 없이 한 번 더 만든다 — 담당자 하나 때문에
    알림 자체가 사라지면 안 된다(본문의 @멘션으로 알림은 간다). 그 밖의 오류는 그대로 올려 실행을 빨갛게 한다."""
    try:
        return client.create_issue(title, body, assignees=[owner] if owner else None)
    except urllib.error.HTTPError as exc:
        if not owner or exc.code != 422:
            raise
        out(f"::warning::담당자({owner}) 지정이 거부되어(HTTP 422) 담당자 없이 이슈를 만듭니다: {title}")
    return client.create_issue(title, body, assignees=None)


def sync_issues(findings, open_issues, client, dry=False, out=print, owner=None, now=None,
                renotify_hours=RENOTIFY_HOURS, max_new=MAX_NEW_ISSUES_PER_RUN):
    """열려야 할 이슈는 만들고(담당자·@멘션), 열린 이슈는 본문을 갱신하며, 해소된 이슈는 닫는다.
    같은 제목의 이슈는 중복 생성하지 않는다. 돌려주는 값: (created, closed, renotified, new_critical).
    new_critical 은 이번 실행에서 처음 만든 심각 건의 제목 — 워크플로를 빨갛게 만드는 기준이다.
    새 이슈는 심각한 것부터(critical → 그 밖) 만든다: 상한(max_new)에 걸려 미뤄지는 쪽은 덜 심각한 건이다."""
    now = now or datetime.now(timezone.utc)
    want = {f.title: f for f in sorted(findings, key=lambda f: _SEVERITY_RANK.get(f.severity, 2))}
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
                _create_issue(client, title, issue_body(finding, owner, now.isoformat(timespec="seconds")),
                              owner, out)
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
                client.comment(issue["number"], f"{mention}아직 해결되지 않았습니다(마지막 알림 {days}일 전). "
                                                f"{_inert(finding.message)}")
            renotified.append(title)
        # 줄 끝(CRLF)·앞뒤 공백 차이만으로는 본문을 다시 쓰지 않는다(사람이 웹에서 고치면 CRLF 로 저장된다).
        if due or _same_text(issue.get("body")) != _same_text(body):
            if not dry and hasattr(client, "update_body"):
                client.update_body(issue["number"], body)
    for title, issue in have.items():
        if title in want:
            continue
        out(f"[알림 해소] {title}")
        if not dry:
            client.comment(issue["number"], "조건이 해소되었거나 다른 알림(예: STALE)으로 대체되어 자동으로 닫습니다.")
            client.close(issue["number"])
        closed.append(title)
    for title in deferred:
        out(f"::warning::새 이슈가 한 번에 너무 많아 다음 실행으로 미룹니다: {title}")
    return created, closed, renotified, new_critical


def last_commit_time(root, path, added_only=False):
    """path 를 건드린 마지막 커밋 시각. added_only 면 '파일이 새로 추가된' 커밋만 센다
    (이미지 교체처럼 기존 글만 고친 커밋을 '새 글'로 오해하지 않기 위해). 커밋이 없거나 알 수 없으면 None."""
    times = commit_times(root, path, added_only=added_only, limit=1)
    return times[0] if times else None


def _is_shallow(root):
    """얕은 복제인가(git rev-parse --is-shallow-repository 가 true). 확인할 수 없으면 아니라고 본다."""
    try:
        res = subprocess.run(["git", "rev-parse", "--is-shallow-repository"], cwd=root, capture_output=True,
                             text=True, check=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return False
    return res.stdout.strip() == "true"


def commit_times(root, path, added_only=False, limit=None, since="30 days ago"):
    """path 를 건드린 커밋 시각 목록(UTC aware, 최신순). git 을 못 쓰면 빈 목록.
    얕은 복제면 None — '글 커밋이 없다'(빈 목록)와 구분되는 '알 수 없다'이다. 얕은 복제에서는 가장 위 커밋이
    모든 파일을 새로 추가한 것처럼 보여 새 글로 오인되므로, 경고를 남기고 git 기반 판정은 하지 않는다.
    시각은 epoch 초(%ct)로 읽는다. %cI 는 git 2.45 부터 UTC 를 '...Z' 로 내는데 Python 3.10 의 fromisoformat 은
    Z 를 읽지 못해 그 커밋이 조용히 사라진다."""
    if _is_shallow(root):
        print("::warning::얕은 복제라 git 이력으로 글 커밋 시각을 판정할 수 없어 건너뜁니다"
              "(워크플로 checkout 에 fetch-depth: 0 이 필요합니다).")
        return None
    cmd = ["git", "log", f"--since={since}", "--format=%ct"]
    if added_only:
        # --first-parent: 승인 흐름(publish_flow: pr)의 글은 PR 병합 커밋으로 main 에 들어온다. 기본 이력 단순화는 병합 대신 초안 브랜치의 커밋(초안을
        # 만든 시각)을 보여 줘 '글이 올라온 시각'이 병합 시각보다 하루 이상 앞설 수 있다. main 줄기만 따라가면 병합 커밋이 글을 더한 커밋으로 잡힌다.
        # 직접 게시(봇이 main 에 한 줄로 커밋)에서는 결과가 같다.
        cmd += ["--first-parent", "--diff-filter=A"]
    if limit:
        cmd.append(f"-{int(limit)}")
    try:
        res = subprocess.run(cmd + ["--", path], cwd=root, capture_output=True, text=True, check=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return []
    out = []
    for line in res.stdout.splitlines():
        try:
            out.append(datetime.fromtimestamp(int(line.strip()), timezone.utc))
        except (ValueError, OverflowError, OSError):
            continue
    return out


def _history_post_stats(history, now):
    """이력 파일 기반 (최근 7일 글 수, 마지막 글 시각). 실제 글이 나온 항목(posted·draft_uploaded, 상태 없는 옛 항목 포함)만 센다."""
    real = [h for h in history if isinstance(h, dict) and h.get("status", "posted") in ("posted", "draft_uploaded")]
    times = [e for e in (entry_time(h) for h in real) if e]
    return sum(1 for t in times if now - t <= timedelta(days=7)), (max(times) if times else None)


def collect(reg, root, now, client=None):
    """(문제 목록, 블로그별 현황). 현황은 실행 요약 표에 쓴다(마지막 글 시각, 최근 7일 글 수)."""
    findings, stats = [], []
    pages_runs = None
    if client is not None:
        try:
            # main 브랜치의 실행만: 다른 ref 에서 workflow_dispatch 로 돌린 성공을 '배포됨'으로 세지 않는다.
            pages_runs = client.workflow_runs(PAGES_WORKFLOW, branch=PAGES_BRANCH)
        except Exception as exc:  # noqa: BLE001 - 조회 실패는 배포 검사만 건너뛰고 다른 검사를 막지 않는다
            # 검사가 꺼진 채로 초록이 이어지지 않게 Actions 화면에 경고 주석으로 올린다.
            print(f"::warning::Pages 워크플로 실행 이력 조회 실패(배포 검사 건너뜀): {_oneline(exc)}")
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
                print(f"[참고] {blog['key']} 워크플로 실행 이력 조회 실패: {_oneline(exc)}")
        content_dir = blog["state"]["content_dir"]
        if blog.get("platform") == "jekyll-git":
            # 글 파일이 '추가된' 커밋만 새 글로 센다(이미지 교체 커밋은 새 글이 아니다).
            added = commit_times(root, content_dir, added_only=True)
            pages = pages_runs
            if added is None:
                # 얕은 복제: 글 커밋 시각을 알 수 없다(경고는 commit_times 가 남겼다). git 기반 판정(최근 커밋으로 STALE 구제,
                # 하루 단위 NO_POSTS_DAY, 글 커밋 뒤 배포 확인)은 건너뛰고 이력 파일만으로 판단한다.
                last_content, post_days = None, None
                posts_7d, last_post = _history_post_stats(history, now)
            else:
                last_content = max(added) if added else None
                post_days = {t.astimezone(KST).date() for t in added}
                posts_7d = sum(1 for t in added if now - t <= timedelta(days=7))
                last_post = last_content
        else:
            last_content = last_commit_time(root, content_dir)
            post_days = None
            posts_7d, last_post = _history_post_stats(history, now)
            pages = None
        pending = None
        if client is not None and blog.get("publish_flow") == "pr":
            # 승인 흐름: 글이 안 나온 것이 멈춤인지 승인 대기인지 가르려고 열린 초안 PR 을 읽는다. 읽지 못하면 None(예전처럼 STALE 등이 그대로 울린다).
            try:
                pending = client.list_open_draft_pulls()
            except Exception as exc:  # noqa: BLE001 - 조회 실패는 이 구분만 건너뛰고 다른 검사를 막지 않는다
                print(f"[참고] {blog['key']} 초안 PR 목록 조회 실패(승인 대기 구분을 건너뜀): {_oneline(exc)}")
        blog_findings = evaluate(blog, history, now, last_content_commit=last_content, recent_runs=runs,
                                 post_days=post_days, pages_runs=pages, pending_drafts=pending)
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
        print(f"실행 요약 쓰기 실패(점검 결과에는 영향 없음): {_oneline(exc)}")


def main():
    safe_output()
    reg = load_registry()
    errors = validate_registry(reg, ROOT)
    if errors:
        print("[오류] 레지스트리 검증 실패:\n  - " + "\n  - ".join(_oneline(e) for e in errors))
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
        # 메시지에는 이력에서 인용한 텍스트가 들어갈 수 있다 — 접지 않으면 둘째 줄이 '::' 로 시작해 워크플로 명령이 된다.
        print(f"- {f.severity.upper():<8} {f.title} — {_oneline(f.message)}")
    if not findings:
        print("이상 없음")
    if client is None:
        print("(토큰/저장소 정보가 없어 dry-run 으로 종료)")
        _write_summary(render_summary(stats, findings, [], [], []))
        return 0
    open_issues = client.list_open_issues()
    created, closed, renotified, new_critical = sync_issues(findings, open_issues, client, dry=dry,
                                                            owner=owner, now=now)
    # 이번 실행에서 막 닫은 이슈는 '열려 있는' 목록에서 뺀다(dry-run 에서는 실제로 닫지 않았으므로 그대로 둔다).
    still_open = open_issues if dry else [i for i in open_issues if i.get("title") not in closed]
    _write_summary(render_summary(stats, findings, created, closed, renotified, still_open))
    for f in findings:
        if f.severity == "warning":
            print(f"::warning::{f.title}: {_oneline(f.message)[:200]}")
    if new_critical and not dry:
        # 감시 실행이 항상 초록이면 Actions 실패 알림이 가지 않는다. 새로 생긴 심각 건만 빨갛게 한다(지속 중인 건은 초록).
        print("::error::새로 생긴 심각 건: " + ", ".join(new_critical))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
