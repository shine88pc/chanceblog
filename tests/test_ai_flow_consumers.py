"""표식 소비자 시험 — AI 입력을 만드는 읽기가 표식 글을 빼는지, 그리고 감사가 재현한 네 연결(a 새 글 · b 이미지 교체 · c Blogger 재작성 · d 이슈 수정)과 그림자 실행에서
'AI 입력에 표식 글의 제목·값이 들어가지 않는다'를 **실제 함수 실행**으로 못박는다. 네트워크 없이 돈다(가짜 Gemini·가짜 피드·임시 저장소).

각 연결마다 같은 장면을 두 번 만든다: ① 표식 글(제목에 값이 들어 있다)과 대조군(표식만 없는 같은 모양의 글)을 `_posts`·`history.json` 에 둔다 ② AI 로 가려는 프롬프트를 붙잡아
표식 글의 제목·설명·태그·분류·값이 **없고**, 대조군은 **그대로 있음**을 본다. 대조군이 그대로 있다는 확인이 이 시험이 아무것도 안 하는 시험이 아님을 보인다(전: 들어감 → 후: 안 들어감은
옛 코드와 새 코드를 같은 장면에 돌린 저장소 밖 비교 도구가 따로 보인다 — 작업 보고서 4절).
"""
import json
import os
import random
import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import _bootstrap
import generator as g
from ai_flow_helpers import FACT_POSTS, NORMAL_POSTS, RepoCase, fact_text, history_entry, normal_text, post_text, write
from edits_helpers import image_body, issue, make_edit_root
from pipeline import ai_guard, gates, main_image, provenance, registry, state, topics
from pipeline import run as run_mod
from pipeline.edits import ops, pages, runner, spec as spec_mod
from pipeline.llm import make_gemini_llm
from test_generator_quality_gate import OFF_BOTH, GenerationBase, candidate_item, model_json
from test_run import RunBase
from test_shadow_run import ShadowRunBase

ROOT = _bootstrap.ROOT
ENV = {"GEMINI_API_KEY": "k"}
REAL_ENTRANCE = g.call_gemini_with_fallback      # 진짜 입구(방벽 포함) — 장면이 g 의 이름을 바꿔치기해도 이 함수를 쓴다
MARKED_TITLE = FACT_POSTS[0]["title"]


class SdkCounter:
    """SDK 계층의 가짜 클라이언트 — 방벽을 지나 모델 호출까지 간 프롬프트만 센다. 진짜 입구와 진짜 호출 객체가 돌고 방벽이 실제로 불린다('모델을 한 번도 부르지 않았다' 의 증거)."""

    def __init__(self, reply=lambda prompt: "{}"):
        self.prompts = []
        counter = self

        class Models:
            def generate_content(inner, model, contents, **kwargs):
                counter.prompts.append(contents)
                return SimpleNamespace(text=reply(contents), usage_metadata=None, model_version=model)

        self.client = SimpleNamespace(models=Models())

    def call_object(self):
        return make_gemini_llm("테스트 키 값", ["모델 하나"], max_retries=0, sleep=lambda seconds: None, client_factory=lambda: self.client)


def enter_repo(case, root):
    """작업 폴더와 방벽의 CODE_ROOT 를 임시 저장소로 둔다(끝나면 되돌린다) — 방벽이 진짜 저장소가 아니라 이 장면의 표식 글을 훑는다."""
    previous = os.getcwd()
    os.chdir(root)
    case.addCleanup(os.chdir, previous)
    patcher = mock.patch.object(ai_guard, "CODE_ROOT", Path(root).resolve())
    patcher.start()
    case.addCleanup(patcher.stop)
    case.addCleanup(ai_guard.reset_cache)
    ai_guard.reset_cache()


def leaked(text, post):
    """프롬프트에 표식 글의 제목·설명 앞부분·태그·분류가 하나라도 들어 있는가(들어 있는 것의 이름 목록)."""
    found = []
    if post["title"] in text:
        found.append("제목")
    if post["description"][:30] in text:
        found.append("설명")
    if any(tag in text for tag in post["tags"][:2]):
        found.append("태그")
    if post["category"] in text:
        found.append("분류")
    if "3.5%" in text or "103.4" in text:
        found.append("값")
    return found


class ReadersTest(RepoCase):
    """AI 입력이 될 수 있는 읽기(generator.load_posts·existing_titles, state.entry_titles·other_blog_titles)의 기본 동작."""

    def setUp(self):
        super().setUp()
        self.add_normal_posts()
        self.add_fact_posts()
        write(self.root, "_posts/깨짐/2026-11-23-KR-100000.md", fact_text(0, marker=False).replace("\n---\n\n", "\n\n"))      # 머리말이 닫히지 않은 글 — 표식 여부를 알 수 없다
        (self.root / "_posts" / "깨짐" / "2026-11-24-KR-bad.md").write_bytes(b"---\ntitle: \xff\xfe\n---\n")             # UTF-8 이 아닌 파일 — 읽지 못한다
        self.patch = mock.patch.object(g, "POSTS_DIR", Path("_posts"))
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def load(self, **kwargs):
        from io import StringIO
        from contextlib import redirect_stdout
        buffer = StringIO()
        with redirect_stdout(buffer):
            posts = g.load_posts(**kwargs)
        return posts, buffer.getvalue()

    def test_for_ai_skips_marked_and_unknown_posts_and_says_how_many(self):
        posts, out = self.load()
        self.assertEqual(sorted(p["title"] for p in posts), sorted(post["title"] for post in NORMAL_POSTS))
        self.assertEqual({p["provenance"] for p in posts}, {provenance.MARK_NONE})
        self.assertIn("3편", out)        # 표식 글 둘 + 닫히지 않은 머리말 하나
        self.assertIn("읽기 실패", out)   # UTF-8 이 아닌 파일은 어느 쪽이든 건너뛴다(충돌 없이)

    def test_not_for_ai_returns_everything_readable_with_the_mark_of_each(self):
        posts, out = self.load(for_ai=False)
        marks = {p["path"].name: p["provenance"] for p in posts}
        self.assertEqual(len(posts), 5)
        self.assertEqual(sum(1 for mark in marks.values() if mark == provenance.MARK_FACTS), 2)
        self.assertEqual(sum(1 for mark in marks.values() if mark == provenance.MARK_UNKNOWN), 1)
        self.assertNotIn("편은 AI 입력이", out)

    def test_nothing_is_said_when_nothing_is_withheld(self):
        for post in FACT_POSTS:
            (self.root / post["rel"]).unlink()
        (self.root / "_posts" / "깨짐" / "2026-11-23-KR-100000.md").unlink()
        posts, out = self.load()
        self.assertEqual(len(posts), 2)
        self.assertNotIn("AI 입력", out)

    def test_existing_titles_drop_marked_history_entries_and_marked_posts(self):
        history = [history_entry(FACT_POSTS[0]["title"], marker=True), history_entry(NORMAL_POSTS[1]["title"]), "문자열 항목 제목", {"provenance": "human", "kr_title": "모르는 값 항목"}]
        posts, _ = self.load(for_ai=False)
        for_ai = g.existing_titles(history, posts)
        self.assertNotIn(FACT_POSTS[0]["title"], for_ai)
        self.assertNotIn(FACT_POSTS[1]["title"], for_ai)
        self.assertNotIn("모르는 값 항목", for_ai)
        self.assertIn(NORMAL_POSTS[1]["title"], for_ai)
        self.assertIn("문자열 항목 제목", for_ai)
        everything = g.existing_titles(history, posts, for_ai=False)
        self.assertIn(FACT_POSTS[0]["title"], everything)
        self.assertIn(FACT_POSTS[1]["title"], everything)

    def test_entry_titles_and_other_blog_titles_skip_marked_entries(self):
        entries = [history_entry(FACT_POSTS[0]["title"], marker=True), history_entry(NORMAL_POSTS[0]["title"]), "문자열 항목", {"provenance": "x", "title": "모르는 값"}]
        self.assertEqual(state.entry_titles(entries).count(FACT_POSTS[0]["title"]), 0)
        self.assertIn(NORMAL_POSTS[0]["title"], state.entry_titles(entries))
        self.assertIn("문자열 항목", state.entry_titles(entries))
        self.assertNotIn("모르는 값", state.entry_titles(entries))
        self.assertIn(FACT_POSTS[0]["title"], state.entry_titles(entries, for_ai=False))
        self.set_history(entries)
        blogs = [{"key": "chance", "state": {"history": "history.json"}}, {"key": "blogger_macat", "state": {"history": "blogger_history.json"}}]
        others = state.other_blog_titles(self.root, blogs, "blogger_macat")
        self.assertNotIn(FACT_POSTS[0]["title"], others)
        self.assertIn(NORMAL_POSTS[0]["title"], others)
        self.assertIn(FACT_POSTS[0]["title"], state.other_blog_titles(self.root, blogs, "blogger_macat", for_ai=False))
        self.assertEqual(state.other_blog_titles(self.root, blogs, "chance"), [])       # 자기 블로그는 제외

    def test_diagnose_and_repair_ignore_marked_posts(self):
        posts, _ = self.load(for_ai=False)
        marked = next(p for p in posts if p["provenance"] == provenance.MARK_FACTS)
        with mock.patch.object(g, "make_image_queries", side_effect=AssertionError("표식 글로 AI 검색어를 만들었다")), \
                mock.patch.object(g, "url_ok", side_effect=AssertionError("표식 글의 이미지를 확인했다")):
            self.assertIsNone(g.diagnose(marked, set()))
            self.assertIsNone(g.diagnose(dict(marked, image=""), {g.image_key(marked["image"])}))      # 이미지가 없거나 겹쳐도 대상이 아니다
            self.assertIsNone(g.repair(marked, set()))
        plain = next(p for p in posts if p["provenance"] == provenance.MARK_NONE)
        self.assertEqual(g.diagnose(dict(plain, image=""), set()), "missing")       # 대조군: 표식 없는 글은 그대로 점검한다


class NewPostPromptTest(GenerationBase):
    """연결 a — 새 글 쓰기: 프롬프트의 '최근 다룬 주제/제목'(existing_titles(...)[-30:])."""

    def setUp(self):
        super().setUp()
        enter_repo(self, self.root)          # 방벽이 진짜 저장소의 표식 글이 아니라 이 임시 저장소만 훑는다(D-194)
        for index, post in enumerate(NORMAL_POSTS):
            write(self.root, post["rel"], normal_text(index))
        for index, post in enumerate(FACT_POSTS):
            write(self.root, post["rel"], fact_text(index))
        self.set_history([history_entry(NORMAL_POSTS[0]["title"]), history_entry(FACT_POSTS[0]["title"], marker=True), history_entry(FACT_POSTS[1]["title"], marker=True)])

    def run_real_prompt(self, use_real_gemini_entrance=False):
        item = candidate_item(0)
        prompts, response = [], json.dumps(model_json(item), ensure_ascii=False)
        self.sdk_prompts = prompts      # 방벽을 지나 모델까지 간 프롬프트(예외로 끝나도 시험이 볼 수 있게)

        def fake_gemini(prompt):
            prompts.append(prompt)
            return SimpleNamespace(text=response)

        class Models:
            def generate_content(inner, model, contents, **kwargs):
                prompts.append(contents)
                return SimpleNamespace(text=response, usage_metadata=None, model_version=model)

        def fake_fetch(editorial_lane=None, stats=None, deadline=None, clock=None):
            if stats is not None:
                stats.setdefault("sources", []).append({"name": "x", "fetched": 1, "kept": 1, "drops": {}})
            return [item] if editorial_lane == "technology" else []

        patches = [mock.patch.object(registry, "chance_settings", return_value=OFF_BOTH), mock.patch.object(g, "fetch_news_items", fake_fetch),
                   mock.patch.object(g, "STUB_GEMINI", False)]
        if use_real_gemini_entrance:        # 진짜 입구(call_gemini_with_fallback — 방벽 포함)와 가짜 클라이언트
            patches.append(mock.patch.object(g, "get_client", return_value=SimpleNamespace(models=Models())))
        else:
            patches += [mock.patch.object(g, "call_gemini_with_fallback", fake_gemini), mock.patch.object(g, "get_client", side_effect=AssertionError("가짜 Gemini 만 쓴다"))]
        for patcher in patches:
            patcher.start()
        try:
            from test_generator_slots import run_captured
            value, out = run_captured(g.generate_blog_posts, slot=self.slot, allow_auto_topic=False, report={})
        finally:
            for patcher in reversed(patches):
                patcher.stop()
        return SimpleNamespace(value=value, out=out, prompts=prompts)

    def test_the_prompt_has_no_marked_title_and_keeps_the_unmarked_ones(self):
        result = self.run_real_prompt()
        self.assertIsNotNone(result.value, result.out)
        self.assertEqual(len(result.prompts), 1)
        prompt = result.prompts[0]
        for post in FACT_POSTS:
            self.assertEqual(leaked(prompt, post), [])
        self.assertIn(NORMAL_POSTS[0]["title"], prompt)           # 대조군: 표식 없는 글·이력 제목은 그대로 최근 제목에 들어간다
        self.assertIn(NORMAL_POSTS[1]["title"], prompt)

    def test_the_same_scene_without_the_filter_does_leak(self):
        """대조: 읽기를 for_ai=False 로 하면 같은 장면에서 제목이 프롬프트에 들어간다 — 위 시험이 '아무것도 안 하는 시험'이 아님을 보인다."""
        posts = g.load_posts(for_ai=False)
        titles = g.existing_titles(g.read_history(), posts, for_ai=False)
        prompt = g.build_post_prompt(candidate_item(0), titles[-30:], "", allow_skip=True, editorial_lane="technology")
        found = leaked(prompt, FACT_POSTS[0])
        self.assertIn("제목", found)        # 전: 표식을 읽지 않으면 최근 제목에 값이 든 제목이 그대로 실린다
        self.assertIn("값", found)

    def test_the_real_entrance_with_the_barrier_runs_clean_when_the_structure_is_right(self):
        result = self.run_real_prompt(use_real_gemini_entrance=True)
        self.assertIsNotNone(result.value, result.out)
        self.assertEqual(len(result.prompts), 1)
        for post in FACT_POSTS:
            self.assertEqual(leaked(result.prompts[0], post), [])

    def test_if_the_filter_were_bypassed_the_barrier_refuses_the_same_run(self):
        """두 번째 방어선: 누가 읽기를 필터 없이 바꿔도(여기서는 existing_titles 를 for_ai=False 로 바꿔치기) 진짜 입구가 모델을 부르지 않고 AiInputForbidden 을 올린다."""
        real = g.existing_titles
        with mock.patch.object(g, "existing_titles", lambda history, posts, for_ai=True: real(history, g.load_posts(for_ai=False), for_ai=False)):
            with self.assertRaises(ai_guard.AiInputForbidden):
                self.run_real_prompt(use_real_gemini_entrance=True)

    def test_scene_1_the_refusal_comes_out_of_generate_blog_posts_and_no_model_call_was_made(self):
        """장면 1(예외 사슬 일곱 곳 중 새 글 쓰기, D-195): 구조 필터가 어쩌다 꺼져도 방벽 예외는 삼켜지지 않고 generate_blog_posts 밖으로 나온다 — 모델은 한 번도 불리지 않았다(docs/AI_FLOW.md 10절)."""
        real = g.existing_titles
        with mock.patch.object(g, "existing_titles", lambda history, posts, for_ai=True: real(history, g.load_posts(for_ai=False), for_ai=False)):
            with self.assertRaises(ai_guard.AiInputForbidden):
                self.run_real_prompt(use_real_gemini_entrance=True)
        self.assertEqual(self.sdk_prompts, [])
        self.run_real_prompt(use_real_gemini_entrance=True)          # 대조군: 필터가 켜져 있으면 모델을 한 번 부르고 글이 나온다
        self.assertEqual(len(self.sdk_prompts), 1)

    def test_a_run_without_marked_posts_is_unchanged_in_the_prompt(self):
        for post in FACT_POSTS:
            (self.root / post["rel"]).unlink()
        self.set_history([history_entry(NORMAL_POSTS[0]["title"])])
        first = self.run_real_prompt().prompts[0]
        posts = g.load_posts(for_ai=False)
        titles = g.existing_titles(g.read_history(), posts, for_ai=False)
        self.assertEqual(titles, g.existing_titles(g.read_history(), posts))
        self.assertIn(NORMAL_POSTS[0]["title"], first)


class ShadowPromptTest(ShadowRunBase):
    """그림자 실행(gate 가지) — _evaluate 가 만드는 프롬프트의 최근 제목도 같은 읽기에서 나온다(감사 F6)."""

    def setUp(self):
        super().setUp()
        enter_repo(self, self.root)          # 방벽이 진짜 저장소의 표식 글이 아니라 이 임시 저장소만 훑는다(D-194)
        for index, post in enumerate(NORMAL_POSTS):
            write(self.root, post["rel"], normal_text(index))
        for index, post in enumerate(FACT_POSTS):
            write(self.root, post["rel"], fact_text(index))
        self.set_history([history_entry(NORMAL_POSTS[0]["title"]), history_entry(FACT_POSTS[1]["title"], marker=True)])

    def test_the_shadow_prompt_has_no_marked_title_and_keeps_the_unmarked_ones(self):
        result = self.run_shadow()
        self.assertTrue(result.prompts, result.out)
        for prompt in result.prompts:
            for post in FACT_POSTS:
                self.assertEqual(leaked(prompt, post), [])
        self.assertTrue(all(NORMAL_POSTS[0]["title"] in prompt for prompt in result.prompts))

    def run_with_the_real_entrance(self, sdk, filter_off):
        """그림자 실행을 진짜 입구(방벽 포함)와 SDK 계층의 가짜 클라이언트로 돌린다. filter_off 면 구조 필터(existing_titles 의 for_ai)가 꺼진 상태를 흉내 낸다."""
        items_by_lane = self.lane_items()
        real_titles = g.existing_titles
        environment = {"SHADOW_RUN": "1", "SHADOW_OUT": str(self.out_root.with_name("shadow-out-filter-off" if filter_off else "shadow-out-filter-on"))}       # 두 번 도는 장면이 서로의 결과 폴더를 쓰지 않게 따로 둔다

        def fake_fetch(editorial_lane=None, stats=None, deadline=None, clock=None):
            found = list(items_by_lane.get(editorial_lane, []))
            if stats is not None:
                stats.setdefault("sources", []).append({"name": "x", "fetched": len(found), "kept": len(found), "drops": {}})
            return found

        patches = [mock.patch.dict(os.environ, environment), mock.patch.object(registry, "chance_settings", return_value=OFF_BOTH), mock.patch.object(g, "fetch_news_items", fake_fetch),
                   mock.patch.object(g, "get_client", return_value=sdk.client), mock.patch.object(g.CALL_LOG, "records", [])]
        if filter_off:
            patches.append(mock.patch.object(g, "existing_titles", lambda history, posts, for_ai=True: real_titles(history, g.load_posts(for_ai=False), for_ai=False)))
        for patcher in patches:
            patcher.start()
        try:
            from test_generator_slots import run_captured
            return run_captured(g.main)
        finally:
            for patcher in reversed(patches):
                patcher.stop()

    def test_scene_3_the_refusal_comes_out_of_the_shadow_run_and_no_model_call_was_made(self):
        """장면 3(예외 사슬 일곱 곳 중 그림자 실행, D-195): 구조 필터가 꺼져도 방벽 예외는 그림자 실행 밖으로 나온다(_evaluate 에는 try 가 없다) — 모델은 한 번도 불리지 않았다."""
        table = {item["title"]: json.dumps(model_json(item, pair=True), ensure_ascii=False) for item in self.every(self.lane_items())}

        def reply(prompt):
            return table[next(title for title in table if title in prompt)]

        sdk = SdkCounter(reply)
        with self.assertRaises(ai_guard.AiInputForbidden):
            self.run_with_the_real_entrance(sdk, filter_off=True)
        self.assertEqual(sdk.prompts, [])
        sdk = SdkCounter(reply)
        self.run_with_the_real_entrance(sdk, filter_off=False)          # 대조군: 필터가 켜져 있으면 후보마다 모델을 부르고 표식 글의 글자는 프롬프트에 없다
        self.assertTrue(sdk.prompts)
        for prompt in sdk.prompts:
            for post in FACT_POSTS:
                self.assertEqual(leaked(prompt, post), [])


class FixImagesTest(RepoCase):
    """연결 b — 기존 글 이미지 교체(chance-fix-images): 글 제목·태그·분류가 영어 검색어 프롬프트가 된다. 공용 자체 이미지 한 장을 두 Fact 글이 쓰면 둘째 글이 duplicate 로 판정됐다(감사 5-3)."""

    def setUp(self):
        super().setUp()
        shared = "https://images.unsplash.com/photo-1000000000099?auto=format&fit=crop&w=1000&q=80"
        write(self.root, "_posts/기술·미래/2026-11-02-KR-090000.md", post_text("공유 사진을 쓰는 첫째 보통 글입니다", "기술·미래", ["a"], "첫째 설명 문장입니다 아주 길게 이어 씁니다 시험용", shared))
        write(self.root, "_posts/기술·미래/2026-11-03-KR-090000.md", post_text("공유 사진을 쓰는 둘째 보통 글입니다", "기술·미래", ["b"], "둘째 설명 문장입니다 아주 길게 이어 씁니다 시험용", shared))
        for index, post in enumerate(FACT_POSTS):
            write(self.root, post["rel"], fact_text(index))            # 두 글이 같은 자체 이미지를 쓴다
        self.prompts = []

        class Response:
            text = json.dumps({"image_queries": ["gray city", "office desk"]})

        def fake_gemini(prompt):
            self.prompts.append(prompt)
            return Response()
        patches = [mock.patch.object(g, "POSTS_DIR", Path("_posts")), mock.patch.object(g, "call_gemini_with_fallback", fake_gemini), mock.patch.object(g, "STUB_GEMINI", False),
                   mock.patch.object(g, "DRY_RUN", True), mock.patch.object(g, "url_ok", lambda url, timeout=10: True), mock.patch.object(g, "search_unsplash", lambda query, per_page=15: []),
                   mock.patch.object(g, "get_client", side_effect=AssertionError("가짜 Gemini 만 쓴다"))]
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)

    def run_fix(self):
        from test_generator_slots import run_captured
        summary, out = run_captured(g.fix_images)
        return summary, out

    def test_marked_posts_are_neither_targets_nor_ai_inputs(self):
        _summary, out = self.run_fix()
        self.assertIn("검사 대상 글: 2개", out)
        self.assertEqual(len(self.prompts), 1, out)          # 대조군: 겹친 보통 글 하나는 그대로 AI 검색어 프롬프트를 만든다
        self.assertIn("공유 사진을 쓰는 둘째 보통 글입니다", self.prompts[0])
        for post in FACT_POSTS:
            self.assertEqual(leaked(self.prompts[0], post), [])
            self.assertNotIn(post["rel"].split("/")[-1], out)
        self.assertIn("표식 글", out)

    def test_without_the_marker_the_same_posts_would_be_duplicates_and_leak(self):
        for index, post in enumerate(FACT_POSTS):
            write(self.root, post["rel"], fact_text(index, marker=False))
        _summary, out = self.run_fix()
        joined = "\n".join(self.prompts)
        self.assertEqual(leaked(joined, FACT_POSTS[1]), ["제목", "태그", "분류", "값"])       # 전: 표식이 없으면 둘째 글의 제목·태그·분류가 AI 입력이 된다

    def run_fix_with_the_real_entrance(self, sdk, title_of_the_second_post):
        """진짜 입구(방벽 포함)와 SDK 계층의 가짜 클라이언트로 이미지 교체를 돈다. 둘째 보통 글(공유 사진 때문에 duplicate 가 되는 글)의 제목을 바꿔 쓸 수 있다."""
        shared = "https://images.unsplash.com/photo-1000000000099?auto=format&fit=crop&w=1000&q=80"
        write(self.root, "_posts/기술·미래/2026-11-03-KR-090000.md", post_text(title_of_the_second_post, "기술·미래", ["b"], "둘째 설명 문장입니다 아주 길게 이어 씁니다 시험용", shared))
        with mock.patch.object(g, "call_gemini_with_fallback", REAL_ENTRANCE), mock.patch.object(g, "get_client", return_value=sdk.client):
            return self.run_fix()

    def test_scene_2_the_refusal_comes_out_of_fix_images_and_no_model_call_was_made(self):
        """장면 2(예외 사슬 일곱 곳 중 기존 글 이미지 교체, D-195): 표식 없는 보통 글이 표식 글과 같은 제목을 가졌다(구조 필터가 거를 수 없는 모양). 방벽 예외는 make_image_queries·repair·fix_images 어디서도
        삼켜지지 않고 올라오며 모델은 한 번도 불리지 않았다."""
        sdk = SdkCounter(lambda prompt: json.dumps({"image_queries": ["gray city", "office desk"]}))
        with self.assertRaises(ai_guard.AiInputForbidden):
            self.run_fix_with_the_real_entrance(sdk, MARKED_TITLE)
        self.assertEqual(sdk.prompts, [])
        sdk = SdkCounter(lambda prompt: json.dumps({"image_queries": ["gray city", "office desk"]}))
        self.run_fix_with_the_real_entrance(sdk, "공유 사진을 쓰는 둘째 보통 글입니다")          # 대조군: 제목이 다르면 같은 장면에서 모델을 한 번 부른다
        self.assertEqual(len(sdk.prompts), 1)


class BloggerRewriteTest(RunBase):
    """연결 c — Blogger·Naver 재작성: 다른 블로그 이력의 제목이 `[DUP_OTHER]` 사유(최대 100자)로 재작성 프롬프트에 실린다(감사 F3)."""

    PROFILE = "blogger_ai_tools_ko"

    def reasons_for(self, title, other_titles):
        profile = registry.load_profile(self.PROFILE)
        post = {"title": title, "labels": ["테스트"], "content": "<p>예시 문단입니다.</p>"}
        return profile, gates.check_post(post, profile, recent_titles=[], other_titles=other_titles, sanitize_stats={}).reasons

    def other_titles(self, entries):
        write(self.root, "history.json", json.dumps(entries, ensure_ascii=False))
        reg = registry.load_registry(self.root / "pipeline" / "blogs.json")
        return state.other_blog_titles(self.root, [registry.merged_blog(reg, b) for b in reg["blogs"]], "blogger_macat")

    def test_a_marked_entry_never_becomes_a_dup_other_reason_but_an_unmarked_one_still_does(self):
        entries = [history_entry(FACT_POSTS[0]["title"], marker=True), history_entry(NORMAL_POSTS[0]["title"])]
        others = self.other_titles(entries)
        profile, reasons = self.reasons_for(FACT_POSTS[0]["title"] + " 알아보기", others)
        self.assertFalse([r for r in reasons if r.startswith("[DUP_OTHER]")], reasons)
        prompt = run_mod.build_prompt("주제: {topic}", "예시 주제", profile, feedback=reasons, today=None)
        self.assertEqual(leaked(prompt, FACT_POSTS[0]), [])
        _profile, control = self.reasons_for(NORMAL_POSTS[0]["title"] + " 알아보기", others)
        dup = [r for r in control if r.startswith("[DUP_OTHER]")]
        self.assertTrue(dup, control)                       # 대조군: 표식 없는 다른 블로그 제목은 지금처럼 사유에 들어간다
        self.assertIn(NORMAL_POSTS[0]["title"], run_mod.build_prompt("주제: {topic}", "예시 주제", profile, feedback=control, today=None))

    def test_the_old_behavior_without_the_filter_does_put_the_title_in_the_rewrite_prompt(self):
        reg = registry.load_registry(self.root / "pipeline" / "blogs.json")
        write(self.root, "history.json", json.dumps([history_entry(FACT_POSTS[0]["title"], marker=True)], ensure_ascii=False))
        everything = state.other_blog_titles(self.root, [registry.merged_blog(reg, b) for b in reg["blogs"]], "blogger_macat", for_ai=False)
        profile, reasons = self.reasons_for(FACT_POSTS[0]["title"] + " 알아보기", everything)
        prompt = run_mod.build_prompt("주제: {topic}", "예시 주제", profile, feedback=reasons, today=None)
        found = leaked(prompt, FACT_POSTS[0])
        self.assertIn("제목", found)        # 전: 필터 없이 읽으면 `[DUP_OTHER]` 사유에 값이 든 제목이 그대로 실려 재작성 프롬프트로 간다
        self.assertIn("값", found)

    def run_scene(self, unfiltered=False):
        """러너를 끝까지 돌린다: Chance 이력에 표식 항목이 있고, 모델이 그 제목과 같은 제목의 글을 쓴다. 필터가 없으면 `[DUP_OTHER]` 로 탈락해 사유가 다음 프롬프트에 실린다."""
        write(self.root, "history.json", json.dumps([history_entry(FACT_POSTS[0]["title"], marker=True)], ensure_ascii=False))
        prompts = []
        from pipeline.stubs import stub_post

        def fake_llm(prompt):
            prompts.append(prompt)
            if "JSON 문자열 배열" in prompt:
                return json.dumps(["출근 전 10분 가볍게 몸 깨우는 아침 루틴"], ensure_ascii=False), "fake"
            return stub_post("작은 습관").replace("제목: 작은 습관, 오늘 바로 해볼 4가지", f"제목: {FACT_POSTS[0]['title']}"), "fake"
        real = state.other_blog_titles
        patch = mock.patch.object(run_mod, "other_blog_titles", lambda root, blogs, key: real(root, blogs, key, for_ai=False)) if unfiltered else mock.patch.object(run_mod, "other_blog_titles", real)
        with patch:
            code, out = self.go(env={"GEMINI_API_KEY": "k", "BLOGGER_PUBLISH": "0"}, llm=fake_llm, extra=["--topic", "작은 습관으로 하루 시작하기"])
        return code, out, prompts

    def test_the_runner_run_with_a_marked_chance_entry_accepts_a_similar_post_and_sends_no_marked_title(self):
        code, out, prompts = self.run_scene()
        for prompt in prompts:
            self.assertEqual(leaked(prompt, FACT_POSTS[0]), [])
        self.assertNotIn("DUP_OTHER", out)
        self.assertEqual(len(prompts), 1, out)

    def test_the_same_run_without_the_filter_is_rejected_with_dup_other_and_the_title_reaches_the_next_prompt(self):
        """대조(전): 필터를 끄면 같은 장면에서 `[DUP_OTHER]` 탈락 → 재작성 프롬프트에 값이 든 제목이 실린다. 위 시험이 이 차이를 만드는 것이 필터임을 보인다."""
        code, out, prompts = self.run_scene(unfiltered=True)
        self.assertGreaterEqual(len(prompts), 2, out)
        self.assertIn("제목", leaked(prompts[1], FACT_POSTS[0]))
        self.assertIn("DUP_OTHER", prompts[1])

    def run_scene_with_the_real_call_object(self, sdk, unfiltered):
        """run_scene 과 같은 장면을 진짜 호출 객체(방벽 포함)와 SDK 계층의 가짜 클라이언트로 돈다."""
        write(self.root, "history.json", json.dumps([history_entry(FACT_POSTS[0]["title"], marker=True)], ensure_ascii=False))
        enter_repo(self, self.root)
        real = state.other_blog_titles
        patch = mock.patch.object(run_mod, "other_blog_titles", lambda root, blogs, key: real(root, blogs, key, for_ai=False)) if unfiltered else mock.patch.object(run_mod, "other_blog_titles", real)
        with patch:
            return self.go(env={"GEMINI_API_KEY": "k", "BLOGGER_PUBLISH": "0"}, llm=sdk.call_object(), extra=["--topic", "작은 습관으로 하루 시작하기"])

    def test_scene_4_the_refusal_comes_out_of_the_blogger_runner_and_no_second_model_call_was_made(self):
        """장면 4(예외 사슬 일곱 곳 중 Blogger 생성 루프, D-195): 모델이 표식 글과 같은 제목의 글을 쓰고 필터가 꺼져 있으면 `[DUP_OTHER]` 사유가 다음 프롬프트에 표식 글 제목을 싣는다 — 그 둘째 호출을 방벽이 막고
        예외는 run.run 밖으로 나온다(run.run 은 LLMError 만 잡는다). 모델은 첫 호출 한 번뿐이다."""
        from pipeline.stubs import stub_post
        bad_post = stub_post("작은 습관").replace("제목: 작은 습관, 오늘 바로 해볼 4가지", f"제목: {FACT_POSTS[0]['title']}")
        sdk = SdkCounter(lambda prompt: bad_post)
        with self.assertRaises(ai_guard.AiInputForbidden):
            self.run_scene_with_the_real_call_object(sdk, unfiltered=True)
        self.assertEqual(len(sdk.prompts), 1)
        self.assertEqual(leaked(sdk.prompts[0], FACT_POSTS[0]), [])          # 모델에 간 것은 표식 글의 글자가 없는 첫 프롬프트뿐이다
        control = SdkCounter(lambda prompt: bad_post)
        code, out = self.run_scene_with_the_real_call_object(control, unfiltered=False)          # 대조군: 필터가 켜져 있으면 첫 글이 그대로 통과한다
        self.assertEqual(len(control.prompts), 1, out)
        self.assertNotIn("DUP_OTHER", out)


class IssueEditTest(unittest.TestCase):
    """연결 d — 이슈 수정: 이미지 변경(image_change)이 글의 제목·태그를 AI 검색어 프롬프트에 싣는다(감사 F4). 본문 전체를 AI 에 보내는 op_llm_patch 의 대상은 고정 페이지뿐이다(F5)."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = make_edit_root(tmp.name)
        write(self.root, "_posts/경제·일/2026-11-20-KR-100000.md", fact_text(0))
        write(self.root, "_posts/사회·정책/2026-11-01-KR-090000.md", normal_text(0))
        self.prompts = []
        self.pick_calls = []

    def llm(self, prompt):
        self.prompts.append(prompt)
        return '{"image_queries": ["gray city", "office desk"]}', "fake"

    def picker(self, queries, used):
        self.pick_calls.append(queries)
        return "https://images.unsplash.com/photo-777?auto=format&fit=crop&w=1000&q=80"

    def go(self, target, prompt="회색 도시 사진으로 바꿔 주세요"):
        return runner.process_issue(issue(image_body(target, prompt), labels=("blog-control", "edit:image"), title="[이미지 변경] x"), self.root, env=ENV, llm=self.llm, image_picker=self.picker)

    def test_an_image_change_on_a_marked_post_is_refused_before_any_ai_call(self):
        result = self.go(FACT_POSTS[0]["title"])
        self.assertEqual(result.status, "rejected", result.reasons)
        self.assertTrue(any("구조화 공개 자료" in reason for reason in result.reasons), result.reasons)
        self.assertEqual((self.prompts, self.pick_calls), ([], []))
        self.assertEqual((self.root / "_posts/경제·일/2026-11-20-KR-100000.md").read_bytes().decode("utf-8"), fact_text(0))      # 파일은 그대로

    def test_the_control_post_without_a_marker_still_sends_its_title_to_the_query_prompt(self):
        result = self.go(NORMAL_POSTS[0]["title"])
        self.assertEqual(result.status, "ok", result.reasons)
        self.assertEqual(len(self.prompts), 1)
        self.assertIn(NORMAL_POSTS[0]["title"], self.prompts[0])
        self.assertEqual(leaked(self.prompts[0], FACT_POSTS[0]), [])

    def test_op_image_refuses_marked_texts_in_every_marked_form_and_unknown_headers(self):
        fields = {"user_prompt": "회색 도시 사진"}
        for name, text in (("정본", fact_text(0)), ("CRLF", fact_text(0, newline="\r\n").replace("\r\n", "\n")), ("키 대소문자", fact_text(0).replace("provenance:", "Provenance:")),
                           ("모르는 값", fact_text(0).replace('"facts"', '"human"')), ("닫히지 않은 머리말", fact_text(0, marker=False).replace("\n---\n\n", "\n\n"))):
            with self.subTest(case=name):
                with self.assertRaises(ops.EditError):
                    ops.op_image(text, fields, {"path": "x.md", "title": FACT_POSTS[0]["title"]}, self.root, llm=self.llm, picker=self.picker)
        self.assertEqual((self.prompts, self.pick_calls), ([], []))

    def test_op_llm_patch_refuses_a_marked_file(self):
        with self.assertRaises(ops.EditError):
            ops.op_llm_patch(fact_text(0), {"after": "첫 문장을 고쳐 주세요"}, {"label": "x", "forbidden": []}, self.llm)
        self.assertEqual(self.prompts, [])

    def test_op_llm_patch_also_refuses_a_file_whose_marker_state_is_unknown_before_any_ai_call(self):
        """D-199: op_image 와 같은 규칙(알 수 없으면 막는다) — 머리말이 닫히지 않았거나 읽을 수 없는 모양이면 표식 여부를 알 수 없으므로 AI 를 부르기 전에 거절한다."""
        for name, text in (("닫히지 않은 머리말", fact_text(0, marker=False).replace("\n---\n\n", "\n\n")), ("줄 안 CR", "---\ntitle: x\rprovenance: facts\n---\n본문\n"),
                           ("복합 키", "---\ntitle: x\n? provenance\n: facts\n---\n본문\n")):
            with self.subTest(case=name):
                with self.assertRaises(ops.EditError):
                    ops.op_llm_patch(text, {"after": "첫 문장을 고쳐 주세요"}, {"label": "x", "forbidden": []}, self.llm)
        self.assertEqual(self.prompts, [])

    def test_every_fixed_page_of_the_real_site_reads_as_unmarked_so_the_refusal_changes_nothing_today(self):
        """위 거절이 오늘의 동작을 바꾸지 않는다는 증거: 진짜 저장소의 고정 페이지(about·privacy·contact·categories·루트 페이지)는 모두 표식 없음 또는 머리말 없음으로 읽혀 거절되지 않는다."""
        spec = spec_mod.load_spec(ROOT)
        discover = ((spec.get("targets") or {}).get("page") or {}).get("discover") or {}
        found = pages._candidates(ROOT, discover)
        self.assertGreaterEqual(len(found), 4)
        for rel in sorted(found):
            with self.subTest(page=rel):
                text = (ROOT / rel).read_bytes().decode("utf-8")
                self.assertIn(provenance.mark_of_text(text), (provenance.MARK_NONE, provenance.MARK_NO_FRONT_MATTER))

    def test_op_llm_patch_still_works_for_a_page_without_a_marker(self):
        def llm(prompt):
            self.prompts.append(prompt)
            return json.dumps({"patches": [{"old": "본문 문장입니다.", "new": "고친 문장입니다."}], "reason": ""}), "fake"
        text = normal_text(0)
        out = ops.op_llm_patch(text, {"after": "문장을 고쳐 주세요"}, {"label": "x", "forbidden": []}, llm)
        self.assertIn("고친 문장입니다.", out)
        self.assertEqual(len(self.prompts), 1)

    def real_call_object(self, reply):
        """진짜 호출 객체(방벽 포함)와 가짜 클라이언트 — 임시 저장소 폴더 안에서(방벽은 작업 폴더의 `_posts` 를 훑는다)."""
        class Models:
            def generate_content(inner, model, contents, **kwargs):
                self.prompts.append(contents)
                return SimpleNamespace(text=reply, usage_metadata=None, model_version=model)
        from pipeline.llm import make_gemini_llm
        ai_guard.reset_cache()
        previous = os.getcwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, previous)
        self.addCleanup(ai_guard.reset_cache)
        return make_gemini_llm("테스트 키 값", ["모델 하나"], client_factory=lambda: SimpleNamespace(models=Models()))

    def test_a_barrier_refusal_inside_the_query_prompt_is_not_swallowed(self):
        """op_image 의 거절을 우회해 image_queries 를 직접 불러도(진짜 호출 객체의 방벽이 막는다) 요청 문구로 덮이지 않고 예외가 그대로 올라온다."""
        call = self.real_call_object('{"image_queries": ["a b"]}')
        with self.assertRaises(ai_guard.AiInputForbidden):
            ops.image_queries("회색 도시 사진", FACT_POSTS[0]["title"], "실업률", call)
        self.assertEqual(self.prompts, [])

    def test_a_barrier_refusal_inside_the_patch_prompt_is_not_turned_into_an_infra_failure(self):
        """표식이 없는 페이지 원문에 표식 글의 제목이 들어 있어도(규칙이 바뀌어 새어 들어온 경우) op_llm_patch 는 AI 를 부르지 않고, 방벽의 예외를 '인프라 실패' 로 바꾸지 않고 그대로 올린다."""
        call = self.real_call_object(json.dumps({"patches": [{"old": "본문 문장입니다.", "new": "고친 문장입니다."}], "reason": ""}))
        page = normal_text(0) + "\n" + FACT_POSTS[0]["title"] + "\n"
        with self.assertRaises(ai_guard.AiInputForbidden):
            ops.op_llm_patch(page, {"after": "문장을 고쳐 주세요"}, {"label": "x", "forbidden": []}, call)
        self.assertEqual(self.prompts, [])

    def test_scene_5_the_refusal_comes_out_of_the_issue_runner_and_the_cli_reports_an_error(self):
        """장면 5(예외 사슬 일곱 곳 중 이슈 수정 — 이미지 변경과 본문 패치를 한 곳으로 센다, D-195): 표식 없는 보통 글이 표식 글과 같은 제목을 가졌다(op_image 의 구조 거절은 표식이 있는 파일만 거절한다).
        제목이 검색어 프롬프트에 실려 방벽이 막고, 예외는 image_queries·op_image·process_issue 어디서도 삼켜지지 않는다. 명령줄(main)은 이를 '예상하지 못한 오류' 로 남기고 빨갛게 끝난다."""
        enter_repo(self, self.root)
        write(self.root, "_posts/사회·정책/2026-11-02-KR-090000.md", post_text(MARKED_TITLE, "사회·정책", ["도서관"], "표식 없는 글의 설명 문장입니다 아주 길게 이어 씁니다 시험용", "https://images.unsplash.com/photo-1000000000003?auto=format&fit=crop&w=1000&q=80"))
        sdk = SdkCounter(lambda prompt: '{"image_queries": ["gray city"]}')
        call = sdk.call_object()
        request = issue(image_body("2026-11-02-KR-090000.md", "회색 도시 사진으로 바꿔 주세요"), labels=("blog-control", "edit:image"), title="[이미지 변경] x")
        with self.assertRaises(ai_guard.AiInputForbidden):
            runner.process_issue(request, self.root, env=ENV, llm=call, image_picker=self.picker)
        self.assertEqual((sdk.prompts, self.pick_calls), ([], []))
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        issue_file, out = Path(scratch.name) / "issue.json", Path(scratch.name) / "out"
        issue_file.write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8")
        from contextlib import redirect_stdout
        from io import StringIO
        buffer = StringIO()
        with mock.patch.object(runner, "build_llm", return_value=call), mock.patch.object(runner, "default_image_picker", return_value=self.picker), \
                mock.patch.dict(os.environ, {"GEMINI_API_KEY": "k"}), redirect_stdout(buffer):
            code = runner.main(["--issue-file", str(issue_file), "--out", str(out), "--root", str(self.root)])
        self.assertNotEqual(code, 0)
        self.assertIn("AiInputForbidden", buffer.getvalue())
        self.assertEqual(sdk.prompts, [])

    def test_fixed_page_candidates_never_include_posts(self):
        """고정 페이지 후보 규칙: 루트 파일만 보고, 명세가 `_posts` 아래 파일을 올리면 거절한다(본문 전체가 AI 로 가는 길을 글에 열지 않는다)."""
        spec = spec_mod.load_spec(self.root)
        discover = ((spec.get("targets") or {}).get("page") or {}).get("discover") or {}
        found = pages._candidates(self.root, discover)
        self.assertTrue(found)
        self.assertFalse([rel for rel in found if rel.startswith("_posts/") or "-KR-" in rel])
        with self.assertRaises(pages.PagesError):
            pages._candidates(self.root, {**discover, "include": [*discover.get("include", []), "_posts/경제·일/2026-11-20-KR-100000.md"]})
        write(self.root, "_posts/editable-post.md", "---\nlayout: post\neditable: true\n---\n본문\n")
        self.assertNotIn("_posts/editable-post.md", pages._candidates(self.root, discover))
        self.assertNotIn("editable-post.md", pages._candidates(self.root, discover))


class ChainSmallScenesTest(RepoCase):
    """예외 사슬 일곱 곳 중 장면 6(주제 확장 pick_topic)과 7(대표 사진 검색어 ask_queries·find_main_image) — D-195. 예전에는 두 곳이 방벽 예외를 `except Exception` 으로 삼켜 결함 신호가 사라졌다
    (pick_topic 은 'LLM 키·할당량을 확인하세요' 로 엉뚱하게 안내하고, ask_queries 는 흔적 없이 영문 제목·라벨 검색어로 대신했다)."""

    def setUp(self):
        super().setUp()
        write(self.root, FACT_POSTS[0]["rel"], fact_text(0))
        self.sdk = SdkCounter(lambda prompt: '["출근 전 10분 가볍게 몸 깨우는 아침 루틴"]')
        self.call = self.sdk.call_object()

    def test_scene_6_pick_topic_does_not_turn_the_refusal_into_expand_failed(self):
        profile = dict(registry.load_profile("blogger_ai_tools_ko"), seed_topics=[])
        marked_history = [{"topic": MARKED_TITLE}]          # 구조 필터가 거르지 못한 표식 제목이 주제 이력으로 들어온 모양
        with self.assertRaises(ai_guard.AiInputForbidden):
            topics.pick_topic(profile, marked_history, date(2026, 11, 20), [], random.Random(1), llm=self.call)
        self.assertEqual(self.sdk.prompts, [])
        topics.pick_topic(profile, [{"topic": "이력에 있는 보통 주제 제목입니다 열두 글자 넘게"}], date(2026, 11, 20), [], random.Random(1), llm=self.call)       # 대조군: 표식 글의 글자가 없으면 모델을 부른다
        self.assertEqual(len(self.sdk.prompts), 1)

    def test_scene_7_ask_queries_does_not_swallow_the_refusal_and_the_photo_step_leaves_one_visible_line(self):
        with self.assertRaises(ai_guard.AiInputForbidden):
            main_image.ask_queries(self.call, MARKED_TITLE, ["가상 지역 가"])
        self.assertEqual(self.sdk.prompts, [])
        result = main_image.find_main_image("k" * 20, MARKED_TITLE, ["가상 지역 가"], self.call)          # 바깥 껍데기는 예외를 올리지 않는다 — 이유 한 줄(클래스 이름)을 남기고 글은 사진 없이 올라간다
        self.assertEqual((result.ok, result.reason, result.detail), (False, "UNEXPECTED", "AiInputForbidden"))
        self.assertEqual(self.sdk.prompts, [])
        main_image.ask_queries(self.call, "Plain English Title Without Any Marked Words", ["sample label"])          # 대조군: 표식 글의 글자가 없으면 모델을 부른다
        self.assertEqual(len(self.sdk.prompts), 1)


if __name__ == "__main__":
    unittest.main()
