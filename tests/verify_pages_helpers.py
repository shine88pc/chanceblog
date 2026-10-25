"""Pages 배포 후 확인(scripts/verify_pages_deploy.py) 테스트 공용 도구: 임시 저장소, 가짜 사이트·시계. 네트워크 없음."""
import io
import json
import re
import sys
import urllib.parse
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
    """가상 시계: sleep 이 시간을 앞으로 보낸다. max_sleeps 번을 넘게 자면 예외로 멈춘다 — 마감·간격 계산이 틀려도(회귀든
    변이든) 테스트가 끝없이 돌지 않고 바로 실패한다."""

    def __init__(self, max_sleeps=500):
        self.t = 0.0
        self.sleeps = []
        self.max_sleeps = max_sleeps

    def __call__(self):
        return self.t

    def sleep(self, seconds):
        if len(self.sleeps) >= self.max_sleeps:
            raise AssertionError(f"가상 시계가 {self.max_sleeps}번을 넘게 잤다 — 마감이 지나도 확인이 끝나지 않는다")
        self.sleeps.append(seconds)
        self.t += seconds


def unshaped(url):
    """쿼리와 요청 모양(끝의 index.html·연속 슬래시·`./`)을 걷어 낸 정규 주소. 원본이 모양을 같은 글로 정규화하는 것과 같다."""
    scheme, sep, rest = url.split("?")[0].partition("://")
    host, slash, path = rest.partition("/")
    path = re.sub(r"/{2,}", "/", slash + path).replace("/./", "/")
    if path.endswith("/index.html"):
        path = path[:-len("index.html")]
    return scheme + sep + host + path


class FakeSite:
    """공개 사이트 대역. routes: {쿼리 없는 정규 주소: 응답 | 응답 목록(호출 순서, 마지막이 반복) | 함수(호출 번호) -> 응답}.
    요청 모양을 바꾼 주소(index.html·`//`·`./`)는 같은 글의 정규 주소로 보고, Accept-Encoding 은 라우팅에 쓰지 않는다.
    없는 주소는 404. clock 이 있으면 요청마다 latency 초가 지난다."""

    def __init__(self, routes=None, clock=None, latency=0.0):
        self.routes = dict(routes or {})
        self.clock, self.latency = clock, latency
        self.calls = []  # (정규 주소, 보낸 전체 주소, limit, 시작 시각, 추가 헤더)
        self.counts = {}

    def __call__(self, url, limit=v.MAX_BYTES, headers=None):
        bare = unshaped(url)
        n = self.counts.get(bare, 0)
        self.counts[bare] = n + 1
        self.calls.append((bare, url, limit, self.clock.t if self.clock else None, headers))
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


class FakeCdn:
    """공개 CDN 대역. 2026-10-25 독립 검증이 실제 사이트(shine88pc.github.io)에서 잰 동작을 따른 모델이다.

    - 캐시 키 = (경로 문자열 그대로, 정규화한 Accept-Encoding). 쿼리 문자열·Cache-Control 요청 헤더는 키에 쓰지 않는다.
      Accept-Encoding 은 gzip·deflate 만 따로 보고 나머지(없음·identity·br)는 한 객체다.
    - 200 은 ttl200(600초), 404 는 ttl404(1100초 — 검증자 1회 측정 약 1114초) 동안 보관한다. 보관 중에는 원본에 다시 묻지 않는다.
    - 원본: 같은 글로 정규화되는 경로(연속 슬래시·`./`·끝의 index.html 변형)는 visible_at 시각부터 200, 그 전과 다른 경로는 404.
      posts.json 은 언제나 빈 목록 200 이다.
    requests: 요청마다 (시각, 경로, Accept-Encoding 분류, 상태, 보관 객체였는가).
    """

    def __init__(self, clock, visible_at, post_path, ttl200=600.0, ttl404=1100.0, index_path=None):
        self.clock, self.visible_at, self.post_path = clock, visible_at, post_path
        self.ttl200, self.ttl404, self.index_path = ttl200, ttl404, index_path
        self.cache = {}
        self.requests = []

    @staticmethod
    def normalize(path):
        parts = [seg for seg in path.split("/") if seg not in ("", ".")]
        if parts and parts[-1] == "index.html":
            parts.pop()
        return "/" + "/".join(parts) + ("/" if parts else "")

    def __call__(self, url, limit=v.MAX_BYTES, headers=None):
        path = urllib.parse.urlsplit(url).path
        encoding = (headers or {}).get("Accept-Encoding", "")
        kind = encoding if encoding in ("gzip", "deflate") else ""
        now = self.clock.t
        if path == self.index_path:
            self.requests.append((now, path, kind, 200, False))
            return v.Resp(200, b"[]", {"x-cache": "MISS", "age": "0"}, "")
        entry = self.cache.get((path, kind))
        hit = bool(entry) and now - entry[1] < (self.ttl200 if entry[0] == 200 else self.ttl404)
        if hit:
            status, born = entry
        else:
            status = 200 if self.normalize(path) == self.post_path and now >= self.visible_at else 404
            born = now
            self.cache[(path, kind)] = (status, born)
        self.requests.append((now, path, kind, status, hit))
        return v.Resp(status, b"", {"x-cache": "HIT" if hit else "MISS", "age": str(int(now - born))}, "")

    def page_keys(self):
        """글 주소 요청들의 캐시 키(경로, Accept-Encoding 분류)."""
        return [(path, kind) for _, path, kind, _, _ in self.requests if path != self.index_path]
