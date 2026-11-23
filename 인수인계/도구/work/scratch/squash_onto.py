"""병합 가지 준비 도우미(총괄 전용) — 갈래의 검증된 머리를 '지금 main 끝' 위에 한 덩어리로 얹은 트리를 만든다(`git merge --squash`).
사용:
  py -3.12 -X utf8 C:/work/ai/scratch/squash_onto.py <저장소 폴더> <임시 작업 나무(sq_ 로 시작)> <얹을 곳(main 끝 등)> <갈래 머리> [--union 경로1,경로2,...] [--dry]
하는 일:
  1) 임시 작업 나무를 `<얹을 곳>` 에 detach 로 맞춘다(없으면 만든다). 이 폴더는 AI 가 만든 임시용이라 되돌려도 안전하다(이름이 sq_ 로 시작할 때만 허용).
  2) `git merge --squash --no-commit <갈래 머리>` — 공통 조상(갈래 시작점)과 갈래 머리의 차이를 그 위에 3방향 병합한다.
  3) 충돌한 파일 중 `--union` 에 적은 '덧붙이기 전용 문서'(CHANGELOG·DECISIONS 표 끝 등)는 양쪽 추가분을 모두 남기는 합집합(`git merge-file --union`)으로 푼다. 나머지 충돌은 목록만 보이고 멈춘다(사람이 고침).
  4) 충돌이 없으면 바뀐 파일 수와 새 트리 해시(`TREE <id>`)를 보인다. 이 트리는 `mk_merge_branch.py <저장소> <트리> <얹을 곳> <메시지 파일> <새 가지>` 의 둘째 인자로 쓴다.
  `--dry`: 결과를 본 뒤 임시 작업 나무를 원래대로 되돌린다(예행 연습 — 어느 파일이 겹치는지 미리 보는 용도).
종료 코드: 0 충돌 없음(또는 합집합으로 모두 해결) · 3 사람이 풀 충돌이 남음 · 1 오류."""
import os
import subprocess
import sys
import tempfile

W = "C:/work/ai"


import re as _re
from pathlib import Path as _Path

_AUTHOR = (_Path(__file__).resolve().parent.parent / "commit_as_author.py").read_text(encoding="utf-8")     # 고정 작성자는 commit_as_author.py 의 상수 하나만 쓴다(2026-11-23 MIG1 — 이 사본에 개인 값을 따로 두지 않는다)
_NAME, _MAIL = (_re.search("GIT_AUTHOR_" + _key + '="([^"]+)"', _AUTHOR).group(1) for _key in ("NAME", "EMAIL"))
ENV = dict(os.environ, GIT_AUTHOR_NAME=_NAME, GIT_AUTHOR_EMAIL=_MAIL, GIT_COMMITTER_NAME=_NAME, GIT_COMMITTER_EMAIL=_MAIL)   # 되돌린 병합이 아닌 실제 3방향 병합은 신원이 있어야 돈다(없으면 'unable to auto-detect email address')


def git(wt, *args, check=True, binary=False):
    done = subprocess.run(["git", "-C", wt, *args], capture_output=True, env=ENV)
    if check and done.returncode:
        raise SystemExit(f"git {' '.join(args[:3])} 실패({done.returncode}): {done.stderr.decode('utf-8', 'replace').strip()[:400]}")
    if binary:
        return done
    done.out = done.stdout.decode("utf-8", "replace")
    return done


def main(argv):
    flags = {"--union": "", "--dry": False}
    pos = []
    it = iter(argv)
    for a in it:
        if a == "--union":
            flags["--union"] = next(it)
        elif a == "--dry":
            flags["--dry"] = True
        else:
            pos.append(a)
    if len(pos) != 4:
        print(__doc__)
        return 1
    repo, wt, onto, head = pos
    wt = wt.replace("\\", "/")
    if not (wt.startswith(W + "/sq_") or wt.startswith(W + "/verify/sq_")):
        print("임시 작업 나무 이름은 C:/work/ai/sq_<이름> 이어야 합니다(되돌림 안전장치).")
        return 1
    union = {p.strip() for p in flags["--union"].split(",") if p.strip()}
    onto_sha = git(repo, "rev-parse", onto).out.strip()
    head_sha = git(repo, "rev-parse", head).out.strip()
    if os.path.isdir(wt):
        git(wt, "reset", "--hard", "-q")
        git(wt, "clean", "-fdq")
        git(wt, "checkout", "--detach", "-q", onto_sha)
    else:
        git(repo, "worktree", "add", "--detach", wt, onto_sha)
    base = git(wt, "merge-base", onto_sha, head_sha).out.strip()
    print(f"얹을 곳 {onto_sha[:7]} · 갈래 머리 {head_sha[:7]} · 공통 조상 {base[:7]}")
    done = git(wt, "merge", "--squash", "--no-commit", head_sha, check=False)
    note = (done.out + done.stderr.decode("utf-8", "replace")).strip()
    if done.returncode not in (0, 1) or "up to date" in note.lower():
        print("병합 명령 출력:", note[-300:])
    unmerged =[p for p in git(wt, "diff", "--name-only", "--diff-filter=U").out.splitlines() if p.strip()]
    left = []
    for path in unmerged:
        if path in union:
            blobs = {}
            for stage, label in ((1, "base"), (2, "ours"), (3, "theirs")):
                got = git(wt, "show", f":{stage}:{path}", check=False, binary=True)
                blobs[label] = got.stdout if got.returncode == 0 else b""
            tmpdir = tempfile.mkdtemp(prefix="sq_union_")
            files = {}
            for label, data in blobs.items():
                fp = os.path.join(tmpdir, label)
                with open(fp, "wb") as f:
                    f.write(data)
                files[label] = fp
            merged = subprocess.run(["git", "merge-file", "--union", "-p", files["ours"], files["base"], files["theirs"]], capture_output=True)
            if merged.returncode < 0 or merged.returncode > 127:
                left.append(path)
                continue
            with open(os.path.join(wt, path), "wb") as f:
                f.write(merged.stdout)
            git(wt, "add", "--", path)
            print(f"  합집합으로 풂: {path}")
        else:
            left.append(path)
    if left:
        print("사람이 풀 충돌:", ", ".join(left))
        print("(임시 작업 나무에 충돌 표시가 남아 있다:", wt, ")")
        if flags["--dry"]:
            git(wt, "reset", "--hard", "-q")
        return 3
    stat = git(wt, "diff", "--cached", "--shortstat").out.strip()
    tree = git(wt, "write-tree").out.strip()
    head_tree = git(repo, "rev-parse", f"{head_sha}^{{tree}}").out.strip()
    print("변경 요약:", stat or "(변경 없음)")
    print("TREE", tree)
    print("갈래 머리 트리와 같음" if tree == head_tree else "갈래 머리 트리와 다름(main 이 앞으로 가서 합쳐진 결과 — 영향 시험 재확인 필요)")
    if flags["--dry"]:
        git(wt, "reset", "--hard", "-q")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
