"""AI 작업 폴더(W)를 만든다 — 새 PC·새 폴더에서 이어서 일할 때 한 번 실행한다.

사용: python -X utf8 인수인계/도구/setup_workspace.py <작업 폴더 W> [--no-clone]

하는 일:
  1. 이 폴더의 `work/*.py`·`work/*.md`(도구·지시서·보고서·병합 부탁 초안)와 `work/양식/*.md`(병합 부탁·진행 현황 양식)를 W 로,
     `work/scratch/*.py`·`work/scratch/*.sh`(검사·감시 읽기 도구)를 W/scratch 로, 정기 현황 알림 프롬프트(`정기_현황_알림_프롬프트_v3.txt`)를 W/cron_status_prompt_v3.txt 로 복사한다.
     같은 이름이 W 에 이미 있으면 저장소 것으로 덮어쓴다(저장소가 진실이다 — W 의 도구는 상태를 갖지 않는다).
  2. W/wt_r30  <- 블로그 저장소(chanceblog)를 clone 하고 요청 가지 `ai/claude/NO-MERGE-operator-requests`(요청 파일을 쌓는 병합 금지 가지)로 전환한다(이미 clone 돼 있으면 건너뛴다).
     요청 가지에 `인수인계/이어가기_자료/` 가 있으면 그 파일(병합 없이 갱신되는 최신 보고서·검증 결과)을 W 로 덮어 복사한다.
  3. W/cd_repo <- 데스크톱 저장소(chanceblog-desktop)를 clone 한다(기본 가지, 이미 있으면 건너뛴다).
`--no-clone` 이면 1 만 한다(저장소를 이미 받아 둔 경우, 또는 복사만 점검할 때 — 네트워크를 쓰지 않는다).

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
REQUEST_BRANCH = "ai/claude/NO-MERGE-operator-requests"
PROMPT_SOURCE = "정기_현황_알림_프롬프트_v3.txt"       # 저장소 안 이름(인수인계/도구/ 바로 아래)
PROMPT_TARGET = "cron_status_prompt_v3.txt"           # W 안 이름(작업내용.md·프롬프트 문서가 부르는 이름)


def run(*args, cwd=None):
    done = subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if done.returncode:
        sys.exit(f"실패: {' '.join(args[:4])} … — {(done.stderr or done.stdout).strip()[:300]}")
    return done.stdout.strip()


def plan_copy():
    """복사할 파일 목록 — (저장소 안 원본, W 아래 상대 위치). 도구 파일이 하나도 없으면 빈 목록."""
    work = HERE / "work"
    pairs = [(path, Path(path.name)) for pattern in ("*.py", "*.md") for path in sorted(work.glob(pattern))]
    pairs += [(path, Path("scratch") / path.name) for pattern in ("*.py", "*.sh") for path in sorted((work / "scratch").glob(pattern))]
    pairs += [(path, Path(path.name)) for path in sorted((work / "양식").glob("*.md"))]
    prompt = HERE / PROMPT_SOURCE
    if prompt.is_file():
        pairs.append((prompt, Path(PROMPT_TARGET)))
    return pairs


def copy_tools(target):
    """plan_copy() 의 파일을 W 로 복사한다. 복사한 (원본, W 아래 위치) 목록을 돌려준다."""
    pairs = plan_copy()
    if not any(rel.parent == Path(".") and rel.suffix == ".py" for _, rel in pairs) or not any(rel.parent == Path("scratch") for _, rel in pairs):
        sys.exit("work/ 폴더에 도구가 없다 — 저장소를 제대로 받았는지 확인한다")
    (target / "scratch").mkdir(parents=True, exist_ok=True)
    for source, rel in pairs:
        shutil.copy2(source, target / rel)
    tools = sum(1 for _, rel in pairs if rel.parent == Path(".") and rel.suffix == ".py")
    documents = sum(1 for _, rel in pairs if rel.parent == Path(".") and rel.suffix in (".md", ".txt"))
    scratch = sum(1 for _, rel in pairs if rel.parent == Path("scratch"))
    print(f"도구·문서·양식 복사: {tools}개 도구 + {documents}개 문서·양식·프롬프트 -> {target}, {scratch}개 검사·감시 도구 -> {target / 'scratch'}")
    return pairs


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
    if shutil.which("git") is None and "--no-clone" not in sys.argv:
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
    print("다음: 1) 인수인계/작업내용.md 맨 위 30초 카드와 §0-1, docs/SESSION_START.md §2-4 를 읽는다")
    print("      2) 첫 점검: python -X utf8 scratch/resume_check.py (W 안에서) — 세 저장소 머리·열린 PR·최근 이슈·다음 번호·작업 폴더 상태")
    print("      3) 정기 현황 알림 크론(cron_status_prompt_v3.txt)과 감시(scratch/watch_issues.py·watch_heads2.sh·watch_light.py·watch_desktop.py)를 다시 켠다")
    print("      4) push 가 필요하면 운영자가 Git 로그인 창에서 직접 로그인한다(AI 는 입력하지 않는다)")


if __name__ == "__main__":
    main()
