"""한 커밋 병합 브랜치를 만든다 — 트리는 원본 커밋의 것, 부모는 지정한 ref 하나, 메시지는 파일에서(작업 폴더를 건드리지 않는 `git commit-tree`).
사용: python -X utf8 mk_merge_branch.py <저장소 경로> <트리 원본 커밋> <부모 ref> <커밋 메시지 파일> <새 로컬 브랜치 이름>
작성자·커미터는 강병수 <shine88pc@gmail.com> (한글 환경 변수는 셸이 아니라 파이썬으로 넘긴다). 같은 이름의 브랜치가 이미 있으면 실패한다(되감기 금지 — 새 이름 -2, -3).
끝에 만든 커밋·트리·부모와 변경 요약을 보여 준다."""
import os
import subprocess
import sys

repo, src, parent, msgfile, branch = sys.argv[1:6]
env = dict(os.environ, GIT_AUTHOR_NAME="강병수", GIT_AUTHOR_EMAIL="shine88pc@gmail.com",
           GIT_COMMITTER_NAME="강병수", GIT_COMMITTER_EMAIL="shine88pc@gmail.com")


def git(*args, use_env=None):
    done = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, encoding="utf-8", env=use_env, check=False)
    if done.returncode:
        sys.exit(f"git {' '.join(args[:2])} 실패: {done.stderr.strip()[:300]}")
    return done.stdout.strip()


if subprocess.run(["git", "-C", repo, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}"], capture_output=True).returncode == 0:
    sys.exit(f"이미 있는 브랜치다(되감기 금지): {branch}")
tree = git("rev-parse", f"{src}^{{tree}}")
parent_sha = git("rev-parse", parent)
new = git("commit-tree", tree, "-p", parent_sha, "-F", msgfile, use_env=env)
git("branch", branch, new)
print("브랜치", branch)
print("커밋  ", new)
print("트리  ", tree)
print("부모  ", parent_sha)
print("제목  ", git("log", "-1", "--format=%s", new))
print("작성자", git("log", "-1", "--format=%an <%ae> | %cn <%ce>", new))
print("요약  ", git("diff", "--shortstat", parent_sha, new))
