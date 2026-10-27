"""텔레그램 알림(pipeline/notify.py) 시험 공용 도구: 가짜 HTTP·가짜 시계·런타임에 조합한 가짜 값·git 저장소 만들기.

네트워크는 쓰지 않는다(urllib.request.urlopen 자리에 FakeNet 을 끼운다). 가짜 토큰·채팅 ID 는 소스에 비밀 모양 리터럴을 두지 않으려고 런타임에 조합한다
(검증기 SEC-2 와 docs/ENGINEERING_GUIDE.md §5 의 4번).
"""
import io
import json
import subprocess
import urllib.error
import urllib.parse
from pathlib import Path

import _bootstrap
from pipeline import notify

ROOT = _bootstrap.ROOT          # 저장소 루트를 import 경로에 올리는 _bootstrap 을 먼저 불러야 pipeline 을 가져올 수 있다

BOT_ID = "1234567" + "890"
SECRET_HALF = "AAF" + "k_-" * 5 + "Z" * 17            # 영숫자·-·_ 35자
TOKEN = BOT_ID + ":" + SECRET_HALF
CHAT = "98765" + "4321"
ENV = {"TELEGRAM_BOT_TOKEN": TOKEN, "TELEGRAM_CHAT_ID": CHAT}
SEND_URL = f"https://api.telegram.org/bot{TOKEN}/sendMessage"      # 시험이 요청 주소를 확인하는 곳에만 쓴다(출력 검사 대상에서는 뺀다)


def secret_forms(chat=True):
    """어떤 출력에도 나오면 안 되는 문자열들: 토큰·비밀 절반·봇 번호와 URL 인코딩 형태, 그리고(chat=True) 채팅 ID."""
    forms = {TOKEN, SECRET_HALF, BOT_ID, urllib.parse.quote(TOKEN, safe=""), urllib.parse.quote(TOKEN),
             urllib.parse.quote_plus(TOKEN), urllib.parse.quote(TOKEN, safe="").lower()}
    if chat:
        forms.add(CHAT)
    return sorted(forms, key=len, reverse=True)


def leaks(*texts, chat=True):
    """texts 에 비밀 문자열이 들어 있으면 (어느 것이, 어느 글에) 목록을 돌려준다. 비어 있으면 샌 것이 없다. 요청 본문처럼 채팅 ID 가 있어야 하는 글은 chat=False."""
    found = []
    for index, text in enumerate(texts):
        raw = text if isinstance(text, str) else repr(text)
        for form in secret_forms(chat):
            if form in raw or form.lower() in raw.lower():
                found.append((form[:3] + "…", index))
    return found


class FakeResponse:
    def __init__(self, status=200, body=None, headers=None):
        self.status = status
        self._raw = body if isinstance(body, bytes) else (body if isinstance(body, str) else json.dumps(body)).encode("utf-8")
        self.headers = headers or {}
        self.closed = False

    def read(self, limit=-1):
        return self._raw if limit is None or limit < 0 else self._raw[:limit]

    def getcode(self):
        return self.status

    def close(self):
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


def ok_reply():
    return FakeResponse(200, {"ok": True, "result": {"message_id": 7, "chat": {"id": int(CHAT)}, "text": "x"}})


def http_error(code, description="", retry_after=None, header_retry=None, raw=None):
    """텔레그램의 오류 응답처럼 요청 주소(토큰 포함)를 단 HTTPError. raw 를 주면 본문을 그대로 쓴다."""
    body = {"ok": False, "error_code": code, "description": description}
    if retry_after is not None:
        body["parameters"] = {"retry_after": retry_after}
    data = raw if raw is not None else json.dumps(body).encode("utf-8")
    headers = {"Retry-After": str(header_retry)} if header_retry is not None else {}
    return urllib.error.HTTPError(SEND_URL, code, description or "error", headers, io.BytesIO(data))


class FakeNet:
    """urllib.request.urlopen 대신 끼우는 가짜. 준비한 결과(응답 객체 또는 던질 예외)를 차례로 돌려주고 마지막 결과는 반복한다. 요청·제한 시간을 기록한다."""

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes) or [ok_reply()]
        self.requests, self.timeouts = [], []

    def __call__(self, request, timeout=None):
        self.requests.append(request)
        self.timeouts.append(timeout)
        outcome = self.outcomes.pop(0) if len(self.outcomes) > 1 else self.outcomes[0]
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome() if callable(outcome) else outcome

    def bodies(self):
        return [json.loads(request.data.decode("utf-8")) for request in self.requests]

    @property
    def calls(self):
        return len(self.requests)


class Clock:
    """가짜 시계: sleep 은 기다리지 않고 시계만 앞으로 보낸다."""

    def __init__(self, start=1000.0):
        self.now, self.sleeps = start, []

    def clock(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds

    def advance(self, seconds):
        self.now += seconds


def make_notifier(net=None, clock=None, environ=None, budget=None):
    """가짜 HTTP·가짜 시계를 끼운 전송기와 (net, clock)."""
    net = net if net is not None else FakeNet()
    clock = clock if clock is not None else Clock()
    budget = budget if budget is not None else notify.Budget()
    notifier = notify.Notifier(ENV if environ is None else environ, opener=net, sleep=clock.sleep, clock=clock.clock, budget=budget)
    return notifier, net, clock


# ---- git 저장소 -------------------------------------------------------------------------
CONFIG = ('title: t\nurl: "https://shine88pc.github.io"\nbaseurl: "/chanceblog"\ntimezone: Asia/Seoul\n'
          'permalink: /posts/:year/:month/:day/:title/\n')


def git(root, *args):
    done = subprocess.run(["git", "-c", "user.name=tester", "-c", "user.email=tester@example.com", "-c", "commit.gpgsign=false",
                           "-c", "core.autocrlf=false", *args], cwd=str(root), capture_output=True)
    if done.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} 실패: {done.stderr.decode('utf-8', 'replace')}")
    return done.stdout.decode("utf-8", "replace").strip()


def post_text(title, lang, category, source="출처 이름", extra="", body="본문입니다.\n"):
    """실제 글 파일 모양(layout·title·category·lang·source_name)의 front matter 와 본문."""
    return ("---\nlayout: post\n" + f"title: {json.dumps(title, ensure_ascii=False)}\n" + f"category: {json.dumps(category, ensure_ascii=False)}\n"
            f"tags: [\"a\", \"b\"]\nlang: {lang}\nsource_name: {json.dumps(source, ensure_ascii=False)}\n" + extra + "---\n\n" + body)


def make_repo(tmp, config=CONFIG):
    """빈 git 저장소 + `_config.yml` 한 파일의 첫 커밋(부모가 되는 커밋)."""
    root = Path(tmp)
    root.mkdir(parents=True, exist_ok=True)
    git(root, "init", "-q", "-b", "main")
    (root / "_config.yml").write_text(config, encoding="utf-8", newline="\n")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "base")
    return root


def commit_files(root, files, message="🤖 자동 포스팅/이미지 수정"):
    """files {상대경로: 내용} 을 쓰고 커밋한다. 커밋 해시를 돌려준다."""
    for rel, text in files.items():
        path = Path(root) / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", message)
    return git(root, "rev-parse", "HEAD")


def make_root(tmp, config=CONFIG):
    """git 없이 `_config.yml` 만 있는 폴더(가짜 git(FakeGit)과 함께 쓴다 — 실제 git 호출은 이 컴퓨터에서 한 번에 0.3초 넘게 걸려 대부분의 시험은 가짜로 한다)."""
    root = Path(tmp)
    root.mkdir(parents=True, exist_ok=True)
    if config is not None:
        (root / "_config.yml").write_text(config, encoding="utf-8", newline="\n")
    return root


class FakeGit:
    """notify 가 부르는 git 명령 셋(rev-list --parents·diff-tree -z·cat-file blob)을 흉내 낸다. changes: [(상태, 경로, 내용), …], parents: 부모 커밋 목록.
    호출(args, kwargs)을 기록한다. broken 에 명령 이름을 주면 그 명령은 종료 코드 128 로 실패한다."""

    SHA = "a" * 40

    def __init__(self, changes=(), parents=("b" * 40,), broken=()):
        self.changes, self.parents, self.broken = list(changes), list(parents), set(broken)
        self.calls = []

    @classmethod
    def adding(cls, files, **kwargs):
        return cls([("A", rel, text) for rel, text in files.items()], **kwargs)

    def __call__(self, args, **kwargs):
        self.calls.append((list(args), kwargs))
        name = args[1]
        if name in self.broken:
            return subprocess.CompletedProcess(args, 128, stdout=b"", stderr=b"fatal")
        if name == "rev-list":
            out = " ".join([self.SHA, *self.parents]) + "\n"
        elif name == "diff-tree":
            out = "".join(f"{status}\0{path}\0" for status, path, _ in self.changes)
        elif name == "cat-file":
            wanted = args[3].split(":", 1)[1]
            for _status, path, content in self.changes:
                if path == wanted:
                    return subprocess.CompletedProcess(args, 0, stdout=content.encode("utf-8"), stderr=b"")
            return subprocess.CompletedProcess(args, 128, stdout=b"", stderr=b"fatal")
        else:
            raise AssertionError(f"예상하지 못한 git 명령: {args}")
        return subprocess.CompletedProcess(args, 0, stdout=out.encode("utf-8"), stderr=b"")


KR_TITLE = "수요가 폭증한 국경 간 전력망: 67개 사업이 EU 공동 재원 28.8억 유로를 신청했다"
EN_TITLE = "Demand Surges for Cross-Border Energy Grids: 67 Projects Seek €2.88 Billion in EU Co-Funding"
KR_PATH = "_posts/경제·일/2026-10-27-KR-093056.md"
EN_PATH = "_posts/Economy & Work/2026-10-27-EN-093056.md"


def pair_files(kr_title=KR_TITLE, en_title=EN_TITLE, stamp="093056", day="2026-10-27", kr_extra="", en_extra=""):
    return {
        f"_posts/경제·일/{day}-KR-{stamp}.md": post_text(kr_title, "ko", "경제·일", "유럽연합 CINEA", kr_extra),
        f"_posts/Economy & Work/{day}-EN-{stamp}.md": post_text(en_title, "en", "Economy & Work", "European Commission (DG Energy)", en_extra),
    }
