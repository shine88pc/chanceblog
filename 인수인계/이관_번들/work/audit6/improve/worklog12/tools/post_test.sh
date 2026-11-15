#!/bin/bash
# 전체 시험이 끝난 뒤 이어서 돌리는 사슬(한 번에 한 프로세스, 순서대로): 편집 9 → 문서를 읽는 15개 모듈(3.12) → validate_repo → 사실 점검 → 새 줄 점검 → 3.10 모듈 11개 → 변이 시험 26개.
# 결과는 post_test.log 에 쌓는다. 사용: post_test.sh   (full_312.status 에 rc= 가 보이면 시작하는 것은 호출하는 쪽 몫)
R=C:/work/ai/audit6/improve/worklog12
WT=C:/work/ai/improve_wt_worklog12
LOG=$R/post_test.log
PY312="<사용자폴더>/AppData/Local/Programs/Python/Python312/python.exe"
: > "$LOG"
say() { echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOG"; }

# 0. M067 병합완료 확인(R-321 이후)이 요청 가지에 올라왔는지 읽는다
git -C C:/work/ai/wt_r30 fetch -q origin ai/claude/NO-MERGE-operator-requests 2>/dev/null
CONF="병합완료 확인과 앱 main 검사 결과는 이 문서를 고친 시점에 아직 없습니다."
for f in $(git -C C:/work/ai/wt_r30 -c core.quotepath=false ls-tree --name-only origin/ai/claude/NO-MERGE-operator-requests "인수인계/요청함/" | grep -E 'R-32[1-9]'); do
  body=$(git -C C:/work/ai/wt_r30 -c core.quotepath=false show "origin/ai/claude/NO-MERGE-operator-requests:$f")
  if echo "$body" | grep -q "^kind: merged" && echo "$body" | grep -q "^no: M067"; then
    hhmm=$(git -C C:/work/ai/wt_r30 -c core.quotepath=false log origin/ai/claude/NO-MERGE-operator-requests --diff-filter=A --format=%cd --date=format:%H:%M -1 -- "$f")
    num=$(echo "$f" | sed -E 's#.*/(R-[0-9]+)_.*#\1#')
    res=$(echo "$body" | grep -m1 "^result:" | sed 's/result: *//')
    CONF="병합완료 확인 '$res' $num($hhmm)이 갔습니다."
  fi
done
say "M067 확인 문구: $CONF"

# 1. 편집 9
say "편집 9 시작"
M067CONFIRM="$CONF" python -X utf8 $R/tools/edit9.py >> "$LOG" 2>&1 || { say "편집 9 실패"; exit 1; }

# 2. 문서를 읽는 15개 모듈(3.12)
say "15개 모듈(3.12)"
bash $R/tools/run_doc_tests.sh $WT >> "$LOG" 2>&1

# 3. validate_repo
say "validate_repo"
( cd $WT && "$PY312" -X utf8 -B scripts/validate_repo.py 2>&1 | tail -2 ) >> "$LOG" 2>&1

# 4. 사실 점검·새 줄 점검
say "verify_worklog12"
python -X utf8 $R/tools/verify_worklog12.py --root $WT --freeze $R/freeze.json --quiet >> "$LOG" 2>&1
say "verify rc=$?"
python -X utf8 $R/tools/check_new_lines.py $WT >> "$LOG" 2>&1
say "check rc=$?"

# 5. 3.10 모듈 11개
say "11개 모듈(3.10)"
PYTHON=C:/ccgui/v310/Scripts/python.exe bash $R/tools/run_doc_tests.sh $WT test_agent_docs test_chance_credit test_chance_credit_fix test_glossary_docs test_main_image_run test_notice_requests test_ops_inbox_cleanup_docs test_telegram_inbox_docs test_operator_loop_docs test_site_cleanup test_workflow_names >> "$LOG" 2>&1

# 6. 변이 시험
say "변이 시험 시작"
python -X utf8 $R/tools/mut_run.py >> "$LOG" 2>&1
say "변이 시험 rc=$?"
say "사슬 끝"
echo done > $R/post_test.status
