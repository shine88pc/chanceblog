"""REST 한도(시간당 60회)를 다 썼을 때 쓰는 읽기 도구 — 공개 웹 페이지(Actions 목록에 실려 있는 JSON)만 읽는다. 로그인·API·다른 모듈 import 없음.

사용: python -X utf8 ci_web.py <소유자/저장소> [개수] [페이지 경로(기본 actions, 예: actions/workflows/ai-request.yml)]
최근 실행 N개의 (번호, 상태/결론, 브랜치, 걸린 시간, 제목)을 한 줄씩 보인다.
"""
import json
import re
import sys
import urllib.error
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (chanceblog-ci-web)"}


def fetch(url, timeout=30):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def find_runs(node):
    """내장 JSON 어디에 있든 'workflowRuns' 목록을 찾는다."""
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


def main():
    repo = sys.argv[1] if len(sys.argv) > 1 else "shine88pc/chanceblog-desktop"
    count = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    path = sys.argv[3] if len(sys.argv) > 3 else "actions"
    try:
        page = fetch(f"https://github.com/{repo}/{path}")
    except urllib.error.HTTPError as exc:
        print(f"[오류] {exc.code}")
        return 1
    match = re.search(r'<script type="application/json" data-target="react-app.embeddedData">(.*?)</script>', page, re.S)
    if not match:
        print("내장 JSON 을 찾지 못했다")
        return 1
    runs = find_runs(json.loads(match.group(1))) or []
    for run in runs[:count]:
        state = run.get("state", {})
        status = state.get("conclusion") or state.get("status") or "?"
        status = status.replace("WORKFLOW_RUN_CONCLUSION_", "").replace("WORKFLOW_RUN_STATUS_", "").lower()
        branch = (run.get("branch") or {}).get("title", "")
        timing = (run.get("timing") or {}).get("text", "")
        print(f"{run.get('id')}  {status:<10} {branch[:34]:<34} {timing:<8} {run.get('title', '')[:70]}")
    if not runs:
        print("실행 목록이 비어 있다")
    return 0


if __name__ == "__main__":
    sys.exit(main())
