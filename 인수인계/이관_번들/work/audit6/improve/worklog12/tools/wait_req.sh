#!/bin/bash
# 요청 가지의 머리가 바뀔 때까지(최대 25분) 45초마다 읽는다 — 새 요청 파일이 올라왔는지 알려 주는 용도(읽기 전용, git ls-remote 만 씀).
BASE="$1"
for i in $(seq 1 33); do
  cur=$(git -C C:/work/ai/wt_r30 ls-remote origin refs/heads/ai/claude/NO-MERGE-operator-requests | cut -c1-7)
  app=$(git -C C:/work/ai/cd_repo ls-remote origin refs/heads/main | cut -c1-7)
  blog=$(git -C C:/work/ai/wt_r30 ls-remote origin refs/heads/main | cut -c1-7)
  if [ "$cur" != "$BASE" ]; then echo "REQUEST HEAD CHANGED: $BASE -> $cur (app main $app, blog main $blog) at $(date +%H:%M:%S)"; exit 0; fi
  sleep 45
done
echo "TIMEOUT no change from $BASE (app main $app, blog main $blog) at $(date +%H:%M:%S)"
