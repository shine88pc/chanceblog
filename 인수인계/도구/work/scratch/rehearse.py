"""병합 예행 연습(총괄 전용, 읽기 전용 성격) — 갈래들의 현재 WIP 머리를 main 끝 위에 차례로 한 덩어리씩 얹어 보며 어느 파일이 겹치는지 미리 본다.
사용: py -3.12 -X utf8 -u C:/work/ai/scratch/rehearse.py <저장소 폴더(아무 작업 나무)> <임시 작업 나무 sq_이름> <가지 모양 예: ai/claude/NO-MERGE-{lane}-wip> <합집합으로 풀 문서 목록(쉼표)> <갈래1,갈래2,...>
결과는 임시 작업 나무와 떠다니는 커밋에만 남고 가지·원격은 건드리지 않는다."""
import os
import subprocess
import sys

W = "C:/work/ai"
repo, tmp, pattern, union, lanes = sys.argv[1:6]
env = dict(os.environ, GIT_AUTHOR_NAME="x", GIT_AUTHOR_EMAIL="x@example.invalid", GIT_COMMITTER_NAME="x", GIT_COMMITTER_EMAIL="x@example.invalid")


def g(*a):
    r = subprocess.run(["git", "-C", repo, *a], capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
    return r.stdout.strip()


onto = g("rev-parse", "origin/main")
print("origin/main", onto[:7], flush=True)
for lane in lanes.split(","):
    head = g("rev-parse", pattern.format(lane=lane))
    print("=== 갈래", lane, head[:7], "onto", onto[:7], flush=True)
    r = subprocess.run([sys.executable, "-X", "utf8", f"{W}/scratch/squash_onto.py", repo, f"{W}/{tmp}", onto, head, "--union", union],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    print(r.stdout.strip())
    if r.stderr.strip():
        print("stderr:", r.stderr.strip()[-400:])
    tree = [line.split()[1] for line in r.stdout.splitlines() if line.startswith("TREE ")]
    if r.returncode != 0 or not tree:
        print("멈춤(종료 코드", r.returncode, ")")
        break
    onto = g("commit-tree", tree[0], "-p", onto, "-m", f"rehearsal {lane}")
print("끝")
