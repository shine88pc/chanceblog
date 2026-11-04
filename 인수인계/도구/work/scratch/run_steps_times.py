"""한 실행(run id)의 job 별 단계 결과·단계 소요 시간·주석(::notice/::warning/::error)을 읽어 보여 준다.
사용: python -X utf8 run_steps_times.py <소유자/저장소> <run id> [주석 읽기: 1(기본)/0]"""
import datetime
import json
import sys
import urllib.request

repo, run_id = sys.argv[1], sys.argv[2]
with_notes = (sys.argv[3] if len(sys.argv) > 3 else "1") == "1"
h = {"User-Agent": "run-steps-times", "Accept": "application/vnd.github+json"}


def api(path):
    return json.load(urllib.request.urlopen(urllib.request.Request(f"https://api.github.com/repos/{repo}/{path}", headers=h), timeout=40))


def parse(value):
    return datetime.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ") if value else None


for job in api(f"actions/runs/{run_id}/jobs")["jobs"]:
    start, end = parse(job.get("started_at")), parse(job.get("completed_at"))
    total = int((end - start).total_seconds()) if start and end else None
    print("JOB", job["name"], job["status"], job["conclusion"], f"{total}초" if total is not None else "")
    for st in job.get("steps", []):
        a, b = parse(st.get("started_at")), parse(st.get("completed_at"))
        sec = int((b - a).total_seconds()) if a and b else None
        print(f"   step {st['number']:>2} {st['name'][:52]:<52} {st['conclusion']!s:<9} {sec if sec is not None else '-'}초")
    if with_notes:
        for note in api(f"check-runs/{job['id']}/annotations"):
            print("   [" + note["annotation_level"] + "]", note.get("title"), "::", (note.get("message") or "").replace("\n", " | ")[:1500])
