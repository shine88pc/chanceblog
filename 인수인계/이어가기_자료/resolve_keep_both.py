"""병합 충돌 표시(<<<<<<< ours … ======= … >>>>>>> theirs)를 '양쪽 모두 남김'(ours 다음 theirs)으로 푼다. 줄바꿈 보존.

사용: python -X utf8 resolve_keep_both.py <파일> [...]
"""
import sys
from pathlib import Path

for arg in sys.argv[1:]:
    path = Path(arg)
    with open(path, encoding="utf-8", newline="") as handle:
        raw = handle.read()
    nl = "\r\n" if "\r\n" in raw else "\n"
    lines = raw.replace("\r\n", "\n").split("\n")
    out, state, blocks = [], "normal", 0
    for line in lines:
        if line.startswith("<<<<<<< "):
            state = "ours"
            blocks += 1
        elif line.startswith("=======") and state == "ours":
            state = "theirs"
        elif line.startswith(">>>>>>> ") and state == "theirs":
            state = "normal"
        else:
            out.append(line)
    if state != "normal":
        sys.exit(f"{path}: 충돌 표시가 닫히지 않았다")
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write("\n".join(out).replace("\n", nl))
    print(path.name, "충돌", blocks, "곳을 양쪽 모두 남김으로 풀었다")
