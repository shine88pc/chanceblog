#!/bin/bash
# 사용: runtest.sh <파이썬 경로> <작업 폴더> <모듈 이름들...>   — tests 폴더에서 PYTHONPATH 를 CI 모양으로 주고 한 프로세스로 돌린다
PY="$1"; ROOT="$2"; shift 2
cd "$ROOT/tests" || exit 99
export PYTHONPATH="$(cygpath -w "$ROOT")\src;$(cygpath -w "$ROOT")\tests;$(cygpath -w "$ROOT")"
export PYTHONUTF8=1 PYTHONDONTWRITEBYTECODE=1
"$PY" -B -X utf8 -m unittest "$@" 2>&1
