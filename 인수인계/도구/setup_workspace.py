"""AI 작업 폴더(W)를 만든다 — 새 PC·새 폴더에서 이어서 일할 때 한 번 실행한다.

사용: python -X utf8 인수인계/도구/setup_workspace.py <작업 폴더 W> [--no-clone]

하는 일(이미 있는 것은 건드리지 않고 건너뛴다):
  1. 이 폴더의 `work/*.py`·`work/*.md`(지시서·보고서·병합 부탁 초안)를 W 로, `work/scratch/*.py` 를 W/scratch 로 복사한다.
  2. W/wt_r30  <- 블로그 저장소(chanceblog)를 clone 하고 가지 `ai/claude/desktop-bootstrap-merge`(요청 파일을 쌓는 가지)로 전환한다.
     요청 가지에 `인수인계/이어가기_자료/` 가 있으면 그 파일(병합 없이 갱신되는 최신 보고서·검증 결과)을 W 로 덮어 복사한다.
  3. W/cd_repo <- 데스크톱 저장소(chanceblog-desktop)를 clone 한다(기본 가지).
`--no-clone` 이면 1 만 한다(저장소를 이미 받아 둔 경우).

표준 라이브러리만 쓴다. 공개 저장소를 읽어 받는 일이라 비밀·로그인이 필요 없다(push 는 Git 이 묻는 창에서 운영자가 직접 로그인한다 —
AI 는 비밀번호·토큰을 입력하지 않는다). 설명: 인수인계/도구/README.md
"""
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BLOG = "https://github.com/shine88pc/chanceblog.git"
DESKTOP = "https://github.com/shine88pc/chanceblog-desktop.git"
REQUEST_BRANCH = "ai/claude/desktop-bootstrap-merge"


def run(*args, cwd=None):
    done = subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if done.returncode:
        sys.exit(f"실패: {' '.join(args[:4])} … — {(done.stderr or done.stdout).strip()[:300]}")
    return done.stdout.strip()


def copy_tools(target):
    scripts = sorted((HERE / "work").glob("*.py"))
    documents = sorted((HERE / "work").glob("*.md"))
    scratch = sorted((HERE / "work" / "scratch").glob("*.py"))
    if not scripts or not scratch:
        sys.exit("work/ 폴더에 도구가 없다 — 저장소를 제대로 받았는지 확인한다")
    (target / "scratch").mkdir(parents=True, exist_ok=True)
    pairs = [(path, target) for path in scripts + documents] + [(path, target / "scratch") for path in scratch]
    for source, folder in pairs:
        shutil.copy2(source, folder / source.name)
    print(f"도구·문서 복사: {len(scripts)}개 도구 + {len(documents)}개 문서 -> {target}, {len(scratch)}개 -> {target / 'scratch'}")


def copy_live_materials(blog, target):
    """요청 가지의 속보 자료(병합 없이 갱신되는 최신 보고서·검증 결과)를 W 로 덮어 복사한다 — 있으면 이쪽이 최신이다."""
    live = blog / "인수인계" / "이어가기_자료"
    if not live.is_dir():
        print("속보 자료 없음(요청 가지에 인수인계/이어가기_자료 폴더가 없다)")
        return
    files = [path for path in sorted(live.iterdir()) if path.is_file()]
    for path in files:
        shutil.copy2(path, target / path.name)
    print(f"속보 자료 복사: {len(files)}개 -> {target} (속보 요약은 {blog / '인수인계' / '이어가기_최신.md'})")


def clone(url, folder):
    if (folder / ".git").exists():
        print(f"건너뜀(이미 있음): {folder}")
        return False
    run("git", "clone", url, str(folder))
    print(f"clone: {url} -> {folder}")
    return True


def main():
    args = [arg for arg in sys.argv[1:] if not arg.startswith("--")]
    if len(args) != 1:
        sys.exit(__doc__)
    if shutil.which("git") is None:
        sys.exit("git 이 없다 — Git 을 먼저 설치한다")
    target = Path(args[0]).resolve()
    target.mkdir(parents=True, exist_ok=True)
    copy_tools(target)
    if "--no-clone" in sys.argv:
        return
    clone(BLOG, target / "wt_r30")
    blog = target / "wt_r30"
    run("git", "fetch", "origin", cwd=blog)
    run("git", "checkout", "-B", REQUEST_BRANCH, f"origin/{REQUEST_BRANCH}", cwd=blog)
    print(f"요청 가지로 전환: {blog} @ {REQUEST_BRANCH}")
    copy_live_materials(blog, target)
    clone(DESKTOP, target / "cd_repo")
    print()
    print("다음: 1) 인수인계/작업내용.md 맨 위 '이어가기' 절과 docs/SESSION_START.md §2 를 읽는다")
    print("      2) 정기 현황 알림 크론(인수인계/도구/정기_현황_알림_프롬프트.txt)과 감시(scratch/watch_*.py)를 다시 켠다")
    print("      3) push 가 필요하면 운영자가 Git 로그인 창에서 직접 로그인한다(AI 는 입력하지 않는다)")


if __name__ == "__main__":
    main()
