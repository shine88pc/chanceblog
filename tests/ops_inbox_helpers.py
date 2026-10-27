"""확인 필요 모음 테스트 공통: 가짜 GitHub 클라이언트와 자료 만들기(네트워크 없음).

FakeGitHub 는 scripts/ops_inbox.GitHubClient 와 같은 모양(get·post·patch·remaining·calls)을 가진 메모리 속 GitHub 다.
모르는 경로를 부르면 AssertionError 를 내서(스크립트 버그) 테스트가 조용히 지나가지 않게 한다.
"""
import copy
import json
import re
import sys
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

import _bootstrap

sys.path.insert(0, str(_bootstrap.ROOT / "scripts"))
import ops_inbox  # noqa: E402

REPO = "octo/blog"
REPO_URL = f"https://github.com/{REPO}"
NOW = datetime(2026, 10, 25, 6, 0, tzinfo=timezone.utc)      # KST 2026-10-25 15:00
BOT = "github-actions[bot]"
SHA = "a" * 40


def iso(moment):
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ago(**delta):
    return iso(NOW - timedelta(**delta))


# ---------------------------------------------------------------- 자료 만들기
def make_issue(number, title, body="", state="open", login=BOT, assoc="CONTRIBUTOR", labels=(), created=None, pull=False):
    issue = {"number": number, "title": title, "body": body, "state": state, "html_url": f"{REPO_URL}/issues/{number}",
             "user": {"login": login, "type": "Bot" if login.endswith("[bot]") else "User"},
             "author_association": assoc, "labels": [{"name": name} for name in labels], "created_at": created or ago(hours=30)}
    if pull:
        issue["pull_request"] = {"url": "x"}
    return issue


def watchdog_body(blog="chance", code="STALE", severity="critical", message="마지막 활동 이후 42시간 경과 (허용 36시간)."):
    return (f"**블로그**: `{blog}` / **코드**: `{code}` / **심각도**: {severity}\n\n{message}\n\n"
            "이 이슈는 워치독(`scripts/watchdog.py`)이 자동으로 만들었고, 문제가 해소되면 자동으로 닫힙니다.\n"
            "대응 절차: `HANDLER.md` §10")


def make_watchdog(number, blog="chance", code="STALE", severity="critical", message="마지막 활동 이후 42시간 경과 (허용 36시간).", **kw):
    return make_issue(number, f"[Watchdog] {blog}: {code}", watchdog_body(blog, code, severity, message), labels=("watchdog",), **kw)


def make_pull_raw(number, title="변경 제안", login="octo", user_type="User", assoc="OWNER", draft=False, created=None, sha=SHA,
                  ref="ai/claude/topic", fork=False):
    base_repo = {"full_name": REPO}
    head_repo = {"full_name": "stranger/blog"} if fork else {"full_name": REPO}
    return {"number": number, "title": title, "draft": draft, "user": {"login": login, "type": user_type},
            "author_association": assoc, "created_at": created or ago(hours=5), "html_url": f"{REPO_URL}/pull/{number}",
            "head": {"ref": ref, "sha": sha, "repo": head_repo}, "base": {"ref": "main", "repo": base_repo}}


def make_pull(number, ci="pass", mergeable=True, state="clean", **kw):
    """규칙이 읽는 평평한 PR dict (normalize_pull 결과와 같은 모양)."""
    raw = make_pull_raw(number, **kw)
    checks = {"pass": [make_check("validate")], "fail": [make_check("validate", "failure")],
              "pending": [make_check("validate", None, "in_progress")], "none": [], "unknown": None}[ci]
    from pipeline import inbox
    return inbox.normalize_pull(raw, {"mergeable": mergeable, "mergeable_state": state}, checks)


def make_check(name, conclusion="success", status="completed"):
    return {"name": name, "status": status, "conclusion": conclusion}


def make_run(run_id, created=None, conclusion="success", status="completed", name="Chance 글 작성", path=".github/workflows/chanceblog.yml",
             event="schedule", branch="main", sha=SHA, title=None, head_repo=REPO):
    return {"id": run_id, "name": name, "display_title": title or name, "path": path, "status": status, "conclusion": conclusion,
            "event": event, "head_branch": branch, "head_sha": sha, "created_at": created or ago(hours=3),
            "head_repository": {"full_name": head_repo}, "html_url": f"{REPO_URL}/actions/runs/{run_id}"}


def make_annotation(message, level="warning", title=""):
    return {"annotation_level": level, "message": message, "title": title, "path": ".github"}


def make_blog(key="blogger_macat", name="Blogger", mode="auto", platform="blogger", history=None, secrets=None, **extra):
    blog = {"key": key, "name": name, "mode": mode, "platform": platform,
            "state": {"history": history or f"{key}_history.json", "content_dir": "drafts"},
            "secrets": secrets or {"llm_api_key": "GEMINI_API_KEY", "blog_id": "BLOGGER_BLOG_ID", "client_id": "BLOGGER_CLIENT_ID",
                                   "client_secret": "BLOGGER_CLIENT_SECRET", "refresh_token": "BLOGGER_REFRESH_TOKEN"}}
    blog.update(extra)
    return blog


def make_entry(status="posted", generated_at=None, reasons=(), date=None, slot=None, **extra):
    entry = {"status": status, "reasons": reasons if reasons is None or isinstance(reasons, str) else list(reasons)}
    if generated_at:
        entry["generated_at"] = generated_at
    if date:
        entry["date"] = date
    if slot is not None:
        entry["slot"] = slot
    entry.update(extra)
    return entry


SECRETS_REASON = "[SECRETS] 게시 시크릿 미등록: blog_id, client_id, client_secret, refresh_token"


def make_draft_raw(number, title="[초안][티스토리] 시험 글", channel="티스토리", hours=30, pull=False, extra_labels=(), state="open", login=BOT,
                   assoc="CONTRIBUTOR", draft_label=True, created=None):
    """GitHub 이슈(또는 pull=True 면 PR) 객체 모양의 초안: 라벨 `초안` + `채널:<channel>`(channel 이 None 이면 채널 라벨 없음)."""
    labels = (["초안"] if draft_label else []) + ([f"채널:{channel}"] if channel else []) + list(extra_labels)
    return make_issue(number, title, state=state, login=login, assoc=assoc, labels=labels, created=created or ago(hours=hours), pull=pull)


def make_draft(number, title="[초안][티스토리] 시험 글", channel="티스토리", **kw):
    """규칙이 읽는 평평한 초안 dict(inbox.normalize_draft 결과)."""
    from pipeline import inbox
    return inbox.normalize_draft(make_draft_raw(number, title, channel, **kw))


def channel_blog(key, label, platform="tistory", mode="package", name=None, history=None, **extra):
    """초안 현황 시험용 레지스트리 블로그(기본값 병합본 모양): channel.label 이 있다."""
    blog = make_blog(key, name or label, mode, platform, history=history, channel={"key": key, "label": label}, **extra)
    return blog


# ---------------------------------------------------------------- 가짜 GitHub
class FakeGitHub:
    def __init__(self, max_calls=1000, reserve=0):
        self.repo, self.calls, self.max_calls, self.reserve = REPO, 0, max_calls, reserve
        self.log = []                  # [(method, path, params 또는 payload)]
        self.issues = []               # 이슈·PR(pull=True) dict
        self.pulls = []                # 목록용 PR dict (make_pull_raw)
        self.details = {}              # PR 번호 → 상세 dict (목록이면 호출마다 차례로 돌려주고 마지막 것을 반복, 예외 값이면 그 호출에서 낸다)
        self.check_runs = {}           # sha → check run 목록
        self.runs = {}                 # 워크플로 파일 → 실행 목록(없는 파일은 404)
        self.approvals = []
        self.jobs = {}                 # 실행 id → job 목록
        self.annotations = {}          # job id → 주석 목록
        self.labels = set()            # 저장소에 있는 라벨 이름(GET /labels 가 돌려주고, POST /labels 가 더한다)
        self.label_payloads = {}       # POST /labels 로 만든 라벨 이름 → 보낸 내용(색·설명)
        self.comments = {}             # 이슈 번호 → [본문]
        self.fail = []                 # [(정규식, ApiError)] — "METHOD /경로?쿼리" 에 맞으면 그 오류를 낸다(쓰기는 쿼리 없음)
        self.reject_assignees = False  # True 면 담당자가 든 이슈 생성을 422 로 거부
        self.next_number = 200

    # --- 공통
    def remaining(self):
        return max(self.max_calls - self.reserve - self.calls, 0)

    def release_reserve(self):
        self.reserve = 0

    def _enter(self, method, path, data):
        if self.calls >= self.max_calls - (self.reserve if method == "GET" else 0):
            raise ops_inbox.ApiBudgetError("상한")
        self.calls += 1
        self.log.append((method, path, copy.deepcopy(data)))
        target = f"{method} {path}" + (("?" + urllib.parse.urlencode(data)) if method == "GET" and data else "")
        for pattern, error in self.fail:
            if re.search(pattern, target):
                raise error

    def writes(self):
        return [entry for entry in self.log if entry[0] in ("POST", "PATCH")]

    def paths(self, method="GET"):
        return [path for m, path, _ in self.log if m == method]

    def find(self, number):
        return next(i for i in self.issues if i["number"] == number)

    # --- 읽기
    def get(self, path, **params):
        self._enter("GET", path, params)
        if path == "/issues":
            return copy.deepcopy(self._list_issues(params))
        if path == "/pulls":
            return copy.deepcopy(self.pulls)
        match = re.fullmatch(r"/pulls/(\d+)", path)
        if match:
            if int(match.group(1)) not in self.details:
                raise ops_inbox.ApiError("HTTP 404", status=404)
            detail = self.details[int(match.group(1))]
            if isinstance(detail, list):
                detail = detail.pop(0) if len(detail) > 1 else detail[0]
            if isinstance(detail, BaseException):
                raise detail
            return copy.deepcopy(detail)
        match = re.fullmatch(r"/commits/([0-9a-f]{40})/check-runs", path)
        if match:
            runs = self.check_runs.get(match.group(1), [])
            return {"total_count": len(runs), "check_runs": copy.deepcopy(runs)}
        match = re.fullmatch(r"/actions/workflows/([^/]+)/runs", path)
        if match:
            if match.group(1) not in self.runs:
                raise ops_inbox.ApiError("HTTP 404", status=404)
            return {"workflow_runs": copy.deepcopy(self.runs[match.group(1)][:params.get("per_page", 30)])}
        if path == "/actions/runs":
            assert params.get("status") == "action_required", params
            return {"workflow_runs": copy.deepcopy(self.approvals)}
        match = re.fullmatch(r"/actions/runs/(\d+)/jobs", path)
        if match:
            return {"jobs": copy.deepcopy(self.jobs.get(int(match.group(1)), []))}
        match = re.fullmatch(r"/check-runs/(\d+)/annotations", path)
        if match:
            return copy.deepcopy(self.annotations.get(int(match.group(1)), []))
        if path == "/labels":
            return [{"name": name, "color": "ededed"} for name in sorted(self.labels)][:params.get("per_page", 30)]
        raise AssertionError(f"가짜 GitHub 가 모르는 GET {path}")

    def _list_issues(self, params):
        out = []
        for issue in self.issues:
            if params.get("state", "open") != "all" and issue["state"] != params.get("state", "open"):
                continue
            if "labels" in params and params["labels"] not in [label["name"] for label in issue["labels"]]:
                continue
            if "creator" in params and issue["user"]["login"] != params["creator"]:
                continue
            out.append(issue)
        per_page, page = params.get("per_page", 30), params.get("page", 1)         # GitHub 처럼 쪽은 1부터 센다
        return out[(page - 1) * per_page:page * per_page]

    # --- 쓰기
    def post(self, path, payload):
        self._enter("POST", path, payload)
        if path == "/labels":
            if payload["name"].casefold() in {name.casefold() for name in self.labels}:         # GitHub 라벨 이름은 대소문자를 구분하지 않고 하나뿐이다
                raise ops_inbox.ApiError("HTTP 422: already_exists", status=422)
            self.labels.add(payload["name"])
            self.label_payloads[payload["name"]] = copy.deepcopy(payload)
            return {"name": payload["name"]}
        if path == "/issues":
            if self.reject_assignees and payload.get("assignees"):
                raise ops_inbox.ApiError("HTTP 422: Validation Failed", status=422)
            number = self.next_number
            self.next_number += 1
            issue = make_issue(number, payload["title"], payload.get("body", ""), labels=payload.get("labels", []))
            issue["assignees"] = payload.get("assignees", [])
            self.issues.append(issue)
            return copy.deepcopy(issue)
        match = re.fullmatch(r"/issues/(\d+)/comments", path)
        if match:
            self.comments.setdefault(int(match.group(1)), []).append(payload["body"])
            return {"id": 1}
        raise AssertionError(f"가짜 GitHub 가 모르는 POST {path}")

    def patch(self, path, payload):
        self._enter("PATCH", path, payload)
        match = re.fullmatch(r"/issues/(\d+)", path)
        if not match:
            raise AssertionError(f"가짜 GitHub 가 모르는 PATCH {path}")
        issue = self.find(int(match.group(1)))
        issue.update(payload)
        return copy.deepcopy(issue)


# ---------------------------------------------------------------- 임시 저장소
# 실제 pipeline/blogs.json 은 다른 변경(예: Blogger mode 조정)으로 바뀔 수 있으므로 테스트는 같은 모양의 가짜 레지스트리를 쓴다.
SYNTHETIC_REGISTRY = json.dumps({
    "schema_version": 1,
    "defaults": {"mode": "draft"},
    "blogs": [
        {"key": "chance", "name": "Chance_Blog", "platform": "jekyll-git", "mode": "auto",
         "state": {"history": "history.json", "content_dir": "_posts"}, "secrets": {"llm_api_key": "GEMINI_API_KEY"}},
        {"key": "blogger_macat", "name": "Blogger (macat0722)", "platform": "blogger", "mode": "auto",
         "state": {"history": "blogger_history.json", "content_dir": "_blogger_drafts"},
         "secrets": {"llm_api_key": "GEMINI_API_KEY", "blog_id": "BLOGGER_BLOG_ID", "client_id": "BLOGGER_CLIENT_ID",
                     "client_secret": "BLOGGER_CLIENT_SECRET", "refresh_token": "BLOGGER_REFRESH_TOKEN"}},
    ]}, ensure_ascii=False)


# 채널(channel.label)이 있는 가짜 레지스트리: Chance(자동 공개)·Blogger(초안함 업로드)·티스토리(패키지)·네이버(정지). 초안 현황 시험용이다.
CHANNEL_REGISTRY = json.dumps({
    "schema_version": 1,
    "defaults": {"mode": "draft"},
    "blogs": [
        {"key": "chance", "name": "Chance_Blog", "channel": {"key": "chance", "label": "Chance"}, "platform": "jekyll-git", "mode": "auto",
         "state": {"history": "history.json", "content_dir": "_posts"}, "secrets": {"llm_api_key": "GEMINI_API_KEY"}},
        {"key": "blogger_macat", "name": "Blogger (macat0722)", "channel": {"key": "blogger", "label": "Blogger"}, "platform": "blogger", "mode": "draft",
         "state": {"history": "blogger_history.json", "content_dir": "_blogger_drafts"},
         "secrets": {"llm_api_key": "GEMINI_API_KEY", "blog_id": "BLOGGER_BLOG_ID", "client_id": "BLOGGER_CLIENT_ID",
                     "client_secret": "BLOGGER_CLIENT_SECRET", "refresh_token": "BLOGGER_REFRESH_TOKEN"}},
        {"key": "tistory_x", "name": "티스토리 시험", "channel": {"key": "tistory", "label": "티스토리"}, "platform": "tistory", "mode": "package",
         "state": {"history": "tistory_history.json", "content_dir": "_tistory_drafts"}, "secrets": {"llm_api_key": "GEMINI_API_KEY"}},
        {"key": "naver_x", "name": "네이버 시험", "channel": {"key": "naver", "label": "네이버"}, "platform": "naver", "mode": "off",
         "state": {"history": "naver_history.json", "content_dir": "_naver_drafts"}, "secrets": {"llm_api_key": "GEMINI_API_KEY"}},
    ]}, ensure_ascii=False)


def make_root(tmp, histories=None, workflows=("chanceblog.yml", "blogger.yml", "watchdog.yml", "guardrails.yml"), blogs_json=None):
    """레지스트리·이력·워크플로 파일만 있는 임시 저장소 폴더. histories: {파일 이름: 목록 또는 원문 문자열}.
    workflows: 파일 이름 목록(내용은 'name: x') 또는 {파일 이름: 파일 내용}."""
    root = Path(tmp)
    (root / "pipeline").mkdir(parents=True, exist_ok=True)
    (root / "pipeline" / "blogs.json").write_text(SYNTHETIC_REGISTRY if blogs_json is None else blogs_json, encoding="utf-8")
    for name, content in (histories or {}).items():
        (root / name).write_text(content if isinstance(content, str) else json.dumps(content, ensure_ascii=False), encoding="utf-8")
    (root / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
    contents = workflows if isinstance(workflows, dict) else {name: "name: x\n" for name in workflows}
    for name, text in contents.items():
        (root / ".github" / "workflows" / name).write_text(text, encoding="utf-8")
    return root
