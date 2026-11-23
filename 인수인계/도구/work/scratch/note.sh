#!/bin/bash
# 사용: bash scratch/note.sh '제목 — 내용'  → 이관_상태.md 맨 끝에 '- **11-17 HH:MM — 제목 — 내용' 한 줄을 실제 시각으로 덧붙인다(따옴표 안 글은 그대로)
printf -- '- **%s %s — %s\n' "$(date +%m-%d)" "$(date +%H:%M)" "$1" >> /c/work/ai/이관_상태.md
