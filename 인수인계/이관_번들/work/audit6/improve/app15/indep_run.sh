#!/bin/bash
# 독립 병합 사본에서 한 항목의 시험을 돌린다 — 한 번에 한 프로세스, 단계 사이에 memfree.
# 사용: indep_run.sh <AP15|AP14>   (사본은 보고서 폴더 indep_<항목>, 결과는 logs/indep_<항목>_*.log, 진행은 indep_chain.log)
H=C:/work/ai/audit6/improve/app15
ITEM="$1"
W="$H/indep_$ITEM"
COMMON="test_security_boundary test_security_boundary_matrix test_security_mask_boundary test_source_rules_output test_source_rules_outgoing test_source_rules_key_display test_external_write_gate test_external_write_zero test_single_instance test_ui_launcher test_ui_core test_ui_c1a_core test_ui_c1c_core test_ui_c1d_core test_ui_backup_core test_ui_candidates_core test_ui_drafts_core test_service_backup_rules test_service_backup_flow test_docs_entrance test_repo_layout test_errors_catalog test_packaging_docs test_packaging_entry test_content_style_stats"
if [ "$ITEM" = "AP15" ]; then
  MINE="test_ui_sentence_color"
  QT="test_ui_sentence_color test_ui_qt_candidates test_ui_qt_drafts test_ui_qt_drafts_save"
else
  MINE="test_security_errorlog"
  QT="test_security_boundary_qt test_ui_qt test_ui_qt_backup"
fi
MODS="$MINE $COMMON"
mem() { python -X utf8 C:/work/ai/audit6/n2/tools/memfree.py "$1" > /dev/null; }
stamp() { echo "$(date +%H:%M:%S) $ITEM $1" >> $H/indep_chain.log; }
run() {  # run <로그 이름> <파이썬> <모듈…>
  local LOG="$1" PY="$2"; shift 2
  ( cd $W/tests && QT_QPA_PLATFORM=offscreen PYTHONPATH="$W/src;$W/tests;$W;$W/scripts" PYTHONUTF8=1 PYTHONDONTWRITEBYTECODE=1 $PY -B -X utf8 -m unittest "$@" > $H/logs/indep_${ITEM}_${LOG}.log 2>&1 )
  stamp "$LOG 끝(종료 $?) — $(grep -E '^Ran ' $H/logs/indep_${ITEM}_${LOG}.log | tail -1) $(grep -E '^(OK|FAILED)' $H/logs/indep_${ITEM}_${LOG}.log | tail -1)"
}
mem 0.7; stamp "3.12 Qt 없음 영향 모듈 시작"; run aff_312 C:/ccgui/dev/Scripts/python.exe $MODS
mem 0.7; stamp "3.10 새 시험 시작"; run new_310 C:/ccgui/v310/Scripts/python.exe $MINE
mem 0.7; stamp "3.10 영향 모듈 시작"; run aff_310 C:/ccgui/v310/Scripts/python.exe $MODS
for MOD in $QT; do
  mem 1.5; stamp "Qt $MOD 시작"; run qt_$MOD C:/ccgui/v/Scripts/python.exe $MOD
done
stamp "끝"
