"""임시 Jekyll 전후 비교 실행의 결과(주석)를 읽는다(공개 REST 3번 안팎, 읽기 전용).
사용: py -3.12 -X utf8 scratch/jk_read.py [저장소=shine88pc/chanceblog] [워크플로 파일=tmp-jekyll-build-check.yml]"""
import json
import sys
import urllib.request

repo = sys.argv[1] if len(sys.argv) > 1 else "shine88pc/chanceblog"
wf = sys.argv[2] if len(sys.argv) > 2 else "tmp-jekyll-build-check.yml"


def get(u):
    req = urllib.request.Request(u, headers={"Accept": "application/vnd.github+json", "User-Agent": "ci-timing-reader"})
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.load(r)


runs = get(f"https://api.github.com/repos/{repo}/actions/workflows/{wf}/runs?per_page=3")["workflow_runs"]
if not runs:
    print("실행 없음")
    sys.exit(0)
r = runs[0]
print(f"== run {r['id']} {r['head_branch']} {r['head_sha'][:7]} {r['status']} {r.get('conclusion')}")
jobs = get(f"https://api.github.com/repos/{repo}/actions/runs/{r['id']}/jobs?per_page=10")["jobs"]
for j in jobs:
    print(f"  job {j['name']} {j['status']} {j.get('conclusion')}")
    for s in j.get("steps", []):
        if s.get("conclusion") not in (None, "success", "skipped"):
            print(f"    단계 실패: {s['name']} {s.get('conclusion')}")
    if j.get("status") == "completed":
        for a in get(f"https://api.github.com/repos/{repo}/check-runs/{j['id']}/annotations?per_page=60"):
            msg = (a.get("message") or "").replace("\n", " | ")
            if "Node.js" in msg and "deprecated" in msg:
                continue
            print(f"    [{a.get('annotation_level')}] {a.get('title') or ''} :: {msg[:1800]}")
