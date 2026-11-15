"""작업 가지(lane)를 최신 main 위 한 커밋 병합 가지로 만든다(푸시는 하지 않는다).

사용: python -X utf8 mk_lane_merge.py <M번호 예 M030> <슬러그> <lane 가지 또는 커밋> <커밋 메시지 파일> [--no-commit]

1) origin/main 을 가져와 새 작업 폴더 C:/work/ai/wt_<m번호>(가지 ai/claude/<M번호>-<슬러그>)를 만든다.
2) `git merge --squash <lane>` — 충돌이면 알리고 멈춘다(작업 폴더는 충돌 상태로 남는다: 직접 해소 뒤 commit_as_author.py 로 커밋).
3) 병합 결과 트리를 lane 머리와 견준다: lane 이 바꾼 경로(merge-base 기준)의 파일 내용이 lane 머리와 같은지(main 이 같은 파일을 따로 바꾼 곳만 달라야 한다).
4) 메시지 파일로 커밋(commit_as_author.py)하고 머리를 보여 준다.
"""
import os
import subprocess
import sys

REPO = "C:/work/ai/cd_repo"


ENV = dict(os.environ, GIT_AUTHOR_NAME="강병수", GIT_AUTHOR_EMAIL="shine88pc@gmail.com",
           GIT_COMMITTER_NAME="강병수", GIT_COMMITTER_EMAIL="shine88pc@gmail.com")


def git(*args, cwd=REPO, check=True):
    done = subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True, encoding="utf-8", env=ENV)
    if check and done.returncode:
        sys.exit(f"git {' '.join(args[:3])} 실패: {(done.stderr or done.stdout).strip()[:800]}")
    return done


def main():
    if len(sys.argv) < 5:
        sys.exit(__doc__)
    mno, slug, lane, msgfile = sys.argv[1:5]
    no_commit = "--no-commit" in sys.argv[5:]
    wt = f"C:/work/ai/cd_wt_{mno.lower()}"
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
    out = subprocess.run([sys.executable, "-X", "utf8", "C:/work/ai/commit_as_author.py", wt, msgfile],
                         capture_output=True, text=True, encoding="utf-8")
    print(out.stdout[-1200:], out.stderr[-600:])
    print("머리:", git("rev-parse", "HEAD", cwd=wt).stdout.strip())
    print("main 위 커밋 수:", git("rev-list", "--count", "origin/main..HEAD", cwd=wt).stdout.strip())


main()
