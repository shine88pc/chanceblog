"""chanceblog-desktop 저장소를 API 한도 없이 지켜본다(git ls-remote + 공개 웹 페이지만, api.github.com 호출 0회).
새 PR 생성·PR 머리 변경·main 이동(병합)·새로 실패한 실행을 한 줄씩 알린다. 한 번 켜면 최대 29분 돌고 끝난다(끝나면 다시 켠다)."""
import html
import re
import subprocess
import time
import urllib.error
import urllib.request

REPO = "shine88pc/chanceblog-desktop"
BASE = f"https://github.com/{REPO}"
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


def run_title(rid):
    page = fetch(f"{BASE}/actions/runs/{rid}") or ""
    title = re.search(r"<title>(.*?)</title>", page, re.S)
    return " · ".join(text_of(title.group(1)).split(" · ")[0:2]) if title else "?"


print("감시 시작(chanceblog-desktop, 웹 페이지·git 만 사용)", flush=True)
known_main, known_prs = ls_remote()
known_commits = {c[0][:7] for c in main_commits()}
known_failures = failure_ids()
print(f"기준: main {str(known_main)[:7]} · PR {len(known_prs)}건 · 실패 실행 {len(known_failures)}건", flush=True)

while time.time() < DEADLINE:
    time.sleep(min(INTERVAL, max(1, DEADLINE - time.time())))
    try:
        main_sha, prs = ls_remote()
        for n, sha in sorted(prs.items()):
            if n not in known_prs:
                print(f"[desktop] PR #{n} 생성됨(머리 {sha[:7]})", flush=True)
            elif known_prs[n] != sha:
                print(f"[desktop] PR #{n} 머리가 바뀜 {known_prs[n][:7]}→{sha[:7]}", flush=True)
        known_prs = prs
        if main_sha and main_sha != known_main:
            fresh = [c for c in main_commits() if c[0][:7] not in known_commits]
            for cid, title, author in reversed(fresh):
                print(f"[desktop] main 에 새 커밋({author}) {cid[:7]}: {title}", flush=True)
                known_commits.add(cid[:7])
            known_main = main_sha
        failures = failure_ids()
        for rid in sorted(failures - known_failures):
            print(f"[desktop] 실행 실패: {run_title(rid)} (#{rid})", flush=True)
        known_failures |= failures
    except Exception as exc:  # noqa: BLE001 - 감시는 죽지 않는다
        print(f"[desktop] 감시 중 일시 오류 {type(exc).__name__}", flush=True)
print("[desktop] 감시 시간 종료(다시 켜야 함)", flush=True)
