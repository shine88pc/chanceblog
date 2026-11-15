"""문서 고치기 도우미 — 줄 끝(CRLF/LF)을 파일에 맞춰 정확히 한 곳만 바꾼다. 사용:
  python -X utf8 doc_edit.py append <파일> <덧붙일 글 파일>                   파일 끝에 덧붙인다(끝에 줄바꿈이 없으면 먼저 붙인다)
  python -X utf8 doc_edit.py after <파일> <앵커 줄 머리글> <넣을 글 파일>      앵커로 시작하는 줄(정확히 한 줄)의 바로 다음에 넣는다
  python -X utf8 doc_edit.py replace <파일> <옛 글 파일> <새 글 파일>          옛 글이 정확히 한 번 나오는 곳을 바꾼다
글 파일은 UTF-8 이고 줄바꿈은 LF 로 적는다(파일 줄 끝에 맞춰 바꿔 넣는다)."""
import sys
from pathlib import Path


def eol_of(data):
    return b"\r\n" if data.count(b"\r\n") * 2 >= data.count(b"\n") else b"\n"


def text_bytes(path, eol):
    raw = Path(path).read_bytes().replace(b"\r\n", b"\n")
    return raw.replace(b"\n", eol)


def main(argv):
    mode, target = argv[0], Path(argv[1])
    data = target.read_bytes()
    eol = eol_of(data)
    if mode == "append":
        add = text_bytes(argv[2], eol)
        if not data.endswith(b"\n"):
            data += eol
        out = data + add
    elif mode == "after":
        anchor = argv[2].encode("utf-8")
        add = text_bytes(argv[3], eol)
        lines = data.split(b"\n")
        hits = [index for index, line in enumerate(lines) if line.startswith(anchor)]
        if len(hits) != 1:
            raise SystemExit(f"앵커로 시작하는 줄이 {len(hits)}개다(정확히 한 줄이어야 한다): {argv[2][:60]!r}")
        index = hits[0]
        insert = add.rstrip(b"\r\n").split(eol)
        lines[index + 1:index + 1] = [line + (b"\r" if eol == b"\r\n" else b"") for line in insert]
        out = b"\n".join(lines)
    elif mode == "replace":
        old, new = text_bytes(argv[2], eol).rstrip(b"\r\n"), text_bytes(argv[3], eol).rstrip(b"\r\n")
        count = data.count(old)
        if count != 1:
            raise SystemExit(f"옛 글이 {count}번 나온다(정확히 한 번이어야 한다)")
        out = data.replace(old, new)
    else:
        raise SystemExit(__doc__)
    target.write_bytes(out)
    print(f"{mode} 끝: {target.name} {len(data)} → {len(out)} 바이트")


if __name__ == "__main__":
    if len(sys.argv) < 4:
        raise SystemExit(__doc__)
    main(sys.argv[1:])
