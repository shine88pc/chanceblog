#!/bin/bash
# 병합 가지를 푸시하기 전에 '문서를 읽는 시험'과 CI 모양(PySide6 없음)에서 불러와지는지를 먼저 확인한다(총괄 전용).
# 사용: bash C:/work/ai/scratch/prepush_check.sh <작업 나무> [추가 모듈 …]
#  - 시스템 파이썬 3.12(PySide6 없음 = CI 모양)로 모듈별 시험을 돌린다. 결과 줄은 scratch/_prepush.log.
#  - 문서 표(결정 번호 중복·절 번호·변경 이력)를 읽는 시험 모듈 + 새로 더한 시험 모듈을 함께 본다.
#  - 2026-11-22 교훈: M099 첫 가지가 (1) 이미 병합된 문서 줄의 합집합 중복(D-512 두 번)으로 test_ui_c1c_core·test_ui_c1d_core 가, (2) PySide6 없는 CI 에서 새 Qt 시험 파일 불러오기가 실패해 12칸이 모두 빨개졌다.
TREE="$1"; shift
PY="$(py -3.12 -c 'import sys; print(sys.executable)')"
BASE="test_ui_c1c_core test_ui_c1d_core test_docs_entrance test_errors_catalog test_errors_wording test_l8_docs test_packaging_docs test_repo_layout test_ui_core test_ui_diagnostics_core test_ui_drafts_core test_ui_settings test_ui_sentence_color test_security_scan_docs test_content_photo_text_body test_workflow_artifacts test_single_instance test_security_errorlog test_content_draft_options test_ci_shard"
# 새·바뀐 Qt 시험 모듈은 PySide6 없이 불러오기만 확인(건너뛰어야 한다) — 추가 모듈로 넘긴다
rm -f C:/work/ai/scratch/_prepush.log
py -3.12 -X utf8 C:/work/ai/scratch/run_modules.py "$TREE" "$PY" C:/work/ai/scratch/_prepush.log $BASE "$@"
RC=$?
cat C:/work/ai/scratch/_prepush.log | cut -c1-200
# 결정 번호·변경 이력 중복도 한 번 더
echo "--- 결정 번호 중복:"; grep -oE '^\| D-[0-9]{3} \|' "$TREE/docs/DECISIONS.md" | sort | uniq -d | head -5; echo "(끝)"
exit $RC
