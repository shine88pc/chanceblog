"""WIP 가지들의 검사(CI) 최신 실행 상태를 한 번의 공개 REST 호출로 보여 준다(읽기만, 로그인 없음 — 시간당 60회 한도를 아끼려고 목록 1회).
사용: py -3.12 -X utf8 C:/work/ai/scratch/ci_wip_status.py <blog|app> [가지 이름에 들어 있어야 하는 글자(기본 NO-MERGE)]
출력: 가지마다 최신 실행 하나 — 머리 해시 7자·상태·결론·경과(분)·실행 번호."""
import json
import sys
import urllib.request
from datetime import datetime, timezone

REPOS = {"blog": ("shine88pc/chanceblog", "guardrails.yml"), "app": ("shine88pc/chanceblog-desktop", "ci.yml")}


def main(argv):
    if not argv or argv[0] not in REPOS:
        print(__doc__)
        return 2
    repo, wf = REPOS[argv[0]]
    needle = argv[1] if len(argv) > 1 else "NO-MERGE"
    req = urllib.request.Request(f"https://api.github.com/repos/{repo}/actions/workflows/{wf}/runs?per_page=60",
                                 headers={"Accept": "application/vnd.github+json", "User-Agent": "ci-timing-reader"})
    with urllib.request.urlopen(req, timeout=40) as r:
        data = json.load(r)
        remaining = r.headers.get("X-RateLimit-Remaining")
    seen = {}
    for run in data["workflow_runs"]:
        br = run.get("head_branch") or ""
        if needle in br and br not in seen:
            seen[br] = run
    now = datetime.now(timezone.utc)
    for br, run in sorted(seen.items()):
        start = datetime.fromisoformat(run["run_started_at"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(run["updated_at"].replace("Z", "+00:00")) if run["status"] == "completed" else now
        print(f"{br.rsplit('/', 1)[-1]:28s} {run['head_sha'][:7]} {run['status']:12s} {str(run.get('conclusion')):10s} {(end - start).total_seconds() / 60:5.1f}분 run {run['id']}")
    print(f"(남은 호출 {remaining})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
