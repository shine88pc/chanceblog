#!/bin/bash
# 병합 가지 M072 작업 폴더에서 문서를 읽는 시험 31개 모듈을 한 번에 하나씩 돌린다(3.12, 외부 접속 0).
OUT=C:/work/ai/audit6/improve/handoff1
WT=C:/work/ai/wt_m072
RUNNER=C:/work/ai/audit6/improve/worklog12/tools/run_doc_tests.sh
rm -f "$OUT/m072_done.flag" "$OUT/m072_default15.log" "$OUT/m072_extra16.log"
cd "$WT" || exit 2
bash "$RUNNER" "$WT" > "$OUT/m072_default15.log" 2>&1
bash "$RUNNER" "$WT" test_pr_ready_workflows test_request_number_notation test_security_settings test_fact_branch_docs test_draft_upload test_edits_core test_manual_run_defaults test_notify_integration test_ops_inbox test_ops_inbox_drafts test_package_docs test_plan_and_watchdog test_profile_ko_ai test_auto_pr_workflow test_github_status test_merged_notice_docs > "$OUT/m072_extra16.log" 2>&1
echo done > "$OUT/m072_done.flag"
