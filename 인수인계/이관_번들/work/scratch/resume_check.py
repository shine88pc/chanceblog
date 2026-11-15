"""재부팅 뒤 '이어서 진행해줘' 첫 점검 — 세 저장소 머리·요청 가지 머리·M070 가지와 검사·열린 PR·새 이슈·다음 번호·작업 폴더 상태를 한 번에 보여 준다(읽기 전용, 비인증 REST 서너 번).
사용: python -X utf8 C:/work/ai/scratch/resume_check.py"""
import json
import subprocess
import urllib.request
from datetime import datetime

BLOG = "shine88pc/chanceblog"
DESK = "shine88pc/chanceblog-desktop"
ROOT = "shine88pc/shine88pc.github.io"


def run(*args, cwd=None):
    done = subprocess.run(list(args), capture_output=True, text=True, encoding="utf-8", cwd=cwd)
    return (done.stdout or done.stderr).strip()


def head(repo, ref="refs/heads/main"):
    out = run("git", "ls-remote", f"https://github.com/{repo}.git", ref)
    return out.split("\t")[0][:7] if out else "?"


def api(path):
    req = urllib.request.Request("https://api.github.com/" + path, headers={"User-Agent": "resume-check"})
    try:
        return json.load(urllib.request.urlopen(req, timeout=20))
    except Exception as exc:  # 한도·네트워크
        return {"error": str(exc)[:80]}


print("지금:", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
print("블로그 main", head(BLOG), "| 데스크톱 main", head(DESK), "| 루트 main", head(ROOT))
print("요청 가지 머리", head(BLOG, "refs/heads/ai/claude/NO-MERGE-operator-requests"), "(마지막 알림 R-330 은 b97faa2)")
m70 = head(BLOG, "refs/heads/ai/claude/M070-worklog13")
print("M070 가지", m70, "(내가 푸시한 머리는 ccccaed — 다르면 누가 고친 것)")
if m70 != "?":
    runs = api(f"repos/{BLOG}/actions/runs?branch=ai/claude/M070-worklog13&per_page=6")
    for r in (runs.get("workflow_runs") or [])[:6]:
        print("  ", r["head_sha"][:7], r["name"][:30], r["status"], r["conclusion"], r["run_started_at"][11:19], "UTC")
    if "error" in runs:
        print("  (검사 목록 읽기 실패:", runs["error"], ")")
prs = api(f"repos/{BLOG}/pulls?state=open&per_page=5")
if isinstance(prs, list):
    print("블로그 열린 PR:", [(p["number"], p["head"]["ref"], p["title"][:40]) for p in prs] or "없음")
else:
    print("블로그 열린 PR 읽기 실패:", prs)
iss = api(f"repos/{BLOG}/issues?state=all&sort=created&direction=desc&per_page=8")
if isinstance(iss, list):
    print("최근 이슈(최신순, #195 가 마지막으로 처리한 운영자 답):")
    for i in iss[:8]:
        if "pull_request" in i:
            continue
        print("  #%s %s | %s | %s | %s" % (i["number"], i["title"][:36], i["user"]["login"], i["created_at"][5:16], [l["name"] for l in i["labels"]]))
else:
    print("이슈 읽기 실패:", iss)
print("번호 도구:")
print(run("python", "-X", "utf8", "C:/work/ai/next_notice_no.py", "--repo", "C:/work/ai/wt_r30", "--dir", "C:/work/ai/wt_r30", "--local"))
print("작업 폴더 wt_m071:", run("git", "-C", "C:/work/ai/wt_m071", "log", "--oneline", "-1")[:90], "|", run("git", "-C", "C:/work/ai/wt_m071", "status", "--short") or "깨끗")
print("요청 가지 작업 폴더 wt_r30:", run("git", "-C", "C:/work/ai/wt_r30", "log", "--oneline", "-1")[:80], "|", run("git", "-C", "C:/work/ai/wt_r30", "status", "--short") or "깨끗")
