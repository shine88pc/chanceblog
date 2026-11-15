"""WORKLOG.md 의 임시 시험 줄을 실제 시험 결과 글로 바꾼다(정확히 한 곳). 사용: fill_tests.py <새 글>"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from docedit import Doc  # noqa: E402

wl = Doc("C:/work/ai/improve_wt_worklog12/WORKLOG.md")
wl.replace_once("(시험 결과 줄 — 전체 시험이 끝나면 이 자리에 채움)", sys.argv[1], "WORKLOG 시험 줄")
if "@@" in wl.text:
    raise SystemExit("FAIL 자리표 남음")
wl.save()
