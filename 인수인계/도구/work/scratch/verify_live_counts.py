"""블로그 병합 뒤 직접 확인(코드 전용 병합용): main 한 커밋 앞·트리 일치·main 실행 상태·공개 글/사이트맵/피드 숫자·홈의 광고 스크립트 줄 수(기준 1).
사용: python -X utf8 verify_live_counts.py <병합 가지 이름> <병합 전 main 앞 7자> [기대 글 수 38] [기대 사이트맵 45] [기대 피드 38]
읽기 전용이다 — 푸시·쓰기가 없고 비밀도 쓰지 않는다. 작업 폴더 W 의 wt_r30(블로그 저장소 clone)에서 `git fetch` 와 읽기만 하고, 공개 사이트와 GitHub 공개 웹·REST 를 읽는다.
그래서 push 권한이 없는 환경에서도 쓸 수 있다. 기대 숫자의 기본값(38·45·38)은 이 도구를 만들 때(2026-11-10)의 값이니 지금의 공개 글 수에 맞춰 인자로 준다.
이 파일은 W/scratch 에 복사돼 있다고 가정한다(W 는 이 파일이 있는 폴더의 위 폴더). 저장소 안 사본(인수인계/도구/work/scratch)에서 돌려도 같은 규칙으로 work 폴더를 W 로 본다."""
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import wait_ci  # noqa: E402

WORK = HERE.parent                         # 작업 폴더 W (setup_workspace.py 가 만든 폴더)
BLOG_REPO = WORK / "wt_r30"                # 블로그 저장소 clone
BLOG = "shine88pc/chanceblog"
BASE = "https://shine88pc.github.io/chanceblog"
UA = {"User-Agent": "Mozilla/5.0 (chanceblog-verify-live)", "Cache-Control": "no-cache"}
DEFAULT_COUNTS = (38, 45, 38)              # 글 수·사이트맵 주소 수·피드 항목 수의 기본 기대값(2026-11-10)


def git(*args):
    return subprocess.run(["git", "-C", str(BLOG_REPO), *args], capture_output=True, text=True, encoding="utf-8").stdout.strip()


def get(path):
    url = f"{BASE}/{path}" + ("&" if "?" in path else "?") + "nocache=v"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as err:
        return err.code, ""
    except Exception as err:  # noqa: BLE001
        return -1, str(err)


def expected_counts(argv):
    """인자 3개(기대 글 수·사이트맵·피드)를 정수로 읽는다 — 없으면 기본값."""
    values = list(DEFAULT_COUNTS)
    for index, text in enumerate(argv[:3]):
        values[index] = int(text)
    return tuple(values)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) < 2:
        print(__doc__)
        return 2
    branch, before = argv[0], argv[1]
    want_posts, want_sitemap, want_feed = expected_counts(argv[2:])
    if not (BLOG_REPO / ".git").exists():
        print(f"블로그 저장소 clone 이 없다: {BLOG_REPO} — 인수인계/도구/setup_workspace.py 로 작업 폴더를 먼저 만든다")
        return 2
    git("fetch", "-q", "origin", "main", branch)
    head = git("rev-parse", "--short=7", "origin/main")
    print("main 머리", head, git("log", "-1", "--format=%s", "origin/main")[:70])
    print("앞으로 간 커밋 수:", git("rev-list", "--count", f"{before}..origin/main"), "(기대 1)")
    main_tree, br_tree = git("rev-parse", "origin/main^{tree}"), git("rev-parse", f"origin/{branch}^{{tree}}")
    print("트리 일치:", main_tree == br_tree, main_tree[:10])
    runs = wait_ci.runs_for(BLOG, "main", head)
    print("main 실행:", [(r["name"][:22], r["status"], r["conclusion"]) for r in runs])
    code, body = get("")
    print("홈", code, "| adsbygoogle 줄 수:", body.count("adsbygoogle"), "(기준 1)")
    code, body = get("posts.json")
    print("posts.json", code, "글", body.count('"absoluteUrl"'), f"(기대 {want_posts})")
    code, body = get("sitemap.xml")
    print("sitemap", code, "주소", body.count("<loc>"), f"(기대 {want_sitemap})")
    code, body = get("feed.xml")
    print("feed", code, "항목", body.count("<item>"), f"(기대 {want_feed})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
