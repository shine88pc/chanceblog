"""블로그 병합 가지를 만든다(푸시는 하지 않는다): 검증된 갈래 머리를 '지금 origin/main' 위에 한 덩어리로 얹고(`git merge --squash`) WORKLOG.md 맨 위에 새 항목을 끼운 트리 → main 위 한 커밋 가지 `ai/claude/<M번호>-<슬러그>`.
사용: py -3.12 -X utf8 C:/work/ai/scratch/build_blog_merge.py <M번호 예 M084> <슬러그> <갈래 머리(가지 또는 해시)> <WORKLOG 항목 파일> <커밋 메시지 파일> [--union 경로1,경로2,...]
  - 충돌이 나면 `--union` 에 적은 덧붙이기 전용 문서만 합집합으로 풀고, 그 밖의 충돌은 목록만 보이고 멈춘다(임시 작업 나무 C:/work/ai/sq_<M번호> 에 충돌 표시가 남는다).
  - 끝에 보여 주는 것: 새 가지·커밋·트리, `갈래 머리 → 새 커밋` 의 변경 파일(main 이 안 움직였으면 WORKLOG.md 하나뿐이어야 한다), 파일 수 요약.
  - WORKLOG 항목 파일의 `@@STAT@@` 는 'main 대비 변경 N개 파일(+a/−b)' 로 바꿔 쓴다."""
import os
import subprocess
import sys

W = "C:/work/ai"
REPO = f"{W}/wt_r30"
import re as _re
from pathlib import Path as _Path

_AUTHOR = (_Path(__file__).resolve().parent.parent / "commit_as_author.py").read_text(encoding="utf-8")     # 고정 작성자는 commit_as_author.py 의 상수 하나만 쓴다(2026-11-23 MIG1 — 이 사본에 개인 값을 따로 두지 않는다)
_NAME, _MAIL = (_re.search("GIT_AUTHOR_" + _key + '="([^"]+)"', _AUTHOR).group(1) for _key in ("NAME", "EMAIL"))
ENV = dict(os.environ, GIT_AUTHOR_NAME=_NAME, GIT_AUTHOR_EMAIL=_MAIL, GIT_COMMITTER_NAME=_NAME, GIT_COMMITTER_EMAIL=_MAIL)
MARKER = "최신 항목이 위에 오도록 **최신순**으로 작성합니다.".encode("utf-8")


def git(cwd, *args, check=True, binary=False):
    done = subprocess.run(["git", "-C", cwd, *args], capture_output=True, env=ENV)
    if check and done.returncode:
        sys.exit(f"git {' '.join(args[:3])} 실패({done.returncode}): {done.stderr.decode('utf-8', 'replace').strip()[:500]}")
    return done if binary else done.stdout.decode("utf-8", "replace").strip()


def main(argv):
    union = ""
    args = []
    it = iter(argv)
    for a in it:
        if a == "--union":
            union = next(it)
        else:
            args.append(a)
    if len(args) != 5:
        print(__doc__)
        return 2
    mno, slug, lane, entry_file, msg_file = args
    union_set = {p.strip() for p in union.split(",") if p.strip()}
    branch = f"ai/claude/{mno}-{slug}"
    wt = f"{W}/sq_{mno.lower()}"
    git(REPO, "fetch", "origin", "main", "-q")
    base = git(REPO, "rev-parse", "origin/main")
    lane_head = git(REPO, "rev-parse", lane)
    mb = git(REPO, "merge-base", base, lane_head)
    print(f"main={base[:7]} 갈래 머리={lane_head[:7]} 공통 조상={mb[:7]}" + ("  (main 이 앞으로 갔다 — 합쳐진 결과를 영향 시험으로 다시 확인할 것)" if mb != base else ""))
    if os.path.isdir(wt):
        git(REPO, "worktree", "remove", "--force", wt, check=False)
    git(REPO, "worktree", "add", "--detach", wt, base)
    done = git(wt, "merge", "--squash", "--no-commit", lane_head, check=False, binary=True)
    unmerged = [p for p in git(wt, "diff", "--name-only", "--diff-filter=U").splitlines() if p.strip()]
    left = []
    for path in unmerged:
        if path in union_set:
            blobs = {}
            for stage, label in ((1, "base"), (2, "ours"), (3, "theirs")):
                got = git(wt, "show", f":{stage}:{path}", check=False, binary=True)
                blobs[label] = got.stdout if got.returncode == 0 else b""
            tmp = f"{W}/scratch/_union_tmp"
            os.makedirs(tmp, exist_ok=True)
            files = {}
            for label, data in blobs.items():
                fp = f"{tmp}/{label}"
                with open(fp, "wb") as f:
                    f.write(data)
                files[label] = fp
            merged = subprocess.run(["git", "merge-file", "--union", "-p", files["ours"], files["base"], files["theirs"]], capture_output=True)
            if merged.returncode < 0 or merged.returncode > 127:
                left.append(path)
                continue
            with open(f"{wt}/{path}", "wb") as f:
                f.write(merged.stdout)
            git(wt, "add", "--", path)
            print(f"  합집합으로 풂(눈으로 검토할 것): {path}")
        else:
            left.append(path)
    if left:
        print("사람이 풀 충돌:", ", ".join(left), f"— {wt} 에서 직접 해소(그 뒤 git add, 다시 이 도구가 아니라 mk_merge_branch 로)")
        return 3
    # WORKLOG 새 항목 끼우기(줄 끝 모양 유지)
    wl_path = f"{wt}/WORKLOG.md"
    data = open(wl_path, "rb").read()
    entry = open(entry_file, encoding="utf-8").read().strip("\n")
    i = data.find(MARKER)
    if i < 0:
        sys.exit("WORKLOG.md 에서 '최신 항목이 위에 오도록' 줄을 못 찾았다")
    j = data.find(b"---", i)
    k = data.find(b"\n", j) + 1                       # '---' 줄의 끝
    crlf = data[:k].count(b"\r\n") > data[:k].count(b"\n") // 2
    nl = b"\r\n" if crlf else b"\n"
    block = (nl + entry.replace("\r\n", "\n").replace("\n", nl.decode()).encode("utf-8") + nl + nl + b"---" + nl)
    # '---' 줄 바로 뒤에 새 항목(앞에 빈 줄)을 넣고 뒤에 구분선을 붙인다 — 기존 첫 항목은 그 구분선 아래로 밀린다
    new = data[:k] + nl + entry.replace("\r\n", "\n").replace("\n", nl.decode()).encode("utf-8") + nl + nl + b"---" + nl + data[k:]
    open(wl_path, "wb").write(new)
    git(wt, "add", "--", "WORKLOG.md")
    tree = git(wt, "write-tree")
    stat = git(wt, "diff", "--cached", "--shortstat")
    print("main 대비:", stat)
    if os.path.exists(f"{W}/_mk_tmp"):
        pass
    out = subprocess.run([sys.executable, "-X", "utf8", f"{W}/mk_merge_branch.py", REPO, tree, "origin/main", msg_file, branch], capture_output=True, text=True, encoding="utf-8")
    print(out.stdout.strip())
    if out.returncode:
        print(out.stderr.strip()[-500:])
        return 1
    commit = git(REPO, "rev-parse", branch)
    print("갈래 머리 → 새 커밋 변경 파일:", git(REPO, "diff", "--name-only", lane_head, commit).replace("\n", ", ") or "(없음)")
    git(REPO, "worktree", "remove", "--force", wt, check=False)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
