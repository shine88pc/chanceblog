"""숫자 자리 표시(`[[이름]]`)를 실제 값으로 바꾼다 — 결정 기록·변경 이력 두 파일(CRLF 보존). 사용: python -X utf8 round2_numbers.py <작업 폴더> 이름=값 [이름=값 ...]
쓰인 자리 표시가 모두 값을 받아야 하고(남으면 실패), 받은 값이 어디에도 안 쓰였으면 알려 준다."""
import re
import sys
from pathlib import Path

root = Path(sys.argv[1])
values = dict(item.split("=", 1) for item in sys.argv[2:])
FILES = ["docs/DECISIONS.md", "CHANGELOG.md"]
used = set()
for rel in FILES:
    path = root / rel
    data = path.read_bytes().decode("utf-8")
    for name, value in values.items():
        token = f"[[{name}]]"
        if token in data:
            used.add(name)
            data = data.replace(token, value)
    left = re.findall(r"\[\[[A-Z0-9_]+\]\]", data)
    if left:
        raise SystemExit(f"{rel}: 값을 못 받은 자리 표시가 남았다: {sorted(set(left))}")
    path.write_bytes(data.encode("utf-8"))
    print(f"{rel}: 자리 표시를 바꿨다")
unused = sorted(set(values) - used)
print("쓰이지 않은 값:", unused if unused else "없음")
