"""Chance 엔진(generator.py)에 최소 품질 Gate 와 chance.languages 를 연결한 곳의 시험. 네트워크 없이 돈다(가짜 피드·가짜 Gemini·임시 폴더).

세 가지를 못박는다.
1. 기본값(quality_gate 없음·off, languages ["ko","en"])에서는 이전과 같다: Gate 를 부르지 않고 글을 그대로 만든다(옛 코드와의 바이트 비교는 저장소 밖 비교 도구가 한다 — 여기서는 호출 0·출력 불변 표지를 고정).
2. hold 에서는 규칙에 걸린 후보를 '본문 검증 탈락'과 같은 길로 버리고 다음 후보로 넘어가며, 전부 탈락하면 글 없이 경고로 끝난다.
3. languages 가 ["ko"] 면 영문은 만들지도·검증하지도·쓰지도 않는다(프롬프트·이력·글 파일·승인 초안).
"""
import ast
import datetime
import hashlib
import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import _bootstrap
import generator as g
import quality_gate_helpers as h
from chance_credit_helpers import fake_pool_photo
from lock_helpers import pre_flip
from pipeline import drafts, quality_gate as qg, registry
from test_generator_slots import at, run_captured

ROOT = _bootstrap.ROOT
OFF_BOTH = registry.ChanceSettings("off", ("ko", "en"))
HOLD_BOTH = registry.ChanceSettings("hold", ("ko", "en"))
OFF_KO = registry.ChanceSettings("off", ("ko",))
HOLD_KO = registry.ChanceSettings("hold", ("ko",))
SPLIT_FIELDS = ("kr_content", "en_content")


def candidate_item(n=0, **overrides):
    """h.fixture_source() 를 후보 번호마다 다른 제목·주소로 만든 후보 항목(서로 제목이 비슷하지 않게 한다)."""
    topics = ("가계 소득 조사", "선박 연료 규정", "도서관 이용 통계", "반도체 설비 투자", "항만 물동량")
    item = h.fixture_source(title=f"{topics[n % 5]} {n} 번째 발표 — 전혀 다른 소재 {n * 11}", link=f"{h.LINK}-{n}")
    item.update(overrides)
    return item


def model_json(item, ko=None, en=None, pair=True):
    """모델의 JSON 응답: 본문은 item 의 링크를 인용한다. pair=False 면 국문만(국문 전용 프롬프트에 대한 응답)."""
    data = h.make_data(ko=h.ko_body(link=item["link"]) if ko is None else ko, en=h.en_body(link=item["link"]) if en is None else en,
                       ko_title=h.KO_TITLE, en_title=h.EN_TITLE)
    out = {"kr_category": "예시", "kr_title": data["kr_title"], "kr_tags": ["예시"], "kr_content": data["kr_content"], "image_queries": ["a", "b", "c"]}
    if pair:
        out.update(en_category="Example", en_title=data["en_title"], en_tags=["example"], en_content=data["en_content"])
    return out


def without_images(text):
    """대표 사진과 작가 출처 줄을 뺀 글(사진은 실행마다 달라질 수 있어 글 내용을 견줄 때 뺀다)."""
    return "\n".join(line for line in text.split("\n") if not line.startswith("image:") and "unsplash.com" not in line and not line.startswith("![Thumbnail]"))


@pre_flip
class GenerationBase(unittest.TestCase):
    """generate_blog_posts 전체 흐름(가짜 피드·가짜 Gemini·임시 폴더)을 설정(settings)별로 돌린다. 운영과 같이 상대 경로(_posts·history.json)로 임시 폴더 안에서 돈다."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        previous = os.getcwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, previous)
        for name, value in (("DRY_RUN", False), ("STUB_GEMINI", False), ("STUB_UNSPLASH", True), ("FIX_IMAGES", False),
                            ("POSTS_DIR", Path("_posts")), ("HISTORY_FILE", Path("history.json")),
                            ("url_ok", lambda url, timeout=10: True), ("fetch_pool_photo", fake_pool_photo)):
            self.patch_value(name, value)
        self.patch_value("now_kst", lambda: at(10, 12, day=28))
        self.downloads = []
        self.real_trigger_download = g.trigger_download          # 진짜 함수(시험이 직접 불러 볼 수 있게)
        self.patch_value("trigger_download", lambda url: self.downloads.append(url))
        self.slot = next(s for s in range(1, 30) if g.editorial_lane_order(s, [])[0] != "technology")

    def patch_value(self, name, value):
        patcher = mock.patch.object(g, name, value)
        patcher.start()
        self.addCleanup(patcher.stop)

    def set_history(self, entries):
        (self.root / "history.json").write_bytes(json.dumps(entries, ensure_ascii=False, indent=2).encode("utf-8"))

    def history(self):
        path = self.root / "history.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []

    def clear_outputs(self):
        for path in (self.root / "_posts").rglob("*.md"):
            path.unlink()
        (self.root / "history.json").unlink(missing_ok=True)

    def run_generation(self, settings, items, responses, draft_flow=False, history=None, call=None):
        """responses: 후보 제목 → 모델 JSON(dict). 돌려주는 값: SimpleNamespace(value, report, out, written, prompts, image_counts, error)."""
        if history is not None:
            self.set_history(history)
        by_title = {item["title"]: json.dumps(responses[item["title"]], ensure_ascii=False) for item in items if item["title"] in responses}
        prompts, written, report, counts = [], [], {}, []

        def fake_gemini(prompt):
            prompts.append(prompt)
            key = next((title for title in by_title if title in prompt), None)
            if key is None:
                raise AssertionError("가짜 Gemini 가 모르는 후보")
            return SimpleNamespace(text=by_title[key])

        def fake_fetch(editorial_lane=None, stats=None, deadline=None, clock=None):
            if stats is not None:
                stats.setdefault("sources", []).append({"name": "x", "fetched": 4, "kept": len(items), "drops": {}})
            return list(items) if editorial_lane == "technology" else []

        real_pick, real_write = g.pick_images, g.write_text_atomic
        patches = [mock.patch.object(registry, "chance_settings", return_value=settings), mock.patch.object(g, "call_gemini_with_fallback", fake_gemini),
                   mock.patch.object(g, "fetch_news_items", fake_fetch), mock.patch.object(g, "get_client", side_effect=AssertionError("가짜 Gemini 만 쓴다")),
                   mock.patch.object(g, "pick_images", lambda queries, used, count=1, allow_pool=False: (counts.append(count), real_pick(queries, used, count, allow_pool))[1]),
                   mock.patch.object(g, "write_text_atomic", lambda path, content: (written.append((str(path), content)), real_write(path, content))[1]),
                   # 프롬프트 모양은 따로 시험한다 — 여기서는 후보 제목만 돌려 가짜 Gemini 가 고르게 한다
                   mock.patch.object(g, "build_post_prompt", lambda item, recent, category_hint="", allow_skip=False, editorial_lane=None, languages=("ko", "en"): item["title"])]
        error = None
        for patcher in patches:
            patcher.start()
        try:
            try:
                if call is not None:
                    value, out = run_captured(call)
                else:
                    value, out = run_captured(g.generate_blog_posts, slot=self.slot, allow_auto_topic=False, report=report, draft_flow=draft_flow)
            except (RuntimeError, ValueError) as exc:
                value, out, error = None, "", exc
        finally:
            for patcher in reversed(patches):
                patcher.stop()
        return SimpleNamespace(value=value, report=report, out=out, written=written, prompts=prompts, image_counts=counts, error=error)


class DefaultOffTest(GenerationBase):
    def test_the_default_run_never_calls_the_gate_and_publishes_as_before(self):
        item = candidate_item()
        with mock.patch.object(qg, "check_candidate", side_effect=AssertionError("꺼진 Gate 를 불렀다")), mock.patch.object(qg, "require_pass", side_effect=AssertionError("꺼진 Gate 를 불렀다")):
            result = self.run_generation(OFF_BOTH, [item], {item["title"]: model_json(item)})
        self.assertIsNone(result.error)
        self.assertEqual(len(result.value), 2)
        self.assertEqual(len([path for path, _ in result.written if path.endswith(".md")]), 2)
        self.assertEqual(len(self.history()), 1)
        self.assertEqual(result.image_counts, [2])
        self.assertNotIn("품질 Gate", result.out)

    def test_a_candidate_the_gate_would_hold_is_still_published_when_the_gate_is_off(self):
        item = candidate_item()
        bad_ko = h.ko_body(link=item["link"]).replace("1,250,000가구", "9,999,999가구")
        result = self.run_generation(OFF_BOTH, [item], {item["title"]: model_json(item, ko=bad_ko)})
        self.assertIsNone(result.error)
        self.assertIsNotNone(result.value)
        self.assertEqual(result.report["outcome"], "PUBLISHED")

    def test_an_unreadable_registry_stops_before_any_model_call(self):
        item = candidate_item()
        calls = []
        with mock.patch.object(registry, "chance_settings", side_effect=registry.RegistryError("읽을 수 없음")), \
                mock.patch.object(g, "call_gemini_with_fallback", lambda prompt: calls.append(prompt)), mock.patch.object(g, "fetch_news_items", lambda *a, **k: [item]):
            with self.assertRaises(registry.RegistryError):
                run_captured(g.generate_blog_posts, slot=self.slot, allow_auto_topic=False, report={})
        self.assertEqual(calls, [])

    def test_the_real_registry_is_hold_and_korean_only(self):
        """켜는 변경(T3, 패치 02·03) 뒤: 진짜 레지스트리는 Gate hold·국문 단독이다(전에는 꺼짐·두 언어). 클래스 도구(pre_flip)가 기본 경로를 켜기 전 표본으로 돌리므로 진짜 파일을 경로로 직접 읽는다."""
        self.assertEqual(registry.chance_settings(_bootstrap.ROOT / "pipeline" / "blogs.json"), HOLD_KO)


class HoldModeTest(GenerationBase):
    def test_a_clean_candidate_passes_the_gate_and_is_published(self):
        item = candidate_item()
        result = self.run_generation(HOLD_BOTH, [item], {item["title"]: model_json(item)})
        self.assertIsNone(result.error)
        self.assertEqual(result.report["outcome"], "PUBLISHED")
        self.assertEqual(result.report["rejects"], [])
        self.assertNotIn("품질 Gate", result.out)

    def test_a_held_candidate_is_dropped_and_the_next_one_is_published(self):
        bad, good = candidate_item(0), candidate_item(1)
        bad_ko = h.ko_body(link=bad["link"]).replace("1,250,000가구", "9,999,999가구")
        result = self.run_generation(HOLD_BOTH, [bad, good], {bad["title"]: model_json(bad, ko=bad_ko), good["title"]: model_json(good)})
        self.assertIsNone(result.error)
        self.assertEqual(result.report["outcome"], "PUBLISHED")
        self.assertEqual(result.report["attempts"], 2)
        self.assertEqual(len(result.report["rejects"]), 1)
        reject = result.report["rejects"][0]
        self.assertEqual(reject["kind"], "BODY")
        self.assertTrue(reject["detail"].startswith("품질 Gate 보류 [QG1-NUMBER"), reject["detail"])
        self.assertIn("본문 검증 탈락: 품질 Gate 보류 [QG1-NUMBER", result.out)
        self.assertIn("::notice::앞선 후보 1건이 탈락한 뒤 2번째 후보로 글을 만들었습니다", result.out)
        self.assertEqual(self.history()[0]["source_url"], good["link"])

    def test_when_every_candidate_is_held_nothing_is_written_and_the_run_ends_with_a_warning(self):
        items = [candidate_item(n) for n in range(3)]
        responses = {item["title"]: model_json(item, ko=h.ko_body(link=item["link"]).replace("1,250,000가구", "9,999,999가구")) for item in items}
        result = self.run_generation(HOLD_BOTH, items, responses)
        self.assertIsNone(result.error)
        self.assertIsNone(result.value)
        self.assertEqual(result.report["outcome"], "ALL_REJECTED")
        self.assertEqual(result.report["attempts"], 3)
        self.assertEqual(result.written, [])
        self.assertEqual(self.history(), [])
        self.assertEqual(len(result.prompts), 3)
        self.assertIn("::warning::후보 3건이 모두 탈락했습니다", result.out)
        self.assertEqual(result.image_counts, [])            # 탈락한 후보에는 이미지 검색도 하지 않는다
        self.assertEqual(self.downloads, [])

    def test_the_run_summary_names_the_hold_reasons(self):
        items = [candidate_item(n) for n in range(3)]
        responses = {item["title"]: model_json(item, ko=h.ko_body(link=item["link"]).replace("1,250,000가구", "9,999,999가구")) for item in items}
        result = self.run_generation(HOLD_BOTH, items, responses)
        summary = g.render_run_summary("schedule", at(10, 12, day=28), self.slot, dict(result.report, gemini_calls={"attempts": 3, "failed": 0}))
        self.assertIn("품질 Gate 보류", summary)
        self.assertEqual(sum(1 for line in summary.splitlines() if "QG1-NUMBER" in line), 4)       # 탈락 요약 한 줄 + 후보별 세 줄
        for line in summary.splitlines():
            self.assertNotIn("##[", line)

    def test_the_gate_sees_the_history_so_a_reused_source_is_held(self):
        item = candidate_item()
        result = self.run_generation(HOLD_BOTH, [item], {item["title"]: model_json(item)}, history=[{"date": "2026-10-20", "topic": "오래된 글", "source_url": item["link"] + "?utm_source=x"}])
        self.assertIsNone(result.value)
        self.assertIn("QG7-REUSE", result.out)

    def test_the_gate_is_applied_to_the_validated_post(self):
        item = candidate_item()
        seen = []
        real = qg.check_candidate

        def spy(data, source, history=(), config=None, as_of=None):
            seen.append((data, source, history, config, as_of))
            return real(data, source, history=history, config=config, as_of=as_of)

        with mock.patch.object(qg, "check_candidate", spy):
            self.run_generation(HOLD_BOTH, [item], {item["title"]: model_json(item)})
        data, source, history, config, as_of = seen[0]
        self.assertTrue(data["kr_content"].startswith("---\nlayout: post\n"))       # validate_post_data 를 거친 글(머리말이 다시 쓰인 모양)
        self.assertIn("example.invalid", data["kr_content"])                          # 자리표시 이미지가 붙은 검증용 사본이다
        # 모델이 보낸 원본 후보가 아니라 검증을 거친 사본이어야 한다(M12): 모델 응답의 대표 사진 줄(x.jpg)이 검증용 자리표시(kr.jpg)로 다시 쓰여 있다
        self.assertIn('image: "https://example.invalid/kr.jpg"', data["kr_content"])
        self.assertNotIn("example.invalid/x.jpg", data["kr_content"])
        self.assertIn('image: "https://example.invalid/en.jpg"', data["en_content"])
        raw = model_json(item)
        self.assertIn("example.invalid/x.jpg", raw["kr_content"])                      # 원본에는 x.jpg 가 있었다 — 같은 객체가 아니다
        self.assertIsNot(data, raw)
        self.assertEqual(source["link"], item["link"])
        self.assertEqual((config.languages, as_of.isoformat()), (("ko", "en"), "2026-10-28"))

    def test_a_validation_failure_comes_before_the_gate(self):
        item = candidate_item()
        thin = {**model_json(item), "kr_content": h.front("t", "ko") + "짧다 " + f"[원문]({item['link']})"}
        with mock.patch.object(qg, "check_candidate", side_effect=AssertionError("검증에 실패한 후보에 Gate 를 불렀다")):
            result = self.run_generation(HOLD_BOTH, [item], {item["title"]: thin})
        self.assertIsNone(result.value)
        self.assertIn("본문 검증 탈락", result.out)

    def test_unreadable_health_profiles_stop_before_any_model_call(self):
        item = candidate_item()
        calls = []
        with mock.patch.object(registry, "chance_settings", return_value=HOLD_BOTH), mock.patch.object(registry, "load_profile", side_effect=registry.RegistryError("프로필 없음")), \
                mock.patch.object(g, "call_gemini_with_fallback", lambda prompt: calls.append(prompt)), mock.patch.object(g, "fetch_news_items", lambda *a, **k: [item]):
            with self.assertRaises(registry.RegistryError):
                run_captured(g.generate_blog_posts, slot=self.slot, allow_auto_topic=False, report={})
        self.assertEqual(calls, [])

    def test_the_gate_config_uses_the_profiles_and_the_languages_of_the_settings(self):
        config = g.quality_gate_config(HOLD_KO)
        self.assertEqual(config.languages, ("ko",))
        self.assertEqual([p["language"] for p in config.health_profiles], ["ko", "en"])
        self.assertIsNone(g.quality_gate_config(OFF_BOTH))
        self.assertIsNone(g.quality_gate_config(OFF_KO))


class KoreanOnlyTest(GenerationBase):
    def run_ko(self, settings=OFF_KO, item=None, ko=None, draft_flow=False):
        item = item or candidate_item()
        return item, self.run_generation(settings, [item], {item["title"]: model_json(item, ko=ko, pair=False)}, draft_flow=draft_flow)

    def test_the_prompt_asks_for_korean_only_and_the_default_prompt_is_unchanged(self):
        item = candidate_item()
        ko_prompt = g.build_post_prompt(item, [], "", True, "economy", languages=("ko",))
        pair_prompt = g.build_post_prompt(item, [], "", True, "economy")
        self.assertEqual(pair_prompt, g.build_post_prompt(item, [], "", True, "economy", languages=("ko", "en")))
        for needle in ("en_content", "en_title", "en_category", "en_tags", "English Title", "English Markdown", "한국어와 영어로 각각", "각 언어에", "영어에서"):
            self.assertIn(needle, pair_prompt, needle)
            self.assertNotIn(needle, ko_prompt, needle)
        for needle in ("kr_content", "kr_title", "kr_category", "kr_tags", "image_queries", "한국어로 작성하세요", "한국어로 자연스럽게"):
            self.assertIn(needle, ko_prompt, needle)
        self.assertEqual(ko_prompt.count('"kr_content"'), 1)
        schema = "{" + ko_prompt.rsplit("{", 1)[1]
        self.assertEqual(sorted(json.loads(schema)), ["image_queries", "kr_category", "kr_content", "kr_tags", "kr_title"])
        self.assertEqual(sorted(json.loads("{" + pair_prompt.rsplit("{", 1)[1])),
                         ["en_category", "en_content", "en_tags", "en_title", "image_queries", "kr_category", "kr_content", "kr_tags", "kr_title"])

    def test_the_default_prompt_is_pinned_byte_for_byte(self):
        item = {"title": "예시 기사", "source": "Example", "link": "https://x.example/a", "published": datetime.datetime(2026, 11, 4, tzinfo=datetime.timezone.utc),
                "summary": "요약 문장입니다. " * 20, "prompt_rule": "소스 규칙 한 줄."}
        outs = [g.build_post_prompt(item, ["이전 제목 하나", "이전 제목 둘"], hint, skip, lane)
                for lane in ("economy", "technology", "daily_life") for hint in ("", "과학·환경") for skip in (False, True)]
        outs.append(g.build_post_prompt(None, [], "", False, "society"))
        outs.append(g.build_post_prompt({"title": "제목만"}, ["a"], "", True, "culture"))
        digest = hashlib.sha256("\n=====\n".join(outs).encode("utf-8")).hexdigest()
        # 이 값은 이 변경 전의 generator.py(origin/main 611b2d2)가 만든 같은 14개 프롬프트의 해시다. 프롬프트를 일부러 바꾸면 이 값도 함께 바꾼다.
        self.assertEqual(digest, "0bd4399a8e3ad4c8f4c4218f16620c3251896e942766919bb88700d8e1dd5f20")

    def test_only_the_korean_post_is_made_validated_written_and_recorded(self):
        item, result = self.run_ko()
        self.assertIsNone(result.error, result.error)
        kr_path, en_path = result.value
        self.assertIsNone(en_path)
        self.assertTrue(str(kr_path).endswith("-KR-101200.md"))
        self.assertEqual([Path(path).name for path, _ in result.written if path.endswith(".md")], ["2026-10-28-KR-101200.md"])
        entry = self.history()[0]
        self.assertNotIn("en_title", entry)
        self.assertNotIn("en_image", entry)
        self.assertEqual(entry["languages"], ["ko"])
        self.assertEqual((entry["kr_title"], entry["source_url"]), (h.KO_TITLE, item["link"]))
        self.assertEqual(list(entry)[:3], ["date", "topic", "kr_title"])
        self.assertEqual(result.report["paths"], [str(kr_path)])
        self.assertIsNone(result.report["en_title"])
        self.assertEqual(result.image_counts, [1])
        self.assertEqual(len(self.downloads), 1)
        self.assertIn("- KR: ", result.out)
        self.assertNotIn("- EN: ", result.out)
        self.assertIn(f"- 이미지: {entry['kr_image']}", result.out)

    def test_the_korean_post_is_what_the_pair_flow_would_have_written_for_the_korean_half(self):
        item = candidate_item()
        _, ko_only = self.run_ko(item=item)
        ko_text = next(content for path, content in ko_only.written if path.endswith(".md"))
        self.clear_outputs()
        both = self.run_generation(OFF_BOTH, [item], {item["title"]: model_json(item)})
        pair_ko = next(content for path, content in both.written if "-KR-" in path)
        self.assertEqual(without_images(ko_text), without_images(pair_ko))

    def test_an_english_half_in_the_model_answer_is_ignored_not_validated_and_not_written(self):
        item = candidate_item()
        answer = model_json(item, pair=True)
        answer["en_content"] = "깨진 영어"          # 한 쌍 설정이라면 본문 검증에서 탈락했을 영어
        result = self.run_generation(OFF_KO, [item], {item["title"]: answer})
        self.assertIsNone(result.error)
        self.assertIsNone(result.value[1])
        self.assertEqual(len([path for path, _ in result.written if path.endswith(".md")]), 1)
        self.assertNotIn("깨진 영어", "".join(content for _, content in result.written))

    def test_a_missing_english_half_still_rejects_the_candidate_in_pair_mode(self):
        item = candidate_item()
        result = self.run_generation(OFF_BOTH, [item], {item["title"]: model_json(item, pair=False)})
        self.assertIsNone(result.value)
        self.assertEqual(result.report["outcome"], "ALL_REJECTED")
        self.assertIn("en_category", result.out)

    def test_korean_only_with_the_gate_on_checks_only_the_korean_text(self):
        item = candidate_item()
        _, ok = self.run_ko(HOLD_KO, item)
        self.assertIsNone(ok.error)
        self.assertEqual(ok.report["outcome"], "PUBLISHED")
        self.clear_outputs()
        item2 = candidate_item(1)
        bad_ko = h.ko_body(link=item2["link"]).replace("1,250,000가구", "9,999,999가구")
        _, held = self.run_ko(HOLD_KO, item2, ko=bad_ko)
        self.assertIsNone(held.value)
        self.assertIn("QG1-NUMBER", held.out)

    def test_the_approval_flow_records_one_path_for_a_korean_only_draft(self):
        item, result = self.run_ko(draft_flow=True)
        self.assertIsNone(result.error, result.error)
        entry = self.history()[0]
        self.assertEqual(entry["flow"], "pr")
        self.assertEqual(len(entry["paths"]), 1)
        self.assertTrue(entry["paths"][0].endswith("-KR-101200.md"))
        self.assertTrue(drafts.valid_post_path(entry["paths"][0]), entry["paths"])
        self.assertEqual(result.report["outcome"], "DRAFT_CREATED")
        self.assertEqual(result.report["paths"], [str(result.value[0])])
        self.assertTrue(drafts.posts_exist(entry))

    def test_the_pair_flow_still_records_two_paths_in_korean_then_english_order(self):
        item = candidate_item()
        result = self.run_generation(OFF_BOTH, [item], {item["title"]: model_json(item)}, draft_flow=True)
        entry = self.history()[0]
        self.assertEqual([p.split("/")[-1] for p in entry["paths"]], ["2026-10-28-KR-101200.md", "2026-10-28-EN-101200.md"])
        self.assertEqual(list(entry)[:6], ["date", "topic", "kr_title", "en_title", "kr_image", "en_image"])
        self.assertEqual(result.image_counts, [2])


class ValidationFunctionsTest(unittest.TestCase):
    """validate_post_data·check_final_front_matter 의 languages 인자: 기본은 예전 그대로, ko 만이면 국문만 본다."""

    def data(self, pair=True):
        item = candidate_item()
        data = h.make_data(ko=h.ko_body(link=item["link"]), en=h.en_body(link=item["link"]))
        if not pair:
            data = {key: value for key, value in data.items() if key.startswith("kr_")}
        return item, data

    def test_the_default_still_requires_both_languages(self):
        item, data = self.data(pair=False)
        with self.assertRaises(ValueError) as caught:
            g.validate_post_data(data, "https://example.invalid/kr.jpg", "https://example.invalid/en.jpg", verified_source_url=item["link"])
        self.assertIn("en_category", str(caught.exception))

    def test_korean_only_validates_the_korean_half_and_leaves_the_rest_alone(self):
        item, data = self.data(pair=False)
        out = g.validate_post_data(data, "https://example.invalid/kr.jpg", None, verified_source_url=item["link"], languages=("ko",))
        self.assertNotIn("en_content", out)
        self.assertIn("![Thumbnail](https://example.invalid/kr.jpg)", out["kr_content"])
        g.check_final_front_matter(out, item, languages=("ko",))

    def test_korean_only_still_rejects_a_thin_or_unlinked_korean_post(self):
        item, data = self.data(pair=False)
        data["kr_content"] = h.front("t", "ko") + "짧다 " + f"[원문]({item['link']})"
        with self.assertRaises(ValueError):
            g.validate_post_data(data, "https://example.invalid/kr.jpg", None, verified_source_url=item["link"], languages=("ko",))

    def test_prefixes(self):
        self.assertEqual(g._prefixes(("ko", "en")), ("kr", "en"))
        self.assertEqual(g._prefixes(("ko",)), ("kr",))
        self.assertEqual(g._prefixes(["ko", "en"]), ("kr", "en"))


class ConnectionIsolationTest(unittest.TestCase):
    """Gate 연결이 다른 코드(Blogger·이슈 수정·승인 흐름·알림)에 닿지 않는다."""

    def test_only_the_generator_and_the_registry_text_mention_the_gate(self):
        users = set()
        for folder in (ROOT, ROOT / "pipeline", ROOT / "scripts", ROOT / "pipeline" / "publishers", ROOT / "pipeline" / "edits"):
            for path in folder.glob("*.py"):
                if "quality_gate" in path.read_text(encoding="utf-8"):
                    users.add(path.name)
        self.assertLessEqual(users, {"generator.py", "registry.py", "quality_gate.py", "shadow_run.py"})
        for name in ("pipeline/run.py", "blogger_generator.py", "pipeline/drafts.py", "pipeline/draft_flow.py", "pipeline/notify.py", "pipeline/operator_loop.py",
                     "pipeline/health.py", "pipeline/inbox.py", "pipeline/main_image.py"):
            self.assertNotIn("quality_gate", (ROOT / name).read_text(encoding="utf-8"), name)

    def test_generator_calls_the_gate_in_exactly_two_places_the_feed_candidate_validation_and_the_fact_check(self):
        """S2b(D-234): 개정 전에는 '정확히 한 곳(피드 후보 검증)'이었다. 구조화 Fact 분기가 두 번째 한 곳(`fact_check_post` — 후보 글 한 편의 검사)에서 같은 Gate 를 부른다 — 두 곳 모두 정확히 한 줄이고 그 밖에는 없으며,
        피드 쪽은 이전과 같은 모양(머리말 최종 검사 바로 뒤 같은 try 안, 보류는 ValueError 로 후보 탈락)이다. `require_pass` 는 피드 쪽 한 곳뿐이다(Fact 쪽은 보류 코드를 글감 건너뜀 사유로 쓴다)."""
        text = (ROOT / "generator.py").read_text(encoding="utf-8")
        self.assertEqual(text.count("quality_gate.check_candidate("), 2)
        self.assertEqual(text.count("quality_gate.require_pass("), 1)
        before, _, after = text.partition("quality_gate.check_candidate(")
        self.assertIn("check_final_front_matter(checked, item", before.rsplit("def ", 1)[1])        # 같은 함수·같은 try 안, 머리말 최종 검사 바로 뒤
        self.assertIn("except ValueError as exc:", "\n".join(after.splitlines()[:3]))
        owners = []
        for function in [node for node in ast.walk(ast.parse(text)) if isinstance(node, ast.FunctionDef)]:
            for node in ast.walk(function):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "check_candidate":
                    owners.append(function.name)
        self.assertEqual(sorted(owners), ["fact_check_post", "generate_blog_posts"])

    def test_generator_never_imports_the_shadow_measuring_tool(self):
        for name in ("generator.py", "pipeline/quality_gate.py"):
            self.assertNotIn("quality_shadow", (ROOT / name).read_text(encoding="utf-8"), name)


if __name__ == "__main__":
    unittest.main()
