"""chanceblog(블로그) 저장소를 API 한도 없이 지켜본다(git ls-remote + 공개 웹 페이지만, api.github.com 호출 0회).
새 PR 생성·PR 머리 변경·main 이동(병합)·새로 실패한 실행·소유자 열린 이슈 변화·봇이 만든 `텔레그램수신` 이슈를 한 줄씩 알린다. 한 번 켜면 최대 29분 돌고 끝난다(끝나면 다시 켠다).
(2026-11-04 17:09 이전 판은 지워져 이 파일로 다시 만들었다 — 기준 줄·사건 문구는 같은 모양)"""
import html
import re
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request

REPO = "shine88pc/chanceblog"
BASE = f"https://github.com/{REPO}"
OWNER = "shine88pc"
TELEGRAM_LABEL = "텔레그램수신"
INTERVAL = 120
DEADLINE = time.time() + 29 * 60
UA = {"User-Agent": "Mozilla/5.0 (chanceblog-light-watch)"}


def fetch(url, timeout=40):
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise


def text_of(fragment):
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", fragment))).strip()


def ls_remote():
    out = subprocess.run(["git", "ls-remote", f"https://github.com/{REPO}.git", "refs/heads/main", "refs/pull/*/head"], capture_output=True, text=True, timeout=90).stdout
    main, prs = None, {}
    for line in out.splitlines():
        sha, _, ref = line.partition("\t")
        if ref == "refs/heads/main":
            main = sha
        else:
            m = re.fullmatch(r"refs/pull/(\d+)/head", ref)
            if m:
                prs[int(m.group(1))] = sha
    return main, prs


def main_commits():
    feed = fetch(f"{BASE}/commits/main.atom") or ""
    out = []
    for entry in re.findall(r"<entry>(.*?)</entry>", feed, re.S)[:8]:
        cid = re.search(r"/commit/([0-9a-f]{7,40})", entry)
        title = re.search(r"<title>(.*?)</title>", entry, re.S)
        author = re.search(r"<name>(.*?)</name>", entry, re.S)
        if cid:
            out.append((cid.group(1), text_of(title.group(1))[:90] if title else "", text_of(author.group(1)) if author else ""))
    return out


def failure_ids():
    page = fetch(f"{BASE}/actions?query=is%3Afailure") or ""
    return set(int(i) for i in re.findall(r"/actions/runs/(\d+)", page))


def run_count():
    page = fetch(f"{BASE}/actions") or ""
    return len(set(re.findall(r"/actions/runs/(\d+)", page)))


def run_title(rid):
    page = fetch(f"{BASE}/actions/runs/{rid}") or ""
    title = re.search(r"<title>(.*?)</title>", page, re.S)
    return " · ".join(text_of(title.group(1)).split(" · ")[0:2]) if title else "?"


def issues_of(query):
    """열린 이슈 목록 첫 쪽의 {번호: 제목} — 공개 웹 페이지만 읽는다."""
    page = fetch(f"{BASE}/issues?q=" + urllib.parse.quote(query, safe=":+")) or ""
    found = {}
    for number, title in re.findall(r'id="issue_(\d+)_link"[^>]*>(.*?)</a>', page, re.S):
        found[int(number)] = text_of(title)[:80]
    if not found:                                              # 페이지 모양이 바뀌었을 때를 대비한 느슨한 읽기
        for number in re.findall(rf"/{re.escape(REPO)}/issues/(\d+)", page):
            found.setdefault(int(number), "")
    return found


def owner_issues():
    return issues_of(f"is:issue is:open author:{OWNER}")


def telegram_issues():
    return issues_of(f"is:issue is:open label:{TELEGRAM_LABEL}")


print("감시 시작(웹 페이지·git 만 사용, API 한도 없음) — 켠 시각 이후 변화를 알립니다", flush=True)
known_main, known_prs = ls_remote()
known_commits = {c[0][:7] for c in main_commits()}
known_failures = failure_ids()
known_owner = owner_issues()
known_telegram = telegram_issues()
print(f"기준: main {str(known_main)[:7]} · PR {len(known_prs)}건 · 실행 목록 {run_count()}건 · 소유자 열린 이슈 {sorted(known_owner)} · 텔레그램수신 열린 이슈 {sorted(known_telegram)}", flush=True)

while time.time() < DEADLINE:
    time.sleep(min(INTERVAL, max(1, DEADLINE - time.time())))
    try:
        main_sha, prs = ls_remote()
        for n, sha in sorted(prs.items()):
            if n not in known_prs:
                print(f"PR #{n} 생성됨(머리 {sha[:7]})", flush=True)
            elif known_prs[n] != sha:
                print(f"PR #{n} 머리가 바뀜 {known_prs[n][:7]}→{sha[:7]}", flush=True)
        known_prs = prs
        if main_sha and main_sha != known_main:
            fresh = [c for c in main_commits() if c[0][:7] not in known_commits]
            for cid, title, author in reversed(fresh):
                print(f"main 에 새 커밋({author}) {cid[:7]}: {title}", flush=True)
                known_commits.add(cid[:7])
            known_main = main_sha
        failures = failure_ids()
        for rid in sorted(failures - known_failures):
            print(f"실행 실패: {run_title(rid)} (#{rid})", flush=True)
        known_failures |= failures
        owner = owner_issues()
        for n in sorted(set(owner) - set(known_owner)):
            print(f"소유자 새 이슈 #{n}: {owner[n]}", flush=True)
        for n in sorted(set(known_owner) - set(owner)):
            print(f"소유자 열린 이슈 #{n} 가 목록에서 빠짐(닫힘 또는 쪽 밀림)", flush=True)
        known_owner = owner
        telegram = telegram_issues()
        for n in sorted(set(telegram) - set(known_telegram)):
            print(f"텔레그램수신 새 이슈 #{n}: {telegram[n]}", flush=True)
        known_telegram = telegram
    except Exception as exc:  # noqa: BLE001 - 감시는 죽지 않는다
        print(f"감시 중 일시 오류 {type(exc).__name__}", flush=True)
print("감시 시간 종료(다시 켜야 함)", flush=True)
