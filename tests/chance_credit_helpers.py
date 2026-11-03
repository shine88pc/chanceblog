"""Chance(generator.py)의 Unsplash 출처·ixid 시험 공용 도구: 가짜 Unsplash(urlopen 자리에 넣는 객체)·가짜 고정 목록 조회·상태 초기화. 네트워크를 쓰지 않는다.

가짜 응답의 모양은 tests/main_image_helpers.py 의 photo_item(Unsplash API 의 사진 항목: id·urls.raw·links.download_location·user)을 그대로 쓴다.
"""
import contextlib
import io
import urllib.error
import urllib.parse
import unittest
from unittest import mock

import _bootstrap  # noqa: F401
import generator as g
from main_image_helpers import FakeResponse, photo_item, results

FAKE_KEY = "unsplash-chance-" + "key-0123456789abcdef"      # 가짜 키(실제 키가 아니다). 시험이 이 글자가 어떤 출력에도 없는지 본다
PHOTO_RAW = "https://images.unsplash.com/photo-1500000000000-{pid}?ixid=M3wxfDB8&ixlib=rb-4.0.3"


def pool_photo_item(pool_url, name="Pool Author", **fields):
    """고정 목록 사진 하나의 `GET /photos/photo-<번호>` 가짜 응답(같은 번호의 주소를 urls.raw 로 돌려준다)."""
    path = urllib.parse.urlsplit(pool_url).path
    raw = f"https://images.unsplash.com{path}?ixid=POOL{path[-6:].replace('-', 'x')}&ixlib=rb-4.0.3"
    pid = "P" + path[-9:].replace("-", "x")
    return photo_item(pid, raw=raw, name=name, username=name.lower().replace(" ", ""), **fields)


def fake_pool_photo(pool_url):
    """`generator.fetch_pool_photo` 의 가짜 — 키 없는 시험(연습 아님)이 네트워크 없이 '조회에 성공한 고정 목록 사진'을 얻게 한다. 진짜처럼 ixid 가 든 주소를 돌려주고 출처를 기록부에 적는다."""
    url = pool_url.replace("?auto=format", "?ixid=FAKEIXID&auto=format")
    g._credits[g.image_key(url)] = ("Pool Photographer", "https://unsplash.com/@pool_photographer")
    return url


class FakeApi:
    """urllib.request.urlopen 자리에 넘기는 가짜 Unsplash. 요청을 모두 `calls` 에 적고 경로별로 답한다.

    searches: `/search/photos` 응답(dict JSON·예외·FakeResponse)을 차례로(모자라면 마지막 것을 되풀이한다). 비우면 결과 없는 응답.
    photos: {사진 번호(`photo-…`): 응답} — `/photos/<id>` 조회. 없는 번호는 404. 값이 함수면 (id) → 응답.
    download_error: `/photos/<id>/download` 에서 던질 예외. 이미지 주소(HEAD)에는 200 으로 답한다.
    """

    def __init__(self, searches=None, photos=None, download_error=None, headers=None):
        self.searches = list(searches) if searches else [results()]
        self.photos = dict(photos or {})
        self.download_error, self.headers = download_error, headers or {}
        self.calls = []

    def __call__(self, request, timeout=None):
        parts = urllib.parse.urlsplit(request.full_url)
        self.calls.append({"url": request.full_url, "host": parts.netloc, "path": parts.path, "query": urllib.parse.parse_qs(parts.query),
                           "headers": dict(request.header_items()), "redirectable": dict(request.headers), "unredirected": dict(request.unredirected_hdrs),
                           "method": request.get_method(), "timeout": timeout, "request": request})      # 기록을 먼저 한다: 아래 단정이 터져도(호출한 쪽이 예외를 삼켜도) 어떤 요청이 나갔는지 남는다
        if parts.scheme != "https":
            raise AssertionError(f"https 가 아닌 주소로 요청했습니다: {request.full_url}")
        if parts.netloc == "images.unsplash.com":
            return FakeResponse(b"", status=200)
        if parts.netloc != "api.unsplash.com":
            raise AssertionError(f"시험이 모르는 호스트로 요청했습니다: {request.full_url}")
        if parts.path == "/search/photos":
            reply = self.searches.pop(0) if len(self.searches) > 1 else self.searches[0]
            return self.answer(reply, request.full_url)
        if parts.path.endswith("/download"):
            if self.download_error is not None:
                raise self.download_error
            return FakeResponse({"url": "https://images.unsplash.com/photo-1"})
        if parts.path.startswith("/photos/"):
            reply = self.photos.get(parts.path[len("/photos/"):])
            if callable(reply):
                reply = reply(parts.path[len("/photos/"):])
            if reply is None:
                raise urllib.error.HTTPError(request.full_url, 404, "Not Found", {}, io.BytesIO(b"{}"))
            return self.answer(reply, request.full_url)
        raise AssertionError(f"시험이 모르는 주소로 요청했습니다: {request.full_url}")

    def answer(self, reply, url):
        if isinstance(reply, BaseException):
            raise reply
        return reply if isinstance(reply, FakeResponse) else FakeResponse(reply, headers=self.headers)

    def paths(self, prefix=""):
        return [call["path"] for call in self.calls if call["host"] == "api.unsplash.com" and call["path"].startswith(prefix)]

    @property
    def searched(self):
        return [call["query"]["query"][0] for call in self.calls if call["path"] == "/search/photos"]

    @property
    def lookups(self):
        return [call["path"] for call in self.calls if call["path"].startswith("/photos/") and not call["path"].endswith("/download")]

    @property
    def downloads(self):
        return [call["path"] for call in self.calls if call["path"].endswith("/download")]


def http_error(status, headers=None, url="https://api.unsplash.com/photos/x"):
    return urllib.error.HTTPError(url, status, "error", headers or {}, io.BytesIO(b"{}"))


class ChanceBase(unittest.TestCase):
    """키가 있는 실제 실행 상태(STUB_UNSPLASH=False·DRY_RUN=False)에서 가짜 Unsplash 로 도는 시험의 바탕. 기록부(_credits·_download_locations)와 한도 기록을 시험마다 비운다.

    self.api 를 `FakeApi(...)` 로 바꾸고 `self.use(api)` 로 urlopen 을 갈아 끼운다. 이미지 주소 확인(url_ok)은 항상 통과로 둔다(HEAD 는 FakeApi 도 받지만 시험이 느려지지 않게)."""

    def setUp(self):
        self.out = io.StringIO()
        for patcher in (mock.patch.multiple(g, STUB_UNSPLASH=False, UNSPLASH_KEY=FAKE_KEY, DRY_RUN=False),
                        mock.patch.dict(g._credits, clear=True), mock.patch.dict(g._download_locations, clear=True),
                        mock.patch.dict(g.UNSPLASH_RATE, {"remaining": None, "limit": None}),
                        mock.patch.object(g, "url_ok", lambda url, timeout=10: True)):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.api = FakeApi()

    def use(self, api):
        self.api = api
        patcher = mock.patch("urllib.request.urlopen", api)
        patcher.start()
        self.addCleanup(patcher.stop)
        return api

    @contextlib.contextmanager
    def captured(self):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            yield buffer

    def call(self, function, *args, **kwargs):
        """함수를 부르고 (돌려준 값, 찍은 글)을 돌려준다."""
        with self.captured() as buffer:
            value = function(*args, **kwargs)
        return value, buffer.getvalue()
