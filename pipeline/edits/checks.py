"""수정 후 사후 검증: LLM·사용자 입력이 무엇을 만들었든, 아래를 통과하지 못하면 파일을 쓰지 않는다.

1. 바뀐 파일은 허용 경로 안에 있고 절대 금지 경로가 아니다
2. 바뀐 파일 수·바뀐 줄 수·파일 크기 상한, 갑작스러운 축소 금지
3. 광고(AdSense) 스니펫 개수가 바뀌지 않는다(추가·삭제 모두 불가)
4. 위험한 마크업(script·iframe·이벤트 속성·javascript: 등)이 늘어나지 않는다
5. front matter 는 방식별로 허용된 범위만 바뀐다
6. 새 비밀 값이 들어가지 않는다, 새 http:// 링크가 들어가지 않는다
"""
import difflib
import html
import re

from pipeline.edits import frontmatter, spec as spec_mod
from pipeline.secret_patterns import find_secrets

AD_PATTERNS = [re.compile(p, re.IGNORECASE) for p in (r"adsbygoogle", r"googlesyndication", r"ca-pub-\d+")]
# 엔티티를 풀고 제어 문자를 공백으로 바꾼 텍스트에서 센다(&#106;avascript:, 속성 안의 개행 등으로 숨긴 것을 드러낸다)
DANGEROUS = [
    ("<script", re.compile(r"<\s*script\b", re.I)),
    ("<iframe", re.compile(r"<\s*iframe\b", re.I)),
    ("<object/<embed", re.compile(r"<\s*(?:object|embed|applet)\b", re.I)),
    ("<form", re.compile(r"<\s*form\b", re.I)),
    ("<style/<link/<base/<meta", re.compile(r"<\s*(?:style|link|base|meta)\b", re.I)),
    ("<svg/<math/<frame", re.compile(r"<\s*(?:svg|math|frame|frameset)\b", re.I)),
    ("javascript:", re.compile(r"javascript\s*:", re.I)),
    ("이벤트 핸들러 속성(on…=)", re.compile(r"""[\s"'/]on[a-z]{3,}\s*=""", re.I)),
]
# 공백까지 지운 소문자 텍스트에서 센다(java<개행>script: 같은 분할 표기)
COMPACT_DANGEROUS = [
    ("javascript:/vbscript: 주소", re.compile(r"(?:javascript|vbscript):")),
    ("data: 주소", re.compile(r"""(?:href|src|action|formaction|srcdoc|poster|background)=["']?data:|\]\(data:""")),
]
LIQUID = re.compile(r"\{%|\{\{")
_AD_BLOCK = re.compile(r"(?is)<\s*script\b.*?(?:<\s*/\s*script\s*>|\Z)|<\s*ins\b[^>]*>")
_EXTERNAL_HOST = re.compile(r"""(?i)\bhttps?://([^/\s)"'<>?#:\\]+)""")
_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f​-‏  ﻿]")
_HTTP_LINK = re.compile(r"""\bhttp://[^\s)"'<>]+""", re.I)
MIN_SHRINK_BASE = 500
AI_MIN_LINES, AI_MAX_RATIO = 12, 0.3   # AI 패치는 작은 파일에서도 '일부'만 바꿔야 한다(절대 한도 80줄은 작은 페이지에서 무의미)

# 게시글 대표 이미지로 허용하는 주소: 호스트는 아래뿐이다(호스트를 늘리는 것은 자동 수정 범위 확대이므로 T3).
IMAGE_HOSTS = ("images.unsplash.com",)
# `https://<호스트>/photo-<id>` + 선택적 질의(영숫자 _ . = & - 와 %XX 만). userinfo(@)·포트·프래그먼트·경로 추가·따옴표·괄호·공백·개행은 모두 불일치
_IMAGE_URL = re.compile(r"https://(?P<host>[a-z0-9.\-]+)/photo-[A-Za-z0-9_\-]{1,64}"
                        r"(?:\?(?:[A-Za-z0-9_.=&\-]|%[0-9A-Fa-f]{2}){1,300})?")
_IMAGE_LINE = re.compile(r"image\s*:")


def _decode(text):
    """엔티티를 반복해서 풀고 제어·보이지 않는 문자를 공백으로 바꾼다."""
    for _ in range(3):
        step = html.unescape(text)
        if step == text:
            break
        text = step
    return _CONTROL.sub(" ", text)


def _compact(text):
    return re.sub(r"\s+", "", _decode(text)).lower()


def _ad_blocks(text):
    """페이지 안의 <script> 블록과 <ins> 태그 전체(공백 정규화). 하나라도 달라지면 광고·스크립트가 바뀐 것이다."""
    return sorted(re.sub(r"\s+", " ", m.group(0)).strip() for m in _AD_BLOCK.finditer(text))


def _hosts(text):
    return {h.lower() for h in _EXTERNAL_HOST.findall(_decode(text))}


def _safe(text, limit=60):
    """사유 문장에 들어갈 신뢰할 수 없는 문자열: 한 줄로 접고 자른다."""
    return re.sub(r"\s+", " ", str(text)).strip()[:limit]


def changed_line_count(before, after):
    diff = difflib.unified_diff(before.splitlines(), after.splitlines(), lineterm="", n=0)
    return sum(1 for line in diff if line[:1] in "+-" and not line.startswith(("+++", "---")))


def unified_diff(before, after, path, max_lines=60):
    lines = list(difflib.unified_diff(before.splitlines(), after.splitlines(), f"a/{path}", f"b/{path}", lineterm="", n=2))
    if len(lines) > max_lines:
        lines = lines[:max_lines] + [f"... (이하 {len(lines) - max_lines}줄 생략)"]
    return "\n".join(lines)


def _front_matter_reasons(path, before, after, mode, only_fields):
    fm_b, body_b = frontmatter.split_front_matter(before)
    fm_a, body_a = frontmatter.split_front_matter(after)
    if fm_b is None:
        return [f"{path}: front matter 가 없던 파일에 front matter 를 추가할 수 없습니다."] if fm_a is not None else []
    if fm_a is None:
        return [f"{path}: front matter 가 사라졌습니다."]
    if mode == "body":
        return [] if fm_a == fm_b else [f"{path}: front matter 가 바뀌었습니다(이 수정 항목은 본문만 바꿀 수 있습니다)."]
    dict_b, dict_a = frontmatter.parse_front_matter(fm_b), frontmatter.parse_front_matter(fm_a)
    if dict_b is None or dict_a is None:
        return [f"{path}: front matter 를 해석할 수 없습니다."]
    allowed = set(only_fields or [])
    changed = {str(k) for k in set(dict_b) | set(dict_a) if dict_b.get(k) != dict_a.get(k)}
    reasons = []
    if changed - allowed:
        reasons.append(f"{path}: 허용되지 않은 front matter 항목이 바뀌었습니다: {', '.join(_safe(k, 40) for k in sorted(changed - allowed))}")
    if mode == "front_matter" and body_a != body_b:
        reasons.append(f"{path}: 본문이 바뀌었습니다(이 수정 항목은 front matter 필드만 바꿀 수 있습니다).")
    return reasons


def image_url_problem(url):
    """게시글 대표 이미지로 허용되는 주소인지. None(허용) 또는 거부 사유. 주소 값은 사유에 쓰지 않는다(공개 코멘트에 되풀이 방지)."""
    match = _IMAGE_URL.fullmatch(url) if isinstance(url, str) else None
    if not match:
        return "이미지 주소가 허용된 형식(https://images.unsplash.com/photo-… 와 영숫자·=&.-_ 질의)이 아닙니다"
    if match.group("host") not in IMAGE_HOSTS:
        return f"허용되지 않은 이미지 호스트입니다(허용: {', '.join(IMAGE_HOSTS)})"
    return None


def is_safe_image_url(url):
    return image_url_problem(url) is None


def front_matter_image(text):
    """front matter 의 image 값(문자열, 없으면 '')과 front matter dict. front matter 를 해석할 수 없으면 (None, None)."""
    fm_text, _body = frontmatter.split_front_matter(text)
    data = frontmatter.parse_front_matter(fm_text) if fm_text is not None else None
    if data is None:
        return None, None
    value = data.get("image")
    return ("" if value is None else str(value)), data


def _without_image_line(text):
    fm_text, body = frontmatter.split_front_matter(text)
    return "\n".join(ln for ln in fm_text.split("\n") if not _IMAGE_LINE.match(ln)) + "\0" + body


def verify_image_change(before, after):
    """게시글 이미지 변경이 '대표 이미지 주소'만 바꿨는지 확인한다. 거부 사유 목록(비어 있으면 통과).

    생성 직후 검증(runner)과 PR 범위 검사(scope_check)가 같은 함수를 쓴다. 통과 조건:
    1. 새 front matter image 가 허용 형식·허용 호스트의 주소다(값은 사유에 되풀이하지 않는다)
    2. 이전 주소가 있었다면, 그것을 새 주소로 바꾼 것 말고는 본문·다른 줄이 한 글자도 다르지 않다(주소를 자리표시자로 바꿔 비교)
    3. 이미지가 없던 글에 이미지가 추가된 경우에는 front matter 의 image 줄만 늘어난 것이다
    """
    old_url, old_fm = front_matter_image(before)
    new_url, new_fm = front_matter_image(after)
    if old_fm is None or new_fm is None:
        return ["front matter 를 해석할 수 없어 이미지 변경을 확인할 수 없습니다."]
    problem = image_url_problem(new_url)
    if problem:
        return [f"새 대표 이미지: {problem}."]
    if new_url == old_url:
        return ["대표 이미지 주소가 바뀌지 않았습니다."]
    reasons = []
    if sum(1 for ln in frontmatter.split_front_matter(after)[0].split("\n") if _IMAGE_LINE.match(ln)) > 1:
        reasons.append("front matter 에 image 줄이 둘 이상입니다.")
    if old_url:
        marker = "\0IMAGE-URL\0"
        while marker in before or marker in after:   # 본문에 자리표시자와 같은 문자열이 있어도 속지 않는다
            marker += "\0"
        same = before.replace(old_url, marker) == after.replace(new_url, marker)
    else:
        same = _without_image_line(before) == _without_image_line(after)
    if not same:
        reasons.append("대표 이미지 주소 외의 내용(본문·다른 front matter)이 바뀌었습니다. 이미지 변경은 주소만 바꿀 수 있습니다.")
    return reasons


def verify_changes(changes, allowed_patterns, limits, mode="body", only_fields=None, ai_patch=False):
    """changes: {경로: (이전 텍스트, 새 텍스트)}. 거부 사유 목록(비어 있으면 통과).

    mode: body(본문만) · front_matter(only_fields 만) · image(front matter 의 image 만 + 본문 이미지 URL)
    ai_patch: AI 가 쓴 변경이면 True — 새 외부 링크를 금지하고 바뀐 비율을 더 엄격히 제한한다
    """
    reasons = []
    if not changes:
        return ["변경된 파일이 없습니다."]
    if len(changes) > limits["max_changed_files"]:
        reasons.append(f"바뀐 파일이 너무 많습니다({len(changes)}개 > {limits['max_changed_files']}개).")
    for path, (before, after) in changes.items():
        if not spec_mod.path_allowed(path, allowed_patterns):
            reasons.append(f"{path}: 이 수정 항목이 허용하지 않는 경로입니다.")
            continue
        if before == after:
            reasons.append(f"{path}: 바뀐 내용이 없습니다.")
            continue
        if len(after) > limits["max_file_chars"]:
            reasons.append(f"{path}: 파일이 너무 큽니다({len(after)}자 > {limits['max_file_chars']}자).")
            continue  # 큰 입력에 정규식 검사를 돌리지 않는다(검사 지연 방지)
        if len(before) >= MIN_SHRINK_BASE and len(after) < len(before) * 0.5:
            reasons.append(f"{path}: 수정 후 파일이 절반 이하로 줄었습니다.")
        lines = changed_line_count(before, after)
        if lines > limits["max_changed_lines"]:
            reasons.append(f"{path}: 바뀐 줄이 너무 많습니다({lines}줄 > {limits['max_changed_lines']}줄). 요청을 더 작게 나눠 주세요.")
        if ai_patch:
            cap = max(AI_MIN_LINES, int(max(len(before.splitlines()), 1) * AI_MAX_RATIO))
            if lines > cap:
                reasons.append(f"{path}: AI 수정이 파일의 큰 부분을 바꿉니다({lines}줄 > {cap}줄). 요청을 더 작게 나눠 주세요.")
            new_hosts = _hosts(after) - _hosts(before)
            if new_hosts:
                reasons.append(f"{path}: AI 수정은 새 외부 링크를 넣을 수 없습니다({sorted(new_hosts)[0]}).")
        for rx in AD_PATTERNS:
            if len(rx.findall(before)) != len(rx.findall(after)):
                reasons.append(f"{path}: 광고 코드({rx.pattern})가 추가되거나 삭제됩니다. 광고 표면은 이 경로로 바꿀 수 없습니다.")
        if _ad_blocks(before) != _ad_blocks(after):
            reasons.append(f"{path}: 페이지 안의 <script>·<ins> 블록이 바뀝니다(광고 ID·주소·본문 포함). 이 경로로 바꿀 수 없습니다.")
        if len(LIQUID.findall(after)) > len(LIQUID.findall(before)):
            reasons.append(f"{path}: Liquid 태그({{% … %}}·{{{{ … }}}})가 새로 들어갑니다. 템플릿 코드는 이 경로로 넣을 수 없습니다.")
        dec_before, dec_after = _decode(before), _decode(after)
        for name, rx in DANGEROUS:
            if len(rx.findall(dec_after)) > len(rx.findall(dec_before)):
                reasons.append(f"{path}: 위험한 마크업({name})이 새로 들어갑니다.")
        cmp_before, cmp_after = _compact(before), _compact(after)
        for name, rx in COMPACT_DANGEROUS:
            if len(rx.findall(cmp_after)) > len(rx.findall(cmp_before)):
                reasons.append(f"{path}: 위험한 마크업({name})이 새로 들어갑니다.")
        known = {label for label, _ in find_secrets(before)}
        for label, preview in find_secrets(after):
            if label not in known:
                reasons.append(f"{path}: 비밀 값으로 보이는 문자열({label}, {preview})이 들어갑니다.")
        new_http = set(_HTTP_LINK.findall(after)) - set(_HTTP_LINK.findall(before))
        if new_http:
            reasons.append(f"{path}: 암호화되지 않은 http:// 링크가 새로 들어갑니다: {sorted(new_http)[0]}")
        fm_mode = "body" if mode == "body" else mode
        fm_only = ["image"] if mode == "image" else only_fields
        if mode == "image":
            reasons += _front_matter_reasons(path, before, after, "image", fm_only)
        else:
            reasons += _front_matter_reasons(path, before, after, fm_mode, fm_only)
    return reasons
