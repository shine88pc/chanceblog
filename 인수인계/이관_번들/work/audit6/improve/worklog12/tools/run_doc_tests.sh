#!/bin/bash
# 문서(작업내용.md·WORKLOG.md)를 읽는 시험 모듈을 한 번에 하나씩 돌린다(시스템 파이썬 3.12, 외부 접속 0).
# 사용: run_doc_tests.sh <작업 폴더> [모듈이름 ...]   (모듈 이름 생략 시 기본 목록 전부)
WT="$1"; shift
PY="${PYTHON:-<사용자폴더>/AppData/Local/Programs/Python/Python312/python.exe}"
if [ "$#" -gt 0 ]; then MODS=("$@"); else
MODS=(test_agent_docs test_chance_credit test_chance_credit_fix test_glossary_docs test_main_image_run test_notice_requests test_ops_inbox_cleanup_docs test_telegram_inbox_docs test_guardrails test_operator_loop_docs test_publish_paths test_run test_site_cleanup test_workflow_names test_validate_repo)
fi
cd "$WT" || exit 2
total=0; bad=0
for m in "${MODS[@]}"; do
  python -X utf8 C:/work/ai/audit6/n2/tools/memfree.py 0.5 > /dev/null
  out=$("$PY" -X utf8 -B -m unittest discover -s tests -p "$m.py" 2>&1)
  rc=$?
  ran=$(echo "$out" | grep -E '^Ran [0-9]+ test' | sed -E 's/Ran ([0-9]+) test.*/\1/')
  tail=$(echo "$out" | tail -1)
  echo "$m | ran=${ran:-?} | rc=$rc | $tail"
  total=$((total + ${ran:-0}))
  if [ "$rc" -ne 0 ]; then bad=$((bad + 1)); echo "$out" | tail -30; fi
done
echo "TOTAL tests=$total failed_modules=$bad"
