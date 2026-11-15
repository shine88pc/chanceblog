"""마감 시각의 사실(머리·마지막 번호·다음 번호·요청 가지 머리·가지 수)을 읽어 freeze.json 에 적는다(읽기 전용). 이후 생긴 일은 문서의 '마지막 갱신 이후 추가' 줄 몫이다."""
import json
import re
import subprocess
import sys
import time

BLOG, APP = "C:/work/ai/wt_r30", "C:/work/ai/cd_repo"
REQ = "origin/ai/claude/NO-MERGE-operator-requests"


def git(repo, *a):
    return subprocess.run(["git", "-C", repo, "-c", "core.quotepath=false", *a], capture_output=True, encoding="utf-8").stdout


def ls_remote(repo, ref):
    return subprocess.run(["git", "-C", repo, "ls-remote", "origin", ref], capture_output=True, encoding="utf-8").stdout


out = {"time": time.strftime("%H:%M:%S")}
out["blog_head"] = ls_remote(BLOG, "refs/heads/main").split()[0][:7]
out["app_head"] = ls_remote(APP, "refs/heads/main").split()[0][:7]
root = subprocess.run(["git", "ls-remote", "https://github.com/shine88pc/shine88pc.github.io.git", "refs/heads/main"], capture_output=True, encoding="utf-8").stdout
out["root_head"] = root.split()[0][:7]
req = ls_remote(BLOG, "refs/heads/ai/claude/NO-MERGE-operator-requests").split()[0][:7]
out["req_head"] = req
git(BLOG, "fetch", "-q", "origin", "ai/claude/NO-MERGE-operator-requests")
names = git(BLOG, "ls-tree", "--name-only", REQ, "인수인계/요청함/").strip().split("\n")
out["max_r"] = max(int(m.group(1)) for n in names for m in [re.match(r"인수인계/요청함/R-(\d+)_", n)] if m)
nn = subprocess.run([sys.executable, "-X", "utf8", "C:/work/ai/next_notice_no.py", "--repo", BLOG, "--dir", BLOG, "--local"], capture_output=True, encoding="utf-8").stdout
out["next_p"] = re.search(r"P 다음 번호: (P\d+)", nn).group(1)
out["next_m"] = re.search(r"M 다음 번호: (M\d+)", nn).group(1)
out["next_c"] = re.search(r"확인 다음 번호: (\d+)", nn).group(1)
out["blog_branches"] = len(ls_remote(BLOG, "refs/heads/ai/claude/*").strip().split("\n"))
out["app_branches"] = len(ls_remote(APP, "refs/heads/ai/claude/*").strip().split("\n"))
json.dump(out, open("C:/work/ai/audit6/improve/worklog12/freeze.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(json.dumps(out, ensure_ascii=False))
