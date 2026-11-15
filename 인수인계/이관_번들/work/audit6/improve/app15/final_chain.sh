#!/bin/bash
# APP15 마지막 시험 사슬 — 한 번에 한 프로세스, 단계 사이에 memfree. 단계마다 로그 파일을 남긴다(진행은 chain.log).
# 사용: final_chain.sh <시험할 사본 폴더>   (작업 폴더의 최종 모습을 snapshot.py 로 복사한 사본 — 시험이 도는 동안 작업 폴더를 고칠 수 있게)
# 3.10 영향 모듈은 조각 도우미(--only)를 쓰지 않고 모듈 이름을 직접 넘긴다 — 조각에 해당 모듈이 하나도 없으면 도우미가 인자 없는 unittest 를 불러 전체 시험을 돌리기 때문이다.
H=C:/work/ai/audit6/improve/app15
W="$1"
SKIP=test_pages_publish,test_vendor_core,test_service_repolock,test_service_recovery,test_service_unpushed
MODS="test_ui_sentence_color test_security_errorlog test_security_boundary test_security_boundary_matrix test_security_mask_boundary test_source_rules_output test_source_rules_outgoing test_source_rules_key_display test_external_write_gate test_external_write_zero test_single_instance test_ui_launcher test_ui_core test_ui_c1a_core test_ui_c1c_core test_ui_c1d_core test_ui_backup_core test_ui_candidates_core test_ui_drafts_core test_service_backup_rules test_service_backup_flow test_docs_entrance test_repo_layout test_errors_catalog test_packaging_docs test_packaging_entry test_content_style_stats"
mem() { python -X utf8 C:/work/ai/audit6/n2/tools/memfree.py 0.7 > /dev/null; }
stamp() { echo "$(date +%H:%M:%S) $1" >> $H/chain.log; }

stamp "시작: 3.12 조각 3개(Qt 없음) — 사본 $W"
for n in 1 2 3; do
  mem; stamp "3.12 조각 $n/3 시작"
  python -X utf8 C:/work/ai/run_shard_like.py C:/ccgui/dev/Scripts/python.exe $W $n 3 --skip=$SKIP > $H/logs/full_312_$n.log 2>&1
  stamp "3.12 조각 $n/3 끝(종료 $?)"
done
mem; stamp "3.10 영향 모듈 시작"
( cd $W/tests && PYTHONPATH="$W/src;$W/tests;$W" PYTHONUTF8=1 PYTHONDONTWRITEBYTECODE=1 C:/ccgui/v310/Scripts/python.exe -B -X utf8 -m unittest $MODS > $H/logs/aff_310.log 2>&1 )
stamp "3.10 영향 모듈 끝(종료 $?)"
mem; stamp "3.12 영향 모듈(Qt 없음, 알파벳 순서 한 프로세스) 시작"
( cd $W/tests && PYTHONPATH="$W/src;$W/tests;$W" PYTHONUTF8=1 PYTHONDONTWRITEBYTECODE=1 C:/ccgui/dev/Scripts/python.exe -B -X utf8 -m unittest $MODS > $H/logs/aff_312.log 2>&1 )
stamp "3.12 영향 모듈 끝(종료 $?)"
stamp "사슬 끝(Qt 있는 3.12 모듈은 따로)"
