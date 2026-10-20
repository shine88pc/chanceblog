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


def normalize_newlines(text):
    return (text or "").replace("\r\n", "\n").replace("\r", "\n")


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


def read_file(path):
    """(LF 정규화 텍스트, 원래 줄 끝 '\\n' 또는 '\\r\\n')."""
    raw = Path(path).read_bytes().decode("utf-8")
    newline = "\r\n" if "\r\n" in raw else "\n"
    return normalize_newlines(raw), newline


def write_file(path, text, newline="\n"):
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(text.replace("\n", newline).encode("utf-8"))
    os.replace(tmp, path)
