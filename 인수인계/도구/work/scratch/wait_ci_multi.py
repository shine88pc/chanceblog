"""여러 브랜치 머리 커밋의 자동 검사를 한 번의 읽기로 함께 기다린다 — 공개 REST(`actions/runs?per_page=30`) 한 건씩만 읽는다(시간당 60건 한도 아낌).

사용: python -X utf8 -u wait_ci_multi.py <소유자/저장소> <최대 분> <간격 초> <커밋 SHA 전체> [<커밋 SHA 전체> ...]
**주어진 커밋 중 하나라도 실행이 모두 끝나면** 그 결과를 한 줄 적고 끝난다(알림이 오면 남은 커밋으로 다시 켠다).
종료 코드: 0 = 끝난 커밋의 실행이 전부 성공 / 1 = 실패·취소가 있음 / 2 = 시간 초과
"""
import json
import sys
import time
import urllib.error
import urllib.request

repo, limit_min, interval = sys.argv[1], float(sys.argv[2]), float(sys.argv[3])
shas = sys.argv[4:]
HEAD = {"User-Agent": "chanceblog-wait-ci-multi", "Accept": "application/vnd.github+json"}
OK = ("success", "skipped", "neutral")
last = None
deadline = time.time() + limit_min * 60
while time.time() < deadline:
    try:
        with urllib.request.urlopen(urllib.request.Request(f"https://api.github.com/repos/{repo}/actions/runs?per_page=30", headers=HEAD), timeout=40) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            remaining = resp.headers.get("X-RateLimit-Remaining")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f"[{time.strftime('%H:%M')}] 읽기 오류(다시 시도): {type(exc).__name__}", flush=True)
        time.sleep(interval)
        continue
    runs = data.get("workflow_runs", [])
    if remaining is not None and int(remaining) < 12:
        interval = max(interval, 360)
    state = {sha[:8]: [(r["name"], r["status"], r.get("conclusion")) for r in runs if r.get("head_sha") == sha] for sha in shas}
    if state != last:
        print(f"[{time.strftime('%H:%M')}] (남은 한도 {remaining}) " + " | ".join(
            f"{k}: " + (", ".join(f"{s}" + (f"·{c}" if c else "") for _, s, c in v) if v else "실행 없음") for k, v in state.items()), flush=True)
        last = state
    for sha in shas:
        mine = [r for r in runs if r.get("head_sha") == sha]
        if mine and all(r["status"] == "completed" for r in mine):
            bad = [r for r in mine if r.get("conclusion") not in OK]
            print(f"끝: {sha[:8]} — " + ("모두 성공" if not bad else "실패·취소 있음: " + ", ".join(f"{r['name']}={r.get('conclusion')}" for r in bad)) + f" (시작 {mine[0].get('run_started_at')} · 갱신 {mine[0].get('updated_at')})", flush=True)
            sys.exit(1 if bad else 0)
    time.sleep(interval)
print(f"{limit_min:.0f}분 안에 끝나지 않음", flush=True)
sys.exit(2)
