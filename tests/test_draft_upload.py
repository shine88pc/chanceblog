"""Blogger 초안함 업로드 모드(draft_uploaded)와 인증 점검: 러너(pipeline/run.py)의 모드×입력×시크릿 동작과 불변식.

구성
  1) 시나리오 시험: 모드·수동 입력·시크릿 조합마다 무엇이 올라가고(초안함/즉시 게시/저장소 파일) 이력·로그·요약에 무엇이 남는지.
  2) 열거 시험: 입력 조건 전수(모드 3 × BLOGGER_PUBLISH 7 × 연습 2 × 시크릿 16가지 × 하루 상한 2)와 단계 경로 전수(인증 점검 11 ×
     글 생성 5 × 게시 결과 11 × 전달 방식 2)를 문서의 처리 순서를 옮긴 기준 모델과 비교하고, '게시 대상 실행이 이유 없이 초록으로
     끝나는 경로 없음'을 포함한 불변식을 모든 조합에서 확인한다(진단의 12,960가지 열거와 같은 취지).
  3) blogger.yml 불변식: 수동 입력 3택·기본값, 입력이 환경 변수로만 흐르는지, PIPELINE_SECRET_* 전달과 권한이 그대로인지.

실제 구글·Blogger·Gemini 호출은 없다(가짜 게시자·가짜 LLM). 시크릿 값은 런타임에 조합한 가짜다.
"""
import contextlib
import json
import random
import re
import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import _bootstrap  # noqa: F401
from pipeline import auth_check as ac
from pipeline import health, registry
from pipeline import run as run_mod
from pipeline.llm import LLMError
from pipeline.publishers.base import PublishError, PublishResult
from pipeline.state import KST
from pipeline.stubs import stub_llm
from test_run import NOW, FakePublisher, make_root

try:
    import yaml
except ImportError:  # pragma: no cover - requirements-dev.txt 가 설치하는 의존성
    yaml = None

REAL = _bootstrap.ROOT

SECRET_NAMES = ("BLOGGER_BLOG_ID", "BLOGGER_CLIENT_ID", "BLOGGER_CLIENT_SECRET", "BLOGGER_REFRESH_TOKEN")
# 실제 비밀처럼 보이는 리터럴을 소스에 쓰지 않으려고 런타임에 조합한다(값은 가짜, 길이는 실제와 비슷하게)
SECRET_VALUES = {"BLOGGER_BLOG_ID": "7654321098" + "765432101",
                 "BLOGGER_CLIENT_ID": "123456789012-" + "fakeclientid",
                 "BLOGGER_CLIENT_SECRET": "fake-client-" + "secret-value-0001",
                 "BLOGGER_REFRESH_TOKEN": "fake-refresh-" + "token-value-0002"}
GEMINI_VALUE = "fake-gemini-" + "key-value-0003"
PROJECT_NUMBER = SECRET_VALUES["BLOGGER_CLIENT_ID"].split("-")[0]       # 클라이언트 ID 앞 12자리 = 구글 클라우드 프로젝트 번호(오류 문구에 실려 나온다)
ALL_ENV = {"GEMINI_API_KEY": GEMINI_VALUE, **SECRET_VALUES}
LLM_ONLY_ENV = {"GEMINI_API_KEY": GEMINI_VALUE}
EVERY_SECRET_VALUE = (GEMINI_VALUE, *SECRET_VALUES.values(), PROJECT_NUMBER)
TODAY_ENTRY = {"v": 1, "blog": "blogger_macat", "date": "2026-10-21", "status": "draft", "topic": "오늘 이미 만든 주제",
               "title": "오늘 이미 만든 글", "generated_at": "2026-10-21T10:00:00+09:00"}
SHORT_POST = "제목: 충분히 긴 제목입니다 정말로\n라벨: 가\n내용:\n<p>너무 짧음</p>", "m"


def seed_history():
    """모든 시드 주제를 이미 쓴 것으로 만드는 이력(주제 확장 호출이 필요한 상황)."""
    seeds = json.loads((REAL / "pipeline" / "profiles" / "blogger_practical_ko.json").read_text(encoding="utf-8"))["seed_topics"]
    return [{"topic": t, "date": "2026-10-20", "status": "posted"} for t in seeds]


class Result:
    def __init__(self, code, out, summary, history, drafts, publisher, llm_calls):
        self.code, self.out, self.summary, self.history = code, out, summary, history
        self.drafts, self.publisher, self.llm_calls = drafts, publisher, llm_calls

    @property
    def lines(self):
        return self.out.splitlines()

    @property
    def skips(self):
        return re.findall(r"^\[SKIP\] code=(\w+)", self.out, re.M)

    @property
    def annotations(self):
        return [line for line in self.lines if line.startswith("::")]

    @property
    def last(self):
        return self.history[-1] if self.history else None

    @property
    def summary_lines(self):
        return self.summary.splitlines()

    def everything(self):
        """로그·요약·이력·초안 파일을 합친 문자열(비밀 값이 어디에도 없는지 볼 때 쓴다)."""
        if not hasattr(self, "_everything"):
            self._everything = "\n".join([self.out, self.summary, json.dumps(self.history, ensure_ascii=False),
                                          *self.drafts.values()])
        return self._everything


class Spy:
    def __init__(self, fn):
        self.fn, self.calls = fn, 0

    def __call__(self, prompt):
        self.calls += 1
        return self.fn(prompt)


class Runner:
    """모드별 임시 저장소를 한 번 만들어 두고, 실행마다 이력·초안·요약만 비워 빠르게 반복한다."""

    def __init__(self, test, in_memory_summary=False):
        """in_memory_summary: 실행 요약을 파일이 아니라 메모리에 모은다(수백 번 도는 열거에서 파일 쓰기 비용을 줄이려는 것. 내용은 같다)."""
        tmp = tempfile.TemporaryDirectory()
        test.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        self.roots = {mode: make_root(self.base / mode, mode=mode) for mode in ("off", "draft", "auto")}
        self.summary_path = self.base / "summary.md"
        self.in_memory_summary = in_memory_summary

    def run(self, mode, env=None, publisher=None, factory=None, llm=stub_llm, extra=(), history=None, now=NOW):
        root = self.roots[mode]
        history_path = root / "blogger_history.json"
        history_path.unlink(missing_ok=True)
        shutil.rmtree(root / "_blogger_drafts", ignore_errors=True)
        self.summary_path.unlink(missing_ok=True)
        if history is not None:
            history_path.write_text(json.dumps(history, ensure_ascii=False), encoding="utf-8")
        if factory is None and publisher is not None:
            factory = lambda blog, environ: publisher  # noqa: E731
        spy, out, memory = Spy(llm), [], []
        capture = (mock.patch.object(run_mod, "_write_summary", lambda environ, text: memory.append(text + "\n"))
                   if self.in_memory_summary else contextlib.nullcontext())
        with capture:
            code = run_mod.run(["--blog", "blogger_macat", "--root", str(root), *extra],
                               environ={"GITHUB_STEP_SUMMARY": str(self.summary_path), **(env or {})}, now=now,
                               llm=spy if llm is not None else None,     # llm=None: 러너가 키로 Gemini 호출 객체를 만들어야 하는 상황
                               publisher_factory=factory, rng=random.Random(1), out=out.append)
        folder = root / "_blogger_drafts"
        if self.in_memory_summary:
            summary = "".join(memory)
        else:
            summary = self.summary_path.read_text(encoding="utf-8") if self.summary_path.exists() else ""
        return Result(code, "\n".join(out), summary,
                      json.loads(history_path.read_text(encoding="utf-8")) if history_path.exists() else [],
                      {p.name: p.read_text(encoding="utf-8") for p in sorted(folder.glob("*.md"))} if folder.exists() else {},
                      publisher, spy)


def must_not_be_called(blog, environ):
    raise AssertionError("Blogger 게시자를 만들면 안 되는 실행이다")


# ----------------------------------------------------------------------------
# 1) 시나리오
# ----------------------------------------------------------------------------
class ScenarioTest(unittest.TestCase):
    def setUp(self):
        self.r = Runner(self)

    def test_draft_mode_with_all_secrets_uploads_to_the_blogger_drafts(self):
        pub = FakePublisher()
        res = self.r.run("draft", ALL_ENV, pub)
        self.assertEqual(res.code, 0, res.out)
        self.assertEqual([p["draft"] for p in pub.published], [True])          # isDraft: 초안함에만 올린다
        self.assertEqual(pub.health_calls, 1)                                    # 인증 점검 1회
        self.assertIn("AI의 도움", pub.published[0]["html"])                     # 면책·AI 사용 문구는 초안에도 붙는다
        self.assertEqual((res.last["status"], res.last["url"], res.last["post_id"]), ("draft_uploaded", "https://macat.example/p1", "p1"))
        self.assertEqual(res.skips, [])
        self.assertEqual(res.annotations, [])
        self.assertEqual(len(res.drafts), 1)                                     # 저장소 초안 파일도 그대로 남는다
        text = next(iter(res.drafts.values()))
        self.assertIn("status: draft_uploaded", text)
        self.assertIn('url: "https://macat.example/p1"', text)
        self.assertNotIn(SECRET_VALUES["BLOGGER_BLOG_ID"], res.everything())    # 블로그 ID 는 어디에도 기록하지 않는다
        self.assertEqual(len(res.summary_lines), 4, res.summary)
        self.assertEqual(res.summary_lines[0], "### blogger_macat")
        self.assertIn("**draft_uploaded**", res.summary_lines[1])
        self.assertIn("https://macat.example/p1", res.summary_lines[2])
        self.assertIn("Blogger 초안함에 올렸습니다", res.summary_lines[3])
        self.assertIn("직접 게시", res.summary_lines[3])                          # 운영자가 할 일을 알려 준다

    def test_draft_mode_without_any_publish_secret_keeps_the_file_draft_and_says_so(self):
        pub = FakePublisher()
        res = self.r.run("draft", LLM_ONLY_ENV, pub)
        self.assertEqual(res.code, 0, res.out)                                   # 오류가 아니다
        self.assertEqual((pub.health_calls, pub.published), (0, []))             # Blogger 에 접속하지 않는다
        self.assertEqual(res.last["status"], "draft")
        self.assertEqual(len(res.drafts), 1)
        self.assertEqual(res.skips, ["UPLOAD_SKIPPED"])
        self.assertIn("reason=NO_SECRETS", res.out)
        self.assertEqual(len(res.annotations), 1, res.annotations)
        self.assertTrue(res.annotations[0].startswith("::notice::[blogger_macat] Blogger 초안함에는 올리지 않고"), res.annotations)
        self.assertEqual(len(res.summary_lines), 4, res.summary)
        self.assertIn("Blogger 초안함에는 올리지 않음(게시용 시크릿 없음)", res.summary_lines[3])
        for name in SECRET_NAMES:                                                 # 등록할 시크릿 '이름'을 안내한다
            self.assertIn(name, res.summary_lines[3])

    def test_a_partially_registered_secret_set_is_a_config_error_naming_only_the_missing_ones(self):
        names = SECRET_NAMES
        for mask in range(1, 15):                                                 # 4종 중 일부만(0과 15는 '없음'·'모두')
            present = [n for i, n in enumerate(names) if mask >> i & 1]
            missing = [n for n in names if n not in present]
            with self.subTest(present=present):
                pub = FakePublisher()
                res = self.r.run("draft", {**LLM_ONLY_ENV, **{n: SECRET_VALUES[n] for n in present}}, pub)
                self.assertEqual(res.code, 2)
                self.assertEqual(res.skips, ["SECRETS_MISSING"])
                self.assertIn("missing=" + ",".join(missing), res.out)
                self.assertEqual(len(res.annotations), 1)
                self.assertTrue(res.annotations[0].startswith("::error::[blogger_macat] 게시용 시크릿이 일부만 등록되어 있습니다"))
                self.assertEqual((res.llm_calls.calls, res.history, res.drafts, pub.health_calls, pub.published), (0, [], {}, 0, []))
                for value in SECRET_VALUES.values():
                    self.assertNotIn(value, res.everything())

    def test_auto_mode_still_publishes_live(self):
        pub = FakePublisher()
        res = self.r.run("auto", ALL_ENV, pub)
        self.assertEqual(res.code, 0, res.out)
        self.assertEqual([p["draft"] for p in pub.published], [False])
        self.assertEqual((pub.health_calls, res.last["status"]), (1, "posted"))
        self.assertEqual(len(res.summary_lines), 3, res.summary)                  # '### 키', '- 결과', '- URL'

    def test_manual_choice_decides_where_the_post_goes_whatever_the_mode(self):
        # (레지스트리 mode, BLOGGER_PUBLISH 값) → (publish 호출의 draft 플래그, 이력 상태)
        table = {("auto", "off"): ([], "draft"), ("auto", "draft"): ([True], "draft_uploaded"),
                 ("auto", "publish"): ([False], "posted"), ("auto", "auto"): ([False], "posted"), ("auto", ""): ([False], "posted"),
                 ("draft", "off"): ([], "draft"), ("draft", "draft"): ([True], "draft_uploaded"),
                 ("draft", "publish"): ([False], "posted"), ("draft", "auto"): ([True], "draft_uploaded"),
                 ("draft", ""): ([True], "draft_uploaded")}
        for (mode, choice), (calls, status) in table.items():
            with self.subTest(mode=mode, choice=choice):
                pub = FakePublisher()
                res = self.r.run(mode, {**ALL_ENV, "BLOGGER_PUBLISH": choice}, pub)
                self.assertEqual(res.code, 0, res.out)
                self.assertEqual(([p["draft"] for p in pub.published], res.last["status"]), (calls, status))

    def test_publish_choice_needs_all_secrets_but_draft_and_off_choices_do_not(self):
        for mode in ("draft", "auto"):
            res = self.r.run(mode, {**LLM_ONLY_ENV, "BLOGGER_PUBLISH": "publish"}, FakePublisher())
            self.assertEqual((res.code, res.skips), (2, ["SECRETS_MISSING"]), mode)
            for choice, status in (("draft", "draft"), ("off", "draft")):
                res = self.r.run(mode, {**LLM_ONLY_ENV, "BLOGGER_PUBLISH": choice}, FakePublisher())
                self.assertEqual((res.code, res.last["status"]), (0, status), (mode, choice))

    def test_off_choice_and_dry_run_never_even_create_a_publisher(self):
        for env_extra, extra in (({"BLOGGER_PUBLISH": "off"}, ()), ({"DRY_RUN": "1"}, ()), ({}, ("--dry-run",))):
            for mode in ("draft", "auto"):
                with self.subTest(env=env_extra, extra=extra, mode=mode):
                    res = self.r.run(mode, {**ALL_ENV, **env_extra}, factory=must_not_be_called, extra=extra)
                    self.assertEqual(res.code, 0, res.out)

    def test_dry_run_writes_nothing_and_reports_the_would_be_upload_target(self):
        res = self.r.run("draft", ALL_ENV, FakePublisher(), extra=["--dry-run"])
        self.assertEqual((res.code, res.history, res.drafts), (0, [], {}))
        self.assertIn("[DRY_RUN]", res.out)
        self.assertEqual(res.publisher.health_calls, 0)
        self.assertEqual(res.publisher.published, [])

    def test_draft_uploaded_counts_toward_the_daily_cap_and_blogger_is_not_contacted_again(self):
        first_pub = FakePublisher()
        first = self.r.run("draft", ALL_ENV, first_pub)
        self.assertEqual(first.last["status"], "draft_uploaded")
        second_pub = FakePublisher()
        second = self.r.run("draft", ALL_ENV, second_pub, history=first.history)
        self.assertEqual((second.code, second.skips), (0, ["DAILY_CAP"]))
        self.assertIn("draft_uploaded", second.annotations[0])                  # 어떤 기록이 상한을 채웠는지 보인다
        self.assertEqual((second_pub.health_calls, second_pub.published), (0, []))   # 같은 날 중복 업로드 없음
        self.assertEqual(len(second.history), 1)
        # 수동 주제 지정은 상한만 건너뛴다(다른 글이므로 다시 올라간다)
        third_pub = FakePublisher()
        third = self.r.run("draft", ALL_ENV, third_pub, history=first.history,
                           extra=["--topic", "수동으로 지정한 오늘의 생활 습관 주제"])
        self.assertEqual((third.code, third.last["status"], third.last["topic_source"]), (0, "draft_uploaded", "override"))
        self.assertEqual(len(third.history), 2)

    def test_the_same_title_is_not_uploaded_twice_even_with_a_manual_topic(self):
        """상한을 건너뛰는 수동 실행이 같은 제목의 글을 또 올리지 않는다: 이력의 제목이 게이트의 중복 검사(DUP_SAME)에 쓰인다."""
        first = self.r.run("draft", ALL_ENV, FakePublisher())
        again = self.r.run("draft", ALL_ENV, FakePublisher(), history=first.history,
                           extra=["--topic", first.last["topic"]])     # 같은 주제 → 같은 제목의 글이 나온다
        self.assertEqual(again.code, 0)
        self.assertEqual(again.last["status"], "rejected")
        self.assertIn("DUP_SAME", json.dumps(again.last["reasons"], ensure_ascii=False))
        self.assertEqual(again.publisher.published, [])

    def test_a_failed_attempt_does_not_use_up_the_day(self):
        failed = self.r.run("draft", ALL_ENV, FakePublisher(fail=PublishError("boom", code="api_error")))
        self.assertEqual((failed.code, failed.last["status"]), (1, "publish_failed"))
        retry_pub = FakePublisher()
        retry = self.r.run("draft", ALL_ENV, retry_pub, history=failed.history)
        self.assertEqual((retry.code, [e["status"] for e in retry.history]), (0, ["publish_failed", "draft_uploaded"]))
        self.assertEqual(len(retry_pub.published), 1)

    def test_a_failing_auth_check_stops_before_any_llm_call_and_leaves_a_trace(self):
        cases = {"auth_expired": 1, "auth_failed": 2, "network": 1, "bad_response": 1, "api_error": 1, "something_new": 1}
        for code, expected_exit in cases.items():
            for mode in ("draft", "auto"):
                with self.subTest(code=code, mode=mode):
                    marker = "RAW-MARKER-서버가-준-문구"
                    pub = FakePublisher(check=PublishError(marker, code=code))
                    res = self.r.run(mode, ALL_ENV, pub)
                    shown = ac.safe_code(code)
                    self.assertEqual(res.code, expected_exit, res.out)
                    self.assertEqual(res.skips, ["AUTH_CHECK_FAILED"])
                    self.assertIn(f"reason={shown} exit={expected_exit}", res.out)
                    self.assertEqual((res.llm_calls.calls, pub.published, res.drafts), (0, [], {}))   # Gemini 도, 게시도, 초안도 없다
                    self.assertEqual(len(res.history), 1)
                    self.assertEqual((res.last["status"], res.last["topic"]), ("publish_failed", ""))
                    self.assertTrue(res.last["reasons"][0].startswith(f"[{shown}] "), res.last["reasons"])
                    # ::error:: 주석에는 고정 문장만(서버가 준 문구는 로그 본문·이력에만)
                    self.assertEqual(res.annotations, [f"::error::[blogger_macat] {ac.sentence_for(shown)}"])
                    self.assertIn(marker, res.out)
                    self.assertEqual(len(res.summary_lines), 2, res.summary)
                    self.assertIn(ac.label_for(shown), res.summary_lines[1])

    def test_a_blog_address_mismatch_stops_everything_and_never_prints_the_other_address(self):
        pub = FakePublisher(blog_url="https://private-diary-of-someone.blogspot.com/")
        res = self.r.run("draft", ALL_ENV, pub)
        self.assertEqual((res.code, res.skips, pub.published, res.llm_calls.calls), (2, ["AUTH_CHECK_FAILED"], [], 0))
        self.assertIn("reason=blog_mismatch exit=2", res.out)
        self.assertEqual(res.last["status"], "publish_failed")
        self.assertNotIn("private-diary", res.everything())
        # http/https·끝 슬래시 차이는 같은 블로그다
        pub = FakePublisher(blog_url="http://macat0722.blogspot.com")
        self.assertEqual(self.r.run("draft", ALL_ENV, pub).code, 0)

    def test_a_missing_gemini_key_stops_before_blogger_is_contacted(self):
        """오프라인으로 알 수 있는 설정 오류(LLM 키 없음)는 네트워크가 필요한 인증 점검보다 먼저 멈춘다."""
        pub = FakePublisher()
        res = self.r.run("draft", {name: SECRET_VALUES[name] for name in SECRET_NAMES}, pub, llm=None)
        self.assertEqual((res.code, res.skips, res.history, pub.health_calls), (2, ["SECRETS_MISSING"], [], 0))
        self.assertIn("GEMINI_API_KEY", res.annotations[0])

    def test_the_auth_check_passes_once_and_is_logged(self):
        pub = FakePublisher()
        res = self.r.run("draft", ALL_ENV, pub)
        self.assertEqual(pub.health_calls, 1)
        self.assertIn("인증 점검 통과", res.out)

    def test_exceptions_outside_the_adapter_are_recorded_and_the_draft_file_is_kept(self):
        leaked = " ".join(SECRET_VALUES.values())
        for label, error in (("KeyError", KeyError("boom")), ("RuntimeError", RuntimeError(f"unexpected {leaked}"))):
            for mode, noun in (("draft", "Blogger 초안함 업로드"), ("auto", "게시")):
                with self.subTest(label=label, mode=mode):
                    pub = FakePublisher(fail=error)
                    res = self.r.run(mode, ALL_ENV, pub)
                    self.assertEqual(res.code, 1, res.out)
                    self.assertEqual(res.last["status"], "publish_failed")
                    self.assertTrue(res.last["reasons"][0].startswith(f"[unexpected] {label}"), res.last["reasons"])
                    self.assertEqual(len(res.drafts), 1)                         # 초안 파일 보존
                    self.assertIn("status: publish_failed", next(iter(res.drafts.values())))
                    self.assertEqual(res.skips, ["PUBLISH_FAILED"])
                    self.assertIn("reason=unexpected", res.out)
                    self.assertEqual(len(res.annotations), 1)
                    self.assertTrue(res.annotations[0].startswith(f"::error::[blogger_macat] {noun} 중 예기치 않은 오류가 났습니다"))
                    self.assertNotIn(label, res.annotations[0])                  # 고정 문장: 예외 이름도 넣지 않는다
                    self.assertTrue(any("사유" in line for line in res.summary_lines))
                    for value in SECRET_VALUES.values():
                        self.assertNotIn(value, res.everything())

    def test_exceptions_while_creating_or_checking_the_publisher_are_auth_check_failures(self):
        def broken_factory(blog, environ):
            raise ImportError("No module named 'google'")
        res = self.r.run("draft", ALL_ENV, factory=broken_factory)
        self.assertEqual((res.code, res.skips, res.last["status"]), (1, ["AUTH_CHECK_FAILED"], "publish_failed"))
        self.assertIn("reason=unexpected exit=1", res.out)
        self.assertIn("ImportError", res.last["reasons"][0])
        res = self.r.run("draft", ALL_ENV, FakePublisher(check=KeyError("x")))
        self.assertEqual((res.code, res.skips), (1, ["AUTH_CHECK_FAILED"]))
        self.assertEqual(res.llm_calls.calls, 0)

    def test_incomplete_publish_results_are_never_recorded_as_uploaded(self):
        class NoneResult(FakePublisher):
            def publish(self, title, html, labels, draft=False):
                return None
        # 글 ID 가 없으면 초안함 업로드도 즉시 게시도 실패다. 주소(url)가 없으면 즉시 게시만 실패이고 초안은 글 ID 만 있으면 성공이다(V-03)
        for label, pub in (("글 ID 없음", FakePublisher(result=PublishResult(post_id="", url="https://macat.example/p1"))),
                           ("결과 없음", NoneResult())):
            for mode in ("draft", "auto"):
                with self.subTest(label=label, mode=mode):
                    res = self.r.run(mode, ALL_ENV, pub)
                    self.assertEqual((res.code, res.last["status"]), (1, "publish_failed"))
                    self.assertIn("[bad_response]", res.last["reasons"][0])
                    self.assertEqual((res.last["url"], len(res.drafts)), ("", 1))
        res = self.r.run("auto", ALL_ENV, FakePublisher(result=PublishResult(post_id="p9", url="")))     # 즉시 게시는 주소가 필수
        self.assertEqual((res.code, res.last["status"], res.last["post_id"], res.last["url"]), (1, "publish_failed", "p9", ""))
        self.assertIn("[bad_response]", res.last["reasons"][0])                  # 주소만 빠졌으면 글 ID 는 남겨 Blogger 에서 찾게 한다

    def test_a_draft_without_a_url_is_still_recorded_as_uploaded_and_tells_the_operator_to_look_in_blogger(self):
        pub = FakePublisher(result=PublishResult(post_id="p9", url=""))
        res = self.r.run("draft", ALL_ENV, pub)
        self.assertEqual((res.code, res.skips, res.annotations), (0, [], []))
        self.assertEqual((res.last["status"], res.last["post_id"], res.last["url"]), ("draft_uploaded", "p9", ""))
        self.assertEqual(len(res.drafts), 1)
        self.assertNotIn("url:", next(iter(res.drafts.values())).split("---")[1])           # 빈 주소는 사본 머리말에 쓰지 않는다
        self.assertIn("(없음)", res.summary_lines[2])
        self.assertIn("주소 없음", res.out)                                        # 로그에도 빈칸이 아니라 이유를 적는다
        self.assertIn("응답에 글 주소(url)가 없어", res.summary)
        self.assertIn("Blogger 화면에서 확인", res.summary)
        # 글은 올라갔으므로 같은 날 다시 올리지 않는다
        again = self.r.run("draft", ALL_ENV, FakePublisher(), history=res.history)
        self.assertEqual((again.code, again.skips), (0, ["DAILY_CAP"]))

    def test_a_failed_upload_that_left_a_post_id_uses_up_the_day_and_says_why(self):
        """글 ID 가 남은 publish_failed 는 초안이 이미 만들어졌을 수 있다. 같은 날 재실행이 초안을 또 만들지 않게 하루 상한에 센다(V-02)."""
        for label, pub in (("응답 검사 실패", FakePublisher(fail=PublishError("응답에 주소가 없습니다", code="bad_response", post_id="77"))),
                           ("즉시 게시 주소 없음", FakePublisher(result=PublishResult(post_id="77", url="")))):
            mode = "auto" if "즉시" in label else "draft"
            with self.subTest(label):
                first = self.r.run(mode, ALL_ENV, pub)
                self.assertEqual((first.code, first.last["status"], first.last["post_id"]), (1, "publish_failed", "77"))
                self.assertIn("글 ID: 77", first.summary)                      # 실패한 실행의 요약에도 정리할 글 ID 가 남는다
                retry_pub = FakePublisher()
                retry = self.r.run(mode, ALL_ENV, retry_pub, history=first.history)
                self.assertEqual((retry.code, retry.skips), (0, ["DAILY_CAP"]))
                self.assertEqual((retry_pub.health_calls, retry_pub.published, len(retry.history)), (0, [], 1))   # 다시 올리지 않는다
                self.assertIn("publish_failed", retry.annotations[0])
                self.assertIn("글 ID", retry.annotations[0])                       # 왜 세었는지 드러난다
                self.assertIn("Blogger", retry.summary)
                self.assertIn("확인", retry.summary)
                # 수동 주제 지정은 상한을 건너뛴다(운영자가 초안함을 확인한 뒤의 선택)
                forced = self.r.run(mode, ALL_ENV, FakePublisher(), history=first.history, extra=["--topic", "수동으로 지정한 오늘의 생활 습관 주제"])
                self.assertEqual((forced.code, forced.last["status"]), (0, "draft_uploaded" if mode == "draft" else "posted"))

    def test_a_failure_without_a_post_id_still_does_not_use_up_the_day(self):
        for entry in ({"status": "publish_failed", "post_id": ""}, {"status": "publish_failed"}, {"status": "publish_failed", "post_id": "  "},
                      {"status": "rejected", "post_id": "77"}, {"status": "llm_failed", "post_id": "77"}):
            with self.subTest(entry):
                history = [{**TODAY_ENTRY, **entry}]
                res = self.r.run("draft", ALL_ENV, FakePublisher(), history=history)
                self.assertEqual((res.code, res.skips, res.last["status"]), (0, [], "draft_uploaded"))

    def test_a_failure_after_the_post_exists_keeps_its_id_for_cleanup(self):
        pub = FakePublisher(fail=PublishError("응답에 주소가 없습니다", code="bad_response", post_id="77"))
        res = self.r.run("draft", ALL_ENV, pub)
        self.assertEqual((res.code, res.last["status"], res.last["post_id"]), (1, "publish_failed", "77"))

    def test_secret_values_never_reach_the_log_the_summary_the_history_or_the_draft_files(self):
        leaked = " ".join(f"{name}={value}" for name, value in SECRET_VALUES.items()) + f" key={GEMINI_VALUE}"
        cases = {"인증 점검": FakePublisher(check=PublishError(f"fail {leaked}", code="auth_failed")),
                 "게시 실패": FakePublisher(fail=PublishError(f"fail {leaked}", code="api_error")),
                 "예기치 않은 예외": FakePublisher(fail=ValueError(leaked))}
        for label, pub in cases.items():
            with self.subTest(label):
                res = self.r.run("draft", ALL_ENV, pub)
                self.assertNotEqual(res.code, 0)
                self.assertIn("***", res.everything())                           # 가려졌다는 흔적
                for value in EVERY_SECRET_VALUE:
                    self.assertNotIn(value, res.everything())
        def llm_down(prompt):
            raise LLMError(f"all models failed {leaked}")
        res = self.r.run("draft", ALL_ENV, FakePublisher(), llm=llm_down)
        for value in EVERY_SECRET_VALUE:
            self.assertNotIn(value, res.everything())

    def test_server_text_cannot_forge_workflow_commands(self):
        forged = "HTTP 500\r::error::위조된 줄\n##[error]가짜 로그"
        for pub in (FakePublisher(check=PublishError(forged, code="api_error")),
                    FakePublisher(fail=PublishError(forged, code="api_error")), FakePublisher(fail=RuntimeError(forged))):
            res = self.r.run("draft", ALL_ENV, pub)
            self.assertNotEqual(res.code, 0)
            self.assertNotIn("\r", res.out)
            self.assertEqual(len([line for line in res.lines if line.lstrip().startswith(("::", "##["))]), 1, res.out)
            self.assertNotIn("위조된", res.annotations[0])
            for line in res.summary_lines:
                self.assertFalse(line.lstrip().startswith(("::", "##[")))
            self.assertEqual(len([line for line in res.summary_lines if line.startswith("#")]), 1, res.summary)

    def test_invalid_publish_value_is_a_config_error_that_reaches_nothing(self):
        for value in ("yolo", "drfat", "publsh", "2", "true false"):
            with self.subTest(value):
                res = self.r.run("auto", {**ALL_ENV, "BLOGGER_PUBLISH": value}, factory=must_not_be_called)
                self.assertEqual((res.code, res.skips, res.history, res.llm_calls.calls), (2, ["INVALID_PUBLISH"], [], 0))
                self.assertNotIn(value, res.annotations[0])                      # 입력한 값은 문구에 넣지 않는다

    def test_pause_and_mode_off_win_over_every_input(self):
        for policy in (None, "auto", "on", "publish", "draft", "off", "yolo"):
            for env_extra, mode, code in (({"PIPELINE_PAUSE": "true"}, "draft", "PAUSED"), ({}, "off", "MODE_OFF")):
                with self.subTest(policy=policy, code=code):
                    env = {**ALL_ENV, **env_extra, **({} if policy is None else {"BLOGGER_PUBLISH": policy})}
                    res = self.r.run(mode, env, factory=must_not_be_called)
                    self.assertEqual((res.code, res.skips, res.history, res.llm_calls.calls), (0, [code], [], 0))

    def test_watchdog_treats_uploaded_drafts_as_real_posts_and_does_not_alarm_in_draft_mode(self):
        res = self.r.run("draft", ALL_ENV, FakePublisher())
        later = datetime(2026, 10, 21, 8, 0, tzinfo=timezone.utc)
        self.assertEqual(health.post_days_from_history(res.history), {NOW.astimezone(KST).date()})
        blog = registry.get_blog(registry.load_registry(REAL / "pipeline" / "blogs.json"), "blogger_macat")
        self.assertEqual(health.evaluate({**blog, "mode": "draft"}, res.history, later), [])
        self.assertEqual(health.evaluate({**blog, "mode": "auto"}, res.history, later), [])

    def test_statuses_and_the_daily_cap_agree_with_the_watchdog(self):
        self.assertEqual(run_mod.COUNTED_STATUSES, {"posted", "draft", "draft_uploaded", "generated_unpublished"})
        self.assertLessEqual(health.REAL_POST_STATUSES, run_mod.COUNTED_STATUSES)   # 독자에게 가는(또는 초안함에 올린) 글은 상한에 센다
        self.assertEqual(run_mod.COUNTED_STATUSES - health.REAL_POST_STATUSES, {"draft", "generated_unpublished"})
        for status in ("publish_failed", "rejected", "llm_failed", "skipped_no_topic"):
            self.assertNotIn(status, run_mod.COUNTED_STATUSES)

    def test_architecture_doc_describes_the_new_status_and_the_cap(self):
        text = (REAL / "docs" / "ARCHITECTURE.md").read_text(encoding="utf-8")
        section = text[text.index("## 5."):text.index("## 6.")]
        self.assertIn("`draft_uploaded`", section)
        cap_line = next(line for line in section.splitlines() if "일일 상한" in line)
        self.assertIn("건수가", cap_line)
        self.assertEqual(set(re.findall(r"`(\w+)`", cap_line.split("건수가")[0])), run_mod.COUNTED_STATUSES)   # 문서의 상태 목록 = 코드


class ReviewFollowUpTest(unittest.TestCase):
    """독립 검증(V-01~V-11) 지적을 고정하는 시험: 어댑터 경고 줄, 이력·초안 파일 쓰기 실패, 응답 속 식별자 가림, 요약 마크다운,
    고정 안내 문장, 수동 주제·스위치 값, 워크플로의 연습 실행 전달."""

    def setUp(self):
        self.r = Runner(self)

    def test_adapter_notes_are_printed_masked_and_folded(self):
        leaky = f"중복 글 확인에 실패해 건너뜁니다(TypeError): key {SECRET_VALUES['BLOGGER_BLOG_ID']}\r::error::위조된 줄\n두 번째 줄"
        for pub in (FakePublisher(notes=[leaky]), FakePublisher(notes=[leaky], fail=PublishError("x", code="network"))):
            res = self.r.run("draft", ALL_ENV, pub)
            self.assertIn("[참고] 중복 글 확인에 실패해 건너뜁니다(TypeError)", res.out)
            self.assertNotIn(SECRET_VALUES["BLOGGER_BLOG_ID"], res.everything())
            self.assertNotIn("\r", res.out)
            errors = [line for line in res.lines if line.lstrip().startswith(("::error::", "##["))]
            self.assertEqual(len(errors), len([a for a in res.annotations if a.startswith("::error::")]))   # 위조된 줄이 명령이 되지 않는다
            self.assertTrue(all("위조된" not in line for line in res.annotations))
        res = self.r.run("draft", ALL_ENV, FakePublisher())
        self.assertNotIn("[참고]", res.out)                                       # 노트가 없으면 줄도 없다

    def test_a_history_write_failure_after_the_upload_is_reported_with_the_upload_result(self):
        pub = FakePublisher()
        with mock.patch.object(run_mod, "write_json_atomic", side_effect=OSError("disk full")):
            res = self.r.run("draft", ALL_ENV, pub)                               # 예외로 죽지 않는다
        self.assertEqual(res.code, 1)
        self.assertEqual(len(pub.published), 1)                                    # 업로드는 이미 됐다
        self.assertEqual(res.history, [])                                          # 이력은 못 썼다
        errors = [a for a in res.annotations if a.startswith("::error::")]
        self.assertEqual(len(errors), 1, res.annotations)
        self.assertIn("이력", errors[0])
        self.assertIn("Blogger 초안함", errors[0])                                  # 같은 날 다시 실행하기 전에 확인하게 한다
        self.assertNotIn("disk full", errors[0])                                   # 고정 문장
        self.assertIn("https://macat.example/p1", res.out)                         # 업로드 결과(주소·글 ID)는 로그에 남는다
        self.assertIn("p1", res.out)
        self.assertEqual(len(res.drafts), 1)                                       # 저장소 초안 파일은 이력과 따로 남긴다
        self.assertIn("이력 기록 실패", res.summary)
        self.assertIn("https://macat.example/p1", res.summary)
        self.assertEqual(res.skips, ["HISTORY_WRITE_FAILED"])                      # 로그에서 [SKIP] 으로 한 번에 찾는다
        self.assertIn("글 ID p1", res.out)                                         # 결과를 한 줄로도 남긴다(주소·글 ID·상태)
        self.assertIn("상태 draft_uploaded", res.out)

    def test_the_history_is_written_before_the_draft_file(self):
        """이력이 같은 글을 두 번 올리지 않게 막는 기준이라 파일 저장보다 먼저 쓴다. 파일 저장이 실패해도 이력은 남는다."""
        order = []
        real_record, real_save = run_mod.write_json_atomic, run_mod.save_draft

        def spy_history(*args, **kwargs):
            order.append("history")
            return real_record(*args, **kwargs)

        def spy_draft(*args, **kwargs):
            order.append("draft")
            return real_save(*args, **kwargs)
        with mock.patch.object(run_mod, "write_json_atomic", spy_history), mock.patch.object(run_mod, "save_draft", spy_draft):
            self.r.run("draft", ALL_ENV, FakePublisher())
        self.assertEqual(order, ["history", "draft"])
        with mock.patch.object(run_mod, "save_draft", side_effect=OSError("read-only")):
            res = self.r.run("draft", ALL_ENV, FakePublisher())
        self.assertEqual((res.code, res.last["status"]), (0, "draft_uploaded"))       # 업로드·이력은 성공이라 초록
        warnings = [a for a in res.annotations if a.startswith("::warning::")]
        self.assertEqual(len(warnings), 1, res.annotations)
        self.assertIn("초안 파일", warnings[0])
        self.assertNotIn("read-only", warnings[0])
        self.assertIn("초안 파일", res.summary)

    def test_when_the_repository_file_is_the_only_result_a_failed_save_is_red(self):
        """Blogger 에 올리지 않는 실행(시크릿 없음·publish=off)은 저장소 초안 파일이 유일한 결과물이다. 못 썼는데 초록이면 글이 사라진다."""
        for env, extra in ((LLM_ONLY_ENV, []), (ALL_ENV, ["--publish", "off"])):
            with self.subTest(env=sorted(env), extra=extra):
                with mock.patch.object(run_mod, "save_draft", side_effect=OSError("read-only")):
                    res = self.r.run("draft", env, factory=must_not_be_called, extra=extra)
                self.assertEqual(res.code, 1)
                errors = [a for a in res.annotations if a.startswith("::error::")]
                self.assertEqual(len(errors), 1, res.annotations)
                self.assertIn("저장소 초안 파일", errors[0])
                self.assertNotIn("read-only", errors[0])
                self.assertEqual([a for a in res.annotations if a.startswith("::warning::")], [])
                self.assertIn("초안 파일 저장 실패", res.summary)

    def test_both_writes_failing_is_red_with_two_fixed_annotations_and_still_prints_the_result(self):
        with mock.patch.object(run_mod, "write_json_atomic", side_effect=OSError("a")), \
                mock.patch.object(run_mod, "save_draft", side_effect=OSError("b")):
            res = self.r.run("auto", ALL_ENV, FakePublisher())
        self.assertEqual(res.code, 1)
        self.assertEqual(len([a for a in res.annotations if a.startswith("::error::")]), 1)
        self.assertEqual(len([a for a in res.annotations if a.startswith("::warning::")]), 1)
        self.assertIn("https://macat.example/p1", res.out)

    def test_a_publish_failure_whose_history_write_also_fails_does_not_lose_the_failure_report(self):
        with mock.patch.object(run_mod, "write_json_atomic", side_effect=OSError("disk full")):
            res = self.r.run("draft", ALL_ENV, FakePublisher(fail=PublishError("x", code="api_error", post_id="77")))
        self.assertEqual(res.code, 1)
        self.assertIn("reason=api_error target=draft", res.out)
        self.assertIn("77", res.out)                                               # 정리할 수 있게 글 ID 는 로그에 남는다

    def test_google_project_numbers_and_blog_ids_in_responses_never_reach_the_outputs(self):
        project, blog_id = PROJECT_NUMBER, SECRET_VALUES["BLOGGER_BLOG_ID"]
        text = f"Blogger API has not been used in project {project} before or it is disabled."
        for label, pub in (("인증 점검", FakePublisher(check=PublishError(text, code="auth_failed"))),
                           ("게시 실패", FakePublisher(fail=PublishError(text, code="api_error"))),
                           ("예기치 않은 예외", FakePublisher(fail=RuntimeError(text)))):
            with self.subTest(label):
                res = self.r.run("draft", ALL_ENV, pub)
                self.assertNotEqual(res.code, 0)
                self.assertNotIn(project, res.everything())
        # 응답 주소·글 ID 속 블로그 ID
        result = PublishResult(post_id=f"{blog_id}-p1", url=f"https://www.blogger.com/blog/post/edit/{blog_id}/p1")
        for mode in ("draft", "auto"):
            res = self.r.run(mode, ALL_ENV, FakePublisher(result=result))
            self.assertEqual(res.code, 0, res.out)
            self.assertNotIn(blog_id, res.everything())
            self.assertIn("***", res.last["url"])
            self.assertIn("***", res.last["post_id"])
        # 실패 응답에 실린 글 ID 에도 블로그 ID 가 섞여 올 수 있다
        res = self.r.run("draft", ALL_ENV, FakePublisher(fail=PublishError("x", code="bad_response", post_id=f"{blog_id}-p7")))
        self.assertEqual((res.code, res.last["status"]), (1, "publish_failed"))
        self.assertNotIn(blog_id, res.everything())
        self.assertIn("***", res.last["post_id"])

    def test_the_summary_url_line_neutralizes_markdown_and_html(self):
        nasty = "https://macat.example/p?x=[a](https://evil.example)|<b>`t`"
        for mode in ("draft", "auto"):
            res = self.r.run(mode, ALL_ENV, FakePublisher(result=PublishResult(post_id="p1", url=nasty)))
            self.assertEqual(res.code, 0)
            line = next(line for line in res.summary_lines if line.startswith("- URL:"))
            for char in "|<>`":
                self.assertNotIn(char, line)
            self.assertNotIn("](", line)
            self.assertIn("macat.example", line)
            self.assertEqual(len([line for line in res.summary_lines if line.startswith("#")]), 1)

    def test_the_log_reads_as_an_upload_for_drafts_and_as_a_publication_for_live_posts(self):
        res = self.r.run("draft", ALL_ENV, FakePublisher())
        self.assertIn("Blogger 초안함에 업로드했습니다(공개되지 않음)", res.out)
        self.assertNotIn("게시 성공", res.out)
        res = self.r.run("auto", ALL_ENV, FakePublisher())
        self.assertIn("게시 성공", res.out)
        self.assertNotIn("초안함에 업로드했습니다", res.out)

    def test_failure_annotations_tell_the_operator_to_look_in_blogger_before_running_again(self):
        for mode, phrase in (("draft", "초안이 만들어졌을 수 있으니 재실행 전에 Blogger 초안함을 확인하세요"),
                             ("auto", "글이 올라갔을 수 있으니 재실행 전에 Blogger 글 목록을 확인하세요")):
            for pub in (FakePublisher(fail=PublishError("x", code="network")), FakePublisher(fail=KeyError("x")),
                        FakePublisher(fail=PublishError("x", code="bad_response", post_id="7"))):
                with self.subTest(mode=mode, pub=type(pub.fail).__name__):
                    res = self.r.run(mode, ALL_ENV, pub)
                    errors = [a for a in res.annotations if a.startswith("::error::")]
                    self.assertEqual(len(errors), 1)
                    self.assertIn(phrase, errors[0])

    def test_the_manual_topic_environment_variable_works_like_the_option(self):
        """워크플로는 수동 주제를 환경변수(BLOGGER_TOPIC)로만 넘긴다. 지정하면 하루 상한을 건너뛰고, 비어 있으면(정기 실행) 쓰이지 않는다."""
        topic = "수동으로 지정한 오늘의 생활 습관 주제"
        res = self.r.run("draft", {**ALL_ENV, "BLOGGER_TOPIC": topic}, FakePublisher(), history=[TODAY_ENTRY])
        self.assertEqual((res.code, res.last["topic"], res.last["topic_source"]), (0, topic, "override"))
        for empty in ("", "   "):
            res = self.r.run("draft", {**ALL_ENV, "BLOGGER_TOPIC": empty}, FakePublisher(), history=[TODAY_ENTRY])
            self.assertEqual((res.code, res.skips), (0, ["DAILY_CAP"]))

    def test_switch_values_ignore_case_and_surrounding_spaces(self):
        on = ("1", "true", "True", "TRUE", "yes", "YES", "on", "On", " true ", "\tTrue\n")
        off = ("0", "false", "no", "off", "", "  ", "maybe", "2", "truee")
        for value in on:
            with self.subTest(switch="DRY_RUN", value=value):
                res = self.r.run("draft", {**ALL_ENV, "DRY_RUN": value}, factory=must_not_be_called)
                self.assertEqual((res.code, res.history), (0, []))
                self.assertIn("[DRY_RUN]", res.out)
            with self.subTest(switch="PIPELINE_PAUSE", value=value):
                res = self.r.run("draft", {**ALL_ENV, "PIPELINE_PAUSE": value}, factory=must_not_be_called)
                self.assertEqual((res.code, res.skips), (0, ["PAUSED"]))
        for value in off:
            for switch in ("DRY_RUN", "PIPELINE_PAUSE"):
                with self.subTest(switch=switch, value=value):
                    res = self.r.run("draft", {**ALL_ENV, switch: value}, FakePublisher())
                    self.assertEqual((res.code, res.last["status"]), (0, "draft_uploaded"))

    def test_the_stale_publish_checkbox_wording_is_gone_from_the_operator_docs(self):
        stale = {"HANDLER.md": ("`publish`를 체크하지 말고", "L3 초안 1건(`publish` 끔)", "결정 — **A(풀오토 API 게시)**로 진행"),
                 "docs/ENGINEERING_GUIDE.md": ("(`publish` 미체크)",),
                 "docs/CHARTER.md": ("`draft`(초안만)",)}
        for rel, phrases in stale.items():
            text = (REAL / rel).read_text(encoding="utf-8")
            for phrase in phrases:
                self.assertNotIn(phrase, text, f"{rel} 에 낡은 문구가 남아 있습니다: {phrase}")
        health_test = (REAL / "tests" / "test_health_daily.py").read_text(encoding="utf-8")
        self.assertNotIn("Blogger 초안 모드(후속 작업)용 예약 상태 이름이다", health_test)
        # 새 절차: 연습 실행을 풀고, 인증 점검 → T3 로 mode draft → 수동 publish=draft
        handler = (REAL / "HANDLER.md").read_text(encoding="utf-8")
        resume = next(line for line in handler.splitlines() if line.startswith("**재개 절차(Blogger)**"))
        for phrase in ("인증 점검만 실행", "`연습 실행` 체크를 푼", "publish=draft", "mode: draft"):
            self.assertIn(phrase, resume)                                          # 재개 절차 한 줄 안에서 이 순서로 안내한다
        self.assertLess(resume.index("인증 점검만 실행"), resume.index("mode: draft` 전환"))
        self.assertLess(resume.index("mode: draft` 전환"), resume.index("publish=draft"))
        self.assertIn("`연습 실행` 체크를 푼", handler[handler.index("4. Actions → **[Blogger] 글 자동 작성(초안함 업로드)**"):])   # §10 5-4 도 같은 안내

    def test_docs_state_that_a_manual_publish_choice_can_post_live_even_in_draft_mode(self):
        for rel in ("docs/ARCHITECTURE.md", ".github/editorial/BLOGGER_API_SETUP.md"):
            text = (REAL / rel).read_text(encoding="utf-8")
            self.assertRegex(text, r"mode: draft.{0,40}publish.{0,60}즉시 게시.{0,60}T3", rel)

    def test_architecture_documents_the_post_id_cap_rule_the_write_order_and_the_explicit_mode_rule(self):
        arch = (REAL / "docs" / "ARCHITECTURE.md").read_text(encoding="utf-8")
        section5 = arch[arch.index("## 5."):arch.index("## 6.")]
        cap_line = next(line for line in section5.splitlines() if "일일 상한" in line)
        self.assertIn("`post_id`", cap_line)
        self.assertIn("publish_failed", cap_line)
        self.assertIn("이력을 먼저", arch)                                          # 이력 → 파일 순서
        self.assertNotIn("같은 날 같은 글이 두 번 올라가는 것은 이력으로 막는다(상한과 제목 중복 게이트 DUP_SAME; 운영자가 Blogger에서 초안을 지웠는지는 알 수 없다).", arch)
        section7 = arch[arch.index("### A."):arch.index("### B.")]
        row = next(line for line in section7.splitlines() if "`blogs.json`에 항목 추가" in line)
        self.assertIn("mode", row)
        self.assertIn("직접", row)
        self.assertIn("REG-1", row)

    def test_defect_register_states_the_check_order_and_corrects_the_timeout_claim(self):
        register = (REAL / "docs" / "DEFECT_REGISTER.md").read_text(encoding="utf-8")
        row = next(line for line in register.splitlines() if line.startswith("| **D-55**"))
        self.assertIn("인증 점검은 글 생성(Gemini) 앞", row)
        self.assertIn("클라이언트 타임아웃", row)
        self.assertIn("60초", row)
        self.assertIn("120초", row)


class PolicyTest(unittest.TestCase):
    def test_publish_policy_values_and_aliases(self):
        table = {None: "auto", "": "auto", "auto": "auto", "AUTO": "auto", " auto ": "auto",
                 "on": "on", "1": "on", "true": "on", "TRUE": "on", "yes": "on", "publish": "on", "Publish": "on",
                 "draft": "draft", "DRAFT": "draft", "off": "off", "0": "off", "false": "off", "no": "off", "OFF": "off"}
        for value, expected in table.items():
            env = {} if value is None else {"BLOGGER_PUBLISH": value}
            self.assertEqual(run_mod.publish_policy(None, env), expected, repr(value))
        for bad in ("yolo", "drfat", "2", "on off", "publish!", "none"):
            self.assertIsNone(run_mod.publish_policy(None, {"BLOGGER_PUBLISH": bad}), bad)

    def test_the_command_line_option_wins_over_the_environment(self):
        self.assertEqual(run_mod.publish_policy("draft", {"BLOGGER_PUBLISH": "off"}), "draft")
        self.assertEqual(run_mod.publish_policy("publish", {}), "on")
        self.assertEqual(run_mod.publish_policy("off", {"BLOGGER_PUBLISH": "publish"}), "off")
        self.assertEqual(run_mod.parse_args(["--blog", "x", "--publish", "draft"]).publish, "draft")
        self.assertEqual(run_mod.parse_args(["--blog", "x", "--publish", "publish"]).publish, "publish")
        with self.assertRaises(SystemExit):
            run_mod.parse_args(["--blog", "x", "--publish", "yolo"])

    def test_delivery_table(self):
        table = {("on", "auto"): "publish", ("on", "draft"): "publish", ("draft", "auto"): "draft", ("draft", "draft"): "draft",
                 ("off", "auto"): "file", ("off", "draft"): "file", ("auto", "auto"): "publish", ("auto", "draft"): "draft",
                 ("auto", "off"): "file"}
        for (policy, mode), expected in table.items():
            self.assertEqual(run_mod.decide_delivery(policy, mode), expected, (policy, mode))


# ----------------------------------------------------------------------------
# 2) 열거
# ----------------------------------------------------------------------------
# 'auto'·'publish' 는 '없음'·'on' 과 같은 값으로 읽히는 별칭이라 열거에서는 뺐다(PolicyTest·ScenarioTest 가 따로 확인한다)
POLICIES = (None, "on", "draft", "off", "yolo")
POLICY_OF = {None: "auto", "auto": "auto", "on": "on", "publish": "on", "draft": "draft", "off": "off"}


def model_inputs(mode, policy, dry, missing, cap):
    """문서(docs/ARCHITECTURE.md §4-1 '처리 순서')를 그대로 옮긴 기준 모델 — 입력 조건 단계.
    돌려주는 값: (종료 코드, [SKIP] 코드 목록, 새 이력 상태 또는 None, publish 호출의 draft 플래그 목록, 인증 점검 호출 수)."""
    if mode == "off":
        return 0, ["MODE_OFF"], None, [], 0
    pol = POLICY_OF.get(policy)
    if pol is None:
        return 2, ["INVALID_PUBLISH"], None, [], 0
    delivery = {"on": "publish", "draft": "draft", "off": "file"}.get(pol) or ("publish" if mode == "auto" else "draft")
    skips = []
    if missing and (delivery == "publish" or (delivery == "draft" and missing < len(SECRET_NAMES))):
        if not dry:
            return 2, ["SECRETS_MISSING"], None, [], 0
    elif missing and delivery == "draft":
        delivery = "file"
        skips.append("UPLOAD_SKIPPED")
    if cap:
        return 0, skips + ["DAILY_CAP"], None, [], 0
    if dry:
        return 0, skips, None, [], 0
    calls = {"publish": [False], "draft": [True], "file": []}[delivery]
    return 0, skips, {"publish": "posted", "draft": "draft_uploaded", "file": "draft"}[delivery], calls, (1 if calls else 0)


def check_invariants(res, mode, policy, dry, before):
    """어느 조합에서도 지켜야 하는 불변식. 어긋난 것을 문자열 목록으로 돌려준다."""
    bad = []
    new = res.history[len(before):]
    gained = [e["status"] for e in new]
    if res.history[:len(before)] != before:
        bad.append("기존 이력이 바뀜")
    if res.code == 0 and not (res.skips or gained or "[DRY_RUN]" in res.out):
        bad.append("이유 없이 초록(건너뜀 코드·새 기록·연습 표시가 모두 없음)")
    if res.code != 0 and len([a for a in res.annotations if a.startswith("::error::")]) != 1:
        bad.append(f"빨강인데 ::error:: 주석이 1개가 아님: {res.annotations}")
    if "### blogger_macat" not in res.summary:
        bad.append("실행 요약이 없음")
    pub = res.publisher
    live = [p for p in pub.published if not p["draft"]] if pub else []
    allowed_live = POLICY_OF.get(policy) == "on" or (POLICY_OF.get(policy) == "auto" and mode == "auto")
    if live and not allowed_live:
        bad.append("허용되지 않은 즉시 게시")
    if pub and len(pub.published) > 1:
        bad.append("글이 두 번 올라감")
    if dry and (new or res.drafts or (pub and (pub.health_calls or pub.published))):
        bad.append("연습 실행이 기록·초안·Blogger 접속을 만듦")
    if len(gained) > 1:
        bad.append(f"한 실행에 이력이 {len(gained)}건 생김")
    for value in EVERY_SECRET_VALUE:
        if value in res.everything():
            bad.append("시크릿 값이 출력에 나옴")
    return bad


class NoneResultPublisher(FakePublisher):
    """publish() 가 결과 객체 대신 None 을 돌려주는 어댑터."""

    def publish(self, title, html, labels, draft=False):
        return None


class Combined:
    """인증 점검은 auth_pub 이, 글 게시는 pub 이 맡는 게시자(두 단계를 따로 시나리오로 만들려고)."""

    def __init__(self, auth_pub, pub):
        self.auth_pub, self.pub = auth_pub, pub

    def healthcheck(self):
        return self.auth_pub.healthcheck()

    def publish(self, title, html, labels, draft=False):
        return self.pub.publish(title, html, labels, draft=draft)


def raising_factory(blog, environ):
    raise ImportError("No module named 'google'")


def llm_down(prompt):
    raise LLMError("all models failed")


OK_URL = "https://macat.example/p1"
# 인증 점검 단계의 결과: 이름 → (게시자 만드는 함수 — None 이면 게시자 생성이 실패, 기대 종료 코드, 기대 분류)
AUTH_STAGE = {
    "auth_expired": (lambda: FakePublisher(check=PublishError("x", "auth_expired")), 1, "auth_expired"),
    "auth_failed": (lambda: FakePublisher(check=PublishError("x", "auth_failed")), 2, "auth_failed"),
    "blog_mismatch": (lambda: FakePublisher(blog_url="https://other.blogspot.com/"), 2, "blog_mismatch"),
    "network": (lambda: FakePublisher(check=PublishError("x", "network")), 1, "network"),
    "bad_response": (lambda: FakePublisher(check=PublishError("x", "bad_response")), 1, "bad_response"),
    "api_error": (lambda: FakePublisher(check=PublishError("x", "api_error")), 1, "api_error"),
    "새 분류": (lambda: FakePublisher(check=PublishError("x", "something_new")), 1, "api_error"),
    "주소 없는 응답": (lambda: FakePublisher(blog_url=""), 1, "bad_response"),
    "예외": (lambda: FakePublisher(check=KeyError("x")), 1, "unexpected"),
    "게시자 생성 실패": (lambda: None, 1, "unexpected"),
}
# 글 생성 단계가 실패하는 결과: 이름 → (LLM 함수, 이력 시작 상태, 기대 종료 코드, 이력 상태, [SKIP] 코드, LLM 호출 수)
LLM_STAGE = {
    "LLM 실패": (llm_down, None, 1, "llm_failed", "LLM_FAILED", 1),
    "게이트 탈락": (lambda prompt: SHORT_POST, None, 0, "rejected", "GATE_REJECTED", 3),     # 재작성 3번
    "주제 없음": (lambda prompt: ("[]", "m"), seed_history(), 0, "skipped_no_topic", "NO_TOPIC", 1),
    "주제 확장 실패": (llm_down, seed_history(), 1, "llm_failed", "EXPAND_FAILED", 1),
}
# 게시 단계의 결과: 이름 → (게시자 만드는 함수, 기대 분류 — None 이면 성공)
PUBLISH_STAGE = {
    "성공": (FakePublisher, None),
    "auth_expired": (lambda: FakePublisher(fail=PublishError("x", "auth_expired")), "auth_expired"),
    "auth_failed": (lambda: FakePublisher(fail=PublishError("x", "auth_failed")), "auth_failed"),
    "network": (lambda: FakePublisher(fail=PublishError("x", "network")), "network"),
    "bad_response": (lambda: FakePublisher(fail=PublishError("x", "bad_response")), "bad_response"),
    "api_error": (lambda: FakePublisher(fail=PublishError("x", "api_error")), "api_error"),
    "새 분류": (lambda: FakePublisher(fail=PublishError("x", "something_new")), "api_error"),
    "예외": (lambda: FakePublisher(fail=KeyError("x")), "unexpected"),
    "글 ID 없음": (lambda: FakePublisher(result=PublishResult(post_id="", url=OK_URL)), "bad_response"),
    # 주소가 비면 즉시 게시만 실패하고, 초안은 글 ID 만 있으면 성공이다(전달 방식별 기대 분류)
    "주소 없음": (lambda: FakePublisher(result=PublishResult(post_id="p1", url="")), {"draft": None, "publish": "bad_response"}),
    "결과 없음": (NoneResultPublisher, "bad_response"),
}


class EnumerationTest(unittest.TestCase):
    def test_every_input_combination_matches_the_reference_model(self):
        """입력 조건 열거: 모드 3 × BLOGGER_PUBLISH 5(없음·on·draft·off·잘못된 값) × 연습 2 × 하루 상한 2 = 60격자. 시크릿은 Blogger 에 닿는 기본 격자(모드 draft·auto ×
        BLOGGER_PUBLISH 없음·on·draft·off, 연습·상한 꺼짐 = 8격자)에서 4종 각각 있음/없음 16가지를 모두 돌고(결과가 어느 것이 있느냐가
        아니라 개수로만 갈리는지 확인), 나머지 격자는 '없음·1종만·모두' 3가지를 돈다. 정지 스위치 조합은 따로 본다."""
        r = Runner(self, in_memory_summary=True)
        mismatches, count = [], 0
        for mode in ("off", "draft", "auto"):
            for policy in POLICIES:
                for dry in (False, True):
                    for cap in (False, True):
                        # 시크릿 16가지를 모두 도는 것은 Blogger 에 닿는 입력(없음·on·draft·off)의 기본 격자뿐이다(나머지는 없음·1종·모두)
                        full = mode != "off" and policy in (None, "on", "draft", "off") and not (dry or cap)
                        masks = range(16) if full else (0, 1, 15)
                        for mask in masks:
                            present = [n for i, n in enumerate(SECRET_NAMES) if mask >> i & 1]
                            env = {**LLM_ONLY_ENV, **{n: SECRET_VALUES[n] for n in present}}
                            if policy is not None:
                                env["BLOGGER_PUBLISH"] = policy
                            if dry:
                                env["DRY_RUN"] = "1"
                            before = [TODAY_ENTRY] if cap else []
                            pub = FakePublisher()
                            res = r.run(mode, env, pub, history=before or None)
                            count += 1
                            want = model_inputs(mode, policy, dry, len(SECRET_NAMES) - len(present), cap)
                            got = (res.code, res.skips, (res.history[len(before):] or [{}])[-1].get("status"),
                                   [p["draft"] for p in pub.published], pub.health_calls)
                            label = f"mode={mode} publish={policy} dry={dry} secrets={len(present)}/4({mask}) cap={cap}"
                            if got != want:
                                mismatches.append(f"{label}: 실제 {got} / 기준 {want}")
                            mismatches += [f"{label}: {problem}" for problem in check_invariants(res, mode, policy, dry, before)]
        self.assertEqual(count, 2 * 4 * 16 + (3 * 5 * 2 * 2 - 2 * 4) * 3)
        self.assertEqual(mismatches[:10], [], f"어긋난 조합 {len(mismatches)}건")
        for mode in ("off", "draft", "auto"):         # 정지 스위치는 어떤 입력보다 앞선다(60조합)
            for policy in POLICIES:
                for dry in (False, True):
                    for env_secrets in (ALL_ENV, LLM_ONLY_ENV):
                        env = {**env_secrets, "PIPELINE_PAUSE": "true", **({} if policy is None else {"BLOGGER_PUBLISH": policy}),
                               **({"DRY_RUN": "1"} if dry else {})}
                        res = r.run(mode, env, factory=must_not_be_called)
                        self.assertEqual((res.code, res.skips, res.history, res.llm_calls.calls), (0, ["PAUSED"], [], 0))
                        self.assertEqual(check_invariants(res, mode, policy, dry, []), [])

    def test_every_reachable_stage_path_matches_the_reference_model(self):
        """단계 경로 열거. 실행은 '인증 점검 → 글 생성 → 게시' 순서로 앞 단계가 성공해야 뒤 단계에 닿으므로, 도달 가능한 경로는
        인증 점검 실패 10 + (통과 후) 글 생성 실패 4 + (둘 다 통과 후) 게시 결과 11 = 25가지 × 전달 방식 2(즉시 게시·초안함)다.
        앞 단계가 실패하는 경로에는 뒤 단계도 실패하는 설정을 겹쳐 '닿지 않는 단계의 설정은 아무 영향이 없다'(Gemini·게시 호출 0회)도 확인한다."""
        r = Runner(self, in_memory_summary=True)
        mismatches, count = [], 0

        def record_problems(label, res, mode, before, want, got):
            if got != want:
                mismatches.append(f"{label}: 실제 {got} / 기준 {want}")
            mismatches.extend(f"{label}: {problem}" for problem in check_invariants(res, mode, None, False, before))

        for delivery, mode in (("publish", "auto"), ("draft", "draft")):
            # (a) 인증 점검 실패 — 뒤 단계 설정(글 생성 실패·게시 실패)을 겹쳐도 같다
            for auth_name, (make_auth, exit_code, reason) in AUTH_STAGE.items():
                for llm_name, pub_name in (("정상", "성공"), ("LLM 실패", "예외")):
                    llm = stub_llm if llm_name == "정상" else llm_down
                    auth_pub, pub = make_auth(), PUBLISH_STAGE[pub_name][0]()
                    factory = raising_factory if auth_pub is None else (lambda blog, environ, a=auth_pub, p=pub: Combined(a, p))
                    res = r.run(mode, ALL_ENV, factory=factory, llm=llm)
                    count += 1
                    new = res.history
                    label = f"{delivery}/인증:{auth_name}/글:{llm_name}/게시:{pub_name}"
                    record_problems(label, res, mode, [], (exit_code, ["AUTH_CHECK_FAILED"], 0, [], 1, 0),
                                    (res.code, res.skips, res.llm_calls.calls, [p["draft"] for p in pub.published], len(new), len(res.drafts)))
                    if not new or new[-1]["status"] != "publish_failed" or new[-1]["topic"] != "" \
                            or not new[-1]["reasons"][0].startswith(f"[{reason}] ") or f"reason={reason} exit={exit_code}" not in res.out:
                        mismatches.append(f"{label}: 이력·로그가 분류 {reason}/종료 {exit_code} 와 다름 {new}")
                    expected_checks = 0 if auth_pub is None else 1
                    if (auth_pub.health_calls if auth_pub is not None else 0) != expected_checks or pub.health_calls:
                        mismatches.append(f"{label}: 인증 점검 호출 수가 다름")
            # (b) 인증 통과 + 글 생성 실패 — 게시 설정(예외)을 겹쳐도 같다
            for llm_name, (llm, start, exit_code, status, skip, llm_calls) in LLM_STAGE.items():
                for pub_name in ("성공", "예외"):
                    pub = PUBLISH_STAGE[pub_name][0]()
                    before = list(start or [])
                    res = r.run(mode, ALL_ENV, pub, llm=llm, history=before or None)
                    count += 1
                    new = res.history[len(before):]
                    label = f"{delivery}/인증:통과/글:{llm_name}/게시:{pub_name}"
                    record_problems(label, res, mode, before, (exit_code, [skip], llm_calls, [], [status], 0, 1),
                                    (res.code, res.skips, res.llm_calls.calls, [p["draft"] for p in pub.published],
                                     [e["status"] for e in new], len(res.drafts), pub.health_calls))
            # (c) 인증·글 생성 통과 + 게시 결과 11가지
            for pub_name, (make_pub, reason) in PUBLISH_STAGE.items():
                pub = make_pub()
                res = r.run(mode, ALL_ENV, pub)
                count += 1
                new = res.history
                label = f"{delivery}/인증:통과/글:정상/게시:{pub_name}"
                reason = reason[delivery] if isinstance(reason, dict) else reason
                if reason is None:
                    status = "posted" if delivery == "publish" else "draft_uploaded"
                    record_problems(label, res, mode, [], (0, [], [status], [delivery == "draft"], 1),
                                    (res.code, res.skips, [e["status"] for e in new], [p["draft"] for p in pub.published], len(res.drafts)))
                    want_url = "" if pub_name == "주소 없음" else OK_URL          # 주소 없는 초안 성공은 주소를 빈칸으로 남긴다
                    if not new or new[-1]["url"] != want_url or new[-1]["post_id"] != "p1":
                        mismatches.append(f"{label}: 성공 이력의 주소·글 ID 가 기대와 다름 {new}")
                else:
                    record_problems(label, res, mode, [], (1, ["PUBLISH_FAILED"], ["publish_failed"], 1),
                                    (res.code, res.skips, [e["status"] for e in new], len(res.drafts)))
                    if (not new or not new[-1]["reasons"][0].startswith(f"[{reason}] ") or new[-1]["url"]
                            or f"reason={reason} target={delivery}" not in res.out):
                        mismatches.append(f"{label}: 실패 이력·로그가 분류 {reason} 와 다름 {new}")
        self.assertEqual(count, 2 * (len(AUTH_STAGE) * 2 + len(LLM_STAGE) * 2 + len(PUBLISH_STAGE)))
        self.assertEqual(count, 2 * (20 + 8 + 11))
        self.assertEqual(mismatches[:10], [], f"어긋난 경로 {len(mismatches)}건")


# ----------------------------------------------------------------------------
# 3) blogger.yml 불변식
# ----------------------------------------------------------------------------
@unittest.skipUnless(yaml is not None, "PyYAML(requirements-dev.txt)이 필요합니다(CI 에서는 항상 실행됩니다)")
class WorkflowPublishInputTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = (REAL / ".github" / "workflows" / "blogger.yml").read_text(encoding="utf-8")
        data = yaml.safe_load(cls.text)
        if True in data and "on" not in data:  # YAML 1.1 은 키 on 을 True 로 읽는다
            data["on"] = data.pop(True)
        cls.data = data
        cls.inputs = data["on"]["workflow_dispatch"]["inputs"]
        cls.run_step = next(step for step in data["jobs"]["generate"]["steps"] if "pipeline.run" in str(step.get("run", "")))

    def test_publish_input_is_a_three_way_choice_that_defaults_to_the_blogger_drafts(self):
        spec = self.inputs["publish"]
        self.assertEqual(spec["type"], "choice")
        self.assertEqual(spec["options"], ["off", "draft", "publish"])
        self.assertEqual(spec["default"], "draft")
        self.assertIn(spec["default"], spec["options"])
        description = spec["description"]
        self.assertRegex(description, r"[가-힣]")
        for word in ("off", "draft", "publish", "저장소 파일", "초안함", "즉시 게시", "기본", "정기 실행", "BLOGGER_API_SETUP.md"):
            self.assertIn(word, description)

    def test_input_descriptions_stay_short_enough_to_read_in_the_run_workflow_dialog(self):
        """이 변경이 넣은 입력(publish, 점검 전용 입력이 있으면 그것도)의 설명은 120자 이하다. 300자가 넘는 설명은 실행 대화상자에서
        읽히지 않으니 한 줄 요약 + 문서 링크로 둔다(V-16). 다른 입력의 설명(dry_run 등)은 이 시험의 대상이 아니다."""
        owned = [name for name in ("publish", "auth_check") if name in self.inputs]
        self.assertIn("publish", owned)
        for name in owned:
            description = self.inputs[name]["description"]
            self.assertRegex(description, r"[가-힣]", name)
            self.assertIn("BLOGGER_API_SETUP.md", description, name)
            self.assertLessEqual(len(description), 120, f"{name} 입력 설명이 너무 깁니다({len(description)}자)")

    def test_the_dry_run_checkbox_reaches_the_runner_as_DRY_RUN(self):
        """연습 실행 체크가 환경변수로 전달되지 않으면 연습이 실제 업로드가 된다. 정기 실행은 연습이 아니다."""
        import test_workflow_names as names
        template = self.data["jobs"]["generate"]["env"]["DRY_RUN"]

        def render(event, dry_run):
            inputs = {} if dry_run is None else {"dry_run": dry_run}
            ctx = {"github": {"event_name": event, "event": {"inputs": inputs}}, "inputs": inputs}
            return names.render(template, ctx)
        self.assertTrue(run_mod._flag({"DRY_RUN": render("workflow_dispatch", "true")}, "DRY_RUN"))
        self.assertFalse(run_mod._flag({"DRY_RUN": render("workflow_dispatch", "false")}, "DRY_RUN"))
        self.assertFalse(run_mod._flag({"DRY_RUN": render("schedule", None)}, "DRY_RUN"))    # 정기 실행에는 입력이 없다

    def test_the_other_inputs_are_still_there(self):
        self.assertEqual(set(self.inputs), {"blog", "topic", "dry_run", "publish", "auth_check"})

    def test_the_choice_reaches_the_runner_only_through_an_environment_variable(self):
        env = self.run_step["env"]
        self.assertIn("BLOGGER_PUBLISH", env)
        for step in self.data["jobs"]["generate"]["steps"] + self.data["jobs"]["plan"]["steps"]:
            self.assertNotIn("inputs.publish", str(step.get("run", "")))      # run 에 직접 보간하지 않는다(WF-4)
        self.assertEqual(self.run_step["run"], 'python -m pipeline.run --blog "$BLOG_KEY"')

    def test_blogger_publish_is_the_chosen_value_for_manual_runs_and_empty_for_scheduled_runs(self):
        import test_workflow_names as names
        template = self.run_step["env"]["BLOGGER_PUBLISH"]

        def render(event, publish):
            inputs = {} if publish is None else {"publish": publish}
            ctx = {"github": {"event_name": event, "event": {"inputs": inputs}}, "inputs": inputs}
            return names.render(template, ctx)
        for choice in self.inputs["publish"]["options"]:
            self.assertEqual(render("workflow_dispatch", choice), choice)
            self.assertEqual(render("schedule", choice), "")                  # 정기 실행은 입력을 쓰지 않고 레지스트리 mode 를 따른다
        self.assertEqual(render("schedule", None), "")
        self.assertEqual(render("workflow_dispatch", None), "")              # 입력이 비면 레지스트리 mode(auto)로 읽힌다
        # 워크플로가 넘기는 모든 값을 러너가 알아듣는다
        for choice in self.inputs["publish"]["options"]:
            self.assertIsNotNone(run_mod.publish_policy(None, {"BLOGGER_PUBLISH": choice}), choice)

    def test_secrets_are_still_passed_only_as_pipeline_secret_variables(self):
        env = self.run_step["env"]
        roles = registry.get_blog(registry.load_registry(REAL / "pipeline" / "blogs.json"), "blogger_macat")["secrets"]
        expected = {"PIPELINE_SECRET_" + role.upper(): "${{ secrets[matrix.secret_%s] }}" % role for role in roles}
        self.assertEqual({k: v for k, v in env.items() if k.startswith("PIPELINE_SECRET_")}, expected)
        for key, value in env.items():
            if "secrets." in str(value) or "secrets[" in str(value):
                self.assertTrue(key.startswith("PIPELINE_SECRET_"), key)     # 시크릿은 이 이름들로만 나간다
        self.assertEqual(set(env) - set(expected), {"BLOG_KEY", "BLOGGER_TOPIC", "BLOGGER_PUBLISH", "BLOGGER_AUTH_CHECK"})

    def test_permissions_and_the_generate_condition_did_not_widen(self):
        self.assertEqual(self.data["permissions"], {"contents": "read"})
        self.assertEqual(self.data["jobs"]["generate"]["permissions"], {"contents": "write"})
        self.assertEqual(self.data["jobs"]["generate"]["if"], "needs.plan.outputs.count != '0'")
        self.assertEqual(self.data["jobs"]["plan"].get("permissions"), None)


if __name__ == "__main__":
    unittest.main()
