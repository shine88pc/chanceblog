# -*- coding: utf-8 -*-
"""PIPELINE_PAUSE 적용 확인(읽기 전용: 공개 웹 페이지·git ls-remote 만 사용, api.github.com 호출 0회).

확인 항목(운영자 2026-11-09 지시):
  1. 워크플로 초록 종료  2. 새 글 0건  3. 새 커밋 0건  4. 확인 필요 모음에 일시정지 표시
  5. 워치독 STALE·UNPUBLISHED 오탐 없음  6. 기존 공개 글·사이트 배포 유지
사용: python -X utf8 verify_pause.py [--since 2026-11-08T22:00:00Z]
"""
import html
import json
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

REPO = "shine88pc/chanceblog"
BASE = f"https://github.com/{REPO}"
BASE_SHA = "611b2d2f4d5e789691e880e082ebec944ca5e0fe"        # 일시정지 전 마지막 main(봇 커밋: 11-08 22:58 KST 자동 포스팅)
BASELINE_PUBLIC_POSTS = 50
BASELINE_POST_FILES = 64
UA = {"User-Agent": "Mozilla/5.0 (chanceblog-pause-verify)"}
KST = timedelta(hours=9)
WORKFLOWS = [("chanceblog.yml", "Chance 글 자동 작성·게시"), ("blogger-en.yml", "Blogger 영문"), ("blogger-ko.yml", "Blogger 한글"),
             ("watchdog.yml", "워치독"), ("ops-inbox.yml", "확인 필요 모음"), ("pages.yml", "사이트 자동 배포")]


def fetch(url, ajax=False, timeout=40):
    headers = dict(UA)
    if ajax:
        headers["X-Requested-With"] = "XMLHttpRequest"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001
        return f"__ERR__ {type(exc).__name__}: {exc}"


def text_of(fragment):
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", fragment))).strip()


def runs_of(workflow_file, limit=6):
    page = fetch(f"{BASE}/actions/workflows/{workflow_file}")
    runs = []
    for m in re.finditer(r'"name":"([^"]*)","runNumber":(\d+),"id":"(\d+)".*?"title":"([^"]*)".*?"conclusion":"([A-Z_]+)".*?"createdAt":\{"timestamp":"([^"]+)".*?"timing":\{"kind":"[A-Z_]+","text":"([^"]*)"', page):
        name, num, rid, title, concl, ts, dur = m.groups()
        t = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")
        runs.append({"num": int(num), "id": rid, "title": html.unescape(title), "conclusion": concl.replace("WORKFLOW_RUN_CONCLUSION_", ""), "utc": t, "kst": t + KST, "duration": dur})
        if len(runs) >= limit:
            break
    return runs


def annotations(run_id):
    raw = fetch(f"{BASE}/actions/runs/{run_id}/annotations_partial", ajax=True)
    txt = text_of(raw)
    txt = re.sub(r"Show (more|less)", "", txt)
    txt = re.sub(r"\"The ubuntu-latest label will migrate[^\"]*\"", "", txt)
    return re.sub(r"\s+", " ", txt).strip()


def main_head():
    out = subprocess.run(["git", "ls-remote", f"https://github.com/{REPO}.git", "refs/heads/main"], capture_output=True, text=True, timeout=90).stdout
    return out.split("\t")[0].strip() if out else "?"


def main_commits(limit=10):
    feed = fetch(f"{BASE}/commits/main.atom")
    rows = []
    for entry in re.findall(r"<entry>(.*?)</entry>", feed, re.S)[:limit]:
        cid = re.search(r"/commit/([0-9a-f]{7,40})", entry)
        title = re.search(r"<title>(.*?)</title>", entry, re.S)
        author = re.search(r"<name>(.*?)</name>", entry, re.S)
        upd = re.search(r"<updated>(.*?)</updated>", entry)
        if cid:
            rows.append((cid.group(1)[:7], upd.group(1) if upd else "", text_of(author.group(1)) if author else "", text_of(title.group(1))[:80] if title else ""))
    return rows


def main():
    since = None
    if "--since" in sys.argv:
        since = datetime.strptime(sys.argv[sys.argv.index("--since") + 1], "%Y-%m-%dT%H:%M:%SZ")
    print(f"== PIPELINE_PAUSE 확인 {datetime.now(timezone.utc).replace(tzinfo=None) + KST:%m-%d %H:%M} KST ==")
    head = main_head()
    print(f"[3 새 커밋] main 머리 {head[:7]} — 일시정지 전 기준 {BASE_SHA[:7]} → {'변화 없음' if head == BASE_SHA else '★ 변함'}")
    if head != BASE_SHA:
        for cid, upd, author, title in main_commits():
            print(f"   {cid} {upd} {author} {title}")
    for wf, label in WORKFLOWS:
        runs = runs_of(wf)
        print(f"[{label}] ({wf}) 최근 {len(runs)}개")
        for r in runs[:4]:
            mark = ""
            if since and r["utc"] >= since:
                mark = " ◀ 정지 뒤 실행"
            note = ""
            if mark and wf in ("chanceblog.yml", "blogger-en.yml", "blogger-ko.yml", "watchdog.yml"):
                ann = annotations(r["id"])
                hit = "PIPELINE_PAUSE" in ann or "일시정지" in ann
                note = f"\n      주석: {'일시정지 안내 있음' if hit else '★ 일시정지 안내 없음'} — {ann[:150]}"
            print(f"   #{r['num']} {r['kst']:%m-%d %H:%M} {r['conclusion']} {r['duration']}{mark}{note}")
    posts = fetch("https://shine88pc.github.io/chanceblog/posts.json")
    n_live = len(re.findall(r'"absoluteUrl"', posts)) if not posts.startswith("__ERR__") else -1
    print(f"[6 공개 글] 라이브 posts.json 글 수 {n_live} (기준 {BASELINE_PUBLIC_POSTS}) → {'유지' if n_live == BASELINE_PUBLIC_POSTS else '★ 변함/확인 필요'}")
    home = fetch("https://shine88pc.github.io/chanceblog/")
    print(f"[6 사이트] 홈 {'정상(응답 있음)' if not home.startswith('__ERR__') and len(home) > 20000 else '★ 이상: ' + home[:80]}")
    # 확인 필요 모음 이슈
    listing = fetch(f"{BASE}/issues?q=" + urllib.parse.quote("is:issue is:open label:ops-inbox", safe=":+"))
    nums = sorted(set(re.findall(r'/shine88pc/chanceblog/issues/(\d+)', listing)), key=int)
    if nums:
        page = fetch(f"{BASE}/issues/{nums[0]}")
        body = text_of(page)
        has = "자동 발행이 멈춰 있습니다" in body
        print(f"[4 확인 필요 모음] 이슈 #{nums[0]} — 일시정지 항목 {'있음' if has else '아직 없음(다음 정기 실행 뒤 갱신)'}")
    else:
        print("[4 확인 필요 모음] 이슈를 못 찾음(웹 페이지 모양 확인 필요)")
    wd = fetch(f"{BASE}/issues?q=" + urllib.parse.quote('is:issue is:open "[Watchdog]" in:title', safe=":+\"[]"))
    wd_nums = sorted(set(re.findall(r'/shine88pc/chanceblog/issues/(\d+)', wd)), key=int)
    wd_titles = re.findall(r'"title":"([^"]{0,80}Watchdog[^"]{0,60})"', wd)
    wd_items = [(n, wd_titles[i] if i < len(wd_titles) else '') for i, n in enumerate(wd_nums)] if wd_titles else []
    print(f"[5 워치독] 열린 [Watchdog] 이슈 {len(wd_items)}건" + "".join(f"\n   #{n} {text_of(t)[:90]}" for n, t in wd_items[:6]))


if __name__ == "__main__":
    main()
