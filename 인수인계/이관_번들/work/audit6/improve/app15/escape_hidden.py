"""소스 파일 속의 숨은 글자(방향 바꿈·폭 없는 공백·줄 나눔 U+2028/U+2029 같은 서식·제어 글자)를 `\\uXXXX` 글자 그대로의 이스케이프로 바꾼다 — 소스에 보이지 않는 글자가 직접 들어가지 않게.
사용: python -X utf8 escape_hidden.py <파일> [<파일> ...]   (CRLF 보존. 바꾼 글자 수를 적고, 바꾼 뒤 다시 검사해 남은 것이 없는지 확인한다)"""
import sys
import unicodedata
from pathlib import Path

BACKSLASH = chr(92)
TARGET = ("Cf", "Zl", "Zp", "Cc")


def hidden(ch):
    return unicodedata.category(ch) in TARGET and ch not in "\t\r\n"


for name in sys.argv[1:]:
    path = Path(name)
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    count = sum(1 for ch in text if hidden(ch))
    fixed = "".join(f"{BACKSLASH}u{ord(ch):04x}" if hidden(ch) else ch for ch in text)
    path.write_bytes(fixed.encode("utf-8"))
    left = sum(1 for ch in path.read_bytes().decode("utf-8") if hidden(ch))
    print(f"{path.name}: 숨은 글자 {count}개를 이스케이프로 바꿈, 남은 것 {left}개")
