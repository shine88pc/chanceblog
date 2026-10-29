"""초안 패키지(티스토리·네이버) 시험 공용 보조: 임시 저장소, 가짜 GitHub REST, 가짜 게시자.

네트워크를 쓰지 않는다. 실제 `pipeline/blogs.json` 의 티스토리·네이버 항목(2026-10-29~)은 `tests/test_package_registry.py`·`tests/test_profiles_tistory_naver.py` 가 따로 보고, 이 시험들은 임시 저장소에
시험용 항목(`tistory_test`·`naver_test`)을 더해 레지스트리 검증·러너·워크플로 경로를 증명한다. 프로필·프롬프트는 시험 안의 fixture(한국어 Blogger 프로필 사본)를 쓴다 — 임시 저장소는 `make_root` 가 실제 package 블로그를 뺀 사본이라 이름이 겹치지 않는다.
"""
import email.message
import io
import json
import re
import shutil
import urllib.error
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

import _bootstrap  # noqa: F401
from pipeline.publishers.base import PublishResult
from test_run import make_root

REAL = _bootstrap.ROOT
NOW = datetime(2026, 10, 21, 5, 20, tzinfo=timezone.utc)      # KST 2026-10-21 14:20 (tistory.yml 의 정기 실행 시각)
KST_DAY = "2026-10-21"
REPO = "owner/repo"
GEMINI_ENV = {"GEMINI_API_KEY": "k"}


def fake_token():
    """실제 토큰처럼 보이는 리터럴을 파일에 두지 않으려고 실행 때 조합한다(저장소 비밀 스캔 SEC-2 가 잡는 모양)."""
    return "ghs_" + "x" * 36


def package_env(**extra):
    """초안 패키지 실제 실행(연습 아님)에 필요한 환경: Gemini 키(PIPELINE_SECRET_ 이름이 아닌 레지스트리 이름)·GitHub 토큰·저장소."""
    return {**GEMINI_ENV, "GITHUB_TOKEN": fake_token(), "GITHUB_REPOSITORY": REPO, **extra}


def package_entry(platform, mode="package", **overrides):
    """임시 레지스트리에 더하는 티스토리·네이버 항목(시험 fixture). 키·주소는 시험용이다."""
    label = {"tistory": "티스토리", "naver": "네이버"}[platform]
    hour = {"tistory": "5", "naver": "6"}[platform]
    entry = {
        "key": f"{platform}_test", "name": f"{label} 시험 블로그", "channel": {"key": platform, "label": label}, "platform": platform,
        "url": f"https://{platform}-test.example/", "role": "시험용", "languages": ["ko"], "mode": mode,
        "workflow": f".github/workflows/{platform}.yml", "entrypoint": "pipeline/run.py", "prompt": ".github/editorial/BLOGGER_PROMPT.md",
        "profile": "package_test_ko", "state": {"history": f"{platform}_test_history.json", "content_dir": f"_{platform}_test_drafts"},
        "schedule": {"cron": f"20 {hour} * * *"}, "limits": {"max_posts_per_day": 1}, "secrets": {"llm_api_key": "GEMINI_API_KEY"}, "ads": "off",
    }
    entry.update(overrides)
    return entry


def make_package_root(tmp, mode="package", platforms=("tistory", "naver"), mutate=None):
    """임시 저장소: 실제 레지스트리(chance·blogger_macat)에 시험용 티스토리·네이버 항목을 더하고, 실제 워크플로 파일 2개와 fixture 프로필을 복사한다."""
    root = make_root(tmp, mode="off")
    reg_path = root / "pipeline" / "blogs.json"
    reg = json.loads(reg_path.read_text(encoding="utf-8"))
    reg["blogs"] += [package_entry(platform, mode) for platform in platforms]
    if mutate:
        mutate(reg)
    reg_path.write_text(json.dumps(reg, ensure_ascii=False), encoding="utf-8")
    profile = json.loads((REAL / "pipeline" / "profiles" / "blogger_practical_ko.json").read_text(encoding="utf-8"))
    profile["name"] = "package_test_ko"
    (root / "pipeline" / "profiles" / "package_test_ko.json").write_text(json.dumps(profile, ensure_ascii=False), encoding="utf-8")
    for platform in ("tistory", "naver"):
        shutil.copy(REAL / ".github" / "workflows" / f"{platform}.yml", root / ".github" / "workflows" / f"{platform}.yml")
    (root / "pipeline" / "run.py").write_text("", encoding="utf-8")
    return root


def registry_of(root):
    return json.loads((Path(root) / "pipeline" / "blogs.json").read_text(encoding="utf-8"))


def entry_of(reg, key):
    return next(blog for blog in reg["blogs"] if blog["key"] == key)


def with_entry(mutate_entry, platform="tistory"):
    """항목 하나를 고치는 레지스트리 변형 함수를 만든다(validate_registry 시험용)."""
    def mutate(reg):
        mutate_entry(entry_of(reg, f"{platform}_test"))
    return mutate


# ----------------------------------------------------------------------------
# 가짜 게시자(러너 시험): 어댑터 자리에 끼운다
# ----------------------------------------------------------------------------
class FakePackagePublisher:
    """count_open_drafts(채널 라벨)와 publish_package(초안)만 가진 가짜. open_drafts·check(점검 때 던질 예외)·fail(만들 때 던질 예외)·notes 를 고른다."""

    def __init__(self, open_drafts=0, check=None, fail=None, result=None, notes=()):
        self.open_drafts, self.check, self.fail, self.result = open_drafts, check, fail, result
        self.notes = list(notes)
        self.counted, self.created = [], []

    def count_open_drafts(self, channel_label):
        self.counted.append(channel_label)
        if self.check:
            raise self.check
        return self.open_drafts

    def publish_package(self, draft):
        if self.fail:
            raise self.fail
        self.created.append(draft)
        number = len(self.created)
        return self.result or PublishResult(post_id=str(number), url=f"https://github.com/{REPO}/issues/{number}", draft=True)


# ----------------------------------------------------------------------------
# 가짜 GitHub REST(urllib 오프너 자리): 이슈·라벨의 필요한 부분만 메모리에서 흉내 낸다
# ----------------------------------------------------------------------------
class FakeResponse:
    def __init__(self, payload, status=200):
        self.status = status
        self._body = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class ReplayableHTTPError(urllib.error.HTTPError):
    """read() 를 몇 번 불러도 같은 본문을 돌려주는 HTTPError. 같은 예외 객체를 재시도마다 던지는 시험에서, 둘째 시도부터 본문이 비는 일이 없게 한다
    (진짜 서버는 응답마다 새 예외와 새 본문을 준다)."""

    def __init__(self, url, code, msg, hdrs, body):
        super().__init__(url, code, msg, hdrs, io.BytesIO(body))
        self._replay = body

    def read(self, amt=None):
        return self._replay


def http_error(status, message="", headers=None):
    hdrs = email.message.Message()
    for key, value in (headers or {}).items():
        hdrs[key] = value
    return ReplayableHTTPError(f"https://api.github.com/repos/{REPO}/x", status, message or f"HTTP {status}", hdrs,
                               json.dumps({"message": message}).encode("utf-8"))


class FakeGitHub:
    """`IssuePackagePublisher(..., opener=FakeGitHub())` 처럼 쓴다. requests 에 (메서드, 경로, 쿼리, 본문, 헤더)가 쌓인다.

    fail 에 (메서드, 경로 정규식, 예외 또는 호출 가능 객체, 횟수)를 넣으면 맞는 요청을 그 횟수만큼 실패시킨다(횟수 None = 계속).
    라벨이 없을 때 이슈를 만들면 진짜 GitHub 처럼 라벨을 자동으로 만든다(auto_labels)."""

    def __init__(self, repo=REPO, auto_labels=True):
        self.repo, self.auto_labels = repo, auto_labels
        self.issues, self.labels, self.requests, self.fail = [], {}, [], []
        self.clock = 0

    # -- 시험 쪽에서 쓰는 도구 -----------------------------------------------------
    def add_issue(self, labels=("초안",), state="open", body="", title="t", pull_request=False, number=None):
        number = number or len(self.issues) + 1
        self.clock += 1
        issue = {"number": number, "title": title, "body": body, "state": state, "labels": [{"name": name} for name in labels],
                 "html_url": f"https://github.com/{self.repo}/issues/{number}", "created_at": f"2026-10-21T00:00:{self.clock:02d}Z",
                 "updated_at": "2026-10-21T00:00:00Z"}
        if pull_request:
            issue["pull_request"] = {"url": "x"}
        self.issues.append(issue)
        return issue

    def fail_next(self, method, pattern, error, times=1):
        self.fail.append([method, re.compile(pattern), error, times])

    def calls(self, method=None, pattern=None):
        return [r for r in self.requests if (method is None or r["method"] == method) and (pattern is None or re.search(pattern, r["path"]))]

    # -- urllib 오프너 흉내 ------------------------------------------------------
    def __call__(self, request, timeout=None):
        parsed = urllib.parse.urlsplit(request.full_url)
        prefix = f"/repos/{self.repo}"
        path = urllib.parse.unquote(parsed.path)
        query = {key: values[0] for key, values in urllib.parse.parse_qs(parsed.query).items()}
        payload = json.loads(request.data.decode("utf-8")) if request.data else None
        record = {"method": request.get_method(), "path": path[len(prefix):] if path.startswith(prefix) else path, "query": query,
                  "payload": payload, "headers": {key.lower(): value for key, value in request.header_items()}, "url": request.full_url}
        self.requests.append(record)
        for rule in self.fail:
            method, regex, error, times = rule
            if method == record["method"] and regex.search(record["path"]) and (times is None or times > 0):
                if times is not None:
                    rule[3] -= 1
                result = error(record) if callable(error) and not isinstance(error, BaseException) else error
                if isinstance(result, BaseException):
                    raise result
                if result is not None:
                    return result
        if not path.startswith(prefix):
            raise http_error(404, "Not Found")
        return self._route(record)

    def _route(self, record):
        method, path, query, payload = record["method"], record["path"], record["query"], record["payload"]
        if method == "GET" and path == "/issues":
            wanted = [name for name in query.get("labels", "").split(",") if name]
            state = query.get("state", "open")
            since = query.get("since")
            items = [issue for issue in self.issues
                     if all(name in [label["name"] for label in issue["labels"]] for name in wanted)
                     and (state == "all" or issue["state"] == state)
                     and (not since or issue["updated_at"] >= since)]
            items.sort(key=lambda issue: issue["created_at"], reverse=True)
            per_page, page = int(query.get("per_page", 30)), int(query.get("page", 1))
            return FakeResponse(items[(page - 1) * per_page:page * per_page])
        if method == "POST" and path == "/issues":
            for name in payload.get("labels", []):
                if name not in self.labels:
                    if not self.auto_labels:
                        raise http_error(422, "Validation Failed")
                    self.labels[name] = {"name": name, "color": "ededed", "description": ""}
            issue = self.add_issue(labels=payload.get("labels", []), body=payload.get("body", ""), title=payload.get("title", ""))
            return FakeResponse(issue, 201)
        if method == "GET" and path.startswith("/labels/"):
            name = path[len("/labels/"):]
            if name not in self.labels:
                raise http_error(404, "Not Found")
            return FakeResponse(self.labels[name])
        if method == "POST" and path == "/labels":
            if payload["name"] in self.labels:
                raise http_error(422, "Validation Failed")
            self.labels[payload["name"]] = payload
            return FakeResponse(payload, 201)
        raise http_error(404, "Not Found")
