"""문서(CRLF)의 글을 정확히 한 곳씩 바꾸는 도우미 - 옛 글이 정확히 한 번 나오지 않으면 그 파일은 하나도 저장하지 않고 멈춘다.

사용: python -X utf8 apply_edits.py <작업 폴더> <지시 파일> [--dry]
지시 파일(UTF-8, 줄 끝은 LF) 형식:
  @@FILE <작업 폴더 안의 상대 경로>             한 파일의 지시를 시작한다
  @@OP replace <이름>                            다음 줄들 = 옛 글(파일 안에 정확히 한 번), @@SEP 줄 뒤 = 새 글
  @@OP insert_after_line_starting <이름>        옛 글 자리에 '줄의 앞부분' 한 줄(그렇게 시작하는 줄이 정확히 하나), @@SEP 뒤 = 그 줄 바로 뒤에 끼울 줄들
  @@OP insert_before_line_starting <이름>       같은 방식(그 줄 바로 앞에 끼움)
  새 글 안의 한 줄이 '@include <경로>' 이면 그 파일의 글(끝 줄바꿈 하나 뗌)로 바뀐다.
끼워 넣기는 첫 비어 있지 않은 줄이 이미 파일에 있으면 멈춘다(두 번 적용 방지).
새 글의 줄바꿈은 모두 CRLF 로 바뀐다(작업 폴더 사본은 CRLF - 저장소 안은 autocrlf 가 LF 로 정규화한다).
"""
import os
import sys

CRLF = chr(13) + chr(10)
LF = chr(10)


def crlf(text):
    return text.replace(CRLF, LF).replace(LF, CRLF)


def read_text(path):
    with open(path, "r", encoding="utf-8", newline="") as handle:
        return handle.read()


def parse(path):
    raw = read_text(path).replace(CRLF, LF)
    files = []
    current_file = None
    op = None
    part = None
    all_lines = raw.split(LF)
    if all_lines and all_lines[-1] == "":
        all_lines.pop()                      # 파일 끝 줄바꿈이 만드는 빈 조각은 새 글의 일부가 아니다
    for line in all_lines:
        if line.startswith("@@FILE "):
            current_file = {"path": line[len("@@FILE "):].strip(), "ops": []}
            files.append(current_file)
            op = None
        elif line.startswith("@@OP "):
            fields = line[len("@@OP "):].split(" ", 1)
            op = {"kind": fields[0], "label": fields[1] if len(fields) > 1 else "", "old": [], "new": [], "sep": False}
            current_file["ops"].append(op)
            part = "old"
        elif line.startswith("@@SEP"):
            part = "new"
            op["sep"] = True
        elif op is not None:
            op[part].append(line)
    return files


def expand(lines, base):
    out = []
    for line in lines:
        if line.startswith("@include "):
            target = line[len("@include "):].strip()
            if not os.path.isabs(target):
                target = os.path.join(base, target)
            text = read_text(target).replace(CRLF, LF)
            if text.endswith(LF):
                text = text[:-1]
            out.append(text)
        else:
            out.append(line)
    return LF.join(out)


def line_start_positions(text, prefix):
    needle = crlf(prefix)
    found = []
    start = 0
    while True:
        idx = text.find(needle, start)
        if idx < 0:
            break
        if idx == 0 or text[idx - 2:idx] == CRLF:
            found.append(idx)
        start = idx + 1
    return found


def apply_file(root, spec, base, dry):
    path = os.path.join(root, spec["path"])
    text = read_text(path)
    original = text
    notes = []
    for op in spec["ops"]:
        label = op["label"]
        if not op["sep"]:
            raise SystemExit("FAIL [%s] @@SEP 줄이 없음" % label)
        old = expand(op["old"], base)
        new = expand(op["new"], base)
        if op["kind"] == "replace":
            needle, repl = crlf(old), crlf(new)
            count = text.count(needle)
            if count != 1:
                raise SystemExit("FAIL [%s] %s: 옛 글이 %d 번 나옴(1 번이어야 함): %r" % (spec["path"], label, count, old[:100]))
            text = text.replace(needle, repl)
        elif op["kind"] in ("insert_after_line_starting", "insert_before_line_starting"):
            positions = line_start_positions(text, old)
            if len(positions) != 1:
                raise SystemExit("FAIL [%s] %s: 그렇게 시작하는 줄이 %d 개(1 개여야 함): %r" % (spec["path"], label, len(positions), old[:100]))
            first = next((ln for ln in new.split(LF) if ln.strip()), "")
            if first and crlf(first) in text:
                raise SystemExit("FAIL [%s] %s: 끼울 글의 첫 줄이 이미 파일에 있음(두 번 적용?): %r" % (spec["path"], label, first[:80]))
            idx = positions[0]
            block = crlf(new) + CRLF
            if op["kind"] == "insert_after_line_starting":
                end = text.index(CRLF, idx) + 2
                text = text[:end] + block + text[end:]
            else:
                text = text[:idx] + block + text[idx:]
        else:
            raise SystemExit("FAIL [%s] 모르는 종류: %s" % (spec["path"], op["kind"]))
        notes.append(label)
    if not dry:
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
    print("%s %s | 단계 %d | 바이트 %d -> %d" % ("(시험)" if dry else "저장", spec["path"], len(notes), len(original.encode("utf-8")), len(text.encode("utf-8"))))
    for note in notes:
        print("   -", note)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry = "--dry" in sys.argv
    if len(args) != 2:
        raise SystemExit("사용: apply_edits.py <작업 폴더> <지시 파일> [--dry]")
    root, instructions = args
    base = os.path.dirname(os.path.abspath(instructions))
    base = os.path.dirname(base) if os.path.basename(base) == "edits" else base
    for spec in parse(instructions):
        apply_file(root, spec, base, dry)


if __name__ == "__main__":
    main()
