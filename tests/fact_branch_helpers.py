"""구조화 Fact 경로 연결(S2b) 시험의 공통 도구. 네트워크·시계·진짜 키 없음 — 응답은 시험이 만든 가상 값이고(NOAA 자료가 아니다 — 모양만 같다), 가짜 transport 가 주소로 돌려준다.

- `payloads(day)`: 그날(한국 날짜)을 기준으로 글감 여섯 개가 모두 글이 되는 가상 응답(제품 → JSON 값).
- `FakeNoaa`: `make_fact_transport` 자리에 넣는 가짜 transport 공장 — 요청한 주소를 순서대로 적고 제품별 응답을 돌려준다(응답을 바꾸거나 오류를 내게 할 수 있다).
- `facts_registry`·`sources_registry`: 켜지는 값이 하나도 없는 실제 파일의 사본을 만들어 **시험 안에서만** facts·enabled 로 바꾼다(저장소의 blogs.json·허용 목록 파일은 그대로다).
- `FactEnv`: 임시 작업 폴더·레지스트리 사본·가짜 시계·AI·피드·사진 함수를 부르면 실패하는 감시자를 갖춘 시험 바탕.
"""
import contextlib
import copy
import datetime
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import _bootstrap
import generator as g
import space_helpers as H
import test_space_recipes as TR

from pipeline import registry, source_registry
from pipeline.adapters import noaa_swpc as N
from registry_states import pre_flip_registry

ROOT = _bootstrap.ROOT
KST = datetime.timezone(datetime.timedelta(hours=9))
PROVIDER_ID = "noaa_swpc_json"
FLARE_CLASSES = ("B4.8", "B4.2", "C1.2", "C2.2", "C5.0", "M2.1", "C9.9", "M1.4", "B9.0", "C3.3")
PROBS = TR.PROBS
AI_NAMES = ("call_gemini_with_fallback", "build_post_prompt", "make_image_queries", "get_client", "fetch_news_items", "pick_images", "_fetch_source_excerpt", "_resolve_article_url",
            "search_unsplash", "trigger_download", "url_ok", "fetch_pool_photo")


def at(day, hour=10, minute=12):
    """한국 시각(KST) — 10시 12분이면 협정 세계시 01시 12분(일별 흑점수 하한 00:30 UTC 이후)이다."""
    day = datetime.date.fromisoformat(day) if isinstance(day, str) else day
    return datetime.datetime(day.year, day.month, day.day, hour, minute, tzinfo=KST)


def day_back(day, count):
    return (day - datetime.timedelta(days=count)).isoformat()


def payloads(day):
    """day(한국 날짜)를 기준으로 글감 여섯 개가 모두 글이 되는 가상 응답 {제품: 값}. 값은 어댑터가 읽는 JSON 모양이고 날짜는 모두 day 보다 앞이다."""
    day = datetime.date.fromisoformat(day) if isinstance(day, str) else day
    month = day.year * 12 + day.month - 2
    events = []
    for index, class_text in enumerate(FLARE_CLASSES):
        stamp_day = day - datetime.timedelta(days=7 - min(index * 7 // len(FLARE_CLASSES), 6))
        events.append((f"{stamp_day.isoformat()}T{(index * 5) % 20 + 2:02d}:15:00Z", class_text))
    events = sorted(set(events))
    return {
        "kp_estimated": H.kp_rows(day_back(day, 8), 8, storm_days=(2,), partial_last=3),
        "ssn_daily": H.ssn_daily_rows(day_back(day, 1), 70),
        "ssn_monthly": H.ssn_monthly_rows(f"{month // 12:04d}-{month % 12 + 1:02d}", 70),
        "xray_flares": H.flare_rows(events),
        "scales": H.scales_object(date_now=day.isoformat(), g_now="1", g_forecast=("1", "2", "0"), probs=PROBS),
    }


class FakeNoaa:
    """`make_fact_transport(sources)` 를 대신하는 가짜 공장: 부르면 transport 를 돌려준다. transport 는 요청 주소를 `calls` 에 적고 `by_product` 의 응답을 JSON 바이트로 돌려준다.
    `fail` 은 {제품: 예외}(그 제품을 부르면 올림), `raw` 는 {제품: 바이트}(JSON 이 아닌 응답이나 깨진 응답을 그대로 돌려줄 때)."""

    def __init__(self, day):
        self.by_product = payloads(day)
        self.calls, self.fail, self.raw, self.factory_calls = [], {}, {}, 0
        self.paths = {product.path: pid for pid, product in N.PRODUCTS.items()}

    def __call__(self, sources):
        self.factory_calls += 1
        return self.transport

    def transport(self, url, *, timeout, max_bytes):
        self.calls.append(url)
        product = self.paths["/" + url.split("/", 3)[3]]
        if product in self.fail:
            raise self.fail[product]
        if product in self.raw:
            return self.raw[product]
        return json.dumps(self.by_product[product], ensure_ascii=False).encode("utf-8")

    def products(self):
        return [self.paths["/" + url.split("/", 3)[3]] for url in self.calls]


def facts_registry(**chance):
    """실제 blogs.json 의 사본에서 chance 항목만 facts 로 켠 모양(시험 안에서만). 값을 더 바꾸려면 키워드로 넘긴다(값이 None 이면 그 키를 지운다)."""
    reg = pre_flip_registry()      # 켜기 전 고정 표본에서 출발한다(진짜 파일이 켜는 변경(T3) 뒤 값이어도 이 도우미의 바탕은 같다)
    values = {"content_source": "facts", "source_policy": "allowlist", "languages": ["ko"], "publish_flow": "pr"}
    values.update(chance)
    for blog in reg["blogs"]:
        if blog["key"] == "chance":
            for key, value in values.items():
                if value is None:
                    blog.pop(key, None)
                else:
                    blog[key] = value
    return reg


def sources_registry(enabled=True, **provider):
    """실제 허용 목록 파일의 사본에서 NOAA 항목만 enabled 로 켠 모양(시험 안에서만). provider 키워드는 그 항목의 칸을 덮어쓴다(값이 None 이면 지운다)."""
    data = json.loads((ROOT / "pipeline" / "source_registry.json").read_text(encoding="utf-8"))
    for item in data["providers"]:
        if item["provider_id"] == PROVIDER_ID:
            item["enabled"] = enabled
            for key, value in provider.items():
                if value is None:
                    item.pop(key, None)
                else:
                    item[key] = value
    return data


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return Path(path)


class FactEnv(unittest.TestCase):
    """임시 작업 폴더 안에서 운영과 같이 상대 경로(_posts·history.json)로 생성기를 돌리는 바탕. 레지스트리·허용 목록은 임시 사본이고(`self.use(…)` 로 바꾼다), AI·피드·사진 함수는 부르면 실패하는 감시자다."""
    NOW = at("2026-11-10")

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.work = self.tmp / "work"
        (self.work / "_posts").mkdir(parents=True)
        previous = os.getcwd()
        os.chdir(self.work)
        self.addCleanup(os.chdir, previous)
        self.noaa = FakeNoaa(self.NOW.date())
        self.now = self.NOW
        self.spies = {}
        for name, value in (("DRY_RUN", False), ("STUB_GEMINI", True), ("STUB_UNSPLASH", True), ("FIX_IMAGES", False), ("POSTS_DIR", Path("_posts")), ("HISTORY_FILE", Path("history.json")),
                            ("EVENT_NAME", "schedule")):
            self.patch_value(g, name, value)
        self.patch_value(g, "now_kst", lambda: self.now)
        self.patch_value(g, "make_fact_transport", self.noaa)
        for name in AI_NAMES:
            spy = mock.Mock(side_effect=AssertionError(f"구조화 Fact 경로가 {name} 을(를) 불렀다"))
            self.spies[name] = spy
            self.patch_value(g, name, spy)
        self.use(facts_registry(), sources_registry())

    def patch_value(self, target, name, value):
        patcher = mock.patch.object(target, name, value)
        patcher.start()
        self.addCleanup(patcher.stop)

    def use(self, blogs, sources):
        """레지스트리(blogs.json 모양)와 허용 목록(source_registry.json 모양) 사본을 쓰게 한다."""
        self.patch_value(registry, "REGISTRY_PATH", write_json(self.tmp / "blogs.json", blogs))
        self.patch_value(source_registry, "DEFAULT_PATH", write_json(self.tmp / "sources.json", sources))

    def set_history(self, entries):
        (self.work / "history.json").write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")

    def history(self):
        path = self.work / "history.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []

    def posts(self):
        return sorted((self.work / "_posts").rglob("*.md"))

    def files(self):
        return sorted(path.relative_to(self.work).as_posix() for path in self.work.rglob("*") if path.is_file())

    def run_branch(self, slot=9, draft_flow=True, topic_override=None, settings=None):
        """generate_blog_posts 를 한 번 돌린다(운영과 같은 진입). 돌려주는 값: (반환값, 보고 사전, 표준 출력, 예외 또는 None)."""
        report, out, value, error = {}, io.StringIO(), None, None
        patches = []
        if settings is not None:
            patches.append(mock.patch.object(registry, "chance_settings", return_value=settings))
        with contextlib.ExitStack() as stack:
            for patch in patches:
                stack.enter_context(patch)
            with contextlib.redirect_stdout(out):
                try:
                    value = g.generate_blog_posts(slot=slot, allow_auto_topic=False, report=report, draft_flow=draft_flow, topic_override=topic_override)
                except (RuntimeError, ValueError) as exc:
                    error = exc
        return value, report, out.getvalue(), error

    def assert_nothing_written(self, before=None):
        self.assertEqual(self.posts(), [])
        self.assertEqual(self.files(), before if before is not None else [])
