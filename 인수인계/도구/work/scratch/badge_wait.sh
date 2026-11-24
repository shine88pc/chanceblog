#!/bin/bash
# 사용: bash scratch/badge_wait.sh <가지> [워크플로 파일=guardrails.yml] [분=25] [저장소=shine88pc/chanceblog]
# 공개 REST 한도를 쓰지 않고 상태 배지로 한 가지의 검사 결과를 기다린다(워크플로 파일은 main 에 있어야 한다). 바뀔 때마다 한 줄, passing·failing·cancelled 이면 끝낸다.
b="$1"; wf="${2:-guardrails.yml}"; max="${3:-25}"; repo="${4:-shine88pc/chanceblog}"
end=$(( $(date +%s) + max*60 )); last=""
while [ "$(date +%s)" -lt "$end" ]; do
  s=$(curl -s -m 20 "https://github.com/$repo/actions/workflows/$wf/badge.svg?branch=$b" | grep -o -m1 'passing\|failing\|no status\|pending\|cancelled' | head -1)
  s=${s:-읽지못함}
  if [ "$s" != "$last" ]; then echo "[$(date +%H:%M)] $b $wf: $s"; last="$s"; fi
  case "$s" in passing|failing|cancelled) echo "끝: $s"; exit 0;; esac
  sleep 45
done
echo "시간 초과(${max}분)"
