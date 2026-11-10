"""AI 입력 방벽 — AI 를 부르기 직전에 프롬프트를 훑어 '표식 글'(provenance: facts)의 글자가 들어 있으면 부르지 않는 마지막 방벽.

위치: AI 를 부르는 입구 둘이 맨 앞에서 `assert_clean(prompt)` 를 부른다 — `generator.call_gemini_with_fallback`(생성기·그림자 실행)과 `pipeline.llm.make_gemini_llm` 의 호출 객체
(Blogger·Naver·이슈 수정·대표 사진·주제 확장). 걸리면 `AiInputForbidden` 이 올라오고 모델은 한 번도 부르지 않는다(재시도·모델 폴백 없음). 예외 문구에는 글 내용이 없다.

이 방벽은 **구조 방벽을 대신하지 않는다.** 1차는 구조다: 표식 글을 AI 입력을 만드는 읽기에서 빼고(generator.load_posts·existing_titles, state.entry_titles, ops.op_image),
Fact 실행에는 AI 키를 주지 않으며(2단계), 정적 규칙(tests/ai_flow_scan.py)이 새 호출 지점·읽기 지점을 막는다. 이 방벽은 '값이 든 제목이 그대로 프롬프트에 들어간 사고'를 잡는 2차다.
**못 막는 것**(시험이 '못 막는다'고 단언한다): 제목의 뒤쪽 조각만(앞 24자와 전체 제목이 아닌 나머지) · 값만(`3.5%` 처럼 너무 일반적인 조각) · 의역 · 번역 · 짧은 제목(정규화한 글자
TITLE_MIN_CHARS 미만 — 일반 낱말과 겹쳐 정상 호출을 막는다) · 표식 글의 본문 · 방벽 밖에서 AI 를 부르는 새 길.

무엇을 비교하나(조각): 표식 글(머리말 `provenance` 가 facts 이거나 모르는 값이거나 머리말을 읽을 수 없는 글)의 제목 전체 · 제목 앞 TITLE_PREFIX_CHARS 자 · 설명 앞
DESCRIPTION_PREFIX_CHARS 자, 그리고 이력(history.json)의 표식 항목의 제목·주제 전체와 앞 TITLE_PREFIX_CHARS 자. 비교는 정규화한 글(NFKC → 소문자 접기 → 글자·숫자만)에서 한다 —
공백·대소문자·문장 부호·JSON 따옴표 이스케이프가 달라도 같은 글로 본다.

비용: 표식 글이 없으면 프롬프트를 읽지도 않고 지나간다. 조각은 호출마다 `_posts` 를 다시 읽지 않고 파일별 (수정 시각·크기·inode) 캐시로 모으되, **호출 직전의 목록·수정 시각을 매번 확인**해
바뀐 파일만 다시 읽는다(방금 수정한 파일은 수정 시각 해상도 때문에 다음 호출에서 한 번 더 읽는다). 프롬프트가 아주 크거나 조각이 아주 많으면 색인 검사로 바꾼다.
읽지 못한 글 파일(읽기 오류)은 캐시하지 않아 다음 호출에서 다시 읽고, 읽지 못한 history.json 은 통과시키되 고정 문장 한 줄을 남긴다(docs/AI_FLOW.md 한계 L8·L9).
이 모듈은 파일을 쓰지 않고 네트워크를 쓰지 않으며 표준 라이브러리와 pipeline.provenance 만 쓴다.
"""
import json
import os
import re
import threading
import time
import unicodedata
from pathlib import Path

from pipeline import provenance

TITLE_MIN_CHARS = 12              # 정규화한 제목이 이보다 짧으면 조각으로 쓰지 않는다(일반 낱말과 겹쳐 정상 호출을 막는다) — 방벽의 한계
TITLE_PREFIX_CHARS = 24           # 제목 앞부분 조각의 길이
DESCRIPTION_PREFIX_CHARS = 40     # 설명 앞부분 조각의 길이
DESCRIPTION_MIN_CHARS = 20        # 정규화한 설명이 이보다 짧으면 조각으로 쓰지 않는다
POST_SUFFIXES = (".md", ".markdown", ".mdown", ".mkd", ".html", ".htm")      # 글 파일로 보는 확장자(생성기는 .md 만 읽지만 방벽은 넉넉하게 훑는다)
HEADER_READ_BYTES = 262_144       # 글 파일은 머리말이 있는 앞쪽만 읽는다
MAX_POST_FILES = 100_000          # 이보다 많으면 확인하지 못한 것으로 보고 막는다(알 수 없으면 막는다)
MAX_HISTORY_BYTES = 50_000_000    # history.json 이 이보다 크면 읽지 않는다
RACY_NS = 3_000_000_000           # 파일을 읽은 때와 수정 시각 차이가 이보다 작으면 캐시를 믿지 않고 다음 호출에서 다시 읽는다
BRUTE_FORCE_LIMIT = 200_000_000   # (조각 수 × 프롬프트 글자 수)가 이 이하면 단순 포함 검사, 넘으면 색인 검사
KINDS = ("post-title", "post-title-prefix", "post-description", "history-title")
HISTORY_WARNING = "[방벽] 이력 history.json 을 읽지 못해(깨졌거나 목록이 아니거나 너무 큼) 표식 이력 항목을 확인하지 못했습니다 — 표식 글 파일(_posts)은 따로 확인합니다(docs/AI_FLOW.md 한계 L8)"

CODE_ROOT = Path(__file__).resolve().parent.parent
_DROP = re.compile(r"[\W_]+")
_LOCK = threading.Lock()
_CACHE = {}


class AiInputForbidden(RuntimeError):
    """표식 글의 글자가 AI 입력에 들어 있다(또는 표식 글 목록을 확인하지 못했다). AI 를 부르지 않았다. 예외 문구에 글 내용은 없다."""


def normalize(text):
    """비교용 정규화: NFKC → 소문자 접기 → 글자·숫자만 남긴다(공백·문장 부호·밑줄·따옴표 이스케이프 제거)."""
    return _DROP.sub("", unicodedata.normalize("NFKC", str(text)).casefold())


def _post_fragments(title, description):
    out = []
    flat = normalize(title)
    if len(flat) >= TITLE_MIN_CHARS:
        out.append((flat, "post-title"))
        if len(flat) > TITLE_PREFIX_CHARS:
            out.append((flat[:TITLE_PREFIX_CHARS], "post-title-prefix"))
    flat = normalize(description)
    if len(flat) >= DESCRIPTION_MIN_CHARS:
        out.append((flat[:DESCRIPTION_PREFIX_CHARS], "post-description"))
    return out


def _entry_fragments(entry):
    out = []
    for title in provenance.entry_titles_of(entry):
        flat = normalize(title)
        if len(flat) >= TITLE_MIN_CHARS:
            out.append((flat, "history-title"))
            if len(flat) > TITLE_PREFIX_CHARS:
                out.append((flat[:TITLE_PREFIX_CHARS], "history-title"))
    return out


class _RootCache:
    __slots__ = ("posts", "history", "merged")

    def __init__(self):
        self.posts = {}        # 상대 경로 → (서명, 읽은 시각 ns, 조각 목록)
        self.history = None    # (서명, 읽은 시각 ns, 조각 목록)
        self.merged = {}       # 조각 → 종류


def _trusted(read_ns, sig):
    """캐시한 읽기를 믿어도 되는가: 수정 시각보다 충분히 뒤에 읽었다."""
    return read_ns - sig[0] >= RACY_NS


def _read_post(path):
    """글 파일 하나의 조각 목록(표식 글·알 수 없는 글만). 읽지 못하면(읽기 오류) None — 부른 쪽이 캐시하지 않아 다음 호출에서 다시 읽는다(읽기 오류를 '조각 없음' 으로 굳히지 않는다 — 한계 L9)."""
    try:
        with open(path, "rb") as handle:
            raw = handle.read(HEADER_READ_BYTES)
        text = raw.decode("utf-8", errors="replace")
    except OSError:
        return None
    if not provenance.blocks_ai(text):
        return []
    title, description = provenance.header_fields(text)
    return _post_fragments(title, description)


def _scan_posts(cache, posts_dir):
    """`_posts` 아래 글 파일의 서명을 모아 바뀐 것만 다시 읽는다. 바뀐 것이 있으면 True."""
    found, changed, count = {}, False, 0
    stack = [posts_dir]
    while stack:
        folder = stack.pop()
        try:
            iterator = os.scandir(folder)
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise AiInputForbidden(f"표식 글 목록을 확인하지 못해 AI 를 부르지 않았습니다(폴더를 열 수 없음: {type(exc).__name__})") from None
        with iterator:
            for entry in iterator:
                try:
                    if entry.is_dir(follow_symlinks=False):
                        stack.append(entry.path)
                        continue
                    if not entry.name.lower().endswith(POST_SUFFIXES) or not entry.is_file():
                        continue
                    stat = entry.stat()
                except OSError:
                    continue
                count += 1
                if count > MAX_POST_FILES:
                    raise AiInputForbidden("표식 글 목록이 너무 커서 확인하지 못해 AI 를 부르지 않았습니다")
                found[entry.path] = (stat.st_mtime_ns, stat.st_size, getattr(stat, "st_ino", 0))
    for path in [p for p in cache.posts if p not in found]:
        del cache.posts[path]
        changed = True
    now = time.time_ns()
    for path, sig in found.items():
        old = cache.posts.get(path)
        if old is not None and old[0] == sig and _trusted(old[1], sig):
            continue
        fragments = _read_post(path)
        if fragments is None:
            continue          # 읽지 못했다 — 캐시하지 않는다(다음 호출에서 다시 읽는다). 이 호출에서는 그 글의 조각이 없다(한계 L9). 이전에 읽은 값이 있으면 그대로 둔다
        if old is None or old[2] != fragments or old[0] != sig:
            changed = True
        cache.posts[path] = (sig, now, fragments)
    return changed


def _scan_history(cache, history_file):
    try:
        stat = os.stat(history_file)
    except OSError:
        changed = cache.history is not None and bool(cache.history[2])
        cache.history = None
        return changed
    sig = (stat.st_mtime_ns, stat.st_size, getattr(stat, "st_ino", 0))
    old = cache.history
    if old is not None and old[0] == sig and _trusted(old[1], sig):
        return False
    fragments, readable = [], False
    if stat.st_size <= MAX_HISTORY_BYTES:
        try:
            with open(history_file, "rb") as handle:
                data = json.loads(handle.read().decode("utf-8"))
            if isinstance(data, list):
                readable = True
                for entry in data:
                    if provenance.entry_blocks_ai(entry):
                        fragments.extend(_entry_fragments(entry))
        except (OSError, ValueError, RecursionError, MemoryError):          # 깊게 중첩된 JSON(RecursionError)·너무 큰 JSON 도 읽지 못한 이력이다(한계 L8)
            fragments = []
    if not readable:
        print(HISTORY_WARNING)          # 통과시키되 조용히 지나가지 않는다 — 읽지 못한 이력의 표식 항목은 확인하지 못했다(고정 문장, 파일 내용 없음). 같은 파일은 캐시 덕에 한 번만 알린다(D-199)
    cache.history = (sig, time.time_ns(), fragments)
    return old is None or old[2] != fragments


def _merge(cache):
    merged = {}
    for _sig, _read, fragments in cache.posts.values():
        for fragment, kind in fragments:
            merged.setdefault(fragment, kind)
    if cache.history is not None:
        for fragment, kind in cache.history[2]:
            merged.setdefault(fragment, kind)
    cache.merged = merged


def default_roots():
    """방벽이 훑는 저장소 루트: 지금 작업 폴더와 이 코드가 든 저장소(보통 같다 — 한 번만 센다)."""
    roots, seen = [], set()
    candidates = []
    try:
        candidates.append(Path.cwd())
    except OSError:
        pass
    candidates.append(CODE_ROOT)
    for candidate in candidates:
        key = os.path.normcase(os.path.realpath(candidate))
        if key not in seen:
            seen.add(key)
            roots.append(Path(key))
    return roots


def marked_fragments(roots=None):
    """{조각: 종류} — 지금 표식 글(과 이력 표식 항목)에서 모은 정규화한 조각. 호출 직전의 파일 목록·수정 시각으로 갱신한다."""
    merged = {}
    with _LOCK:
        for root in (roots if roots is not None else default_roots()):
            key = os.path.normcase(os.path.realpath(root))
            cache = _CACHE.get(key)
            if cache is None:
                cache = _CACHE[key] = _RootCache()
            changed = _scan_posts(cache, os.path.join(key, "_posts"))
            changed = _scan_history(cache, os.path.join(key, "history.json")) or changed
            if changed:
                _merge(cache)
            for fragment, kind in cache.merged.items():
                merged.setdefault(fragment, kind)
    return merged


def reset_cache():
    """캐시를 비운다(시험이 쓴다)."""
    with _LOCK:
        _CACHE.clear()


def _indexed_hit(flat, fragments):
    """조각이 아주 많거나 프롬프트가 아주 클 때의 검사: 가장 짧은 조각의 길이 k 로 조각의 앞 k 자를 색인하고 프롬프트를 한 번 훑는다(조각 수와 상관없이 글자 수에 비례)."""
    width = min(len(fragment) for fragment in fragments)
    index = {}
    for fragment, kind in fragments.items():
        index.setdefault(fragment[:width], []).append((fragment, kind))
    for start in range(len(flat) - width + 1):
        bucket = index.get(flat[start:start + width])
        if bucket:
            for fragment, kind in bucket:
                if flat.startswith(fragment, start):
                    return kind
    return None


def find_hit(prompt, fragments):
    """프롬프트(정규화)에 조각이 하나라도 있으면 그 종류, 없으면 None. 단순 포함 검사와 색인 검사는 같은 답을 낸다(시험이 견준다)."""
    if not fragments:
        return None
    if isinstance(prompt, bytes):
        text = prompt.decode("utf-8", errors="replace")
    elif isinstance(prompt, str):
        text = prompt
    else:
        text = str(prompt)
    flat = normalize(text)
    if not flat:
        return None
    if len(fragments) * len(flat) <= BRUTE_FORCE_LIMIT:
        for fragment, kind in fragments.items():
            if fragment in flat:
                return kind
        return None
    return _indexed_hit(flat, fragments)


def assert_clean(prompt, roots=None):
    """AI 를 부르기 직전에 부른다. 표식 글의 글자가 프롬프트에 있으면 AiInputForbidden — 부른 쪽은 AI 를 부르지 않고 그대로 올려야 한다(재시도·폴백 금지)."""
    fragments = marked_fragments(roots)
    if not fragments:
        return
    kind = find_hit(prompt, fragments)
    if kind is not None:
        raise AiInputForbidden("표식 글(구조화 공개 자료로 만든 글)의 제목·설명 글자가 AI 입력에 들어 있어 AI 를 부르지 않았습니다"
                               f"(종류 {kind}). 이 입력을 만드는 코드를 고치세요 — docs/AI_FLOW.md")
