"""생성물 게이트: 파싱 → HTML 정화 → 정책·중복 검사.

원칙(fail closed): LLM 출력은 '데이터'이지 명령이 아니다. 형식이 맞지 않거나 하나라도 규칙을
어기면 게시하지 않고 사유를 남긴다. 이 모듈은 네트워크·파일 I/O가 없는 순수 함수만 둔다.
설명: docs/SECURITY_GUARDRAILS.md (G-L*, G-C*)
"""
import html as html_lib
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from html.parser import HTMLParser
from urllib.parse import urlsplit


class GateError(ValueError):
    """생성물을 형식대로 파싱할 수 없을 때(제목/라벨/내용 누락 등)."""


@dataclass
class GateResult:
    ok: bool
    reasons: list = field(default_factory=list)   # 게시를 막는 사유. "[코드] 설명" 형식
    warnings: list = field(default_factory=list)  # 참고 사항(게시는 막지 않음)

    def codes(self):
        return [r.split("]", 1)[0].lstrip("[") for r in self.reasons if r.startswith("[")]


# ----------------------------------------------------------------------------
# HTML 정화 (허용 목록 방식)
# ----------------------------------------------------------------------------
ALLOWED_TAGS = frozenset({"p", "h2", "h3", "h4", "ul", "ol", "li", "strong", "b", "em", "i", "br", "blockquote"})
VOID_TAGS = frozenset({"br"})
# 내용까지 통째로 버리는 태그(스크립트·임베드·폼 등)
DROP_WITH_CONTENT = frozenset({
    "script", "style", "iframe", "object", "embed", "form", "svg", "math", "noscript",
    "template", "head", "title", "textarea", "select", "button", "canvas", "audio", "video",
})


class _Sanitizer(HTMLParser):
    def __init__(self, allow_links=False, allowed_hosts=()):
        super().__init__(convert_charrefs=True)
        self.allow_links = allow_links
        self.allowed_hosts = tuple(h.lower() for h in allowed_hosts)
        self.out = []
        self.open_tags = []  # 실제로 출력한 열린 태그
        self.skip = []       # 내용째 버리는 태그 스택
        self.stats = {"dropped_blocks": 0, "unwrapped_tags": 0, "links_removed": 0}

    def _href_ok(self, href):
        href = (href or "").strip()
        if not href or re.search(r"[\s\x00-\x1f]", href):
            return False
        try:
            parts = urlsplit(href)
        except ValueError:
            return False
        if parts.scheme != "https" or not parts.netloc:
            return False
        host = (parts.hostname or "").lower()
        if self.allowed_hosts and not any(host == h or host.endswith("." + h) for h in self.allowed_hosts):
            return False
        return True

    def handle_starttag(self, tag, attrs):
        if self.skip:
            if tag in DROP_WITH_CONTENT:
                self.skip.append(tag)
            return
        if tag in DROP_WITH_CONTENT:
            self.skip.append(tag)
            self.stats["dropped_blocks"] += 1
            return
        if tag == "a":
            href = dict(attrs).get("href")
            if self.allow_links and self._href_ok(href):
                self.out.append('<a href="%s" rel="nofollow noopener">' % html_lib.escape(href.strip(), quote=True))
                self.open_tags.append("a")
            else:
                self.stats["links_removed"] += 1
            return
        if tag in ALLOWED_TAGS:
            self.out.append(f"<{tag}>")  # 속성은 전부 버린다
            if tag not in VOID_TAGS:
                self.open_tags.append(tag)
            return
        self.stats["unwrapped_tags"] += 1  # 모르는 태그는 벗기고 텍스트만 남긴다

    def handle_endtag(self, tag):
        if self.skip:
            if tag == self.skip[-1]:
                self.skip.pop()
            return
        if tag in VOID_TAGS:
            return
        if (tag == "a" or tag in ALLOWED_TAGS) and tag in self.open_tags:
            while self.open_tags:
                top = self.open_tags.pop()
                self.out.append(f"</{top}>")
                if top == tag:
                    break

    def handle_data(self, data):
        if not self.skip:
            self.out.append(html_lib.escape(data, quote=False))

    def handle_comment(self, data):
        pass

    def handle_decl(self, decl):
        pass

    def handle_pi(self, data):
        pass

    def unknown_decl(self, data):
        pass


def sanitize_html(raw_html, allow_links=False, allowed_hosts=()):
    """허용 태그만 남긴 안전한 HTML과 정화 통계를 돌려준다. 모든 속성은 제거된다(a[href] 예외)."""
    parser = _Sanitizer(allow_links=allow_links, allowed_hosts=allowed_hosts)
    parser.feed(raw_html or "")
    parser.close()
    while parser.open_tags:
        parser.out.append(f"</{parser.open_tags.pop()}>")
    return "".join(parser.out).strip(), parser.stats


def plain_text(clean_html):
    """정화된 HTML에서 텍스트를 뽑는다(블록 경계는 줄바꿈). 정화 이후에만 사용할 것."""
    s = re.sub(r"</?(?:p|h[2-4]|ul|ol|li|blockquote)\b[^>]*>|<br\s*/?>", "\n", clean_html or "", flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    s = html_lib.unescape(s)
    s = re.sub(r"[ \t\r\f\v\xa0]+", " ", s)
    s = re.sub(r"\s*\n\s*", "\n", s)
    return s.strip()


def text_length(text):
    return len(re.sub(r"\s+", " ", text or "").strip())


# ----------------------------------------------------------------------------
# 파싱
# ----------------------------------------------------------------------------
def strip_code_fences(text):
    text = re.sub(r"^\s*```[a-zA-Z0-9_-]*\s*\n", "", text or "")
    text = re.sub(r"\n\s*```\s*$", "", text)
    return text.replace("```html", "").replace("```", "")


def _clean_title(value):
    value = re.sub(r"[*_`#]+", "", value or "")
    return value.strip().strip("\"'“”‘’「」『』").strip()


def parse_labeled_post(raw):
    """'제목:/라벨:/내용:' 형식의 응답을 파싱한다. 하나라도 없으면 GateError(기본값으로 채우지 않는다)."""
    text = strip_code_fences(raw).strip()
    if not text:
        raise GateError("응답이 비어 있음")
    m_title = re.search(r"^\s*제목\s*:\s*(.+?)\s*$", text, re.M)
    m_labels = re.search(r"^\s*라벨\s*:\s*(.+?)\s*$", text, re.M)
    m_body = re.search(r"^\s*내용\s*:[ \t]*\n?([\s\S]+)$", text, re.M)
    missing = [name for name, m in (("제목", m_title), ("라벨", m_labels), ("내용", m_body)) if not m]
    if missing:
        raise GateError("형식 오류: 누락된 항목 " + ", ".join(missing))
    labels = []
    for item in re.split(r"[,，、#]+", m_labels.group(1)):
        item = item.strip()
        if item and item not in labels:
            labels.append(item)
    title = _clean_title(m_title.group(1))
    body = m_body.group(1).strip()
    if not title or not body:
        raise GateError("형식 오류: 제목 또는 내용이 비어 있음")
    return {"title": title, "labels": labels, "content": body}


# ----------------------------------------------------------------------------
# 유사도(중복 방지)
# ----------------------------------------------------------------------------
def norm_title(value):
    value = re.sub(r"[^\w\s]", " ", (value or "").casefold())
    return re.sub(r"\s+", " ", value).strip()


def similarity(a, b):
    na, nb = norm_title(a), norm_title(b)
    if not na or not nb:
        return 0.0
    return SequenceMatcher(None, na, nb).ratio()


def most_similar(text, candidates):
    """(점수, 후보). 후보가 없으면 (0.0, None)."""
    best_score, best = 0.0, None
    for cand in candidates:
        score = similarity(text, cand)
        if score > best_score:
            best_score, best = score, cand
    return best_score, best


# ----------------------------------------------------------------------------
# 정책·품질 검사
# ----------------------------------------------------------------------------
def _compiled(patterns):
    return [re.compile(p, re.IGNORECASE) for p in patterns or []]


def matches_any(patterns, text):
    """text에서 처음 맞는 패턴 문자열을 돌려준다(없으면 None)."""
    for raw, rx in zip(patterns or [], _compiled(patterns)):
        if rx.search(text or ""):
            return raw
    return None


def topic_allowed(topic, profile):
    """주제가 금지 주제 패턴에 걸리지 않으면 True."""
    return matches_any(profile.get("banned_topic_patterns"), topic) is None


def check_post(post, profile, recent_titles=(), other_titles=(), sanitize_stats=None):
    """정화된 post({title, labels, content})를 프로필 기준으로 검사한다."""
    reasons, warnings = [], []
    title = post.get("title", "")
    content = post.get("content", "")
    labels = post.get("labels", [])
    text = plain_text(content)
    n = text_length(text)

    t_cfg = profile.get("title", {})
    if not t_cfg.get("min_chars", 1) <= len(title) <= t_cfg.get("max_chars", 200):
        reasons.append(f"[TITLE_LEN] 제목 길이 {len(title)}자 (허용 {t_cfg.get('min_chars')}~{t_cfg.get('max_chars')}자)")
    hit = matches_any(profile.get("title_banned_patterns"), title)
    if hit:
        reasons.append(f"[TITLE_BANNED] 자극적/금지 제목 표현: {hit}")

    l_cfg = profile.get("length", {})
    if n < l_cfg.get("min_chars", 0):
        reasons.append(f"[LEN_SHORT] 본문 {n}자 (최소 {l_cfg['min_chars']}자)")
    if n > l_cfg.get("max_chars", 10 ** 9):
        reasons.append(f"[LEN_LONG] 본문 {n}자 (최대 {l_cfg['max_chars']}자)")

    if profile.get("language") == "ko":
        letters = re.findall(r"[A-Za-z가-힣]", text)
        hangul = re.findall(r"[가-힣]", text)
        ratio = (len(hangul) / len(letters)) if letters else 0.0
        if ratio < profile.get("min_hangul_ratio", 0.5):
            reasons.append(f"[LANG] 한글 비율 {ratio:.0%} (최소 {profile.get('min_hangul_ratio', 0.5):.0%})")

    s_cfg = profile.get("structure", {})
    h3_count = len(re.findall(r"<h[23]>", content))
    if h3_count < s_cfg.get("min_h3", 0):
        reasons.append(f"[STRUCT_H3] 소제목 {h3_count}개 (최소 {s_cfg['min_h3']}개)")
    if s_cfg.get("require_list") and not re.search(r"<(?:ul|ol)>", content):
        reasons.append("[STRUCT_LIST] 체크리스트/목록이 없음")

    hit = matches_any(profile.get("banned_patterns"), title + "\n" + text)
    if hit:
        reasons.append(f"[BANNED] 금지 표현(과장·의학적 단정): {hit}")
    hit = matches_any(profile.get("leak_patterns"), title + "\n" + text)
    if hit:
        reasons.append(f"[LEAK] 프롬프트/AI 메타 문구·마크다운 잔여물: {hit}")

    lab_cfg = profile.get("labels", {})
    if not lab_cfg.get("min", 1) <= len(labels) <= lab_cfg.get("max", 5):
        reasons.append(f"[LABELS] 라벨 {len(labels)}개 (허용 {lab_cfg.get('min', 1)}~{lab_cfg.get('max', 5)}개)")
    elif any(len(x) > lab_cfg.get("max_chars", 20) for x in labels):
        reasons.append("[LABELS] 너무 긴 라벨이 있음")
    if labels and not all(topic_allowed(x, profile) for x in labels):
        reasons.append("[LABELS] 금지 주제 라벨이 있음")

    sim = profile.get("similarity", {})
    score, other = most_similar(title, recent_titles)
    if score >= sim.get("same_blog", 1.1):
        reasons.append(f"[DUP_SAME] 이 블로그의 기존 글과 제목이 비슷함({score:.2f}): {other}")
    score, other = most_similar(title, other_titles)
    if score >= sim.get("other_blogs", 1.1):
        reasons.append(f"[DUP_OTHER] 다른 블로그 글과 제목이 비슷함({score:.2f}): {other}")

    if sanitize_stats:
        removed = {k: v for k, v in sanitize_stats.items() if v}
        if removed:
            warnings.append(f"[SANITIZED] HTML 정화로 제거됨: {removed}")
    return GateResult(ok=not reasons, reasons=reasons, warnings=warnings)


def append_disclosure(clean_html, profile):
    """프로필의 AI 사용·면책 문구를 본문 뒤에 붙인다(작성자가 빼먹을 수 없게 게시 직전에 붙인다)."""
    block = (profile.get("disclosure_html") or "").strip()
    return f"{clean_html}\n{block}" if block else clean_html
