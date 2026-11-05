"""병합 브랜치의 자동 검사(사전 검사)가 끝나기를 기다린다 — 공개 웹 목록만 읽는다(API 한도 없음, 로그인 없음).

사용: python -X utf8 -u wait_ci.py <소유자/저장소> <브랜치> <커밋 SHA 앞부분(7자 이상)> [최대 분(기본 30)]
그 커밋(머리)의 실행을 목록에서 찾아 모두 끝날 때까지 기다린다. 상태가 바뀔 때만 한 줄씩 보인다.
종료 코드: 0 = 찾은 실행이 모두 끝났고 전부 성공 / 1 = 실패·취소가 있음 / 2 = 시간 초과 또는 실행을 못 찾음(push 직후 6분 안에 안 보이면)
"""
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (chanceblog-wait-ci)"}
OK_CONCLUSIONS = ("success", "skipped", "neutral")        # 건너뜀·중립은 실패가 아니다(다른 워크플로가 조건 때문에 건너뛴 경우)


def fetch(url, timeout=40):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def find_runs(node):
    if isinstance(node, dict):
        if isinstance(node.get("workflowRuns"), list):
            return node["workflowRuns"]
        for value in node.values():
            found = find_runs(value)
            if found is not None:
                return found
    elif isinstance(node, list):
        for value in node:
            found = find_runs(value)
            if found is not None:
                return found
    return None


def _runs_for_web(repo, branch, sha):
    query = urllib.parse.quote(f"branch:{branch}", safe="")
    page = fetch(f"https://github.com/{repo}/actions?query={query}")
    match = re.search(r'<script type="application/json" data-target="react-app.embeddedData">(.*?)</script>', page, re.S)
    if not match:
        raise RuntimeError("내장 JSON 을 찾지 못했다")
    found = []
    for run in find_runs(json.loads(match.group(1))) or []:
        link = (run.get("description") or {}).get("linkUrl", "")
        if f"/commit/{sha}" in link:
            state = run.get("state", {})
            status = (state.get("status") or "").replace("WORKFLOW_RUN_STATUS_", "").lower()
            conclusion = (state.get("conclusion") or "").replace("WORKFLOW_RUN_CONCLUSION_", "").lower()
            found.append({
                "id": run.get("id"),
                "name": run.get("workflowName") or run.get("name") or "",
                "event": (run.get("description") or {}).get("action", ""),
                "status": status,
                "conclusion": conclusion,
                "timing": (run.get("timing") or {}).get("text", ""),
            })
    return found


def _runs_for_html(repo, branch, sha):
    """내장 JSON 이 없을 때 — 브랜치로 걸러 낸 공개 Actions 페이지의 HTML 행을 직접 읽는다(2026-11-05 추가, API 한도 없음).
    행마다 상태(aria-label)·커밋 링크(전체 SHA)·브랜치 이름이 한 번씩 있다. 상태 라벨 위치로 행을 나눠 그 안의 커밋 링크를 본다."""
    import html as html_mod
    query = urllib.parse.quote(f"branch:{branch}", safe="")
    page = fetch(f"https://github.com/{repo}/actions?query={query}")
    label_rx = re.compile(r'aria-label="((?:completed successfully|failed|cancelled|skipped|queued|currently running|in progress|waiting|timed out|neutral|action required)[^"]*)"')
    labels = list(label_rx.finditer(page))
    if not labels:
        raise RuntimeError("실행 행의 상태 표시를 찾지 못했다")
    found = []
    for index, label in enumerate(labels):
        end = labels[index + 1].start() if index + 1 < len(labels) else len(page)
        block = page[label.start():end]
        commits = re.findall(r"/commit/([0-9a-f]{7,40})", block)
        if not commits or not any(c.startswith(sha) or sha.startswith(c[:len(sha)]) for c in commits):
            continue
        titles = re.findall(r'class="h4 Link--primary[^"]*"[^>]*>(.*?)</a>', block, re.S)
        branch_names = re.findall(r'class="d-inline-block branch-name[^"]*"[^>]*title="([^"]+)"', block)
        if branch_names and branch not in branch_names:
            continue
        run_ids = re.findall(r"/actions/runs/(\d+)", block)
        state = html_mod.unescape(label.group(1)).strip(": ").strip().lower()
        status, conclusion = "completed", ""
        if state.startswith("completed successfully"):
            conclusion = "success"
        elif state.startswith("failed") or state.startswith("timed out"):
            conclusion = "failure"
        elif state.startswith("cancelled"):
            conclusion = "cancelled"
        elif state.startswith("skipped"):
            conclusion = "skipped"
        elif state.startswith("neutral"):
            conclusion = "neutral"
        else:
            status = "in_progress" if state.startswith(("currently", "in progress")) else "queued"
        duration = re.findall(r"(\d+m \d+s|\d+s)", re.sub(r"<[^>]+>", " ", block))
        found.append({
            "id": int(run_ids[0]) if run_ids else 0,
            "name": html_mod.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", titles[0] if titles else ""))).strip()[:60],
            "event": "push",
            "status": status,
            "conclusion": conclusion,
            "timing": duration[0] if duration else "",
        })
    return found


def _runs_for_rest(repo, branch, sha):
    """웹 목록의 내장 JSON 을 못 읽을 때(2026-11-04 08:30 부터 그랬다)의 대체 — 공개 REST(시간당 60건 한도)로 같은 모양의 값을 만든다."""
    import datetime
    url = f"https://api.github.com/repos/{repo}/actions/runs?branch={urllib.parse.quote(branch, safe='')}&per_page=30"
    found = []
    for run in json.loads(fetch(url)).get("workflow_runs", []):
        if not (run.get("head_sha") or "").startswith(sha):
            continue
        timing = ""
        if run.get("run_started_at") and run.get("updated_at") and run.get("status") == "completed":
            parse = lambda text: datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))
            seconds = int((parse(run["updated_at"]) - parse(run["run_started_at"])).total_seconds())
            timing = f"{seconds // 60}분 {seconds % 60}초"
        found.append({
            "id": run.get("id"),
            "name": run.get("name") or "",
            "event": run.get("event") or "",
            "status": run.get("status") or "",
            "conclusion": run.get("conclusion") or "",
            "timing": timing,
        })
    return found


def runs_for(repo, branch, sha):
    try:
        return _runs_for_web(repo, branch, sha)
    except RuntimeError:
        pass
    try:
        found = _runs_for_html(repo, branch, sha)
        if found:
            return found
    except RuntimeError:
        pass
    return _runs_for_rest(repo, branch, sha)


def main():
    if len(sys.argv) < 4:
        print(__doc__)
        return 2
    repo, branch, sha = sys.argv[1], sys.argv[2], sys.argv[3]
    limit_min = float(sys.argv[4]) if len(sys.argv) > 4 else 30
    if len(sha) < 7:
        print("커밋 SHA 앞부분은 7자 이상이어야 한다")
        return 2
    started = time.time()
    last = None
    while True:
        try:
            runs = runs_for(repo, branch, sha)
        except (urllib.error.URLError, RuntimeError, OSError) as exc:
            runs = None
            print(f"[{time.strftime('%H:%M')}] 읽기 오류(다시 시도): {exc}", flush=True)
        if runs is not None:
            snapshot = [(r["id"], r["status"], r["conclusion"]) for r in runs]
            if snapshot != last:
                last = snapshot
                if not runs:
                    print(f"[{time.strftime('%H:%M')}] 아직 그 커밋의 실행이 목록에 없음", flush=True)
                for r in runs:
                    print(f"[{time.strftime('%H:%M')}] 실행 {r['id']} ({r['name']}, {r['event']}) {r['status']}/{r['conclusion'] or '-'} {r['timing']}", flush=True)
            if runs and all(r["status"] == "completed" for r in runs):
                ok = all(r["conclusion"] in OK_CONCLUSIONS for r in runs)
                print(("모두 성공" if ok else "실패·취소 있음") + f" — 실행 {len(runs)}건", flush=True)
                return 0 if ok else 1
            if not runs and time.time() - started > 6 * 60:
                print("6분이 지나도 그 커밋의 실행이 목록에 없음", flush=True)
                return 2
        if time.time() - started > limit_min * 60:
            print(f"{limit_min:g}분 안에 끝나지 않음", flush=True)
            return 2
        time.sleep(45)


if __name__ == "__main__":
    sys.exit(main())
