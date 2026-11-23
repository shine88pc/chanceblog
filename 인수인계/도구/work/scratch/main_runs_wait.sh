#!/bin/bash
# 한 저장소의 한 가지(기본 main)에서 '지금 실행 중' 표시가 모두 사라질 때까지 웹 페이지로만(REST 한도 0) 기다린다. 끝나면 한 줄 내고 종료.
# 사용: bash scratch/main_runs_wait.sh [가지=main] [분=15] [저장소=shine88pc/chanceblog]
b="${1:-main}"; max="${2:-15}"; repo="${3:-shine88pc/chanceblog}"
q=$(printf '%s' "$b" | sed 's#/#%2F#g')
end=$(( $(date +%s) + max*60 )); last=""
while [ "$(date +%s)" -lt "$end" ]; do
  page=$(curl -s -m 25 "https://github.com/$repo/actions?query=branch%3A$q")
  n=$(printf '%s' "$page" | grep -o 'currently running' | wc -l)
  if [ "$n" != "$last" ]; then echo "[$(date +%H:%M)] $repo $b: 실행 중 표시 $n"; last="$n"; fi
  if [ "$n" = "0" ] && [ -n "$page" ]; then echo "끝: 실행 중 표시 없음"; exit 0; fi
  sleep 40
done
echo "시간 초과(${max}분)"
