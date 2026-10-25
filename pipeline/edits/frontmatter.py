"""Front matter·파일 읽기/쓰기 공통 도구.

파일은 줄 끝(LF/CRLF)을 보존하며 읽고 쓴다. 내부 처리는 항상 LF 로 정규화한 텍스트로 한다
(GitHub 이슈 본문은 CRLF 라서, 사용자가 붙여 넣은 '변경 전' 문구도 같은 방식으로 정규화해야 맞는다).
"""
import os
import re
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

FM_RE = re.compile(r"\A---[ \t]*\n(.*?)\n---[ \t]*(?:\n|\Z)", re.S)


class LineEndingError(ValueError):
    """파일의 줄 끝이 한 가지(LF 또는 CRLF)가 아니라 줄 끝을 보존한 채 고칠 수 없을 때."""


def normalize_newlines(text):
    return (text or "").replace("\r\n", "\n").replace("\r", "\n")


def line_ending_kind(text):
    """줄 끝 유형: 'lf' · 'crlf' · 'cr'(CR 단독) · 'mixed'(둘 이상이 섞임) · 'none'(줄바꿈 없음). 정규화 전 원본에 쓴다."""
    crlf = text.count("\r\n")
    cr = text.count("\r") - crlf
    lf = text.count("\n") - crlf
    kinds = [name for name, count in (("lf", lf), ("crlf", crlf), ("cr", cr)) if count]
    if not kinds:
        return "none"
    return kinds[0] if len(kinds) == 1 else "mixed"


def split_front_matter(text):
    """(front matter 원문 또는 None, 본문). text 는 LF 로 정규화돼 있어야 한다."""
    m = FM_RE.match(text)
    if not m:
        return None, text
    return m.group(1), text[m.end():]


def parse_front_matter(fm_text):
    """front matter 를 dict 로. 없거나 형식이 틀리면 None."""
    if fm_text is None or yaml is None:
        return None
    try:
        data = yaml.safe_load(fm_text)
    except (yaml.YAMLError, ValueError):  # date: 2026-02-30 같은 값은 YAMLError 가 아니라 ValueError 를 낸다
        return None
    if data is None:
        return {}
    return data if isinstance(data, dict) else None


def read_file(path, strict=False):
    """(LF 정규화 텍스트, 원래 줄 끝 '\\n' 또는 '\\r\\n').

    strict 이면 줄 끝이 섞였거나(LF+CRLF) CR 단독인 파일을 LineEndingError 로 거부한다. 그런 파일을 한 가지 줄 끝으로
    다시 쓰면 요청하지 않은 줄 끝 변경이 파일 전체에 생기므로, 수정하는 쪽(runner)은 strict 로 읽는다(fail closed)."""
    raw = Path(path).read_bytes().decode("utf-8")
    kind = line_ending_kind(raw)
    if strict and kind in ("mixed", "cr"):
        raise LineEndingError(kind)
    newline = "\r\n" if "\r\n" in raw else "\n"
    return normalize_newlines(raw), newline


def write_file(path, text, newline="\n"):
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(text.replace("\n", newline).encode("utf-8"))
    os.replace(tmp, path)
