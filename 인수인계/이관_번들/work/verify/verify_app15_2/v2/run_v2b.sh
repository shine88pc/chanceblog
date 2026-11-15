#!/bin/bash
# Round-2 part B: runs after the main pipeline finished. One process at a time.
H=C:/work/ai/verify_app15_2; V=$H/v2
PYS=<사용자폴더>/AppData/Local/Programs/Python/Python312/python.exe
QPY=C:/ccgui/v/Scripts/python.exe
L=$V/logs/v2b.log
export PYTHONDONTWRITEBYTECODE=1
stamp() { echo "$(date +%H:%M:%S) $1" >> $L; }
mem() { python -X utf8 C:/work/ai/audit6/n2/tools/memfree.py "$1" > /dev/null; }
until grep -q "ALL DONE" $V/logs/v2.log 2>/dev/null; do sleep 5; done
IMPL=C:/work/ai/audit6/improve/app15/mut_ap15.py
SUITE=test_ui_sentence_color,test_ui_core,test_ui_cdesign_core,test_ui_c1a_core

stamp "F1 five extra new mutants on dev (alone)"; $PYS -X utf8 $V/mut2.py $V/my_mut_new.py dev N20 N23 N24 N27 FP8 > $V/logs/mut_extra_dev.log 2>&1
stamp "F2 N27 suite variant"; MUT_MODULES=$SUITE $PYS -X utf8 $V/mut2.py $V/my_mut_new.py dev N27 > $V/logs/mut_extra_dev_suite.log 2>&1
stamp "F3 implementer R01-R10 on dev"; $PYS -X utf8 $V/mut2.py $IMPL dev R01 R02 R03 R04 R05 R06 R07 R08 R09 R10 > $V/logs/mut_impl_R_dev.log 2>&1
stamp "F4 implementer R11 R12 under Qt"; $PYS -X utf8 $V/mut2.py $IMPL qt R11 R12 > $V/logs/mut_impl_R_qt.log 2>&1
stamp "G1 baseline probe: can a user reach go() while the home drawer is open"; mem 1.5; PYTHONPATH="" PYTHONUTF8=1 QT_QPA_PLATFORM=offscreen $QPY -B -X utf8 $V/probe_baseline_drawer.py > $V/logs/probe_baseline_drawer.log 2>&1
stamp "G2 effect probes"
for t in final2; do mem 1.5; PYTHONPATH="" PYTHONUTF8=1 QT_QPA_PLATFORM=offscreen $QPY -B -X utf8 $V/probe_effect.py "C:\work\ai\verify_app15_2\final2" > $V/logs/effect_base.log 2>&1; done
for id in N09 N10 N04; do
  $PYS -X utf8 $V/make_eff.py $id $V/eff_$id > $V/logs/make_eff_$id.log 2>&1
  mem 1.5; PYTHONPATH="" PYTHONUTF8=1 QT_QPA_PLATFORM=offscreen $QPY -B -X utf8 $V/probe_effect.py "C:\work\ai\verify_app15_2\v2\eff_$id" > $V/logs/effect_$id.log 2>&1
done
stamp "G3 Qt counts"; for c in $V/tree_start $H/final2; do mem 1.5; QT_QPA_PLATFORM=offscreen $QPY -B -X utf8 C:/work/ai/audit6/improve/app15/count_tests.py $c >> $V/logs/counts_qt.log 2>&1; done
stamp "PART B DONE"
