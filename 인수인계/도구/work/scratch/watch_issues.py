"""블로그 저장소의 새 이슈를 알려 주는 가벼운 감시(Monitor 용 — 줄 하나가 이벤트 하나).

운영자가 텔레그램으로 보낸 글은 '텔레그램수신 가져오기' 워크플로가 이슈(라벨 텔레그램수신)로 옮기고, 급할 때 운영자가 직접 올리는 이슈(답변·요청)도 같다.
이 감시는 300초(5분)마다 이슈 목록을 ETag(If-None-Match)로 조회해 새로 생긴
'운영자 관련' 이슈 한 줄을 출력한다: 라벨 텔레그램수신·운영자응답 이거나, 작성자가 운영자(shine88pc)인 이슈. PR·봇이 만든 일반 이슈는 건너뛴다.
※ 2026-11-15 실측: 비인증 요청은 304 도 시간당 60 한도(IP 기준)에 센다(남은 횟수 22→21→20) — 그래서 90초 주기(시간당 40회)는 한도의 3분의 2 를 쓰고 다른 조회가 막혔다. 300초 주기는 시간당 12회다.
출력에는 번호·제목(80자)·작성자·라벨·시각만 싣고 본문은 싣지 않는다. 네트워크 오류는 조용히 다시 시도한다. 사용: python -X utf8 watch_issues.py"""
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

REPO = "shine88pc/chanceblog"
URL = f"https://api.github.com/repos/{REPO}/issues?state=open&sort=created&direction=desc&per_page=15"
OPERATOR = "shine88pc"
LABELS = ("텔레그램수신", "운영자응답")
INTERVAL = 600
KST = timezone(timedelta(hours=9))


COMMENTS_URL = f"https://api.github.com/repos/{REPO}/issues/comments?sort=created&direction=desc&per_page=15"


def fetch(etag, url=URL):
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "chanceblog-watch"})
    if etag:
        req.add_header("If-None-Match", etag)
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            return resp.headers.get("ETag"), json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        if err.code == 304:
            return etag, None
        raise


def relevant(item):
    if "pull_request" in item:
        return False
    names = [l.get("name", "") for l in item.get("labels", [])]
    return any(n in LABELS for n in names) or (item.get("user") or {}).get("login") == OPERATOR


def line(item):
    names = ",".join(l.get("name", "") for l in item.get("labels", [])) or "라벨 없음"
    when = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00")).astimezone(KST).strftime("%m-%d %H:%M")
    title = " ".join((item.get("title") or "").split())[:80]
    return f"[새 이슈] #{item['number']} {title} | 작성 {(item.get('user') or {}).get('login', '?')} | 라벨 {names} | {when} KST"


def comment_line(comment):
    number = (comment.get("issue_url") or "").rstrip("/").rsplit("/", 1)[-1]
    when = datetime.fromisoformat(comment["created_at"].replace("Z", "+00:00")).astimezone(KST).strftime("%m-%d %H:%M")
    return f"[새 코멘트] #{number} | 작성 {(comment.get('user') or {}).get('login', '?')} | {when} KST (본문은 싣지 않음 — 이슈를 직접 읽는다)"


def main():
    etag, seen, warned = None, None, False
    c_etag, c_seen = None, None
    while True:
        try:
            etag, items = fetch(etag)
            if items is not None:
                top = max([i["number"] for i in items] or [0])
                if seen is None:
                    seen = top
                    print(f"이슈 감시 시작: 지금 최신 이슈 #{top} (이후에 생기는 운영자 관련 이슈를 알립니다)", flush=True)
                else:
                    for item in sorted(items, key=lambda i: i["number"]):
                        if item["number"] > seen and relevant(item):
                            print(line(item), flush=True)
                    seen = max(seen, top)
        except urllib.error.HTTPError as err:
            if err.code in (403, 429):  # 비인증 한도 소진 — 초기화 시각(X-RateLimit-Reset)까지 쉰다(최대 15분)
                try:
                    wait = max(60, min(900, int(err.headers.get('X-RateLimit-Reset', '0')) - int(time.time())))
                except Exception:
                    wait = 300
                time.sleep(wait)
                continue
            if seen is None and not warned:
                warned = True
                print(f"이슈 감시: 첫 조회 실패(HTTP {err.code}) — 다시 시도합니다", flush=True)
        except Exception as err:  # 네트워크·한도 오류는 다음 주기에 다시(첫 조회 실패만 한 번 알림)
            if seen is None and not warned:
                warned = True
                print(f"이슈 감시: 첫 조회 실패({type(err).__name__}) — 다시 시도합니다", flush=True)
        try:  # 운영자가 새 이슈 대신 이슈 코멘트로 답한 경우(2026-11-17 추가 — 본문은 싣지 않고 번호·시각만)
            c_etag, comments = fetch(c_etag, COMMENTS_URL)
            if comments is not None:
                top_id = max([c["id"] for c in comments] or [0])
                if c_seen is None:
                    c_seen = top_id
                else:
                    for comment in sorted(comments, key=lambda c: c["id"]):
                        if comment["id"] > c_seen and (comment.get("user") or {}).get("login") == OPERATOR:
                            print(comment_line(comment), flush=True)
                    c_seen = max(c_seen, top_id)
        except urllib.error.HTTPError as err:
            if err.code in (403, 429):
                try:
                    wait = max(60, min(900, int(err.headers.get('X-RateLimit-Reset', '0')) - int(time.time())))
                except Exception:
                    wait = 300
                time.sleep(wait)
                continue
        except Exception:
            pass
        time.sleep(INTERVAL)


if __name__ == "__main__":
    sys.exit(main())
