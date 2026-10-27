"""Chance 초안 → 사람 승인 후 공개 흐름(레지스트리 publish_flow: pr)의 규칙과 GitHub REST 클라이언트.

배경: 구글 게시자 정책은 '수동 검토나 큐레이션 없이 자동 생성된 콘텐츠에 광고를 두지 말라'고 안내한다. publish_flow 가 pr 이면
Chance 엔진은 글 한 쌍을 같은 방식(소스 선정·게이트·Gemini 폴백)으로 만들되 main 에 바로 올리지 않고 초안 브랜치(ai/draft/<날짜>-s<슬롯>)와
PR 로 올린다. 운영자가 휴대폰에서 PR 을 병합하면 push 이벤트가 사이트 배포(pages.yml)를 일으키고 그것이 공개이며, 닫으면 폐기다.
기본값 direct 는 지금 동작 그대로다(이 모듈은 direct 에서 아무것도 하지 않는다). 설명: docs/ARCHITECTURE.md §4-4.

이 모듈은 I/O 가 없는 규칙(이름·판정·소독·PR 본문)과 표준 라이브러리 REST 클라이언트만 둔다. git 을 부르는 실행부는 pipeline/draft_flow.py.

설계 결정(근거는 docs/ARCHITECTURE.md §4-4):
- 이력(history.json)의 항목은 글과 같은 커밋이 아니라 생성 시점에 main 에 따로 커밋한다. PR 에는 글 파일 둘만 있다. 슬롯·제목·이미지 중복
  검사가 지금처럼 main 의 이력만 보고, 초안이 둘 열려 있어도 이력 파일 충돌이 생기지 않는다(둘 다 같은 줄을 고치면 하나를 병합한 뒤
  다른 쪽이 충돌해 휴대폰에서 병합할 수 없다).
- 슬롯의 상태는 이력 항목(flow·branch·paths)과 글 파일이 main 에 있는지로 정한다: 항목이 있고 글이 main 에 있으면 ALREADY_PUBLISHED(병합됨),
  글이 없으면 DRAFT_PENDING(승인 대기이거나 닫혀 폐기됨 — 둘 다 같은 날 다시 만들지 않는다).
- 보조 안전망: 이력에 항목이 없어도 그 슬롯의 초안 브랜치가 원격에 있으면 DRAFT_PENDING 이다(이력 쓰기가 실패한 드문 경우).

보안: PR 제목·본문에는 AI 가 쓴 글과 외부 피드 문구가 섞인다. 모두 neutralize()를 거친다 — 멘션·이슈 참조·HTML·링크·코드 펜스를 무력화하고
한 줄로 접고 길이를 제한하며 비밀 모양을 가린다. 운영자 멘션과 원문 링크만 이 모듈이 직접 붙인다. 토큰은 환경변수로만 받고 로그·오류에 쓰지 않는다.
"""
import http.client
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import namedtuple
from datetime import date
from pathlib import Path

from pipeline import registry
from pipeline.console import one_line
from pipeline.llm import mask, scrub

FLOW_DIRECT, FLOW_PR = registry.PUBLISH_FLOWS
CHANCE_KEY = "chance"

BRANCH_PREFIX = "ai/draft/"
PR_TITLE_PREFIX = "[초안][Chance]"
TITLE_LIMIT = 200                  # PR 제목 전체(GitHub 한도 256자 안쪽)
BODY_LIMIT = 9000                  # PR 본문(GitHub 한도 65,536자보다 훨씬 작게 — 사람이 휴대폰에서 읽는 분량)
RETENTION_DAYS = 7                 # 병합됐거나 닫힌 초안 브랜치를 지우기까지(브랜치 이름의 날짜 기준)
ORPHAN_RETRY_DAYS = 3              # PR 이 없는 초안 브랜치에 PR 열기를 다시 시도하는 기간
MIN_BODY_CHARS = {"kr": 1000, "en": 1500}   # generator.MIN_BODY_CHARS 와 같은 값(시험이 대조한다)

LABEL_DRAFT = "초안"
LABEL_CHANNEL = "채널:Chance"
LABELS = (
    (LABEL_DRAFT, "d4c5f9", "승인 대기 중인 자동 생성 초안(병합하면 공개, 닫으면 폐기)"),
    (LABEL_CHANNEL, "1d76db", "Chance_Blog(GitHub Pages) 채널"),
)

STATE_PENDING = "DRAFT_PENDING"             # 이 슬롯의 초안이 있다(승인 대기이거나 닫힘) — 같은 슬롯을 다시 만들지 않는다
STATE_CHECK_FAILED = "DRAFT_CHECK_FAILED"   # 초안 브랜치 확인(git ls-remote)을 못 했다 — 이번 실행은 건너뛰고 다음 실행이 다시 본다

ZWSP = "\u200b"
_OWNER_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")
_REPO_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,38}/(?!\.+$)[A-Za-z0-9._-]{1,100}$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_BRANCH_RE = re.compile(r"^ai/draft/(\d{4}-\d{2}-\d{2})-(?:s(\d{1,2})|m(\d{6}))$")
_SAFE_URL_RE = re.compile(r"^https://[^\s<>\"'\\()\[\]`|]{1,480}$")
_POST_PATH_RE = re.compile(r"^_posts/[^\x00-\x1f\\]{1,200}\.md$")


class DraftFlowError(RuntimeError):
    """발행 흐름을 읽을 수 없거나 올바르지 않을 때. 직접 게시로 되돌아가지 않고 멈추게 하려고 예외로 올린다."""


# ----------------------------------------------------------------------------
# 발행 흐름 읽기
# ----------------------------------------------------------------------------
def chance_flow(registry_path=None):
    """레지스트리에서 chance 블로그의 publish_flow('direct'|'pr'). 항목이 없으면 direct(기본).

    읽지 못하거나 값이 올바르지 않으면 DraftFlowError 다: 승인 흐름을 켜 둔 채 레지스트리 오류 때문에 조용히 직접 게시로 떨어지면
    승인 없는 게시가 나가므로 멈춘다(레지스트리가 깨지면 CI·워치독이 먼저 알린다). pr 은 jekyll-git·mode auto 에서만 인정한다."""
    try:
        blog = registry.get_blog(registry.load_registry(registry_path), CHANCE_KEY)
    except registry.RegistryError as exc:
        raise DraftFlowError(f"발행 흐름을 읽을 수 없습니다: {one_line(exc, 200)}") from exc
    flow = blog.get("publish_flow", registry.DEFAULT_PUBLISH_FLOW)
    if flow not in registry.PUBLISH_FLOWS:
        raise DraftFlowError(f"레지스트리 publish_flow 값이 올바르지 않습니다: {one_line(repr(flow), 40)} (direct 또는 pr)")
    if flow == FLOW_PR and (blog.get("platform") != "jekyll-git" or blog.get("mode") != "auto"):
        raise DraftFlowError("publish_flow 가 pr 이면 platform 은 jekyll-git, mode 는 auto 여야 합니다(레지스트리 검증 규칙).")
    return flow


# ----------------------------------------------------------------------------
# 초안 브랜치 이름과 이력 항목
# ----------------------------------------------------------------------------
BranchInfo = namedtuple("BranchInfo", "day slot stamp")


def branch_name(date_str, slot=None, stamp=None):
    """초안 브랜치 이름. 정기 실행은 슬롯(ai/draft/2026-10-28-s9), 수동 실행은 생성 시각 HHMMSS(ai/draft/2026-10-28-m091722)."""
    if not _DATE_RE.fullmatch(str(date_str)):
        raise ValueError(f"날짜 형식이 올바르지 않습니다: {date_str!r}")
    if slot is not None:
        if isinstance(slot, bool) or not isinstance(slot, int) or not 0 <= slot <= 23:
            raise ValueError(f"슬롯은 0~23 정수여야 합니다: {slot!r}")
        return f"{BRANCH_PREFIX}{date_str}-s{slot}"
    if not re.fullmatch(r"\d{6}", str(stamp or "")):
        raise ValueError(f"수동 실행의 시각은 HHMMSS 6자리여야 합니다: {stamp!r}")
    return f"{BRANCH_PREFIX}{date_str}-m{stamp}"


def parse_branch(name):
    """branch_name 이 만든 이름이면 BranchInfo(day, slot, stamp), 아니면 None(모르는 브랜치는 정리 대상이 아니다)."""
    match = _BRANCH_RE.fullmatch(str(name))
    if not match:
        return None
    try:
        day = date.fromisoformat(match.group(1))
    except ValueError:
        return None
    slot = int(match.group(2)) if match.group(2) is not None else None
    if slot is not None and slot > 23:
        return None
    return BranchInfo(day, slot, match.group(3))


def entry_fields(date_str, slot, stamp, paths):
    """승인 흐름에서 이력 항목에 더하는 필드. flow=pr 표시, 초안 브랜치 이름, 글 파일 경로(저장소 상대, '/' 구분)."""
    return {"flow": FLOW_PR, "branch": branch_name(date_str, slot, stamp), "paths": [Path(p).as_posix() for p in paths]}


# ----------------------------------------------------------------------------
# 슬롯 판정
# ----------------------------------------------------------------------------
def slot_entry(history, date_str, slot):
    """generator.slot_state 와 같은 기준(날짜·슬롯이 같은 첫 항목)으로 그 슬롯의 이력 항목을 찾는다."""
    for item in history:
        if isinstance(item, dict) and item.get("date") == date_str and item.get("slot") == slot:
            return item
    return None


def valid_post_path(path):
    """글 파일 경로로 쓸 수 있는가: `_posts/` 아래의 .md, 제어 문자·역슬래시·`..` 구간이 없다."""
    return isinstance(path, str) and bool(_POST_PATH_RE.fullmatch(path)) and ".." not in path.split("/")


def posts_exist(entry, exists=os.path.exists):
    """이력 항목의 글 파일이 모두 있는가(승인 흐름의 글이 main 에 병합됐는가). 경로가 없거나 이상하면 없는 것으로 본다."""
    paths = entry.get("paths")
    return isinstance(paths, list) and bool(paths) and all(valid_post_path(p) and exists(p) for p in paths)


def refine_slot_state(state, slot, history, date_str, branch_exists=False, exists=os.path.exists):
    """generator.slot_state 의 결과(OUT_OF_WINDOW·ALREADY_PUBLISHED·DUE)를 승인 흐름에 맞게 다듬는다.

    - ALREADY_PUBLISHED: 그 슬롯의 이력 항목이 flow=pr 이고 글이 main 에 아직 없으면 STATE_PENDING(승인 대기 또는 닫혀 폐기).
      글이 main 에 있으면(병합됨) 그대로 ALREADY_PUBLISHED, flow 가 없는 옛·직접 게시 항목도 그대로다.
    - DUE: 이력에 없어도 그 슬롯의 초안 브랜치가 원격에 있으면 STATE_PENDING(이력 쓰기가 실패한 드문 경우의 중복 방지),
      브랜치를 확인하지 못했으면(branch_exists 가 None) STATE_CHECK_FAILED.
    - OUT_OF_WINDOW 는 그대로다."""
    if state == "ALREADY_PUBLISHED":
        entry = slot_entry(history, date_str, slot)
        if entry is not None and entry.get("flow") == FLOW_PR and not posts_exist(entry, exists):
            return STATE_PENDING
        return state
    if state == "DUE":
        if branch_exists is None:
            return STATE_CHECK_FAILED
        if branch_exists:
            return STATE_PENDING
    return state


# ----------------------------------------------------------------------------
# 외부 유래 문구 소독
# ----------------------------------------------------------------------------
_HTML_COMMENT = re.compile(r"(?s)<!--.*?(?:-->|\Z)")
_HTML_BLOCK = re.compile(r"(?is)<\s*(script|style|iframe|object|embed|svg|math|template|noscript)\b.*?(?:<\s*/\s*\1\s*>|\Z)")
_INVISIBLE = re.compile("[\u200b-\u200f\u202a-\u202e\u2060-\u2064\u2066-\u2069\ufeff]")
_ENTITY_START = re.compile(r"&(?=#?\w+;)")


def _clip(text, limit):
    if limit is None or len(text) <= limit:
        return text
    return text[:max(limit - 1, 0)].rstrip() + "…"


def neutralize(text, limit=None):
    """AI·피드에서 온 문구를 PR 제목·본문에 안전하게 넣을 한 줄로 만든다. 순서: 보이지 않는 글자 제거 → HTML 주석·script 류 제거 →
    비밀 모양 가리기 → 한 줄로 접기('::'·'##[' 포함) → 꺾쇠·대괄호·백틱·물결표를 무력화(HTML·링크·코드 펜스) → '&#64;' 같은 문자 참조를
    '&amp;' 로 감싸기 → '@' 뒤·'#' 뒤·'://' 가운데·'www.' 뒤에 영(0)폭 공백(멘션·이슈 참조·자동 링크) → 길이 제한.
    이 함수의 결과에는 '<'·'>'·'['·']'·'`'·'~'·멘션·이슈 참조·자동 링크가 남지 않는다(시험이 입력 종류별로 확인한다)."""
    raw = _INVISIBLE.sub("", "" if text is None else str(text))
    raw = _HTML_BLOCK.sub(" ", _HTML_COMMENT.sub(" ", raw))
    raw = one_line(mask(raw), 10 ** 9)
    for char, safe in (("<", "＜"), (">", "＞"), ("[", "［"), ("]", "］"), ("`", "'"), ("~", "～")):
        raw = raw.replace(char, safe)
    raw = _ENTITY_START.sub("&amp;", raw)
    raw = raw.replace("@", "@" + ZWSP).replace("#", "#" + ZWSP).replace("://", ":/" + ZWSP + "/")
    raw = re.sub(r"(?i)\bGH-(?=\d)", "GH-" + ZWSP, raw)
    raw = re.sub(r"(?i)\bwww\.", lambda m: m.group(0)[:3] + ZWSP + ".", raw)     # 'www.' 로 시작하는 주소도 자동 링크가 된다
    return _clip(raw, limit)


def safe_url(url):
    """링크로 걸어도 되는 단순한 https 주소만 돌려준다(공백·꺾쇠·따옴표·괄호·백틱·세로선이 있으면 빈 문자열)."""
    text = str(url or "")
    return text if _SAFE_URL_RE.fullmatch(text) else ""


def valid_owner(owner):
    return bool(_OWNER_RE.fullmatch(str(owner or "")))


def valid_repo(repo):
    return bool(_REPO_RE.fullmatch(str(repo or "")))


# ----------------------------------------------------------------------------
# 글 파일에서 PR 본문 재료 읽기
# ----------------------------------------------------------------------------
_FRONT = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.S)
_SOURCES_HEADING = re.compile(r"(?im)^##\s*(?:출처|참고 자료|sources)\s*$")


def split_post(text):
    """(front matter 문자열 또는 '', 본문)."""
    text = str(text or "").lstrip("\ufeff")
    match = _FRONT.match(text)
    if not match:
        return "", text
    return match.group(1), text[match.end():]


def front_value(front, key):
    """front matter 의 한 줄 `키: 값`(따옴표는 벗긴다). 없으면 빈 문자열."""
    found = re.search(rf"(?m)^{re.escape(key)}:[ \t]*(.*?)[ \t]*$", front or "")
    if not found:
        return ""
    value = found.group(1).strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1]
    return value


def story_of(body):
    """본문에서 출처 목록(## 출처·## Sources) 앞부분."""
    return _SOURCES_HEADING.split(body, maxsplit=1)[0]


def readable_length(body):
    """generator._validate_editorial_body 가 분량을 재는 방식과 같은 글자 수(링크·이미지·마크다운 기호·공백을 뺀 본문 글자)."""
    readable = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", story_of(body))
    readable = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", readable)
    readable = re.sub(r"<[^>]+>|[`*_>#|~]", " ", readable)
    return len(re.sub(r"\s+", "", readable))


def has_source_list(body, url):
    """글 끝 출처 목록(## 출처·## Sources)에 원문 주소가 있는가."""
    parts = _SOURCES_HEADING.split(body, maxsplit=1)
    return len(parts) == 2 and bool(url) and url in parts[1]


def cites_source(body, url):
    """본문(출처 목록 앞)이 원문 주소를 인용하는가(생성기의 본문 검증과 같은 기준)."""
    return bool(url) and url in story_of(body)


def has_notice(body):
    """글 끝에 소스 약관이 요구하는 고지문(기울임 한 문단)이 있는가."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
    last = paragraphs[-1] if paragraphs else ""
    return len(last) >= 20 and last.startswith("*") and last.endswith("*") and "\n" not in last


def excerpt_of(body, limit=240):
    """본문의 첫 문단(60자 이상인 첫 문단) 발췌: 이미지·링크·제목 표시·HTML·강조 기호를 걷어 낸 평문. 없으면 빈 문자열."""
    for paragraph in re.split(r"\n\s*\n", story_of(body)):
        text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", paragraph)
        text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
        text = re.sub(r"(?m)^\s{0,3}(?:#{1,6}\s*|>\s*|[-*+]\s+|\d+[.)]\s+)", "", text)
        text = re.sub(r"<[^>]+>", " ", text)
        text = " ".join(re.sub(r"[*_`~]", "", text).split())
        if len(text) >= 60:
            return _clip(text, limit)
    return ""


# ----------------------------------------------------------------------------
# PR 제목·본문
# ----------------------------------------------------------------------------
def build_pr_title(kr_title, en_title, limit=TITLE_LIMIT):
    """`[초안][Chance] <한국어 제목> / <영어 제목>`. 제목은 각각 소독하고 80자로 줄이며 전체는 limit 이하다."""
    kr = neutralize(kr_title, 80) or "(제목 없음)"
    en = neutralize(en_title, 80) or "(no title)"
    return _clip(f"{PR_TITLE_PREFIX} {kr} / {en}", limit)


def _slot_text(entry):
    slot = entry.get("slot")
    day = neutralize(entry.get("date"), 12) or "날짜 미상"
    if isinstance(slot, int) and not isinstance(slot, bool) and 0 <= slot <= 23:
        return f"{day} {slot}시 슬롯"
    return f"{day} 수동 실행(슬롯 없음)"


def _facts(body, url, minimum):
    """한 언어 글의 자동 점검 값: (분량 문구, 인용 여부, 출처 목록 여부, 고지문 여부)."""
    length = readable_length(body)
    mark = "통과" if length >= minimum else "미달(확인 필요)"
    return f"{length:,}자(최소 {minimum:,}자, {mark})", cites_source(body, url), has_source_list(body, url), has_notice(body)


def _yn(flag):
    return "있음" if flag else "**없음(확인 필요)**"


def build_pr_body(entry, kr_text, en_text, owner=None, repo=None):
    """승인 PR 본문(마크다운). entry 는 이력 항목, kr_text·en_text 는 글 파일 전체. 모든 외부 유래 문구는 neutralize 를 거친다.

    구성: 승인 안내(운영자 멘션) · 요약(분야·출처·원문 링크·슬롯) · 제목 · 첫 문단 발췌 · 자동 점검 결과 · 체크리스트 · 안내."""
    entry = entry if isinstance(entry, dict) else {}
    kr_front, kr_body = split_post(kr_text)
    en_front, en_body = split_post(en_text)
    kr_title = entry.get("kr_title") or front_value(kr_front, "title")
    en_title = entry.get("en_title") or front_value(en_front, "title")
    url = safe_url(entry.get("source_url"))
    source = neutralize(entry.get("source") or front_value(kr_front, "source_name"), 60) or "출처 이름 없음"
    source_line = f"- 출처: {source}" + (f" — [원문 보기]({url})" if url else " — 원문 주소가 안전한 https 주소가 아니라 링크를 걸지 않았습니다(확인 필요)")
    category = neutralize(front_value(kr_front, "category"), 40) or neutralize(entry.get("lane"), 30) or "분야 미상"
    kr_len, kr_cite, kr_list, kr_notice = _facts(kr_body, url, MIN_BODY_CHARS["kr"])
    en_len, en_cite, en_list, en_notice = _facts(en_body, url, MIN_BODY_CHARS["en"])
    mention = f"@{owner} " if valid_owner(owner) else ""
    quotes = []
    for label, body in (("한국어", kr_body), ("English", en_body)):
        excerpt = neutralize(excerpt_of(body), 260) or "(발췌할 문단을 찾지 못했습니다 — 글 파일을 직접 확인하세요)"
        quotes.append(f"> **{label}** {excerpt}")
    lines = [
        f"{mention}**승인 대기 초안**입니다. **병합(Merge)하면 공개**되고, **닫으면(Close) 폐기**됩니다.",
        "",
        "## 요약",
        f"- 분야: {category}",
        source_line,
        f"- 발행 슬롯: {_slot_text(entry)}",
        "",
        "## 제목",
        f"- 한국어: {neutralize(kr_title, 120) or '(제목 없음)'}",
        f"- English: {neutralize(en_title, 120) or '(no title)'}",
        "",
        "## 첫 문단 발췌",
        "\n>\n".join(quotes),
        "",
        "## 자동 점검 결과(저장 전에 이미 통과한 항목 — 사람의 확인을 대신하지 않습니다)",
        f"- 본문 분량: 한국어 {kr_len} · 영어 {en_len}",
        f"- 원문 링크 인용: 한국어 {_yn(kr_cite)} · 영어 {_yn(en_cite)}",
        f"- 글 끝 출처 목록: 한국어 {_yn(kr_list)} · 영어 {_yn(en_list)}",
        f"- 출처 고지문(AI 작성·검토 안 받음 안내): 한국어 {_yn(kr_notice)} · 영어 {_yn(en_notice)}",
        "- 제목 유사도: 기존 글·대기 중인 초안과 비슷하지 않음(후보 0.6·생성 제목 0.7 기준, 생성기가 검사함)",
        "",
        "## 승인 체크리스트",
        "- [ ] 원문과 수치·사실을 대조했다",
        "- [ ] 제목·요약에 문제가 없다",
        "- [ ] 병합 = 공개(사람 검토 단계)",
        "",
        "## 안내",
        "- 글은 **Files changed** 의 `_posts/` 파일 두 개(한국어·영어)입니다. 병합하기 전에는 사이트에 보이지 않습니다.",
        "- **병합하면** `main` 에 올라가 `[공통] 사이트 자동 배포`가 실행되고 몇 분 안에 공개됩니다. **닫으면** 글은 올라가지 않습니다"
        f"(브랜치는 {RETENTION_DAYS}일 뒤 자동으로 지워지고, 같은 슬롯·같은 주제는 다시 만들지 않습니다).",
        "- 검사(CI)는 봇이 만든 PR 에서는 자동으로 돌지 않습니다(GitHub 규칙). 글 파일만 바뀌므로 병합에 필요하지 않습니다.",
        "- 이 글은 AI 가 만든 초안이고 이 PR 은 `[Chance] 글 자동 작성·게시` 워크플로가 만들었습니다.",
    ]
    return _clip("\n".join(lines), BODY_LIMIT)


# ----------------------------------------------------------------------------
# GitHub REST 클라이언트(표준 라이브러리)
# ----------------------------------------------------------------------------
API_ROOT = "https://api.github.com"


class GitHubError(Exception):
    """GitHub API 호출 실패. status 는 HTTP 상태(네트워크 오류면 None). 메시지에는 토큰·헤더가 들어가지 않고 소독돼 있다."""

    def __init__(self, message, status=None):
        super().__init__(message)
        self.message, self.status = message, status

    @property
    def retryable(self):
        return self.status is None or self.status >= 500

    @property
    def already_exists(self):
        return self.status == 422 and "already exists" in self.message.lower()


class PullList(list):
    """list_draft_pull_requests 의 결과. complete 가 False 면 읽을 수 있는 쪽을 모두 가득 채워 읽었다는 뜻이라 더 오래된 PR 이
    목록에 없을 수 있다 — 목록에 없다는 것이 'PR 이 없다'는 증거가 아니다(그 브랜치를 지우면 열린 PR 이 닫힌다)."""
    complete = True


class GitHubClient:
    """저장소 범위 REST 클라이언트. 모든 실패는 GitHubError 로 바꾼다. opener 를 바꿔 끼워 네트워크 없이 시험한다."""

    def __init__(self, repo, token, opener=None, timeout=20):
        if not valid_repo(repo):
            raise ValueError("저장소 이름 형식이 올바르지 않습니다(소유자/저장소)")
        self.repo, self._token, self._timeout = repo, token, timeout
        self._open = opener or urllib.request.urlopen

    def _clean(self, text, limit=200):
        return scrub(one_line(text, limit), (self._token,))

    def request(self, method, path, payload=None, params=None):
        url = f"{API_ROOT}/repos/{self.repo}{path}" + (("?" + urllib.parse.urlencode(params)) if params else "")
        headers = {"Authorization": f"Bearer {self._token}", "Accept": "application/vnd.github+json",
                   "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "chanceblog-draft-flow"}
        data = None
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with self._open(request, timeout=self._timeout) as resp:
                body = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                parsed = json.loads(exc.read().decode("utf-8", "replace"))
                if isinstance(parsed, dict):
                    detail = str(parsed.get("message") or "")
                    errors = parsed.get("errors")
                    if isinstance(errors, list):
                        detail += " " + " ".join(str(e.get("message") if isinstance(e, dict) else e) for e in errors[:3])
            except (OSError, ValueError, AttributeError):
                detail = ""
            raise GitHubError(f"HTTP {exc.code}" + (f": {self._clean(detail)}" if detail.strip() else ""), status=exc.code) from None
        except (urllib.error.URLError, http.client.HTTPException, OSError, UnicodeDecodeError) as exc:
            raise GitHubError(f"{type(exc).__name__}: {self._clean(exc, 150)}") from None
        if not body:
            return None
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            raise GitHubError("응답이 JSON 이 아닙니다") from None

    # ---- PR ----
    def create_pull_request(self, title, head, base, body):
        """PR 을 연다. 돌려주는 값: 번호(정수). 이미 같은 브랜치의 PR 이 있으면 GitHubError(already_exists)."""
        data = self.request("POST", "/pulls", {"title": title, "head": head, "base": base, "body": body})
        number = data.get("number") if isinstance(data, dict) else None
        if isinstance(number, bool) or not isinstance(number, int):
            raise GitHubError("응답에 PR 번호가 없습니다")
        return number

    @staticmethod
    def _summary(raw):
        head = raw.get("head") if isinstance(raw.get("head"), dict) else {}
        repo = head.get("repo") if isinstance(head.get("repo"), dict) else {}
        return {"number": raw.get("number"), "state": raw.get("state"), "merged": bool(raw.get("merged_at")),
                "head_ref": head.get("ref"), "head_repo": repo.get("full_name"), "created_at": raw.get("created_at"),
                "title": raw.get("title")}

    def list_draft_pull_requests(self, state="all", max_pages=3):
        """이 저장소 안의 초안 브랜치(ai/draft/…)에서 연 PR 목록(최신순, 저장소의 PR 최근 100×max_pages건 안에서). 포크의 PR 은 뺀다.
        결과의 complete 가 False 면 더 오래된 PR 이 목록 밖에 있을 수 있다(PullList)."""
        found = PullList()
        for page in range(1, max_pages + 1):
            items = self.request("GET", "/pulls", params={"state": state, "sort": "created", "direction": "desc",
                                                          "per_page": 100, "page": page})
            if not isinstance(items, list):
                raise GitHubError("PR 목록 응답이 배열이 아닙니다")
            for raw in items:
                if not isinstance(raw, dict):
                    continue
                summary = self._summary(raw)
                same_repo = str(summary["head_repo"] or "").lower() == self.repo.lower()
                if same_repo and str(summary["head_ref"] or "").startswith(BRANCH_PREFIX):
                    found.append(summary)
            if len(items) < 100:
                break
        else:
            found.complete = False        # 쪽마다 가득 찬 채 끝까지 읽었다: 더 오래된 PR 이 남아 있을 수 있다
        return found

    def find_pull_request(self, head_ref):
        """브랜치 head_ref 로 연 PR(어느 상태든) 한 건. 없으면 None."""
        owner = self.repo.split("/", 1)[0]
        items = self.request("GET", "/pulls", params={"state": "all", "head": f"{owner}:{head_ref}", "per_page": 5})
        for raw in items if isinstance(items, list) else []:
            if isinstance(raw, dict) and isinstance(raw.get("head"), dict) and raw["head"].get("ref") == head_ref:
                return self._summary(raw)
        return None

    # ---- 라벨 ----
    def ensure_label(self, name, color, description):
        """라벨을 만든다. 이미 있으면(HTTP 422) 그대로 둔다."""
        try:
            self.request("POST", "/labels", {"name": name, "color": color, "description": description})
        except GitHubError as exc:
            if exc.status != 422:
                raise

    def add_labels(self, number, labels):
        self.request("POST", f"/issues/{int(number)}/labels", {"labels": list(labels)})


def pull_url(repo, number):
    """PR 주소. API 가 준 주소가 아니라 저장소 이름과 숫자 번호로 직접 만든다."""
    return f"https://github.com/{repo}/pull/{int(number)}"


def retry(call, attempts=3, sleep=time.sleep, delays=(2, 5)):
    """call() 을 부른다. GitHubError 중 재시도할 수 있는 것(5xx·네트워크)만 최대 attempts 번까지 다시 시도한다(4xx 는 바로 올린다)."""
    for index in range(attempts):
        try:
            return call()
        except GitHubError as exc:
            if not exc.retryable or index == attempts - 1:
                raise
            sleep(delays[min(index, len(delays) - 1)])
