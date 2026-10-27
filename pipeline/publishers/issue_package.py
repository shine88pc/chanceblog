"""초안 패키지(GitHub 이슈) 어댑터 — 티스토리·네이버처럼 공식 자동 게시 수단이 없는 채널용.

게이트를 통과한 글을 **GitHub 이슈 1개(= 초안 1건)** 로 만들어 보여 주기만 한다. 공개하지 않는다. 운영자가 이슈의 복사 상자를 복사해
티스토리·네이버에 직접 발행하고 이슈를 닫는다. 로그인·세션·쿠키 자동화는 만들지 않고 계정 정보는 저장·처리하지 않는다.
설명: docs/ARCHITECTURE.md §7-B, docs/ACTIONS_GUIDE.md 6-12·6-13, docs/SECURITY_GUARDRAILS.md G-S7·G-L8.

이 모듈은 표준 라이브러리와 pipeline.gates 만 쓴다(의존성 추가 없음). 두 부분이다.

1) 순수 함수(입출력 없음): `build_issue(draft)` 가 제목·본문·라벨·초안 번호를 만든다. 연습 실행(DRY_RUN)은 이것만 불러 본문을 실행 요약에
   보이고 API 를 부르지 않는다. **AI 출력은 신뢰하지 않는다** — 이슈 본문·제목이 되기 전에 모두 소독한다(G-L8):
   - `@이름` 멘션과 `#123`·`GH-123` 이슈 참조 뒤에 영(0)폭 공백(U+200B)을 넣어 알림·자동 링크가 되지 않게 한다(코드 상자 안도 같다. 주소 안의
     것과 영문·숫자 바로 뒤의 `@`(이메일)는 건드리지 않는다). HTML 주석 `<!--` 도 같은 방식으로 풀어 숨은 표지(`draft-id`)를 흉내 낼 수 없다.
   - 코드 상자(복사 상자)는 본문 안의 가장 긴 백틱 줄보다 더 긴 펜스로 감싸 상자를 빠져나오지 못하게 한다.
   - 티스토리 HTML 상자는 gates.sanitize_html(허용 태그만, 속성 제거, 링크 기본 제거, script·iframe·style·object 내용째 제거)을 한 번 더 거친다.
   - 네이버의 서식 있는 글은 정화된 HTML 을 마크다운으로 옮기며 마크다운·HTML 문법 문자를 모두 이스케이프한다(`<`·`&`·`[`·`|`·`$` 등).
   - 제목은 태그·제어 문자를 지우고 한 줄로 접어 60자로 자른다. 접두사 `[초안][<채널>]`과 라벨(`초안`·`채널:<라벨>`)은 고정값이다(모델이 정하지 않는다).
   - 본문은 이슈 한도(65,536자) 안에 안전 여유(60,000자)를 두고, 못 맞추면 잘라 내지 않고 실패한다(잘린 글을 그대로 발행하지 않게).
2) 입출력: `IssuePackagePublisher` 가 GitHub REST API 를 urllib 로 부른다(토큰은 `GITHUB_TOKEN`, 오류 문구에서 가린다).
   - 멱등: 본문 첫 줄의 숨은 표지 `<!-- draft-id: <블로그키>-<날짜>-<해시> -->` 와 같은 표지가 있는 이슈(열림·닫힘 모두)를 만들기 전에 찾는다.
     있으면 새로 만들지 않고 그 이슈를 돌려준다. 만들다 응답만 실패한 경우(시간 초과 등)도 다시 찾아 본다.
   - 라벨 `초안`·`채널:<라벨>` 은 없으면 만든다(색·설명 고정).
   - 같은 채널에 열린 초안 이슈 수를 센다(적체 방지, run.py 가 OPEN_DRAFT_LIMIT 이상이면 새로 만들지 않는다).
"""
import hashlib
import http.client
import json
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import date as date_type
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser

from pipeline import gates
from pipeline.publishers.base import PublishError, PublishResult, redact
from pipeline.state import KST

API_ROOT = "https://api.github.com"
DRAFT_LABEL = "초안"
CHANNEL_LABEL_PREFIX = "채널:"
DISCARD_LABEL = "폐기"            # 운영자가 쓰지 않을 초안에 붙인다(이 어댑터는 만들지 않는다). 붙은 이슈는 적체 점검에서 세지 않는다
OPEN_DRAFT_LIMIT = 3              # 같은 채널에 열린 초안 이슈가 이만큼이면 새 초안을 만들지 않는다(적체 방지)
TITLE_SHOWN = 60                  # 이슈 제목에 쓰는 글 제목의 최대 글자 수
COPY_TITLE_MAX = 200              # 복사용 제목 상자의 최대 글자 수
BODY_LIMIT = 65536                # GitHub 이슈 본문의 최대 글자 수
BODY_BUDGET = 60000               # 안전 여유를 둔 목표(이 안에 못 맞추면 실패한다)
IMAGES_MAX, SOURCES_MAX, TAGS_MAX, NOTES_MAX = 12, 12, 10, 12
SEARCH_PAGES = 3                  # 같은 표지를 찾을 때 읽는 쪽 수(쪽마다 100건)
ZWSP = "​"                   # 영(0)폭 공백: 멘션·이슈 참조·HTML 주석을 무력화하는 데 쓴다
UNSPLASH_UTM = "utm_source=chanceblog&utm_medium=referral"   # Unsplash 표기 링크의 출처 표시(앱 이름은 운영자가 등록한 것으로 바꿀 수 있다 — 미확인)

# platform → (채널 라벨, 서비스 이름, 본문 형식). 라벨은 레지스트리 PACKAGE_PLATFORMS 와 같다(어댑터는 레지스트리를 읽지 않으므로 여기에도 둔다).
PACKAGE_INFO = {
    "tistory": {"label": "티스토리", "service": "티스토리", "format": "html"},
    "naver": {"label": "네이버", "service": "네이버 블로그", "format": "rich"},
}
# 라벨 색(16진수, # 없음)·설명(100자 이내). 라벨이 없을 때만 만든다.
LABEL_STYLE = {
    DRAFT_LABEL: ("fbca04", "AI가 만든 초안 — 읽고 직접 발행한 뒤 이슈를 닫는다(발행 완료)"),
    CHANNEL_LABEL_PREFIX + "티스토리": ("ff6a3d", "티스토리에 올릴 초안 패키지"),
    CHANNEL_LABEL_PREFIX + "네이버": ("03c75a", "네이버 블로그에 올릴 초안 패키지"),
}
# 정화 통계(gates.sanitize_html 의 stats 키) → 운영자가 읽는 말
REMOVED_TEXT = {"dropped_blocks": "내용째 지운 블록(script·iframe 등)", "unwrapped_tags": "벗겨 낸 태그", "links_removed": "지운 링크"}

_KEY_RX = re.compile(r"^[a-z][a-z0-9_]{1,30}$")
_DATE_RX = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_RUN_URL_RX = re.compile(r"^https://github\.com/[A-Za-z0-9_.\-]+/[A-Za-z0-9_.\-]+/actions/runs/\d+$")
_ISSUE_URL_RX = re.compile(r"^https://github\.com/[A-Za-z0-9_.\-]+/[A-Za-z0-9_.\-]+/issues/\d+$")
_REPO_RX = re.compile(r"^(?!\.+/)[A-Za-z0-9_.\-]+/(?!\.+$)[A-Za-z0-9_.\-]+$")   # `소유자/이름`. 점으로만 된 조각(`.`·`..`)은 경로를 거슬러 오르므로 막는다
_SAFE_URL_RX = re.compile(r"^https://[^\s<>\"'`()\\|\[\]{}]{1,500}$")
_UNSPLASH_RX = re.compile(r"^https://unsplash\.com/[^\s<>\"'`()\\|\[\]{}]{0,300}$")
_MARKER_RX = re.compile(r"^\s*<!--\s*draft-id:\s*(\S+)\s*-->")


# ----------------------------------------------------------------------------
# 입력 모양
# ----------------------------------------------------------------------------
@dataclass
class PackageDraft:
    """초안 패키지 한 건의 재료. 러너가 게이트를 통과한 글로 채운다.

    html: gates 정화를 거친 본문(면책 문구 포함). 어댑터가 한 번 더 정화한다(allow_links 가 거짓이면 링크도 지운다).
    tags: 해시태그(글의 라벨). images: [{purpose, url, source, author, author_url, license, ai_generated}]. sources: [{title, url}].
    gate: 게이트 점검 요약(attempts·model·chars·min_chars·max_chars·title_chars·title_min·title_max·warnings·removed).
    run_url: 만든 Actions 실행 주소(있을 때만 본문에 링크로 쓴다)."""
    blog_key: str
    platform: str
    channel_label: str
    date: str
    title: str
    html: str
    tags: list = field(default_factory=list)
    images: list = field(default_factory=list)
    sources: list = field(default_factory=list)
    gate: dict = field(default_factory=dict)
    allow_links: bool = False
    run_url: str = ""


@dataclass
class IssueSpec:
    title: str
    body: str
    labels: list
    draft_id: str
    channel_label: str


# ----------------------------------------------------------------------------
# 소독(G-L8): AI 출력은 이슈 본문·제목이 되기 전에 여기를 지난다
# ----------------------------------------------------------------------------
# 눈에 안 보이면서 글자 방향·모양을 바꾸는 서식 문자(방향 표시·방향 덮어쓰기·단어 결합·BOM·소프트 하이픈). 영폭 공백(ZWSP)은 이 어댑터가 쓰는 것이라
# 일부러 지우지 않는다 — clean() 을 소독 뒤에 또 불러도 소독이 풀리지 않게(멱등)
_INVISIBLE = frozenset("‎‏‪‫‬‭‮⁠⁦⁧⁨⁩﻿­")
# 소독 대상. 주소(URL)는 그대로 둔다(안의 `@`·`#` 은 링크의 일부다). 멘션은 GitHub 이 보는 것과 같게 '앞 글자가 영문·숫자·밑줄이 아닐 때'만(이메일 안의
# @ 는 그대로, 한글 바로 뒤의 @이름 은 멘션이 되므로 소독한다). 이슈 참조는 `#숫자`(owner/repo#12 포함)와 `GH-숫자`, HTML 주석은 `<!--`.
_NEUTRAL_RX = re.compile(r"(?P<url>https?://[^\s<>\"'`]+)"
                         r"|(?P<mention>(?<![A-Za-z0-9_])@(?=[A-Za-z0-9]))"
                         r"|(?P<ref>#(?=\d))"
                         r"|(?P<gh>(?i:GH-)(?=\d))"
                         r"|(?P<comment><!--)")
_DANGEROUS_BLOCK_RX = re.compile(r"<(script|style|iframe|object|embed|svg|math|template)\b[^>]*>.*?</\1\s*>", re.IGNORECASE | re.DOTALL)
_TAG_RX = re.compile(r"</?[A-Za-z!][^>]*>")


def clean(text, multiline=False):
    """제어 문자·방향 서식 문자를 지우고 줄 끝을 \\n 으로 통일한다. multiline 이 아니면 한 줄로 접는다(연속 공백 하나로)."""
    raw = str(text if text is not None else "")
    raw = raw.replace("\r\n", "\n").replace("\r", "\n").replace(" ", "\n").replace(" ", "\n")
    kept = "".join(ch for ch in raw if ch in "\n\t" or (unicodedata.category(ch) != "Cc" and ch not in _INVISIBLE))
    return kept if multiline else " ".join(kept.split())


def neutralize(text):
    """`@이름`·`#123`·`GH-123`·`<!--` 를 알림·자동 링크·주석이 되지 않게 영폭 공백으로 푼다. 이미 푼 글에 또 불러도 같다(멱등)."""
    def swap(match):
        if match.group("url"):
            return match.group("url")
        if match.group("mention"):
            return "@" + ZWSP
        if match.group("ref"):
            return "#" + ZWSP
        if match.group("gh"):
            return match.group("gh") + ZWSP
        return "<" + ZWSP + "!--"
    return _NEUTRAL_RX.sub(swap, str(text))


def fence(text, info=""):
    """복사 상자. 본문 안의 가장 긴 백틱 줄(``` 포함)보다 한 칸 더 긴 펜스로 감싸 상자를 빠져나오지 못하게 한다(최소 3칸)."""
    body = str(text).replace("\r\n", "\n").replace("\r", "\n").strip("\n")
    longest = max([len(run) for run in re.findall(r"`+", body)] + [2])
    ticks = "`" * (longest + 1)
    return f"{ticks}{info}\n{body}\n{ticks}"


_MD_SPECIAL = re.compile(r"([\\`*_\[\]<>|~$&])")


def md_escape(text):
    """마크다운·HTML 문법 문자를 글자로 만든다(제목·목록·표·링크·코드·강조·HTML·수식·엔티티). 줄 맨 앞의 문법은 문단 단위로 따로 푼다(_line_starts)."""
    return _MD_SPECIAL.sub(r"\\\1", str(text))


def md_inline(text):
    """한 줄 마크다운(목록·표 칸·문장)에 넣을 AI·외부 유래 글: 접고 → 이스케이프하고 → 멘션·참조를 푼다."""
    return neutralize(md_escape(clean(text)))


def safe_url(url, pattern=_SAFE_URL_RX):
    """https 주소만(공백·꺾쇠·따옴표·괄호·세로선·역슬래시·대괄호 없음). 아니면 빈 문자열."""
    value = str(url or "").strip()
    return value if pattern.match(value) else ""


def plain_title(title):
    """글 제목을 한 줄 글자로: script·style 같은 블록은 내용째, 나머지 태그·HTML 주석은 태그만 지우고 접는다."""
    text = _TAG_RX.sub(" ", _DANGEROUS_BLOCK_RX.sub(" ", clean(title)))
    return " ".join(text.split())


# ----------------------------------------------------------------------------
# 정화된 HTML → 마크다운·평문(네이버의 서식 있는 글·평문 상자)
# ----------------------------------------------------------------------------
class _Node:
    __slots__ = ("tag", "attrs", "children")

    def __init__(self, tag, attrs=None):
        self.tag, self.attrs, self.children = tag, dict(attrs or ()), []


class _TreeBuilder(HTMLParser):
    """gates.sanitize_html 이 낸 HTML 을 트리로 읽는다(허용 태그만 있고 닫힘이 맞는다). 모르는 태그가 와도 자식 글만 살린다."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = _Node("root")
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = _Node(tag, attrs)
        self.stack[-1].children.append(node)
        if tag != "br":
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.stack[-1].children.append(_Node(tag, attrs))

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                return

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def _tree(clean_html):
    builder = _TreeBuilder()
    builder.feed(clean_html or "")
    builder.close()
    return builder.root.children


_BLOCK_TAGS = frozenset({"p", "h2", "h3", "h4", "ul", "ol", "li", "blockquote"})
_HEADING_MARK = {"h2": "###", "h3": "####", "h4": "#####"}   # 이슈 구역 제목(##)보다 한 단계 아래로
_HARD_BREAK = "\\\n"                                         # 마크다운 강제 줄바꿈(<br>)
_LIST_ITEM_RX = re.compile(r"^(?:- |\d+\. )")


def _ws(text):
    return re.sub(r"[ \t\r\n\f\v]+", " ", text)


def _wrap(inner, mark):
    core = inner.strip()
    if not core:
        return inner
    return inner[:len(inner) - len(inner.lstrip())] + mark + core + mark + inner[len(inner.rstrip()):]


def _inline_md(nodes):
    out = []
    for node in nodes:
        if isinstance(node, str):
            out.append(md_escape(_ws(node)))
        elif node.tag == "br":
            out.append(_HARD_BREAK)
        elif node.tag in ("strong", "b"):
            out.append(_wrap(_inline_md(node.children), "**"))
        elif node.tag in ("em", "i"):
            out.append(_wrap(_inline_md(node.children), "*"))
        elif node.tag == "a":
            text, href = _inline_md(node.children), safe_url(node.attrs.get("href"))
            out.append(f"[{text}]({href})" if href and text.strip() else text)
        else:
            out.append(_inline_md(node.children))
    return "".join(out)


def _tidy(text):
    """노드(굵게·기울임·링크) 사이에 겹친 공백을 하나로 접고, 강제 줄바꿈 앞뒤의 공백을 지운다."""
    folded = re.sub(r"[ \t]{2,}", " ", text)
    return re.sub(r" ?\\\n ?", lambda _match: _HARD_BREAK, folded)


def _line_starts(text):
    """문단의 각 줄(강제 줄바꿈으로 나뉨) 맨 앞의 `#`·`-`·`+`·`=`·`1.` 이 제목·목록·구분선이 되지 않게 푼다. 문단 글자는 이미 md_escape 를 거쳤다."""
    lines = []
    for line in text.strip().split(_HARD_BREAK):
        lead = len(line) - len(line.lstrip())
        rest = line[lead:]
        number = re.match(r"^\d+(?=[.)])", rest)
        if number:
            at = lead + number.end()
            line = line[:at] + "\\" + line[at:]
        elif rest[:1] in ("#", "-", "+", "="):
            line = line[:lead] + "\\" + line[lead:]
        lines.append(line)
    return _HARD_BREAK.join(lines)


def _is_block(node):
    return not isinstance(node, str) and node.tag in _BLOCK_TAGS


def _blocks_md(nodes):
    blocks, run = [], []

    def paragraph(items):
        text = _tidy(_inline_md(items)).strip()
        if text:
            blocks.append(_line_starts(text))

    for node in nodes:
        if not _is_block(node):
            run.append(node)
            continue
        paragraph(run)
        run.clear()
        if node.tag in _HEADING_MARK:
            text = _tidy(_inline_md(node.children)).strip().replace(_HARD_BREAK, " ")
            if text:
                blocks.append(f"{_HEADING_MARK[node.tag]} {text}")
        elif node.tag == "p":
            blocks.extend(_blocks_md(node.children))      # 문단 안에 문단·목록이 중첩돼 오면 따로 떼어 낸다(글자만 있으면 문단 하나)
        elif node.tag in ("ul", "ol"):
            blocks.append(_list_md(node))
        elif node.tag == "li":
            blocks.append(_item_md(node, "- "))
        elif node.tag == "blockquote":
            inner = "\n\n".join(_blocks_md(node.children))
            blocks.append("\n".join(("> " + line) if line else ">" for line in inner.split("\n")))
    paragraph(run)
    return [block for block in blocks if block]


def _item_md(item, marker):
    blocks = _blocks_md(item.children)
    if not blocks:
        return ""                                  # 빈 항목은 만들지 않는다(마커만 남아 "1." 한 줄이 되지 않게)
    pad = " " * len(marker)
    out = []
    for index, block in enumerate(blocks):
        lines = block.split("\n")
        if index == 0:
            out.append(marker + lines[0])
            out.extend((pad + line) if line else "" for line in lines[1:])
            continue
        if not _LIST_ITEM_RX.match(block):      # 중첩 목록은 바로 이어 붙이고, 그 밖의 블록은 빈 줄로 띄운다
            out.append("")
        out.extend((pad + line) if line else "" for line in lines)
    return "\n".join(out)


def _list_items(node):
    """목록의 항목(li). 목록 바로 아래의 글·다른 태그는 항목으로 감싸 살린다(AI 글이 `<ul>글<li>…` 모양으로 와도 글자를 잃지 않는다)."""
    for child in node.children:
        if isinstance(child, str) and not child.strip():
            continue
        if isinstance(child, str) or child.tag != "li":
            wrapped = _Node("li")
            wrapped.children.append(child)
            child = wrapped
        yield child


def _list_md(node):
    ordered, items = node.tag == "ol", []
    for child in _list_items(node):
        text = _item_md(child, f"{len(items) + 1}. " if ordered else "- ")
        if text:                                   # 빈 항목은 건너뛰고 번호를 이어서 센다
            items.append(text)
    return "\n".join(items)


def to_markdown(clean_html):
    """정화된 HTML 을 이슈 화면에서 선택·복사할 마크다운으로 옮긴다. 글자는 모두 이스케이프하고 멘션·참조를 푼다."""
    return neutralize("\n\n".join(_blocks_md(_tree(clean_html))))


def _inline_plain(nodes):
    out = []
    for node in nodes:
        if isinstance(node, str):
            out.append(_ws(node))
        elif node.tag == "br":
            out.append("\n")
        else:
            out.append(_inline_plain(node.children))
    return "".join(out)


def _blocks_plain(nodes):
    blocks, run = [], []

    def paragraph(items):
        text = "\n".join(line.strip() for line in _inline_plain(items).strip().split("\n"))
        if text:
            blocks.append(text)

    for node in nodes:
        if not _is_block(node):
            run.append(node)
            continue
        paragraph(run)
        run.clear()
        if node.tag in ("ul", "ol"):
            lines = []
            for child in _list_items(node):
                text = "\n".join(_blocks_plain(child.children)).strip()
                if text:
                    marker = f"{len(lines) + 1}. " if node.tag == "ol" else "- "
                    lines.append(marker + text.replace("\n", "\n" + " " * len(marker)))
            blocks.append("\n".join(lines))
        elif node.tag == "blockquote":
            inner = "\n\n".join(_blocks_plain(node.children))
            blocks.append("\n".join(("> " + line) if line else ">" for line in inner.split("\n")))
        elif node.tag == "p":
            blocks.extend(_blocks_plain(node.children))
        else:
            paragraph(node.children)
    paragraph(run)
    return [block for block in blocks if block]


def to_plain(clean_html):
    """정화된 HTML 의 글자만 평문으로(소제목은 줄, 목록은 `- `·`1. `, 문단 사이는 빈 줄). 멘션·참조는 푼다."""
    return neutralize(clean("\n\n".join(_blocks_plain(_tree(clean_html))), multiline=True))


# ----------------------------------------------------------------------------
# 본문 조립
# ----------------------------------------------------------------------------
def make_draft_id(blog_key, date, title, html):
    """숨은 표지의 초안 번호: <블로그키>-<날짜>-<해시>. 해시는 제목·본문(정화 뒤)에서 만든다 — 같은 글을 다시 올리면 같은 번호다."""
    digest = hashlib.sha256((clean(title) + "\n" + html).encode("utf-8")).hexdigest()[:12]
    return f"{blog_key}-{date}-{digest}"


def issue_title(channel_label, title):
    """`[초안][<채널>] <글 제목 60자>`. 접두사는 고정값이고, 글 제목은 태그·제어 문자를 지우고 한 줄로 접어 멘션·참조를 풀고 자른다."""
    text = neutralize(plain_title(title))
    if len(text) > TITLE_SHOWN:
        text = text[:TITLE_SHOWN - 1].rstrip() + "…"
    return f"[{DRAFT_LABEL}][{channel_label}] {text}"


def _images_section(images, info):
    rows, notes = [], []
    for item in list(images or [])[:IMAGES_MAX]:
        url = safe_url(item.get("url")) if isinstance(item, dict) else ""
        if not url:
            continue
        ai = {True: "예", False: "아니오"}.get(item.get("ai_generated"), "확인 필요")
        source, author = clean(item.get("source") or ""), clean(item.get("author") or "")
        shown = f"{source} — {author}" if source and author else (source or author or "출처 확인 필요")
        rows.append((len(rows) + 1, md_inline(item.get("purpose") or "-"), f"`{url}`", md_inline(shown),
                     md_inline(clean(item.get("license") or "") or "확인 필요"), ai))
        if source.lower() == "unsplash":
            author_url = safe_url(item.get("author_url"), _UNSPLASH_RX)
            if author and author_url:
                who = f"[{md_inline(author)}]({author_url}{'&' if '?' in author_url else '?'}{UNSPLASH_UTM})"
            else:
                who = md_inline(author or "작가")
            notes.append(f"{len(rows)}번: Photo by {who} on [Unsplash](https://unsplash.com/?{UNSPLASH_UTM})")
    lines = []
    if not rows:
        lines.append("이 초안에는 자동으로 고른 이미지가 없습니다. 대표 이미지는 직접 올리세요 — 직접 찍은 사진이나 사용 권한이 있는 이미지만 쓰고, "
                     "출처·라이선스·AI로 만든 이미지인지를 기록해 두세요.")
    else:
        lines += ["| 번호 | 용도 | 주소 | 출처 | 라이선스 | AI 생성 이미지 |", "|---|---|---|---|---|---|"]
        lines += [f"| {n} | {purpose} | {url} | {source} | {lic} | {ai} |" for n, purpose, url, source, lic, ai in rows]
        if notes:
            lines += ["", "**Unsplash 이미지는 글 아래에 작가와 Unsplash 링크를 표기해야 합니다.** 붙여넣을 문구:"] + [f"- {note}" for note in notes]
    if info["format"] == "html":
        lines += ["", "외부 링크 이미지는 본문에는 보여도 목록 썸네일에는 나오지 않습니다(티스토리 공식 FAQ). **대표 이미지 1장은 직접 업로드하세요.**"]
    else:
        lines += ["", "네이버가 외부 주소 이미지를 어떻게 보여 주는지는 확인되지 않았습니다(미확인) — 이미지는 올려서 쓰세요."]
    return lines


def _sources_section(sources):
    rows = []
    for item in list(sources or [])[:SOURCES_MAX]:
        url = safe_url(item.get("url")) if isinstance(item, dict) else ""
        if url:
            rows.append(f"- [{md_inline(item.get('title') or '') or url}]({url})")
    if rows:
        return rows
    return ["이 초안에는 자동으로 모은 출처가 없습니다. 사실·수치·고유명사가 있으면 공식 자료로 직접 확인하고, 필요하면 출처를 글에 적으세요."]


def _span(low, high):
    return f"(기준 {low}~{high}자)" if isinstance(low, int) and isinstance(high, int) else ""


def _gate_section(gate):
    gate = gate if isinstance(gate, dict) else {}
    attempts = gate.get("attempts")
    if isinstance(attempts, int) and attempts >= 1:
        lines = [f"- 결과: **통과**(재작성 {attempts - 1}회, 시도 {attempts}번째에 통과)"]
    else:
        lines = ["- 결과: **통과**"]
    if gate.get("model"):
        lines.append(f"- 모델: {md_inline(str(gate['model'])[:60])}")
    sizes = []
    if isinstance(gate.get("chars"), int):
        sizes.append(f"본문 {gate['chars']}자{_span(gate.get('min_chars'), gate.get('max_chars'))}")
    if isinstance(gate.get("title_chars"), int):
        sizes.append(f"제목 {gate['title_chars']}자{_span(gate.get('title_min'), gate.get('title_max'))}")
    if sizes:
        lines.append("- 분량: " + " · ".join(sizes))
    lines.append("- 점검한 것: 제목·본문 길이, 글 언어, 소제목·목록 구조, 금지 표현·금지 주제 낱말, 프롬프트 유출 문구, 라벨, "
                 "이 블로그·다른 블로그와의 제목 중복, HTML 정화")
    removed = gate.get("removed") if isinstance(gate.get("removed"), dict) else {}
    parts = [f"{md_inline(REMOVED_TEXT.get(str(key), str(key)))} {value}건" for key, value in removed.items()
             if isinstance(value, int) and not isinstance(value, bool) and value]
    lines.append("- 정화로 제거된 것: " + (", ".join(parts) if parts else "없음"))
    for warning in list(gate.get("warnings") or [])[:NOTES_MAX]:
        lines.append(f"- 참고: {md_inline(str(warning)[:300])}")
    lines.append("- **사실 확인은 하지 않았습니다.** 게이트는 길이·표현·주제·중복만 봅니다. 사실·수치는 발행 전에 직접 확인하세요.")
    return lines


def _checklist(info):
    html = info["format"] == "html"
    return [
        "- [ ] 제목 붙여넣기",
        "- [ ] HTML 모드로 본문 붙여넣기" if html else "- [ ] 서식 있는 글을 복사해 스마트에디터에 붙여넣기(서식이 깨지면 평문을 쓰고 직접 꾸미기)",
        "- [ ] 대표 이미지 업로드(외부 링크 이미지는 목록 썸네일에 안 나온다)" if html else "- [ ] 대표 이미지 업로드",
        "- [ ] 카테고리·홈주제 선택" if html else "- [ ] 카테고리 선택",
        "- [ ] 태그 붙여넣기",
        "- [ ] 직접 경험·판단 문단을 더했다(AI 글을 그대로 올리지 않는다)",
        "- [ ] 광고·협찬 표기 필요 여부 확인",
        "- [ ] 발행 후 주소 기록하고 이 이슈 닫기",
    ]


def _tags_text(tags):
    seen, out = set(), []
    for tag in list(tags or []):
        text = " ".join(re.sub(r"[#,，、]+", " ", clean(tag)).split())
        if text and text.lower() not in seen:
            seen.add(text.lower())
            out.append(text)
    return neutralize(", ".join(out[:TAGS_MAX]))


def _validate(draft):
    info = PACKAGE_INFO.get(draft.platform)
    if info is None:
        raise PublishError(f"초안 패키지를 지원하지 않는 platform 입니다: {str(draft.platform)[:20]!r}", code="bad_response")
    if draft.channel_label != info["label"]:
        raise PublishError(f"채널 라벨이 platform 과 맞지 않습니다({str(draft.channel_label)[:20]!r} ≠ {info['label']!r})", code="bad_response")
    if not _KEY_RX.match(str(draft.blog_key or "")) or not _DATE_RX.match(str(draft.date or "")):
        raise PublishError("블로그 key 또는 날짜 모양이 올바르지 않습니다", code="bad_response")
    return info


def _compose(draft, info, level, title_text, html, draft_id):
    """level 0 = 전부, 1 = 네이버 평문 상자를 줄임, 2 = 이미지·출처·게이트 설명도 한 줄로 줄임. 복사 상자(제목·본문·태그)는 어느 단계에서도 그대로다."""
    service = info["service"]
    out = [f"<!-- draft-id: {draft_id} -->",
           f"> **AI가 만든 초안입니다. 아직 {service}에 공개되지 않았습니다.** 아래 상자를 복사해 {service}에 직접 발행하세요. "
           "발행 전에 글을 읽고 사실·수치를 확인하고, 직접 겪은 일과 판단을 더하세요. 이 초안은 자동으로 올라가지 않습니다.",
           "",
           f"- 채널: {draft.channel_label} (`{draft.blog_key}`)",
           f"- 만든 날: {draft.date}(KST)",
           f"- 초안 번호: `{draft_id}`"]
    run_url = safe_url(draft.run_url, _RUN_URL_RX)
    if run_url:
        out.append(f"- 만든 실행: [Actions 실행]({run_url})")
    number = [0]

    def heading(text):
        number[0] += 1
        out.extend(["", f"## {number[0]}. {text}", ""])

    heading("복사용 제목")
    out.append(fence(neutralize(title_text[:COPY_TITLE_MAX]), "text"))
    if info["format"] == "html":
        heading("본문 — HTML 모드에 붙여넣기")
        out.append(f"{service} 글쓰기 화면(PC 웹)에서 편집기 모드를 **HTML**로 바꾼 뒤 아래 상자를 복사해 붙여넣으세요. 모바일 앱 편집기에는 HTML 모드가 없습니다. "
                   "붙여넣은 뒤 미리보기로 서식을 확인하세요(모드를 바꾸면 서식이 달라질 수 있습니다).")
        out.extend(["", fence(neutralize(html), "html")])
    else:
        heading("본문 — 서식 있는 글(이 화면에서 복사)")
        out.append("아래 두 가로줄 사이의 글을 끝까지 선택해 복사한 뒤 네이버 스마트에디터에 붙여넣으세요. 소제목·목록·굵게가 어떻게 붙는지는 확인되지 않았으니(미확인) "
                   "첫 글은 비공개로 시험하세요.")
        out.extend(["", "---", "", to_markdown(html), "", "---"])
        heading("본문 — 평문(서식이 깨질 때)")
        if level == 0:
            out.extend(["서식 있는 글이 제대로 붙지 않으면 이 평문을 붙여넣고 소제목·목록은 직접 꾸미세요.", "", fence(to_plain(html), "text")])
        else:
            out.append("이슈 본문 한도 때문에 평문 상자를 생략했습니다. 위 서식 있는 글을 복사하세요.")
    heading("해시태그(쉼표로 구분, # 없음)")
    tags = _tags_text(draft.tags)
    out.append(fence(tags, "text") if tags else "글에 라벨이 없습니다. 직접 고르세요.")
    heading("이미지")
    out.extend(_images_section(draft.images, info) if level < 2 else ["이미지 표는 이슈 본문 한도 때문에 생략했습니다. 대표 이미지는 직접 올리세요."])
    heading("근거 출처")
    out.extend(_sources_section(draft.sources) if level < 2 else ["출처 목록은 이슈 본문 한도 때문에 생략했습니다."])
    heading("게이트 점검 결과")
    out.extend(_gate_section(draft.gate) if level < 2 else ["- 결과: **통과**(자세한 내용은 이슈 본문 한도 때문에 생략했습니다)"])
    heading("발행 체크리스트")
    out.extend(_checklist(info))
    out.extend(["", f"발행하면 주소를 이 이슈에 코멘트로 남기고 이슈를 닫으세요(닫으면 발행 완료로 봅니다). 쓰지 않을 초안은 라벨 `{DISCARD_LABEL}`를 붙이거나 닫으세요. "
                f"같은 채널에 열린 초안({DISCARD_LABEL} 라벨이 붙은 것은 제외)이 {OPEN_DRAFT_LIMIT}건 이상이면 새 초안은 만들어지지 않습니다."])
    return "\n".join(out) + "\n"


def build_issue(draft):
    """초안 한 건 → IssueSpec(제목·본문·라벨·초안 번호). 입출력이 없다. 본문이 이슈 한도(안전 여유 포함)에 안 들어가면 PublishError(too_long)."""
    info = _validate(draft)
    title_text = plain_title(draft.title)
    if not title_text:
        raise PublishError("글 제목이 비어 있습니다", code="bad_response")
    html, _stats = gates.sanitize_html(draft.html, allow_links=bool(draft.allow_links))
    if not html.strip():
        raise PublishError("정화한 뒤 본문이 비어 있습니다", code="bad_response")
    draft_id = make_draft_id(draft.blog_key, draft.date, title_text, html)
    body = ""
    for level in (0, 1, 2):
        body = _compose(draft, info, level, title_text, html, draft_id)
        if len(body) <= BODY_BUDGET:
            break
    else:
        raise PublishError(f"초안이 이슈 본문 한도에 들어가지 않습니다({len(body)}자 > 안전 한도 {BODY_BUDGET}자, GitHub 한도 {BODY_LIMIT}자). "
                           "잘라서 올리면 글이 도중에 끊긴 채 발행될 수 있어 만들지 않습니다 — 프로필의 length.max_chars 를 줄이세요", code="too_long")
    return IssueSpec(title=issue_title(info["label"], title_text), body=body,
                     labels=[DRAFT_LABEL, CHANNEL_LABEL_PREFIX + info["label"]], draft_id=draft_id, channel_label=info["label"])


# ----------------------------------------------------------------------------
# 입출력: GitHub REST
# ----------------------------------------------------------------------------
_TRANSIENT = {429, 500, 502, 503, 504}


def _http_detail(exc):
    try:
        data = json.loads(exc.read().decode("utf-8", "replace"))
        return str(data.get("message") or "") if isinstance(data, dict) else ""
    except (OSError, ValueError, AttributeError):
        return ""


def _has_label(item, name):
    """GitHub 이슈 항목에 그 이름의 라벨이 붙어 있는지(라벨은 {"name": …} 객체 목록이다)."""
    return any((label.get("name") if isinstance(label, dict) else label) == name for label in item.get("labels") or ())


def _failure(message, code, status=None):
    exc = PublishError(message, code=code)
    exc.status = status        # HTTP 상태(연결 오류 등 응답이 없으면 None). 러너는 쓰지 않고 이 어댑터가 422(이미 있는 라벨)를 가를 때 쓴다
    return exc


class IssuePackagePublisher:
    """초안 패키지를 GitHub 이슈로 만든다. repo 는 `소유자/이름`, token 은 GITHUB_TOKEN(권한: issues write)."""

    def __init__(self, repo, token, opener=None, sleep=time.sleep, retries=2):
        self.repo = str(repo or "").strip()
        self._token = str(token or "").strip()
        self._open = opener or urllib.request.urlopen
        self._sleep = sleep
        self._retries = retries
        self.notes = []   # 실패하지 않았지만 운영자가 알아야 할 일(예: 같은 표지의 이슈가 이미 있어 새로 만들지 않음). 러너가 [참고] 줄로 찍는다
        self.calls = 0

    def _scrub(self, text):
        return redact(text, (self._token,))

    def _request(self, method, path, params=None, payload=None, allow_404=False, retry=True):
        """GitHub REST 한 번 호출. 일시 오류(429·5xx·연결 오류)는 늘려 가며 재시도하고(retry), 실패는 PublishError 로 분류한다.
        auth_failed 401·403·404·410(권한·저장소·이슈 기능) / network 연결 실패 / bad_response 응답 이상 / api_error 그 밖.
        retry=False 는 되풀이하면 안 되는 호출(이슈 만들기)용이다: 서버가 이미 만들었는데 응답만 잃은 것일 수 있어 같은 요청을 그대로 다시 보내면
        글이 둘이 된다. 그 재시도는 호출한 쪽이 같은 표지가 있는지 확인한 뒤에 한다."""
        if not _REPO_RX.match(self.repo):
            raise _failure("저장소 이름(GITHUB_REPOSITORY)이 `소유자/이름` 모양이 아닙니다", "auth_failed")
        url = f"{API_ROOT}/repos/{self.repo}{path}" + (("?" + urllib.parse.urlencode(params)) if params else "")
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28",
                   "User-Agent": "chanceblog-package", "Authorization": f"Bearer {self._token}"}
        data = None
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        attempts = self._retries if retry else 0
        for attempt in range(attempts + 1):
            self.calls += 1
            request = urllib.request.Request(url, data=data, method=method, headers=headers)
            try:
                with self._open(request, timeout=20) as resp:
                    body = resp.read().decode("utf-8")
            except urllib.error.HTTPError as exc:
                status, detail = exc.code, self._scrub(" ".join(_http_detail(exc).split()))[:160]
                hdrs = getattr(exc, "headers", None)
                limited = hdrs is not None and hdrs.get("x-ratelimit-remaining") == "0"
                if status == 404 and allow_404:
                    return None
                if status in _TRANSIENT or (status == 403 and (limited or "rate limit" in detail.lower())):
                    if attempt < attempts:
                        self._sleep(3 * (2 ** attempt))
                        continue
                    raise _failure(f"GitHub API 호출 한도·서버 오류(status={status}): {detail}", "api_error", status) from None
                if status in (401, 403, 404, 410):
                    raise _failure(f"GitHub 권한·저장소 접근 오류(status={status}): {detail}", "auth_failed", status) from None
                raise _failure(f"GitHub API 오류(status={status}): {detail}", "api_error", status) from None
            except (urllib.error.URLError, http.client.HTTPException, OSError, UnicodeDecodeError) as exc:
                if attempt < attempts:
                    self._sleep(3 * (2 ** attempt))
                    continue
                raise _failure(f"GitHub 서버에 연결하지 못했습니다: {type(exc).__name__}: {self._scrub(' '.join(str(exc).split()))[:120]}",
                               "network") from None
            if not body:
                return None
            try:
                return json.loads(body)
            except ValueError:
                raise _failure("GitHub 응답이 JSON 이 아닙니다", "bad_response") from None
        raise _failure("GitHub API 호출 재시도 초과", "api_error")

    def _issues(self, labels, state, **extra):
        """라벨이 모두 붙은 이슈 목록(풀 리퀘스트 제외). 쪽마다 100건, SEARCH_PAGES 쪽까지."""
        found = []
        for page in range(1, SEARCH_PAGES + 1):
            params = {"labels": ",".join(labels), "state": state, "per_page": 100, "page": page, "sort": "created", "direction": "desc", **extra}
            items = self._request("GET", "/issues", params=params)
            if not isinstance(items, list):
                raise _failure("이슈 목록 응답이 배열이 아닙니다", "bad_response")
            found += [item for item in items if isinstance(item, dict) and "pull_request" not in item]
            if len(items) < 100:
                break
        return found

    def count_open_drafts(self, channel_label):
        """같은 채널에 열려 있는 초안 이슈 수(적체 점검). 라벨 `폐기`가 붙은 것은 쓰지 않기로 한 초안이라 세지 않는다(확인 필요 모음의 현황판과 같은 규칙:
        폐기 = 라벨 `폐기` 또는 닫기). 읽기만 한다."""
        items = self._issues([DRAFT_LABEL, CHANNEL_LABEL_PREFIX + channel_label], "open")
        return sum(1 for item in items if not _has_label(item, DISCARD_LABEL))

    def ensure_labels(self, labels):
        """라벨이 없으면 만든다(있으면 그대로). 같은 이름을 동시에 만들어 422 가 나면 이미 있는 것으로 본다."""
        for name in labels:
            color, description = LABEL_STYLE.get(name, ("ededed", "초안 패키지"))
            if self._request("GET", "/labels/" + urllib.parse.quote(name, safe=""), allow_404=True) is not None:
                continue
            try:
                self._request("POST", "/labels", payload={"name": name, "color": color, "description": description})
            except PublishError as exc:
                if getattr(exc, "status", None) != 422:
                    raise

    def find_existing(self, spec, date):
        """같은 표지(draft-id)를 본문 첫 줄에 가진 이슈(열림·닫힘 모두)를 찾는다. 본문 가운데 같은 글자가 있어도 첫 줄이 아니면 같은 이슈로 보지 않는다."""
        day = date_type.fromisoformat(date)
        since = (datetime(day.year, day.month, day.day, tzinfo=KST) - timedelta(days=1)).astimezone(timezone.utc)
        for item in self._issues(spec.labels, "all", since=since.strftime("%Y-%m-%dT%H:%M:%SZ")):
            match = _MARKER_RX.match(str(item.get("body") or ""))
            if match and match.group(1) == spec.draft_id:
                return item
        return None

    @staticmethod
    def _result(item):
        number, url = (item or {}).get("number"), str((item or {}).get("html_url") or "").strip()
        if isinstance(number, bool) or not isinstance(number, int) or number < 1 or not _ISSUE_URL_RX.match(url):
            raise _failure("이슈 응답에 번호나 주소가 없습니다(GitHub 이슈 목록에서 초안이 만들어졌는지 확인하세요)", "bad_response")
        return PublishResult(post_id=str(number), url=url, draft=True)

    def publish_package(self, draft):
        """초안 한 건을 이슈로 만든다(멱등). 같은 표지의 이슈가 있으면 만들지 않고 그 이슈를 돌려준다."""
        spec = build_issue(draft)
        existing = self.find_existing(spec, draft.date)
        if existing is not None:
            result = self._result(existing)
            self.notes.append(f"같은 초안 번호의 이슈 #{result.post_id} 가 이미 있어 새로 만들지 않았습니다")
            return result
        self.ensure_labels(spec.labels)
        payload = {"title": spec.title, "body": spec.body, "labels": spec.labels}
        for attempt in range(self._retries + 1):
            try:
                return self._result(self._request("POST", "/issues", payload=payload, retry=False))
            except PublishError as exc:
                if exc.code not in ("network", "api_error", "bad_response"):
                    raise
                # 서버는 이슈를 만들었는데 응답만 실패했을 수 있다: 다시 만들기 전에 같은 표지가 있는지 본다(확인에 실패하면 '없음'으로 보되 참고를 남긴다)
                try:
                    found = self.find_existing(spec, draft.date)
                except PublishError as check:
                    found = None
                    self.notes.append(f"만들기 실패 뒤 중복 확인에도 실패해 '없음'으로 봅니다({check.code})")
                if found is not None:
                    self.notes.append(f"만들기 응답은 실패했지만 이슈 #{found.get('number')} 가 이미 만들어져 있어 그것을 씁니다")
                    return self._result(found)
                if exc.code == "bad_response" or attempt >= self._retries:
                    raise      # 응답이 이상한 경우는 다시 만들지 않는다(이미 만들어졌을 수 있어 같은 글이 둘이 된다)
                self._sleep(3 * (2 ** attempt))
        raise _failure("초안 이슈 만들기 재시도 초과", "api_error")
