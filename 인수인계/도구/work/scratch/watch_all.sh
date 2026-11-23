#!/bin/bash
# 감시기 하나로 합침(2026-11-23 운영자 지시 — 개인 PC·무료 AI 한도를 앞두고 AI 알림 줄이기): 저장소 main 머리 변화와 운영자 새 이슈를 한 줄씩 알린다.
# '시작'·'수명 만료' 줄은 내지 않는다 — AI 가 그 알림마다 깨어나(대화 전체를 다시 읽는 한 번의 작업) 아무 일도 안 하던 것을 없앤다.
# 사용: Monitor 로 `bash C:/work/ai/scratch/watch_all.sh` (30분 제한 — 끝나면 도구가 한 번 알리고 다시 무장).
bash C:/work/ai/scratch/watch_heads2.sh 2>&1 | grep --line-buffered -v -e "감시 시작" -e "수명 만료" &
py -3.12 -X utf8 -u C:/work/ai/scratch/watch_issues.py 2>&1 | grep --line-buffered -v -e "감시 시작" &
wait
