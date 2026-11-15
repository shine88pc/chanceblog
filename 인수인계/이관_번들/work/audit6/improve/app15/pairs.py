"""정확히 한 곳만 바꾸는 도우미(문서·소스 공용) — 줄 끝(CRLF/LF)을 파일에 맞춰 옛 글이 정확히 한 번 나올 때만 바꾼다. 다른 스크립트가 가져다 쓴다.
`replace_once(root, rel, old, new)` · `insert_after_line(root, rel, anchor_prefix, text)` · `append_text(root, rel, text)` (글은 LF 로 적는다)."""
from pathlib import Path


def _eol(data):
    return b"\r\n" if data.count(b"\r\n") * 2 >= data.count(b"\n") else b"\n"


def _fit(text, eol):
    return text.encode("utf-8").replace(b"\r\n", b"\n").replace(b"\n", eol)


def replace_once(root, rel, old, new):
    path = Path(root) / rel
    data = path.read_bytes()
    eol = _eol(data)
    old_b, new_b = _fit(old, eol), _fit(new, eol)
    count = data.count(old_b)
    if count != 1:
        raise SystemExit(f"{rel}: 옛 글이 {count}번 나온다(정확히 한 번이어야 한다): {old[:70]!r}")
    path.write_bytes(data.replace(old_b, new_b))
    print(f"replace 끝: {rel} {len(data)} → {len(data) - len(old_b) + len(new_b)} 바이트")


def insert_after_line(root, rel, anchor_prefix, text):
    path = Path(root) / rel
    data = path.read_bytes()
    eol = _eol(data)
    anchor = anchor_prefix.encode("utf-8")
    lines = data.split(b"\n")
    hits = [index for index, line in enumerate(lines) if line.startswith(anchor)]
    if len(hits) != 1:
        raise SystemExit(f"{rel}: 앵커로 시작하는 줄이 {len(hits)}개다(정확히 한 줄이어야 한다): {anchor_prefix[:60]!r}")
    insert = _fit(text.rstrip("\n"), eol).split(eol)
    lines[hits[0] + 1:hits[0] + 1] = [line + (b"\r" if eol == b"\r\n" else b"") for line in insert]
    out = b"\n".join(lines)
    path.write_bytes(out)
    print(f"after 끝: {rel} {len(data)} → {len(out)} 바이트")


def append_text(root, rel, text):
    path = Path(root) / rel
    data = path.read_bytes()
    eol = _eol(data)
    if not data.endswith(b"\n"):
        data += eol
    path.write_bytes(data + _fit(text, eol))
    print(f"append 끝: {rel} {len(data)} → {len(data) + len(_fit(text, eol))} 바이트")
