"""이력(history) 파일 읽기/쓰기.

- 읽기: 파일이 없으면 빈 목록. 파일이 있는데 깨져 있으면 StateError (조용히 비우면 중복 방지가 무너진다 → fail closed)
- 쓰기: 같은 디렉터리의 임시 파일에 쓴 뒤 교체(원자적)
"""
import json
import os
from datetime import timedelta, timezone
from pathlib import Path

from pipeline import provenance   # 이력 항목의 출처 표식(provenance) 읽기 — 중립 모듈(표준 라이브러리만)

KST = timezone(timedelta(hours=9))


class StateError(RuntimeError):
    """이력 파일이 존재하지만 읽을 수 없을 때."""


def read_json_list(path):
    path = Path(path)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StateError(f"이력 파일을 읽을 수 없습니다 ({path}): {exc}") from exc
    if not isinstance(data, list):
        raise StateError(f"이력 파일 최상위가 배열이 아닙니다: {path}")
    return data


def write_json_atomic(path, data, keep=None):
    path = Path(path)
    if keep is not None and isinstance(data, list):
        data = data[-keep:]
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def entry_titles(entries, *, for_ai=True):
    """이력 항목에서 비교용 제목/주제 문자열을 모은다(블로그마다 스키마가 달라도 동작). for_ai 는 키워드로만 받는다.
    for_ai=True(기본)는 표식 항목(`provenance` 칸이 있는 항목 — 구조화 Fact 글)을 건너뛴다: 이 목록은 Blogger·Naver 의 재작성 사유(다른 블로그 글과 제목이 비슷함: 비슷한 제목)로 AI 입력이 된다.
    for_ai=False 는 사람이 읽는 곳 전용이다(AI 를 부르는 함수는 쓰지 않는다 — tests/ai_flow_scan.py AF6)."""
    out = []
    for entry in entries:
        if for_ai and provenance.entry_blocks_ai(entry):
            continue
        if isinstance(entry, str):
            out.append(entry)
        elif isinstance(entry, dict):
            for key in ("title", "kr_title", "en_title", "topic"):
                value = entry.get(key)
                if isinstance(value, str) and value.strip():
                    out.append(value.strip())
    return out


def other_blog_titles(root, reg_blogs, current_key, *, for_ai=True):
    """현재 블로그를 제외한 다른 블로그들의 이력 제목(교차 중복 방지용). 기본(for_ai=True)은 표식 항목을 건너뛴다(entry_titles). for_ai 는 키워드로만 받는다."""
    titles = []
    for blog in reg_blogs:
        if blog.get("key") == current_key:
            continue
        path = Path(root) / blog["state"]["history"]
        try:
            titles.extend(entry_titles(read_json_list(path), for_ai=for_ai))
        except StateError:
            continue  # 다른 블로그의 이력 문제로 이 블로그 실행을 막지 않는다
    return titles
