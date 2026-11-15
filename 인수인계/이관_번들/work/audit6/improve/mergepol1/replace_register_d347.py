"""docs/DEFECT_REGISTER.md 의 D-347 행 한 줄만 새 글로 바꾼다 — 줄 끝(CRLF)을 지키고, 옛 행이 정확히 한 줄이 아니면 실패한다."""
import sys

TARGET = "C:/work/ai/improve_wt_mergepol1/docs/DEFECT_REGISTER.md"
NEW = "C:/work/ai/audit6/improve/mergepol1/register_row_d347.txt"

data = open(TARGET, "rb").read()
new_row = open(NEW, encoding="utf-8").read().rstrip("\n")
assert new_row.startswith("| **D-347** |") and new_row.count("|") == 7, "row shape"
start_mark = "| **D-347** |".encode("utf-8")
if data.count(start_mark) != 1:
    print("FAIL: D-347 row occurs", data.count(start_mark), "times")
    sys.exit(1)
start = data.index(start_mark)
end = data.index(b"\r\n", start)
old_row = data[start:end]
assert old_row.count(b"\n") == 0
open(TARGET, "wb").write(data[:start] + new_row.encode("utf-8") + data[end:])
print("ok: replaced D-347 row,", len(old_row), "->", len(new_row.encode("utf-8")), "bytes")
