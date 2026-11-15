"""블로그 병합 뒤 직접 확인(코드 전용 병합용): main 한 커밋 앞·트리 일치·main 실행 상태·공개 글/사이트맵/피드 숫자·홈의 광고 스크립트 줄 수(기준 1).
사용: python -X utf8 verify_live_counts.py <병합 가지 이름> <병합 전 main 앞 7자> [기대 글 수 38] [기대 사이트맵 45] [기대 피드 38]"""
import re
import subprocess
import sys
import urllib.error
import urllib.request

sys.path.insert(0, "C:/work/ai/scratch")
import wait_ci  # noqa: E402

BASE = "https://shine88pc.github.io/chanceblog"
UA = {"User-Agent": "Mozilla/5.0 (chanceblog-verify-live)", "Cache-Control": "no-cache"}
branch, before = sys.argv[1], sys.argv[2]
want_posts = int(sys.argv[3]) if len(sys.argv) > 3 else 38
want_sitemap = int(sys.argv[4]) if len(sys.argv) > 4 else 45
want_feed = int(sys.argv[5]) if len(sys.argv) > 5 else 38


def git(*args):
    return subprocess.run(["git", "-C", "C:/work/ai/wt_r30", *args], capture_output=True, text=True, encoding="utf-8").stdout.strip()


def get(path):
    url = f"{BASE}/{path}" + ("&" if "?" in path else "?") + "nocache=v"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as err:
        return err.code, ""
    except Exception as err:  # noqa: BLE001
        return -1, str(err)


git("fetch", "-q", "origin", "main", branch)
head = git("rev-parse", "--short=7", "origin/main")
print("main 머리", head, git("log", "-1", "--format=%s", "origin/main")[:70])
print("앞으로 간 커밋 수:", git("rev-list", "--count", f"{before}..origin/main"), "(기대 1)")
main_tree, br_tree = git("rev-parse", "origin/main^{tree}"), git("rev-parse", f"origin/{branch}^{{tree}}")
print("트리 일치:", main_tree == br_tree, main_tree[:10])
runs = wait_ci.runs_for("shine88pc/chanceblog", "main", head)
print("main 실행:", [(r["name"][:22], r["status"], r["conclusion"]) for r in runs])
code, body = get("")
print("홈", code, "| adsbygoogle 줄 수:", body.count("adsbygoogle"), "(기준 1)")
code, body = get("posts.json")
print("posts.json", code, "글", body.count('"absoluteUrl"'), f"(기대 {want_posts})")
code, body = get("sitemap.xml")
print("sitemap", code, "주소", body.count("<loc>"), f"(기대 {want_sitemap})")
code, body = get("feed.xml")
print("feed", code, "항목", body.count("<item>"), f"(기대 {want_feed})")
