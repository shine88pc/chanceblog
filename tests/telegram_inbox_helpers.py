"""텔레그램 수신(pipeline/telegram_inbox.py) 시험 공용 도구: 상태를 가진 가짜 텔레그램 서버·가짜 GitHub 이슈 API·글 만들기·바깥 연결 차단.

진짜 텔레그램·GitHub 는 부르지 않는다(둘 다 urllib 의 opener 자리에 끼우는 프로세스 안 가짜 서버). 가짜 토큰·채팅 ID 는 소스에 비밀 모양 리터럴을 두지 않으려고 런타임에 조합한 값이다
(notify_helpers 의 TOKEN·CHAT — 검증기 SEC-2·docs/ENGINEERING_GUIDE.md §5). 시험은 소켓 연결을 막아(NoOutbound) 어떤 경로로든 진짜 서버에 닿으려는 시도가 있으면 실패한다.
"""
import contextlib
import io
import json
import os
import re
import socket
import urllib.parse
import urllib.request
from unittest import mock

import _bootstrap  # noqa: F401
import notify_helpers as nh
import operator_loop_helpers as oh
from pipeline import telegram_inbox as ti

CHAT_INT = int(nh.CHAT)
OTHER_ID = CHAT_INT + 1111
GH_TOKEN = oh.GH_TOKEN
REPO = oh.REPO
BOT = ti.BOT_LOGIN
T0 = 1762226400                      # 2025-11-04 03:20:00 UTC = 12:20 KST(가짜 보낸 시각)


# ---- 텔레그램 글(update) 만들기 ------------------------------------------------------------------------------------------
def message_update(update_id, text="안녕하세요", chat_id=CHAT_INT, from_id=None, chat_type="private", date=T0, **extra):
    """운영자 본인이 비공개 대화로 보낸 글 update. from_id 를 주지 않으면 chat_id 와 같다. extra 의 키는 message 에 더한다(photo·voice·caption 등)."""
    message = {"message_id": update_id + 100, "date": date, "chat": {"id": chat_id, "type": chat_type}, "from": {"id": chat_id if from_id is None else from_id, "is_bot": False}}
    if text is not None:
        message["text"] = text
    message.update(extra)
    return {"update_id": update_id, "message": message}


def other_update(update_id, kind, **body):
    """message 가 아닌 update(edited_message·channel_post·callback_query …)."""
    return {"update_id": update_id, kind: body or {"x": 1}}


def renamed(update, kind):
    """운영자 본인의 진짜 글과 모양이 같지만 종류 이름만 다른 update(edited_message·channel_post …) — 종류를 가리지 않고 읽으면 이슈가 된다."""
    return {"update_id": update["update_id"], kind: update["message"]}


# ---- 가짜 텔레그램 서버 --------------------------------------------------------------------------------------------------
class FakeTelegram:
    """Bot API 의 getUpdates·sendMessage 만 흉내 내는 서버(opener 자리에 끼운다). getUpdates 는 진짜처럼 offset 보다 작은 번호의 글을 '확인됨' 으로 지우고 limit 만큼 돌려준다.

    failures: [{'method': 이름, 'when': payload → 참/거짓(없으면 항상), 'outcome': 던질 예외 또는 응답(또는 호출하면 응답을 주는 함수), 'times': 횟수(기본 1)}] — 앞에서부터 맞는 것을 쓴다.
    webhook=True 면 getUpdates 는 409(웹훅이 켜져 있음). calls 는 모든 요청의 기록, sent 는 sendMessage 본문, outbound 는 요청 주소 전체."""

    def __init__(self, updates=(), failures=(), token=nh.TOKEN, webhook=False, ignore_offset=False, max_polls=None):
        self.queue = sorted(updates, key=lambda item: item["update_id"])
        self.failures = [dict(item, times=item.get("times", 1)) for item in failures]
        self.token, self.webhook = token, webhook
        self.ignore_offset, self.max_polls = ignore_offset, max_polls      # ignore_offset: offset 을 무시하는 고장난 서버, max_polls: 이만큼 넘게 읽으면 연결 오류(되풀이 읽기 감지)
        self.calls, self.sent, self.urls, self.timeouts = [], [], [], []

    def add(self, *updates):
        self.queue = sorted(self.queue + list(updates), key=lambda item: item["update_id"])

    def methods(self):
        return [call["method"] for call in self.calls]

    def polls(self):
        return [call["payload"] for call in self.calls if call["method"] == "getUpdates"]

    def texts(self):
        return [payload.get("text", "") for payload in self.sent]

    def _failure(self, method, payload):
        for item in self.failures:
            if item["method"] == method and item["times"] > 0 and (item.get("when") is None or item["when"](payload)):
                item["times"] -= 1
                return item["outcome"]
        return None

    def __call__(self, request, timeout=None):
        self.urls.append(request.full_url)
        self.timeouts.append(timeout)
        found = re.fullmatch(r"https://api\.telegram\.org/bot([^/]+)/([A-Za-z]+)", request.full_url)
        assert found and found.group(1) == self.token, "텔레그램 주소 모양이 다릅니다"
        method = found.group(2)
        payload = json.loads(request.data.decode("utf-8")) if request.data else {}
        self.calls.append({"method": method, "payload": payload})
        if method == "getUpdates" and self.max_polls is not None and len(self.polls()) > self.max_polls:
            raise OSError("시험: 같은 글을 너무 여러 번 읽습니다(되풀이 읽기)")
        outcome = self._failure(method, payload)
        if outcome is not None:
            if isinstance(outcome, BaseException):
                raise outcome
            return outcome() if callable(outcome) else outcome
        if method == "getUpdates":
            if self.webhook:
                raise nh.http_error(409, "Conflict: can't use getUpdates method while webhook is active; use deleteWebhook to delete the webhook first")
            offset = payload.get("offset")
            if offset is not None and not self.ignore_offset:
                self.queue = [item for item in self.queue if item["update_id"] >= offset]       # 진짜 텔레그램처럼: 이 번호보다 작은 글은 확인된 것
            return nh.FakeResponse(200, {"ok": True, "result": self.queue[:payload.get("limit", 100)]})
        if method == "sendMessage":
            self.sent.append(payload)
            return nh.ok_reply()
        raise AssertionError(f"예상하지 못한 텔레그램 메서드: {method}")


# ---- 가짜 GitHub(이슈) ---------------------------------------------------------------------------------------------------
class FakeIssues(oh.FakeGitHub):
    """operator_loop_helpers.FakeGitHub 에 이슈 목록·만들기·라벨 붙이기를 더한 가짜. issues 는 만들어진 이슈 목록(시험이 미리 넣을 수 있다).
    drop_labels=True 면 만들 때 라벨을 조용히 버린다(권한이 없을 때의 GitHub 동작)."""

    def __init__(self, issues=(), labels=(), failures=(), drop_labels=False):
        super().__init__(labels=labels, failures=failures)
        self.issues = [dict(item) for item in issues]
        self.drop_labels = drop_labels

    def new_issues(self):
        return [item for item in self.issues if item.get("_made")]

    def _route(self, method, path, payload):
        if method == "GET" and path == "/issues":
            query = urllib.parse.parse_qs(self.requests[-1]["query"])
            wanted = query.get("labels", [""])[0]
            per_page, page = int(query.get("per_page", ["30"])[0]), int(query.get("page", ["1"])[0])
            rows = [item for item in self.issues if wanted in [label["name"] for label in item.get("labels", [])]]
            rows.sort(key=lambda item: -item["number"])
            return nh.FakeResponse(200, [{key: value for key, value in row.items() if not key.startswith("_")} for row in rows[(page - 1) * per_page: page * per_page]])
        if method == "POST" and path == "/issues":
            number = max([item["number"] for item in self.issues] + [100]) + 1
            labels = [] if self.drop_labels else [{"name": name} for name in payload.get("labels", [])]
            issue = {"number": number, "title": payload["title"], "body": payload["body"], "state": "open", "user": {"login": BOT}, "labels": labels, "_made": True}
            self.issues.append(issue)
            return nh.FakeResponse(201, {key: value for key, value in issue.items() if not key.startswith("_")})
        found = re.fullmatch(r"/issues/([0-9]+)/labels", path)
        if method == "POST" and found:
            number = int(found.group(1))
            for item in self.issues:
                if item["number"] == number:
                    item.setdefault("labels", []).extend({"name": name} for name in payload["labels"])
            return nh.FakeResponse(200, [{"name": name} for name in payload["labels"]])
        return super()._route(method, path, payload)


def stored_issue(number, update_id, state="open", login=BOT, label=ti.LABEL, body=None, pull=False):
    """이미 저장소에 있는 텔레그램 수신 이슈(앞선 실행이 만든 것)."""
    issue = {"number": number, "title": ti.TITLE_PREFIX + "옛 글", "state": state, "user": {"login": login}, "labels": [{"name": label}] if label else [],
             "body": body if body is not None else ti.MARKER_FORMAT.format(update_id) + "\n\n> 옛 글\n"}
    if pull:
        issue["pull_request"] = {"url": "https://api.github.com/x"}
    return issue


# ---- 실행 -------------------------------------------------------------------------------------------------------------------
def make_env(**extra):
    env = {"GITHUB_TOKEN": GH_TOKEN, "GITHUB_REPOSITORY": REPO}
    env.update(nh.ENV)
    env.update(extra)
    return env


class Run:
    """한 번의 실행 결과: 종료 코드·출력 줄·가짜 서버 둘."""

    def __init__(self, code, lines, tg, gh, clock):
        self.code, self.lines, self.tg, self.gh, self.clock = code, lines, tg, gh, clock

    @property
    def text(self):
        return "\n".join(self.lines)

    def issues(self):
        return self.gh.new_issues()


def run_inbox(tg=None, gh=None, env=None, argv=(), clock=None, base=None):
    """pipeline.telegram_inbox.main 을 가짜 텔레그램(tg)·가짜 GitHub(gh)·가짜 시계로 돌린다. 같은 tg·gh 로 여러 번 부르면 '다음 예약 실행' 이 된다."""
    tg = tg if tg is not None else FakeTelegram()
    gh = gh if gh is not None else FakeIssues()
    clock = clock if clock is not None else nh.Clock()
    environ = make_env() if env is None else dict(env)
    lines = []
    api = ti.loop.GitHub(environ.get("GITHUB_REPOSITORY"), environ.get("GITHUB_TOKEN"), opener=gh, sleep=clock.sleep)
    extra = {} if base is None else {"base": base}
    code = ti.main(list(argv), environ=environ, out=lines.append, opener=tg, sleep=clock.sleep, clock=clock.clock, api=api, **extra)
    unexpected = set(tg.methods()) - {"getUpdates", "sendMessage"}
    assert not unexpected, f"웹훅을 포함해 getUpdates·sendMessage 밖의 텔레그램 메서드를 불렀습니다: {sorted(unexpected)}"
    return Run(code, lines, tg, gh, clock)


# ---- 바깥 연결 차단 ---------------------------------------------------------------------------------------------------------
class NoOutbound:
    """시험이 쓰는 믹스인: 소켓 연결을 막고 시도를 기록한다(루프백 127.0.0.1 만 허용 — 진짜 urllib 경로를 지역 서버로 시험할 때). tearDown 에서 시도가 0 인지 확인한다."""

    allow_loopback = False

    def setUp(self):
        super().setUp()
        self.attempts = []
        real_connect = socket.socket.connect

        def guarded(sock, address, *args, **kwargs):
            host = address[0] if isinstance(address, tuple) else str(address)
            if self.allow_loopback and host in ("127.0.0.1", "::1", "localhost"):
                return real_connect(sock, address, *args, **kwargs)
            self.attempts.append(str(host))
            raise OSError("시험: 바깥 연결이 막혀 있습니다")

        def guarded_lookup(host, *args, **kwargs):
            if not (self.allow_loopback and host in ("127.0.0.1", "::1", "localhost")):
                self.attempts.append(str(host))
                raise OSError("시험: 이름 조회가 막혀 있습니다")
            return real_lookup(host, *args, **kwargs)

        real_lookup = socket.getaddrinfo
        patchers = [mock.patch.object(socket.socket, "connect", guarded), mock.patch.object(socket, "getaddrinfo", guarded_lookup)]
        if self.allow_loopback:
            # 진짜 urllib 경로를 지역 서버로 시험할 때: 이 PC 의 시스템·환경 프록시가 지역 주소를 가로채지 않게 한다(no_proxy 가 있으면 레지스트리 프록시는 읽지 않는다).
            patchers += [mock.patch.dict(os.environ, {"NO_PROXY": "127.0.0.1,localhost", "no_proxy": "127.0.0.1,localhost"}), mock.patch.object(urllib.request, "_opener", None)]
        for patcher in patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

    def tearDown(self):
        self.assertEqual(self.attempts, [], "시험이 진짜 네트워크에 닿으려 했습니다")
        super().tearDown()


def capture_streams(function, *args, **kwargs):
    """function 이 stdout·stderr 에 쓴 글을 함께 돌려준다: (반환값, stdout 글, stderr 글)."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        value = function(*args, **kwargs)
    return value, out.getvalue(), err.getvalue()
