"""운영자 요청함(pipeline/operator_loop.py) 시험 공용 도구: 가짜 git·가짜 GitHub REST·이벤트 파일·요청 파일 글·양식이 만드는 이슈 본문.

네트워크·실제 GitHub·실제 텔레그램은 쓰지 않는다(GitHub 는 FakeGitHub 를 opener 자리에 끼우고 텔레그램은 notify_helpers.FakeNet 을 쓴다). 가짜 토큰은 소스에 비밀 모양 리터럴을
두지 않으려고 런타임에 조합한다(검증기 SEC-2·docs/ENGINEERING_GUIDE.md §5).
"""
import io
import json
import re
import subprocess
import urllib.error
from pathlib import Path

import _bootstrap
import notify_helpers as nh
from notify_helpers import FakeResponse
from pipeline import operator_loop as ol

ROOT = _bootstrap.ROOT
OWNER = "shine88pc"
REPO = "shine88pc/chanceblog"
GH_TOKEN = "gh" + "s_" + "Q" * 36                 # 가짜 GITHUB_TOKEN(런타임 조합)
SHA_A, SHA_B, SHA_C = "a" * 40, "b" * 40, "c" * 40
ZERO = "0" * 40
DIR = ol.REQUEST_DIR + "/"
ANSWER = dict(ol.ANSWER_OPTIONS)                      # 짧은 말 → 양식의 전체 문구
TASK_SCOPE = dict(ol.TASK_APPROVAL_OPTIONS)           # no(논의·준비까지만)·yes(구현·시험까지) → 양식의 전체 문구


# ---- 요청 파일 ----------------------------------------------------------------------------------
def request_text(id="R-001", kind="merge", title="PR 병합 부탁", summary="아래 PR 을 병합해 주세요.", urgency=None, pr=None, created=None, extra="", body="상세 설명\n"):
    """앞머리(---)와 본문이 있는 요청 파일 글. None 인 키는 줄 자체를 뺀다."""
    pairs = [("id", id), ("kind", kind), ("title", title), ("summary", summary), ("urgency", urgency), ("pr", pr), ("created", created)]
    lines = [f"{key}: {value}" for key, value in pairs if value is not None]
    return "---\n" + "\n".join(lines) + ("\n" + extra if extra else "") + "\n---\n" + body


def paths(*names):
    return [DIR + name for name in names]


# ---- 가짜 git(운영자 요청함이 부르는 명령만) ---------------------------------------------------------
class RequestGit:
    """new_request_names·notify.read_blob 이 부르는 git 명령(rev-parse --is-shallow-repository·merge-base·diff·log·cat-file)을 흉내 낸다.
    tree: `git diff` 가 돌려줄 경로 목록, log: `git log` 가 돌려줄 경로 목록, files: {이름: 내용}, broken: 실패시킬 명령 이름 집합. 호출(args)을 기록한다."""

    def __init__(self, tree=(), log=None, files=None, shallow=False, merge_base=SHA_C, broken=()):
        self.tree, self.log = list(tree), list(tree if log is None else log)
        self.files, self.shallow, self.merge_base, self.broken = dict(files or {}), shallow, merge_base, set(broken)
        self.calls = []

    @classmethod
    def with_requests(cls, requests, **kwargs):
        """requests: {이름: 내용} — 새 요청 파일 둘 다(트리·커밋 차이)에 있는 것으로 둔다."""
        return cls(tree=paths(*requests), files=requests, **kwargs)

    def names(self, command):
        return [args for args, _ in self.calls if args[1] == command]

    def __call__(self, args, **kwargs):
        self.calls.append((list(args), kwargs))
        command = args[1]
        if command in self.broken:
            return subprocess.CompletedProcess(args, 128, stdout=b"", stderr=b"fatal")
        if command == "rev-parse":
            out = "true\n" if self.shallow else "false\n"
        elif command == "merge-base":
            out = self.merge_base + "\n"
        elif command == "diff":
            out = "".join(f"{path}\0" for path in self.tree)
        elif command == "log":
            out = "".join(f"{path}\0" for path in self.log)
        elif command == "cat-file":
            name = args[3].split(":", 1)[1].rsplit("/", 1)[-1]
            if name not in self.files:
                return subprocess.CompletedProcess(args, 128, stdout=b"", stderr=b"fatal")
            return subprocess.CompletedProcess(args, 0, stdout=self.files[name].encode("utf-8"), stderr=b"")
        else:
            raise AssertionError(f"예상하지 못한 git 명령: {args}")
        return subprocess.CompletedProcess(args, 0, stdout=out.encode("utf-8"), stderr=b"")


def requests_env(before=SHA_B, after=SHA_A, default_branch="main", ref_name="ai/claude/operator-loop", telegram=True, **extra):
    env = {"BEFORE_SHA": before, "AFTER_SHA": after, "DEFAULT_BRANCH": default_branch, "GITHUB_REF_NAME": ref_name}
    if telegram:
        env.update(nh.ENV)
    env.update(extra)
    return env


# ---- 가짜 GitHub REST --------------------------------------------------------------------------------
def http_error(status, message="", url="https://api.github.com/x"):
    body = json.dumps({"message": message}).encode("utf-8")
    return urllib.error.HTTPError(url, status, message or "error", {}, io.BytesIO(body))


class FakeGitHub:
    """urllib 의 opener 자리에 끼우는 가짜 GitHub REST(저장소 하나). 이슈 코멘트·저장소 라벨·이슈 라벨을 흉내 내고 모든 요청을 기록한다.

    failures: [(메서드, 경로에 들어 있는 글, 결과[, 먼저 처리])] — 맞는 요청이 오면 앞에서부터 하나씩 써서 결과(예외면 던지고 응답이면 돌려줌)를 낸다. 네 번째 값이 참이면 서버가 요청을
    처리한 뒤에 결과를 낸다(응답만 잃은 경우). 코멘트는 작성자가 봇이다.
    comments: {이슈 번호: [{'user': {'login': …}, 'body': …}]} — 시험이 미리 넣어 둘 수 있다."""

    def __init__(self, labels=(), comments=None, failures=()):
        self.labels, self.comments, self.failures = set(labels), {key: list(value) for key, value in (comments or {}).items()}, list(failures)
        self.requests, self.issue_labels = [], {}

    def calls(self, method=None, containing=""):
        return [item for item in self.requests if (method is None or item["method"] == method) and containing in item["path"]]

    def writes(self):
        return [item for item in self.requests if item["method"] != "GET"]

    def __call__(self, request, timeout=None):
        match = re.fullmatch(r"https://api\.github\.com/repos/([^/]+/[^/?]+)(/[^?]*)(?:\?(.*))?", request.full_url)
        assert match, request.full_url
        method, path = request.get_method(), match.group(2)
        payload = json.loads(request.data.decode("utf-8")) if request.data else None
        self.requests.append({"method": method, "path": path, "query": match.group(3) or "", "payload": payload, "headers": dict(request.header_items()), "timeout": timeout})
        for index, failure in enumerate(self.failures):
            want_method, fragment, outcome = failure[:3]
            if want_method == method and fragment in path:
                del self.failures[index]
                if len(failure) > 3 and failure[3]:
                    self._route(method, path, payload)          # 서버는 처리했는데 응답만 잃은 경우(코멘트는 만들어졌다)
                if isinstance(outcome, BaseException):
                    raise outcome
                return outcome
        return self._route(method, path, payload)

    def _route(self, method, path, payload):
        if method == "GET" and path.endswith("/comments"):
            return FakeResponse(200, self.comments.get(int(path.split("/")[2]), []))
        if method == "POST" and path == "/labels":
            if payload["name"] in self.labels:
                raise http_error(422, "Validation Failed")
            self.labels.add(payload["name"])
            return FakeResponse(201, {"name": payload["name"]})
        if method == "POST" and path.endswith("/labels"):
            self.issue_labels.setdefault(int(path.split("/")[2]), []).extend(payload["labels"])
            return FakeResponse(200, [{"name": name} for name in payload["labels"]])
        if method == "POST" and path.endswith("/comments"):
            number = int(path.split("/")[2])
            self.comments.setdefault(number, []).append({"user": {"login": ol.BOT_LOGIN}, "body": payload["body"]})
            return FakeResponse(201, {"id": len(self.comments[number])})
        raise AssertionError(f"예상하지 못한 요청: {method} {path}")

    def posted(self, number):
        """이 이슈에 봇이 단 코멘트 본문들."""
        return [item["body"] for item in self.comments.get(number, []) if item["user"]["login"] == ol.BOT_LOGIN]


# ---- 이슈 이벤트·양식 본문 --------------------------------------------------------------------------------
def reply_body(request_id="R-001", answer="승인", choice="", memo="", crlf=True, raw_answer=None):
    """이슈 양식 `[답변]` 이 만드는 본문 모양(`### 항목 제목` 아래에 값, 빈 선택 항목은 `_No response_`). answer 는 짧은 말(전체 문구로 바꿔 쓴다),
    raw_answer 를 주면 그 글을 그대로 쓴다(양식에 없는 값 시험)."""
    full = raw_answer if raw_answer is not None else ANSWER.get(answer, answer)
    body = f"### 요청 번호\n\n{request_id}\n\n### 답변\n\n{full}\n\n### 선택\n\n{choice or '_No response_'}\n\n### 메모\n\n{memo or '_No response_'}"
    return body.replace("\n", "\r\n") if crlf else body


def task_body(what="PR 을 정리해 주세요", done="", urgency="보통", approval="논의·준비까지만", crlf=True):
    body = f"### 해 주었으면 하는 일\n\n{what}\n\n### 끝났다고 볼 기준\n\n{done or '_No response_'}\n\n### 긴급도\n\n{urgency}\n\n### 진행 범위\n\n{approval}"
    return body.replace("\n", "\r\n") if crlf else body


def issue_event(number=12, title="[답변] ", body=None, login=OWNER, association="OWNER", labels=(), action="opened"):
    body = reply_body() if body is None else body
    issue = {"number": number, "title": title, "body": body, "user": {"login": login}, "author_association": association,
             "labels": [{"name": name} for name in labels]}
    return {"action": action, "issue": issue, "repository": {"full_name": REPO, "owner": {"login": OWNER}}}


def ack_env(tmp, event, telegram=True, token=GH_TOKEN, event_name="issues", owner=OWNER, **extra):
    """ack 명령의 환경: 이벤트 JSON 을 임시 파일에 쓰고 GITHUB_EVENT_PATH 로 가리킨다."""
    path = Path(tmp) / "event.json"
    path.write_text(json.dumps(event, ensure_ascii=False), encoding="utf-8")
    env = {"GITHUB_EVENT_PATH": str(path), "GITHUB_EVENT_NAME": event_name, "GITHUB_REPOSITORY": REPO, "GITHUB_REPOSITORY_OWNER": owner}
    if token:
        env["GITHUB_TOKEN"] = token
    if telegram:
        env.update(nh.ENV)
    env.update(extra)
    return env


def run_cli(*argv, environ, net=None, root=None, runner=None, opener=None, github=None):
    """pipeline.operator_loop.main 을 가짜 텔레그램(net)·가짜 GitHub(github)·가짜 git(runner)으로 돌린다. (종료 코드, 출력 줄들, net, github) 를 돌려준다."""
    lines, clock = [], nh.Clock()
    net = net if net is not None else nh.FakeNet()
    kwargs = {} if runner is None else {"runner": runner}
    github = github if github is not None else FakeGitHub()
    api = ol.GitHub(environ.get("GITHUB_REPOSITORY"), environ.get("GITHUB_TOKEN"), opener=github, sleep=clock.sleep)
    code = ol.main(list(argv), environ=dict(environ), out=lines.append, root=root, opener=net, sleep=clock.sleep, clock=clock.clock,
                   budget=nh.notify.Budget(), api=api, **kwargs)
    return code, lines, net, github
