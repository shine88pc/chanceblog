"""앱 갈래 여러 개를 '지금 main 끝' 위 **한 커밋** 병합 가지로 묶는다(총괄 전용, 푸시는 하지 않는다).
검사(CI) 한 번에 갈래 둘셋을 병합해 일정을 줄이려는 용도 — 서로 겹치는 파일이 없고 각각 독립 검증을 통과한 갈래만 묶는다.
사용:
  py -3.12 -X utf8 C:/work/ai/scratch/combine_lanes_desktop.py <M번호> <슬러그> <커밋 메시지 파일> <갈래머리1> <갈래머리2> [<갈래머리3> ...] [--union 경로,경로] [--dry]
하는 일: scratch/squash_onto.py 로 갈래를 차례로 얹는다(앞 결과를 임시 커밋으로 만들어 다음 갈래의 '얹을 곳' 으로 쓴다 — 덧붙이기 전용 문서 충돌은 --union 합집합).
  마지막 트리를 mk_merge_branch.py 로 `ai/claude/<M번호>-<슬러그>` 한 커밋(부모 origin/main)으로 만든다. --dry 면 트리·충돌 여부만 보이고 가지는 안 만든다.
종료 코드: 0 성공 · 3 사람이 풀 충돌이 남음 · 1 오류."""
import os
import re
import subprocess
import sys

W = "C:/work/ai"
REPO = f"{W}/cd_repo"
import re as _re
from pathlib import Path as _Path

_AUTHOR = (_Path(__file__).resolve().parent.parent / "commit_as_author.py").read_text(encoding="utf-8")     # 고정 작성자는 commit_as_author.py 의 상수 하나만 쓴다(2026-11-23 MIG1 — 이 사본에 개인 값을 따로 두지 않는다)
_NAME, _MAIL = (_re.search("GIT_AUTHOR_" + _key + '="([^"]+)"', _AUTHOR).group(1) for _key in ("NAME", "EMAIL"))
ENV = dict(os.environ, GIT_AUTHOR_NAME=_NAME, GIT_AUTHOR_EMAIL=_MAIL, GIT_COMMITTER_NAME=_NAME, GIT_COMMITTER_EMAIL=_MAIL)


def run(*args, env=None):
    return subprocess.run(list(args), capture_output=True, text=True, encoding="utf-8", errors="replace", env=env or ENV)


def git(*args):
    done = run("git", "-C", REPO, *args)
    if done.returncode:
        sys.exit(f"git {' '.join(args[:3])} 실패: {(done.stderr or done.stdout).strip()[:400]}")
    return done.stdout.strip()


def main(argv):
    union = ""
    dry = False
    onto_ref = None
    pos = []
    it = iter(argv)
    for a in it:
        if a == "--union":
            union = next(it)
        elif a == "--dry":
            dry = True
        elif a == "--onto":     # 글자 읽기 갈래처럼 다른 갈래(B1) 위에서 만들어진 것들은 그 갈래의 머리 위에 얹어야 겹침이 안 생긴다(최종 부모는 그대로 origin/main)
            onto_ref = next(it)
        else:
            pos.append(a)
    if len(pos) < 5:
        print(__doc__)
        return 1
    mno, slug, msgfile, *heads = pos
    git("fetch", "origin", "main", "-q")
    onto = git("rev-parse", "origin/main")
    base = git("rev-parse", onto_ref) if onto_ref else onto
    tree = None
    print(f"main={onto[:7]} · 갈래 {len(heads)}개")
    for i, head in enumerate(heads, 1):
        head_sha = git("rev-parse", head)
        cmd = [sys.executable, "-X", "utf8", f"{W}/scratch/squash_onto.py", REPO, f"{W}/sq_comb", base, head_sha]
        if union:
            cmd += ["--union", union]
        done = run(*cmd)
        out = (done.stdout + done.stderr).strip()
        print(f"--- 갈래 {i}: {head_sha[:7]}")
        print(out[-600:])
        if done.returncode == 3:
            print("→ 사람이 풀 충돌이 있어 멈춘다(임시 작업 나무 C:/work/ai/sq_comb 에 충돌 표시가 남아 있다).")
            return 3
        if done.returncode:
            return 1
        found = re.search(r"^TREE (\w+)", out, re.M)
        if not found:
            print("TREE 줄을 못 찾음")
            return 1
        tree = found.group(1)
        if i < len(heads):
            made = run("git", "-C", REPO, "commit-tree", tree, "-p", base, "-m", f"tmp: main + lane {i}")
            if made.returncode:
                sys.exit(f"임시 커밋 실패: {made.stderr.strip()[:300]}")
            base = made.stdout.strip()
    print(f"최종 TREE {tree}")
    print("main 대비:", git("diff", "--shortstat", onto, tree))
    if dry:
        print("(--dry: 가지는 만들지 않음)")
        return 0
    done = run(sys.executable, "-X", "utf8", f"{W}/mk_merge_branch.py", REPO, tree, "origin/main", msgfile, f"ai/claude/{mno}-{slug}")
    print((done.stdout + done.stderr).strip())
    return done.returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
