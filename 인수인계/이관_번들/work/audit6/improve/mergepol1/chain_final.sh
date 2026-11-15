#!/bin/bash
# 최종 상태 검증을 한 번에 하나씩 차례로 돈다(메모리가 모자라 동시에 돌리지 않는다): 15개 문서 모듈(3.12·3.10) → 소스 훑는 12개 → 문서·대장을 읽는 27개 → 전체 변이.
H=C:/work/ai/audit6/improve/mergepol1
WT=C:/work/ai/improve_wt_mergepol1
RUN=C:/work/ai/audit6/improve/worklog12/tools/run_doc_tests.sh
cd "$WT" || exit 2
bash "$RUN" "$WT" > "$H/final_doc15_312.log" 2>&1
PYTHON=C:/ccgui/v310/Scripts/python.exe bash "$RUN" "$WT" > "$H/final_doc15_310.log" 2>&1
bash "$RUN" "$WT" test_security_settings test_egress test_ai_flow test_fact_structure test_provenance test_shadow_raw test_ai_guard test_fact_thin test_guardrails_precheck test_source_policy test_request_number_notation test_registry > "$H/final_scan12_312.log" 2>&1
MODS=$(sed -n '13,39p' C:/work/ai/verify_mp1_T/extra_312_lf.log | cut -d' ' -f1 | tr '\n' ' ')
bash "$RUN" "$WT" $MODS > "$H/final_readers27_312.log" 2>&1
cd "$H" || exit 2
cp mutation_results.txt mutation_results_partial_backup.txt
python -X utf8 mutate.py > mutation_run6.log 2>&1
echo CHAIN_DONE > "$H/chain_final.flag"
