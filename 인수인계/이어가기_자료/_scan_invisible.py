"""보이지 않는 글자·BOM·제어 문자를 찾는다(글자 코드는 chr()로만 다룬다).

사용: python -X utf8 _scan_invisible.py <폴더 또는 파일> [...]
"""
import sys
from pathlib import Path

SUSPECT = set(range(0x200B, 0x2010)) | set(range(0x202A, 0x202F)) | set(range(0x2060, 0x2070)) | {0xFEFF, 0x00AD, 0x180E, 0x00A0, 0x3000}
total = 0
for arg in sys.argv[1:]:
    root = Path(arg)
    files = [root] if root.is_file() else sorted(path for path in root.rglob("*") if path.is_file())
    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            print("UTF-8 아님:", path)
            continue
        for number, line in enumerate(text.splitlines(), 1):
            for index, char in enumerate(line):
                code = ord(char)
                if code in SUSPECT or (code < 32 and char not in "\t") or code == 0x7F:
                    total += 1
                    print(f"{path}:{number}:{index + 1} U+{code:04X} …{line[max(0, index - 20):index + 20]!r}")
print("발견:", total)
