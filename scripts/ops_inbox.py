#!/usr/bin/env python3
"""확인 필요 모음(운영 인박스) 갱신 — GitHub 에서 읽고, 이슈 1개와 Actions 실행 요약에 쓴다.

운영자가 해야 할 일·확인할 일(워치독 알림, 병합 대기 PR, 실패한 워크플로, 승인 대기 실행, 일시정지, Blogger 게시 설정 등)을
한 곳에 모은다. 판단 규칙은 pipeline/inbox.py(순수 함수), 이 스크립트는 입출력만 맡는다. 설명서: docs/OPS_INBOX.md

초안 현황(작업요청서 5 PR-B): 라벨 `초안`이 붙은 열린 이슈·PR 을 읽어(최대 3쪽 × 100건) 채널별 표와 항목을 만들고, 초안 모델의 라벨(초안·폐기·채널:<채널>)이
저장소에 없으면 점검 끝에 만든다(색·설명 고정, 실패해도 점검 결과에는 영향이 없다). 워크플로는 초안 이슈·PR 이 열리고 닫히고 라벨이 바뀔 때도 이 스크립트를 부른다.

필요 환경변수: GITHUB_REPOSITORY(소유자/저장소)
쓰기에 필요: GITHUB_TOKEN (권한: contents:read, actions:read, checks:read, pull-requests:read, issues:write)
옵션: INBOX_DRY_RUN=true    이슈·코멘트·라벨을 쓰지 않는다(읽기만 하고 할 일을 출력)
      PIPELINE_PAUSE        워크플로가 저장소 변수를 넘긴다(1/true/yes/on 이면 '일시정지' 항목을 만든다)
      DEFAULT_BRANCH        실행 기록을 볼 브랜치(기본 main)
      GITHUB_REPOSITORY_OWNER  담당자·@멘션 대상(기본: 저장소 이름의 소유자)
      INBOX_MAX_API_CALLS   GitHub API 호출 상한(기본: 토큰이 있으면 150, 없으면 25. 24~1000 사이의 숫자만 받고 그 밖의 값은 기본값을 쓴다)
      GITHUB_STEP_SUMMARY   Actions 실행 요약 파일(있으면 같은 마크다운을 덧붙인다)
토큰이 없으면(로컬) 읽기 전용으로 마크다운만 출력한다(인증 없는 공개 API 는 시간당 60회 제한). 열린 이슈 목록(워치독 알림용)은 읽지만 모음 이슈는 읽지도 쓰지도 않는다.

한 소스(이슈·PR·실행 기록·주석·이력 파일)를 읽지 못해도 멈추지 않고 '조회 실패' 항목으로 남긴 뒤 계속한다.
스크립트 자체의 버그(예상 밖 예외)는 그대로 올려 실행을 빨갛게 한다.
종료 코드: 0 정상(조회 일부 실패 포함) / 1 이슈·코멘트 쓰기 실패 / 2 설정 오류
"""
import http.client
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import inbox  # noqa: E402
from pipeline.console import safe_output  # noqa: E402
from pipeline.registry import ROOT, RegistryError, load_registry, merged_blog  # noqa: E402
from pipeline.state import StateError, read_json_list  # noqa: E402

API_ROOT = "https://api.github.com"
EXIT_OK, EXIT_WRITE_FAILED, EXIT_CONFIG = 0, 1, 2
MAX_CALLS_WITH_TOKEN = 150
MAX_CALLS_ANONYMOUS = 25
WRITE_RESERVE = 8        # 이슈 찾기·라벨·본문·코멘트 쓰기에 남겨 두는 호출 수(읽기 쪽이 다 써 버리지 않게)
MIN_API_CALLS = 3 * WRITE_RESERVE      # 호출 상한의 하한(24): 쓰기용 reserve 를 온전히 남기고도 읽기에 2/3 이상을 쓸 수 있다. 더 낮으면 쓰기가 실패하거나 알림이 유실된다
MAX_API_CALLS = 1000
PULL_RETRY_WAIT_SECONDS = 3   # 병합 가능 여부(mergeable)가 아직 계산 중(null)이면 이만큼 기다렸다가 같은 점검 안에서 한 번만 다시 묻는다
MAX_WORKFLOW_CHARS = 100000   # 워크플로 파일은 앞쪽 이만큼만 읽어 최상위 name 을 찾는다
ERROR_COMMENT_FAILED = "::error::알림 코멘트를 쓰지 못했습니다. 다음 점검에서 다시 시도합니다. 이유는 실행 로그의 바로 다음 줄에 있습니다."
ERROR_ISSUE_FAILED = "::error::이슈를 읽거나 쓰지 못했습니다. 이유는 실행 로그의 바로 다음 줄에 있습니다."
# ::error:: 주석에는 이 고정 문장만 쓴다(R9). 오류 문구는 접고 마스킹한 일반 로그 줄로 따로 낸다
MAX_PULLS = 8            # PR 은 상세·검사 조회에 호출이 둘씩 들어가므로 처음 8건까지만 본다
MAX_DRAFT_PAGES = 3      # 열린 `초안` 이슈·PR 은 한 쪽 100건씩 최대 3쪽(300건)까지 읽는다(그보다 많으면 참고 항목으로 알린다)
DRAFTS_PER_PAGE = 100
MAX_LABEL_CREATES = 10   # 초안 모델 라벨을 한 번의 점검에서 새로 만드는 수의 상한(초안·폐기 + 채널 라벨 — 채널 라벨 종류가 6개라 모두 있어도 8개). 목록 읽기 1회와 합해 라벨에 쓰는 호출은 11회 이하
MAX_JOBS_PER_RUN = 6
MAX_READ_SECONDS = 300    # 읽기에 쓰는 시간 상한(잡 제한 10분 안에 쓰기까지 끝내려고). 호출 하나는 20초에서 끊긴다
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class ApiError(Exception):
    """GitHub API 호출 실패. status 는 HTTP 상태(네트워크 오류·상한 도달이면 None). 메시지에 토큰·헤더는 들어가지 않는다."""

    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


class ApiBudgetError(ApiError):
    """호출 상한(INBOX_MAX_API_CALLS)에 도달해 더 부르지 않았다."""


def _http_message(exc):
    detail = ""
    try:
        data = json.loads(exc.read().decode("utf-8", "replace"))
        if isinstance(data, dict):
            detail = str(data.get("message") or "")
    except (OSError, ValueError, AttributeError):
        detail = ""
    headers = getattr(exc, "headers", None)
    remaining = headers.get("x-ratelimit-remaining") if headers is not None else None
    if exc.code in (403, 429) and remaining == "0":
        return f"HTTP {exc.code}: API 호출 한도를 모두 썼습니다(다음 점검에서 다시 시도합니다)"
    return f"HTTP {exc.code}: {inbox.ext(detail, 160)}" if detail else f"HTTP {exc.code}"


class GitHubClient:
    """저장소 범위 GitHub REST 클라이언트(표준 라이브러리). 호출 수와 읽기 시간에 상한이 있고, 실패는 모두 ApiError 로 바꾼다.
    (scripts/watchdog.py 의 GitHubClient 와 일부 겹치지만 그쪽은 다른 PR 이 고치는 중이라 따로 둔다 — 통합은 후속 작업.)"""

    def __init__(self, repo, token=None, opener=None, max_calls=MAX_CALLS_WITH_TOKEN, reserve=0,
                 max_seconds=MAX_READ_SECONDS, clock=time.monotonic):
        self.repo, self.token, self.max_calls, self.reserve, self.calls = repo, token, max_calls, reserve, 0
        self.max_seconds, self._clock, self._reading = max_seconds, clock, True
        self._started = clock()
        self._open = opener or urllib.request.urlopen

    def remaining(self):
        """읽기에 더 쓸 수 있는 호출 수(쓰기용으로 남겨 둔 reserve 는 뺀다)."""
        return max(self.max_calls - self.reserve - self.calls, 0)

    def release_reserve(self):
        """쓰기 단계로 넘어갈 때 남겨 둔 호출을 풀어 주고, 읽기 시간 상한을 끝낸다."""
        self.reserve, self._reading = 0, False

    def request(self, method, path, params=None, payload=None):
        limit = self.max_calls - (self.reserve if method == "GET" else 0)      # 읽기는 쓰기용 reserve 를 침범하지 못한다
        if self.calls >= limit:
            raise ApiBudgetError(f"GitHub API 호출 상한({self.max_calls}회)에 도달했습니다")
        if method == "GET" and self._reading and self._clock() - self._started > self.max_seconds:
            raise ApiBudgetError(f"읽기 시간 상한({self.max_seconds}초)에 도달했습니다")
        self.calls += 1
        url = f"{API_ROOT}/repos/{self.repo}{path}" + (("?" + urllib.parse.urlencode(params)) if params else "")
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28",
                   "User-Agent": "chanceblog-ops-inbox"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        data = None
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with self._open(request, timeout=20) as resp:
                body = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            raise ApiError(_http_message(exc), status=exc.code) from None
        except (urllib.error.URLError, http.client.HTTPException, OSError, UnicodeDecodeError) as exc:
            raise ApiError(f"{type(exc).__name__}: {inbox.ext(exc, 150)}") from None
        if not body:
            return None
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            raise ApiError("응답이 JSON 이 아닙니다") from None

    def get(self, path, **params):
        return self.request("GET", path, params=params)

    def post(self, path, payload):
        return self.request("POST", path, payload=payload)

    def patch(self, path, payload):
        return self.request("PATCH", path, payload=payload)


# ----------------------------------------------------------------------------
# 읽기 1: 저장소 파일(레지스트리·이력·워크플로 목록)
# ----------------------------------------------------------------------------
def _read_error(exc):
    """파일을 읽지 못한 이유를 경로 없이 짧게 적는다(실행 환경의 절대 경로가 공개 이슈에 남지 않게)."""
    cause = exc.__cause__ if exc.__cause__ is not None else (exc if isinstance(exc, (OSError, ValueError)) else None)
    if isinstance(cause, json.JSONDecodeError):
        return f"JSON 형식 오류({inbox.fold(cause.msg, 60)}, {cause.lineno}번째 줄)"
    if isinstance(cause, FileNotFoundError):
        return "파일이 없습니다"
    if cause is not None:
        return type(cause).__name__
    return "형식이 올바르지 않습니다(최상위가 배열·객체가 아님 등)"


def read_blogs(root, failures):
    try:
        reg = load_registry(Path(root) / "pipeline" / "blogs.json")
    except RegistryError as exc:
        failures.append(("registry", f"pipeline/blogs.json: {_read_error(exc)}"))
        return []
    if not isinstance(reg, dict):
        failures.append(("registry", "pipeline/blogs.json: 최상위가 객체가 아닙니다"))
        return []
    return [merged_blog(reg, raw) for raw in reg.get("blogs", []) if isinstance(raw, dict)]


def read_histories(root, blogs, failures):
    """블로그 key → 이력 목록. 파일이 없으면 빈 목록(StateError 는 '깨진 파일'일 때만). 읽지 못한 파일은 한 줄로 모아 실패로 남긴다."""
    out, bad = {}, []
    base = Path(root).resolve()
    for blog in blogs:
        key = blog.get("key")
        rel = (blog.get("state") or {}).get("history") if isinstance(blog.get("state"), dict) else None
        if not isinstance(key, str) or not isinstance(rel, str):
            continue
        try:
            path = (base / rel).resolve()
            if not path.is_relative_to(base):      # 레지스트리의 경로가 저장소 밖을 가리키면 읽지 않는다
                bad.append(f"{key}: 경로가 저장소 밖입니다")
                continue
            out[key] = read_json_list(path)
        except (StateError, OSError, ValueError) as exc:
            bad.append(f"{rel}: {_read_error(exc)}")
    if bad:
        failures.append(("history", "; ".join(bad)))
    return out


def list_workflow_files(root):
    folder = Path(root) / ".github" / "workflows"
    if not folder.is_dir():
        return []
    return sorted({p.name for pattern in ("*.yml", "*.yaml") for p in folder.glob(pattern) if p.is_file()})


_NAME_KEY_RE = re.compile(r"^name[ \t]*:(?:[ \t]+(.*))?$")
_PLAIN_FORBIDDEN_START = "[]{}&*!|>%@`,?"         # 흐름·앵커·태그·블록 표기로 시작하는 값은 읽지 않는다


def _after_value(rest):
    """따옴표가 닫힌 뒤에는 공백과 주석('#' 앞에 공백)만 올 수 있다."""
    return not rest.strip() or (rest[0] in " \t" and rest.strip().startswith("#"))


def _scalar(value):
    value = value.strip()
    if not value or value.startswith("#"):
        return None
    if value[0] == '"':
        end = value.find('"', 1)
        if end < 0 or "\\" in value[1:end] or not _after_value(value[end + 1:]):      # 탈출(\n·\"·\u…)은 해석하지 않는다
            return None
        return value[1:end].strip() or None
    if value[0] == "'":
        chars, index = [], 1
        while index < len(value):
            if value[index] == "'":
                if value[index + 1:index + 2] != "'":
                    break
                index += 1                          # '' 는 작은따옴표 하나
            chars.append(value[index])
            index += 1
        else:
            return None                             # 닫는 따옴표가 없다
        return "".join(chars).strip() or None if _after_value(value[index + 1:]) else None
    if value[0] in _PLAIN_FORBIDDEN_START:
        return None
    cut = re.search(r"[ \t]#", value)              # 공백 뒤의 '#' 부터는 주석
    return (value[:cut.start()] if cut else value).strip() or None


def workflow_name(text):
    """워크플로 파일 본문 → 최상위 name(들여쓰기 없는 첫 'name:' 줄의 값). 표준 라이브러리만 쓰려고 YAML 전체를 해석하지 않고
    일반 문자열·작은따옴표·큰따옴표(탈출 없음)만 읽는다. 그 밖의 모양(블록·앵커·배열·탈출 문자)이거나 name 이 없으면 None."""
    if not isinstance(text, str):
        return None
    for line in re.split(r"\r\n|\r|\n", text.lstrip(chr(0xFEFF))):
        match = _NAME_KEY_RE.match(line)
        if match:
            return _scalar(match.group(1) or "")
    return None


def read_workflow_names(root, files):
    """워크플로 파일 이름 → 그 파일의 최상위 name. 체크아웃한 .github/workflows 에서 읽으므로 API 호출은 0회다. 읽지 못한 파일(없음·인코딩 오류 등)이나
    name 이 없는 파일은 빠지고, 화면에는 파일 이름이 쓰인다. 실행(run)의 name 은 run-name 이라 실행마다 다르고 옛 이름도 남아 있어 쓰지 않는다."""
    folder = Path(root) / ".github" / "workflows"
    names = {}
    for file in files:
        try:
            with open(folder / file, encoding="utf-8") as fh:
                name = workflow_name(fh.read(MAX_WORKFLOW_CHARS))
        except (OSError, ValueError):               # UnicodeDecodeError 는 ValueError 의 하위
            continue
        if name:
            names[file] = name
    return names


# ----------------------------------------------------------------------------
# 읽기 2: GitHub(소스마다 실패를 따로 처리한다)
# ----------------------------------------------------------------------------
def fetch_issues(client, failures):
    try:
        data = client.get("/issues", state="open", per_page=100)
    except ApiError as exc:
        failures.append(("issues", str(exc)))
        return []
    return [i for i in data if isinstance(i, dict) and "pull_request" not in i] if isinstance(data, list) else []


def fetch_drafts(client, failures, notes):
    """열린 `초안` 라벨 이슈·PR(GET /issues 는 PR 도 돌려준다)을 한 쪽 100건씩 최대 MAX_DRAFT_PAGES 쪽 읽어 normalize_draft 한 목록으로 돌려준다.
    어느 쪽이든 읽지 못하면 일부만 센 숫자가 '정상'으로 보이지 않게 전부 버리고 ('drafts', 사유) 하나만 남긴다(표는 그 칸을 '조회 실패'로 보인다).
    모든 쪽이 가득 차 있으면 더 있을 수 있어 참고 항목으로 알린다."""
    found = []
    for page in range(1, MAX_DRAFT_PAGES + 1):
        try:
            data = client.get("/issues", state="open", labels=inbox.DRAFT_LABEL, per_page=DRAFTS_PER_PAGE, page=page)
        except ApiError as exc:
            failures.append(("drafts", str(exc)))
            return []
        if not isinstance(data, list):
            failures.append(("drafts", "응답이 목록이 아닙니다"))
            return []
        found += data
        if len(data) < DRAFTS_PER_PAGE:
            break
    else:
        notes.append(("drafts_cap", f"열린 초안(이슈·PR)이 {MAX_DRAFT_PAGES * DRAFTS_PER_PAGE}건을 넘을 수 있어 처음 {MAX_DRAFT_PAGES * DRAFTS_PER_PAGE}건만 셉니다."))
    return [draft for draft in (inbox.normalize_draft(raw) for raw in found) if draft is not None]


def _ask_again_while_computing(client, entries, sleep):
    """GitHub 는 병합 가능 여부(mergeable)를 첫 조회 때 계산하기 시작해 null 로 답하는 일이 잦다(main 에 새 커밋이 생긴 직후). 첫 조회가 모두 끝난 뒤
    한 번만 기다렸다가(그동안의 호출도 기다림이 된다) null 인 PR 의 상세만 한 번 더 묻는다. 읽기 호출 상한 안에서만 하고, 실패하면 첫 답을 그대로 쓴다."""
    waiting = [e for e in entries if not e[3] and isinstance(e[1], dict) and e[1].get("mergeable") is None]
    if not waiting or client.remaining() < 1:
        return
    sleep(PULL_RETRY_WAIT_SECONDS)
    for entry in waiting:
        try:
            detail = client.get(f"/pulls/{entry[0].get('number')}")
        except ApiError:                            # 호출 상한 도달(ApiBudgetError)이나 일시 오류 — 첫 답을 그대로 쓴다
            continue
        if isinstance(detail, dict):
            entry[1] = detail


def fetch_pulls(client, failures, notes, sleep=time.sleep):
    try:
        listing = client.get("/pulls", state="open", per_page=50)
    except ApiError as exc:
        failures.append(("pulls", str(exc)))
        return []
    open_prs = [p for p in listing if isinstance(p, dict) and not p.get("draft")] if isinstance(listing, list) else []
    entries, errors = [], []            # entries: [원본 PR, 상세, 검사 목록, 오류]
    for raw in open_prs[:MAX_PULLS]:
        number = raw.get("number")
        if not isinstance(number, int) or isinstance(number, bool):
            continue
        detail, checks, error = None, None, ""
        try:
            detail = client.get(f"/pulls/{number}")
            sha = (raw.get("head") or {}).get("sha") if isinstance(raw.get("head"), dict) else None
            if isinstance(sha, str) and _SHA_RE.fullmatch(sha):
                result = client.get(f"/commits/{sha}/check-runs", per_page=100)
                checks = result.get("check_runs") if isinstance(result, dict) else None
        except ApiError as exc:
            error = str(exc)
            errors.append(error)
        entries.append([raw, detail, checks, error])
    _ask_again_while_computing(client, entries, sleep)
    pulls = [inbox.normalize_pull(raw, detail, checks, error) for raw, detail, checks, error in entries]
    if len(open_prs) > MAX_PULLS:
        notes.append(("pulls_cap", f"열린 PR {len(open_prs)}건 중 처음 {MAX_PULLS}건만 확인했습니다."))
    if errors:
        failures.append(("pull_details", errors[0] + (f" (외 {len(errors) - 1}건)" if len(errors) > 1 else "")))
    return pulls


def fetch_runs(client, files, now, branch, failures, repo=None):
    """워크플로 파일마다 기본 브랜치의 최근 실행(48시간 창). 기본 브랜치에 아직 없는 파일(404)은 기록 없음으로 본다.
    포크 PR 이 일으킨 실행은 읽자마자 뺀다(head 브랜치가 main 이면 섞여 들 수 있다 — 판단에도, 경고(주석) 읽기에도 쓰지 않게)."""
    repo = repo or getattr(client, "repo", "")
    since = (now - timedelta(hours=inbox.RUN_WINDOW_HOURS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    runs, errors = {}, []
    for file in files:
        if file == inbox.OWN_WORKFLOW:
            continue
        try:
            data = client.get(f"/actions/workflows/{urllib.parse.quote(file, safe='')}/runs", branch=branch,
                              per_page=inbox.RUNS_PER_FILE, created=f">={since}")
        except ApiBudgetError as exc:
            errors.append(f"{file}: {exc}")
            break
        except ApiError as exc:
            if exc.status == 404:
                runs[file] = []
            else:
                errors.append(f"{file}: {exc}")
            continue
        found = data.get("workflow_runs") if isinstance(data, dict) else None
        runs[file] = [r for r in found if isinstance(r, dict) and not inbox.foreign_pull_run(r, repo)] if isinstance(found, list) else []
    if errors:
        failures.append(("runs", errors[0] + (f" (외 {len(errors) - 1}개 워크플로)" if len(errors) > 1 else "")))
    return runs


def fetch_approvals(client, failures):
    try:
        data = client.get("/actions/runs", status="action_required", per_page=20)
    except ApiError as exc:
        failures.append(("approvals", str(exc)))
        return []
    found = data.get("workflow_runs") if isinstance(data, dict) else None
    return [r for r in found if isinstance(r, dict)] if isinstance(found, list) else []


def fetch_annotations(client, runs, now, failures, notes):
    """파일마다 최근 성공 실행 3건의 job 주석을 읽는다(전체에서 가장 최근 것부터, 남은 호출 수가 모자라면 멈추고 알린다).
    주석은 GET .../runs/{id}/jobs 로 job id 를 얻고 GET .../check-runs/{job_id}/annotations 로 읽는다(공개 저장소는 인증 없이도 읽힌다)."""
    targets = []
    for file_runs in runs.values():
        done = [r for r in file_runs
                if r.get("status") == "completed" and r.get("conclusion") == "success"
                and isinstance(r.get("id"), int) and inbox.parse_time(r.get("created_at")) is not None
                and now - inbox.parse_time(r.get("created_at")) <= timedelta(hours=inbox.RUN_WINDOW_HOURS)]
        done.sort(key=lambda r: inbox.parse_time(r["created_at"]), reverse=True)
        targets += done[:inbox.ANNOTATION_RUNS_PER_FILE]
    targets.sort(key=lambda r: inbox.parse_time(r["created_at"]), reverse=True)
    annotations, errors, skipped = {}, [], 0
    for index, run in enumerate(targets):
        if client.remaining() < 2:                  # job 목록 1회 + 주석 1회는 있어야 읽을 의미가 있다
            skipped = len(targets) - index
            break
        found = []
        try:
            jobs = client.get(f"/actions/runs/{run['id']}/jobs", per_page=30)
            job_ids = [j["id"] for j in (jobs.get("jobs") if isinstance(jobs, dict) else None) or []
                       if isinstance(j, dict) and isinstance(j.get("id"), int)][:MAX_JOBS_PER_RUN]
            for job_id in job_ids:
                if client.remaining() < 1:
                    break
                anns = client.get(f"/check-runs/{job_id}/annotations", per_page=50)
                found += [a for a in anns if isinstance(a, dict)] if isinstance(anns, list) else []
            annotations[run["id"]] = found
        except ApiBudgetError as exc:
            errors.append(str(exc))
            skipped = len(targets) - index
            break
        except ApiError as exc:
            errors.append(f"실행 {run['id']}: {exc}")
    if skipped:
        notes.append(("annotations_cap", f"실행 경고(주석)는 API 호출 상한 때문에 {skipped}건을 읽지 못했습니다."))
    if errors:
        failures.append(("annotations", errors[0] + (f" (외 {len(errors) - 1}건)" if len(errors) > 1 else "")))
    return annotations


# ----------------------------------------------------------------------------
# 쓰기: 이슈 1개 유지
# ----------------------------------------------------------------------------
def find_inbox_issue(client):
    """모음 이슈(열림·닫힘 모두)를 찾는다. 라벨 ops-inbox 가 붙은 이슈를 먼저 찾고(사람이 제목을 바꿔도 같은 이슈로 본다),
    없으면 봇이 만든 이슈에서 같은 제목을 찾는다(라벨을 지웠거나 라벨 생성이 실패했던 경우).
    작성자가 봇·소유자·멤버·협업자가 아닌 이슈는 무시한다(낯선 사람이 같은 제목으로 위장). 열린 것 우선, 같은 상태면 번호가 작은 것."""
    def pick(data, same_title):
        found = [i for i in (data if isinstance(data, list) else []) if isinstance(i, dict) and "pull_request" not in i
                 and (not same_title or i.get("title") == inbox.ISSUE_TITLE) and inbox.trusted_author(i) and isinstance(i.get("number"), int)]
        return sorted(found, key=lambda i: (i.get("state") != "open", i["number"]))

    found = pick(client.get("/issues", labels=inbox.LABEL, state="all", per_page=30), same_title=False)
    if not found:
        found = pick(client.get("/issues", state="all", creator=inbox.BOT_LOGIN, per_page=100), same_title=True)
    return found[0] if found else None


def ensure_label(client, out):
    try:
        client.post("/labels", {"name": inbox.LABEL, "color": inbox.LABEL_COLOR, "description": inbox.LABEL_DESCRIPTION})
    except ApiError as exc:
        if exc.status != 422:                       # 422 = 이미 있음
            out(f"[참고] 라벨 {inbox.LABEL} 을 만들지 못했습니다(계속 진행합니다): {inbox.ext(exc, 200)}")


def ensure_draft_labels(client, specs, out):
    """초안 모델의 라벨(초안·폐기·채널:<채널>)이 저장소에 없으면 만든다 — 이름·색·설명은 고정(inbox.draft_label_specs). 운영자가 휴대폰에서 라벨을 고르고
    초안 목록을 거르려면 라벨이 미리 있어야 한다. 점검 끝에 하는 '있으면 좋은' 일이라 실패해도 점검 결과·종료 코드에는 영향이 없다(로그 한 줄만, 다음 점검이 다시 시도).
    라벨 목록을 한 번 읽어(GET /labels, 100건) 없는 것만 만든다 — 목록을 못 읽으면 모두 만들기를 시도하고 이미 있는 것은 422 로 끝난다.
    422 가 아닌 오류(권한·서버 오류)나 호출 상한에서는 거기서 멈춘다 — 같은 원인이 나머지 라벨에도 똑같이 나서 줄만 늘기 때문이다(다음 점검이 이어서 만든다).
    한 번에 만드는 수는 MAX_LABEL_CREATES 이하."""
    existing = set()
    try:
        data = client.get("/labels", per_page=100)
        existing = {str(label.get("name") or "").casefold() for label in data if isinstance(label, dict)} if isinstance(data, list) else set()
    except ApiBudgetError as exc:
        out(f"[참고] 초안 라벨 목록을 읽지 못해 라벨 확인을 건너뜁니다(다음 점검에서 다시 시도합니다): {inbox.ext(exc, 200)}")
        return
    except ApiError:
        existing = set()
    made = []
    for spec in specs:
        if spec["name"].casefold() in existing:
            continue
        if len(made) >= MAX_LABEL_CREATES:
            break
        try:
            client.post("/labels", {"name": spec["name"], "color": spec["color"], "description": spec["description"]})
            made.append(spec["name"])
        except ApiError as exc:
            if exc.status == 422:                   # 422 = 이미 있음(목록을 못 읽었거나 사이에 누가 만들었다)
                continue
            out(f"[참고] 초안 라벨 {inbox.ext(spec['name'], 60)} 을 만들지 못해 라벨 만들기를 멈춥니다(다음 점검에서 이어서 만듭니다): {inbox.ext(exc, 200)}")
            break
    if made:
        out(f"[라벨] 초안 모델의 라벨 {len(made)}개를 만들었습니다: {', '.join(inbox.ext(name, 60) for name in made)}")


def create_issue(client, body, owner, out):
    """이슈를 만든다. 담당자 지정이 거부되면(HTTP 422) 담당자 없이 한 번 더 만든다 — 담당자 하나 때문에 모음 자체가 없어지면 안 된다."""
    payload = {"title": inbox.ISSUE_TITLE, "body": body, "labels": [inbox.LABEL]}
    if owner:
        payload["assignees"] = [owner]
    try:
        return client.post("/issues", payload)
    except ApiError as exc:
        if not owner or exc.status != 422:
            raise
        out(f"[참고] 담당자({owner}) 지정이 거부되어(HTTP 422) 담당자 없이 이슈를 만듭니다.")
    payload.pop("assignees")
    return client.post("/issues", payload)


def post_comment(client, number, text, out):
    try:
        client.post(f"/issues/{number}/comments", {"body": text})
        return True
    except ApiError as exc:
        out(ERROR_COMMENT_FAILED)
        out(f"[코멘트 실패 이유] {inbox.ext(exc, 200)}")
        return False


def sync_issue(client, items, visible, failures, owner, repo_url, dry, out):
    """이슈 1개를 만들거나 고친다. 돌려주는 값: {'action': ..., 'number': 번호|None, 'new': 새 action 항목 수, 'comment': ...}.

    - 본문은 내용(보이는 마크다운의 해시)이나 알린 action id 가 바뀐 때만 PATCH 한다.
    - 새로 생긴 action 항목이 있을 때만 코멘트(@멘션)를 쓴다. 코멘트를 먼저 쓰고 본문을 고친다 — 코멘트가 실패하면 표식에서
      그 id 를 빼 다음 점검이 다시 알리게 한다(알림을 놓치는 쪽보다 한 번 더 알리는 쪽이 낫다).
    - 이슈를 처음 만들 때는 알린 id 없이 만들고, 코멘트가 성공한 뒤에야 본문을 고쳐 id 를 적는다. 먼저 적어 두면 코멘트 실패 뒤의
      복구 쓰기까지 실패했을 때 id 가 표식에 남아 첫 알림이 영영 사라진다. 성공한 뒤의 쓰기가 실패하면 한 번 더 알리게 된다(놓치는 것보다 낫다).
    - 사람이 닫은 이슈는 새 action 항목이 생겼을 때만 코멘트와 함께 다시 연다. 그 밖의 변화는 닫힌 채로 본문만 고쳐 둔다
      (본문 수정은 알림이 없고, 표식이 현실을 따라가야 '해소됐다가 다시 생긴' 항목을 새 항목으로 알릴 수 있다).
    - 연습(dry)이면 읽기만 하고 아무것도 쓰지 않는다."""
    issue = find_inbox_issue(client)
    marker = inbox.parse_marker(issue.get("body")) if issue else None
    new_ids, kept_ids = inbox.plan_notice(items, marker.items if marker else None, failures)
    new_items = [i for i in items if i.id in new_ids]
    result = {"action": "unchanged", "number": issue["number"] if issue else None, "new": len(new_items), "comment": "none"}
    closed = bool(issue) and issue.get("state") != "open"
    reopen = closed and bool(new_items)

    if dry:
        result["action"] = "would_create" if not issue else ("would_reopen" if reopen else (
            "would_update" if inbox.needs_update(marker, visible, kept_ids) else "unchanged"))
        result["comment"] = "dry" if new_items else "none"
        return result

    if issue is None:
        ensure_label(client, out)
        created = create_issue(client, inbox.build_body(visible, [i for i in kept_ids if i not in new_ids]), owner, out)      # 아직 알리지 못한 id 는 표식에 없다
        number = created.get("number") if isinstance(created, dict) else None
        if not isinstance(number, int):
            raise ApiError("이슈를 만들었지만 번호를 읽지 못했습니다")
        result.update(action="created", number=number)
        if new_items:
            ok = post_comment(client, number, inbox.comment_text(owner, new_items, f"{repo_url}/issues/{number}"), out)
            result["comment"] = "posted" if ok else "failed"
            if ok:  # 알렸으니 이제 표식에 id 를 적는다(실패하면 다음 점검이 한 번 더 알린다)
                client.patch(f"/issues/{number}", {"body": inbox.build_body(visible, kept_ids)})
        return result

    number = issue["number"]
    final_ids = kept_ids
    if new_items:
        ok = post_comment(client, number, inbox.comment_text(owner, new_items, f"{repo_url}/issues/{number}"), out)
        result["comment"] = "posted" if ok else "failed"
        if not ok:
            final_ids = [i for i in kept_ids if i not in new_ids]
    if reopen or inbox.needs_update(marker, visible, final_ids):
        payload = {"body": inbox.build_body(visible, final_ids)}
        if reopen:
            payload["state"] = "open"
        client.patch(f"/issues/{number}", payload)
        result["action"] = "reopened" if reopen else ("updated_closed" if closed else "updated")
    return result


_RESULT_TEXT = {
    "created": "이슈를 새로 만들었습니다", "updated": "이슈 본문을 갱신했습니다", "unchanged": "변경 없음(이슈를 쓰지 않았습니다)",
    "reopened": "닫혀 있던 이슈를 다시 열고 본문을 갱신했습니다", "updated_closed": "닫혀 있는 이슈의 본문만 갱신했습니다(다시 열지 않음)",
    "would_create": "(연습) 이슈를 새로 만들 예정입니다", "would_update": "(연습) 이슈 본문을 갱신할 예정입니다",
    "would_reopen": "(연습) 닫힌 이슈를 다시 열 예정입니다",
}
_COMMENT_TEXT = {"posted": "알림 코멘트 작성", "failed": "알림 코멘트 실패(다음 점검에서 다시 시도)", "dry": "(연습) 알림 코멘트를 쓸 예정", "none": "새 알림 없음"}


def describe(result):
    number = f" #{result['number']}" if result.get("number") else ""
    return f"{_RESULT_TEXT.get(result['action'], result['action'])}{number} · 새 해야 할 일 {result['new']}건 · {_COMMENT_TEXT[result['comment']]}"


# ----------------------------------------------------------------------------
# 실행
# ----------------------------------------------------------------------------
def _int_env(value, default, low, high):
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    return number if low <= number <= high else default


def _write_summary(environ, text, out):
    target = environ.get("GITHUB_STEP_SUMMARY")
    if not target:
        return
    try:
        with open(target, "a", encoding="utf-8") as fh:
            fh.write(text.rstrip() + "\n\n")
    except OSError as exc:
        out(f"[참고] 실행 요약 쓰기 실패(점검 결과에는 영향 없음): {inbox.fold(exc, 150)}")


def run(environ=None, client=None, now=None, root=ROOT, out=print, sleep=time.sleep):
    environ = os.environ if environ is None else environ
    repo = (environ.get("GITHUB_REPOSITORY") or "").strip()
    if not inbox.is_valid_repo(repo):
        out("[설정 오류] GITHUB_REPOSITORY(예: 소유자/저장소)를 환경변수로 지정하세요.")
        return EXIT_CONFIG
    token = (environ.get("GITHUB_TOKEN") or "").strip()
    dry = inbox.is_truthy(environ.get("INBOX_DRY_RUN"))
    owner = (environ.get("GITHUB_REPOSITORY_OWNER") or repo.split("/")[0]).strip()
    branch = (environ.get("DEFAULT_BRANCH") or "").strip() or "main"
    now = now or datetime.now(timezone.utc)
    raw_cap = (environ.get("INBOX_MAX_API_CALLS") or "").strip()
    cap = _int_env(raw_cap, None, MIN_API_CALLS, MAX_API_CALLS)
    if cap is None:
        cap = MAX_CALLS_WITH_TOKEN if token else MAX_CALLS_ANONYMOUS
        if raw_cap:
            out(f"[참고] INBOX_MAX_API_CALLS 는 {MIN_API_CALLS}~{MAX_API_CALLS} 사이의 숫자여야 해서 기본값 {cap}회를 씁니다(받은 값: {inbox.fold(raw_cap, 20)}).")
    if client is None:
        client = GitHubClient(repo, token or None, max_calls=cap, reserve=WRITE_RESERVE if token else 0)
    repo_url = f"https://github.com/{repo}"

    failures, notes = [], []
    blogs = read_blogs(root, failures)
    histories = read_histories(root, blogs, failures)
    issues = fetch_issues(client, failures)
    pulls = fetch_pulls(client, failures, notes, sleep)
    drafts = fetch_drafts(client, failures, notes)
    files = list_workflow_files(root)
    names = read_workflow_names(root, files)
    runs = fetch_runs(client, files, now, branch, failures, repo)
    approvals = fetch_approvals(client, failures)
    annotations = fetch_annotations(client, runs, now, failures, notes)
    snapshot = inbox.Snapshot(
        now=now, repo=repo, issues=issues, pulls=pulls, runs=runs, approvals=approvals, annotations=annotations,
        paused=inbox.is_truthy(environ.get("PIPELINE_PAUSE")), blogs=blogs, histories=histories, failures=failures, notes=notes,
        workflow_names=names, drafts=drafts)
    items = inbox.build_items(snapshot)
    board = inbox.draft_board(snapshot)

    counts = {level: sum(1 for i in items if i.level == level) for level in inbox.LEVELS}
    out(f"[점검] 지금 해야 할 일 {counts['action']}건 · 확인하면 좋은 것 {counts['check']}건 · 참고 {counts['info']}건 "
        f"(조회 실패 {len(failures)}건, GitHub API 호출 {getattr(client, 'calls', 0)}회)")
    visible = inbox.render(items, repo_url, inbox.BODY_LIMIT, board=board)
    summary_md = inbox.render(items, repo_url, inbox.SUMMARY_LIMIT, board=board)
    out(summary_md)
    _write_summary(environ, summary_md, out)

    if not token:
        out("(토큰이 없어 읽기 전용으로 끝냅니다 — 열린 이슈 목록은 읽었지만 모음 이슈는 읽지도 쓰지도 않았습니다)")
        _write_summary(environ, "### 이번 점검\n- 토큰이 없어 읽기 전용으로 끝냈습니다(이슈를 쓰지 않음).", out)
        return EXIT_OK
    release = getattr(client, "release_reserve", None)
    if callable(release):
        release()                                   # 쓰기 단계에서는 남겨 둔 호출도 쓴다
    try:
        result = sync_issue(client, items, visible, failures, owner, repo_url, dry, out)
    except ApiError as exc:
        out(ERROR_ISSUE_FAILED)
        out(f"[이슈 오류 이유] {inbox.ext(exc, 200)}")
        _write_summary(environ, f"### 이번 점검\n- **이슈를 읽거나 쓰지 못했습니다**: {inbox.ext(exc, 200)}", out)
        return EXIT_WRITE_FAILED
    if not dry:
        ensure_draft_labels(client, inbox.draft_label_specs(blogs), out)       # 이슈를 쓴 뒤에 한다 — 있으면 좋은 일이 이슈 쓰기에 쓸 호출을 먹지 않게
    line = describe(result)
    out(f"[이슈] {line}")
    _write_summary(environ, f"### 이번 점검\n- 점검 시각: {inbox.fmt_kst(now)} · GitHub API 호출 {getattr(client, 'calls', 0)}회\n"
                            f"- 이슈: {line}" + ("\n- 연습 실행이라 이슈·코멘트를 쓰지 않았습니다." if dry else ""), out)
    return EXIT_WRITE_FAILED if result["comment"] == "failed" else EXIT_OK


def main():
    safe_output()
    return run()


if __name__ == "__main__":
    sys.exit(main())
