"""'꺼진 기능은 출력이 바이트까지 이전과 같다'를 보이는 시나리오 모음(source_policy 가 legacy 일 때의 생성기 동작).

모든 시나리오는 생성기 모듈 `g` 와 작업 폴더를 인자로 받고 네트워크·시계·무작위·진짜 키 없이 돈다(가짜 피드·가짜 기사 페이지·가짜 Gemini·스텁 이미지). 결과는 시나리오별 sha256 이다.
이 모듈은 소스 정책(pipeline/source_policy.py)을 전혀 모른다 — 그래서 소스 정책이 없는 옛 생성기와 새 생성기에 똑같이 돌려 값을 견줄 수 있다.

다시 만드는 법(시나리오를 바꿨을 때): 기준 커밋(소스 정책 도입 전 main)의 작업 사본을 만들고 그 루트와 이 폴더를 경로에 올려 이 모듈을 직접 돌린다.
    PYTHONPATH=<기준 사본 루트>:<이 tests 폴더> python -X utf8 -m source_policy_scenarios <임시 작업 폴더>
출력된 JSON 의 값을 tests/test_generator_source_policy.py 의 GOLDEN 에 옮긴다(이 값들은 기준 커밋 78c6b89 의 generator.py 가 만든 것이다).
"""
import contextlib
import datetime
import hashlib
import io
import json
import os
import pathlib
import re
import sys
import tempfile
import urllib.parse
from unittest import mock

KST = datetime.timezone(datetime.timedelta(hours=9))
FUTURE = "2099-01-01T00:00:00Z"            # 피드 항목 날짜: 먼 미래라 72시간 창 판정이 시계와 무관하게 '최근'이다
NOW = datetime.datetime(2026, 11, 9, 10, 12, tzinfo=KST)


def digest(*parts):
    h = hashlib.sha256()
    for part in parts:
        h.update(part.encode("utf-8") if isinstance(part, str) else part)
        h.update(b"\x00")
    return h.hexdigest()


class FakeHTTP:
    """urlopen 이 돌려주는 응답 대신 쓰는 가짜(with 로 쓸 수 있다)."""

    def __init__(self, body, url):
        self._body, self._url = body, url

    def read(self, n=-1):
        return self._body if n is None or n < 0 else self._body[:n]

    def geturl(self):
        return self._url

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def feed_xml(name, host, count=4):
    """가짜 Atom 피드: 항목마다 제목·링크(그 피드 호스트)·미래 날짜·요약. 마지막 항목은 요약이 짧아 기사 페이지 발췌 경로를 지난다."""
    entries = []
    for i in range(count):
        summary = (f"{name} item {i} summary " * 12)[:320] if i < count - 1 else "short"
        entries.append(f"<entry><title>{name} headline number {i}</title><link href=\"https://{host}/news/{re.sub('[^a-z0-9]+', '-', name.lower())}-{i}\"/>"
                       f"<updated>{FUTURE}</updated><summary>{summary}</summary></entry>")
    return ("<?xml version=\"1.0\"?><feed xmlns=\"http://www.w3.org/2005/Atom\">" + "".join(entries) + "</feed>").encode("utf-8")


def page_html(url):
    desc = ("Official page description for " + urllib.parse.urlsplit(url).path + " ") * 4
    return f"<html><head><meta name=\"description\" content=\"{desc.strip()}\"></head><body>x</body></html>".encode("utf-8")


class FakeNet:
    """urllib.request.urlopen 자리에 넣는 가짜: 소스 피드 주소는 가짜 Atom, 그 밖은 가짜 기사 페이지. 요청(메서드·주소·User-Agent·제한 시간)을 순서대로 적는다."""

    def __init__(self, g):
        self.calls = []
        self.feeds = {src["url"]: feed_xml(src["name"], urllib.parse.urlsplit(src["url"]).hostname) for src in g.NEWS_SOURCES}

    def __call__(self, request, timeout=None):
        url = request.full_url if hasattr(request, "full_url") else str(request)
        method = request.get_method() if hasattr(request, "get_method") else "GET"
        ua = request.get_header("User-agent") if hasattr(request, "get_header") else None
        self.calls.append((method, url, ua, timeout))
        return FakeHTTP(self.feeds.get(url) or page_html(url), url)

    def log(self):
        return "\n".join(f"{m} {u} {ua} {t}" for m, u, ua, t in self.calls)


def fake_model(g):
    """call_gemini_with_fallback 자리에 넣는 가짜 모델: 프롬프트의 주제(첫 줄)와 원문 URL 로 본문 검증을 통과하는 스텁 글(g.stub_post_data)을 JSON 으로 돌려준다."""
    def call(prompt):
        topic = re.search(r"\[주제\]\n(.*)", prompt).group(1)
        link = re.search(r"\[원문 URL\] (\S+)", prompt)
        return type("R", (), {"text": json.dumps(g.stub_post_data(topic, link.group(1) if link else None))})()
    return call


def fake_pick_images(g):
    """pick_images 자리에 넣는 가짜: 항상 사진 count 장(고정 주소)을 돌려주고 작가 출처를 기록부에 적는다(출처 없는 사진은 저장되지 않는다)."""
    def pick(queries, used, count=1, allow_pool=False):
        urls = [f"https://images.unsplash.com/photo-1500000000000-fake{i}?ixid=FAKE{i}&auto=format&fit=crop&w=1000&q=80" for i in range(count)]
        for url in urls:
            g._credits[g.image_key(url)] = ("Fake Author", "https://unsplash.com/@fakeauthor")
            used.add(g.image_key(url))
        return urls
    return pick


def _patches(g, net, history, summary_path, **flags):
    base = dict(DRY_RUN=False, STUB_GEMINI=True, STUB_UNSPLASH=True, FIX_IMAGES=False, EVENT_NAME="schedule")
    base.update(flags)
    stack = contextlib.ExitStack()
    stack.enter_context(mock.patch.multiple(g, **base))
    stack.enter_context(mock.patch.object(g, "now_kst", return_value=NOW))
    stack.enter_context(mock.patch.object(g, "draft_flow_on", return_value=False))
    stack.enter_context(mock.patch("urllib.request.urlopen", net))
    stack.enter_context(mock.patch("time.sleep", lambda s: None))
    stack.enter_context(mock.patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": str(summary_path)}, clear=False))
    stack.enter_context(mock.patch.dict(os.environ, {"PIPELINE_PAUSE": ""}, clear=False))
    # 같은 프로세스의 다른 시험이 남긴 모듈 전역 상태(호출 횟수·사진 한도·호출 기록·출처 기록부)가 요약·출력에 섞이지 않게 한다
    stack.enter_context(mock.patch.dict(g.GEMINI_CALLS, {"attempts": 0, "failed": 0}))
    stack.enter_context(mock.patch.dict(g.UNSPLASH_RATE, {"remaining": None, "limit": None}))
    stack.enter_context(mock.patch.dict(g._credits))
    stack.enter_context(mock.patch.object(g, "CALL_LOG", g.CallLog(label="chance", purpose="post", out=print, secrets=())))
    if history is not None:
        (g.HISTORY_FILE).write_text(json.dumps(history, ensure_ascii=False), encoding="utf-8")
    return stack


def _tree_digest(root):
    """작업 폴더의 파일 모두(상대 경로·내용)를 차례로 해시한다."""
    parts = []
    for path in sorted(root.rglob("*")):
        if path.is_file():
            parts.append(path.relative_to(root).as_posix())
            parts.append(path.read_bytes().replace(b"\r\n", b"\n"))      # 운영체제가 달라도 같은 값이 되게 윈도의 줄 끝(CRLF)을 LF 로 통일한다
    return digest(*parts)


def scenario_prompts(g):
    """build_post_prompt 14가지 입력(분야·힌트·skip 허용 여부 조합 + 출처 없음 + 제목만) — 프롬프트 바이트."""
    item = {"title": "예시 기사", "source": "Example", "link": "https://x.example/a", "published": datetime.datetime(2026, 11, 4, tzinfo=datetime.timezone.utc),
            "summary": "요약 문장입니다. " * 20, "prompt_rule": "소스 규칙 한 줄."}
    outs = [g.build_post_prompt(item, ["이전 제목 하나", "이전 제목 둘"], hint, skip, lane)
            for lane in ("economy", "technology", "daily_life") for hint in ("", "과학·환경") for skip in (False, True)]
    outs.append(g.build_post_prompt(None, [], "", False, "society"))
    outs.append(g.build_post_prompt({"title": "제목만"}, ["a"], "", True, "culture"))
    return digest(*outs)


def scenario_fetch_all_lanes(g):
    """모든 분야의 fetch_news_items: 출력 글·돌려준 후보(요약·출처·인용 틀 포함)·요청 순서."""
    net = FakeNet(g)
    parts = []
    with mock.patch("urllib.request.urlopen", net), mock.patch("time.sleep", lambda s: None):
        for lane in g.EDITORIAL_LANES:
            out, stats = io.StringIO(), {}
            with contextlib.redirect_stdout(out):
                items = g.fetch_news_items(lane, stats=stats)
            parts += [lane, out.getvalue(), json.dumps(stats, sort_keys=True, ensure_ascii=False),
                      json.dumps([{k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in sorted(item.items())} for item in items], ensure_ascii=False, sort_keys=True)]
    parts.append(net.log())
    return digest(*parts)


def scenario_excerpt_and_resolver(g):
    """기사 페이지 발췌(_fetch_source_excerpt)와 주소 해석(_resolve_article_url)을 직접 부른 결과."""
    net = FakeNet(g)
    with mock.patch("urllib.request.urlopen", net):
        parts = [g._fetch_source_excerpt("https://www.nasa.gov/news/a"), g._resolve_article_url("https://www.nasa.gov/news/b"), g._resolve_article_url(""), net.log()]
    return digest(*parts)


def scenario_main(g, workdir, name, event, dry_run):
    """main() 한 번: 표준 출력·실행 요약·작업 폴더의 모든 파일(글·이력)·요청 순서. 가짜 피드 + 스텁 모델(스텁 응답은 본문 검증을 통과하도록 만들어져 있다) + 스텁 이미지."""
    work = workdir / name
    posts, summary = work / "_posts", work / "summary.md"
    posts.mkdir(parents=True)
    old_cwd = os.getcwd()
    os.chdir(work)
    try:
        net = FakeNet(g)
        out = io.StringIO()
        code = None
        gemini_flags = dict(STUB_GEMINI=True) if dry_run else dict(STUB_GEMINI=False)
        with _patches(g, net, [{"date": "2026-11-08", "topic": "어제의 글감", "slot": 18, "source_url": "https://x.example/y"}], summary, EVENT_NAME=event, DRY_RUN=dry_run, **gemini_flags):
            with contextlib.ExitStack() as extra:
                if not dry_run:                               # 실제 쓰기 시나리오: 가짜 모델과 가짜 사진 선택기(출처가 기록된 사진 두 장)
                    extra.enter_context(mock.patch.object(g, "call_gemini_with_fallback", fake_model(g)))
                    extra.enter_context(mock.patch.object(g, "pick_images", fake_pick_images(g)))
                with contextlib.redirect_stdout(out):
                    try:
                        g.main()
                    except SystemExit as exc:
                        code = exc.code
        text = summary.read_text(encoding="utf-8") if summary.exists() else ""
        (work / "summary.md").unlink(missing_ok=True)
        return digest(out.getvalue().replace("\\", "/"), str(code), text.replace("\\", "/"), net.log(), _tree_digest(work))      # 윈도 경로 구분자(역슬래시)도 리눅스와 같게 통일한다
    finally:
        os.chdir(old_cwd)


def scenario_finish_outcomes(g):
    """finish_run 이 옛 결과 코드마다 하는 일(출력·종료)과 render_run_summary 의 요약 — 새 결과 코드를 더해도 옛 코드의 동작은 같다."""
    parts = []
    for outcome in ("PUBLISHED", "DRAFT_CREATED", "ALL_LANES_EMPTY", "SOURCES_UNREACHABLE", "ALL_DUPLICATES", "NO_CANDIDATES", "ALL_REJECTED", "NO_MATCH", "UNKNOWN_CODE"):
        for result in (None, ("a", "b")):
            report = {"outcome": outcome, "lanes": [], "title": "제목", "paths": ["_posts/a.md"], "gemini_calls": {"attempts": 0, "failed": 0}, "gemini_notes": [], "unsplash_rate": {}}
            out, code = io.StringIO(), None
            summary_dir = tempfile.mkdtemp()
            target = os.path.join(summary_dir, "s.md")
            with mock.patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": target}), mock.patch.object(g, "DRY_RUN", False), contextlib.redirect_stdout(out):
                try:
                    g.finish_run(result, report, "schedule", NOW, 9)
                except SystemExit as exc:
                    code = exc.code
            text = pathlib.Path(target).read_text(encoding="utf-8") if os.path.exists(target) else ""
            parts += [outcome, str(result), out.getvalue(), str(code), text]
    return digest(*parts)


def run_all(g, workdir):
    """모든 시나리오의 sha256. workdir 은 비어 있는 임시 폴더."""
    from pathlib import Path
    workdir = Path(workdir)
    return {
        "prompts": scenario_prompts(g),
        "fetch_all_lanes": scenario_fetch_all_lanes(g),
        "excerpt_and_resolver": scenario_excerpt_and_resolver(g),
        "main_schedule_dry_run": scenario_main(g, workdir, "schedule_dry", "schedule", True),
        "main_manual_dry_run": scenario_main(g, workdir, "manual_dry", "workflow_dispatch", True),
        "main_schedule_write": scenario_main(g, workdir, "schedule_write", "schedule", False),
        "main_manual_write": scenario_main(g, workdir, "manual_write", "workflow_dispatch", False),
        "finish_outcomes": scenario_finish_outcomes(g),
    }


if __name__ == "__main__":
    import generator
    folder = sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp()
    print(json.dumps(run_all(generator, folder), indent=1, sort_keys=True))
