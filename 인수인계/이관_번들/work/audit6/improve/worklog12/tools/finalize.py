"""마감 — 두 문서의 자리표(@@END_HM@@·@@T_REF@@·@@NEWLINES@@·@@TESTS@@)를 실제 값으로 채운다.

사용: python -X utf8 finalize.py <끝 시각 HH:MM> <다시 읽은 시각 HH:MM> <시험 줄(@@TESTS@@ 자리에 넣을 글)>
추가·바뀐 줄 수는 check_new_lines.py 의 출력에서 읽는다(자리표는 줄 수에 영향이 없다).
"""
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from docedit import Doc  # noqa: E402

WT = "C:/work/ai/improve_wt_worklog12"
end_hm, t_ref, tests_line = sys.argv[1], sys.argv[2], sys.argv[3]
hh, mm = end_hm.split(":")
end_kr = "%d시 %02d분" % (int(hh), int(mm))

out = subprocess.run([sys.executable, "-X", "utf8", os.path.dirname(os.path.abspath(__file__)) + "/check_new_lines.py", WT], capture_output=True, encoding="utf-8").stdout
counts = re.findall(r"== (\S+) 추가·바뀐 줄 (\d+)", out)
cmap = {name: int(n) for name, n in counts}
doc_n, wl_n = cmap["인수인계/작업내용.md"], cmap["WORKLOG.md"]
total = doc_n + wl_n

doc = Doc(WT + "/인수인계/작업내용.md")
wl = Doc(WT + "/WORKLOG.md")
# 제목 줄의 '@@END_HM@@ 에 다시 갱신' 은 조사를 붙여 쓴다
doc.replace_once("같은 날 @@END_HM@@ 에 다시 갱신", "같은 날 %s에 다시 갱신" % end_kr, "§0 제목 시각")
doc.text = doc.text.replace("@@END_HM@@", end_kr).replace("@@T_REF@@", t_ref)
wl.replace_once("(11-13 18:56–@@END_HM@@)", "(11-13 18:56–%s)" % end_hm, "WORKLOG 끝 시각")
wl.replace_once("새로 들어간 줄 @@NEWLINES@@개에서", "새로 들어간·바뀐 줄 %d개(작업내용.md %d·WORKLOG.md %d)에서" % (total, doc_n, wl_n), "WORKLOG 줄 수")
wl.replace_once("@@TESTS@@", tests_line, "WORKLOG 시험 줄")
for d in (doc, wl):
    if "@@" in d.text:
        raise SystemExit("FAIL 자리표가 남음: " + d.path)
doc.save()
wl.save()
print("채움:", end_kr, t_ref, "줄 수", total)
