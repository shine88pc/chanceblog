"""한 실행(run id)의 job 별 단계 결과와 주석(::notice/::warning)을 읽어 보여 준다. 사용: python -X utf8 run_annotations.py <소유자/저장소> <run id>"""
import json, sys, urllib.request
repo, run_id = sys.argv[1], sys.argv[2]
h = {"User-Agent": "run-annotations", "Accept": "application/vnd.github+json"}
def api(path):
    return json.load(urllib.request.urlopen(urllib.request.Request(f"https://api.github.com/repos/{repo}/{path}", headers=h), timeout=40))
for job in api(f"actions/runs/{run_id}/jobs")["jobs"]:
    print("JOB", job["name"], job["status"], job["conclusion"])
    for st in job.get("steps", []):
        print("   step", st["number"], st["name"][:44], st["conclusion"])
    for a in api(f"check-runs/{job['id']}/annotations"):
        print("   [" + a["annotation_level"] + "]", a.get("title"), "::", (a.get("message") or "").replace("\n", " | ")[:3000])
