"""출처 표식(provenance) — 구조화 Fact 글을 'AI 입력'에서 빼려고 글과 이력에 다는 표식을 읽고 쓰는 **한 군데**.

왜 있나: Fact 글의 제목에는 공개 자료의 값이 들어 있을 수 있다(예: 실업률 수치). 기존 코드는 `_posts` 의 제목·태그·분류를 AI 입력으로 보내는 자리가 여럿이다(새 글의 '최근 제목',
기존 글 이미지 교체의 검색어, Blogger·Naver 재작성 사유의 다른 블로그 제목, 이슈 수정의 이미지 검색어). 그래서 Fact 글에는 표식을 달고, AI 입력을 만드는 읽기는 표식 글을 건너뛴다.
이 세 곳(통계청·영국 정부·NOAA) 자료에는 AI 서술·번역·요약·다듬기·이미지 설명 단계를 두지 않는다(docs/AI_FLOW.md).

표식의 모양
- 글 파일: 머리말의 한 줄 `provenance: "facts"`(정본). 키는 `provenance`, 값은 정확히 `facts`.
- 이력(history.json) 항목: `"provenance": "facts"`.
표식은 생성기만 쓴다(`with_marker`·`entry_with_marker` — 시험이 다른 곳의 호출을 막는다). 모델이 쓴 머리말의 표식은 지운다(generator._front_matter_from_model).

읽는 규칙 — **알 수 없으면 막는다**(fail closed)
- 닫힌 머리말이 있고 표식 키가 없다 → `none`(AI 입력으로 쓸 수 있다).
- 머리말 자체가 없다 → `no-front-matter`(표식이 있을 수 없다. 오늘의 동작 그대로).
- 표식 키가 있고 값이 정확히 `facts` → `facts`. 키가 있는데 값이 다르거나 키가 둘 이상이다 → `other-value`(모르는 값 — 막는다).
- 머리말이 시작됐는데 닫히지 않았다·울타리가 정확히 `---` 가 아니다·`...` 줄이 있다·YAML 이 줄바꿈으로 읽는 글자(줄 안 CR 포함)나 제어 문자가 있다·한 줄 묶음(`{…}`) 머리말이다·
  0열 줄이 `키: 값`(평문 키·이스케이프 없는 따옴표 키)이나 `- ` 항목이 아니다(복합 키 `?`·앵커·태그·별칭·병합 키 `<<`·줄 머리 BOM 따위)·읽을 수 없는 파일이다 → `unknown`(막는다).
키는 대소문자·앞 공백·따옴표·`- ` 목록 표지와 상관없이 찾는다.

한계: 우리가 정확히 읽는 좁은 문법(허용 목록)만 '읽을 수 있음' 으로 보고 나머지는 막는다. 생성기가 쓰는 정본·흔한 서식 차이·독립 검증이 찾은 YAML 모양(위 목록)은 막고, 무작위 머리말을 PyYAML 의 답과 견주는 차분 시험에서
빠져나감 0 을 확인했다. 그러나 **YAML 이 읽는 모든 모양을 막는다고 증명한 것은 아니다**(사이트 빌더의 파서는 PyYAML 과 다를 수 있다). YAML 로는 표식이 아닌데 막는 경우(과차단)는 안전한 쪽이다.

이 모듈은 표준 라이브러리 중 `re`·`json` 만 쓰고 pipeline 의 다른 모듈을 가져오지 않는다(AI 쪽 모듈과 Fact 쪽 모듈 어디에도 속하지 않는 중립 모듈).
"""
import json
import re

KEY = "provenance"
FACTS = "facts"
CANONICAL_LINE = f'{KEY}: "{FACTS}"'

MARK_NONE = "none"                       # 닫힌 머리말이 있고 표식 키가 없다
MARK_NO_FRONT_MATTER = "no-front-matter"  # 머리말이 없다 — 표식이 있을 수 없다
MARK_FACTS = "facts"                     # 정본 표식
MARK_OTHER = "other-value"               # 표식 키는 있으나 값이 facts 가 아니거나 키가 여럿이다
MARK_UNKNOWN = "unknown"                 # 머리말을 끝까지·안전하게 읽지 못했다
# AI 입력에서 빼는 표식 — '표식 글' 과 '표식 여부를 알 수 없는 글' 모두
BLOCKING_MARKS = frozenset({MARK_FACTS, MARK_OTHER, MARK_UNKNOWN})

ENTRY_TITLE_KEYS = ("topic", "kr_title", "en_title", "title")     # 이력 항목에서 제목으로 읽는 칸(generator.existing_titles·state.entry_titles 와 같다)

HEADER_SCAN_LIMIT = 200_000       # 머리말을 찾으려고 읽는 글자 수 상한 — 이 안에 닫는 줄이 없으면 알 수 없는 글이다
_FENCE = re.compile(r"-{3,}[ \t\r\f\v]*")      # 사이트 빌더(Jekyll)는 여는·닫는 `---` 줄 뒤의 공백을 [ \t\r\n\f\v]* 로 본다 — CR 뒤에 공백이 오는 `---\r ` 도 울타리로 알아본다(독립 검증 2차 N1). 정확한 `---` 줄이 아니면 _strict_unknown 이 알 수 없음으로 막는다
_YAML_BREAKS = re.compile("[\x85\u2028\u2029]")      # YAML 이 줄바꿈으로 읽는 글자 — 한 줄 안에 숨은 둘째 줄을 만들 수 있다
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_TRAILING_COMMENT = re.compile(r"[ \t]#.*$")
_FENCE_EXACT = re.compile(r"---[ \t]*")      # 정확히 `---` 한 줄. 사이트 빌더(Jekyll)는 대시가 더 긴 줄을 울타리로 보지 않는다 — 머리말의 범위가 우리와 어긋나면 안 된다
_KEYLINE = re.compile(r"(?:[A-Za-z_][A-Za-z0-9_-]*|\"[A-Za-z_][A-Za-z0-9_-]*\"|'[A-Za-z_][A-Za-z0-9_-]*')[ \t]*:(?:[ \t]|\Z)")      # 0열에서 시작하는 머리말 줄의 허용 모양: 평문 키 또는 이스케이프 없는 따옴표 키 + 콜론 (_key_value 가 YAML 과 같게 읽는 모양)
_ITEMLINE = re.compile(r"-[ \t]")      # 0열의 `- ` 줄은 목록 항목이라 최상위 키가 될 수 없다


def _split_header(text):
    """(상태, 머리말 줄 목록). 상태: 'none'(머리말 없음) · 'ok'(닫힌 머리말) · 'open'(열렸는데 닫는 줄이 없다). 첫 줄 앞의 BOM·빈 줄은 눈감아 준다(찾기를 넉넉하게 — 막는 쪽으로 틀린다)."""
    if not isinstance(text, str):
        return "open", []
    lines = text[:HEADER_SCAN_LIMIT].lstrip("\ufeff").split("\n")
    first = 0
    while first < len(lines) and not lines[first].strip(" \t\r\x0b\x0c"):
        first += 1
    if first >= len(lines) or not _FENCE.fullmatch(lines[first].rstrip("\r")):
        return "none", []
    for index in range(first + 1, len(lines)):
        if _FENCE.fullmatch(lines[index].rstrip("\r")):
            return "ok", [line.rstrip("\r") for line in lines[first + 1:index]]
    return "open", [line.rstrip("\r") for line in lines[first + 1:]]


def _key_value(line):
    """머리말 한 줄의 (소문자 키, 값 글자). 키 줄이 아니면 None. 앞 공백·`- `·`? ` 표지·따옴표 친 키를 모두 풀어서 읽는다."""
    stripped = line.lstrip(" \t")
    while stripped[:2] in ("- ", "-\t"):
        stripped = stripped[2:].lstrip(" \t")
    if stripped[:2] in ("? ", "?\t"):
        stripped = stripped[2:].lstrip(" \t")
    if not stripped or stripped[0] in "#{[]}":
        return None
    if stripped[0] in "\"'":
        end = stripped.find(stripped[0], 1)
        if end < 0:
            return None
        key, rest = stripped[1:end], stripped[end + 1:].lstrip(" \t")
        return (key.strip().lower(), rest[1:]) if rest.startswith(":") else None
    colon = stripped.find(":")
    if colon < 0:
        return None
    return stripped[:colon].strip().lower(), stripped[colon + 1:]


def _unquote(value):
    """값 글자를 따옴표·뒤 주석을 벗겨 읽는다(JSON 큰따옴표 문자열이면 JSON 으로)."""
    text = value.strip()
    if text[:1] == '"':
        try:
            parsed = json.loads(text)
            if isinstance(parsed, str):
                return parsed
        except ValueError:
            pass
    text = _TRAILING_COMMENT.sub("", text).strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        text = text[1:-1]
    return text


def _strict_unknown(text, lines):
    """머리말이 '단순한 한 줄 한 키' 문법이 아니어서 우리가 안전하게 읽을 수 없는가(True 면 알 수 없음 = 차단). 허용 목록 방식이다 — YAML 이 표식 키로 읽을 수 있는 서식(복합 키 `?`·앵커 `&`·태그 `!`·별칭 `*`·병합 키 `<<`·
    이스케이프를 쓴 따옴표 키·줄 머리 BOM 따위)을 하나씩 막으려 하지 않고, 우리가 정확히 읽는 모양만 통과시킨다. 통과 조건:
    ① 여는·닫는 울타리가 정확히 `---`(뒤 공백·탭만 허용) ② 정확히 `...` 인 줄이 없음(Jekyll 은 거기서 머리말을 닫는다) ③ 첫 내용 줄이 들여쓰기가 아님
    ④ 0열에서 시작하는 내용 줄은 `키: 값`(평문 키 또는 이스케이프 없는 따옴표 키) 이거나 `- ` 목록 항목이다. 들여쓴 줄은 값의 이어짐으로 본다."""
    raw = text[:HEADER_SCAN_LIMIT].lstrip(chr(0xFEFF)).split("\n")          # _split_header 와 같은 방식으로 머리말 앞쪽을 자른다(글 앞 BOM 은 눈감아 준다)
    first = 0
    while first < len(raw) and not raw[first].strip(" \t\r\x0b\x0c"):
        first += 1
    close = first + 1 + len(lines)          # _split_header 가 돌려준 머리말 줄 목록 바로 뒤의 줄 = 닫는 울타리
    if first >= len(raw) or close >= len(raw):
        return True
    if not _FENCE_EXACT.fullmatch(raw[first].rstrip("\r")) or not _FENCE_EXACT.fullmatch(raw[close].rstrip("\r")):
        return True
    seen = False
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if line.startswith("...") and stripped == "...":
            return True
        if line[0] in " \t":
            if not seen:
                return True
            continue
        seen = True
        if not _KEYLINE.match(line) and not _ITEMLINE.match(line):
            return True
    return False


def mark_of_text(text):
    """글 한 편(머리말 + 본문, 줄 끝은 LF·CRLF 모두)의 표식 상태 — MARK_* 중 하나."""
    status, lines = _split_header(text)
    if status == "none":
        return MARK_NO_FRONT_MATTER
    if status == "open":
        return MARK_UNKNOWN
    joined = "\n".join(lines)
    if _YAML_BREAKS.search(joined) or _CONTROL.search(joined) or "\r" in joined:      # 줄 끝 CR 은 _split_header 가 이미 벗겼다 — 남은 CR 은 줄 안 CR(YAML 은 줄바꿈으로 읽는다)
        return MARK_UNKNOWN
    if _strict_unknown(text, lines):
        return MARK_UNKNOWN
    values, first_content = [], True
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if first_content and stripped[0] == "{":      # 한 줄 묶음(flow mapping) 머리말 — 우리 쪽에서 안전하게 읽을 수 없다
            return MARK_UNKNOWN
        first_content = False
        pair = _key_value(line)
        if pair is not None and pair[0] == KEY:
            values.append(_unquote(pair[1]))
        elif pair is None and stripped[0] in "{[" and re.search(KEY, stripped, re.I):     # 한 줄 묶음 안의 표식 낱말 — 읽을 수 없으니 막는다
            return MARK_UNKNOWN
    if not values:
        return MARK_NONE
    return MARK_FACTS if values == [FACTS] else MARK_OTHER


def mark_blocks_ai(mark):
    """표식 상태가 AI 입력에서 빼야 하는 것인가(표식 글·모르는 값·알 수 없음)."""
    return mark in BLOCKING_MARKS


def blocks_ai(text):
    """글 한 편의 텍스트가 AI 입력에서 빠져야 하는가."""
    return mark_blocks_ai(mark_of_text(text))


def mark_of_file(path):
    """글 파일의 표식 상태. 파일을 못 읽거나 UTF-8 이 아니면 MARK_UNKNOWN(알 수 없으면 막는다)."""
    try:
        with open(path, "rb") as handle:
            raw = handle.read(HEADER_SCAN_LIMIT * 4 + 8)
        return mark_of_text(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError):
        return MARK_UNKNOWN


def post_blocks_ai(post):
    """generator.load_posts 가 만든 글 사전 하나가 AI 입력에서 빠져야 하는가. `provenance` 칸이 있으면 그것을, 없으면 `text` 에서 읽는다(둘 다 없는 시험용 가짜 글은 표식 없음)."""
    if not isinstance(post, dict):
        return False
    mark = post.get("provenance")
    if mark is None:
        mark = mark_of_text(post.get("text") or "")
    return mark_blocks_ai(mark)


def entry_mark(entry):
    """이력(history.json) 항목 하나의 표식 상태. 사전이 아니면(문자열 항목) 표식이 없다. 키는 대소문자·앞뒤 공백과 상관없이 찾는다."""
    if not isinstance(entry, dict):
        return MARK_NONE
    values = [value for key, value in entry.items() if str(key).strip().lower() == KEY]
    if not values:
        return MARK_NONE
    return MARK_FACTS if values == [FACTS] else MARK_OTHER


def entry_blocks_ai(entry):
    """이력 항목이 AI 입력에서 빠져야 하는가(표식 키가 있으면 값과 상관없이 — 모르는 값도 막는다)."""
    return mark_blocks_ai(entry_mark(entry))


def header_fields(text):
    """머리말에서 `title`·`description` 값을 느슨하게 읽는다(표식 글의 AI 입력 방벽이 쓴다). (제목, 설명) — 없으면 빈 글자. 닫히지 않은 머리말에서도 읽는다."""
    status, lines = _split_header(text)
    found = {"title": "", "description": ""}
    if status == "none":
        return "", ""
    for line in lines:
        pair = _key_value(line)
        if pair is not None and pair[0] in found and not found[pair[0]]:
            found[pair[0]] = _unquote(pair[1])
    return found["title"], found["description"]


def entry_titles_of(entry):
    """이력 항목 하나의 제목·주제 글자들(비어 있지 않은 문자열만)."""
    if not isinstance(entry, dict):
        return [entry] if isinstance(entry, str) and entry.strip() else []
    return [value.strip() for key in ENTRY_TITLE_KEYS for value in [entry.get(key)] if isinstance(value, str) and value.strip()]


def with_marker(content):
    """글 한 편(머리말 + 본문)의 머리말 끝에 정본 표식 줄(`provenance: "facts"`)을 넣어 돌려준다. 줄 끝(LF·CRLF)은 글을 따른다. 이미 정본 표식이 있으면 그대로,
    머리말이 없거나 읽을 수 없거나 모르는 표식 값이 있으면 ValueError. 이 함수는 **생성기가 구조화 Fact 글을 만들 때만** 부른다(시험이 확인)."""
    text = str(content)
    mark = mark_of_text(text)
    if mark == MARK_FACTS:
        return text
    if mark != MARK_NONE:
        raise ValueError("머리말을 안전하게 읽을 수 없거나 모르는 표식 값이 있어 표식을 넣지 못합니다")
    newline = "\r\n" if "\r\n" in text else "\n"
    body = text.lstrip("\ufeff")
    prefix = text[:len(text) - len(body)]            # 글 앞의 BOM 은 그대로 둔다(읽는 쪽과 같은 규칙으로 머리말을 찾는다)
    lines = body.split("\n")
    first = 0
    while not lines[first].strip(" \t\r\x0b\x0c"):
        first += 1
    end = next(index for index in range(first + 1, len(lines)) if _FENCE.fullmatch(lines[index].rstrip("\r")))
    lines.insert(end, CANONICAL_LINE + ("\r" if newline == "\r\n" else ""))
    return prefix + "\n".join(lines)


def entry_with_marker(entry):
    """이력 항목 사전에 `"provenance": "facts"` 칸을 더한 새 사전. 이미 다른 값이 있으면 ValueError. 생성기만 부른다(시험이 확인)."""
    if not isinstance(entry, dict):
        raise ValueError("이력 항목이 사전이 아닙니다")
    mark = entry_mark(entry)
    if mark == MARK_OTHER:
        raise ValueError("이력 항목에 모르는 표식 값이 있습니다")
    return dict(entry, **{KEY: FACTS})
