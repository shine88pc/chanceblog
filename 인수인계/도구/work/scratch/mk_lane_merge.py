"""작업 가지(lane)를 최신 main 위 한 커밋 병합 가지로 만든다(푸시는 하지 않는다) — 블로그(chanceblog) 저장소용.

사용: python -X utf8 mk_lane_merge.py <M번호 예 M030> <슬러그> <lane 가지 또는 커밋> <커밋 메시지 파일의 절대 경로> [--no-commit]

1) origin/main 을 가져와 새 작업 폴더 <W>/wt_<m번호>(가지 ai/claude/<M번호>-<슬러그>)를 만든다. W 는 이 파일이 있는 폴더의 위 폴더(setup_workspace.py 가 만든 작업 폴더)이고
   기준 저장소는 <W>/wt_r30 이다. 같은 이름의 작업 폴더와 로컬 가지가 이미 있으면 지우고 다시 만든다(원격은 건드리지 않는다).
2) `git merge --squash <lane>` — 충돌이면 알리고 멈춘다(작업 폴더는 충돌 상태로 남는다: 직접 해소 뒤 commit_as_author.py 로 커밋).
3) 병합 결과 트리를 lane 머리와 견준다: lane 이 바꾼 경로(merge-base 기준)의 파일 내용이 lane 머리와 같은지(main 이 같은 파일을 따로 바꾼 곳만 달라야 한다).
4) 메시지 파일로 커밋(commit_as_author.py)하고 머리를 보여 준다.
푸시·병합 부탁은 하지 않는다 — 병합 가지는 독립 검증이 끝난 뒤에만 만들고, 그 뒤 절차는 인수인계/도구/README.md 의 '병합 부탁 보내기'를 따른다.
"""
import os
import re as _re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORK = HERE.parent                                   # 작업 폴더 W (setup_workspace.py 가 만든 폴더)
REPO = str(WORK / "wt_r30")
COMMIT_TOOL = str(WORK / "commit_as_author.py")
WT_PREFIX = "wt_"

_AUTHOR = (Path(__file__).resolve().parent.parent / "commit_as_author.py").read_text(encoding="utf-8")     # 고정 작성자는 commit_as_author.py 의 상수 하나만 쓴다(확인 032 승인 — 이 도구에 개인 값을 따로 두지 않는다)
_NAME, _MAIL = (_re.search("GIT_AUTHOR_" + _key + '="([^"]+)"', _AUTHOR).group(1) for _key in ("NAME", "EMAIL"))
ENV = dict(os.environ, GIT_AUTHOR_NAME=_NAME, GIT_AUTHOR_EMAIL=_MAIL, GIT_COMMITTER_NAME=_NAME, GIT_COMMITTER_EMAIL=_MAIL)


def git(*args, cwd=REPO, check=True):
    done = subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True, encoding="utf-8", env=ENV)
    if check and done.returncode:
        sys.exit(f"git {' '.join(args[:3])} 실패: {(done.stderr or done.stdout).strip()[:800]}")
    return done


def main():
    if len(sys.argv) < 5:
        sys.exit(__doc__)
    mno, slug, lane, msgfile = sys.argv[1:5]
    msgfile = str(Path(msgfile).resolve())               # 상대 경로면 저장소 기준으로 읽혀 실패하므로 절대 경로로 바꾼다
    no_commit = "--no-commit" in sys.argv[5:]
    wt = str(WORK / f"{WT_PREFIX}{mno.lower()}")
    branch = f"ai/claude/{mno}-{slug}"
    git("fetch", "origin", "main", "-q")
    base = git("rev-parse", "origin/main").stdout.strip()
    lane_head = git("rev-parse", lane).stdout.strip()
    mb = git("merge-base", "origin/main", lane_head).stdout.strip()
    print(f"main={base[:7]} lane={lane_head[:7]} merge-base={mb[:7]}")
    if os.path.isdir(wt):
        git("worktree", "remove", "--force", wt, check=False)
    git("branch", "-D", branch, check=False)
    git("worktree", "add", "-q", "-b", branch, wt, "origin/main")
    done = git("merge", "--squash", lane_head, cwd=wt, check=False)
    print((done.stdout or "").strip()[-600:])
    if done.returncode:
        print("충돌:", (done.stderr or "").strip()[-600:])
        print(git("status", "--short", cwd=wt, check=False).stdout)
        sys.exit(f"충돌 — {wt} 에서 직접 해소하세요(가지 {branch})")
    # 3) 견주기: lane 이 바꾼 경로가 병합 결과에서 lane 머리와 같은지
    changed = [p for p in git("diff", "--name-only", mb, lane_head).stdout.splitlines() if p]
    diffs = []
    for p in changed:
        a = git("rev-parse", f":{p}", cwd=wt, check=False).stdout.strip()   # 인덱스(병합 결과)
        b = git("rev-parse", f"{lane_head}:{p}", check=False).stdout.strip()
        if a != b:
            diffs.append(p)
    print(f"lane 이 바꾼 경로 {len(changed)}개 중 병합 결과가 lane 머리와 다른 것 {len(diffs)}개: {diffs[:12]}")
    print(git("diff", "--cached", "--stat", cwd=wt).stdout[-1500:])
    if no_commit:
        print("(--no-commit) 커밋하지 않음:", wt)
        return
    out = subprocess.run([sys.executable, "-X", "utf8", COMMIT_TOOL, wt, msgfile],
                         capture_output=True, text=True, encoding="utf-8")
    print(out.stdout[-1200:], out.stderr[-600:])
    print("머리:", git("rev-parse", "HEAD", cwd=wt).stdout.strip())
    print("main 위 커밋 수:", git("rev-list", "--count", "origin/main..HEAD", cwd=wt).stdout.strip())


if __name__ == "__main__":
    main()
