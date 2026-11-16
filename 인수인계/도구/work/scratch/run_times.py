"""블로그 저장소 워크플로의 최근 실행 시각(KST)을 읽는다 — 공개 Actions 페이지의 내장 JSON(`createdAt.timestamp`)에서.
(2026-11-06: GitHub 가 `<relative-time datetime=…>` 을 없애서 옛 방식이 비게 됐다. 이 도구는 내장 JSON 을 읽는다.)
사용: python -X utf8 run_times.py [저장소(기본 shine88pc/chanceblog)] 워크플로파일 …  예: run_times.py chanceblog.yml blogger-en.yml"""
import datetime
import re
import sys
import urllib.error
import urllib.request

args = sys.argv[1:]
repo = "shine88pc/chanceblog"
if args and "/" in args[0] and not args[0].endswith(".yml"):
    repo, args = args[0], args[1:]
workflows = args or ["chanceblog.yml", "blogger-en.yml", "blogger-ko.yml"]
kst = datetime.timezone(datetime.timedelta(hours=9))
now = datetime.datetime.now(kst)
for wf in workflows:
    url = f"https://github.com/{repo}/actions/workflows/{wf}"
    try:
        page = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (chanceblog-run-times)"}), timeout=40).read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        print(wf, "HTTPError", exc.code)
        continue
    except Exception as exc:  # noqa: BLE001
        print(wf, "오류", type(exc).__name__)
        continue
    stamps = []
    for m in re.finditer(r'"createdAt":\{"timestamp":"([0-9T:\-]+Z)"', page):
        moment = datetime.datetime.fromisoformat(m.group(1).replace("Z", "+00:00")).astimezone(kst)
        if moment not in stamps:
            stamps.append(moment)
    stamps.sort(reverse=True)
    if not stamps:
        print(wf, "시각을 못 읽음")
        continue
    print(wf, "| 최근:", ", ".join(s.strftime("%m-%d %H:%M") for s in stamps[:4]), "| 마지막부터", str(now - stamps[0]).split(".")[0])
