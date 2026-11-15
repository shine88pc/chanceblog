"""문서(CRLF) 안의 글을 정확히 한 곳씩 바꾸는 도우미 — 옛 글이 정확히 한 번 나오지 않으면 실패한다(바이트 단위 치환과 같은 효과).

사용: from docedit import Doc  →  doc = Doc(경로); doc.replace_once(옛, 새); doc.insert_after_line(줄 끝 조각, 새 블록); doc.save()
새 글에 들어 있는 줄바꿈은 모두 CRLF 로 바뀐다(작업 폴더 사본은 CRLF — 저장소 안은 autocrlf 가 LF 로 정규화한다).
"""
import sys

CRLF = chr(13) + chr(10)


def crlf(text):
    return text.replace(CRLF, chr(10)).replace(chr(10), CRLF)


class Doc:
    def __init__(self, path):
        self.path = path
        with open(path, "r", encoding="utf-8", newline="") as handle:
            self.text = handle.read()
        self.original = self.text
        self.done = []

    def count(self, fragment):
        return self.text.count(crlf(fragment))

    def replace_once(self, old, new, label=""):
        old, new = crlf(old), crlf(new)
        found = self.text.count(old)
        if found != 1:
            raise SystemExit("FAIL [%s] 옛 글이 %d 번 나옴(1 번이어야 함): %r" % (label, found, old[:120]))
        self.text = self.text.replace(old, new)
        self.done.append(label or old[:40])

    def insert_after_line(self, line_tail, block, label=""):
        """line_tail 로 끝나는 줄(그 줄 끝까지 정확히 일치, 바로 뒤가 줄바꿈)이 정확히 하나여야 하고, 그 줄 바로 뒤에 block 을 줄로 끼워 넣는다."""
        anchor = crlf(line_tail) + CRLF
        found = self.text.count(anchor)
        if found != 1:
            raise SystemExit("FAIL [%s] 줄 끝 조각이 %d 번 나옴(1 번이어야 함): %r" % (label, found, line_tail[-100:]))
        self.text = self.text.replace(anchor, anchor + crlf(block) + CRLF)
        self.done.append(label or line_tail[-40:])

    def region(self, start_marker, end_marker):
        """start_marker 로 시작하는 줄의 처음부터 end_marker 로 시작하는 줄의 처음 직전까지(각각 정확히 하나) 의 (시작, 끝) 위치."""
        start_marker, end_marker = crlf(start_marker), crlf(end_marker)
        if self.text.count(start_marker) != 1 or self.text.count(end_marker) != 1:
            raise SystemExit("FAIL region 표지가 정확히 하나가 아님: %r / %r" % (start_marker[:60], end_marker[:60]))
        start = self.text.index(start_marker)
        end = self.text.index(end_marker)
        if end <= start:
            raise SystemExit("FAIL region 순서가 거꾸로")
        return start, end

    def replace_region(self, start_marker, end_marker, new_text, label=""):
        start, end = self.region(start_marker, end_marker)
        self.text = self.text[:start] + crlf(new_text) + self.text[end:]
        self.done.append(label or start_marker[:40])

    def save(self):
        with open(self.path, "w", encoding="utf-8", newline="") as handle:
            handle.write(self.text)
        print("저장:", self.path, "| 바뀐 단계", len(self.done), "| 바이트", len(self.original.encode("utf-8")), "->", len(self.text.encode("utf-8")))
        for item in self.done:
            print("  -", item)


def read_block(path):
    """블록 파일(UTF-8, LF)을 읽어 끝의 줄바꿈 하나를 뗀 글을 돌려준다."""
    with open(path, "r", encoding="utf-8", newline="") as handle:
        text = handle.read()
    text = text.replace(CRLF, chr(10))
    if text.endswith(chr(10)):
        text = text[:-1]
    return text


if __name__ == "__main__":
    print("이 파일은 도우미 모듈입니다.", file=sys.stderr)
