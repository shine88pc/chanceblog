"""공개 Actions 웹 페이지의 실행 행을 읽는다(REST 한도가 바닥일 때 — ci_web.py 가 쓰던 내장 JSON 이 GitHub 개편으로 사라져 HTML 행을 직접 읽는 새 판, 2026-11-05).
사용: python -X utf8 web_runs.py <소유자/저장소> [워크플로 파일 이름, 예: ai-request.yml 또는 guardrails.yml(기본: 전체 actions)] [브랜치 이름 조각]
행마다 '상태 | 브랜치 | 제목' 한 줄을 위에서(최신) 아래로 보인다. 상태는 aria-label(completed successfully / failed / cancelled / skipped / currently running …)."""
import html
import re
import sys
import urllib.request

repo = sys.argv[1] if len(sys.argv) > 1 else "shine88pc/chanceblog"
wf = sys.argv[2] if len(sys.argv) > 2 else ""
branch_filter = sys.argv[3] if len(sys.argv) > 3 else ""
url = f"https://github.com/{repo}/actions" + (f"/workflows/{wf}" if wf else "")
page = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (chanceblog-web-runs)"}), timeout=40).read().decode("utf-8", "replace")

status_rx = r'aria-label="((?:completed successfully|failed|cancelled|skipped|queued|currently running|in progress|waiting|timed out|neutral|action required)[^"]*)"'
title_rx = r'class="h4 Link--primary[^"]*"[^>]*>(.*?)</a>'
branch_rx = r'class="d-inline-block branch-name[^"]*"[^>]*title="([^"]+)"'
events = []
for kind, rx in (("S", status_rx), ("T", title_rx), ("B", branch_rx)):
    for m in re.finditer(rx, page, re.S):
        value = html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", m.group(1)))).strip()
        events.append((m.start(), kind, value))
events.sort()
row = {}
rows = []
for _, kind, value in events:
    if kind == "S":
        if row.get("B"):
            rows.append(row)
            row = {}
        elif row.get("S") and not row.get("B"):
            row = {}
        row["S"] = value.rstrip(": ").strip()
    elif kind == "T":
        row["T"] = value
    elif kind == "B":
        row["B"] = value
        rows.append(row)
        row = {}
for r in rows:
    if branch_filter and branch_filter not in r.get("B", ""):
        continue
    print(f'{r.get("S", "?")} | {r.get("B", "?")} | {r.get("T", "")[:80]}')
