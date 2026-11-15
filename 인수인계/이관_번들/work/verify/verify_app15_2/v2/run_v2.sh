#!/bin/bash
# Round-2 pipeline: Qt-less first, Qt steps last (each waits for 1.5 GB). One process at a time.
H=C:/work/ai/verify_app15_2; V=$H/v2
PYS=<사용자폴더>/AppData/Local/Programs/Python/Python312/python.exe
RT=C:/work/ai/audit6/improve/l1/runtest.sh
L=$V/logs/v2.log
mkdir -p $V/logs
export PYTHONDONTWRITEBYTECODE=1
stamp() { echo "$(date +%H:%M:%S) $1" >> $L; }
mem() { python -X utf8 C:/work/ai/audit6/n2/tools/memfree.py "$1" > /dev/null; }
OLD=$H/my_mut_ap15.py; NEW=$V/my_mut_new.py
SUITE=test_ui_sentence_color,test_ui_core,test_ui_cdesign_core,test_ui_c1a_core

stamp "A1 baseline new test dev (final2)"; mem 0.7; bash $RT C:/ccgui/dev/Scripts/python.exe $H/final2 test_ui_sentence_color -v > $V/logs/base_dev.log 2>&1
stamp "A2 baseline new test 3.10 (final2)"; mem 0.7; bash $RT C:/ccgui/v310/Scripts/python.exe $H/final2 test_ui_sentence_color -v > $V/logs/base_310.log 2>&1
stamp "A3 counts dev"; for c in $V/tree_start $H/final2; do mem 0.7; C:/ccgui/dev/Scripts/python.exe -B -X utf8 C:/work/ai/audit6/improve/app15/count_tests.py $c >> $V/logs/counts_dev.log 2>&1; done
stamp "A4 counts 3.10"; for c in $V/tree_start $H/final2; do mem 0.7; C:/ccgui/v310/Scripts/python.exe -B -X utf8 C:/work/ai/audit6/improve/app15/count_tests.py $c >> $V/logs/counts_310.log 2>&1; done
stamp "B1 old mutants NM1-13 dev"; $PYS -X utf8 $V/mut2.py $OLD dev all > $V/logs/mut_old_dev.log 2>&1
stamp "B2 new mutants dev"; $PYS -X utf8 $V/mut2.py $NEW dev all > $V/logs/mut_new_dev.log 2>&1
S1=$($PYS -X utf8 $V/survivors.py $OLD dev); S2=$($PYS -X utf8 $V/survivors.py $NEW dev)
stamp "B3 suite variant for survivors: old[$S1] new[$S2]"
[ -n "$S1" ] && MUT_MODULES=$SUITE $PYS -X utf8 $V/mut2.py $OLD dev $S1 > $V/logs/mut_old_dev_suite.log 2>&1
[ -n "$S2" ] && MUT_MODULES=$SUITE $PYS -X utf8 $V/mut2.py $NEW dev $S2 > $V/logs/mut_new_dev_suite.log 2>&1
stamp "STAGE QTLESS-MUT DONE"

stamp "C1 single-item AP15 tree 3.12 dev"; mem 0.7
A15="test_ui_sentence_color test_ui_core test_ui_c1a_core test_ui_c1c_core test_ui_c1d_core test_ui_candidates_core test_ui_drafts_core test_docs_entrance test_repo_layout test_content_style_stats test_service_backup_rules"
bash $RT C:/ccgui/dev/Scripts/python.exe $V/tree_AP15 $A15 > $V/logs/ap15only_dev.log 2>&1; stamp "C1 exit=$?"
stamp "C2 single-item AP15 tree 3.10"; mem 0.7; bash $RT C:/ccgui/v310/Scripts/python.exe $V/tree_AP15 $A15 > $V/logs/ap15only_310.log 2>&1; stamp "C2 exit=$?"
A14="test_security_errorlog test_security_boundary test_security_boundary_matrix test_security_mask_boundary test_source_rules_output test_source_rules_outgoing test_source_rules_key_display test_external_write_gate test_external_write_zero test_single_instance test_ui_launcher test_ui_core test_ui_c1a_core test_ui_c1c_core test_ui_c1d_core test_ui_backup_core test_ui_candidates_core test_ui_drafts_core test_service_backup_rules test_service_backup_flow test_docs_entrance test_repo_layout test_errors_catalog test_packaging_docs test_packaging_entry test_content_style_stats"
stamp "C3 single-item AP14 tree 3.12 dev"; mem 0.7; bash $RT C:/ccgui/dev/Scripts/python.exe $V/tree_AP14 $A14 > $V/logs/ap14only_dev.log 2>&1; stamp "C3 exit=$?"
stamp "C4 single-item AP14 tree 3.10"; mem 0.7; bash $RT C:/ccgui/v310/Scripts/python.exe $V/tree_AP14 $A14 > $V/logs/ap14only_310.log 2>&1; stamp "C4 exit=$?"
stamp "STAGE TREES DONE"

stamp "D1 final2 union of affected modules 3.12 dev"; mem 0.7
UNION="test_ui_sentence_color $A14"
bash $RT C:/ccgui/dev/Scripts/python.exe $H/final2 $UNION > $V/logs/final2_union_dev.log 2>&1; stamp "D1 exit=$?"
stamp "STAGE UNION DONE"

stamp "E1 Qt new test on final2"; mem 1.5; QT_QPA_PLATFORM=offscreen bash $RT C:/ccgui/v/Scripts/python.exe $H/final2 test_ui_sentence_color -v > $V/logs/base_qt.log 2>&1; stamp "E1 exit=$?"
stamp "E2 Qt new test on AP15-only tree"; mem 1.5; QT_QPA_PLATFORM=offscreen bash $RT C:/ccgui/v/Scripts/python.exe $V/tree_AP15 test_ui_sentence_color > $V/logs/ap15only_qt.log 2>&1; stamp "E2 exit=$?"
stamp "E3 Qt red check (start tree + new test)"; cp $H/final2/tests/test_ui_sentence_color.py $V/tree_start/tests/test_ui_sentence_color.py
mem 1.5; QT_QPA_PLATFORM=offscreen bash $RT C:/ccgui/v/Scripts/python.exe $V/tree_start test_ui_sentence_color > $V/logs/red_qt.log 2>&1; stamp "E3 exit=$?"
mem 0.7; bash $RT C:/ccgui/dev/Scripts/python.exe $V/tree_start test_ui_sentence_color > $V/logs/red_dev.log 2>&1; stamp "E3b exit=$?"
stamp "E4 old mutants under Qt"; $PYS -X utf8 $V/mut2.py $OLD qt all > $V/logs/mut_old_qt.log 2>&1
stamp "E5 new mutants under Qt"; $PYS -X utf8 $V/mut2.py $NEW qt all > $V/logs/mut_new_qt.log 2>&1
stamp "ALL DONE"
