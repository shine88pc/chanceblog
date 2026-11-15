"""마감 직전 공개 값을 다시 읽어 문서의 주장과 견줄 값을 출력한다(읽기 전용: 공개 사이트·공개 REST·공개 실행 목록·git ls-remote 만).

출력: 공개 글·사이트맵·피드·광고 줄 수, 세 저장소 열린 PR 수, 그림자·Package 워크플로 실행 수, 이슈 #22 요약과 갱신 시각, 운영자 이슈 상태, 앱 main 검사 상태.
"""
import datetime
import json
import re
import subprocess
import sys
import urllib.request

sys.path.insert(0, "C:/work/ai/scratch")
import wait_ci  # noqa: E402

UA = {"User-Agent": "chanceblog-doc-check"}


def get(url, timeout=40):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def rest(path):
    try:
        return json.loads(get("https://api.github.com/" + path))
    except Exception as err:  # noqa: BLE001
        return {"error": str(err)[:80]}


def kst(s):
    return (datetime.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ") + datetime.timedelta(hours=9)).strftime("%m-%d %H:%M:%S")


base = "https://shine88pc.github.io/chanceblog"
home = get(base + "/?nocache=v")
print("홈 adsbygoogle 줄 수:", home.count("adsbygoogle"))
print("글:", get(base + "/posts.json?nocache=v").count('"absoluteUrl"'), "| 사이트맵:", get(base + "/sitemap.xml?nocache=v").count("<loc>"), "| 피드:", get(base + "/feed.xml?nocache=v").count("<item>"))
for repo in ("chanceblog", "chanceblog-desktop", "shine88pc.github.io"):
    d = rest("repos/shine88pc/%s/pulls?state=open&per_page=5" % repo)
    print("열린 PR", repo, ":", len(d) if isinstance(d, list) else d)
issue22 = rest("repos/shine88pc/chanceblog/issues/22")
if "body" in issue22:
    m = re.search(r"\*\*지금 해야 할 일 \d+건\*\* · 확인하면 좋은 것 \d+건 · 참고 \d+건", issue22["body"])
    print("이슈 #22:", m.group(0) if m else "?", "| 갱신(KST)", kst(issue22["updated_at"]), "| 일시정지 참고 항목:", "계획된 일시정지" in issue22["body"], "| 변수 꺼짐 점검 항목:", "변수 PIPELINE_PAUSE 가 꺼져 있습니다" in issue22["body"])
latest = rest("repos/shine88pc/chanceblog/issues?state=all&per_page=4&sort=created&direction=desc")
if isinstance(latest, list):
    for i in latest:
        print("  블로그 #%d %s %s %s %s" % (i["number"], kst(i["created_at"]), i["user"]["login"], i["state"], i["title"][:40]))
latest_app = rest("repos/shine88pc/chanceblog-desktop/issues?state=all&per_page=3&sort=created&direction=desc")
if isinstance(latest_app, list):
    for i in latest_app:
        print("  앱 #%d %s %s %s %s" % (i["number"], kst(i["created_at"]), i["user"]["login"], i["state"], i["title"][:40]))
for n in (190, 191):
    d = rest("repos/shine88pc/chanceblog/issues/%d" % n)
    if "state" in d:
        print("이슈 #%d 상태 %s 라벨 %s" % (n, d["state"], [l["name"] for l in d["labels"]]))


def workflow_runs(repo, wf):
    page = get("https://github.com/shine88pc/%s/actions/workflows/%s" % (repo, wf))
    m = re.search(r'<script type="application/json" data-target="react-app.embeddedData">(.*?)</script>', page, re.S)
    runs = wait_ci.find_runs(json.loads(m.group(1))) if m else None
    return [(r.get("state", {}).get("conclusion", "").replace("WORKFLOW_RUN_CONCLUSION_", ""), (r.get("time") or {}).get("timestamp")) for r in (runs or [])]


print("그림자 실행:", workflow_runs("chanceblog", "chance-shadow.yml"))
print("Package 실행:", workflow_runs("chanceblog-desktop", "package.yml"))
app_head = subprocess.run(["git", "-C", "C:/work/ai/cd_repo", "ls-remote", "origin", "refs/heads/main"], capture_output=True, encoding="utf-8").stdout.split()[0][:7]
runs = wait_ci.runs_for("shine88pc/chanceblog-desktop", "main", app_head)
print("앱 main %s 검사:" % app_head, [((r["name"] or "")[:20], r["status"], r["conclusion"]) for r in runs])
blog_head = subprocess.run(["git", "-C", "C:/work/ai/wt_r30", "ls-remote", "origin", "refs/heads/main"], capture_output=True, encoding="utf-8").stdout.split()[0][:7]
runs = wait_ci.runs_for("shine88pc/chanceblog", "main", blog_head)
print("블로그 main %s 실행:" % blog_head, [((r["name"] or "")[:16], r["status"], r["conclusion"]) for r in runs])
