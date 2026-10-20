"""수정 후 사후 검증: LLM·사용자 입력이 무엇을 만들었든, 아래를 통과하지 못하면 파일을 쓰지 않는다.

1. 바뀐 파일은 허용 경로 안에 있고 절대 금지 경로가 아니다
2. 바뀐 파일 수·바뀐 줄 수·파일 크기 상한, 갑작스러운 축소 금지
3. 광고(AdSense) 스니펫 개수가 바뀌지 않는다(추가·삭제 모두 불가)
4. 위험한 마크업(script·iframe·이벤트 속성·javascript: 등)이 늘어나지 않는다
5. front matter 는 방식별로 허용된 범위만 바뀐다
6. 새 비밀 값이 들어가지 않는다, 새 http:// 링크가 들어가지 않는다
"""
import difflib
import re

from pipeline.edits import frontmatter, spec as spec_mod
from pipeline.secret_patterns import find_secrets

AD_PATTERNS = [re.compile(p, re.IGNORECASE) for p in (r"adsbygoogle", r"googlesyndication", r"ca-pub-\d+")]
DANGEROUS = [
    ("<script", re.compile(r"<\s*script\b", re.I)),
    ("<iframe", re.compile(r"<\s*iframe\b", re.I)),
    ("<object/<embed", re.compile(r"<\s*(?:object|embed)\b", re.I)),
    ("<form", re.compile(r"<\s*form\b", re.I)),
    ("javascript:", re.compile(r"javascript\s*:", re.I)),
    ("이벤트 핸들러 속성(on…=)", re.compile(r"""[\s"'/]on[a-z]{3,}\s*=""", re.I)),
    ("meta refresh", re.compile(r"""<\s*meta[^>]+http-equiv\s*=\s*["']?refresh""", re.I)),
]
_HTTP_LINK = re.compile(r"""\bhttp://[^\s)"'<>]+""", re.I)
MIN_SHRINK_BASE = 500


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
    changed = {k for k in set(dict_b) | set(dict_a) if dict_b.get(k) != dict_a.get(k)}
    reasons = []
    if changed - allowed:
        reasons.append(f"{path}: 허용되지 않은 front matter 항목이 바뀌었습니다: {', '.join(sorted(changed - allowed))}")
    if mode == "front_matter" and body_a != body_b:
        reasons.append(f"{path}: 본문이 바뀌었습니다(이 수정 항목은 front matter 필드만 바꿀 수 있습니다).")
    return reasons


def verify_changes(changes, allowed_patterns, limits, mode="body", only_fields=None):
    """changes: {경로: (이전 텍스트, 새 텍스트)}. 거부 사유 목록(비어 있으면 통과).

    mode: body(본문만) · front_matter(only_fields 만) · image(front matter 의 image 만 + 본문 이미지 URL)
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
        if len(before) >= MIN_SHRINK_BASE and len(after) < len(before) * 0.5:
            reasons.append(f"{path}: 수정 후 파일이 절반 이하로 줄었습니다.")
        lines = changed_line_count(before, after)
        if lines > limits["max_changed_lines"]:
            reasons.append(f"{path}: 바뀐 줄이 너무 많습니다({lines}줄 > {limits['max_changed_lines']}줄). 요청을 더 작게 나눠 주세요.")
        for rx in AD_PATTERNS:
            if len(rx.findall(before)) != len(rx.findall(after)):
                reasons.append(f"{path}: 광고 코드({rx.pattern})가 추가되거나 삭제됩니다. 광고 표면은 이 경로로 바꿀 수 없습니다.")
        for name, rx in DANGEROUS:
            if len(rx.findall(after)) > len(rx.findall(before)):
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
