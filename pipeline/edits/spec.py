"""수정 명세(.github/editorial/edit-spec.yml) 로드·검증과 경로 규칙.

핵심 보안 규칙: 명세가 무엇을 허용하든 NEVER_ALLOW 에 해당하는 경로는 **수정할 수 없다**
(워크플로·코드·레이아웃·설정·광고 표면·문서 규칙 등). 명세 자체가 이 경로를 허용하면 검증 오류다.
"""
import re
from pathlib import Path, PurePosixPath

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

SPEC_PATH = ".github/editorial/edit-spec.yml"
KNOWN_FIELDS = {"target_page", "target_post", "edit_type", "before", "after", "user_prompt"}
METHODS = {"image", "text", "link", "front_matter", "llm_patch"}
TARGETS = {"page", "post"}
FRONT_MATTER_FIELDS = {"title", "description"}
PLACEHOLDERS = {"{page.path}", "{post.path}"}
OUTPUT_KEYS = {"mode", "branch_prefix"}   # 명세 output 에서 코드가 읽는 키(그 밖의 키는 SPEC-1 오류)
ALLOWED_ASSOCIATIONS = ("OWNER", "MEMBER", "COLLABORATOR")

# 이슈 자동화가 어떤 경우에도 고칠 수 없는 경로(글로브). 대소문자 구분 없이 비교한다.
NEVER_ALLOW = (
    ".github/**", "pipeline/**", "scripts/**", "tests/**", "docs/**", "인수인계/**",
    "_layouts/**", "_includes/**", "_config.yml", "index.html", "robots.txt", "ads.txt", "CNAME",
    ".gitignore", "google*.html", "naver*.html",
    "*.py", "*.yml", "*.yaml", "*.json", "*.sh", "*.bat",
    "AGENTS.md", "CLAUDE.md", "GEMINI.md", "HANDLER.md", "WORKLOG.md", "AI_COLLAB.md", "README.md",
    "requirements*.txt", "feed.xml",
)


class SpecError(ValueError):
    """명세를 읽을 수 없거나 형식이 잘못됐을 때."""


# ----------------------------------------------------------------------------
# 경로 규칙
# ----------------------------------------------------------------------------
def glob_to_regex(pattern, flags=0):
    """`**` 는 디렉터리를 넘나들고 `*`·`?` 는 `/` 를 넘지 않는 글로브를 정규식으로 바꾼다."""
    i, out = 0, []
    while i < len(pattern):
        c = pattern[i]
        if c == "*":
            if pattern[i:i + 2] == "**":
                i += 2
                if pattern[i:i + 1] == "/":
                    i += 1
                    out.append("(?:.*/)?")
                else:
                    out.append(".*")
                continue
            out.append("[^/]*")
        elif c == "?":
            out.append("[^/]")
        else:
            out.append(re.escape(c))
        i += 1
    return re.compile("^" + "".join(out) + "$", flags)


def normalize_path(path):
    """저장소 상대 POSIX 경로로 정규화한다. 절대 경로·상위 디렉터리(`..`)·빈 값은 ValueError."""
    if not isinstance(path, str) or not path.strip():
        raise ValueError("경로가 비어 있습니다.")
    raw = path.strip().replace("\\", "/")
    if re.search(r"[\x00-\x1f\x7f]", raw):
        raise ValueError("경로에 제어 문자(개행 등)가 들어 있습니다.")
    if re.match(r"^[A-Za-z]:", raw) or raw.startswith("/"):
        raise ValueError(f"절대 경로는 허용되지 않습니다: {path}")
    parts = [p for p in PurePosixPath(raw).parts if p not in ("", ".")]
    if not parts or ".." in parts:
        raise ValueError(f"올바르지 않은 경로입니다: {path}")
    return "/".join(parts)


def is_never_allowed(path):
    norm = normalize_path(path)
    return any(glob_to_regex(g, re.IGNORECASE).match(norm) for g in NEVER_ALLOW)


def path_allowed(path, patterns):
    """path 가 patterns 중 하나에 맞고 절대 금지 경로가 아니면 True."""
    try:
        norm = normalize_path(path)
    except ValueError:
        return False
    if is_never_allowed(norm):
        return False
    return any(glob_to_regex(p).match(norm) for p in patterns)


def _probe(glob):
    return glob.replace("**/", "").replace("**", "a/b").replace("*", "x").replace("?", "x")


def pattern_conflicts(pattern):
    """명세의 허용 패턴이 절대 금지 경로를 포함할 수 있으면 True(보수적 판정)."""
    if pattern in PLACEHOLDERS:
        return False
    if any(glob_to_regex(g, re.IGNORECASE).match(pattern) for g in NEVER_ALLOW):
        return True
    rx = glob_to_regex(pattern, re.IGNORECASE)
    return any(rx.match(_probe(g)) for g in NEVER_ALLOW)


# ----------------------------------------------------------------------------
# 로드·검증
# ----------------------------------------------------------------------------
def load_spec(root, path=SPEC_PATH):
    if yaml is None:
        raise SpecError("PyYAML 이 필요합니다 (pip install pyyaml).")
    file = Path(root) / path
    try:
        spec = yaml.safe_load(file.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise SpecError(f"명세를 읽을 수 없습니다 ({path}): {exc}") from exc
    if not isinstance(spec, dict):
        raise SpecError("명세 최상위는 객체여야 합니다.")
    return spec


def validate_spec(spec):
    """명세 오류 목록(비어 있으면 정상)."""
    errors = []
    if not isinstance(spec, dict):
        return ["명세 최상위는 객체여야 합니다."]
    if spec.get("version") != 1:
        errors.append("version 은 1 이어야 합니다.")

    targets = spec.get("targets") or {}
    for name in TARGETS:
        if not isinstance(targets.get(name), dict):
            errors.append(f"targets.{name} 이 필요합니다.")
    page_t = targets.get("page") if isinstance(targets.get("page"), dict) else {}
    discover = page_t.get("discover") or {}
    for key in ("include", "exclude"):
        if not isinstance(discover.get(key, []), list):
            errors.append(f"targets.page.discover.{key} 는 배열이어야 합니다.")

    edit_types = spec.get("edit_types")
    if not isinstance(edit_types, dict) or not edit_types:
        errors.append("edit_types 는 비어 있지 않은 객체여야 합니다.")
        edit_types = {}
    for key, cfg in edit_types.items():
        label = f"edit_types.{key}"
        if not re.match(r"^[a-z][a-z0-9_]{1,30}$", str(key)):
            errors.append(f"{label}: 키가 올바르지 않습니다.")
        if not isinstance(cfg, dict):
            errors.append(f"{label}: 객체여야 합니다.")
            continue
        if not isinstance(cfg.get("label"), str) or not cfg["label"].strip():
            errors.append(f"{label}: label 이 필요합니다.")
        if not re.match(r"^edit:[a-z]+$", str(cfg.get("issue_label", ""))):
            errors.append(f"{label}: issue_label 은 'edit:<이름>' 형식이어야 합니다.")
        target = cfg.get("target")
        if target not in TARGETS:
            errors.append(f"{label}: target 은 {sorted(TARGETS)} 중 하나여야 합니다.")
        if cfg.get("method") not in METHODS:
            errors.append(f"{label}: method 는 {sorted(METHODS)} 중 하나여야 합니다.")
        required = cfg.get("required")
        if not isinstance(required, list) or not required or not set(required) <= KNOWN_FIELDS:
            errors.append(f"{label}: required 는 {sorted(KNOWN_FIELDS)} 의 부분집합(비어 있지 않음)이어야 합니다.")
        elif target == "page" and "target_page" not in required:
            errors.append(f"{label}: 페이지 대상은 required 에 target_page 가 있어야 합니다.")
        elif target == "post" and "target_post" not in required:
            errors.append(f"{label}: 게시글 대상은 required 에 target_post 가 있어야 합니다.")
        paths = cfg.get("allowed_paths")
        if not isinstance(paths, list) or not paths or not all(isinstance(p, str) and p for p in paths):
            errors.append(f"{label}: allowed_paths 는 비어 있지 않은 문자열 배열이어야 합니다.")
        else:
            for pattern in paths:
                if pattern.startswith("/") or ".." in pattern or "\\" in pattern:
                    errors.append(f"{label}: 허용 경로 {pattern!r} 이(가) 올바르지 않습니다.")
                elif pattern_conflicts(pattern):
                    errors.append(f"{label}: 허용 경로 {pattern!r} 은(는) 절대 금지 경로(레이아웃·코드·워크플로·광고 표면 등)를 포함합니다.")
                elif pattern not in PLACEHOLDERS and (pattern.startswith("{") or "{" in pattern):
                    errors.append(f"{label}: 알 수 없는 자리표시자 {pattern!r} (허용: {sorted(PLACEHOLDERS)})")
            expected = "{page.path}" if target == "page" else "{post.path}"
            if target in TARGETS and expected not in paths:
                errors.append(f"{label}: allowed_paths 에 {expected} 가 있어야 합니다(대상 파일만 수정).")
        if cfg.get("method") == "front_matter":
            only = cfg.get("only_fields")
            if not isinstance(only, list) or not only or not set(only) <= FRONT_MATTER_FIELDS:
                errors.append(f"{label}: only_fields 는 {sorted(FRONT_MATTER_FIELDS)} 의 부분집합이어야 합니다.")
        if cfg.get("method") == "image" and target != "post":
            errors.append(f"{label}: image 방식은 게시글 대상이어야 합니다.")

    limits = spec.get("limits") or {}
    for key in ("max_changed_files", "max_changed_lines", "max_file_chars"):
        if not isinstance(limits.get(key), int) or limits[key] <= 0:
            errors.append(f"limits.{key} 는 양의 정수여야 합니다.")

    output = spec.get("output") or {}
    if not isinstance(output, dict):
        errors.append("output 은 객체여야 합니다.")
        output = {}
    # 코드가 읽지 않는 키를 받아들이지 않는다: 읽지도 않는 스위치(예: comment_on_reject: false)는 조용한 실패를 부른다.
    # 새 키를 지원하려면 OUTPUT_KEYS 와 이 검증을 같은 변경에서 고친다(런타임도 이 검증을 쓴다).
    unknown = sorted(str(k) for k in output if k not in OUTPUT_KEYS)
    if unknown:
        errors.append(f"output 에 지원하지 않는 키가 있습니다: {', '.join(unknown)} (지원: {', '.join(sorted(OUTPUT_KEYS))}). "
                      "거부·오류는 항상 이슈에 사유를 코멘트하며 끌 수 없습니다.")
    if output.get("mode") != "pull_request":
        errors.append("output.mode 는 pull_request 여야 합니다(main 직접 push 금지).")
    prefix = output.get("branch_prefix", "")
    if not isinstance(prefix, str) or not re.match(r"^[a-z][a-z0-9\-]*/$", prefix):
        errors.append("output.branch_prefix 는 'issue-edit/' 같은 형식이어야 합니다.")
    return errors


def resolve_allowed(edit_cfg, target_path):
    """{page.path}·{post.path} 를 실제 대상 경로로 바꾼 허용 패턴 목록."""
    norm = normalize_path(target_path)
    out = []
    for pattern in edit_cfg["allowed_paths"]:
        out.append(norm if pattern in PLACEHOLDERS else pattern)
    return out


def edit_types_for_label(spec, issue_label):
    return {k: v for k, v in spec["edit_types"].items() if v.get("issue_label") == issue_label}


def issue_labels(spec):
    return sorted({v["issue_label"] for v in spec["edit_types"].values()})
