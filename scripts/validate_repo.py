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
from pipeline.console import safe_output  # noqa: E402
from pipeline.secret_patterns import SECRET_PATTERNS  # noqa: E402

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
            for label, rx in SECRET_PATTERNS:
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


# 알림 단계(pipeline/notify.py)의 모양: run 이 정확히 `python -m pipeline.notify <이벤트> [--commit HEAD|해시]` 한 줄. 이 모양의 단계만 continue-on-error 를 써도
# 경고(WF-6)가 나지 않는다 — 알림은 보조라 실패해도 글 게시 실행을 실패시키지 않아야 하고, 실패는 알림 명령이 스스로 `::warning::`(과 로그 줄)로 드러내므로
# '조용한 실패'가 아니다(G-O2). timeout-minutes 가 있어야 하고, 다른 명령에 붙은 continue-on-error 는 그대로 경고한다.
_ALERT_RUN = re.compile(r"python3? -m pipeline\.notify [a-z][a-z-]*(?: --commit (?:HEAD|[0-9a-fA-F]{7,40}))?")


def _is_alert_step(step):
    run = step.get("run")
    timeout = step.get("timeout-minutes")
    return (isinstance(run, str) and _ALERT_RUN.fullmatch(run.strip()) is not None
            and isinstance(timeout, (int, float)) and not isinstance(timeout, bool) and timeout > 0)


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
                if step.get("continue-on-error") is True and not _is_alert_step(step):
                    out.append(warn("WF-6", "continue-on-error: true 로 실패를 숨기고 있습니다 (G-O2)", rel))
                uses = step.get("uses")
                if isinstance(uses, str) and not uses.startswith("./") and not uses.startswith("docker://"):
                    m = _USES_RX.match(uses)
                    if m and m.group(1) not in FIRST_PARTY_OWNERS and not _SHA_RX.match(m.group(3)):
                        out.append(err("WF-5", f"외부 액션 {uses} 는 커밋 SHA 로 고정해야 합니다 (G-A4)", rel))
    return out


TELEGRAM_SECRETS = ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")
_TELEGRAM_NAME = re.compile("|".join(TELEGRAM_SECRETS), re.IGNORECASE)   # GitHub 시크릿 이름은 대소문자를 가리지 않는다: secrets.telegram_bot_token 도 같은 값이다
_TELEGRAM_ENV_VALUE = re.compile(r"\$\{\{\s*secrets\.(TELEGRAM_BOT_TOKEN|TELEGRAM_CHAT_ID)\s*\}\}")


def _walk_strings(node, path=()):
    """파싱한 워크플로의 모든 문자열 값과 그 위치(키·번호의 튜플)."""
    if isinstance(node, str):
        yield path, node
    elif isinstance(node, dict):
        for key, value in node.items():
            yield from _walk_strings(value, path + (key,))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _walk_strings(value, path + (index,))


def check_telegram_secrets(root, files):
    """WF-13: 텔레그램 시크릿(TELEGRAM_BOT_TOKEN·TELEGRAM_CHAT_ID)은 워크플로의 **단계 env 값**으로만 나타난다 — 같은 이름의 환경변수에
    `${{ secrets.그 이름 }}` 그대로. run 본문·with·if·job/워크플로 env·outputs·이름 등 어디에도 나타나면 오류다.

    이 토큰은 요청 주소의 경로(https://api.telegram.org/bot<토큰>/…)에 들어가는 서비스의 열쇠라, 셸 명령 줄(echo·set -x·`::set-output`·GITHUB_ENV 에 쓰기)이나
    외부 액션의 입력(with)으로 흘러가면 공개 Actions 로그로 샐 수 있다. 값은 `env:` 로 파이썬 프로세스에 넘기고 pipeline/notify.py 가 환경변수에서만 읽는다
    (G-C11). 문자열 안에 두 이름 중 하나라도 들어 있으면(`$TELEGRAM_BOT_TOKEN`·`${TELEGRAM_CHAT_ID}` 처럼 환경변수를 셸에서 펼치는 것 포함, 대소문자를 바꾼
    `secrets.telegram_bot_token` 도 같은 시크릿이라 같게 본다) 허용된 모양이 아닌 한 오류다.

    한계(문서에도 적었다): 이름이 **글자로** 나오는 곳만 본다 — `toJSON(secrets)`·`secrets[format(…)]`·`secrets: inherit` 처럼 이름 없이 시크릿을 넘기는 길과,
    외부 `uses:` 단계의 env 는 못 잡는다. 호출 쪽 재사용 워크플로의 `secrets:` 매핑(`jobs.<잡>.secrets.TELEGRAM_*`)은 허용된 자리가 아니라 오류다."""
    if yaml is None:
        return []  # PyYAML 이 없다는 경고는 WF-0(check_workflows)이 이미 낸다
    out = []
    for rel in _workflow_files(files):
        try:
            data = _load_yaml(read_text(root, rel) or "")
        except yaml.YAMLError:
            continue
        if not isinstance(data, dict):
            continue
        for path, value in _walk_strings(data):
            names = sorted({found.upper() for found in _TELEGRAM_NAME.findall(value)})
            if not names:
                continue
            in_step_env = len(path) == 6 and path[0] == "jobs" and path[2] == "steps" and path[4] == "env"
            match = _TELEGRAM_ENV_VALUE.fullmatch(value.strip()) if in_step_env else None
            if match is None or match.group(1) != path[5]:       # 단계 env 의 같은 이름 환경변수에 `${{ secrets.이름 }}` 그대로일 때만 허용
                where = ".".join(str(part) for part in path)
                out.append(err("WF-13", f"텔레그램 시크릿 이름({', '.join(names)})이 허용되지 않은 자리({where})에 있습니다 — 단계의 env 에서 같은 이름의 환경변수로만 "
                                        "`${{ secrets.이름 }}` 그대로 넘기세요(run·with·if·job/워크플로 env 에는 쓰지 않습니다). "
                                        "토큰이 셸 명령 줄이나 로그로 새는 길을 막는 규칙입니다 (G-C11)", rel))
    return out


_HANGUL_RX = re.compile(r"[가-힣ㄱ-ㅎㅏ-ㅣ]")  # 한글 음절 + 호환 자모


def _has_hangul(value):
    return isinstance(value, str) and bool(_HANGUL_RX.search(value))


def _without_label(name):
    """name 맨 앞의 `[구분] ` 접두사를 뗀 나머지(접두사가 없으면 그대로). `[공통]`·`[네이버]` 같은 한글 구분이 한글 이름 검사(WF-11)를
    대신 통과시키지 않게 한다 — 이름 본문에 한글이 있어야 하는 것이지 접두사가 아니다."""
    return name.split("] ", 1)[1] if reg_mod.name_label(name) is not None else name


def check_workflow_names(root, files):
    """WF-11: 워크플로 name 과 job name 에 한글을 쓴다(운영자가 Actions 탭에서 이름만 보고 하는 일을 짐작하게).

    워크플로 name 이 없거나 한글이 없으면 오류, job name 이 없거나 한글이 없으면 경고. name 의 `[구분] ` 접두사는 빼고 본다(WF-12).
    YAML 문법 오류는 WF-0 이 알리므로 여기서는 건너뛴다. 규칙: docs/ENGINEERING_GUIDE.md W10."""
    if yaml is None:
        return []  # PyYAML 이 없다는 경고는 WF-0(check_workflows)이 이미 낸다
    out = []
    for rel in _workflow_files(files):
        try:
            data = _load_yaml(read_text(root, rel) or "")
        except yaml.YAMLError:
            continue
        if not isinstance(data, dict):
            continue
        name = data.get("name")
        if not _has_hangul(_without_label(name) if isinstance(name, str) else name):
            problem = "에 name 이 없습니다" if name is None else f" name '{str(name)[:40]}' 에 한글이 없습니다"
            if isinstance(name, str) and reg_mod.name_label(name) is not None:
                problem += "(접두사 `[구분]` 뒤의 이름 부분에 한글이 있어야 합니다)"
            out.append(err("WF-11", f"워크플로{problem} — Actions 탭에서 이름만 보고 하는 일을 짐작할 수 있게 "
                                    "한글로 지으세요(예: '[공통] 사이트 자동 배포'). 외부 템플릿을 복사해 넣을 때는 한글 name 을 붙이세요", rel))
        jobs = data.get("jobs")
        for job_id, job in (jobs.items() if isinstance(jobs, dict) else []):
            if isinstance(job, dict) and not _has_hangul(job.get("name")):
                out.append(warn("WF-11", f"job '{job_id}' 에 name 이 없거나 한글이 없습니다 — 한글 이름을 붙이세요(예: '글 작성·게시')", rel))
    return out


# 워크플로 이름 접두사 `[구분] `의 허용 목록: 블로그 채널 라벨(레지스트리 channel.label) + 블로그에 속하지 않는 구분 둘
# (`공통` = 배포·검사·감시처럼 모든 채널이 함께 쓰는 것, `내부` = 다른 워크플로가 부르는 공용 워크플로로 직접 실행하지 않는 것)
WORKFLOW_LABELS = tuple(reg_mod.CHANNEL_LABELS) + ("공통", "내부")


def check_workflow_prefixes(root, files):
    """WF-12: 모든 워크플로의 name 은 `[구분] ` 으로 시작하고(구분 = 채널 라벨 또는 공통·내부), run-name 이 있으면 같은 접두사로 시작한다.

    Actions 왼쪽 목록은 이름순이라 접두사가 같은 워크플로끼리 붙어 보이고, 실행 목록의 제목(run-name)에서도 어느 채널의 실행인지 읽힌다
    (GitHub 에는 워크플로 폴더·분류가 없어 이름 접두사가 구분 수단이다). 워크플로 name 이 없거나 문자열이 아닌 것은 WF-11 이 알리므로
    여기서는 건너뛴다. 레지스트리 블로그의 워크플로가 자기 채널 라벨로 시작하는지는 레지스트리 검증(REG-1)이 본다. 규칙: docs/ENGINEERING_GUIDE.md W10."""
    if yaml is None:
        return []  # PyYAML 이 없다는 경고는 WF-0(check_workflows)이 이미 낸다
    out = []
    allowed = " ".join(f"[{label}]" for label in WORKFLOW_LABELS)
    for rel in _workflow_files(files):
        try:
            data = _load_yaml(read_text(root, rel) or "")
        except yaml.YAMLError:
            continue
        if not isinstance(data, dict):
            continue
        name = data.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        label = reg_mod.name_label(name)
        if label is None:
            out.append(err("WF-12", f"워크플로 name '{name[:40]}' 이 `[구분] ` 접두사로 시작하지 않습니다 — Actions 목록에서 채널별로 묶이게 "
                                    f"허용 구분({allowed}) 중 하나를 맨 앞에 붙이세요. 대괄호로 시작하는 값은 YAML 에서 따옴표가 필요합니다"
                                    "(예: name: \"[공통] 사이트 자동 배포\")", rel))
            continue
        if label not in WORKFLOW_LABELS:
            out.append(err("WF-12", f"워크플로 name 의 구분 '[{label}]' 은(는) 허용 목록에 없습니다 — 허용: {allowed}. "
                                    "새 채널이면 레지스트리 CHANNEL_LABELS(pipeline/registry.py)와 문서를 같이 고칩니다", rel))
            continue
        run_name = data.get("run-name")
        if run_name is not None and reg_mod.name_label(run_name) != label:
            shown = run_name[:40] if isinstance(run_name, str) else repr(run_name)[:40]
            out.append(err("WF-12", f"run-name '{shown}' 이 name 과 같은 접두사 `[{label}] ` 로 시작하지 않습니다 — 실행 목록의 제목에서도 "
                                    "채널이 읽히게 같은 접두사를 붙이세요", rel))
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
# REG-5 가 찾는 광고 코드 모양. pipeline/edits/checks.py 의 AD_PATTERNS 와 같은 목록이다(그쪽은 PyYAML 이 필요한 모듈이라 가져오지 않고,
# 두 목록이 같은지는 tests/test_validate_repo.py 가 대조한다).
_AD_CODE_PATTERNS = [re.compile(p, re.IGNORECASE) for p in (r"adsbygoogle", r"googlesyndication", r"ca-pub-\d+")]


def _ads_drift(root, files, blog):
    """REG-5: 레지스트리의 ads 선언이 사이트의 실제 광고 코드와 맞는지. 광고 코드를 가진 사이트가 이 저장소에 있는 jekyll-git 블로그만 본다
    (다른 플랫폼의 광고는 플랫폼 화면에서 켜므로 저장소에서는 확인할 수 없다 — 레지스트리 검증이 그쪽 on 을 막는다).
    광고 표면(protected_paths)의 파일에 광고 코드가 있으면 ads 는 on 이어야 하고, ads 가 on 이면 광고 코드가 있어야 한다."""
    if blog.get("platform") != "jekyll-git":
        return []
    protected = [p for p in blog.get("protected_paths") or [] if isinstance(p, str)]
    hits = []
    for rel in files:
        if any(rel == p or (p.endswith("/") and rel.startswith(p)) for p in protected):
            text = read_text(root, rel)
            if text and any(rx.search(text) for rx in _AD_CODE_PATTERNS):
                hits.append(rel)
    ads, key = blog.get("ads"), blog["key"]
    approval = "사용자 승인(T3)과 커밋 메시지의 'Ad-Surface-Approved: <사유>' 가 필요합니다 (G-C6·G-C10)"
    if ads == "on" and not hits:
        return [err("REG-5", f"블로그 '{key}' 는 ads=on 인데 광고 표면(protected_paths)에서 광고 코드(adsbygoogle·googlesyndication·ca-pub-)를 "
                             f"찾지 못했습니다 — 광고 코드를 일부러 뺐다면 ads 를 off 로 같이 고치세요. 둘 다 {approval}", "pipeline/blogs.json")]
    if ads != "on" and hits:
        return [err("REG-5", f"블로그 '{key}' 는 ads={ads} 인데 광고 표면에 광고 코드가 있습니다({', '.join(hits)}) — 코드가 잘못 들어간 것이면 "
                             f"빼고, 광고를 켜는 것이 맞다면 품질 게이트를 통과한 뒤 ads 를 on 으로 고치세요. 둘 다 {approval}", "pipeline/blogs.json")]
    return []


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
        out.extend(_ads_drift(root, files, blog))
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
    """제어용 이슈 양식(blog-control 라벨)의 제목이 이슈 처리 워크플로의 제목 조건과 맞는지(D-01 재발 방지).

    워크플로가 startsWith(github.event.issue.title, '…') 조건을 가지면, 제어용 양식의 제목은 그중 하나로 시작해야
    이슈를 만들었을 때 워크플로가 실행된다(라벨 조건이 함께 있으면 안전망이 되지만 제목도 맞춰 둔다).
    """
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
            if isinstance(data, dict) and isinstance(data.get("title"), str) and "blog-control" in (data.get("labels") or []):
                templates[rel] = data["title"]
    for rel in _workflow_files(files):
        text = read_text(root, rel) or ""
        prefixes = re.findall(r"startsWith\(github\.event\.issue\.title,\s*'([^']*)'\)", text)
        if not prefixes:
            continue
        for tpl, title in templates.items():
            if not any(title.startswith(p) for p in prefixes):
                out.append(warn("CONTRACT-1", f"이슈 양식 {tpl} 의 제목 '{title}' 이(가) 워크플로 조건 {prefixes} 중 어느 것으로도 시작하지 않아 "
                                              "이슈로 워크플로가 실행되지 않을 수 있습니다 (D-01)", rel))
    return out


def check_edit_system(root, files):
    """이슈 기반 수정 시스템: 명세가 금지 경로를 허용하지 않는지(SPEC-1), 양식·명세 일관성(SPEC-2), 자동 생성물 최신 여부(SYNC-1)."""
    spec_path = ".github/editorial/edit-spec.yml"
    if yaml is None or spec_path not in files:
        return []
    from pipeline.edits import forms, pages, spec as spec_mod  # noqa: PLC0415 - PyYAML 이 있을 때만 필요
    try:
        spec = spec_mod.load_spec(root)
    except spec_mod.SpecError as exc:
        return [err("SPEC-1", str(exc), spec_path)]
    problems = spec_mod.validate_spec(spec)
    if problems:
        return [err("SPEC-1", p, spec_path) for p in problems]
    out = []
    try:
        templates = forms.load_templates(root)
        forms.label_map(templates)
    except forms.FormError as exc:
        return [err("SPEC-2", str(exc), ".github/ISSUE_TEMPLATE")]
    control_labels = {lab for t in forms.control_templates(templates) for lab in t["labels"]}
    for label in spec_mod.issue_labels(spec):
        if label not in control_labels:
            out.append(err("SPEC-2", f"명세의 처리 경로 라벨 {label} 을(를) 쓰는 제어용 이슈 양식이 없습니다", spec_path))
    spec_labels = set(spec_mod.issue_labels(spec))
    for tpl in forms.control_templates(templates):
        for label in tpl["labels"]:
            if label.startswith("edit:") and label not in spec_labels:
                out.append(warn("SPEC-2", f"양식 {tpl['file']} 의 라벨 {label} 은(는) 명세에 없는 처리 경로입니다", ".github/ISSUE_TEMPLATE"))
    try:
        for message in pages.check_registry(root, spec):
            out.append(warn("SYNC-1", message, "pages.json"))
        if forms.sync_page_form(root, spec, pages.load_registry(root), write=False):
            out.append(warn("SYNC-1", "이슈 양식 드롭다운이 최신이 아닙니다 (python scripts/sync_issue_form.py)",
                            ".github/ISSUE_TEMPLATE/page-edit.yml"))
    except (pages.PagesError, forms.FormError, OSError) as exc:
        out.append(err("SPEC-2", f"페이지 레지스트리·양식을 확인할 수 없습니다: {exc}", "pages.json"))
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


def check_liquid_in_docs(root, files):
    """front matter 없는 .md 도 GitHub Pages(jekyll-optional-front-matter)가 Liquid 로 처리한다.

    문서 속 Liquid 구문(중괄호-퍼센트 태그)은 빌드를 깨뜨려 사이트 배포가 멈춘다(2026-10-20 Pages 배포 실패 사례).
    이중 중괄호는 빌드를 깨지는 않지만 빈 칸으로 렌더링돼 내용이 사라진다. 숨김 폴더(.github 등)와 `_` 폴더는 게시되지 않는다."""
    out = []
    for rel in files:
        if not rel.endswith(".md") or any(part.startswith((".", "_")) for part in rel.split("/")):
            continue
        text = read_text(root, rel) or ""
        if text.startswith("---"):  # front matter 가 있는 페이지는 Liquid 가 정상 용도다
            continue
        if "{%" in text:
            out.append(err("LIQUID-1", "front matter 없는 문서에 Liquid 태그(중괄호-퍼센트)가 있습니다 — Pages 빌드가 실행·해석해 "
                                       "배포가 실패할 수 있습니다. 문장으로 풀어 쓰거나 raw 블록으로 감싸세요", rel))
        elif "{{" in text:
            out.append(warn("LIQUID-1", "front matter 없는 문서에 이중 중괄호가 있습니다 — Liquid 출력 구문으로 처리돼 내용이 사라질 수 있습니다", rel))
    return out


_BRIEFING = "docs/REQUEST_BRIEFING.md"


def check_briefing(root, files):
    """저장소를 볼 수 없는 AI에게 주는 브리핑이 현재 블로그·워크플로·수정 항목을 빠뜨리지 않았는지(드리프트 경고).

    항목 이름이 `백틱`으로 적혀 있어야 인정한다(문장 속 우연한 일치를 막는다)."""
    if _BRIEFING not in files:
        return [warn("BRIEF-1", "저장소를 볼 수 없는 AI에게 주는 브리핑 문서가 없습니다", _BRIEFING)]
    text = read_text(root, _BRIEFING) or ""
    expected = []
    try:
        reg = reg_mod.load_registry(Path(root) / "pipeline" / "blogs.json")
        expected += [("블로그", b["key"]) for b in reg.get("blogs", []) if isinstance(b, dict) and b.get("key")]
    except reg_mod.RegistryError:
        pass  # 레지스트리 오류는 REG-* 가 알린다
    expected += [("워크플로", Path(f).name) for f in _workflow_files(files)]
    spec_path = ".github/editorial/edit-spec.yml"
    if yaml is not None and spec_path in files:
        try:
            spec = _load_yaml(read_text(root, spec_path) or "") or {}
            expected += [("수정 항목", k) for k in (spec.get("edit_types") or {})] if isinstance(spec, dict) else []
        except yaml.YAMLError:
            pass  # 명세 오류는 SPEC-1 이 알린다
    missing = [f"{kind} {name}" for kind, name in expected if f"`{name}`" not in text]
    if missing:
        return [warn("BRIEF-1", "브리핑에 현재 항목이 빠져 있습니다 — " + ", ".join(missing)
                     + " (docs/REQUEST_BRIEFING.md 갱신)", _BRIEFING)]
    return []


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
    findings += check_telegram_secrets(root, files)
    findings += check_workflow_names(root, files)
    findings += check_workflow_prefixes(root, files)
    findings += check_registry(root, files)
    findings += check_issue_contract(root, files)
    findings += check_edit_system(root, files)
    findings += check_python(root, files)
    findings += check_json(root, files)
    findings += check_doc_links(root, files)
    findings += check_agent_files(root, files)
    findings += check_briefing(root, files)
    findings += check_liquid_in_docs(root, files)
    findings += check_exposure(root, files)
    findings += check_dependencies(root, files)
    findings += check_ad_surface(root, base)
    return findings


def main(argv=None):
    safe_output()
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
