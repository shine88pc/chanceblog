"""대표 사진(pipeline/main_image.py) 시험 공용 도구: 가짜 Unsplash(opener)·검색 결과 만들기·영어 검색어를 돌려주는 가짜 LLM. 네트워크를 쓰지 않는다.

실제 Unsplash 호출은 한 번도 하지 않는다 — 응답의 모양은 Unsplash API 문서의 `/search/photos` 항목(id·alt_description·urls.raw·links.download_location·user)을 따랐지만
실제 응답과 글자까지 같은지는 첫 실제 실행에서만 확인된다.
"""
import io
import json
import urllib.error
import urllib.parse

from pipeline.stubs import stub_llm

KEY = "unsplash-test-" + "key-0123456789abcdef"   # 가짜 키(실제 키가 아니다). 시험이 이 글자가 어떤 출력에도 없는지 본다
DEFAULT_QUERIES = '{"image_queries": ["morning coffee cup", "coffee on table", "breakfast"]}'


def photo_item(photo_id="Abc123XyZ_k", **fields):
    """Unsplash 검색 결과 한 건(실제 응답과 같은 모양). fields 로 칸을 바꾼다: raw·download·name·username·author_url·alt(None 이면 alt_description 이 null)·
    칸을 통째로 빼려면 `remove=("urls", "links", "user", "alt_description")` 를 준다."""
    name = fields.get("name", "Jane Doe")
    username = fields.get("username", "janedoe")
    item = {
        "id": photo_id,
        "alt_description": fields.get("alt", "a cup of coffee on a wooden table"),
        "urls": {"raw": fields.get("raw", f"https://images.unsplash.com/photo-1500000000000-{photo_id.lower()}?ixid=M3wxfDB8&ixlib=rb-4.0.3"),
                 "regular": f"https://images.unsplash.com/photo-1500000000000-{photo_id.lower()}?w=1080"},
        "links": {"html": f"https://unsplash.com/photos/{photo_id}", "download": f"https://unsplash.com/photos/{photo_id}/download",
                  "download_location": fields.get("download", f"https://api.unsplash.com/photos/{photo_id}/download?ixid=M3wxfDB8")},
        "user": {"username": username, "name": name, "links": {"html": fields.get("author_url", f"https://unsplash.com/@{username}")}},
    }
    for key in fields.get("remove", ()):
        item.pop(key, None)
    return item


def results(*items):
    return {"total": len(items), "total_pages": 1, "results": list(items)}


def http_error(status, headers=None, url="https://api.unsplash.com/search/photos"):
    return urllib.error.HTTPError(url, status, "error", headers or {}, io.BytesIO(b"{}"))


class FakeResponse:
    """urlopen 이 돌려주는 응답 흉내: with 로 쓰고 read(amt)·headers 가 있다."""

    def __init__(self, body=b"{}", headers=None, status=200):
        self._body = body if isinstance(body, (bytes, bytearray)) else json.dumps(body).encode("utf-8")
        self.headers, self.status = headers or {}, status

    def read(self, amt=None):
        return self._body if amt is None else self._body[:amt]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeUnsplash:
    """urllib.request.urlopen 자리에 넘기는 opener. 검색 요청(/search/photos)에는 `searches` 를 차례로 돌려주고(모자라면 마지막 것을 되풀이한다),
    download 요청(/photos/<id>/download)은 `pings` 에 기록한다. 그 밖의 주소는 시험이 틀렸다는 뜻이라 AssertionError 다.

    searches 의 항목: dict(응답 JSON) · bytes(본문 그대로) · 예외 객체(던진다) · FakeResponse(그대로). headers: 성공 응답에 실을 머리글.
    ping_error: download 요청에서 던질 예외. calls: 모든 요청의 기록(주소·호스트·경로·질의·머리글·timeout)."""

    def __init__(self, *searches, headers=None, ping_error=None):
        self.searches = list(searches) or [results()]
        self.headers, self.ping_error = headers or {}, ping_error
        self.calls = []

    def __call__(self, request, timeout=None):
        parts = urllib.parse.urlsplit(request.full_url)
        if parts.scheme != "https":      # 독립 검증 F3: http 로 가면 키가 평문으로 나간다
            raise AssertionError(f"https 가 아닌 주소로 요청했습니다: {request.full_url}")
        self.calls.append({"url": request.full_url, "host": parts.netloc, "path": parts.path, "query": urllib.parse.parse_qs(parts.query),
                           "headers": dict(request.header_items()), "timeout": timeout})
        if parts.path == "/search/photos":
            reply = self.searches.pop(0) if len(self.searches) > 1 else self.searches[0]
            if isinstance(reply, BaseException):
                raise reply
            return reply if isinstance(reply, FakeResponse) else FakeResponse(reply, headers=self.headers)
        if parts.path.endswith("/download"):
            if self.ping_error is not None:
                raise self.ping_error
            return FakeResponse({"url": "https://images.unsplash.com/photo-1"})
        raise AssertionError(f"시험이 모르는 주소로 요청했습니다: {request.full_url}")

    @property
    def searched(self):
        """검색 요청의 검색어 목록(보낸 순서대로)."""
        return [call["query"]["query"][0] for call in self.calls if call["path"] == "/search/photos"]

    @property
    def pings(self):
        return [call for call in self.calls if call["path"].endswith("/download")]


class QueryLLM:
    """영어 검색어 요청(프롬프트에 `image_queries` 가 있다)에는 정해진 응답을 주고, 그 밖의 요청(글·주제)은 스텁 LLM 에 맡기는 가짜 호출 객체.
    reply: 검색어 요청에 돌려줄 글. fail: 검색어 요청에서 던질 예외. prompts: 받은 검색어 요청 프롬프트 전부. all_prompts: 모든 프롬프트."""

    def __init__(self, reply=DEFAULT_QUERIES, fail=None, inner=stub_llm):
        self.reply, self.fail, self.inner = reply, fail, inner
        self.prompts, self.all_prompts = [], []

    def __call__(self, prompt):
        self.all_prompts.append(prompt)
        if "image_queries" in prompt:
            self.prompts.append(prompt)
            if self.fail is not None:
                raise self.fail
            return self.reply, "stub"
        return self.inner(prompt)
