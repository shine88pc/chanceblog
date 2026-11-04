"""한 번의 읽기로 여러 커밋(앞 7자리)의 실행 상태를 보여 준다. 사용: python -X utf8 runs_by_sha.py <소유자/저장소> <sha7> [<sha7> …]"""
import json, sys, time, urllib.request
repo, prefixes = sys.argv[1], sys.argv[2:]
h = {"User-Agent": "runs-by-sha", "Accept": "application/vnd.github+json"}
r = urllib.request.urlopen(urllib.request.Request(f"https://api.github.com/repos/{repo}/actions/runs?per_page=30", headers=h), timeout=40)
d = json.load(r)
print(time.strftime("%H:%M:%S"), "남은 한도", r.headers.get("X-RateLimit-Remaining"))
for p in prefixes:
    mine = [x for x in d["workflow_runs"] if x["head_sha"].startswith(p)]
    print(f"== {p}: " + ("실행 없음" if not mine else ""))
    for x in mine:
        print(f"   {x['name'][:40]:<40} {x['status']}/{x['conclusion']} id={x['id']} {x['run_started_at']}→{x['updated_at']}")
