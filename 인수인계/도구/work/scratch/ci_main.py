"""두 저장소의 main 검사(CI) 실행·열린 PR·GitHub 호출 한도를 한 번에 본다(읽기 전용, 인증 없음).

사용: py -3.12 -X utf8 scratch/ci_main.py
"""
import json
import urllib.request


def get(url):
    req = urllib.request.Request(
        url,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "ai-ci-check"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


try:
    core = get("https://api.github.com/rate_limit")["resources"]["core"]
    print("GitHub 호출 한도: 남은", core["remaining"], "/", core["limit"], "재설정 시각(epoch)", core["reset"])
except Exception as e:  # noqa: BLE001
    print("한도 조회 오류:", e)

for repo in ["shine88pc/chanceblog", "shine88pc/chanceblog-desktop"]:
    print("==", repo)
    try:
        runs = get(f"https://api.github.com/repos/{repo}/actions/runs?branch=main&per_page=8")["workflow_runs"]
        for r in runs:
            print(r["id"], r["created_at"], r["head_sha"][:7], r["event"], r["status"], r["conclusion"], r["name"][:40])
    except Exception as e:  # noqa: BLE001
        print("실행 목록 오류:", e)
    try:
        prs = get(f"https://api.github.com/repos/{repo}/pulls?state=open&per_page=20")
        print("열린 PR:", [(p["number"], p["title"][:60]) for p in prs])
    except Exception as e:  # noqa: BLE001
        print("PR 목록 오류:", e)
