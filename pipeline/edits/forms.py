"""이슈 양식(.github/ISSUE_TEMPLATE/*.yml) 읽기, 이슈 본문 파싱, 드롭다운 동기화.

GitHub 이슈 양식으로 만든 이슈 본문은 `### <항목 라벨>` 제목 아래에 값이 들어가는 형태다(빈 선택 항목은 `_No response_`).
본문은 **신뢰할 수 없는 입력**이다. 그래서
- 양식에 정의된 라벨만 항목 경계로 인정한다(텍스트 칸 안의 `###` 줄은 값의 일부다).
- 같은 항목 제목이 두 번 나오면(= 텍스트 칸에 가짜 제목을 심어 대상을 바꾸려는 시도) 처리를 거부한다.
"""
import json
import re
from pathlib import Path

from pipeline.edits import frontmatter, spec as spec_mod

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

TEMPLATE_DIR = ".github/ISSUE_TEMPLATE"
PAGE_TEMPLATE = "page-edit.yml"
CONTROL_LABEL = "blog-control"
_NO_RESPONSE = {"_no response_", "no response"}
_FIELD_TYPES = ("input", "textarea", "dropdown", "checkboxes")


class FormError(ValueError):
    pass


def load_templates(root):
    """제어용 양식 목록: file, title, labels, fields[{id,label,type,required}]."""
    if yaml is None:
        raise FormError("PyYAML 이 필요합니다.")
    templates = []
    for path in sorted((Path(root) / TEMPLATE_DIR).glob("*.y*ml")):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            raise FormError(f"이슈 양식을 읽을 수 없습니다 ({path.name}): {exc}") from exc
        if not isinstance(data, dict) or not isinstance(data.get("body"), list):
            continue
        fields = []
        for item in data["body"]:
            if isinstance(item, dict) and item.get("type") in _FIELD_TYPES and item.get("id"):
                attrs = item.get("attributes") or {}
                fields.append({"id": item["id"], "label": str(attrs.get("label", "")), "type": item["type"],
                               "required": bool((item.get("validations") or {}).get("required"))})
        templates.append({"file": path.name, "title": str(data.get("title", "")),
                          "labels": [str(x) for x in (data.get("labels") or [])], "fields": fields})
    return templates


def control_templates(templates):
    return [t for t in templates if CONTROL_LABEL in t["labels"]]


def label_map(templates):
    """제어용 양식 전체의 {항목 라벨: 필드 id}. 같은 라벨이 다른 id 를 가리키면 FormError."""
    out = {}
    for tpl in control_templates(templates):
        for field in tpl["fields"]:
            if field["label"] in out and out[field["label"]] != field["id"]:
                raise FormError(f"항목 라벨 {field['label']!r} 이(가) 서로 다른 필드를 가리킵니다.")
            out[field["label"]] = field["id"]
    return out


def field_labels(templates):
    """{필드 id: 라벨} (사용자에게 보여 줄 메시지용)."""
    return {v: k for k, v in label_map(templates).items()}


def parse_issue_body(body, labels):
    """(필드 id -> 값, 중복된 항목 라벨 목록). labels 는 {라벨: id}."""
    sections, duplicates, current = {}, set(), None
    for line in frontmatter.normalize_newlines(body).split("\n"):
        m = re.match(r"^###\s+(.+?)\s*$", line)
        if m and m.group(1) in labels:
            label = m.group(1)
            if label in sections:
                duplicates.add(label)
            else:
                sections[label] = []
            current = label
            continue
        if current is not None and current not in duplicates:
            sections[current].append(line)
    fields = {}
    for label, buf in sections.items():
        value = "\n".join(buf).strip()
        fields[labels[label]] = "" if value.lower() in _NO_RESPONSE else value
    return fields, sorted(duplicates)


def option_id(value):
    """'about | 소개와 편집 원칙' → 'about'."""
    return str(value or "").split("|", 1)[0].strip()


def identify_issue_label(issue, spec, templates, labels):
    """(처리 경로 라벨 'edit:*', 사유). 못 정하면 (None, 사유)."""
    wanted = spec_mod.issue_labels(spec)
    present = [l.get("name") if isinstance(l, dict) else str(l) for l in (issue.get("labels") or [])]
    hit = [x for x in wanted if x in present]
    if len(hit) == 1:
        return hit[0], ""
    if len(hit) > 1:
        return None, f"처리 경로 라벨이 여러 개입니다: {', '.join(hit)}"
    title = str(issue.get("title") or "")
    by_title = []
    for tpl in control_templates(templates):
        prefix = tpl["title"].strip()
        if prefix and title.startswith(prefix):
            by_title += [x for x in tpl["labels"] if x in wanted]
    if len(set(by_title)) == 1:
        return by_title[0], ""
    fields, _ = parse_issue_body(issue.get("body") or "", labels)
    by_fields = []
    for tpl in control_templates(templates):
        needed = {f["id"] for f in tpl["fields"] if f["required"]}
        if needed and needed <= set(fields):
            by_fields += [x for x in tpl["labels"] if x in wanted]
    if len(set(by_fields)) == 1:
        return by_fields[0], ""
    return None, "이슈 양식을 인식하지 못했습니다(라벨·제목·항목 구성 모두 일치하지 않음)."


# ----------------------------------------------------------------------------
# 드롭다운 동기화 (마커 사이만 다시 쓴다)
# ----------------------------------------------------------------------------
def replace_marker_block(text, name, options):
    """`# NAME:START ...` 와 `# NAME:END` 줄 사이를 options 로 교체한다. 마커 줄 자체는 보존."""
    if not options:
        raise FormError(f"{name} 드롭다운에 넣을 항목이 하나도 없습니다(양식이 무효가 됩니다).")
    lines = text.split("\n")
    start = next((i for i, l in enumerate(lines) if f"# {name}:START" in l), None)
    end = next((i for i, l in enumerate(lines) if f"# {name}:END" in l), None)
    if start is None or end is None or end <= start:
        raise FormError(f"양식에서 '# {name}:START' / '# {name}:END' 마커를 찾을 수 없습니다.")
    indent = re.match(r"\s*", lines[start]).group(0)
    body = [f"{indent}- {json.dumps(opt, ensure_ascii=False)}" for opt in options]
    return "\n".join(lines[:start + 1] + body + lines[end:])


def page_options(pages):
    return [f"{p['id']} | {p['title']}" for p in pages]


def edit_options(spec):
    return [f"{key} | {cfg['label']}" for key, cfg in spec["edit_types"].items() if cfg.get("issue_label") == "edit:page"]


def render_page_form(text, spec, pages):
    text = frontmatter.normalize_newlines(text)
    text = replace_marker_block(text, "PAGES", page_options(pages))
    return replace_marker_block(text, "EDITS", edit_options(spec))


def sync_page_form(root, spec, pages, write=True):
    """양식 파일을 최신 상태로 만든다. 바뀌면 True."""
    path = Path(root) / TEMPLATE_DIR / PAGE_TEMPLATE
    current = frontmatter.normalize_newlines(path.read_text(encoding="utf-8"))
    updated = render_page_form(current, spec, pages)
    if updated == current:
        return False
    if write:
        path.write_text(updated, encoding="utf-8", newline="\n")
    return True
