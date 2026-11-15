"""편집 4 — WORKLOG.md 맨 위에 이번 현행화 항목을 더한다(그 밖의 줄은 그대로)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from docedit import Doc, read_block  # noqa: E402

WT = "C:/work/ai/improve_wt_worklog12"
BLK = "C:/work/ai/audit6/improve/worklog12/blocks/"
doc = Doc(WT + "/WORKLOG.md")
anchor = "## [2026-11-12] Claude – DOC: 인수인계/작업내용.md 현행화(11-10 12시 40분 이후 사흘치)"
doc.replace_once(anchor, read_block(BLK + "b30_worklog_entry.txt") + chr(10) + chr(10) + "---" + chr(10) + chr(10) + anchor, "WORKLOG.md 맨 위 항목")
doc.save()
