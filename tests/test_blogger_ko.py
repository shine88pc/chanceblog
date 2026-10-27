"""한글 Blogger(kcyoon, 레지스트리 키 blogger_kcyoon) 러너 흐름 시험(작업 D).

영문 Blogger 와 같은 러너(pipeline.run)가 레지스트리 값만 바꿔 읽어 한글 블로그를 돌린다는 것을 임시 저장소에서 끝까지 돌려 확인한다.
실제 레지스트리의 한글 블로그는 mode: off 라 운영자가 켜기 전에는 아무 일도 일어나지 않는다 — 이 시험이 mode 를 draft·auto 로 바꾸는 것은 임시 저장소 사본에서뿐이다.
시크릿 값은 가짜이고, Blogger·Gemini 는 가짜 게시자·스텁 LLM 으로 대신한다(실제 호출 없음).

구성
  1) 초안함 흐름: 한글 시크릿으로 한글 블로그 초안함에 올리고 한글 전용 파일에만 쓴다. 요약 머리·AI 고지·링크 없음·시드 주제.
  2) 시크릿: 영문 시크릿 이름은 한글 블로그를 켜지 못하고, 일부만 있으면 글을 만들기 전에 멈추며 한글 이름만 안내한다.
  3) 정지·점검: mode off 는 아무것도 쓰지 않고, 인증 점검만은 정지 중에도 한다. 연습 실행은 쓰기가 없다.
  4) 게이트: 한글 프로필의 금지 표현이 러너에서 글을 막는다(올리지도 저장하지도 않는다).
  5) 교차 중복: 영문→한글, 한글→영문 양쪽에서 다른 블로그 이력의 주제를 피한다.
  6) 영문 불간섭: 한글 실행이 영문 이력·초안·시크릿 이름을 건드리지 않고, 그 반대도 같다.
"""
import json
import tempfile
import unittest
from pathlib import Path

import yaml

import _bootstrap
from blogger_ko_helpers import (EN, EN_ENV, EN_NAMES, EN_VALUES, GEMINI, KO, KO_ENV, KO_NAMES, KO_URL, KO_VALUES, KO_WORKFLOW_ENV, KoreanRunBase,
                                ko_publisher, make_pair_root)
from pipeline import registry
from pipeline.publishers.base import PublishError
from pipeline.stubs import stub_llm
from test_run import FakePublisher

REAL = _bootstrap.ROOT
PROFILE = json.loads((REAL / "pipeline" / "profiles" / "blogger_ai_tools_ko.json").read_text(encoding="utf-8"))
SEEDS = PROFILE["seed_topics"]
ALL_ROLES = ("llm_api_key", "blog_id", "client_id", "client_secret", "refresh_token")


def llm_with(sentence):
    """스텁 글의 첫 문단 끝에 문장 하나를 붙여 돌려주는 LLM(게이트가 그 문장을 막는지 본다)."""
    def llm(prompt):
        text, model = stub_llm(prompt)
        if "JSON 문자열 배열" in prompt:
            return text, model
        return text.replace("</p>", f" {sentence}</p>", 1), model
    return llm


class CountingLLM:
    def __init__(self, inner=stub_llm):
        self.inner, self.calls = inner, 0

    def __call__(self, prompt):
        self.calls += 1
        return self.inner(prompt)


class DraftFlowTest(KoreanRunBase):
    MODE = "draft"

    def test_the_korean_blog_uploads_its_draft_to_the_korean_draft_box_and_keeps_its_own_files(self):
        publisher = ko_publisher()
        code, out = self.go(env=KO_WORKFLOW_ENV, publisher=publisher)
        self.assertEqual(code, 0, out)
        self.assertEqual(publisher.health_calls, 1)                                             # 글을 만들기 전에 인증 점검 한 번
        self.assertEqual(len(publisher.published), 1)
        self.assertIs(publisher.published[0]["draft"], True)                                    # 초안함(공개되지 않음)
        entry = self.history()[-1]
        self.assertEqual((entry["blog"], entry["status"], entry["post_id"], entry["date"], entry["v"]), (KO, "draft_uploaded", "ko1", "2026-10-21", 1))
        self.assertTrue(entry["url"].startswith(KO_URL), entry)                                  # 주소는 한글 블로그의 것
        self.assertEqual(len(self.drafts()), 1)                                                  # _blogger_ko_drafts/ 에 사본 한 개
        self.assertIn("status: draft_uploaded", self.drafts()[0].read_text(encoding="utf-8"))
        self.assertFalse((self.root / "blogger_history.json").exists())                          # 영문 이력·초안 폴더는 만들어지지도 않는다
        self.assertFalse((self.root / "_blogger_drafts").exists())

    def test_the_local_secret_names_work_like_the_workflow_role_names(self):
        """로컬에서 `export BLOGGER_KO_*` 로 돌려도, 워크플로가 넘기는 PIPELINE_SECRET_<역할> 로 돌려도 같은 결과다."""
        results = []
        for env in (KO_WORKFLOW_ENV, KO_ENV):
            with tempfile.TemporaryDirectory() as tmp:
                root = make_pair_root(tmp, ko_mode="draft")
                publisher = ko_publisher()
                code, _out = self.go(env=env, publisher=publisher, root=root)
                results.append((code, [(p["draft"], p["title"]) for p in publisher.published], [e["status"] for e in self.history(root=root)]))
        self.assertEqual(results[0], results[1])
        self.assertEqual(results[0][0], 0)
        self.assertEqual(results[0][2], ["draft_uploaded"])

    def test_the_topic_comes_from_the_korean_profile_seeds_and_the_post_is_korean(self):
        publisher = ko_publisher()
        self.go(env=KO_WORKFLOW_ENV, publisher=publisher)
        entry = self.history()[-1]
        self.assertIn(entry["topic"], SEEDS)
        self.assertRegex(publisher.published[0]["title"], "[가-힣]")
        self.assertEqual(publisher.published[0]["labels"], ["생활습관", "루틴", "일상"])      # 스텁이 만든 라벨이 그대로 간다

    def test_the_post_carries_the_honest_ai_notice_and_no_links(self):
        publisher = ko_publisher()
        self.go(env=KO_WORKFLOW_ENV, publisher=publisher)
        html = publisher.published[0]["html"]
        self.assertIn("이 글은 AI의 도움을 받아 작성·편집한 일반 정보입니다", html)             # 프로필 disclosure_html 이 항상 붙는다
        self.assertIn("전문가와 상담하세요", html)
        lowered = html.lower()
        for forbidden in ("<a ", "href=", "<script", "<iframe", "http://", "https://", "@"):
            self.assertNotIn(forbidden, lowered, forbidden)                                     # allow_links:false

    def test_the_summary_starts_with_the_korean_channel_label_and_blog_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            summary = Path(tmp) / "summary.md"
            code, _out = self.go(env={**KO_WORKFLOW_ENV, "GITHUB_STEP_SUMMARY": str(summary)})
            self.assertEqual(code, 0)
            lines = summary.read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines[0], "### [Blogger 한글] Blogger (kcyoon)")
        self.assertEqual([line for line in lines if line.startswith("#")], [lines[0]])

    def test_a_second_run_the_same_day_is_stopped_by_the_daily_cap(self):
        first, second = ko_publisher(), ko_publisher()
        self.assertEqual(self.go(env=KO_WORKFLOW_ENV, publisher=first)[0], 0)
        code, out = self.go(env=KO_WORKFLOW_ENV, publisher=second)
        self.assertEqual(code, 0, out)
        self.assertEqual((len(first.published), len(second.published)), (1, 0))                 # 하루 한 건(레지스트리 limits)
        self.assertEqual(len(self.history()), 1)

    def test_dry_run_writes_nothing_and_never_publishes(self):
        publisher = ko_publisher()
        before = {path for path in self.root.rglob("*")}
        code, out = self.go(env=KO_WORKFLOW_ENV, publisher=publisher, extra=["--dry-run"])
        self.assertEqual(code, 0, out)
        self.assertEqual(publisher.published, [])
        self.assertEqual({path for path in self.root.rglob("*")}, before)
        self.assertIn("DRY_RUN", out)

    def test_the_kill_switch_stops_the_korean_blog_too(self):
        publisher = ko_publisher()
        code, out = self.go(env={**KO_WORKFLOW_ENV, "PIPELINE_PAUSE": "true"}, publisher=publisher)
        self.assertEqual(code, 0)
        self.assertIn("code=PAUSED", out)
        self.assertEqual((publisher.health_calls, publisher.published, self.history(), self.drafts()), (0, [], [], []))

    def test_a_publish_failure_is_recorded_as_a_korean_history_entry(self):
        publisher = ko_publisher(fail=PublishError("서버 오류", code="api_error"))
        code, _out = self.go(env=KO_WORKFLOW_ENV, publisher=publisher)
        self.assertEqual(code, 1)
        entry = self.history()[-1]
        self.assertEqual((entry["blog"], entry["status"]), (KO, "publish_failed"))
        self.assertFalse((self.root / "blogger_history.json").exists())


class SecretTest(KoreanRunBase):
    MODE = "draft"

    def test_english_secret_names_alone_never_activate_the_korean_blog(self):
        """영문 이름(BLOGGER_*)만 환경에 있으면 한글 블로그는 게시용 시크릿이 '하나도 없는' 것으로 본다 → 올리지 않고 저장소 파일에만 저장."""
        publisher = ko_publisher()
        code, out = self.go(env=EN_ENV, publisher=publisher)
        self.assertEqual(code, 0, out)
        self.assertEqual((publisher.health_calls, publisher.published), (0, []))                  # Blogger 에 접속조차 하지 않는다
        self.assertEqual(self.history()[-1]["status"], "draft")
        self.assertIn("code=UPLOAD_SKIPPED", out)
        for name in KO_NAMES:
            self.assertIn(name, out)                                                             # 등록해야 하는 이름은 한글 것으로 안내한다
        for name in EN_NAMES:
            self.assertNotIn(name, out)
        for value in (*EN_VALUES.values(), GEMINI):
            self.assertNotIn(value, out)

    def test_workflow_form_english_values_in_the_korean_run_stop_at_the_auth_check_not_at_the_korean_blog(self):
        """한 번 더 막는 줄: 한글 래퍼가 영문 시크릿을 넘기는 사고가 나도(REG-6 이 PR 에서 먼저 막는다) 영문 계정 블로그 주소가 레지스트리와 다르면 쓰기 전에 멈춘다."""
        workflow_form = {"PIPELINE_SECRET_LLM_API_KEY": GEMINI, "PIPELINE_SECRET_BLOG_ID": EN_VALUES["BLOGGER_BLOG_ID"],
                         "PIPELINE_SECRET_CLIENT_ID": EN_VALUES["BLOGGER_CLIENT_ID"], "PIPELINE_SECRET_CLIENT_SECRET": EN_VALUES["BLOGGER_CLIENT_SECRET"],
                         "PIPELINE_SECRET_REFRESH_TOKEN": EN_VALUES["BLOGGER_REFRESH_TOKEN"]}
        llm = CountingLLM()
        publisher = ko_publisher(blog_url="https://macat0722.blogspot.com/")
        code, out = self.go(env=workflow_form, publisher=publisher, llm=llm)
        self.assertEqual(code, 2, out)
        self.assertIn("reason=blog_mismatch exit=2", out)
        self.assertEqual((llm.calls, publisher.published, self.drafts()), (0, [], []))
        self.assertEqual([(e["blog"], e["status"], e["topic"]) for e in self.history()], [(KO, "publish_failed", "")])
        self.assertNotIn("macat0722", out)

    def test_partial_korean_secrets_stop_before_any_llm_call_and_name_only_the_missing_korean_secrets(self):
        llm = CountingLLM()
        env = {"PIPELINE_SECRET_LLM_API_KEY": GEMINI, "PIPELINE_SECRET_BLOG_ID": KO_VALUES["BLOGGER_KO_BLOG_ID"]}
        code, out = self.go(env=env, llm=llm)
        self.assertEqual(code, 2, out)
        self.assertEqual((llm.calls, self.history(), self.drafts()), (0, [], []))
        self.assertIn("[SKIP] code=SECRETS_MISSING", out)
        for name in KO_NAMES[1:]:
            self.assertIn(name, out)
        self.assertNotIn("BLOGGER_KO_BLOG_ID", out.replace("BLOGGER_KO_CLIENT", ""))             # 등록된 것은 누락 목록에 없다
        for name in EN_NAMES:
            self.assertNotIn(name, out)
        self.assertNotIn(KO_VALUES["BLOGGER_KO_BLOG_ID"], out)                                    # 값은 어디에도 없다

    def test_mixing_one_korean_and_the_english_secrets_is_a_partial_registration_not_a_working_one(self):
        env = {**EN_ENV, "BLOGGER_KO_BLOG_ID": KO_VALUES["BLOGGER_KO_BLOG_ID"]}
        publisher = ko_publisher()
        code, out = self.go(env=env, publisher=publisher)
        self.assertEqual(code, 2, out)
        self.assertEqual((publisher.health_calls, publisher.published), (0, []))
        self.assertIn("BLOGGER_KO_CLIENT_ID", out)

    def test_no_secrets_at_all_in_draft_mode_saves_only_the_repository_file(self):
        publisher = ko_publisher()
        code, out = self.go(env={"PIPELINE_SECRET_LLM_API_KEY": GEMINI}, publisher=publisher)
        self.assertEqual(code, 0, out)
        self.assertEqual((publisher.health_calls, publisher.published), (0, []))
        self.assertEqual(self.history()[-1]["status"], "draft")
        self.assertEqual(len(self.drafts()), 1)
        self.assertIn("저장소 파일에만 저장", out)

    def test_a_missing_llm_key_is_a_configuration_error_naming_the_shared_gemini_secret(self):
        code, out = self.go(env={name: value for name, value in KO_WORKFLOW_ENV.items() if name != "PIPELINE_SECRET_LLM_API_KEY"}, llm=None)
        self.assertEqual(code, 2, out)
        self.assertIn("GEMINI_API_KEY", out)                                                     # LLM 키는 영문·한글이 같은 Gemini 키를 쓴다(작업요청서)
        self.assertEqual(self.history(), [])


class AutoModeTest(KoreanRunBase):
    MODE = "auto"

    def test_auto_mode_publishes_immediately_to_the_korean_blog(self):
        publisher = ko_publisher()
        code, out = self.go(env=KO_WORKFLOW_ENV, publisher=publisher)
        self.assertEqual(code, 0, out)
        self.assertIs(publisher.published[0]["draft"], False)
        self.assertEqual(self.history()[-1]["status"], "posted")

    def test_auto_mode_without_korean_secrets_stops_before_any_llm_call_and_lists_the_korean_names(self):
        llm = CountingLLM()
        code, out = self.go(env={"PIPELINE_SECRET_LLM_API_KEY": GEMINI, **{k: v for k, v in EN_ENV.items() if k != "GEMINI_API_KEY"}}, llm=llm)
        self.assertEqual(code, 2, out)
        self.assertEqual((llm.calls, self.history()), (0, []))
        for name in KO_NAMES:
            self.assertIn(name, out)
        for name in EN_NAMES:
            self.assertNotIn(name, out)


class StoppedTest(KoreanRunBase):
    MODE = "off"

    def test_mode_off_is_a_noop_that_writes_nothing(self):
        publisher = ko_publisher()
        before = {path for path in self.root.rglob("*")}
        code, out = self.go(env=KO_WORKFLOW_ENV, publisher=publisher)
        self.assertEqual(code, 0, out)
        self.assertIn("code=MODE_OFF", out)
        self.assertEqual((publisher.health_calls, publisher.published), (0, []))
        self.assertEqual({path for path in self.root.rglob("*")}, before)

    def test_the_auth_check_still_runs_while_stopped_and_writes_nothing(self):
        """켜기 전에 시크릿을 확인할 수 있어야 한다: `인증 점검만 실행` 은 정지 중에도, 글 생성 없이, 쓰기 없이 돈다."""
        for label, kwargs in (("--auth-check", dict(extra=["--auth-check"], env=KO_WORKFLOW_ENV)),
                              ("BLOGGER_AUTH_CHECK=1", dict(env={**KO_WORKFLOW_ENV, "BLOGGER_AUTH_CHECK": "1"}))):
            with self.subTest(label), tempfile.TemporaryDirectory() as tmp:
                summary = Path(tmp) / "summary.md"
                kwargs["env"] = {**kwargs["env"], "GITHUB_STEP_SUMMARY": str(summary)}
                publisher, llm = ko_publisher(), CountingLLM()
                before = {path for path in self.root.rglob("*")}
                code, out = self.go(publisher=publisher, llm=llm, **kwargs)
                self.assertEqual(code, 0, out)
                self.assertIn("mode=off(정지 중)이지만 인증 점검은 쓰기가 없어 실행합니다", out)
                self.assertIn("인증 점검 통과", out)
                lines = summary.read_text(encoding="utf-8").splitlines()
                self.assertEqual(lines[0], "### [Blogger 한글] Blogger (kcyoon)")
                self.assertIn("AUTH_CHECK_OK", lines[1])                                          # 결과 코드는 실행 요약에 남는다
                self.assertEqual((publisher.health_calls, publisher.published, llm.calls), (1, [], 0))
                self.assertEqual({path for path in self.root.rglob("*")}, before)

    def test_the_auth_check_reports_missing_korean_secrets_by_their_korean_names(self):
        code, out = self.go(env={"PIPELINE_SECRET_LLM_API_KEY": GEMINI}, extra=["--auth-check"])
        self.assertEqual(code, 2, out)
        for name in KO_NAMES:
            self.assertIn(name, out)
        for name in EN_NAMES:
            self.assertNotIn(name, out)


class GateTest(KoreanRunBase):
    """한글 프로필의 게이트가 러너에서 글을 막는다: 올리지도, 초안 파일로 저장하지도 않고 '거절' 한 줄만 남긴다."""
    MODE = "draft"

    BAD = ("직접 써 봤더니 정리 시간이 확 줄었어요.",                 # 지어낸 경험
           "이 설정으로 작업 속도가 30% 빨라집니다.",                 # 지어낸 수치
           "혈압을 낮추는 데 이 앱이 도움이 됩니다.",                 # 의료
           "변호사를 거치지 않고 합의금을 정하세요.",                 # 법률
           "주식 투자 종목을 AI에게 추천받아 보세요.",               # 투자
           "자세한 내용은 https://example.com/help 에서 확인하세요.",  # 링크
           "월 9,900원짜리 요금제를 쓰면 한도가 늘어납니다.",         # 요금·한도
           "이 도구는 강력 추천합니다.",                              # 광고 어조
           "저는 AI 언어 모델이라서 직접 써 볼 수는 없어요.")        # AI 자기 언급

    def test_each_kind_of_forbidden_sentence_turns_the_post_down_and_nothing_is_uploaded(self):
        for sentence in self.BAD:
            with self.subTest(sentence):
                with tempfile.TemporaryDirectory() as tmp:
                    root = make_pair_root(tmp, ko_mode="draft")
                    publisher = ko_publisher()
                    code, out = self.go(env=KO_WORKFLOW_ENV, publisher=publisher, llm=llm_with(sentence), root=root)
                    self.assertEqual(code, 0, out)
                    self.assertIn("code=GATE_REJECTED", out)
                    self.assertEqual(publisher.published, [])
                    entry = self.history(root=root)[-1]
                    self.assertEqual((entry["blog"], entry["status"]), (KO, "rejected"))
                    self.assertFalse((Path(root) / "_blogger_ko_drafts").exists())

    def test_the_same_sentences_are_not_blocked_when_the_post_is_clean(self):
        """대조군: 문장을 붙이지 않은 글은 같은 설정에서 올라간다(위 시험이 우연히 모든 글을 막는 것이 아님을 확인)."""
        publisher = ko_publisher()
        code, out = self.go(env=KO_WORKFLOW_ENV, publisher=publisher)
        self.assertEqual((code, len(publisher.published)), (0, 1), out)

    def test_a_topic_typed_by_the_operator_is_checked_against_the_forbidden_topic_words(self):
        for topic in ("주식 투자 종목 추천받는 법", "대출 금리 비교하는 법", "소송 서류 쓰는 법", "다이어트 약 고르는 법"):
            with self.subTest(topic):
                llm = CountingLLM()
                code, out = self.go(env=KO_WORKFLOW_ENV, llm=llm, extra=["--topic", topic])
                self.assertEqual(code, 2, out)
                self.assertIn("code=TOPIC_BLOCKED", out)
                self.assertEqual((llm.calls, self.history()), (0, []))

    def test_a_normal_operator_topic_is_accepted(self):
        publisher = ko_publisher()
        code, out = self.go(env=KO_WORKFLOW_ENV, publisher=publisher, extra=["--topic", "스마트폰 사진을 날짜별로 정리하는 순서"])
        self.assertEqual((code, len(publisher.published)), (0, 1), out)
        self.assertEqual(self.history()[-1]["topic"], "스마트폰 사진을 날짜별로 정리하는 순서")


class CrossBlogTest(unittest.TestCase):
    """다른 블로그 이력의 주제는 서로 피한다: 한글은 영문(+Chance) 이력을, 영문은 한글 이력을 본다 — 두 방향 모두."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def test_the_korean_blog_avoids_topics_in_the_english_blogs_history(self):
        root = make_pair_root(self._tmp.name, ko_mode="draft", en_mode="off")
        # 영문 이력에 한글 시드가 하나만 빼고 전부 이미 있다 → 남은 하나만 골라야 한다(Chance 이력과 같은 방식의 교차 중복 방지)
        (root / "blogger_history.json").write_text(json.dumps([{"topic": seed, "date": "2026-10-20", "status": "posted"} for seed in SEEDS[:-1]], ensure_ascii=False), encoding="utf-8")
        case = KoreanRunBase("setUp")
        case.root = root
        code, out = case.go(env=KO_WORKFLOW_ENV)
        self.assertEqual(code, 0, out)
        self.assertEqual(case.history()[-1]["topic"], SEEDS[-1])

    def test_the_korean_blog_avoids_topics_in_the_chance_history_too(self):
        root = make_pair_root(self._tmp.name, ko_mode="draft", en_mode="off")
        (root / "history.json").write_text(json.dumps(SEEDS[:-1], ensure_ascii=False), encoding="utf-8")
        case = KoreanRunBase("setUp")
        case.root = root
        code, _out = case.go(env=KO_WORKFLOW_ENV)
        self.assertEqual(code, 0)
        self.assertEqual(case.history()[-1]["topic"], SEEDS[-1])

    def test_the_english_blog_avoids_topics_in_the_korean_blogs_history(self):
        english_profile = json.loads((REAL / "pipeline" / "profiles" / "blogger_practical_en.json").read_text(encoding="utf-8"))
        english_seeds = english_profile["seed_topics"]
        root = make_pair_root(self._tmp.name, ko_mode="off", en_mode="draft", en_lang="en")
        (root / "blogger_ko_history.json").write_text(json.dumps([{"topic": seed, "date": "2026-10-20", "status": "posted"} for seed in english_seeds[:-1]], ensure_ascii=False),
                                                     encoding="utf-8")
        case = KoreanRunBase("setUp")
        case.root = root
        code, out = case.go(env={"PIPELINE_SECRET_LLM_API_KEY": GEMINI, **{f"PIPELINE_SECRET_{role.upper()}": EN_VALUES[name]
                                                                           for role, name in zip(ALL_ROLES[1:], EN_NAMES)}},
                            publisher=FakePublisher(), blog=EN)
        self.assertEqual(code, 0, out)
        self.assertEqual(case.history(name="blogger_history.json")[-1]["topic"], english_seeds[-1])

    def test_the_reverse_check_reads_a_history_file_that_exists_only_in_the_registry(self):
        """영문이 한글 이력 파일을 읽는 길은 하드코딩이 아니라 레지스트리의 state.history 다 — 이름을 바꾸면 그 이름을 읽는다."""
        reg = registry.load_registry(REAL / "pipeline" / "blogs.json")
        self.assertEqual(registry.get_blog(reg, KO)["state"], {"history": "blogger_ko_history.json", "content_dir": "_blogger_ko_drafts"})
        self.assertNotEqual(registry.get_blog(reg, EN)["state"]["history"], registry.get_blog(reg, KO)["state"]["history"])
        self.assertNotEqual(registry.get_blog(reg, EN)["state"]["content_dir"], registry.get_blog(reg, KO)["state"]["content_dir"])


class IsolationTest(KoreanRunBase):
    """한쪽 블로그 실행이 다른 쪽의 파일을 건드리지 않는다."""
    MODE = "draft"

    def test_a_korean_run_leaves_the_english_files_byte_identical(self):
        english_history = json.dumps([{"v": 1, "blog": EN, "date": "2026-10-20", "status": "draft_uploaded", "topic": "A quiet evening reset", "title": "A quiet evening reset"}], indent=2) + "\n"
        (self.root / "blogger_history.json").write_text(english_history, encoding="utf-8")
        (self.root / "_blogger_drafts").mkdir()
        (self.root / "_blogger_drafts" / "2026-10-20-x.md").write_text("english draft\n", encoding="utf-8")
        before = {path: path.read_bytes() for path in self.root.rglob("*") if path.is_file() and ("blogger_history.json" in path.name or "_blogger_drafts" in path.parts)}
        self.assertEqual(self.go(env=KO_WORKFLOW_ENV)[0], 0)
        after = {path: path.read_bytes() for path in self.root.rglob("*") if path.is_file() and ("blogger_history.json" in path.name or "_blogger_drafts" in path.parts)}
        self.assertEqual(after, before)

    def test_the_korean_run_is_unaffected_by_an_english_run_the_same_day(self):
        """하루 상한은 블로그별이다: 영문이 오늘 올렸어도 한글은 오늘 올릴 수 있다."""
        (self.root / "blogger_history.json").write_text(
            json.dumps([{"v": 1, "blog": EN, "date": "2026-10-21", "status": "draft_uploaded", "topic": "x", "title": "x"}]), encoding="utf-8")
        publisher = ko_publisher()
        self.assertEqual(self.go(env=KO_WORKFLOW_ENV, publisher=publisher)[0], 0)
        self.assertEqual(len(publisher.published), 1)

    def test_an_english_run_leaves_the_korean_files_alone(self):
        korean_history = json.dumps([{"v": 1, "blog": KO, "date": "2026-10-20", "status": "draft_uploaded", "topic": "x", "title": "x"}], indent=2) + "\n"
        with tempfile.TemporaryDirectory() as tmp:
            root = make_pair_root(tmp, ko_mode="draft", en_mode="draft", en_lang="en")
            (root / "blogger_ko_history.json").write_text(korean_history, encoding="utf-8")
            env = {"PIPELINE_SECRET_LLM_API_KEY": GEMINI, "PIPELINE_SECRET_BLOG_ID": EN_VALUES["BLOGGER_BLOG_ID"], "PIPELINE_SECRET_CLIENT_ID": EN_VALUES["BLOGGER_CLIENT_ID"],
                   "PIPELINE_SECRET_CLIENT_SECRET": EN_VALUES["BLOGGER_CLIENT_SECRET"], "PIPELINE_SECRET_REFRESH_TOKEN": EN_VALUES["BLOGGER_REFRESH_TOKEN"]}
            code, out = self.go(env=env, publisher=FakePublisher(), root=root, blog=EN)
            self.assertEqual(code, 0, out)
            self.assertEqual((root / "blogger_ko_history.json").read_text(encoding="utf-8"), korean_history)
            self.assertFalse((root / "_blogger_ko_drafts").exists())
            self.assertEqual(self.history(name="blogger_history.json", root=root)[-1]["blog"], EN)


class RegistryContractTest(unittest.TestCase):
    """레지스트리의 한글 블로그 항목이 이 시험들이 전제하는 값 그대로인지(실제 파일)."""

    def setUp(self):
        self.reg = registry.load_registry(REAL / "pipeline" / "blogs.json")
        self.blog = registry.get_blog(self.reg, KO)

    def test_the_real_registry_keeps_the_korean_blog_stopped_and_ad_free(self):
        self.assertEqual((self.blog["mode"], self.blog["ads"], self.blog["ad_surface"]), ("off", "off", False))   # 켜는 것은 운영자 승인 뒤 PR 한 줄
        self.assertEqual(registry.validate_registry(self.reg, REAL), [])

    def test_identity_and_files_do_not_overlap_with_the_english_blog(self):
        english = registry.get_blog(self.reg, EN)
        self.assertEqual((self.blog["platform"], self.blog["languages"], self.blog["url"]), ("blogger", ["ko"], "https://kcyoon.blogspot.com/"))
        self.assertNotEqual(self.blog["url"], english["url"])
        self.assertEqual(self.blog["channel"], {"key": "blogger_ko", "label": "Blogger 한글"})
        self.assertEqual(english["channel"], {"key": "blogger_en", "label": "Blogger 영문"})
        self.assertEqual((self.blog["profile"], self.blog["prompt"]), ("blogger_ai_tools_ko", ".github/editorial/BLOGGER_PROMPT_KO_AI.md"))
        self.assertEqual(self.blog["entrypoint"], english["entrypoint"])                              # 같은 러너 코드
        for field in ("workflow", "profile", "prompt"):
            self.assertNotEqual(self.blog[field], english[field], field)
        self.assertEqual(set(self.blog["state"].values()) & set(english["state"].values()), set())    # 이력·초안 폴더가 겹치지 않는다
        self.assertEqual(self.blog["limits"], english["limits"])                                       # 하루 한 건

    def test_secrets_are_its_own_four_names_plus_the_shared_gemini_key(self):
        english = registry.get_blog(self.reg, EN)
        self.assertEqual(self.blog["secrets"], {"llm_api_key": "GEMINI_API_KEY", "blog_id": "BLOGGER_KO_BLOG_ID", "client_id": "BLOGGER_KO_CLIENT_ID",
                                                "client_secret": "BLOGGER_KO_CLIENT_SECRET", "refresh_token": "BLOGGER_KO_REFRESH_TOKEN"})
        self.assertEqual(self.blog["secrets"]["llm_api_key"], english["secrets"]["llm_api_key"])
        self.assertEqual(set(self.blog["secrets"].values()) & set(english["secrets"].values()), {"GEMINI_API_KEY"})

    def test_the_korean_history_file_must_be_kept_off_the_public_site_before_the_blog_is_turned_on(self):
        """Jekyll 은 밑줄로 시작하지 않는 루트 파일을 사이트에 그대로 낸다 — `blogger_ko_history.json` 은 `_config.yml` 의 exclude 에 이름이 적혀야 한다
        (영문 `blogger_history.json` 이 거기 있는 이유와 같다). `_config.yml` 은 광고 표면이라 T3 승인이 필요해 한글 Blogger 를 등록하는 이 작업은 건드리지 않았다.
        그래서 정지(off)인 동안만 비어 있어도 되게 하고, exclude 를 더하기 전에 `mode` 를 켜는 실수를 시험이 막는다(첫 실행이 이력을 루트에 커밋하면 공개 주소가 된다)."""
        excluded = yaml.safe_load((REAL / "_config.yml").read_text(encoding="utf-8")).get("exclude") or []
        history = self.blog["state"]["history"]
        self.assertTrue(history in excluded or self.blog["mode"] == "off",
                        f"{history} 가 `_config.yml` exclude 에 없는데 {KO} 의 mode 가 {self.blog['mode']} 입니다 — exclude 를 먼저 더하세요(T3)")
        self.assertIn("blogger_history.json", excluded)                              # 영문 이력은 이미 빠져 있다(같은 이유)
        self.assertTrue(self.blog["state"]["content_dir"].startswith("_"))           # 밑줄로 시작하는 초안 폴더는 Jekyll 이 처음부터 무시한다
        self.assertEqual((REAL / history).exists(), False)                           # 정지 중에는 이력 파일이 아예 만들어지지 않았다

    def test_the_default_plan_has_no_korean_target_until_it_is_turned_on(self):
        from pipeline import plan
        self.assertEqual([item["key"] for item in plan.build_matrix(self.reg, "blogger", include_off=True)["include"]], [EN, KO])
        self.assertEqual(plan.build_matrix(self.reg, "blogger")["include"], [])


if __name__ == "__main__":
    unittest.main()
