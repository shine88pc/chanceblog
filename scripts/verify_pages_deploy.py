"""Pages 배포 뒤, 공개 사이트에 저장소의 최신 글이 실제로 올라왔는지 확인한다.

배포 워크플로가 초록이어도 "글이 공개 사이트에서 보인다"는 뜻은 아니다(빌드 설정·캐시·권한 문제로 반영이 안 될 수 있다).
저장소 `_posts`의 가장 새 글(같은 시각에 만든 KR/EN 쌍)이 공개 `posts.json`에 있고, 그 글의 주소가 열리면(HTTP 200) 통과한다.
공개 사이트가 아직 새 배포를 내보내지 못했을 수 있으니 몇 분 동안 다시 시도하고, 끝내 없으면 실패(종료 1)로 끝나
배포 실행이 빨갛게 된다(워치독이 그 실패를 알린다).

사용: python scripts/verify_pages_deploy.py --base https://사용자.github.io/저장소/  [--root .] [--attempts 10] [--wait 30]
환경변수: PAGE_URL(--base 대신), GITHUB_SHA(요약에 표시), GITHUB_STEP_SUMMARY(있으면 요약을 덧붙임)
종료 코드: 0 반영 확인(또는 확인할 글 없음) / 1 반영 안 됨 / 2 사용법·설정 오류
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.console import safe_output  # noqa: E402

POST_NAME = re.compile(r"^(\d{4}-\d{2}-\d{2})-(.+)\.md$")
TIME_TAIL = re.compile(r"(\d{6})$")
MAX_BYTES = 20 * 1024 * 1024  # posts.json 이 이보다 크면 읽지 않는다(이상 징후)
USER_AGENT = "chanceblog-verify-pages"


def fold(text, limit=200):
    """외부에서 온 문자열을 한 줄로 접는다(로그 줄 머리의 ::error:: 같은 명령 위조 방지)."""
    folded = " ".join(str(text).split())
    if folded.startswith("::"):
        folded = " " + folded
    return folded[:limit]


def newest_posts(root):
    """저장소 `_posts` 아래에서 가장 새 글의 경로 목록(저장소 기준, 예: `_posts/기술·미래/2026-10-25-KR-101307.md`).

    '새롭다'는 파일명의 날짜와 끝의 시각(HHMMSS)으로 정한다. 같은 시각에 만든 KR/EN 쌍이면 둘 다 돌려준다."""
    root = Path(root)
    found = []
    for path in sorted((root / "_posts").rglob("*.md")):
        match = POST_NAME.match(path.name)
        if not match:
            continue
        tail = TIME_TAIL.search(match.group(2))
        found.append(((match.group(1), tail.group(1) if tail else "000000"), path.relative_to(root).as_posix()))
    if not found:
        return []
    best = max(key for key, _ in found)
    return [rel for key, rel in found if key == best]


def fetch(url, timeout=30, opener=urllib.request.urlopen):
    """(HTTP 상태, 본문 바이트). 4xx/5xx 도 예외 대신 상태로 돌려준다. 네트워크 오류는 (0, 오류 설명 바이트)."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Cache-Control": "no-cache"})
    try:
        with opener(req, timeout=timeout) as resp:
            return resp.status, resp.read(MAX_BYTES + 1)
    except urllib.error.HTTPError as exc:
        return exc.code, b""
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        return 0, type(exc).__name__.encode("utf-8")


def valid_base(base):
    """공개 사이트 주소: https, 호스트가 있고, 주소에 계정 정보(user@)가 없다."""
    parts = urllib.parse.urlsplit(base)
    return parts.scheme == "https" and bool(parts.netloc) and "@" not in parts.netloc


def with_cache_buster(url, token):
    """CDN 캐시를 피하려고 쿼리를 붙인다(사이트는 쿼리를 무시한다)."""
    parts = urllib.parse.urlsplit(url)
    query = (parts.query + "&" if parts.query else "") + "cb=" + urllib.parse.quote(str(token), safe="")
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))


def check_once(base, expected, token, fetcher):
    """한 번 확인한다. (문제 목록, 확인된 글 주소 목록). 문제가 없으면 []."""
    status, body = fetcher(with_cache_buster(base + "posts.json", token))
    if status != 200:
        return [f"posts.json 을 읽지 못함(HTTP {status or '연결 실패'})"], []
    if len(body) > MAX_BYTES:
        return ["posts.json 이 비정상적으로 큼"], []
    try:
        entries = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return ["posts.json 이 올바른 JSON 이 아님"], []
    if not isinstance(entries, list):
        return ["posts.json 의 최상위 값이 목록이 아님"], []
    by_path = {e.get("path"): e for e in entries if isinstance(e, dict)}
    problems, urls = [], []
    for rel in expected:
        entry = by_path.get(rel)
        if entry is None:
            problems.append(f"공개 posts.json 에 없음: {fold(rel, 120)}")
            continue
        url = str(entry.get("absoluteUrl") or "")
        if not url.startswith(("https://", "http://")):
            problems.append(f"주소가 없음: {fold(rel, 120)}")
            continue
        code, _ = fetcher(with_cache_buster(url, token))
        if code != 200:
            problems.append(f"글 주소가 열리지 않음(HTTP {code or '연결 실패'}): {fold(url, 160)}")
            continue
        urls.append(url)
    return problems, urls


def verify(base, root, attempts=10, wait=30, fetcher=None, sleep=None, token="run"):
    """(성공 여부, 요약 마크다운, 로그 줄 목록, 확인할 글 경로)."""
    fetcher = fetcher or fetch  # 기본값을 인자 자리에 두면 정의 시점의 함수에 묶여 테스트에서 바꿀 수 없다
    sleep = sleep or time.sleep
    expected = newest_posts(root)
    if not expected:
        return True, "- 저장소에 확인할 글이 없어 건너뜀", ["확인할 글이 없어 건너뜁니다."], []
    problems, urls, tried = [], [], 0
    for attempt in range(1, attempts + 1):
        tried = attempt
        problems, urls = check_once(base, expected, f"{token}-{attempt}", fetcher)
        if not problems:
            break
        print(f"  시도 {attempt}/{attempts}: " + "; ".join(problems))
        if attempt < attempts:
            sleep(wait)
    sha = (os.environ.get("GITHUB_SHA") or "")[:7]
    head = ["### 공개 사이트 반영 확인", f"- 배포 커밋: {sha or '(알 수 없음)'}",
            "- 확인한 최신 글: " + ", ".join(f"`{Path(p).name}`" for p in expected)]
    if not problems:
        lines = head + [f"- 결과: **반영됨** — 공개 `posts.json`에 있고 주소가 열림(HTTP 200), 시도 {tried}회"]
        lines += [f"  - {fold(url, 200)}" for url in urls]
        return True, "\n".join(lines), ["반영 확인: " + ", ".join(urls)], expected
    lines = head + [f"- 결과: **반영 안 됨** — 시도 {tried}회(약 {wait * (tried - 1)}초) 뒤에도 확인되지 않음"]
    lines += [f"  - {fold(p, 200)}" for p in problems]
    lines += ["- 조치: Actions의 이 실행 로그와 Deploy GitHub Pages 이전 실행을 확인하고, 사이트 주소를 직접 열어 본다"]
    return False, "\n".join(lines), problems, expected


def _write_summary(markdown):
    target = os.environ.get("GITHUB_STEP_SUMMARY")
    if not target:
        return
    try:
        with open(target, "a", encoding="utf-8") as fh:
            fh.write(markdown.rstrip() + "\n\n")
    except OSError as exc:
        print(f"실행 요약 쓰기 실패(점검 결과에는 영향 없음): {fold(exc)}")


def main(argv=None):
    safe_output()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base", default=os.environ.get("PAGE_URL", ""))
    parser.add_argument("--root", default=".")
    parser.add_argument("--attempts", type=int, default=10)
    parser.add_argument("--wait", type=int, default=30)
    args = parser.parse_args(argv)
    base = args.base.strip()
    if not valid_base(base):
        print("::error::--base(또는 PAGE_URL)는 https:// 로 시작하는 공개 사이트 주소여야 합니다.")
        return 2
    if not base.endswith("/"):
        base += "/"
    if args.attempts < 1 or args.wait < 0:
        print("::error::--attempts 는 1 이상, --wait 는 0 이상이어야 합니다.")
        return 2
    token = (os.environ.get("GITHUB_SHA") or "run")[:12]
    ok, summary, lines, expected = verify(base, args.root, args.attempts, args.wait, token=token)
    _write_summary(summary)
    for line in lines:
        print(fold(line, 400))
    if not ok:
        print("::error::공개 사이트에 최신 글이 반영되지 않았습니다. 실행 요약을 확인하세요.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
