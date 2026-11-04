"""작업 폴더의 변경을 모두 add 하고 UTF-8 메시지 파일로 커밋한다(작성자·커미터 강병수 <shine88pc@gmail.com> — 한글 환경 변수는 셸이 아니라 파이썬으로 넘긴다).
사용: python -X utf8 commit_as_author.py <작업 폴더> <커밋 메시지 파일> [--only 경로 …]   (--only 가 있으면 그 경로만 add)"""
import os
import subprocess
import sys

repo, msgfile = sys.argv[1], sys.argv[2]
only = sys.argv[4:] if len(sys.argv) > 3 and sys.argv[3] == "--only" else []
env = dict(os.environ, GIT_AUTHOR_NAME="강병수", GIT_AUTHOR_EMAIL="shine88pc@gmail.com",
           GIT_COMMITTER_NAME="강병수", GIT_COMMITTER_EMAIL="shine88pc@gmail.com")


def git(*args, use_env=None):
    done = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, encoding="utf-8", env=use_env)
    if done.returncode:
        sys.exit(f"git {' '.join(args[:2])} 실패: {(done.stderr or done.stdout).strip()[:400]}")
    return done.stdout.strip()


git("add", *(only if only else ["-A"]))
git("commit", "-F", msgfile, use_env=env)
print(git("log", "-1", "--format=%h %an | %s"))
print(git("show", "--stat", "--format=", "HEAD"))
