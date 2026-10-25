"""Pages 배포 후 확인(scripts/verify_pages_deploy.py) 테스트 공용 도구: 임시 저장소, 가짜 사이트·시계. 네트워크 없음."""
import io
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import _bootstrap  # noqa: F401

sys.path.insert(0, str(_bootstrap.ROOT / "scripts"))
import verify_pages_deploy as v  # noqa: E402

BASE = "https://example.github.io/blog/"
INDEX = BASE + "posts.json"
NOW = datetime(2026, 10, 25, 12, 0, tzinfo=timezone.utc)  # = 한국 시간 2026-10-25 21:00
KST = timezone(timedelta(hours=9))
SITE_CONFIG = "title: t\ntimezone: Asia/Seoul\npermalink: /posts/:year/:month/:day/:title/\nplugins:\n  - x\n"
KR = "기술·미래/2026-10-25-KR-101307.md"
EN = "Technology & Future/2026-10-25-EN-101307.md"
KR_URL = BASE + "posts/2026/10/25/KR-101307/"
EN_URL = BASE + "posts/2026/10/25/EN-101307/"


def make_post(root, name, front=""):
    """임시 저장소의 _posts 아래에 글 하나를 만든다. front: 추가 front matter 줄(끝 개행 포함)."""
    path = Path(root) / "_posts" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\nlayout: post\ntitle: t\n{front}---\n본문\n", encoding="utf-8")
    return path


def make_repo(root, names=(KR, EN), config=SITE_CONFIG, fronts=None):
    """임시 저장소: 글들과 _config.yml. fronts: {글 이름: 추가 front matter}."""
    Path(root).mkdir(parents=True, exist_ok=True)
    for name in names:
        make_post(root, name, (fronts or {}).get(name, ""))
    if config is not None:
        (Path(root) / "_config.yml").write_text(config, encoding="utf-8")
    return Path(root)


def post_of(name="2026-10-25-KR-101307.md", front=None, folder="a"):
    """front matter 를 이미 읽은 Post. name 은 YYYY-MM-DD-slug.md."""
    year, month, day = int(name[0:4]), int(name[5:7]), int(name[8:10])
    return v.Post(f"_posts/{folder}/{name}", name, date(year, month, day), name[11:-3], front or {})


def page(status=200, headers=None):
    return v.Resp(status, b"<html></html>" if status == 200 else b"", dict(headers or {}), "")


def down(error="URLError"):
    """연결 실패(상태 0)."""
    return v.Resp(0, b"", {}, error)


def entries(*pairs):
    """posts.json 항목 목록. pairs: (글 이름 'category/file.md', 주소)."""
    return [{"path": "_posts/" + name, "absoluteUrl": url} for name, url in pairs]


def index_resp(value, status=200, headers=None):
    return v.Resp(status, json.dumps(value, ensure_ascii=False).encode("utf-8"), dict(headers or {}), "")


class FakeClock:
    """가상 시계: sleep 이 시간을 앞으로 보낸다."""

    def __init__(self):
        self.t = 0.0
        self.sleeps = []

    def __call__(self):
        return self.t

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.t += seconds


class FakeSite:
    """공개 사이트 대역. routes: {쿼리 없는 주소: 응답 | 응답 목록(호출 순서, 마지막이 반복) | 함수(호출 번호) -> 응답}.
    없는 주소는 404. clock 이 있으면 요청마다 latency 초가 지난다."""

    def __init__(self, routes=None, clock=None, latency=0.0):
        self.routes = dict(routes or {})
        self.clock, self.latency = clock, latency
        self.calls = []  # (쿼리 없는 주소, 전체 주소, limit, 시작 시각)
        self.counts = {}

    def __call__(self, url, limit=v.MAX_BYTES):
        bare = url.split("?")[0]
        n = self.counts.get(bare, 0)
        self.counts[bare] = n + 1
        self.calls.append((bare, url, limit, self.clock.t if self.clock else None))
        if self.clock:
            self.clock.t += self.latency
        script = self.routes.get(bare, page(404))
        if callable(script):
            return script(n)
        if isinstance(script, list):
            return script[min(n, len(script) - 1)]
        return script

    def bare_urls(self):
        return [call[0] for call in self.calls]

    def starts(self):
        return [call[3] for call in self.calls]


class Flushy(io.StringIO):
    """flush 호출 수를 센다(파이프 stdout 에서도 진행 로그가 바로 보이는지)."""

    def __init__(self):
        super().__init__()
        self.flushes = 0

    def flush(self):
        self.flushes += 1
        super().flush()
