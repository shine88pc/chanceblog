"""AI 입력 방벽(pipeline/ai_guard.py) 시험 — AI 를 부르기 직전에 표식 글의 글자가 프롬프트에 있으면 부르지 않는다. 네트워크 없이 돈다(가짜 클라이언트).

못박는 것
1. 막는 것: 제목 전체·제목 앞 24자·설명 앞 40자·이력 표식 항목의 제목, 공백·대소문자·문장 부호·JSON 따옴표 이스케이프가 달라도 같은 글로 본다. 오탐 없음(표식 없는 글·표식 글이 없을 때는 통과).
2. **못 막는 것을 '못 막는다'고 단언한다**(방벽을 믿고 구조 방벽을 줄이지 못하게): 제목의 뒤쪽 조각만 · 값만 · 의역 · 번역 · 짧은 제목 · 표식 글의 본문·태그·분류.
3. 두 입구(generator.call_gemini_with_fallback·pipeline.llm.make_gemini_llm 의 호출 객체)가 모델을 한 번도 부르지 않고(재시도·폴백·대기 없음) 예외 문구에 글 내용이 없다.
4. 호출 직전의 최신 상태: 파일을 더하거나 고치거나 지우면 다음 호출에 반영된다(수정 시각 해상도 한계를 넘어서도). 캐시가 있어도 `_posts` 가 수백 편이어도 호출당 ms 단위, 적대적 입력에서 시간 한도.
"""
import io
import json
import os
import random
import shutil
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import _bootstrap  # noqa: F401
import generator as g
from ai_flow_helpers import FACT_POSTS, NORMAL_POSTS, RepoCase, fact_text, history_entry, normal_text, post_text, write
from pipeline import ai_guard, llm, main_image

FACT_TITLE = FACT_POSTS[0]["title"]
FACT_DESCRIPTION = FACT_POSTS[0]["description"]
P_LINE = 'provenance: "facts"'


def prompt_with(*pieces):
    """실제 프롬프트처럼 지침 글 사이에 조각을 끼운 글."""
    return "당신은 편집자입니다. 아래 [최근 다룬 주제/제목]을 피해 글을 쓰세요.\n" + "\n".join(pieces) + "\n[중요 지침]\n- JSON 객체만 반환하세요.\n"


def titles_json(*titles):
    return json.dumps(list(titles), ensure_ascii=False)


class NormalizeTest(unittest.TestCase):
    def test_spaces_case_punctuation_and_width_do_not_matter(self):
        base = ai_guard.normalize("가상 지역 가 실업률 3.5%(2026년 3월 기준)")
        for variant in ("가상  지역\n가\t실업률 3.5% ( 2026년 3월 기준 )", "가상지역가실업률3.5%(2026년3월기준)", "가상 지역 가 실업률 ３．５％（２０２６년 ３월 기준）"):
            self.assertEqual(ai_guard.normalize(variant), base)
        self.assertEqual(ai_guard.normalize("Unemployment RATE"), ai_guard.normalize("unemployment   rate"))
        self.assertEqual(ai_guard.normalize("ＡＢＣ ｄｅｆ"), "abcdef")
        self.assertEqual(ai_guard.normalize("a_b-c.d"), "abcd")

    def test_case_folding_not_lowercasing_is_used_so_german_sharp_s_and_final_sigma_match(self):
        """독립 검증이 찾은 시험 틈(변이 X1): casefold 대신 lower 를 써도 시험이 초록이었다 — 독일어 ß(→ss)·그리스 끝 시그마(ς→σ)가 같은 글자로 접히는 것을 못박는다."""
        self.assertEqual(ai_guard.normalize("Straße"), ai_guard.normalize("STRASSE"))
        self.assertEqual(ai_guard.normalize("οδος"), ai_guard.normalize("οδοσ"))

    def test_json_quote_escapes_disappear(self):
        title = '가상 "지역" 실업률 3.5%'
        escaped = titles_json(title)         # 프롬프트에는 \" 로 들어간다
        self.assertIn('\\"', escaped)
        self.assertIn(ai_guard.normalize(title), ai_guard.normalize(escaped))


class FragmentsTest(RepoCase):
    def test_a_marked_post_gives_title_prefix_and_description_fragments(self):
        write(self.root, FACT_POSTS[0]["rel"], fact_text(0))
        fragments = ai_guard.marked_fragments()
        title = ai_guard.normalize(FACT_TITLE)
        self.assertEqual(fragments[title], "post-title")
        self.assertEqual(fragments[title[:ai_guard.TITLE_PREFIX_CHARS]], "post-title-prefix")
        self.assertEqual(fragments[ai_guard.normalize(FACT_DESCRIPTION)[:ai_guard.DESCRIPTION_PREFIX_CHARS]], "post-description")
        self.assertEqual(len(fragments), 3)

    def test_unmarked_posts_and_a_folder_without_posts_give_nothing(self):
        self.assertEqual(ai_guard.marked_fragments(), {})
        self.add_normal_posts()
        self.assertEqual(ai_guard.marked_fragments(), {})

    def test_a_post_whose_marker_state_is_unknown_still_gives_fragments(self):
        broken = fact_text(0, marker=False).replace("\n---\n\n", "\n\n")      # 머리말을 닫는 줄을 지웠다 — 표식 여부를 알 수 없는 글
        write(self.root, FACT_POSTS[0]["rel"], broken)
        self.assertIn(ai_guard.normalize(FACT_TITLE), ai_guard.marked_fragments())

    def test_a_marked_history_entry_gives_title_fragments_and_an_unmarked_one_does_not(self):
        self.set_history([history_entry(FACT_POSTS[1]["title"], marker=True), history_entry(NORMAL_POSTS[0]["title"])])
        fragments = ai_guard.marked_fragments()
        self.assertEqual(set(fragments.values()), {"history-title"})
        self.assertIn(ai_guard.normalize(FACT_POSTS[1]["title"]), fragments)
        self.assertNotIn(ai_guard.normalize(NORMAL_POSTS[0]["title"]), fragments)

    def test_short_titles_and_descriptions_are_not_used_as_fragments(self):
        write(self.root, "_posts/짧은/2026-11-22-KR-100000.md", post_text("실업률 동향", "경제", ["a"], "짧은 설명", "https://example.invalid/a.png", marker=True))
        self.assertEqual(ai_guard.marked_fragments(), {})

    def test_other_file_types_and_names_are_scanned_too(self):
        text = fact_text(0)
        for index, name in enumerate(("a.markdown", "b.HTML", "c.MD")):
            write(self.root, f"_posts/x/2026-11-2{index}-{name}", text.replace(FACT_POSTS[0]["title"], FACT_POSTS[0]["title"] + f" {index}"))
        write(self.root, "_posts/x/readme.txt", text)
        self.assertEqual(len([k for k, v in ai_guard.marked_fragments().items() if v == "post-title"]), 3)

    def test_a_file_that_is_not_utf8_does_not_break_the_scan(self):
        write(self.root, FACT_POSTS[0]["rel"], fact_text(0))
        bad = self.root / "_posts" / "x" / "2026-11-25-KR-bad.md"
        bad.parent.mkdir(parents=True, exist_ok=True)
        bad.write_bytes(b"---\ntitle: \xff\xfe\n---\n")
        self.assertIn(ai_guard.normalize(FACT_TITLE), ai_guard.marked_fragments())


class AssertCleanTest(RepoCase):
    def setUp(self):
        super().setUp()
        self.add_fact_posts()
        self.add_normal_posts()
        self.set_history([history_entry("이력에만 있는 가상 지역 다 청년 고용률 61.2% 보도", marker=True), history_entry("이력의 보통 글 제목은 이것이다 — 숫자 없음")])

    def blocked(self, prompt, kind=None):
        with self.assertRaises(ai_guard.AiInputForbidden) as ctx:
            ai_guard.assert_clean(prompt)
        if kind is not None:
            self.assertIn(f"종류 {kind}", str(ctx.exception))
        return ctx.exception

    def test_the_whole_title_is_blocked(self):
        self.blocked(prompt_with(titles_json("다른 제목", FACT_TITLE)), "post-title")

    def test_the_first_24_normalized_characters_of_the_title_are_blocked(self):
        flat = ai_guard.normalize(FACT_TITLE)
        self.assertGreater(len(flat), ai_guard.TITLE_PREFIX_CHARS + 3)
        size = next(k for k in range(1, len(FACT_TITLE)) if len(ai_guard.normalize(FACT_TITLE[:k])) >= ai_guard.TITLE_PREFIX_CHARS)      # 정규화하면 막 24자가 되는 앞부분 — 잘린 제목(100자 한도 따위)
        cut = FACT_TITLE[:size]
        self.assertNotIn(flat, ai_guard.normalize(cut))
        self.blocked(prompt_with(titles_json(cut + " …")), "post-title-prefix")
        short = FACT_TITLE[:size - 3]            # 24자에 모자라면 막지 못한다(제목 앞 24자가 이 방벽의 최소 조각이다)
        self.assertLess(len(ai_guard.normalize(short)), ai_guard.TITLE_PREFIX_CHARS)
        ai_guard.assert_clean(prompt_with(titles_json(short)))

    def test_the_first_40_normalized_characters_of_the_description_are_blocked(self):
        self.blocked(prompt_with(FACT_DESCRIPTION[:60]), "post-description")

    def test_a_marked_history_entry_title_is_blocked(self):
        self.blocked(prompt_with("이력에만 있는 가상 지역 다 청년 고용률 61.2% 보도"), "history-title")

    def test_the_first_24_normalized_characters_of_a_marked_history_title_are_blocked(self):
        """독립 검증이 찾은 시험 틈(변이 X4): 이력 표식 항목의 제목 앞 24자 조각을 만들지 않아도 시험이 초록이었다 — 잘린 제목(100자 한도 따위)이 프롬프트에 든 경우를 막는다."""
        title = "이력에만 있는 가상 지역 마 신규 창업 건수가 전년 대비 늘어난 이유를 값으로 살펴보기"
        self.set_history([history_entry(title, marker=True)])
        flat = ai_guard.normalize(title)
        self.assertGreater(len(flat), ai_guard.TITLE_PREFIX_CHARS + 6)
        size = next(k for k in range(1, len(title)) if len(ai_guard.normalize(title[:k])) >= ai_guard.TITLE_PREFIX_CHARS)
        cut = title[:size]
        self.assertNotIn(flat, ai_guard.normalize(cut))
        self.blocked(prompt_with(cut + " …"), "history-title")

    def test_variants_of_spacing_case_punctuation_and_quotes_are_blocked(self):
        for variant in (FACT_TITLE.replace(" ", ""), FACT_TITLE.replace(" ", "  ").upper(), FACT_TITLE.replace("(", " ( ").replace(")", " ) "),
                        titles_json(FACT_TITLE.replace("가상", '"가상"')), FACT_TITLE.replace("%", "％").replace("3.5", "３．５"), "\n".join(FACT_TITLE.split(" "))):
            with self.subTest(variant=variant[:30]):
                self.blocked(prompt_with(variant))

    def test_the_exception_message_never_carries_the_text(self):
        error = self.blocked(prompt_with(FACT_TITLE))
        message = str(error)
        for piece in (FACT_TITLE, FACT_TITLE[:8], FACT_TITLE[4:12], "3.5", FACT_DESCRIPTION[:8], "실업률"):
            self.assertNotIn(piece, message)
        self.assertNotRegex(message, r"[~]|https?://")

    def test_prompts_without_marked_text_pass_including_unmarked_posts(self):
        ai_guard.assert_clean(prompt_with(titles_json(*[post["title"] for post in NORMAL_POSTS])))
        ai_guard.assert_clean(prompt_with("이력의 보통 글 제목은 이것이다 — 숫자 없음"))
        ai_guard.assert_clean("")
        ai_guard.assert_clean("아무 관계 없는 짧은 글")
        ai_guard.assert_clean(prompt_with(*[normal_text(i) for i in range(len(NORMAL_POSTS))]))

    def test_no_marked_posts_means_no_work_and_a_pass_for_anything(self):
        for post in FACT_POSTS:
            (self.root / post["rel"]).unlink()
        (self.root / "history.json").unlink()
        ai_guard.reset_cache()
        with mock.patch.object(ai_guard, "normalize", side_effect=AssertionError("표식 글이 없으면 프롬프트를 읽지도 않는다")):
            ai_guard.assert_clean(prompt_with(FACT_TITLE, FACT_DESCRIPTION))

    def test_prompt_types_other_than_text_are_handled(self):
        self.blocked(FACT_TITLE.encode("utf-8"))
        self.blocked([FACT_TITLE, "다른 조각"])
        ai_guard.assert_clean(b"\xff\xfe broken bytes")
        ai_guard.assert_clean(None)


class LimitsTest(RepoCase):
    """못 막는 것 — 이 시험이 '못 막는다'를 못박는다. 이 중 하나라도 막히게 바꾸면 이 시험을 고치고 docs/AI_FLOW.md 의 한계 표를 같이 고친다(그래야 방벽을 믿고 구조 방벽을 줄이는 일을 막는다)."""

    LONG_TITLE = "가상 지역 다 청년 고용률 61.2%(2026년 3월 기준)와 가상 지역 라 평균 임금 월 312만 원(2026년 3월 기준)의 차이, 가상 지역 마 신규 창업 412건의 변화까지 함께 읽기"

    def setUp(self):
        super().setUp()
        write(self.root, "_posts/경제/2026-11-26-KR-100000.md", post_text(self.LONG_TITLE, "경제", ["고용"], FACT_DESCRIPTION, "https://example.invalid/a.png", marker=True))
        write(self.root, FACT_POSTS[0]["rel"], fact_text(0))

    def passes(self, text):
        ai_guard.assert_clean(prompt_with(text))

    def test_the_tail_of_a_long_title_alone_is_not_blocked(self):
        flat = ai_guard.normalize(self.LONG_TITLE)
        self.assertGreater(len(flat), ai_guard.TITLE_PREFIX_CHARS + 30)
        self.passes(self.LONG_TITLE[-30:])
        self.passes(self.LONG_TITLE[-40:])

    def test_a_value_alone_is_not_blocked(self):
        for value in ("3.5%", "103.4", "61.2%", "월 312만 원", "0.3%p"):
            self.passes(value)

    def test_a_paraphrase_is_not_blocked(self):
        self.passes("가상 지역 가의 실업률이 한 달 전보다 조금 올라 3.5% 수준이라는 내용")
        self.passes("지역 가 실업률 상승(3월)")

    def test_a_translation_is_not_blocked(self):
        self.passes("Unemployment rate in Virtual Region A is 3.5% (March 2026), up 0.3 points from the previous period")

    def test_a_short_title_is_not_a_fragment(self):
        write(self.root, "_posts/짧은/2026-11-27-KR-100000.md", post_text("가상 지역 실업률", "경제", ["a"], "짧은 설명", "https://example.invalid/b.png", marker=True))
        self.assertLess(len(ai_guard.normalize("가상 지역 실업률")), ai_guard.TITLE_MIN_CHARS)
        self.passes("가상 지역 실업률")

    def test_tags_category_and_body_sentences_of_a_marked_post_are_not_fragments(self):
        for text in ("실업률 가상 지역 가 공개 통계 숫자로 읽기", "경제·일", "본문 문장입니다. 이 글은 시험용 가짜 글이며 실제 자료가 아닙니다."):
            self.passes(text)

    def test_a_corrupt_or_oversized_history_file_is_not_read(self):
        """생성기는 깨진 이력을 '빈 기록' 으로 읽는다(read_history) — 이력 제목이 그 길로 AI 입력이 되지 않으므로 방벽도 읽지 못한 이력은 훑지 않고 지나간다(한계 L8). 읽히면 막히는 것을 대조로 둔다."""
        title = "이력에만 있는 가상 지역 사 고용 지표 보도 제목입니다 값 47.5%"
        text = json.dumps([history_entry(title, marker=True)], ensure_ascii=False)
        write(self.root, "history.json", text[:-3])          # 잘린 JSON
        self.passes(title)
        write(self.root, "history.json", text)                # 읽히면 막힌다(대조)
        with self.assertRaises(ai_guard.AiInputForbidden):
            self.passes(title)
        write(self.root, "history.json", "[" * 100000 + "]" * 100000)          # 깊게 중첩된 JSON — 읽는 중 RecursionError 가 나도 예외로 터지지 않는다
        self.passes(title)
        write(self.root, "history.json", text)
        with mock.patch.object(ai_guard, "MAX_HISTORY_BYTES", 10):
            ai_guard.reset_cache()
            self.passes(title)                                 # 너무 큰 이력은 읽지 않는다
        ai_guard.reset_cache()
        with self.assertRaises(ai_guard.AiInputForbidden):
            self.passes(title)

    def test_a_post_file_that_cannot_be_read_gives_no_fragments_that_call_but_is_read_again_on_the_next(self):
        """L9(D-199): 읽기 오류가 난 글은 그 호출에서 조각을 못 만든다(통과) — 그러나 '조각 없음' 으로 굳혀 캐시하지 않아 다음 호출에서 다시 읽어 막는다(오래된 파일도 마찬가지). 생성기도 같은 글을 읽지 못해 건너뛴다."""
        path = write(self.root, "_posts/읽기오류/2026-11-28-KR-100000.md", fact_text(1))
        old_ns = time.time_ns() - 3600 * 10 ** 9
        os.utime(path, ns=(old_ns, old_ns))
        ai_guard.reset_cache()
        title = FACT_POSTS[1]["title"]
        real_open = open

        def denied(target, *args, **kwargs):
            if str(target).endswith("2026-11-28-KR-100000.md"):
                raise PermissionError("denied")
            return real_open(target, *args, **kwargs)
        with mock.patch("builtins.open", denied):
            self.passes(title)                      # 읽지 못한 호출에서는 통과(한계)
        with self.assertRaises(ai_guard.AiInputForbidden):
            self.passes(title)                      # 다음 호출에서 다시 읽어 막는다(예전에는 오래된 파일이면 영구히 통과했다)

    def test_a_marker_added_in_place_with_the_same_size_inode_and_an_old_time_is_not_seen(self):
        """L10(D-199): (수정 시각·크기·inode) 가 그대로인 제자리 수정은 오래된 파일의 캐시가 놓친다 — `touch -r`·`rsync -t`·`cp -p` 처럼 시각을 되돌리는 도구로 표식을 더한 글. 방금 쓴 파일은 따로 다시 읽는다(CacheFreshnessTest)."""
        decoy = fact_text(1, marker=False).replace("description: ", 'xxxxxxxxxx: "facts"\ndescription: ', 1)
        marked = fact_text(1, marker=False).replace("description: ", P_LINE + "\ndescription: ", 1)
        self.assertEqual(len(decoy.encode("utf-8")), len(marked.encode("utf-8")))
        path = write(self.root, "_posts/제자리/2026-11-29-KR-100000.md", decoy)
        old_ns = time.time_ns() - 3600 * 10 ** 9
        os.utime(path, ns=(old_ns, old_ns))
        ai_guard.reset_cache()
        title = FACT_POSTS[1]["title"]
        self.passes(title)                          # 표식이 없는 글로 읽어 캐시한다
        path.write_bytes(marked.encode("utf-8"))
        os.utime(path, ns=(old_ns, old_ns))
        self.passes(title)                          # 표식이 생겼지만 서명이 같아 놓친다(한계)
        ai_guard.reset_cache()
        with self.assertRaises(ai_guard.AiInputForbidden):
            self.passes(title)                      # 캐시를 비우고 다시 읽으면 막힌다(대조 — 글에는 표식이 있다)

    def test_prompts_held_as_bytearray_or_memoryview_are_not_read(self):
        """L11(D-199): 프롬프트가 str·bytes·목록·사전 같은 흔한 모양이 아니라 bytearray·memoryview 이면 글자로 읽지 않는다(지금 호출자는 모두 str 이다)."""
        data = prompt_with(FACT_TITLE).encode("utf-8")
        with self.assertRaises(ai_guard.AiInputForbidden):
            ai_guard.assert_clean(data)             # 대조: bytes 는 막힌다
        ai_guard.assert_clean(bytearray(data))
        ai_guard.assert_clean(memoryview(data))

    def test_lookalike_letters_from_other_scripts_are_not_the_same_text(self):
        """L12(D-199): 정규화(NFKC→소문자 접기→글자·숫자만)는 키릴·그리스 동형 글자·한글 호환 자모 따위를 같은 글자로 접지 못한다. 현재 코드는 제목을 이렇게 바꿔 프롬프트에 싣지 않는다."""
        english = "Virtual region A unemployment rate 3.5 percent in March 2026"
        write(self.root, "_posts/영문/2026-11-30-EN-100000.md", post_text(english, "economy", ["a"], "A short synthetic description that is long enough to count", "https://example.invalid/e.png", marker=True, lang="en"))
        with self.assertRaises(ai_guard.AiInputForbidden):
            self.passes(english)                    # 대조: 같은 글자는 막힌다
        self.passes(english.replace("o", chr(0x043E)))          # 라틴 o 를 키릴 о 로 바꾸면 통과(한계)

    def test_a_block_or_multiline_title_is_not_read_as_the_title(self):
        """L13(D-199): 방벽은 머리말의 title·description 을 한 줄 값으로만 읽는다 — 블록 글자(`title: |`)로 쓴 제목은 YAML 과 다르게 읽어 제목 조각을 놓친다(구조 방벽이 막고, 생성기가 쓰는 정본은 한 줄 큰따옴표 제목이다)."""
        title = FACT_POSTS[1]["title"]
        before = dict(ai_guard.marked_fragments())
        text = "\n".join(["---", "layout: post", "title: |", "  " + title, 'provenance: "facts"', "---", "", "본문", ""])
        write(self.root, "_posts/블록/2026-11-30-KR-100000.md", text)
        self.assertEqual(ai_guard.marked_fragments(), before)          # 표식 글인데도 새 조각이 하나도 생기지 않는다
        self.passes(title)

    def test_a_history_that_cannot_be_read_passes_with_one_fixed_warning_line(self):
        """정책 ①(D-199): 깨진·목록이 아닌·너무 큰 이력은 통과시키되 조용히 지나가지 않는다 — 고정 문장 한 줄(파일 내용 없음), 같은 파일은 한 번만. 읽히는 이력·없는 이력에는 아무 줄도 없다."""
        import contextlib
        import io

        old_ns = time.time_ns() - 3600 * 10 ** 9

        def put(text):
            path = write(self.root, "history.json", text)
            os.utime(path, ns=(old_ns, old_ns))          # 오래된 파일 — 캐시를 믿으므로 같은 파일은 한 번만 알린다
            ai_guard.reset_cache()

        def calls(times=3):
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                for _ in range(times):
                    self.passes("아무 글")
            return buffer.getvalue()
        put("{ 깨진 JSON 비밀 값")
        out = calls()
        self.assertEqual(out.splitlines(), [ai_guard.HISTORY_WARNING])
        self.assertNotIn("비밀", out)
        put('{"not": "a list"}')
        self.assertEqual(calls().splitlines(), [ai_guard.HISTORY_WARNING])
        put("[]")
        self.assertEqual(calls(), "")
        ai_guard.reset_cache()
        (self.root / "history.json").unlink()
        self.assertEqual(calls(), "")

    def test_the_limits_are_documented_in_the_constants(self):
        self.assertEqual((ai_guard.TITLE_MIN_CHARS, ai_guard.TITLE_PREFIX_CHARS, ai_guard.DESCRIPTION_PREFIX_CHARS, ai_guard.DESCRIPTION_MIN_CHARS), (12, 24, 40, 20))


class CacheFreshnessTest(RepoCase):
    def blocked(self, prompt):
        with self.assertRaises(ai_guard.AiInputForbidden):
            ai_guard.assert_clean(prompt)

    def test_a_post_added_after_the_first_call_is_seen_on_the_next_call(self):
        prompt = prompt_with(FACT_TITLE)
        ai_guard.assert_clean(prompt)          # 아직 표식 글이 없다
        write(self.root, FACT_POSTS[0]["rel"], fact_text(0))
        self.blocked(prompt)

    def test_a_post_removed_is_no_longer_blocked(self):
        write(self.root, FACT_POSTS[0]["rel"], fact_text(0))
        prompt = prompt_with(FACT_TITLE)
        self.blocked(prompt)
        (self.root / FACT_POSTS[0]["rel"]).unlink()
        ai_guard.assert_clean(prompt)

    DECOY = 'xxxxxxxxxx: "facts"'              # 표식 줄과 글자 수가 같은 다른 키 줄 — 표식을 더하거나 빼도 파일 크기가 같다

    def with_line(self, line):
        return fact_text(0, marker=False).replace("description: ", line + "\ndescription: ", 1)

    def test_a_marker_added_in_place_with_the_same_size_and_time_is_seen(self):
        """같은 크기로 같은 수정 시각을 되돌려 놓고 고친 글 — 방금 읽은 파일은 믿지 않고 다시 읽는다(수정 시각 해상도에 기대지 않는다)."""
        before, after = self.with_line(self.DECOY), self.with_line(P_LINE)
        self.assertEqual(len(before.encode("utf-8")), len(after.encode("utf-8")))
        path = write(self.root, FACT_POSTS[0]["rel"], before)
        ai_guard.assert_clean(prompt_with(FACT_TITLE))
        stat = path.stat()
        path.write_bytes(after.encode("utf-8"))
        os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        self.blocked(prompt_with(FACT_TITLE))

    def test_a_marker_removed_in_place_with_the_same_size_and_time_is_seen(self):
        before, after = self.with_line(P_LINE), self.with_line(self.DECOY)
        path = write(self.root, FACT_POSTS[0]["rel"], before)
        self.blocked(prompt_with(FACT_TITLE))
        stat = path.stat()
        path.write_bytes(after.encode("utf-8"))
        os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        ai_guard.assert_clean(prompt_with(FACT_TITLE))

    def test_history_changes_are_seen(self):
        self.set_history([history_entry("이력의 표식 항목 제목입니다 — 가상 지역 마 신규 창업 412건", marker=True)])
        self.blocked(prompt_with("이력의 표식 항목 제목입니다 — 가상 지역 마 신규 창업 412건"))
        self.set_history([history_entry("이력의 표식 항목 제목입니다 — 가상 지역 마 신규 창업 412건")])
        ai_guard.assert_clean(prompt_with("이력의 표식 항목 제목입니다 — 가상 지역 마 신규 창업 412건"))
        (self.root / "history.json").unlink()
        ai_guard.assert_clean(prompt_with("이력의 표식 항목 제목입니다 — 가상 지역 마 신규 창업 412건"))

    def test_a_corrupt_history_file_does_not_stop_calls(self):
        write(self.root, "history.json", "{ 깨진 JSON")
        ai_guard.assert_clean(prompt_with("아무 글"))

    def test_an_old_unchanged_file_is_not_read_again(self):
        path = write(self.root, FACT_POSTS[0]["rel"], fact_text(0))
        old_ns = time.time_ns() - 3600 * 10 ** 9
        os.utime(path, ns=(old_ns, old_ns))
        roots = [self.root]
        ai_guard.marked_fragments(roots)
        with mock.patch.object(ai_guard, "_read_post", side_effect=AssertionError("바뀌지 않은 오래된 글을 다시 읽었다")):
            with self.assertRaises(ai_guard.AiInputForbidden):
                ai_guard.assert_clean(prompt_with(FACT_TITLE), roots=roots)

    def test_too_many_post_files_block_the_call_because_the_list_cannot_be_checked(self):
        for index in range(5):
            write(self.root, f"_posts/많은/2026-11-{index + 1:02d}-KR-{index:06d}.md", normal_text(index % 2))
        roots = [self.root]
        with mock.patch.object(ai_guard, "MAX_POST_FILES", 3):
            ai_guard.reset_cache()
            with self.assertRaises(ai_guard.AiInputForbidden) as caught:
                ai_guard.assert_clean(prompt_with("아무 글"), roots=roots)
            self.assertNotIn("2026-11-01", str(caught.exception))
        ai_guard.reset_cache()
        ai_guard.assert_clean(prompt_with("아무 글"), roots=roots)          # 한도 안이면 통과

    def test_a_folder_that_cannot_be_listed_is_not_passed_silently(self):
        write(self.root, FACT_POSTS[0]["rel"], fact_text(0))
        real_scandir = os.scandir

        def broken(path):
            if str(path).endswith("_posts"):
                raise PermissionError("denied")
            return real_scandir(path)
        with mock.patch.object(os, "scandir", broken):
            with self.assertRaises(ai_guard.AiInputForbidden) as ctx:
                ai_guard.assert_clean(prompt_with("아무 글"))
        self.assertIn("확인하지 못해", str(ctx.exception))

    def test_a_posts_folder_that_does_not_exist_is_the_normal_empty_state(self):
        ai_guard.assert_clean(prompt_with(FACT_TITLE))


class IndexSearchTest(unittest.TestCase):
    def test_the_indexed_search_agrees_with_plain_containment(self):
        rng = random.Random(20261110)
        alphabet = "가나다라마바사abc123 "
        for round_number in range(400):
            fragments = {}
            for _ in range(rng.randint(1, 30)):
                text = "".join(rng.choice(alphabet) for _ in range(rng.randint(3, 14))).strip()
                if len(text) >= 3:
                    fragments[ai_guard.normalize(text) or "x1"] = "post-title"
            fragments = {k: v for k, v in fragments.items() if len(k) >= 3}
            if not fragments:
                continue
            prompt = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 400)))
            flat = ai_guard.normalize(prompt)
            expected = any(fragment in flat for fragment in fragments)
            self.assertEqual(ai_guard._indexed_hit(flat, fragments) is not None, expected, (round_number, flat, list(fragments)))

    def test_fragments_longer_than_the_prompt_and_at_the_edges(self):
        fragments = {"가나다라마바사아자차": "post-title", "카타파하": "post-title"}
        self.assertIsNone(ai_guard._indexed_hit("가나다", fragments))
        self.assertIsNotNone(ai_guard._indexed_hit("zzz카타파하", fragments))
        self.assertIsNotNone(ai_guard._indexed_hit("카타파하zzz", fragments))
        self.assertIsNotNone(ai_guard._indexed_hit("가나다라마바사아자차", fragments))
        self.assertIsNone(ai_guard._indexed_hit("", {"abc": "post-title"}))

    def test_find_hit_uses_the_same_answer_on_both_paths(self):
        fragments = {ai_guard.normalize(FACT_TITLE): "post-title"}
        prompt = prompt_with(FACT_TITLE)
        with mock.patch.object(ai_guard, "BRUTE_FORCE_LIMIT", 0):
            self.assertEqual(ai_guard.find_hit(prompt, fragments), "post-title")
            self.assertIsNone(ai_guard.find_hit(prompt_with("관계 없는 글"), fragments))
        self.assertEqual(ai_guard.find_hit(prompt, fragments), "post-title")
        self.assertIsNone(ai_guard.find_hit(prompt, {}))


class EntrancesTest(RepoCase):
    """두 입구가 모델을 한 번도 부르지 않는다 — 재시도·폴백·대기 없음, 호출 기록에도 남지 않는다."""

    def setUp(self):
        super().setUp()
        write(self.root, FACT_POSTS[0]["rel"], fact_text(0))
        self.calls = []

        class Models:
            def generate_content(inner, model, contents, **kwargs):
                self.calls.append((model, contents))
                return SimpleNamespace(text="{}", usage_metadata=None, model_version=model)

        self.client = SimpleNamespace(models=Models())

    def test_call_gemini_with_fallback_refuses_before_any_attempt(self):
        with mock.patch.object(g, "get_client", return_value=self.client), mock.patch.dict(g.GEMINI_CALLS, {"attempts": 0, "failed": 0}):
            with self.assertRaises(ai_guard.AiInputForbidden):
                g.call_gemini_with_fallback(prompt_with(FACT_TITLE))
            self.assertEqual(g.GEMINI_CALLS, {"attempts": 0, "failed": 0})
            self.assertEqual(self.calls, [])
            g.call_gemini_with_fallback(prompt_with("관계 없는 글"))        # 대조군: 표식 글의 글자가 없으면 그대로 부른다
            self.assertEqual(len(self.calls), 1)

    def test_the_llm_call_object_refuses_before_any_attempt_retry_or_wait(self):
        sleeps = []
        call = llm.make_gemini_llm("테스트 키 값", ["모델 하나", "모델 둘"], max_retries=2, sleep=sleeps.append, client_factory=lambda: self.client)
        with self.assertRaises(ai_guard.AiInputForbidden):
            call(prompt_with(FACT_TITLE))
        self.assertEqual((self.calls, sleeps, call.call_log.attempts), ([], [], 0))
        text, model = call(prompt_with("관계 없는 글"))
        self.assertEqual(len(self.calls), 1)

    def test_the_exception_is_not_an_llm_error_so_no_caller_treats_it_as_a_model_failure(self):
        self.assertFalse(issubclass(ai_guard.AiInputForbidden, llm.LLMError))
        self.assertTrue(issubclass(ai_guard.AiInputForbidden, RuntimeError))

    def test_make_image_queries_does_not_swallow_the_refusal(self):
        with mock.patch.object(g, "get_client", return_value=self.client), mock.patch.object(g, "STUB_GEMINI", False):
            with self.assertRaises(ai_guard.AiInputForbidden):
                g.make_image_queries(FACT_TITLE, "실업률, 가상 지역 가", "경제·일")
        self.assertEqual(self.calls, [])

    def test_ask_queries_does_not_swallow_the_refusal_and_the_photo_step_leaves_one_visible_line(self):
        """D-195: 예전에는 ask_queries 가 방벽 예외를 '검색어 실패' 로 삼켜 영문 제목·라벨로 대신했고 흔적이 없었다. 이제 예외가 올라오고, 사진 단계의 바깥 껍데기(find_main_image — 어떤 경우에도 예외를 올리지 않는다)가
        `UNEXPECTED(AiInputForbidden)` 이유 한 줄로 남긴다(글은 사진 없이 올라간다). 모델은 두 경우 모두 부르지 않는다."""
        call = llm.make_gemini_llm("테스트 키 값", ["모델 하나"], client_factory=lambda: self.client)
        with self.assertRaises(ai_guard.AiInputForbidden):
            main_image.ask_queries(call, FACT_TITLE, ["가상 지역 가"])
        self.assertEqual(self.calls, [])
        result = main_image.find_main_image("k" * 20, FACT_TITLE, ["가상 지역 가"], call)
        self.assertEqual((result.ok, result.reason, result.detail), (False, "UNEXPECTED", "AiInputForbidden"))
        self.assertEqual(self.calls, [])
        queries, asked = main_image.ask_queries(call, "관계 없는 평범한 영어 제목 Sample Title Words", ["sample label"])         # 대조군: 표식 글의 글자가 없으면 지금처럼 모델을 부른다
        self.assertEqual(len(self.calls), 1)

    def test_the_shadow_runs_audit_hook_allows_the_barrier_to_read_files(self):
        """그림자 실행은 읽기 전용 구간에서 쓰기를 막는다 — 방벽은 읽기만 하므로 그 안에서도 돈다."""
        from pipeline import shadow_run
        out = self.root.parent / "shadow-guard-out"
        out.mkdir(exist_ok=True)
        self.addCleanup(shutil.rmtree, out, True)
        ai_guard.reset_cache()
        with shadow_run.read_only(g, out):
            with self.assertRaises(ai_guard.AiInputForbidden):
                ai_guard.assert_clean(prompt_with(FACT_TITLE))
            ai_guard.assert_clean(prompt_with("관계 없는 글"))


class PerformanceTest(RepoCase):
    def test_hundreds_of_marked_posts_cost_milliseconds_per_call(self):
        for index in range(300):
            title = f"가상 지역 {index:03d} 번 통계 값 {index * 7 + 11}.{index % 10}% 와 비교 보고서 제목"
            write(self.root, f"_posts/큰/2026-11-{index % 28 + 1:02d}-KR-{index:06d}.md", post_text(title, "경제", ["a"], f"설명 문장 {index} 번째 시험용 가짜 글 설명입니다 길게 이어 씁니다", "https://example.invalid/c.png", marker=True))
        old_ns = time.time_ns() - 3600 * 10 ** 9          # 방금 쓴 파일은 한동안(3초) 캐시를 믿지 않고 다시 읽는다 — 오래된 파일로 만들어 '캐시가 찬 상태' 를 잰다(느린 러너에서 한도 여유가 흔들리지 않게, D-198)
        for path in (self.root / "_posts").rglob("*.md"):
            os.utime(path, ns=(old_ns, old_ns))
        ai_guard.reset_cache()
        prompt = prompt_with(*(["관계 없는 문장 하나입니다. " * 25] * 60))          # 약 2만 자
        ai_guard.assert_clean(prompt)           # 처음 훑기(캐시 채움)
        start = time.perf_counter()
        for _ in range(100):
            ai_guard.assert_clean(prompt)
        per_call = (time.perf_counter() - start) / 100
        self.assertLess(per_call, 0.25, f"호출당 {per_call * 1000:.1f}ms")
        with self.assertRaises(ai_guard.AiInputForbidden):
            ai_guard.assert_clean(prompt_with(f"가상 지역 {299:03d} 번 통계 값 {299 * 7 + 11}.{299 % 10}% 와 비교 보고서 제목"))

    def test_a_huge_prompt_with_thousands_of_fragments_stays_within_the_time_limit(self):
        rng = random.Random(7)
        fragments = {}
        while len(fragments) < 15000:
            fragments["".join(rng.choice("가나다라마바사아자차카타파하abcdefg0123456789") for _ in range(rng.randint(12, 40)))] = "post-title"
        filler = "관계 없는 평범한 문장입니다 숫자는 들어 있지 않습니다. " * 60000          # 약 3백만 자
        start = time.perf_counter()
        self.assertIsNone(ai_guard.find_hit(filler, fragments))
        elapsed_clean = time.perf_counter() - start
        planted = filler + " " + next(iter(fragments))
        start = time.perf_counter()
        self.assertEqual(ai_guard.find_hit(planted, fragments), "post-title")
        elapsed_hit = time.perf_counter() - start
        self.assertLess(elapsed_clean, 40, f"{elapsed_clean:.1f}s")
        self.assertLess(elapsed_hit, 40, f"{elapsed_hit:.1f}s")

    def test_a_thousand_marked_files_are_scanned_once_and_then_cheaply(self):
        for index in range(1000):
            write(self.root, f"_posts/천/2026-11-{index % 28 + 1:02d}-KR-{index:06d}.md",
                  post_text(f"가상 지역 {index:04d} 항목 통계 보고서 제목입니다 값 {index}", "경제", ["a"], f"가짜 설명 {index}", "https://example.invalid/d.png", marker=True))
        start = time.perf_counter()
        fragments = ai_guard.marked_fragments()
        cold = time.perf_counter() - start
        self.assertGreaterEqual(len(fragments), 1000)
        old_ns = time.time_ns() - 3600 * 10 ** 9
        for path in (self.root / "_posts").rglob("*.md"):
            os.utime(path, ns=(old_ns, old_ns))
        ai_guard.reset_cache()
        ai_guard.marked_fragments()                 # 오래된 파일로 다시 채운다
        start = time.perf_counter()
        for _ in range(20):
            ai_guard.marked_fragments()
        warm = (time.perf_counter() - start) / 20
        self.assertLess(cold, 60, f"{cold:.1f}s")
        self.assertLess(warm, 0.5, f"{warm * 1000:.0f}ms")


class RepoStateIndependenceTest(unittest.TestCase):
    """진짜 저장소(`ai_guard.CODE_ROOT`)에 표식 글이 있어도 RepoCase 바탕의 시험은 같은 결과를 낸다 — 첫 Fact 글이 승인 PR 로 올라온 날 이 시험들 때문에 검사가 빨개지지 않게(D-194).
    진짜 저장소의 `_posts`·`history.json` 사본에 표식 글 한 편과 표식 이력 항목 하나를 더한 폴더를 CODE_ROOT 로 두고, 방벽 시험 묶음을 그대로 한 번 더 돌린다."""

    CASES = ("FragmentsTest", "AssertCleanTest", "LimitsTest", "CacheFreshnessTest", "EntrancesTest")      # RepoCase 바탕의 방벽 시험(느린 PerformanceTest 는 뺀다)

    def make_marked_copy(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name).resolve()
        real = Path(ai_guard.CODE_ROOT)
        if (real / "_posts").is_dir():
            shutil.copytree(real / "_posts", root / "_posts")
        history = []
        if (real / "history.json").is_file():
            try:
                loaded = json.loads((real / "history.json").read_text(encoding="utf-8"))
                history = loaded if isinstance(loaded, list) else []
            except (OSError, ValueError):
                history = []
        write(root, FACT_POSTS[0]["rel"], fact_text(0))
        history.append(history_entry(FACT_POSTS[1]["title"], marker=True))
        write(root, "history.json", json.dumps(history, ensure_ascii=False, indent=2) + "\n")
        return root

    def test_the_planted_copy_really_has_marked_fragments(self):
        """대조: 심은 사본을 방벽이 훑으면 표식 글·표식 이력의 조각이 나온다(아래 시험이 '아무것도 심지 않아서 통과' 하는 것이 아님을 보인다)."""
        copy = self.make_marked_copy()
        ai_guard.reset_cache()
        self.addCleanup(ai_guard.reset_cache)
        fragments = ai_guard.marked_fragments([copy])
        self.assertIn(ai_guard.normalize(FACT_TITLE), fragments)
        self.assertIn(ai_guard.normalize(FACT_POSTS[1]["title"]), fragments)

    def test_repo_case_tests_do_not_depend_on_marked_posts_of_the_real_repository(self):
        copy = self.make_marked_copy()
        suite = unittest.TestSuite()
        for name in self.CASES:
            suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(globals()[name]))
        self.assertGreaterEqual(suite.countTestCases(), 30)
        stream = io.StringIO()
        with mock.patch.object(ai_guard, "CODE_ROOT", copy):
            result = unittest.TextTestRunner(stream=stream, verbosity=0).run(suite)
        self.assertTrue(result.wasSuccessful(), "진짜 저장소에 표식 글이 있을 때 방벽 시험이 실패한다 — RepoCase.setUp 이 CODE_ROOT 를 임시 폴더로 고정하는지 확인하세요:\n" + stream.getvalue()[-1500:])
        self.assertEqual(os.path.normcase(str(Path(ai_guard.CODE_ROOT).resolve())), os.path.normcase(str(Path(__file__).resolve().parent.parent)))      # 시험이 끝나면 CODE_ROOT 는 진짜 저장소로 돌아와 있다


class RepoCaseIsolationTest(RepoCase):
    def test_the_barrier_looks_only_at_the_temporary_folder_during_a_repo_case(self):
        self.assertEqual(Path(ai_guard.CODE_ROOT), self.root)
        self.assertEqual([os.path.normcase(str(root)) for root in ai_guard.default_roots()], [os.path.normcase(str(self.root))])


if __name__ == "__main__":
    unittest.main()
