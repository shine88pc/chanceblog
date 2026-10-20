#!/usr/bin/env python3
"""저장소 가드레일 검증기 — 여러 AI가 같은 저장소를 고쳐도 규칙이 깨지지 않게 하는 자동 점검.

사용
  python scripts/validate_repo.py                    # 현재 저장소 점검
  python scripts/validate_repo.py --base <git-sha>   # 해당 커밋 이후 변경에 대한 광고 표면 검사 포함
  python scripts/validate_repo.py --strict           # 경고도 실패로 취급
  python scripts/validate_repo.py --json             # 기계가 읽는 출력

종료 코드: ERROR 가 있으면 1, 없으면 0 (WARN 은 --strict 일 때만 실패).
검사 ID 는 docs/SECURITY_GUARDRAILS.md(G-*)와 docs/DEFECT_REGISTER.md(D-*)에 대응한다.
표준 라이브러리만 쓰되, 워크플로 검사는 PyYAML 이 있을 때만 수행한다(없으면 WARN 후 건너뜀).
"""
import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - 환경에 따라 다름
    yaml = None

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import registry as reg_mod  # noqa: E402

TEXT_EXT = {".md", ".py", ".yml", ".yaml", ".json", ".html", ".htm", ".js", ".css", ".txt", ".xml",
            ".bat", ".sh", ".toml", ".cfg", ".ini", ".csv", ".svg", ".gitignore"}
MAX_TEXT_BYTES = 2_000_000
SKIP_DIRS = {".git", "node_modules", "_site", ".jekyll-cache", "__pycache__", ".venv", "venv"}
FIRST_PARTY_OWNERS = {"actions", "github"}


@dataclass
class Finding:
    level: str  # ERROR | WARN
    check: str
    message: str
    path: str = ""

    def line(self):
        where = f" {self.path}:" if self.path else ""
        return f"{self.level:<5} [{self.check}]{where} {self.message}"


def err(check, message, path=""):
    return Finding("ERROR", check, message, path)


def warn(check, message, path=""):
    return Finding("WARN", check, message, path)


# ----------------------------------------------------------------------------
# 파일 열거·읽기
# ----------------------------------------------------------------------------
def list_files(root):
    root = Path(root)
    try:
        res = subprocess.run(["git", "ls-files", "-z", "-co", "--exclude-standard"], cwd=root,
                             capture_output=True, check=True, timeout=60)
        names = [n for n in res.stdout.decode("utf-8", "replace").split("\0") if n]
        return sorted(n for n in set(names) if (root / n).is_file())
    except (OSError, subprocess.SubprocessError):
        out = []
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for name in filenames:
                out.append(Path(dirpath, name).relative_to(root).as_posix())
        return sorted(out)


def read_text(root, rel):
    path = Path(root) / rel
    suffix = path.suffix.lower()
    if suffix not in TEXT_EXT and path.name not in {".gitignore", "LICENSE", "CODEOWNERS"}:
        return None
    try:
        if path.stat().st_size > MAX_TEXT_BYTES:
            return None
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


# ----------------------------------------------------------------------------
# 1. 비밀 (G-S1)
# ----------------------------------------------------------------------------
_FORBIDDEN_FILES = [
    (re.compile(r"^client_secret.*\.json$", re.I), "OAuth 클라이언트 시크릿 파일"),
    (re.compile(r"^token.*\.json$", re.I), "토큰 파일"),
    (re.compile(r"^\.env(?!\.(?:example|sample|template)$)(\..+)?$", re.I), ".env 파일"),
    (re.compile(r".*\.(pem|key|p12|pfx)$", re.I), "키/인증서 파일"),
    (re.compile(r"^id_(?:rsa|dsa|ecdsa|ed25519)$"), "SSH 개인 키"),
    (re.compile(r".*(?:credentials|service[-_]?account).*\.json$", re.I), "자격 증명 JSON"),
]

_SECRET_PATTERNS = [
    ("Google API 키", re.compile(r"AIza[0-9A-Za-z_\-]{35}")),
    ("Google OAuth 클라이언트 시크릿", re.compile(r"GOCSPX-[0-9A-Za-z_\-]{20,}")),
    ("Google refresh token", re.compile(r"\b1//0[0-9A-Za-z_\-]{40,}")),
    ("Google access token", re.compile(r"\bya29\.[0-9A-Za-z_\-]{30,}")),
    ("GitHub 토큰", re.compile(r"\bgh[pousr]_[0-9A-Za-z]{36,}")),
    ("GitHub PAT", re.compile(r"\bgithub_pat_[0-9A-Za-z_]{40,}")),
    ("개인 키 블록", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY(?: BLOCK)?-----")),
    ("Slack 토큰", re.compile(r"\bxox[baprs]-[0-9A-Za-z\-]{10,}")),
    ("AWS 액세스 키", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("sk- 형식 API 키", re.compile(r"\bsk-[A-Za-z0-9]{32,}\b")),
    # 값이 환경변수 이름(대문자_숫자_밑줄)이면 시크릿이 아니라 레지스트리의 '이름 매핑'이다
    ("client_secret JSON 값", re.compile(r'"client_secret"\s*:\s*"(?![A-Z][A-Z0-9_]*")[^"]{8,}"')),
    ("키/토큰 할당", re.compile(r"""(?i)\b(?:api[_-]?key|secret|token|passwd|password)\b\s*[:=]\s*['"][A-Za-z0-9_\-/+=]{24,}['"]""")),
]
ALLOW_MARKER = "validate-repo: allow"


def check_forbidden_files(files):
    out = []
    for rel in files:
        name = Path(rel).name
        for rx, label in _FORBIDDEN_FILES:
            if rx.match(name):
                out.append(err("SEC-1", f"{label}이(가) 저장소에 있습니다. 삭제하고 .gitignore 로 막으세요 (G-S1)", rel))
                break
    return out


def check_secret_patterns(root, files):
    out = []
    for rel in files:
        text = read_text(root, rel)
        if not text:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            if ALLOW_MARKER in line:
                continue
            for label, rx in _SECRET_PATTERNS:
                match = rx.search(line)
                if match:
                    shown = match.group(0)[:4] + "***"
                    out.append(err("SEC-2", f"{label}로 보이는 값이 있습니다({shown}). 즉시 폐기·교체 대상입니다 (G-S5)",
                                   f"{rel}:{lineno}"))
    return out


# ----------------------------------------------------------------------------
# 2. 워크플로 (G-A*)
# ----------------------------------------------------------------------------
_UNTRUSTED_EXPR = re.compile(
    r"\$\{\{\s*(?:github\.event\.(?:issue|comment|pull_request|review|review_comment|discussion|head_commit|"
    r"commits|pages|workflow_run)\b[^}]*|github\.head_ref)\s*\}\}")
_INPUT_EXPR = re.compile(r"\$\{\{\s*(?:github\.event\.inputs\.|inputs\.)[^}]*\}\}")
_USES_RX = re.compile(r"^([\w.\-]+)/([\w./\-]+)@(.+)$")
_SHA_RX = re.compile(r"^[0-9a-f]{40}$")


def _workflow_files(files):
    return [f for f in files if re.match(r"^\.github/workflows/[^/]+\.ya?ml$", f)]


def _load_yaml(text):
    return yaml.safe_load(text) if yaml else None


def _triggers(data):
    raw = data.get("on", data.get(True)) if isinstance(data, dict) else None  # YAML 1.1: on -> True
    if isinstance(raw, str):
        return {raw: None}
    if isinstance(raw, list):
        return {k: None for k in raw}
    return raw if isinstance(raw, dict) else {}


def check_workflows(root, files):
    out = []
    workflows = _workflow_files(files)
    if workflows and yaml is None:
        return [warn("WF-0", "PyYAML 이 없어 워크플로 보안 검사를 건너뜁니다 (pip install pyyaml)")]
    for rel in workflows:
        text = read_text(root, rel) or ""
        try:
            data = _load_yaml(text)
        except yaml.YAMLError as exc:
            out.append(err("WF-0", f"YAML 문법 오류: {str(exc).splitlines()[0]}", rel))
            continue
        if not isinstance(data, dict):
            out.append(err("WF-0", "워크플로 최상위가 객체가 아닙니다", rel))
            continue
        perms = data.get("permissions")
        if perms is None:
            out.append(err("WF-1", "최상위 permissions 가 없습니다. 최소 권한을 명시하세요 (G-A1)", rel))
        elif perms == "write-all" or (isinstance(perms, dict) and any(v == "write-all" for v in perms.values())):
            out.append(err("WF-1", "permissions: write-all 은 금지입니다 (G-A1)", rel))
        triggers = _triggers(data)
        if "pull_request_target" in triggers:
            out.append(err("WF-3", "pull_request_target 은 금지입니다(포크 코드 + 시크릿 노출 위험) (G-A3)", rel))
        jobs = data.get("jobs") or {}
        scheduled = "schedule" in triggers
        has_concurrency = "concurrency" in data or any(isinstance(j, dict) and "concurrency" in j for j in jobs.values())
        if scheduled and not has_concurrency:
            out.append(warn("WF-8", "schedule 워크플로에 concurrency 가 없어 실행이 겹칠 수 있습니다", rel))
        for job_name, job in jobs.items():
            if not isinstance(job, dict):
                continue
            if "timeout-minutes" not in job and "uses" not in job:
                out.append(warn("WF-7", f"job '{job_name}' 에 timeout-minutes 가 없습니다", rel))
            for step in job.get("steps") or []:
                if not isinstance(step, dict):
                    continue
                run = step.get("run")
                if isinstance(run, str):
                    if _UNTRUSTED_EXPR.search(run):
                        out.append(err("WF-4", f"run 안에서 신뢰할 수 없는 입력을 직접 보간합니다 — env 로 넘기세요 (G-A2): "
                                               f"{_UNTRUSTED_EXPR.search(run).group(0)[:60]}", rel))
                    if _INPUT_EXPR.search(run):
                        out.append(warn("WF-4", "run 안에서 inputs 를 직접 보간합니다 — env 로 넘기는 편이 안전합니다 (G-A2)", rel))
                    if re.search(r"\|\|\s*true\b", run):
                        out.append(warn("WF-6", "'|| true' 로 오류를 숨기고 있습니다 (G-O2: 조용한 실패 금지)", rel))
                    if re.search(r"echo\b[^\n]*\$\{\{\s*secrets\.", run):
                        out.append(err("WF-9", "시크릿을 echo 로 출력합니다 (G-S3)", rel))
                if step.get("continue-on-error") is True:
                    out.append(warn("WF-6", "continue-on-error: true 로 실패를 숨기고 있습니다 (G-O2)", rel))
                uses = step.get("uses")
                if isinstance(uses, str) and not uses.startswith("./") and not uses.startswith("docker://"):
                    m = _USES_RX.match(uses)
                    if m and m.group(1) not in FIRST_PARTY_OWNERS and not _SHA_RX.match(m.group(3)):
                        out.append(err("WF-5", f"외부 액션 {uses} 는 커밋 SHA 로 고정해야 합니다 (G-A4)", rel))
    return out


def _workflow_crons(root, rel):
    if yaml is None:
        return None
    try:
        data = _load_yaml(read_text(root, rel) or "")
    except yaml.YAMLError:
        return None
    sched = _triggers(data).get("schedule") or []
    return [item.get("cron") for item in sched if isinstance(item, dict)]


# ----------------------------------------------------------------------------
# 3. 레지스트리·계약 (문서/코드/설정 드리프트 방지)
# ----------------------------------------------------------------------------
def check_registry(root, files):
    out = []
    path = Path(root) / "pipeline" / "blogs.json"
    if not path.exists():
        return [err("REG-0", "pipeline/blogs.json 이 없습니다")]
    try:
        reg = reg_mod.load_registry(path)
    except reg_mod.RegistryError as exc:
        return [err("REG-0", str(exc), "pipeline/blogs.json")]
    for message in reg_mod.validate_registry(reg, root):
        out.append(err("REG-1", message, "pipeline/blogs.json"))
    if out:
        return out
    for raw in reg["blogs"]:
        blog = reg_mod.merged_blog(reg, raw)
        wf_text = read_text(root, blog["workflow"]) or ""
        crons = _workflow_crons(root, blog["workflow"])
        if crons is not None and blog["schedule"]["cron"] not in crons:
            out.append(err("REG-2", f"블로그 '{blog['key']}' cron({blog['schedule']['cron']})이 워크플로 schedule {crons} 와 다릅니다",
                           blog["workflow"]))
        for role, env_name in blog["secrets"].items():
            wired = (f"secrets.{env_name}" in wf_text or f"secrets['{env_name}']" in wf_text
                     or "secrets[matrix." in wf_text)
            if not wired:
                out.append(warn("REG-3", f"블로그 '{blog['key']}' 의 시크릿 {env_name}({role})이 워크플로에 연결돼 있지 않습니다",
                                blog["workflow"]))
        if blog["platform"] == "jekyll-git" and "git push" in wf_text and "gh workflow run" not in wf_text:
            out.append(warn("WF-10", "GITHUB_TOKEN 으로 push 한 커밋은 push 트리거(Pages 배포)를 일으키지 않습니다 — "
                                     "배포 워크플로를 dispatch 해야 합니다 (D-02)", blog["workflow"]))
    gen = read_text(root, "generator.py") or ""
    m = re.search(r"MODEL_CANDIDATES\s*=\s*\[(.*?)\]", gen, re.S)
    if m:
        code_models = re.findall(r"['\"]([^'\"]+)['\"]", m.group(1))
        reg_models = reg.get("defaults", {}).get("llm", {}).get("models", [])
        if code_models and code_models != reg_models:
            out.append(warn("REG-4", f"generator.py MODEL_CANDIDATES {code_models} 가 레지스트리 {reg_models} 와 다릅니다 "
                                     "(모델 목록은 한 곳에서 관리)", "generator.py"))
    return out


def check_issue_contract(root, files):
    """이슈 양식 제목 접두사와 워크플로의 이슈 조건이 맞는지(D-01 재발 방지)."""
    if yaml is None:
        return []
    out = []
    templates = {}
    for rel in files:
        if re.match(r"^\.github/ISSUE_TEMPLATE/[^/]+\.ya?ml$", rel):
            try:
                data = _load_yaml(read_text(root, rel) or "")
            except yaml.YAMLError:
                continue
            if isinstance(data, dict) and isinstance(data.get("title"), str):
                templates[rel] = data["title"]
    for rel in _workflow_files(files):
        text = read_text(root, rel) or ""
        prefixes = re.findall(r"startsWith\(github\.event\.issue\.title,\s*'([^']*)'\)", text)
        for prefix in prefixes:
            for tpl, title in templates.items():
                if not title.startswith(prefix):
                    out.append(warn("CONTRACT-1", f"이슈 양식 {tpl} 의 제목 '{title}' 이(가) 워크플로 조건 '{prefix}' 로 시작하지 않아 "
                                                  "이슈로 워크플로가 실행되지 않습니다 (D-01)", rel))
    return out


# ----------------------------------------------------------------------------
# 4. 코드·데이터·문서
# ----------------------------------------------------------------------------
def check_python(root, files):
    out = []
    for rel in files:
        if rel.endswith(".py"):
            try:
                compile(read_text(root, rel) or "", rel, "exec")
            except SyntaxError as exc:
                out.append(err("PY-1", f"문법 오류 line {exc.lineno}: {exc.msg}", rel))
    return out


def check_json(root, files):
    out = []
    for rel in files:
        if rel.endswith(".json"):
            text = read_text(root, rel)
            if text is None or text.lstrip().startswith("---"):
                continue  # 읽을 수 없음 / Jekyll front matter 템플릿(빌드 후에야 JSON)
            try:
                json.loads(text)
            except json.JSONDecodeError as exc:
                out.append(err("JSON-1", f"JSON 오류 line {exc.lineno}: {exc.msg}", rel))
    return out


_LINK_RX = re.compile(r"\]\(([^)\s#]+)(?:#[^)]*)?\)")
_STRICT_DOCS = re.compile(r"^(docs/.*\.md|AGENTS\.md|CLAUDE\.md|GEMINI\.md|\.github/copilot-instructions\.md)$")


def check_doc_links(root, files):
    out = []
    for rel in files:
        if not rel.endswith(".md"):
            continue
        text = read_text(root, rel) or ""
        base = (Path(root) / rel).parent
        for lineno, line in enumerate(text.splitlines(), 1):
            for target in _LINK_RX.findall(line):
                if re.match(r"^[a-zA-Z][a-zA-Z0-9+.\-]*:", target) or target.startswith(("/", "#")):
                    continue
                if not (base / target).exists():
                    maker = err if _STRICT_DOCS.match(rel) else warn
                    out.append(maker("DOC-1", f"깨진 링크: {target}", f"{rel}:{lineno}"))
    return out


_AGENT_FILES = ["AGENTS.md", "CLAUDE.md", "GEMINI.md", ".github/copilot-instructions.md"]


def check_agent_files(root, files):
    out = []
    for rel in _AGENT_FILES:
        text = read_text(root, rel) if rel in files else None
        if text is None:
            out.append(warn("AGENT-1", "AI 에이전트용 지침 파일이 없습니다(AI마다 읽는 파일이 달라 모두 필요)", rel))
        elif "HANDLER.md" not in text or "SECURITY_GUARDRAILS" not in text:
            out.append(warn("AGENT-1", "HANDLER.md 와 docs/SECURITY_GUARDRAILS.md 를 가리키지 않습니다", rel))
    return out


def check_exposure(root, files):
    """Jekyll 이 내부 문서·스크립트를 사이트에 정적 파일로 내보내는지(D-08)."""
    if yaml is None or "_config.yml" not in files:
        return []
    try:
        cfg = _load_yaml(read_text(root, "_config.yml") or "") or {}
    except yaml.YAMLError:
        return []
    excluded = cfg.get("exclude") or []
    internal = [f for f in ("HANDLER.md", "WORKLOG.md", "AI_COLLAB.md") if f in files and f not in excluded]
    if internal:
        return [warn("EXPOSE-1", f"{', '.join(internal)} 등 내부 문서가 사이트에 정적 파일로 공개됩니다. "
                                 "_config.yml exclude 추가를 검토하세요 (사용자 승인 필요, D-08)", "_config.yml")]
    return []


_PIN_RX = re.compile(r"(==|>=|<=|~=|<|>|!=)")


def _unpinned(tokens):
    skip = {"pip", "setuptools", "wheel"}
    out = []
    for tok in tokens:
        if tok.startswith("-") or tok.startswith(("./", ".", "$")) or tok in skip:
            continue
        if tok.endswith((".txt", ".whl")) or "/" in tok:
            continue
        if not _PIN_RX.search(tok):
            out.append(tok)
    return out


def check_dependencies(root, files):
    out = []
    for rel in _workflow_files(files):
        text = read_text(root, rel) or ""
        for m in re.finditer(r"pip install ([^\n|&;]+)", text):
            bad = _unpinned(m.group(1).split())
            if bad:
                out.append(warn("DEP-1", f"버전 범위 없이 설치하는 패키지: {', '.join(bad)} (D-10)", rel))
    for rel in files:
        if re.match(r"^requirements[^/]*\.txt$", Path(rel).name):
            bad = _unpinned([ln.split("#")[0].strip() for ln in (read_text(root, rel) or "").splitlines() if ln.split("#")[0].strip()])
            if bad:
                out.append(warn("DEP-1", f"버전 범위 없는 항목: {', '.join(bad)} (D-10)", rel))
    return out


# ----------------------------------------------------------------------------
# 5. 광고 표면 (G-C6) — 변경 범위 기반
# ----------------------------------------------------------------------------
def _git(root, *args):
    return subprocess.run(["git", *args], cwd=root, capture_output=True, check=True, timeout=60).stdout.decode("utf-8", "replace")


def check_ad_surface(root, base):
    if not base or re.fullmatch(r"0+", base):
        return []
    path = Path(root) / "pipeline" / "blogs.json"
    try:
        reg = reg_mod.load_registry(path)
        changed = [p for p in _git(root, "diff", "--name-only", f"{base}..HEAD").splitlines() if p]
        messages = _git(root, "log", "--format=%B", f"{base}..HEAD")
    except (reg_mod.RegistryError, OSError, subprocess.SubprocessError):
        return [warn("AD-0", f"base({base[:8]})를 해석할 수 없어 광고 표면 검사를 건너뜁니다")]
    protected = []
    for raw in reg["blogs"]:
        blog = reg_mod.merged_blog(reg, raw)
        if blog.get("ad_surface"):
            protected.extend(blog.get("protected_paths", []))
    hits = sorted({p for p in changed for pp in protected if p == pp or (pp.endswith("/") and p.startswith(pp))})
    if hits and "Ad-Surface-Approved:" not in messages:
        return [err("AD-1", "광고 표면(AdSense 심사 대상) 파일이 승인 표시 없이 변경됐습니다: " + ", ".join(hits) +
                    ". 사용자 승인 후 커밋 메시지에 'Ad-Surface-Approved: <사유>' 를 넣으세요 (G-C6)")]
    return []


# ----------------------------------------------------------------------------
# 실행
# ----------------------------------------------------------------------------
def run_checks(root, base=None):
    files = list_files(root)
    findings = []
    findings += check_forbidden_files(files)
    findings += check_secret_patterns(root, files)
    findings += check_workflows(root, files)
    findings += check_registry(root, files)
    findings += check_issue_contract(root, files)
    findings += check_python(root, files)
    findings += check_json(root, files)
    findings += check_doc_links(root, files)
    findings += check_agent_files(root, files)
    findings += check_exposure(root, files)
    findings += check_dependencies(root, files)
    findings += check_ad_surface(root, base)
    return findings


def main(argv=None):
    parser = argparse.ArgumentParser(description="저장소 가드레일 검증기")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--base", default=os.environ.get("VALIDATE_BASE"))
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    findings = run_checks(Path(args.root), args.base)
    errors = [f for f in findings if f.level == "ERROR"]
    warns = [f for f in findings if f.level == "WARN"]
    if args.json:
        print(json.dumps([asdict(f) for f in findings], ensure_ascii=False, indent=2))
    else:
        for f in errors + warns:
            print(f.line())
        print(f"\n요약: 오류 {len(errors)}건, 경고 {len(warns)}건" + (" — 통과" if not errors else " — 실패"))
    return 1 if errors or (args.strict and warns) else 0


if __name__ == "__main__":
    sys.exit(main())
