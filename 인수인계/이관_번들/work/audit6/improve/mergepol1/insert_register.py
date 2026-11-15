"""docs/DEFECT_REGISTER.md 의 D 표 끝(D-345 행 뒤, 빈 줄과 '## 운영 중 확인할 것' 앞)에 두 줄을 덧붙인다 — 작업 사본의 줄 끝(CRLF)에 맞추고, 앵커가 정확히 한 번 나오지 않으면 실패한다."""
import sys

TARGET = "C:/work/ai/improve_wt_mergepol1/docs/DEFECT_REGISTER.md"
ROWS = "C:/work/ai/audit6/improve/mergepol1/register_rows.txt"

data = open(TARGET, "rb").read()
rows = [line for line in open(ROWS, encoding="utf-8").read().split("\n") if line.strip()]
assert len(rows) == 2 and all(row.startswith("| **D-34") and row.count("|") == 7 for row in rows), "rows shape"
assert b"D-346" not in data and b"D-347" not in data, "already inserted"
anchor = "\r\n\r\n## 운영 중 확인할 것 (관측 체크리스트)".encode("utf-8")
if data.count(anchor) != 1:
    print("FAIL: anchor occurs", data.count(anchor), "times")
    sys.exit(1)
insert = "".join("\r\n" + row for row in rows).encode("utf-8")
open(TARGET, "wb").write(data.replace(anchor, insert + anchor))
print("ok: inserted", len(rows), "rows")
