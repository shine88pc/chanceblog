#!/bin/bash
# 사용: run_mods.sh <로그 이름> <파이썬 경로> <작업 폴더> <모듈…>
# 모듈을 하나씩(한 번에 한 프로세스, 시작 전 memfree) 돌리고 모듈마다 한 줄 요약을 남긴다. 자세한 출력은 logs/<로그 이름>_<모듈>.log
LOGNAME="$1"; PY="$2"; ROOT="$3"; shift 3
H=C:/work/ai/audit6/improve/app15
SUMMARY="$H/logs/${LOGNAME}_summary.log"
: > "$SUMMARY"
for MOD in "$@"; do
  python -X utf8 C:/work/ai/audit6/n2/tools/memfree.py 0.8 > /dev/null
  START=$(date +%s)
  QT_QPA_PLATFORM=offscreen bash C:/work/ai/audit6/improve/l1/runtest.sh "$PY" "$ROOT" "$MOD" > "$H/logs/${LOGNAME}_${MOD}.log" 2>&1
  CODE=$?
  END=$(date +%s)
  RAN=$(grep -E '^Ran ' "$H/logs/${LOGNAME}_${MOD}.log" | tail -1)
  RES=$(grep -E '^(OK|FAILED)' "$H/logs/${LOGNAME}_${MOD}.log" | tail -1)
  echo "$MOD exit=$CODE $RAN | $RES | $((END-START))s" >> "$SUMMARY"
done
echo "DONE" >> "$SUMMARY"
