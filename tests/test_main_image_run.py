"""Blogger 글 맨 위 대표 사진 — 러너(pipeline/run.py) 통합 시험.

임시 저장소(실제 레지스트리의 사본)에서 영문(blogger_macat)·한글(blogger_kcyoon) 두 블로그를 끝까지 돌린다. Blogger 는 가짜 게시자, Gemini 는 스텁 LLM(검색어 요청만 정해진 응답),
Unsplash 는 가짜 opener(`image_opener`)다 — 네트워크 호출이 없다. 실제 Unsplash·Blogger 호출은 한 번도 하지 않았다.

구성
  1) 붙이기: 글 HTML 이 사진 블록으로 시작하고 면책 문구가 맨 끝에 남는다, 이력 `image`·로그·실행 요약, 영문·한글(영어 검색어를 AI 에게 요청), 즉시 게시.
  2) 안 붙이는 길: 키 없음·연습 실행·저장소 파일만·초안 패키지·역할 없는 블로그 — Unsplash 를 부르지 않고 글은 예전과 바이트까지 같다.
  3) 실패해도 글은 그대로: Unsplash 오류·결과 없음·검사 탈락·예기치 않은 예외 — 종료 코드·상태·글 HTML 이 사진이 없는 실행과 같다.
  4) 이력: 최근 30개 항목의 사진은 다시 쓰지 않는다.
  5) 키: 로그·요약·이력·초안 사본·게시한 HTML·AI 프롬프트 어디에도 없다.
  6) 호출 기록·문서·워크플로: 검색어 요청이 Gemini 호출로 세어진다, 문서가 고정 코드를 모두 설명한다, 프롬프트는 그대로다.
"""
import html
import json
import random
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

import _bootstrap
from blogger_ko_helpers import EN, KO, KO_WORKFLOW_ENV, KoreanRunBase, ko_publisher, make_pair_root
from main_image_helpers import DEFAULT_QUERIES, KEY, FakeResponse, FakeUnsplash, QueryLLM, http_error, photo_item, results
from package_helpers import FakePackagePublisher, make_package_root, package_env
from package_helpers import NOW as PACKAGE_NOW
from pipeline import main_image, registry
from pipeline import run as run_mod
from pipeline.llm import LLMError, make_gemini_llm
from pipeline.publishers.base import PublishError
from pipeline.stubs import stub_llm
from test_run import NOW, WORKFLOW_ENV, FakePublisher

REAL = _bootstrap.ROOT
EN_PROFILE = json.loads((REAL / "pipeline" / "profiles" / "blogger_practical_en.json").read_text(encoding="utf-8"))
KO_PROFILE = json.loads((REAL / "pipeline" / "profiles" / "blogger_ai_tools_ko.json").read_text(encoding="utf-8"))
EN_KEY_ENV = {**WORKFLOW_ENV, "PIPELINE_SECRET_UNSPLASH_KEY": KEY}        # 워크플로가 러너에 넘기는 모양(래퍼가 UNSPLASH_ACCESS_KEY 를 역할 이름으로 넘긴다)
KO_KEY_ENV = {**KO_WORKFLOW_ENV, "PIPELINE_SECRET_UNSPLASH_KEY": KEY}
TWO = results(photo_item("Aaa111bbb22"), photo_item("Bbb222ccc33"))
HEADERS = {"X-Ratelimit-Remaining": "49", "X-Ratelimit-Limit": "50"}
BLOCK_START = '<div style="text-align:center;margin:0 0 1.5em;"><img src="https://images.unsplash.com/photo-'


class ImageRunBase(KoreanRunBase):
    """영문·한글 Blogger 가 모두 draft 인 임시 저장소(영문은 실제 영문 프로필·프롬프트, 한글은 실제 한글 프로필·프롬프트)."""
    MODE = "draft"
    EN_MODE = "draft"

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = make_pair_root(self._tmp.name, ko_mode="draft", en_mode=self.EN_MODE, en_lang="en")
        summary_dir = tempfile.TemporaryDirectory()                                       # 실행 요약은 저장소 밖에 둔다(연습 실행이 저장소에 아무것도 안 쓰는지 볼 때 섞이지 않게)
        self.addCleanup(summary_dir.cleanup)
        self.summary_file = Path(summary_dir.name) / "summary.md"

    def run_blog(self, blog=EN, env=None, llm=None, publisher=None, fake=None, extra=(), root=None, seed=1):
        """(종료 코드, 로그 전체, 가짜 게시자). env 에는 실행 요약 파일 경로를 더한다. fake 는 Unsplash opener(None 이면 러너가 진짜 urlopen 을 쓴다 — 키가 없는 시험에서만)."""
        out = []
        publisher = publisher if publisher is not None else (FakePublisher() if blog == EN else ko_publisher())
        env = {**(env if env is not None else (EN_KEY_ENV if blog == EN else KO_KEY_ENV)), "GITHUB_STEP_SUMMARY": str(self.summary_file)}
        if fake is None:
            fake = FakeUnsplash(results())                                    # 부르면 '결과 없음'이 된다. 부르지 말아야 하는 시험은 fake.calls 가 비어 있는지 본다
        code = run_mod.run(["--blog", blog, "--root", str(root or self.root), *extra], environ=env, now=NOW, llm=llm if llm is not None else QueryLLM(),
                           publisher_factory=lambda b, e: publisher, rng=random.Random(seed), out=out.append, image_opener=fake)
        return code, "\n".join(out), publisher

    def summary(self):
        return self.summary_file.read_text(encoding="utf-8") if self.summary_file.exists() else ""

    def english_history(self, root=None):
        return self.history("blogger_history.json", root=root)


class AttachTest(ImageRunBase):
    def test_an_english_draft_starts_with_the_photo_block_and_keeps_the_disclosure_last(self):
        fake = FakeUnsplash(TWO, headers=HEADERS)
        code, out, publisher = self.run_blog(EN, fake=fake)
        self.assertEqual(code, 0, out)
        sent = publisher.published[0]["html"]
        self.assertTrue(sent.startswith(BLOCK_START), sent[:200])
        block_end = sent.index("</div>") + len("</div>")
        self.assertEqual(sent[block_end], "\n")                                       # 블록과 글 사이는 줄바꿈 하나
        rest = sent[block_end + 1:]
        self.assertTrue(rest.startswith("<p>"), rest[:80])                            # 그 뒤가 모델이 쓴 글
        self.assertTrue(sent.rstrip().endswith(EN_PROFILE["disclosure_html"].strip()))   # 면책 문구는 그대로 맨 끝
        self.assertLess(sent.index("<img"), sent.index("<h3>"))
        self.assertLess(sent.index("<h3>"), sent.rindex(EN_PROFILE["disclosure_html"].strip()))
        self.assertEqual((sent.count("<img"), sent.count("<a "), sent.count("<div")), (1, 2, 1))
        for forbidden in ("<a ", "<img", "http", "<script"):
            self.assertNotIn(forbidden, rest, forbidden)                              # 모델이 쓴 글(과 면책 문구)에는 여전히 이미지·링크가 없다
        self.assertIs(publisher.published[0]["draft"], True)                          # 초안함 업로드

    def test_the_run_records_the_photo_in_the_history_the_log_the_summary_and_the_saved_copy(self):
        fake = FakeUnsplash(TWO, headers=HEADERS)
        code, out, publisher = self.run_blog(EN, fake=fake)
        self.assertEqual(code, 0, out)
        entry = self.english_history()[-1]
        self.assertEqual((entry["status"], entry["image"]), ("draft_uploaded", "Aaa111bbb22"))
        self.assertEqual(entry["reasons"], [])
        self.assertIn("[blogger_macat] 대표 사진: Aaa111bbb22 (Photo by Jane Doe)", out.splitlines())
        lines = self.summary().splitlines()
        self.assertIn("- 대표 사진: 있음 — Aaa111bbb22 (Photo by Jane Doe)", lines)
        self.assertIn("- Unsplash 남은 호출: 49회(시간당 한도 50회)", lines)
        saved = self.drafts("_blogger_drafts")[0].read_text(encoding="utf-8")
        self.assertIn(publisher.published[0]["html"], saved)                         # 저장소 사본은 올린 HTML 과 같다(사진 블록 포함)
        self.assertEqual((len(fake.searched), len(fake.pings)), (1, 1))

    def test_the_search_asks_the_llm_for_queries_and_uses_the_first_one(self):
        llm = QueryLLM(reply='{"image_queries": ["evening park walk", "city park", "sunset"]}')
        fake = FakeUnsplash(TWO)
        code, out, publisher = self.run_blog(EN, fake=fake, llm=llm)
        self.assertEqual(code, 0, out)
        self.assertEqual(fake.searched, ["evening park walk"])
        self.assertEqual(len(llm.prompts), 1)
        self.assertIn("[제목] " + publisher.published[0]["title"], llm.prompts[0])
        self.assertIn("[라벨] " + ", ".join(publisher.published[0]["labels"]), llm.prompts[0])

    def test_the_korean_blog_gets_a_photo_with_english_queries_from_the_llm_and_its_title_as_alt_text(self):
        llm = QueryLLM()
        fake = FakeUnsplash(results(photo_item("Aaa111bbb22", alt=None)), headers=HEADERS)
        code, out, publisher = self.run_blog(KO, fake=fake, llm=llm)
        self.assertEqual(code, 0, out)
        sent, title = publisher.published[0]["html"], publisher.published[0]["title"]
        self.assertTrue(sent.startswith(BLOCK_START))
        self.assertTrue(sent.rstrip().endswith(KO_PROFILE["disclosure_html"].strip()))
        self.assertEqual(len(llm.prompts), 1)
        for needle in ("영어 검색어", "반드시 영어로", title, "생활습관, 루틴, 일상"):
            self.assertIn(needle, llm.prompts[0])                                     # 한글 제목·라벨을 주고 영어 검색어를 요청했다
        self.assertEqual(fake.searched, ["morning coffee cup"])                       # 검색에는 AI 가 준 영어 검색어가 간다
        self.assertIn(f'alt="{html.escape(title, quote=True)}"', sent)                # 설명이 없는 사진은 글 제목이 alt
        self.assertIn("[blogger_kcyoon] 대표 사진: Aaa111bbb22 (Photo by Jane Doe)", out)
        self.assertEqual(self.history()[-1]["image"], "Aaa111bbb22")                  # 한글 이력 파일에 기록된다
        self.assertFalse((self.root / "blogger_history.json").exists())
        for forbidden in ("<a ", "<img", "http"):
            self.assertNotIn(forbidden, sent[sent.index("</div>"):], forbidden)

    def test_the_korean_blog_cannot_get_a_photo_without_english_queries(self):
        fake = FakeUnsplash(TWO)
        code, out, publisher = self.run_blog(KO, fake=fake, llm=QueryLLM(fail=LLMError("down")))
        self.assertEqual(code, 0, out)
        self.assertEqual(fake.calls, [])                                              # 한글 제목에서는 검색어를 만들 수 없다 — 검색하지 않는다
        self.assertIn("[IMAGE] 건너뜀: NO_QUERY", out)
        self.assertNotIn("<img", publisher.published[0]["html"])
        self.assertEqual(self.history()[-1]["status"], "draft_uploaded")
        self.assertIn("- 대표 사진: 없음(NO_QUERY)", self.summary())

    def test_an_english_blog_falls_back_to_its_title_and_labels_and_says_so_in_the_summary(self):
        fake = FakeUnsplash(TWO)
        code, out, publisher = self.run_blog(EN, fake=fake, llm=QueryLLM(fail=LLMError("down")))
        self.assertEqual(code, 0, out)
        expected = main_image.fallback_queries(publisher.published[0]["title"], publisher.published[0]["labels"])
        self.assertEqual(fake.searched, expected[:1])
        self.assertIn("검색어는 AI 응답이 아니라 제목·라벨로 만들었습니다", self.summary())
        self.assertTrue(publisher.published[0]["html"].startswith(BLOCK_START))

    def test_mode_auto_posts_live_with_the_photo_too(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_pair_root(tmp, ko_mode="draft", en_mode="auto", en_lang="en")
            code, out, publisher = self.run_blog(EN, fake=FakeUnsplash(TWO), root=root)
            self.assertEqual(code, 0, out)
            self.assertIs(publisher.published[0]["draft"], False)
            self.assertTrue(publisher.published[0]["html"].startswith(BLOCK_START))
            entry = json.loads((root / "blogger_history.json").read_text(encoding="utf-8"))[-1]
            self.assertEqual((entry["status"], entry["image"]), ("posted", "Aaa111bbb22"))

    def test_without_an_injected_opener_the_runner_uses_urllib_urlopen(self):
        """`image_opener` 를 주지 않는 실제 실행은 urllib.request.urlopen 을 쓴다 — 시험은 그 함수를 가짜로 바꿔 연결만 확인한다(진짜 호출 없음)."""
        fake, out = FakeUnsplash(TWO), []
        with mock.patch("urllib.request.urlopen", fake):
            code = run_mod.run(["--blog", EN, "--root", str(self.root)], environ=dict(EN_KEY_ENV), now=NOW, llm=QueryLLM(),
                               publisher_factory=lambda b, e: FakePublisher(), rng=random.Random(1), out=out.append)
        self.assertEqual(code, 0, "\n".join(out))
        self.assertEqual(len(fake.searched), 1)
        self.assertEqual(self.english_history()[-1]["image"], "Aaa111bbb22")

    def test_the_local_secret_name_works_like_the_workflow_role_name(self):
        env = {**WORKFLOW_ENV, "UNSPLASH_ACCESS_KEY": KEY}                            # 로컬 실행: 레지스트리에 적힌 이름
        fake = FakeUnsplash(TWO)
        code, out, publisher = self.run_blog(EN, env=env, fake=fake)
        self.assertEqual(code, 0, out)
        self.assertEqual(len(fake.searched), 1)
        self.assertTrue(publisher.published[0]["html"].startswith(BLOCK_START))

    def test_the_photo_is_added_after_the_gate_so_a_post_the_gate_rejects_never_reaches_unsplash(self):
        fake, llm = FakeUnsplash(TWO), QueryLLM(inner=lambda prompt: ("제목: 충분히 긴 제목입니다 정말로\n라벨: 가\n내용:\n<p>너무 짧음</p>", "m"))
        code, out, publisher = self.run_blog(EN, fake=fake, llm=llm)
        self.assertEqual((code, publisher.published, fake.calls, llm.prompts), (0, [], [], []))
        self.assertEqual(self.english_history()[-1]["status"], "rejected")

    def test_even_a_bug_in_the_photo_step_cannot_stop_the_post(self):
        """main_image 는 예외를 올리지 않지만, 러너 쪽 조립에서 예외가 나도 글은 사진 없이 올라가고 종료 코드·상태는 그대로다(클래스 이름만 로그에 남는다)."""
        with mock.patch.object(main_image, "find_main_image", side_effect=RuntimeError(f"boom {KEY}")):
            code, out, publisher = self.run_blog(EN, fake=FakeUnsplash(TWO))
        self.assertEqual(code, 0, out)
        self.assertEqual(len(publisher.published), 1)
        self.assertNotIn("<img", publisher.published[0]["html"])
        self.assertIn("[IMAGE] 건너뜀: UNEXPECTED(RuntimeError)", out.splitlines())
        self.assertIn("- 대표 사진: 없음(UNEXPECTED(RuntimeError))", self.summary().splitlines())
        self.assertEqual(self.english_history()[-1]["status"], "draft_uploaded")
        self.assertNotIn("image", self.english_history()[-1])
        self.assertNotIn(KEY, out + self.summary())

    def test_a_publish_failure_with_a_photo_keeps_the_same_exit_code_and_still_records_the_photo(self):
        publisher = FakePublisher(fail=PublishError("서버 오류", code="api_error"))
        code, out, _ = self.run_blog(EN, fake=FakeUnsplash(TWO), publisher=publisher)
        entry = self.english_history()[-1]
        self.assertEqual((code, entry["status"], entry["image"]), (1, "publish_failed", "Aaa111bbb22"))
        self.assertIn("- 대표 사진: 있음", self.summary())
        baseline = FakePublisher(fail=PublishError("서버 오류", code="api_error"))
        with tempfile.TemporaryDirectory() as tmp:
            root = make_pair_root(tmp, ko_mode="draft", en_mode="draft", en_lang="en")
            base_code, _out, _ = self.run_blog(EN, env=WORKFLOW_ENV, publisher=baseline, root=root)
            self.assertEqual((base_code, json.loads((root / "blogger_history.json").read_text(encoding="utf-8"))[-1]["status"]), (1, "publish_failed"))


class NoPhotoPathsTest(ImageRunBase):
    """사진을 붙이지 않는 길: Unsplash 를 부르지 않고(opener·AI 검색어 요청 0회), 글은 사진 단계가 없던 때와 같다."""

    def baseline(self, blog=EN):
        """키가 없는 실행의 결과(= 사진 단계가 없던 때와 글이 같다): (종료 코드, 올린 글 하나, 이력 마지막 항목)."""
        with tempfile.TemporaryDirectory() as tmp:
            root = make_pair_root(tmp, ko_mode="draft", en_mode="draft", en_lang="en")
            code, _out, publisher = self.run_blog(blog, env=WORKFLOW_ENV if blog == EN else KO_WORKFLOW_ENV, root=root)
            name = "blogger_history.json" if blog == EN else "blogger_ko_history.json"
            return code, publisher.published[0], json.loads((root / name).read_text(encoding="utf-8"))[-1]

    def test_without_a_key_the_post_goes_up_text_only_with_one_notice_and_no_call(self):
        fake, llm = FakeUnsplash(TWO), QueryLLM()
        code, out, publisher = self.run_blog(EN, env=WORKFLOW_ENV, fake=fake, llm=llm)
        self.assertEqual(code, 0, out)
        self.assertEqual((fake.calls, llm.prompts), ([], []))
        sent = publisher.published[0]["html"]
        self.assertTrue(sent.startswith("<p>"))
        self.assertNotIn("<img", sent)
        self.assertEqual([line for line in out.splitlines() if "[IMAGE]" in line], ["[IMAGE] 건너뜀: NO_KEY"])
        self.assertEqual([line for line in out.splitlines() if line.startswith("::")], [])     # 독립 검증 F3(c): 키 없음은 경고도 알림 주석도 만들지 않는다(같은 줄이 매 실행 남는 설정 상태 — 사진도 주석도 없으면 NO_KEY)
        self.assertNotIn("image", self.english_history()[-1])
        self.assertIn("- 대표 사진: 없음(NO_KEY)", self.summary().splitlines())
        self.assertEqual(self.english_history()[-1]["status"], "draft_uploaded")

    def test_a_dry_run_never_calls_unsplash_or_asks_for_queries_and_writes_nothing(self):
        fake, llm = FakeUnsplash(TWO), QueryLLM()
        before = {path for path in self.root.rglob("*")}
        code, out, publisher = self.run_blog(EN, fake=fake, llm=llm, extra=["--dry-run"])
        self.assertEqual(code, 0, out)
        self.assertEqual((fake.calls, llm.prompts, publisher.published), ([], [], []))
        self.assertIn("[DRY_RUN] 대표 사진 단계는 건너뜁니다(외부 호출 없음)", out.splitlines())
        self.assertNotIn("[IMAGE]", out)
        self.assertEqual({path for path in self.root.rglob("*")}, before)

    def test_the_dry_run_line_is_the_only_new_line_of_a_blogger_dry_run(self):
        env = {**WORKFLOW_ENV, "DRY_RUN": "1"}
        _code, with_role, _ = self.run_blog(EN, env=env, extra=["--dry-run"])
        lines = with_role.splitlines()
        self.assertEqual(sum("대표 사진" in line for line in lines), 1)
        self.assertEqual(lines.index("[DRY_RUN] 대표 사진 단계는 건너뜁니다(외부 호출 없음)") + 1, next(i for i, line in enumerate(lines) if line.startswith("[DRY_RUN] 게이트 통과")))

    def test_saving_only_to_the_repository_never_calls_unsplash(self):
        fake, llm = FakeUnsplash(TWO), QueryLLM()
        code, out, publisher = self.run_blog(EN, env={**EN_KEY_ENV, "BLOGGER_PUBLISH": "off"}, fake=fake, llm=llm)
        self.assertEqual(code, 0, out)
        self.assertEqual((fake.calls, llm.prompts, publisher.published), ([], [], []))
        self.assertNotIn("[IMAGE]", out)
        self.assertNotIn("대표 사진", out + self.summary())
        self.assertNotIn("<img", self.drafts("_blogger_drafts")[0].read_text(encoding="utf-8"))
        self.assertEqual(self.english_history()[-1]["status"], "draft")

    def test_a_blog_without_the_unsplash_role_has_the_feature_off_with_no_line_anywhere(self):
        path = self.root / "pipeline" / "blogs.json"
        reg = json.loads(path.read_text(encoding="utf-8"))
        for blog in reg["blogs"]:
            if blog["platform"] == "blogger":
                blog["secrets"].pop("unsplash_key")
        path.write_text(json.dumps(reg, ensure_ascii=False), encoding="utf-8")
        self.assertEqual(registry.validate_registry(registry.load_registry(path), self.root), [])
        fake, llm = FakeUnsplash(TWO), QueryLLM()
        code, out, publisher = self.run_blog(EN, fake=fake, llm=llm)                  # 환경에 키가 있어도
        self.assertEqual(code, 0, out)
        self.assertEqual((fake.calls, llm.prompts), ([], []))
        self.assertNotIn("[IMAGE]", out)
        self.assertNotIn("대표 사진", out + self.summary())
        self.assertNotIn("<img", publisher.published[0]["html"])
        _code, dry_out, _ = self.run_blog(EN, fake=fake, llm=llm, extra=["--dry-run"], root=self.root)
        self.assertNotIn("대표 사진", dry_out)                                         # 연습 실행에도 줄이 없다
        code_base, post_base, _entry = self.baseline()
        self.assertEqual((code, publisher.published[0]["html"]), (code_base, post_base["html"]))

    def test_a_draft_package_run_is_byte_for_byte_the_same_with_or_without_the_unsplash_machinery(self):
        spy = FakeUnsplash(TWO)
        results_by_variant = []
        for extra in ((), ("--dry-run",)):
            runs = []
            for with_key in (False, True):
                with tempfile.TemporaryDirectory() as tmp:
                    root = make_package_root(Path(tmp) / "repo")
                    summary = Path(tmp) / "summary.md"
                    env = {"GITHUB_STEP_SUMMARY": str(summary), **package_env(**({"PIPELINE_SECRET_UNSPLASH_KEY": KEY, "UNSPLASH_ACCESS_KEY": KEY} if with_key else {}))}
                    out = []
                    code = run_mod.run(["--blog", "tistory_test", "--root", str(root), *extra], environ=env, now=PACKAGE_NOW, llm=stub_llm,
                                       publisher_factory=lambda blog, environ: FakePackagePublisher(), rng=random.Random(1), out=out.append,
                                       image_opener=spy if with_key else None)
                    files = {str(path.relative_to(root)): path.read_bytes() for path in sorted(root.rglob("*")) if path.is_file() and path.name != "summary.md"}
                    runs.append((code, "\n".join(out), summary.read_text(encoding="utf-8") if summary.exists() else "", files))
            self.assertEqual(runs[0], runs[1], extra)                                  # 키 환경변수와 가짜 opener 가 있어도 출력·요약·이력·초안 사본이 같다
            self.assertNotIn("대표 사진", runs[1][1] + runs[1][2])
            self.assertNotIn("[IMAGE]", runs[1][1])
            results_by_variant.append(runs[1][0])
        self.assertEqual(spy.calls, [])
        self.assertEqual(results_by_variant, [0, 0])


class FailureParityTest(ImageRunBase):
    """Unsplash 쪽의 어떤 문제도 종료 코드·이력 상태·올라가는 글을 바꾸지 못한다(사진이 없을 뿐이다)."""

    SCENARIOS = (
        ("HTTP_403", http_error(403)), ("HTTP_429", http_error(429)), ("HTTP_5XX", http_error(500)), ("HTTP_401", http_error(401)),
        ("TIMEOUT", TimeoutError("timed out")), ("NETWORK", OSError("down")), ("BAD_JSON", FakeResponse(b"<html>")), ("BAD_RESPONSE", FakeResponse(b"[]")),
        ("NO_RESULT", results()), ("UNSAFE_URL", results(photo_item("Bad111aaa11", raw="https://evil.example/photo-1"))),
        ("UNEXPECTED", RuntimeError(f"boom {KEY}")),
    )

    def outcome(self, blog, scenario, env):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_pair_root(tmp, ko_mode="draft", en_mode="draft", en_lang="en")
            fake = FakeUnsplash(scenario)
            code, out, publisher = self.run_blog(blog, env=env, fake=fake, root=root)
            name = "blogger_history.json" if blog == EN else "blogger_ko_history.json"
            entry = json.loads((root / name).read_text(encoding="utf-8"))[-1]
            return code, out, publisher.published, entry, fake

    def test_english_failures_leave_the_exit_code_the_status_the_entry_and_the_html_unchanged(self):
        base_code, _out, base_published, base_entry, _fake = self.outcome(EN, FakeUnsplash(results()), WORKFLOW_ENV)
        for code_name, scenario in self.SCENARIOS:
            code, out, published, entry, fake = self.outcome(EN, scenario, EN_KEY_ENV)
            self.assertEqual(code, base_code, code_name)
            self.assertEqual(published, base_published, code_name)                    # 올라간 글이 키 없는 실행과 같다(사진 없음)
            self.assertEqual(entry, base_entry, code_name)                            # 이력 항목도 같다(`image` 칸 없음)
            expected_line = "[IMAGE] 건너뜀: UNEXPECTED(RuntimeError)" if code_name == "UNEXPECTED" else f"[IMAGE] 건너뜀: {code_name}"
            self.assertEqual([line for line in out.splitlines() if "[IMAGE]" in line], [expected_line], code_name)
            self.assertNotIn(KEY, out, code_name)
            self.assertEqual(len([call for call in fake.calls if call["path"] == "/search/photos"]), 1 if code_name != "NO_RESULT" and code_name != "UNSAFE_URL" else 3, code_name)

    def test_korean_failures_are_the_same(self):
        base_code, _out, base_published, base_entry, _fake = self.outcome(KO, FakeUnsplash(results()), KO_WORKFLOW_ENV)
        for code_name, scenario in self.SCENARIOS:
            code, _out, published, entry, _fake = self.outcome(KO, scenario, KO_KEY_ENV)
            self.assertEqual((code, published, entry), (base_code, base_published, base_entry), code_name)

    def test_the_summary_names_the_reason_and_the_hourly_limit_when_unsplash_told_us(self):
        fake = FakeUnsplash(http_error(429, HEADERS | {"X-Ratelimit-Remaining": "0"}))
        code, out, _publisher = self.run_blog(EN, fake=fake)
        self.assertEqual(code, 0, out)
        lines = self.summary().splitlines()
        self.assertIn("- 대표 사진: 없음(HTTP_429)", lines)
        self.assertIn("- Unsplash 남은 호출: 0회(시간당 한도 50회)", lines)

    def test_no_image_failure_makes_a_warning_or_an_error_annotation_only_one_fixed_notice(self):
        for _name, scenario in self.SCENARIOS:
            _code, out, _published, _entry, _fake = self.outcome(EN, scenario, EN_KEY_ENV)
            marks = [line for line in out.splitlines() if line.startswith("::")]
            self.assertEqual(len(marks), 1, (_name, marks))     # 읽기 쉬운 ::notice:: 한 줄뿐(독립 검증 F4) — AI 가 공개 주석 API 로 이유를 읽는다
            self.assertRegex(marks[0], r"^::notice::\[blogger_macat\] 대표 사진 없이 올립니다\([A-Z0-9_]+(\([A-Za-z0-9_]+\))?\)$", _name)     # ::warning::·::error:: 가 아니다 — 실행은 초록 그대로    # 주석(::error::·::warning::)이 없다 — 실행은 초록 그대로


class HistoryTest(ImageRunBase):
    def seed_history(self, entries):
        (self.root / "blogger_history.json").write_text(json.dumps(entries, ensure_ascii=False), encoding="utf-8")

    @staticmethod
    def filler(count):
        return [{"v": 1, "blog": "blogger_macat", "date": "2026-09-01", "status": "skipped_no_topic", "topic": "", "reasons": ["[TOPIC] x"]} for _ in range(count)]

    def test_a_photo_used_by_one_of_the_last_thirty_entries_is_skipped(self):
        self.seed_history([{"v": 1, "blog": "blogger_macat", "date": "2026-10-20", "status": "draft_uploaded", "topic": "", "image": "Aaa111bbb22"}] + self.filler(28))
        fake = FakeUnsplash(TWO)
        self.run_blog(EN, fake=fake)
        self.assertEqual(self.english_history()[-1]["image"], "Bbb222ccc33")

    def test_a_photo_older_than_the_last_thirty_entries_may_come_back(self):
        self.seed_history([{"v": 1, "blog": "blogger_macat", "date": "2026-10-20", "status": "draft_uploaded", "topic": "", "image": "Aaa111bbb22"}] + self.filler(30))
        self.run_blog(EN, fake=FakeUnsplash(TWO))
        self.assertEqual(self.english_history()[-1]["image"], "Aaa111bbb22")

    def test_the_other_blogs_history_does_not_count(self):
        (self.root / "blogger_ko_history.json").write_text(json.dumps([{"v": 1, "blog": "blogger_kcyoon", "date": "2026-10-20", "status": "draft_uploaded", "topic": "", "image": "Aaa111bbb22"}]),
                                                          encoding="utf-8")
        self.run_blog(EN, fake=FakeUnsplash(TWO))
        self.assertEqual(self.english_history()[-1]["image"], "Aaa111bbb22")

    def test_two_days_in_a_row_never_use_the_same_photo(self):
        from datetime import datetime, timezone
        fake = FakeUnsplash(TWO)
        self.run_blog(EN, fake=fake)
        out = []
        later = datetime(2026, 10, 22, 2, 0, tzinfo=timezone.utc)
        env = {**EN_KEY_ENV, "GITHUB_STEP_SUMMARY": str(self.summary_file)}
        code = run_mod.run(["--blog", EN, "--root", str(self.root)], environ=env, now=later, llm=QueryLLM(), publisher_factory=lambda b, e: FakePublisher(),
                           rng=random.Random(2), out=out.append, image_opener=fake)
        self.assertEqual(code, 0, "\n".join(out))
        self.assertEqual([entry["image"] for entry in self.english_history()], ["Aaa111bbb22", "Bbb222ccc33"])

    def test_when_every_candidate_was_used_recently_there_is_no_photo_and_no_stand_in(self):
        self.seed_history([{"v": 1, "blog": "blogger_macat", "date": "2026-10-20", "status": "draft_uploaded", "topic": "", "image": "Aaa111bbb22"},
                           {"v": 1, "blog": "blogger_macat", "date": "2026-10-19", "status": "draft_uploaded", "topic": "", "image": "Bbb222ccc33"}])
        code, out, publisher = self.run_blog(EN, fake=FakeUnsplash(TWO))
        self.assertEqual(code, 0, out)
        self.assertIn("[IMAGE] 건너뜀: NO_RESULT", out)
        self.assertNotIn("<img", publisher.published[0]["html"])
        self.assertNotIn("image", self.english_history()[-1])


class KeyNeverLeaksTest(ImageRunBase):
    SCENARIOS = (results(photo_item("Aaa111bbb22")), results(), http_error(403), TimeoutError("t"), RuntimeError(f"leak {KEY}"), FakeResponse(b"nope"),
                 results(photo_item("Aaa111bbb22", name=KEY)), results(photo_item("Aaa111bbb22", alt=f"alt {KEY} alt")))

    def everything(self, blog, scenario, env):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_pair_root(tmp, ko_mode="draft", en_mode="draft", en_lang="en")
            llm = QueryLLM()
            code, out, publisher = self.run_blog(blog, env=env, fake=FakeUnsplash(scenario), llm=llm, root=root)
            texts = [out, self.summary(), json.dumps(publisher.published, ensure_ascii=False), "\n".join(llm.all_prompts)]
            texts += [path.read_text(encoding="utf-8") for path in sorted(root.rglob("*")) if path.is_file() and path.suffix in (".json", ".md")
                      and path.name != "blogs.json" and not path.is_relative_to(root / ".github")]
            return code, texts

    def test_the_key_is_in_no_log_summary_history_saved_copy_published_html_or_prompt(self):
        for blog, env in ((EN, EN_KEY_ENV), (KO, KO_KEY_ENV), (EN, {**WORKFLOW_ENV, "UNSPLASH_ACCESS_KEY": KEY})):
            for scenario in self.SCENARIOS:
                code, texts = self.everything(blog, scenario, env)
                self.assertEqual(code, 0)
                for text in texts:
                    self.assertNotIn(KEY, text, (blog, repr(scenario)[:60]))

    def test_the_key_is_one_of_the_values_the_runner_redacts(self):
        blog = registry.get_blog(registry.load_registry(REAL / "pipeline" / "blogs.json"), EN)
        self.assertIn(KEY, run_mod._secret_values(blog, EN_KEY_ENV))
        self.assertIn(KEY, run_mod._secret_values(blog, {"UNSPLASH_ACCESS_KEY": KEY}))
        self.assertEqual(run_mod.redact(f"x {KEY} y", run_mod._secret_values(blog, EN_KEY_ENV)), "x *** y")

    def test_the_optional_key_never_counts_as_a_missing_publishing_secret(self):
        blog = registry.get_blog(registry.load_registry(REAL / "pipeline" / "blogs.json"), EN)
        self.assertEqual(registry.missing_secret_roles(blog, WORKFLOW_ENV), [])
        self.assertNotIn("unsplash_key", run_mod.PUBLISH_ROLES)
        self.assertEqual(registry.PLATFORMS["blogger"]["optional_secrets"], ["unsplash_key"])
        code, out, publisher = self.run_blog(EN, env=WORKFLOW_ENV)                    # 키가 없어도 게시용 시크릿 점검(종료 2)에 걸리지 않는다
        self.assertEqual((code, len(publisher.published)), (0, 1), out)
        self.assertNotIn("SECRETS_MISSING", out)

    def test_an_invisible_character_in_the_key_is_cleaned_and_announced_by_name_only(self):
        code, out, publisher = self.run_blog(EN, env={**WORKFLOW_ENV, "PIPELINE_SECRET_UNSPLASH_KEY": "​" + KEY + "⁠"}, fake=FakeUnsplash(TWO))
        self.assertEqual(code, 0, out)
        self.assertIn("UNSPLASH_ACCESS_KEY", [line for line in out.splitlines() if line.startswith("::notice::") and "보이지 않는 문자" in line][0])
        self.assertTrue(publisher.published[0]["html"].startswith(BLOCK_START))       # 지운 값으로 호출했다
        self.assertNotIn(KEY, out)


class GeminiCallLogTest(ImageRunBase):
    def test_the_query_request_is_counted_as_one_more_gemini_call_with_its_own_purpose(self):
        class Client:
            def __init__(self):
                self.prompts, self.models = [], self

            def generate_content(self, model, contents):
                self.prompts.append(contents)
                text = DEFAULT_QUERIES if "image_queries" in contents else stub_llm(contents)[0]
                return types.SimpleNamespace(text=text, usage_metadata=None, candidates=None, model_version=None)
        client = Client()
        llm = make_gemini_llm("gemini-fake-" + "key-0000000000", ["fake-model"], 0, sleep=lambda seconds: None, client_factory=lambda: client)
        code, out, publisher = self.run_blog(EN, llm=llm, fake=FakeUnsplash(TWO))
        self.assertEqual(code, 0, out)
        self.assertTrue(publisher.published[0]["html"].startswith(BLOCK_START))
        self.assertEqual(len(client.prompts), 2)                                       # 글 1회 + 검색어 1회
        lines = self.summary().splitlines()
        self.assertIn("- Gemini 호출: 2회(실패 0회)", lines)
        self.assertIn("- Gemini 용도별 호출: generate 1회 · image-queries 1회", lines)
        self.assertLess(lines.index("- 대표 사진: 있음 — Aaa111bbb22 (Photo by Jane Doe)"), lines.index("- Gemini 호출: 2회(실패 0회)"))     # 사진 줄은 Gemini 호출 줄 앞이다
        self.assertEqual(len([line for line in out.splitlines() if line.startswith("[GEMINI]") and "purpose=image-queries" in line]), 1)


class DocsAndWorkflowTest(unittest.TestCase):
    """운영자·AI 문서가 이 기능을 실제 코드와 같게 설명하는지, 모델에게 가는 글이 그대로인지."""

    def read(self, rel):
        return (REAL / rel).read_text(encoding="utf-8")

    def test_the_model_prompt_does_not_mention_the_photo_step_because_the_pipeline_adds_it_after_the_gate(self):
        for key in (EN, KO, "blogger_macat"):
            blog = registry.get_blog(registry.load_registry(REAL / "pipeline" / "blogs.json"), key)
            template = run_mod.load_prompt_template(REAL, blog)
            profile = registry.load_profile(blog["profile"])
            prompt = run_mod.build_prompt(template, "topic", profile)
            for needle in ("Unsplash", "대표 사진", "main photo", "pipeline/main_image", "image_queries"):
                self.assertNotIn(needle, prompt, (key, needle))
            self.assertFalse(profile["allow_links"])

    def test_the_prompt_documents_and_profiles_carry_a_note_that_the_pipeline_adds_the_photo(self):
        for rel in (".github/editorial/BLOGGER_PROMPT.md", ".github/editorial/BLOGGER_PROMPT_EN.md", ".github/editorial/BLOGGER_PROMPT_KO_AI.md"):
            text = self.read(rel)
            before_block = text.split("```text", 1)[0]
            self.assertIn("대표 사진", before_block, rel)                                # 안내는 모델에게 가는 코드 블록 바깥에 있다
            self.assertIn("pipeline/main_image.py", before_block, rel)
        for name in ("blogger_practical_ko", "blogger_practical_en", "blogger_ai_tools_ko"):
            doc = json.loads(self.read(f"pipeline/profiles/{name}.json"))["_doc"]
            self.assertIn("대표 사진", doc, name)
            self.assertIn("pipeline/main_image.py", doc, name)

    def test_the_actions_guide_explains_every_reason_code_the_log_can_show(self):
        text = self.read("docs/ACTIONS_GUIDE.md")
        for code in main_image.REASONS:
            self.assertIn(f"`{code}`", text, code)
        for needle in ("[IMAGE] 건너뜀", "대표 사진: 있음", "대표 사진: 없음", "UNSPLASH_ACCESS_KEY"):
            self.assertIn(needle, text, needle)

    def test_the_architecture_doc_describes_the_flow_the_secret_role_and_how_to_turn_it_off(self):
        text = self.read("docs/ARCHITECTURE.md")
        section = text[text.index("## 4-7. "):text.index("## 5. 상태·멱등성·동시성")]
        for needle in ("pipeline/main_image.py", "unsplash_key", "PIPELINE_SECRET_UNSPLASH_KEY", "images.unsplash.com", "api.unsplash.com", "download_location", "image_queries",
                       "REG-6", "IMAGE_POOL", "[IMAGE] 건너뜀", "끄려면", "allow_links", "30개"):
            self.assertIn(needle, section, needle)
        for code in main_image.REASONS:
            self.assertIn(f"`{code}`", section, code)                               # 고정 코드 15개가 모두 적혀 있다
        self.assertIn("시크릿 8개(선택", text)                                         # 공용 워크플로 행: 역할 이름 6 + 텔레그램 2
        self.assertNotIn("시크릿 7개(선택)", text)

    def test_the_security_doc_extends_the_licensed_image_rule_to_blogger(self):
        row = next(line for line in self.read("docs/SECURITY_GUARDRAILS.md").splitlines() if line.startswith("| G-C7 |"))
        for needle in ("Blogger", "pipeline/main_image.py", "download", "출처", "PIPELINE_SECRET_UNSPLASH_KEY"):
            self.assertIn(needle, row, needle)

    def test_the_work_log_and_the_handover_documents_record_the_photo_step_and_its_grade(self):
        worklog = self.read("WORKLOG.md")
        entry = worklog[worklog.index("## [2026-10-29] Claude – Blogger 글 맨 위 대표 사진"):worklog.index("## [2026-10-29] Claude – Blogger 한글·영문 켜기")]
        self.assertIn("T2", entry)
        self.assertIn("워크플로 시크릿 전달", entry)                                    # 등급 설명: 코드 기능이지만 워크플로의 시크릿 경로가 바뀌었다
        self.assertIn("pipeline/main_image.py", entry)
        handover = self.read("인수인계/작업내용.md")
        self.assertGreaterEqual(handover.count("Blogger 대표 사진"), 2)               # §1 한 줄 + §2 한 행
        self.assertIn("pipeline/main_image.py", self.read("HANDLER.md"))

    def test_the_workflows_pass_the_optional_key_by_name_and_never_inherit(self):
        reusable = self.read(".github/workflows/blogger.yml")
        self.assertEqual(reusable.count("PIPELINE_SECRET_UNSPLASH_KEY:"), 2)           # workflow_call.secrets 정의 + 러너 단계 env
        self.assertIn("PIPELINE_SECRET_UNSPLASH_KEY: ${{ secrets.PIPELINE_SECRET_UNSPLASH_KEY }}", reusable)
        for wrapper in ("blogger-en.yml", "blogger-ko.yml"):
            text = self.read(f".github/workflows/{wrapper}")
            self.assertIn("PIPELINE_SECRET_UNSPLASH_KEY: ${{ secrets.UNSPLASH_ACCESS_KEY }}", text, wrapper)
            self.assertNotIn("secrets: inherit", "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#")), wrapper)


if __name__ == "__main__":
    unittest.main()
