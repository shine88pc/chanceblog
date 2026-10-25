"""확인 필요 모음(scripts/ops_inbox.py) 입출력 테스트 — 가짜 GitHub 로 읽기·이슈 관리·실행 요약·워크플로 파일을 확인한다.

네트워크는 쓰지 않는다(urlopen 대신 가짜 opener, 클라이언트 대신 FakeGitHub). 규칙 자체는 test_ops_inbox.py.
"""
import ast
import http.client
import io
import json
import os
import re
import socket
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

import yaml

import _bootstrap
import ops_inbox_helpers as h
import ops_inbox as oi
from pipeline import inbox

NOW, URL, ago = h.NOW, h.REPO_URL, h.ago
TOKEN = "gh" + "s_" + "Q" * 36          # 런타임에 조합한 가짜 토큰(소스에 비밀 모양 리터럴을 두지 않는다)
ENV = {"GITHUB_REPOSITORY": h.REPO, "GITHUB_TOKEN": TOKEN, "GITHUB_REPOSITORY_OWNER": "octo"}
WORKFLOWS = _bootstrap.ROOT / ".github" / "workflows"


class FakeResponse:
    def __init__(self, body):
        self._body = body if isinstance(body, bytes) else body.encode("utf-8")

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeOpener:
    """요청을 기록하고, 준비한 결과(응답 본문 또는 던질 예외)를 차례로 돌려준다(마지막 결과는 반복)."""

    def __init__(self, *outcomes):
        self.outcomes, self.requests, self.timeouts = list(outcomes), [], []

    def __call__(self, request, timeout=None):
        self.requests.append(request)
        self.timeouts.append(timeout)
        outcome = self.outcomes.pop(0) if len(self.outcomes) > 1 else self.outcomes[0]
        if isinstance(outcome, BaseException):
            raise outcome
        return FakeResponse(outcome)


def http_error(code, message="", headers=None):
    body = json.dumps({"message": message}).encode("utf-8")
    return urllib.error.HTTPError("https://api.github.com/x", code, "err", headers or {}, io.BytesIO(body))


# ----------------------------------------------------------------------------
# 클라이언트
# ----------------------------------------------------------------------------
class ClientTest(unittest.TestCase):
    def client(self, *outcomes, **kw):
        opener = FakeOpener(*(outcomes or ("{}",)))
        return oi.GitHubClient(h.REPO, kw.pop("token", TOKEN), opener=opener, **kw), opener

    def test_get_builds_a_repo_scoped_url_with_encoded_parameters_and_headers(self):
        client, opener = self.client('[{"a": 1}]')
        data = client.get("/actions/workflows/a.yml/runs", branch="main", per_page=10, created=">=2026-10-23T06:00:00Z")
        self.assertEqual(data, [{"a": 1}])
        request = opener.requests[0]
        self.assertEqual(request.get_method(), "GET")
        self.assertTrue(request.full_url.startswith(f"https://api.github.com/repos/{h.REPO}/actions/workflows/a.yml/runs?"))
        self.assertIn("branch=main", request.full_url)
        self.assertIn("per_page=10", request.full_url)
        self.assertIn("created=%3E%3D2026-10-23T06%3A00%3A00Z", request.full_url)
        self.assertEqual(request.get_header("Authorization"), f"Bearer {TOKEN}")
        self.assertEqual(request.get_header("Accept"), "application/vnd.github+json")
        self.assertEqual(request.get_header("X-github-api-version"), "2022-11-28")
        self.assertTrue(request.get_header("User-agent"))
        self.assertEqual(opener.timeouts, [20])

    def test_no_token_means_no_authorization_header(self):
        client, opener = self.client("[]", token=None)
        client.get("/issues")
        self.assertFalse(opener.requests[0].has_header("Authorization"))
        self.assertNotIn("?", opener.requests[0].full_url)

    def test_post_and_patch_send_json_utf8(self):
        client, opener = self.client('{"number": 5}')
        self.assertEqual(client.post("/issues", {"title": "[운영] 제목", "labels": ["ops-inbox"]}), {"number": 5})
        client.patch("/issues/5", {"state": "open"})
        post, patch = opener.requests
        self.assertEqual((post.get_method(), patch.get_method()), ("POST", "PATCH"))
        self.assertEqual(json.loads(post.data.decode("utf-8")), {"title": "[운영] 제목", "labels": ["ops-inbox"]})
        self.assertEqual(post.get_header("Content-type"), "application/json")
        self.assertTrue(post.full_url.endswith(f"/repos/{h.REPO}/issues"))

    def test_empty_body_is_none(self):
        self.assertIsNone(self.client("")[0].get("/x"))

    def test_call_budget_is_enforced_and_counted(self):
        client, opener = self.client("{}", max_calls=2)
        client.get("/a")
        client.get("/b")
        with self.assertRaises(oi.ApiBudgetError) as caught:
            client.get("/c")
        self.assertIsInstance(caught.exception, oi.ApiError)
        self.assertIsNone(caught.exception.status)
        self.assertEqual((client.calls, len(opener.requests)), (2, 2))          # 상한을 넘는 호출은 네트워크로 나가지 않는다
        with self.assertRaises(oi.ApiBudgetError):
            client.post("/d", {})

    def test_reads_cannot_use_the_write_reserve_until_it_is_released(self):
        client, opener = self.client("{}", max_calls=5, reserve=2)
        self.assertEqual(client.remaining(), 3)
        for _ in range(3):
            client.get("/r")
        with self.assertRaises(oi.ApiBudgetError):
            client.get("/r")
        client.post("/w", {})                                                   # 쓰기는 reserve 를 쓴다
        client.release_reserve()
        self.assertEqual(client.remaining(), 1)
        client.get("/r")
        with self.assertRaises(oi.ApiBudgetError):
            client.get("/r")
        self.assertEqual(len(opener.requests), 5)

    def test_reads_stop_after_the_time_limit_while_writes_and_the_write_phase_are_not_cut_off(self):
        now = [100.0]
        opener = FakeOpener("{}")
        client = oi.GitHubClient(h.REPO, TOKEN, opener=opener, max_seconds=60, clock=lambda: now[0])
        client.get("/a")
        now[0] = 160.0                                    # 정확히 60초 — 아직 상한 안이다
        client.get("/b")
        now[0] = 160.5
        with self.assertRaises(oi.ApiBudgetError) as caught:
            client.get("/c")
        self.assertIn("시간 상한", str(caught.exception))
        self.assertEqual(len(opener.requests), 2)         # 상한을 넘은 읽기는 네트워크로 나가지 않는다
        client.post("/w", {})                             # 쓰기는 시간 상한과 무관하다
        client.release_reserve()
        client.get("/d")                                  # 쓰기 단계(이슈 찾기)의 읽기는 시간 상한을 받지 않는다
        self.assertEqual(len(opener.requests), 4)

    def test_http_errors_become_api_errors_with_status_and_a_short_message(self):
        client, _ = self.client(http_error(404, "Not Found"))
        with self.assertRaises(oi.ApiError) as caught:
            client.get("/x")
        self.assertEqual(caught.exception.status, 404)
        self.assertEqual(str(caught.exception), "HTTP 404: Not Found")

    def test_error_message_masks_secret_shaped_text_and_neutralises_markup(self):
        token = "gh" + "p_" + "B" * 36
        client, _ = self.client(http_error(422, f"@victim <b>{token}</b> ::error::x"))
        with self.assertRaises(oi.ApiError) as caught:
            client.get("/x")
        text = str(caught.exception)
        for raw in (token, "@", "<", "::"):
            self.assertNotIn(raw, text, raw)

    def test_the_quota_message_needs_both_a_rate_limit_status_and_the_exhausted_header(self):
        exhausted = {"x-ratelimit-remaining": "0"}
        for code, headers, quota in ((403, exhausted, True), (429, exhausted, True), (403, {}, False),
                                     (403, {"x-ratelimit-remaining": "7"}, False), (500, exhausted, False), (404, exhausted, False)):
            client, _ = self.client(http_error(code, "원문 메시지", headers))
            with self.assertRaises(oi.ApiError) as caught:
                client.get("/x")
            self.assertEqual("호출 한도" in str(caught.exception), quota, (code, headers))
            if not quota:
                self.assertIn(f"HTTP {code}: 원문 메시지", str(caught.exception))

    def test_remaining_never_goes_below_zero_and_writes_may_use_the_very_last_call(self):
        reader, _ = self.client("{}", max_calls=2)
        reader.get("/a")
        reader.get("/b")
        self.assertEqual(reader.remaining(), 0)
        writer, opener = self.client("{}", max_calls=2)
        writer.post("/w", {})
        writer.patch("/w", {})
        with self.assertRaises(oi.ApiBudgetError):
            writer.post("/w", {})
        self.assertEqual(len(opener.requests), 2)

    def test_rate_limit_exhaustion_is_reported_plainly(self):
        client, _ = self.client(http_error(403, "API rate limit exceeded", {"x-ratelimit-remaining": "0"}))
        with self.assertRaises(oi.ApiError) as caught:
            client.get("/x")
        self.assertIn("호출 한도", str(caught.exception))
        self.assertEqual(caught.exception.status, 403)

    def test_network_errors_become_api_errors_without_status(self):
        for failure in (urllib.error.URLError("dns"), socket.timeout("timed out"), ConnectionResetError("reset"), OSError("boom")):
            client, _ = self.client(failure)
            with self.assertRaises(oi.ApiError) as caught:
                client.get("/x")
            self.assertIsNone(caught.exception.status)
            self.assertIn(type(failure).__name__, str(caught.exception))

    def test_http_client_exceptions_are_wrapped_too(self):
        client, _ = self.client(http.client.IncompleteRead(b"x"))
        with self.assertRaises(oi.ApiError):
            client.get("/x")

    def test_exception_text_never_leaks_the_token(self):
        client, _ = self.client(OSError(f"connection failed for Authorization: Bearer {TOKEN}"))
        with self.assertRaises(oi.ApiError) as caught:
            client.get("/x")
        self.assertNotIn(TOKEN, str(caught.exception))

    def test_non_json_and_undecodable_responses_are_api_errors(self):
        for body in ("<html>", b"\xff\xfe"):
            client, _ = self.client(body)
            with self.assertRaises(oi.ApiError):
                client.get("/x")

    def test_default_opener_is_looked_up_when_the_client_is_made(self):
        with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("offline")) as patched:
            with self.assertRaises(oi.ApiError):
                oi.GitHubClient(h.REPO).get("/x")
        self.assertEqual(patched.call_count, 1)


# ----------------------------------------------------------------------------
# 읽기: 저장소 파일
# ----------------------------------------------------------------------------
class LocalReadersTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def test_blogs_are_merged_with_registry_defaults(self):
        failures = []
        blogs = oi.read_blogs(h.make_root(self.tmp), failures)
        self.assertEqual([b["key"] for b in blogs], ["chance", "blogger_macat"])
        self.assertEqual(failures, [])
        registry = json.loads(h.SYNTHETIC_REGISTRY)
        registry["blogs"][1].pop("mode")
        (self.tmp / "pipeline" / "blogs.json").write_text(json.dumps(registry), encoding="utf-8")
        self.assertEqual(oi.read_blogs(self.tmp, [])[1]["mode"], "draft")             # defaults 의 값

    def test_the_real_registry_is_readable(self):
        failures = []
        blogs = oi.read_blogs(_bootstrap.ROOT, failures)
        self.assertEqual(failures, [])
        self.assertTrue(blogs)
        for blog in blogs:
            self.assertTrue(blog["key"] and blog["state"]["history"])

    def test_broken_registry_is_a_failure_not_a_crash(self):
        for text in ("{깨짐", "[]", '"문자열"'):
            root = h.make_root(self.tmp, blogs_json=text)
            failures = []
            self.assertEqual(oi.read_blogs(root, failures), [])
            self.assertEqual([f[0] for f in failures], ["registry"], text)
            self.assertTrue(failures[0][1].startswith("pipeline/blogs.json: "), failures)
            self.assertNotIn(str(self.tmp), failures[0][1])               # 실행 환경의 절대 경로를 공개 이슈에 남기지 않는다
        failures = []
        oi.read_blogs(h.make_root(self.tmp, blogs_json="{깨짐"), failures)
        self.assertIn("JSON 형식 오류", failures[0][1])

    def test_missing_registry_is_a_failure(self):
        failures = []
        self.assertEqual(oi.read_blogs(self.tmp, failures), [])
        self.assertEqual([f[0] for f in failures], ["registry"])
        self.assertEqual(failures[0][1], "pipeline/blogs.json: 파일이 없습니다")

    def test_histories_are_read_per_blog_and_missing_files_are_empty(self):
        root = h.make_root(self.tmp, histories={"history.json": [{"date": "2026-10-25"}]})
        failures = []
        histories = oi.read_histories(root, oi.read_blogs(root, failures), failures)
        self.assertEqual(histories, {"chance": [{"date": "2026-10-25"}], "blogger_macat": []})
        self.assertEqual(failures, [])

    def test_corrupt_history_is_reported_by_file_and_others_still_load(self):
        root = h.make_root(self.tmp, histories={"history.json": "{깨짐", "blogger_history.json": [{"status": "posted"}]})
        failures = []
        histories = oi.read_histories(root, oi.read_blogs(root, failures), failures)
        self.assertEqual(histories, {"blogger_macat": [{"status": "posted"}]})
        self.assertEqual([f[0] for f in failures], ["history"])
        self.assertTrue(failures[0][1].startswith("history.json: JSON 형식 오류("), failures)
        self.assertNotIn(str(self.tmp), failures[0][1])

    def test_unreadable_history_names_the_error_kind_without_a_path(self):
        root = h.make_root(self.tmp)
        (root / "history.json").mkdir()                      # 파일이 아니라 폴더 → 읽기 오류(OSError 계열)
        failures = []
        oi.read_histories(root, oi.read_blogs(root, failures), failures)
        self.assertRegex(failures[0][1], r"^history\.json: [A-Za-z]+Error$")
        self.assertNotIn(str(self.tmp), failures[0][1])

    def test_history_that_is_not_a_list_is_reported(self):
        root = h.make_root(self.tmp, histories={"history.json": {"a": 1}})
        failures = []
        oi.read_histories(root, oi.read_blogs(root, failures), failures)
        self.assertEqual(failures[0][1], "history.json: 형식이 올바르지 않습니다(최상위가 배열·객체가 아님 등)")

    def test_history_path_outside_the_repository_is_not_read(self):
        outside = self.tmp / "outside.json"
        outside.write_text('[{"status": "posted"}]', encoding="utf-8")
        inner = self.tmp / "repo"
        inner.mkdir()
        blogs = [h.make_blog("evil", history="../outside.json"), h.make_blog("abs", history=str(outside))]
        failures = []
        self.assertEqual(oi.read_histories(inner, blogs, failures), {})
        self.assertEqual([f[0] for f in failures], ["history"])
        self.assertIn("저장소 밖", failures[0][1])

    def test_blogs_without_a_history_path_are_skipped(self):
        failures = []
        self.assertEqual(oi.read_histories(self.tmp, [{"key": "x"}, {"key": "y", "state": "깨짐"}, {"state": {"history": "a.json"}}], failures), {})
        self.assertEqual(failures, [])

    def test_workflow_files_are_listed_sorted_with_both_extensions(self):
        root = h.make_root(self.tmp, workflows=("b.yml", "a.yaml", "c.yml"))
        (root / ".github" / "workflows" / "readme.md").write_text("x", encoding="utf-8")
        (root / ".github" / "workflows" / "d.yml").mkdir()
        self.assertEqual(oi.list_workflow_files(root), ["a.yaml", "b.yml", "c.yml"])
        self.assertEqual(oi.list_workflow_files(self.tmp / "none"), [])


class WorkflowNameReadingTest(unittest.TestCase):
    """항목에 쓰는 워크플로 이름은 체크아웃한 .github/workflows/<파일>의 최상위 name 이다(API 호출 0회).
    표준 라이브러리만 쓰므로 YAML 전체를 해석하지 않고 필요한 모양만 읽는다. 못 읽으면 파일 이름이 쓰인다."""

    PARSED = (
        ("name: 확인 필요 모음\nrun-name: x\n", "확인 필요 모음"),
        ('name: "Chance 글 자동 작성·게시"\non: push\n', "Chance 글 자동 작성·게시"),
        ("name: 'it''s ok'\n", "it's ok"),
        ('name: "a # b" # 주석\n', "a # b"),
        ("name: 'a'  # c\n", "a"),
        ("name: 발행 중단 감시·알림   # 주석\n", "발행 중단 감시·알림"),
        ("name: 값 # 주석 # 또 주석\n", "값"),
        ("name: C#언어\n", "C#언어"),                                    # '#' 앞에 공백이 없으면 주석이 아니다
        ("name:   값  \r\non:\r\n", "값"),                               # CRLF(Windows 작업 사본)
        ("\ufeffname: BOM 파일\n", "BOM 파일"),
        ("# 설명\n\non: push\nname : 늦게 나오는 이름\njobs: {}\n", "늦게 나오는 이름"),
        ("on: push\nname:\tTab 뒤의 값\n", "Tab 뒤의 값"),
    )
    NOT_FOUND = (
        "", "on: push\njobs:\n  build:\n    name: 잡 이름\n", "  name: 들여쓴 이름\n", "# name: 주석\n", "names: x\n", "name-x: y\n", "namex: y\n", "nam: y\n",
        "name:값\n", "name: >\n  접힌 문장\n", "name: |\n  줄\n", "name: *anchor\n", "name: &a 값\n", "name: [a, b]\n", "name: {a: b}\n",
        "name: !!str 값\n", "name: @값\n", "name: `값\n", "name: %값\n", 'name: "탈출 \\n 문자"\n', "name:\n", "name: ''\n", 'name: ""\n',
        "name: ' '\n", "name: # 값 없음\n", 'name: "닫히지 않음\n', "name: 'a' b\n", 'name: "a" b\n', "name: 'a''\n",
    )

    def test_the_top_level_name_is_parsed(self):
        for text, expected in self.PARSED:
            self.assertEqual(oi.workflow_name(text), expected, text)

    def test_anything_that_is_not_a_plain_top_level_name_gives_none(self):
        for text in self.NOT_FOUND:
            self.assertIsNone(oi.workflow_name(text), text)
        for bad in (None, 5, b"name: x", ["name: x"]):
            self.assertIsNone(oi.workflow_name(bad), bad)

    def test_the_first_top_level_name_wins_over_names_further_down(self):
        self.assertEqual(oi.workflow_name("name: 위\njobs:\n  a:\n    name: 아래\n"), "위")

    def test_names_are_read_from_the_checked_out_files(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = h.make_root(Path(self._tmp.name), workflows={"a.yml": "name: 에이\non: push\n", "b.yaml": 'name: "비"\n', "c.yml": "on: push\n"})
        (root / ".github" / "workflows" / "lf.yml").write_bytes("name: 엘에프\njobs: {}\n".encode("utf-8"))
        files = oi.list_workflow_files(root)
        self.assertEqual(oi.read_workflow_names(root, files), {"a.yml": "에이", "b.yaml": "비", "lf.yml": "엘에프"})     # name 이 없는 c.yml 은 빠진다

    def test_unreadable_files_are_left_out_without_noise(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = h.make_root(Path(self._tmp.name), workflows={"ok.yml": "name: 정상\n"})
        folder = root / ".github" / "workflows"
        (folder / "dir.yml").mkdir()
        (folder / "bad.yml").write_bytes(b"name: \xff\xfe\n")
        self.assertEqual(oi.read_workflow_names(root, ["ok.yml", "dir.yml", "bad.yml", "missing.yml"]), {"ok.yml": "정상"})
        self.assertEqual(oi.read_workflow_names(Path(self._tmp.name) / "none", ["a.yml"]), {})

    def test_only_the_beginning_of_a_huge_file_is_read(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        big = {"big.yml": "name: 앞쪽 이름\n# " + "가" * 300000 + "\n", "late.yml": "# " + "가" * 300000 + "\nname: 너무 뒤\n"}
        root = h.make_root(Path(self._tmp.name), workflows=big)
        self.assertEqual(oi.read_workflow_names(root, ["big.yml", "late.yml"]), {"big.yml": "앞쪽 이름"})

    def test_every_real_workflow_name_matches_what_yaml_reads(self):
        files = oi.list_workflow_files(_bootstrap.ROOT)
        names = oi.read_workflow_names(_bootstrap.ROOT, files)
        self.assertEqual(sorted(names), files)
        for file in files:
            self.assertEqual(names[file], yaml.safe_load((WORKFLOWS / file).read_text(encoding="utf-8"))["name"], file)


# ----------------------------------------------------------------------------
# 읽기: GitHub 소스
# ----------------------------------------------------------------------------
def api_error(status=500, text="HTTP 500"):
    return oi.ApiError(text, status=status)


class FetchTest(unittest.TestCase):
    def setUp(self):
        self.fake, self.failures, self.notes = h.FakeGitHub(), [], []

    def add_pull(self, number, ci="pass", mergeable=True, state="clean", sha=None, **kw):
        sha = sha or f"{number:040x}"
        self.fake.pulls.append(h.make_pull_raw(number, sha=sha, **kw))
        self.fake.details[number] = {"mergeable": mergeable, "mergeable_state": state}
        self.fake.check_runs[sha] = {"pass": [h.make_check("v")], "fail": [h.make_check("v", "failure")], "none": []}[ci]

    def test_issues_exclude_pull_requests_and_ask_for_open_ones(self):
        self.fake.issues = [h.make_issue(1, "a"), h.make_issue(2, "b", pull=True), h.make_issue(3, "c", state="closed")]
        found = oi.fetch_issues(self.fake, self.failures)
        self.assertEqual([i["number"] for i in found], [1])
        self.assertEqual(self.fake.log[0][2], {"state": "open", "per_page": 100})

    def test_issue_failure_is_recorded_and_returns_nothing(self):
        self.fake.fail = [(r"GET /issues", api_error(502, "HTTP 502"))]
        self.assertEqual(oi.fetch_issues(self.fake, self.failures), [])
        self.assertEqual(self.failures, [("issues", "HTTP 502")])

    def test_pulls_are_normalised_with_detail_and_checks(self):
        self.add_pull(15)
        self.add_pull(16, ci="fail", mergeable=True, state="unstable")
        self.add_pull(17, ci="pass", mergeable=False, state="dirty")
        pulls = {p["number"]: p for p in oi.fetch_pulls(self.fake, self.failures, self.notes)}
        self.assertEqual((pulls[15]["ci"], pulls[15]["mergeable"], pulls[15]["mergeable_state"]), ("pass", True, "clean"))
        self.assertEqual(pulls[16]["ci"], "fail")
        self.assertEqual((pulls[17]["mergeable"], pulls[17]["mergeable_state"]), (False, "dirty"))
        self.assertEqual((self.failures, self.notes), ([], []))
        self.assertEqual(len(self.fake.paths()), 1 + 3 * 2)                       # 목록 1 + PR 마다 상세·검사 2

    def test_request_parameters_are_the_documented_ones(self):
        self.add_pull(15)
        oi.fetch_pulls(self.fake, self.failures, self.notes)
        oi.fetch_approvals(self.fake, self.failures)
        by_path = {path: params for _method, path, params in self.fake.log}
        self.assertEqual(by_path["/pulls"], {"state": "open", "per_page": 50})
        self.assertEqual(by_path["/pulls/15"], {})
        self.assertEqual(by_path[f"/commits/{15:040x}/check-runs"], {"per_page": 100})
        self.assertEqual(by_path["/actions/runs"], {"status": "action_required", "per_page": 20})

    # --- 병합 가능 여부(mergeable)가 아직 계산 중(null)이면 같은 점검 안에서 한 번 다시 묻는다
    NULL_DETAIL = {"mergeable": None, "mergeable_state": "unknown"}
    CLEAN_DETAIL = {"mergeable": True, "mergeable_state": "clean"}

    def test_a_mergeable_value_that_is_not_computed_yet_is_asked_again_once_after_a_short_wait(self):
        self.add_pull(15)
        self.fake.details[15] = [dict(self.NULL_DETAIL), dict(self.CLEAN_DETAIL)]
        slept = []
        pulls = oi.fetch_pulls(self.fake, self.failures, self.notes, sleep=slept.append)
        self.assertEqual((pulls[0]["mergeable"], pulls[0]["mergeable_state"]), (True, "clean"))
        self.assertEqual(slept, [oi.PULL_RETRY_WAIT_SECONDS])
        self.assertEqual(self.fake.paths().count("/pulls/15"), 2)
        self.assertEqual((self.failures, self.notes), ([], []))

    def test_it_asks_once_more_only_for_the_pulls_still_unknown_and_waits_once_for_all(self):
        for n in (1, 2, 3):
            self.add_pull(n)
        self.fake.details[1] = [dict(self.NULL_DETAIL), dict(self.CLEAN_DETAIL)]
        self.fake.details[2] = [dict(self.NULL_DETAIL)]                    # 끝까지 null
        slept = []
        pulls = {p["number"]: p for p in oi.fetch_pulls(self.fake, self.failures, self.notes, sleep=slept.append)}
        self.assertEqual((pulls[1]["mergeable"], pulls[2]["mergeable"], pulls[3]["mergeable"]), (True, None, True))
        asked = [path for path in self.fake.paths() if path.startswith("/pulls/")]
        self.assertEqual(asked, ["/pulls/1", "/pulls/2", "/pulls/3", "/pulls/1", "/pulls/2"])      # 첫 조회가 모두 끝난 뒤에 다시 묻는다(그동안이 기다림이 된다)
        self.assertEqual(len(slept), 1)

    def test_a_known_mergeable_value_costs_no_extra_call_and_no_wait(self):
        self.add_pull(15)
        slept = []
        oi.fetch_pulls(self.fake, self.failures, self.notes, sleep=slept.append)
        self.assertEqual(slept, [])
        self.assertEqual(len(self.fake.paths()), 1 + 2)

    def test_a_pull_whose_check_lookup_failed_is_not_asked_again(self):
        self.add_pull(15)
        self.fake.details[15] = [dict(self.NULL_DETAIL), dict(self.CLEAN_DETAIL)]
        self.fake.fail = [(r"GET /commits/", api_error(500, "HTTP 500"))]            # 상세는 받았지만(null) 검사 조회가 실패했다
        slept = []
        pulls = oi.fetch_pulls(self.fake, self.failures, self.notes, sleep=slept.append)
        self.assertEqual(pulls[0]["error"], "HTTP 500")
        self.assertEqual((slept, self.fake.paths().count("/pulls/15")), ([], 1))

    def test_a_pull_whose_first_lookup_failed_is_not_asked_again(self):
        self.add_pull(15)
        self.fake.details[15] = [api_error(500, "HTTP 500")]
        slept = []
        pulls = oi.fetch_pulls(self.fake, self.failures, self.notes, sleep=slept.append)
        self.assertEqual(pulls[0]["error"], "HTTP 500")
        self.assertEqual((slept, self.fake.paths().count("/pulls/15")), ([], 1))

    def test_a_failed_or_empty_second_answer_keeps_the_first_answer_and_records_nothing(self):
        for second in (api_error(502, "HTTP 502"), None, "문자열", ["목록"]):
            fake, failures, notes = h.FakeGitHub(), [], []
            fake.pulls, fake.check_runs = [h.make_pull_raw(15, sha=f"{15:040x}")], {f"{15:040x}": [h.make_check("v")]}
            fake.details = {15: [dict(self.NULL_DETAIL), second]}
            pulls = oi.fetch_pulls(fake, failures, notes, sleep=lambda seconds: None)
            self.assertEqual((pulls[0]["mergeable"], pulls[0]["mergeable_state"], pulls[0]["error"]), (None, "unknown", ""), second)
            self.assertEqual((failures, notes), ([], []), second)

    def test_the_second_question_stays_inside_the_read_budget_and_skips_the_wait_without_budget(self):
        self.add_pull(15)
        self.fake.details[15] = [dict(self.NULL_DETAIL), dict(self.CLEAN_DETAIL)]
        for max_calls, reserve in ((3, 0), (4, 1)):                   # 읽기 3회(목록·상세·검사)로 이미 상한이거나, 남은 1회가 쓰기용 reserve 다
            fake = h.FakeGitHub(max_calls=max_calls, reserve=reserve)
            fake.pulls, fake.check_runs = self.fake.pulls, self.fake.check_runs
            fake.details = {15: [dict(self.NULL_DETAIL), dict(self.CLEAN_DETAIL)]}
            slept, failures = [], []
            pulls = oi.fetch_pulls(fake, failures, [], sleep=slept.append)
            self.assertEqual((pulls[0]["mergeable"], slept, failures, fake.calls), (None, [], [], 3), (max_calls, reserve))

    def test_pull_entries_without_a_numeric_number_are_skipped_without_calls(self):
        self.fake.pulls = [dict(h.make_pull_raw(1), number=None), dict(h.make_pull_raw(2), number="7"), dict(h.make_pull_raw(3), number=True)]
        self.assertEqual(oi.fetch_pulls(self.fake, self.failures, self.notes), [])
        self.assertEqual(len(self.fake.log), 1)

    def test_exactly_eight_pulls_need_no_cap_note(self):
        for n in range(1, 9):
            self.add_pull(n)
        self.assertEqual(len(oi.fetch_pulls(self.fake, self.failures, self.notes)), 8)
        self.assertEqual(self.notes, [])

    def test_two_detail_failures_say_one_more(self):
        for n in (1, 2):
            self.add_pull(n)
        self.fake.fail = [(r"GET /commits/", api_error(500, "HTTP 500"))]
        oi.fetch_pulls(self.fake, self.failures, self.notes)
        self.assertEqual(self.failures, [("pull_details", "HTTP 500 (외 1건)")])

    def test_a_single_failing_workflow_has_no_remainder_text(self):
        self.fake.runs["a.yml"] = []
        self.fake.fail = [(r"workflows/a\.yml", api_error(500, "HTTP 500"))]
        oi.fetch_runs(self.fake, ["a.yml"], NOW, "main", self.failures)
        self.assertEqual(self.failures, [("runs", "a.yml: HTTP 500")])

    def test_draft_pulls_cost_no_calls(self):
        self.add_pull(20, draft=True)
        self.assertEqual(oi.fetch_pulls(self.fake, self.failures, self.notes), [])
        self.assertEqual(len(self.fake.log), 1)

    def test_only_the_first_eight_pulls_are_checked_and_the_rest_are_noted(self):
        for n in range(1, 12):
            self.add_pull(n)
        pulls = oi.fetch_pulls(self.fake, self.failures, self.notes)
        self.assertEqual(len(pulls), 8)
        self.assertEqual(self.notes[0][0], "pulls_cap")
        self.assertIn("11건 중 처음 8건", self.notes[0][1])
        self.assertEqual(len(self.fake.log), 1 + 8 * 2)

    def test_detail_failure_of_one_pull_keeps_the_others(self):
        self.add_pull(1)
        self.add_pull(2)
        self.add_pull(3)
        self.fake.fail = [(r"GET /pulls/2$", api_error(500, "HTTP 500: boom"))]
        pulls = {p["number"]: p for p in oi.fetch_pulls(self.fake, self.failures, self.notes)}
        self.assertEqual(pulls[2]["error"], "HTTP 500: boom")
        self.assertEqual((pulls[1]["error"], pulls[3]["error"]), ("", ""))
        self.assertEqual(self.failures, [("pull_details", "HTTP 500: boom")])

    def test_several_detail_failures_are_summarised_in_one_failure(self):
        for n in (1, 2, 3):
            self.add_pull(n)
        self.fake.fail = [(r"GET /commits/", api_error(500, "HTTP 500"))]
        oi.fetch_pulls(self.fake, self.failures, self.notes)
        self.assertEqual(self.failures, [("pull_details", "HTTP 500 (외 2건)")])

    def test_pull_list_failure_is_recorded(self):
        self.fake.fail = [(r"GET /pulls\?", api_error(500, "HTTP 500"))]
        self.assertEqual(oi.fetch_pulls(self.fake, self.failures, self.notes), [])
        self.assertEqual([f[0] for f in self.failures], ["pulls"])

    def test_pull_with_an_unexpected_head_sha_skips_the_check_call(self):
        self.add_pull(5, sha="not-a-sha")
        pulls = oi.fetch_pulls(self.fake, self.failures, self.notes)
        self.assertEqual(pulls[0]["ci"], "unknown")
        self.assertEqual(len(self.fake.log), 2)

    def test_runs_ask_for_the_default_branch_window_and_skip_this_workflow(self):
        for name in ("a.yml", "b.yml", inbox.OWN_WORKFLOW):
            self.fake.runs[name] = [h.make_run(1, ago(hours=1))]
        runs = oi.fetch_runs(self.fake, ["a.yml", "b.yml", inbox.OWN_WORKFLOW], NOW, "trunk", self.failures)
        self.assertEqual(sorted(runs), ["a.yml", "b.yml"])
        self.assertEqual(self.fake.paths(), ["/actions/workflows/a.yml/runs", "/actions/workflows/b.yml/runs"])
        params = self.fake.log[0][2]
        self.assertEqual((params["branch"], params["per_page"]), ("trunk", 10))
        self.assertEqual(params["created"], ">=2026-10-23T06:00:00Z")                # NOW 의 48시간 전
        self.assertEqual(self.failures, [])

    def test_runs_of_fork_pull_requests_are_dropped_when_they_are_read(self):
        own = h.make_run(1, ago(hours=2))
        fork = h.make_run(2, ago(minutes=5), event="pull_request", head_repo="stranger/blog")
        mine = h.make_run(3, ago(minutes=30), event="pull_request")                                        # 이 저장소 안의 PR 이 일으킨 실행은 남는다
        self.fake.runs["a.yml"] = [fork, mine, own]
        runs = oi.fetch_runs(self.fake, ["a.yml"], NOW, "main", self.failures)                             # 저장소는 클라이언트가 알고 있다
        self.assertEqual([r["id"] for r in runs["a.yml"]], [3, 1])
        kept = oi.fetch_runs(self.fake, ["a.yml"], NOW, "main", self.failures, repo="stranger/blog")        # 부르는 쪽이 알려 줄 수도 있다
        self.assertEqual([r["id"] for r in kept["a.yml"]], [2, 1])
        self.assertEqual(self.failures, [])

    def test_workflow_unknown_to_the_default_branch_is_just_empty(self):
        runs = oi.fetch_runs(self.fake, ["new.yml"], NOW, "main", self.failures)
        self.assertEqual((runs, self.failures), ({"new.yml": []}, []))

    def test_other_run_errors_are_summarised_and_other_workflows_continue(self):
        for name in ("a.yml", "b.yml", "c.yml"):
            self.fake.runs[name] = [h.make_run(1, ago(hours=1))]
        self.fake.fail = [(r"workflows/(a|b)\.yml", api_error(500, "HTTP 500"))]
        runs = oi.fetch_runs(self.fake, ["a.yml", "b.yml", "c.yml"], NOW, "main", self.failures)
        self.assertEqual(list(runs), ["c.yml"])
        self.assertEqual(self.failures, [("runs", "a.yml: HTTP 500 (외 1개 워크플로)")])

    def test_budget_exhaustion_stops_the_run_listing_once(self):
        fake = h.FakeGitHub(max_calls=2)
        for name in ("a.yml", "b.yml", "c.yml", "d.yml"):
            fake.runs[name] = []
        runs = oi.fetch_runs(fake, ["a.yml", "b.yml", "c.yml", "d.yml"], NOW, "main", self.failures)
        self.assertEqual(sorted(runs), ["a.yml", "b.yml"])
        self.assertEqual([f[0] for f in self.failures], ["runs"])
        self.assertEqual(fake.calls, 2)

    def test_unexpected_exceptions_are_script_bugs_and_are_never_turned_into_check_items(self):
        """읽기 실패(ApiError)만 '조회 실패'로 남긴다. 그 밖의 예외는 스크립트 버그이므로 그대로 올라가 실행이 빨개져야 한다."""
        self.add_pull(1)
        self.fake.runs["a.yml"] = [h.make_run(1, ago(hours=1))]
        self.fake.jobs[1] = [{"id": 11}]
        calls = {
            r"GET /issues": lambda: oi.fetch_issues(self.fake, self.failures),
            r"GET /pulls\?": lambda: oi.fetch_pulls(self.fake, self.failures, self.notes),
            r"GET /pulls/1$": lambda: oi.fetch_pulls(self.fake, self.failures, self.notes),
            r"GET /commits/": lambda: oi.fetch_pulls(self.fake, self.failures, self.notes),
            r"GET /actions/workflows": lambda: oi.fetch_runs(self.fake, ["a.yml"], NOW, "main", self.failures),
            r"GET /actions/runs\?": lambda: oi.fetch_approvals(self.fake, self.failures),
            r"/actions/runs/1/jobs": lambda: oi.fetch_annotations(self.fake, self.fake.runs, NOW, self.failures, self.notes),
            r"/check-runs/11/annotations": lambda: oi.fetch_annotations(self.fake, self.fake.runs, NOW, self.failures, self.notes),
        }
        for pattern, call in calls.items():
            self.fake.fail = [(pattern, RuntimeError("스크립트 버그"))]
            with self.assertRaises(RuntimeError, msg=pattern):
                call()
        self.assertEqual(self.failures, [])

    def test_approvals(self):
        self.fake.approvals = [h.make_run(1, None, None, "action_required")]
        self.assertEqual(len(oi.fetch_approvals(self.fake, self.failures)), 1)
        self.fake.fail = [(r"GET /actions/runs\?", api_error(500))]
        self.assertEqual(oi.fetch_approvals(self.fake, self.failures), [])
        self.assertEqual([f[0] for f in self.failures], ["approvals"])


class FetchAnnotationsTest(unittest.TestCase):
    def setUp(self):
        self.fake, self.failures, self.notes = h.FakeGitHub(), [], []

    def add_run(self, file, run_id, hours, job_ids=(), conclusion="success", message="경고"):
        run = h.make_run(run_id, ago(hours=hours), conclusion)
        self.fake.runs.setdefault(file, []).append(run)
        self.fake.jobs[run_id] = [{"id": job_id, "name": "job"} for job_id in job_ids]
        for job_id in job_ids:
            self.fake.annotations[job_id] = [h.make_annotation(f"{message} {job_id}")]
        return run

    def fetch(self, **kw):
        return oi.fetch_annotations(kw.pop("client", self.fake), self.fake.runs, NOW, self.failures, self.notes)

    def test_reads_jobs_then_each_jobs_annotations_for_recent_successful_runs(self):
        self.add_run("a.yml", 1, 1, job_ids=(11, 12))
        found = self.fetch()
        self.assertEqual(sorted(found), [1])
        self.assertEqual([a["message"] for a in found[1]], ["경고 11", "경고 12"])
        self.assertEqual(self.fake.paths(), ["/actions/runs/1/jobs", "/check-runs/11/annotations", "/check-runs/12/annotations"])
        self.assertEqual(self.fake.log[0][2], {"per_page": 30})
        self.assertEqual(self.fake.log[1][2], {"per_page": 50})
        self.assertEqual((self.failures, self.notes), ([], []))

    def test_only_the_latest_three_successes_per_workflow_are_read(self):
        for n, hours in enumerate((1, 3, 5, 7, 9), start=1):
            self.add_run("a.yml", n, hours, job_ids=(100 + n,))
        self.assertEqual(sorted(self.fetch()), [1, 2, 3])

    def test_failed_old_and_unfinished_runs_are_not_read(self):
        self.add_run("a.yml", 1, 1, job_ids=(11,), conclusion="failure")
        self.add_run("a.yml", 2, 60, job_ids=(12,))
        self.fake.runs["a.yml"].append(h.make_run(3, ago(hours=1), None, "in_progress"))
        self.assertEqual(self.fetch(), {})
        self.assertEqual(self.fake.log, [])

    def test_most_recent_runs_across_workflows_are_read_first_when_calls_run_short(self):
        self.add_run("a.yml", 1, 10, job_ids=(11,))
        self.add_run("b.yml", 2, 1, job_ids=(21,))
        self.add_run("c.yml", 3, 5, job_ids=(31,))
        fake = h.FakeGitHub(max_calls=4)                       # 실행 둘(2+2)만 읽을 수 있다
        fake.runs, fake.jobs, fake.annotations = self.fake.runs, self.fake.jobs, self.fake.annotations
        found = oi.fetch_annotations(fake, fake.runs, NOW, self.failures, self.notes)
        self.assertEqual(sorted(found), [2, 3])
        self.assertEqual(self.notes[0][0], "annotations_cap")
        self.assertIn("1건", self.notes[0][1])
        self.assertEqual(self.failures, [])

    def test_the_write_reserve_is_never_spent_on_annotations(self):
        self.add_run("a.yml", 1, 1, job_ids=(11,))
        fake = h.FakeGitHub(max_calls=4, reserve=3)
        fake.runs, fake.jobs, fake.annotations = self.fake.runs, self.fake.jobs, self.fake.annotations
        self.assertEqual(oi.fetch_annotations(fake, fake.runs, NOW, self.failures, self.notes), {})
        self.assertEqual(fake.calls, 0)
        self.assertEqual(self.notes[0][0], "annotations_cap")

    def test_garbage_job_entries_are_skipped(self):
        self.fake.runs["a.yml"] = [h.make_run(1, ago(hours=1))]
        self.fake.jobs[1] = [None, "x", {"id": "7"}, {"name": "id 없음"}, {"id": 11}]
        self.fake.annotations[11] = [h.make_annotation("경고")]
        found = self.fetch()
        self.assertEqual([a["message"] for a in found[1]], ["경고"])
        self.assertEqual(self.fake.paths(), ["/actions/runs/1/jobs", "/check-runs/11/annotations"])

    def test_two_failing_runs_are_summarised_with_a_remainder(self):
        self.add_run("a.yml", 1, 1, job_ids=(11,))
        self.add_run("b.yml", 2, 2, job_ids=(21,))
        self.fake.fail = [(r"/actions/runs/\d+/jobs", api_error(500, "HTTP 500"))]
        self.fetch()
        self.assertEqual(self.failures, [("annotations", "실행 1: HTTP 500 (외 1건)")])

    def test_a_run_exactly_48_hours_old_is_still_read(self):
        self.add_run("a.yml", 1, 48, job_ids=(11,))
        self.assertEqual(sorted(self.fetch()), [1])

    def test_job_count_per_run_is_capped(self):
        self.add_run("a.yml", 1, 1, job_ids=tuple(range(10, 20)))
        self.fetch()
        self.assertEqual(len(self.fake.paths()), 1 + 6)

    def test_budget_exhausted_mid_run_keeps_what_was_read_and_notes_the_rest(self):
        self.add_run("a.yml", 1, 1, job_ids=(11, 12, 13))
        self.add_run("a.yml", 2, 3, job_ids=(21,))
        fake = h.FakeGitHub(max_calls=3)
        fake.runs, fake.jobs, fake.annotations = self.fake.runs, self.fake.jobs, self.fake.annotations
        found = oi.fetch_annotations(fake, fake.runs, NOW, self.failures, self.notes)
        self.assertEqual(sorted(found), [1])
        self.assertEqual(len(found[1]), 2)                      # jobs 1회 + 주석 2회로 상한
        self.assertEqual(self.notes[0][0], "annotations_cap")

    def test_a_failing_run_does_not_stop_the_others(self):
        self.add_run("a.yml", 1, 1, job_ids=(11,))
        self.add_run("b.yml", 2, 2, job_ids=(21,))
        self.fake.fail = [(r"/actions/runs/1/jobs", api_error(500, "HTTP 500"))]
        found = self.fetch()
        self.assertEqual(sorted(found), [2])
        self.assertEqual(self.failures, [("annotations", "실행 1: HTTP 500")])

    def test_run_without_jobs_is_scanned_with_no_annotations(self):
        self.add_run("a.yml", 1, 1, job_ids=())
        self.assertEqual(self.fetch(), {1: []})


# ----------------------------------------------------------------------------
# 이슈 1개 유지
# ----------------------------------------------------------------------------
def action_items(*titles):
    return [inbox.Item(f"a:{n}", "action", title, url=f"{URL}/pull/{n}") for n, title in enumerate(titles, start=1)]


class IssueSyncTest(unittest.TestCase):
    OWNER = "octo"

    def setUp(self):
        self.fake, self.out = h.FakeGitHub(), []

    def sync(self, items, failures=(), dry=False, visible=None):
        visible = visible if visible is not None else inbox.render(items, URL)
        return oi.sync_issue(self.fake, items, visible, list(failures), self.OWNER, URL, dry, self.out.append)

    def inbox_issue(self):
        found = [i for i in self.fake.issues if i["title"] == inbox.ISSUE_TITLE]
        self.assertEqual(len(found), 1)
        return found[0]

    def seed(self, items, state="open", login=h.BOT, assoc="CONTRIBUTOR", number=50, labels=(inbox.LABEL,), failures=()):
        """이미 있는 모음 이슈(표식 포함)를 가짜 GitHub 에 심는다."""
        visible = inbox.render(items, URL)
        issue = h.make_issue(number, inbox.ISSUE_TITLE, inbox.build_body(visible, inbox.plan_notice(items, None, failures)[1]),
                             state=state, login=login, assoc=assoc, labels=labels)
        self.fake.issues.append(issue)
        return issue

    # --- 만들기
    def test_first_run_creates_label_issue_assignee_body_and_a_mention_comment(self):
        items = action_items("PR #1 병합하면 됩니다", "워크플로 실패")
        result = self.sync(items)
        self.assertEqual((result["action"], result["comment"], result["new"]), ("created", "posted", 2))
        issue = self.inbox_issue()
        self.assertEqual(issue["title"], "[운영] 확인 필요 모음")
        self.assertEqual([label["name"] for label in issue["labels"]], ["ops-inbox"])
        self.assertEqual(issue["assignees"], ["octo"])
        self.assertIn("# 확인 필요 모음", issue["body"])
        self.assertEqual(inbox.parse_marker(issue["body"]).items, ("a:1", "a:2"))
        self.assertIn("ops-inbox", self.fake.labels)
        label = [e[2] for e in self.fake.log if e[:2] == ("POST", "/labels")][0]
        self.assertEqual(label, {"name": "ops-inbox", "color": inbox.LABEL_COLOR, "description": inbox.LABEL_DESCRIPTION})
        comment = self.fake.comments[issue["number"]][0]
        self.assertTrue(comment.startswith("@octo "))
        self.assertIn("PR #1 병합하면 됩니다", comment)
        self.assertIn(f"{URL}/issues/{issue['number']}", comment)
        self.assertEqual([p for p in self.fake.paths("POST")][:2], ["/labels", "/issues"])

    def test_first_run_without_action_items_makes_the_issue_but_no_comment(self):
        result = self.sync([inbox.Item("stat:x", "info", "현황")])
        self.assertEqual((result["action"], result["comment"], result["new"]), ("created", "none", 0))
        self.assertEqual(self.fake.comments, {})

    def test_second_run_with_the_same_content_writes_nothing(self):
        items = action_items("PR #1")
        self.sync(items)
        before = len(self.fake.writes())
        result = self.sync(items)
        self.assertEqual((result["action"], result["comment"], result["new"]), ("unchanged", "none", 0))
        self.assertEqual(len(self.fake.writes()), before)

    def test_assignee_rejection_422_falls_back_to_an_unassigned_issue(self):
        self.fake.reject_assignees = True
        result = self.sync(action_items("PR #1"))
        self.assertEqual(result["action"], "created")
        self.assertEqual(self.inbox_issue()["assignees"], [])
        self.assertTrue(any("담당자(octo)" in line for line in self.out))
        self.assertEqual(len([e for e in self.fake.log if e[0] == "POST" and e[1] == "/issues"]), 2)
        self.assertIn("@octo", self.fake.comments[self.inbox_issue()["number"]][0])          # 알림은 @멘션으로 간다

    def test_other_creation_errors_are_raised(self):
        self.fake.fail = [(r"POST /issues$", api_error(500, "HTTP 500"))]
        with self.assertRaises(oi.ApiError):
            self.sync(action_items("PR #1"))
        self.assertEqual(len([e for e in self.fake.log if e[:2] == ("POST", "/issues")]), 1)       # 담당자 문제가 아니므로 다시 시도하지 않는다
        self.fake.fail = [(r"POST /issues$", api_error(422, "HTTP 422"))]
        self.out.clear()
        with self.assertRaises(oi.ApiError):                                                 # 담당자 없이 다시 해도 같은 오류
            self.sync(action_items("PR #1"))

    def test_label_that_already_exists_is_fine_and_label_failure_does_not_stop_creation(self):
        self.fake.labels.add("ops-inbox")
        self.assertEqual(self.sync(action_items("PR #1"))["action"], "created")
        self.assertEqual(self.out, [])
        other = h.FakeGitHub()
        other.fail = [(r"POST /labels", api_error(403, "HTTP 403: forbidden"))]
        self.fake, self.out = other, []
        self.assertEqual(self.sync(action_items("PR #1"))["action"], "created")
        self.assertTrue(any("라벨 ops-inbox" in line and "HTTP 403" in line for line in self.out))

    def test_creation_without_an_owner_has_no_assignee_and_no_mention(self):
        self.OWNER = ""
        self.sync(action_items("PR #1"))
        self.assertNotIn("assignees", [e for e in self.fake.log if e[1] == "/issues" and e[0] == "POST"][0][2])
        self.assertNotIn("@", self.fake.comments[self.inbox_issue()["number"]][0])

    def test_comment_failure_on_creation_takes_the_new_ids_out_of_the_marker(self):
        self.fake.fail = [(r"POST /issues/\d+/comments", api_error(500, "HTTP 500"))]
        result = self.sync(action_items("PR #1"))
        self.assertEqual((result["action"], result["comment"]), ("created", "failed"))
        self.assertEqual(inbox.parse_marker(self.inbox_issue()["body"]).items, ())
        self.assertTrue(any(line.startswith("::error::") for line in self.out))
        self.fake.fail = []
        again = self.sync(action_items("PR #1"))                                              # 다음 점검이 다시 알린다
        self.assertEqual((again["comment"], again["new"]), ("posted", 1))
        self.assertEqual(inbox.parse_marker(self.inbox_issue()["body"]).items, ("a:1",))
        self.assertEqual(self.sync(action_items("PR #1"))["comment"], "none")

    def test_first_run_writes_the_marker_without_notified_ids_and_adds_them_only_after_the_comment(self):
        self.sync(action_items("PR #1", "PR #2"))
        created = [e for e in self.fake.log if e[:2] == ("POST", "/issues")][0][2]
        self.assertEqual(inbox.parse_marker(created["body"]).items, ())                       # 아직 알리지 못한 id 는 표식에 없다
        self.assertEqual([(m, p) for m, p, _ in self.fake.writes()],
                         [("POST", "/labels"), ("POST", "/issues"), ("POST", "/issues/200/comments"), ("PATCH", "/issues/200")])
        patch = [e for e in self.fake.log if e[0] == "PATCH"][0][2]
        self.assertEqual(set(patch), {"body"})
        self.assertEqual(inbox.parse_marker(self.inbox_issue()["body"]).items, ("a:1", "a:2"))
        self.assertEqual(self.sync(action_items("PR #1", "PR #2"))["action"], "unchanged")

    def test_first_run_without_action_items_needs_no_second_write(self):
        self.sync([inbox.Item("stat:x", "info", "현황"), inbox.Item("c:1", "check", "확인")])
        self.assertEqual([(m, p) for m, p, _ in self.fake.writes()], [("POST", "/labels"), ("POST", "/issues")])

    def test_first_run_with_a_failing_comment_and_a_failing_patch_still_notifies_next_time(self):
        self.fake.fail = [(r"POST /issues/\d+/comments", api_error(500, "HTTP 500")), (r"PATCH /issues/\d+", api_error(500, "HTTP 500"))]
        result = self.sync(action_items("PR #1"))                                              # 코멘트가 실패하면 고칠 본문이 없다 — 예외 없이 끝난다
        self.assertEqual((result["action"], result["comment"]), ("created", "failed"))
        self.assertEqual(inbox.parse_marker(self.inbox_issue()["body"]).items, ())
        self.fake.fail = []
        again = self.sync(action_items("PR #1"))
        self.assertEqual((again["comment"], again["new"]), ("posted", 1))
        self.assertEqual(inbox.parse_marker(self.inbox_issue()["body"]).items, ("a:1",))

    def test_first_run_when_only_the_patch_after_a_good_comment_fails_notifies_again_rather_than_never(self):
        self.fake.fail = [(r"PATCH /issues/\d+", api_error(500, "HTTP 500"))]
        with self.assertRaises(oi.ApiError):
            self.sync(action_items("PR #1"))
        self.assertEqual(len(self.fake.comments[200]), 1)
        self.assertEqual(inbox.parse_marker(self.inbox_issue()["body"]).items, ())             # 알림은 갔지만 표식에는 아직 없다
        self.fake.fail = []
        again = self.sync(action_items("PR #1"))
        self.assertEqual((again["comment"], again["new"]), ("posted", 1))                       # 한 번 더 알린다(영영 못 알리는 쪽보다 낫다)
        self.assertEqual(len(self.fake.comments[200]), 2)
        self.assertEqual(inbox.parse_marker(self.inbox_issue()["body"]).items, ("a:1",))

    def test_first_run_that_creates_the_issue_without_an_assignee_still_adds_the_ids_after_the_comment(self):
        self.fake.reject_assignees = True
        self.sync(action_items("PR #1"))
        self.assertEqual(inbox.parse_marker(self.inbox_issue()["body"]).items, ("a:1",))
        self.assertEqual(len([e for e in self.fake.log if e[0] == "PATCH"]), 1)

    # --- 고치기
    def test_changed_visible_text_patches_only_the_body(self):
        items = action_items("PR #1")
        self.seed(items)
        changed = action_items("PR #1") + [inbox.Item("stat:x", "info", "새 현황")]
        result = self.sync(changed)
        self.assertEqual((result["action"], result["comment"]), ("updated", "none"))
        patch = [e for e in self.fake.log if e[0] == "PATCH"]
        self.assertEqual(len(patch), 1)
        self.assertEqual(set(patch[0][2]), {"body"})
        self.assertIn("새 현황", patch[0][2]["body"])
        self.assertEqual(self.fake.comments, {})

    def test_new_action_item_comments_with_only_the_new_titles_and_patches_the_marker(self):
        self.seed(action_items("PR #1"))
        result = self.sync(action_items("PR #1", "충돌 PR"))
        self.assertEqual((result["action"], result["comment"], result["new"]), ("updated", "posted", 1))
        comment = self.fake.comments[50][0]
        self.assertIn("충돌 PR", comment)
        self.assertNotIn("PR #1\n", comment)
        self.assertIn("1건 생겼습니다", comment)
        self.assertEqual(inbox.parse_marker(self.fake.find(50)["body"]).items, ("a:1", "a:2"))

    def test_comment_is_written_before_the_body_is_patched(self):
        self.seed(action_items("PR #1"))
        self.sync(action_items("PR #1", "새 일"))
        methods = [(m, p) for m, p, _ in self.fake.writes()]
        self.assertEqual(methods, [("POST", "/issues/50/comments"), ("PATCH", "/issues/50")])

    def test_resolved_item_is_dropped_from_the_body_without_a_comment(self):
        self.seed(action_items("PR #1", "PR #2"))
        result = self.sync(action_items("PR #1"))
        self.assertEqual((result["action"], result["comment"]), ("updated", "none"))
        self.assertEqual(inbox.parse_marker(self.fake.find(50)["body"]).items, ("a:1",))

    def test_comment_failure_on_update_is_retried_next_time(self):
        self.seed(action_items("PR #1"))
        self.fake.fail = [(r"POST /issues/\d+/comments", api_error(500, "HTTP 500"))]
        result = self.sync(action_items("PR #1", "새 일"))
        self.assertEqual((result["action"], result["comment"]), ("updated", "failed"))
        self.assertEqual(inbox.parse_marker(self.fake.find(50)["body"]).items, ("a:1",))     # 새 id 는 아직 알리지 못했다
        self.fake.fail = []
        again = self.sync(action_items("PR #1", "새 일"))
        self.assertEqual((again["action"], again["comment"], again["new"]), ("updated", "posted", 1))
        self.assertEqual(self.sync(action_items("PR #1", "새 일"))["action"], "unchanged")

    def test_failed_source_keeps_its_ids_so_recovery_does_not_alert_again(self):
        pr = [inbox.Item("pr:15:ready", "action", "PR #15 병합하면 됩니다")]
        self.sync(pr)
        number = self.inbox_issue()["number"]
        outage = [inbox.Item("source:pulls", "check", "조회 실패 — 열린 PR 목록")]
        self.sync(outage, failures=[("pulls", "HTTP 502")])
        self.assertEqual(inbox.parse_marker(self.fake.find(number)["body"]).items, ("pr:15:ready",))
        before = len(self.fake.comments.get(number, []))
        self.sync(pr)
        self.assertEqual(len(self.fake.comments.get(number, [])), before)                     # 복구 때 다시 알리지 않는다

    def test_body_without_a_marker_is_rewritten(self):
        issue = self.seed(action_items("PR #1"))
        issue["body"] = "사람이 지운 본문"
        result = self.sync(action_items("PR #1"))
        self.assertEqual(result["action"], "updated")
        self.assertEqual(result["new"], 1)                       # 표식이 없으면 지금 있는 action 이 전부 새 것

    # --- 닫힌 이슈
    def test_closed_issue_with_a_new_action_is_commented_and_reopened_with_a_fresh_body(self):
        self.seed(action_items("PR #1"), state="closed")
        result = self.sync(action_items("PR #1", "새 일"))
        self.assertEqual((result["action"], result["comment"]), ("reopened", "posted"))
        issue = self.fake.find(50)
        self.assertEqual(issue["state"], "open")
        self.assertEqual(inbox.parse_marker(issue["body"]).items, ("a:1", "a:2"))
        self.assertEqual([(m, p) for m, p, _ in self.fake.writes()], [("POST", "/issues/50/comments"), ("PATCH", "/issues/50")])
        self.assertEqual(len([i for i in self.fake.issues if i["title"] == inbox.ISSUE_TITLE]), 1)        # 새로 만들지 않는다

    def test_closed_issue_without_new_actions_stays_closed_and_only_its_body_is_kept_current(self):
        self.seed(action_items("PR #1"), state="closed")
        same = self.sync(action_items("PR #1"))
        self.assertEqual((same["action"], same["comment"]), ("unchanged", "none"))
        self.assertEqual(self.fake.writes(), [])                                              # 달라진 것이 없으면 아무것도 쓰지 않는다
        changed = self.sync(action_items("PR #1") + [inbox.Item("stat:x", "info", "달라진 현황")])
        self.assertEqual((changed["action"], changed["comment"]), ("updated_closed", "none"))
        patches = [e for e in self.fake.log if e[0] == "PATCH"]
        self.assertEqual([set(p[2]) for p in patches], [{"body"}])                            # state 는 건드리지 않는다
        self.assertIn("달라진 현황", self.fake.find(50)["body"])
        self.assertEqual(self.fake.find(50)["state"], "closed")
        self.assertEqual(self.fake.comments, {})

    def test_an_action_that_vanished_and_came_back_while_the_issue_was_closed_is_new_again(self):
        self.seed(action_items("PR #1"), state="closed")
        self.assertEqual(self.sync([])["action"], "updated_closed")                           # 해소: 닫힌 채 표식에서 빠진다
        self.assertEqual(inbox.parse_marker(self.fake.find(50)["body"]).items, ())
        again = self.sync(action_items("PR #1"))
        self.assertEqual((again["action"], again["comment"], again["new"]), ("reopened", "posted", 1))
        self.assertEqual(self.fake.find(50)["state"], "open")

    def test_dry_run_on_a_closed_issue_without_new_actions_reports_only_a_body_update(self):
        self.seed(action_items("PR #1"), state="closed")
        self.assertEqual(self.sync(action_items("PR #1"), dry=True)["action"], "unchanged")
        self.assertEqual(self.sync(action_items("PR #1") + [inbox.Item("stat:x", "info", "달라진 현황")], dry=True)["action"], "would_update")
        self.assertEqual(self.fake.writes(), [])

    def test_dry_run_on_a_closed_issue_with_new_action_says_it_would_reopen(self):
        self.seed(action_items("PR #1"), state="closed")
        result = self.sync(action_items("PR #1", "새 일"), dry=True)
        self.assertEqual((result["action"], result["comment"]), ("would_reopen", "dry"))
        self.assertEqual(self.fake.writes(), [])

    # --- 이슈 찾기
    def test_issue_is_found_by_label_with_a_single_lookup(self):
        self.seed(action_items("PR #1"))
        self.assertEqual(oi.find_inbox_issue(self.fake)["number"], 50)
        self.assertEqual(len(self.fake.log), 1)
        self.assertEqual(self.fake.log[0][2], {"labels": "ops-inbox", "state": "all", "per_page": 30})

    def test_a_labelled_issue_is_ours_even_if_a_person_renamed_it(self):
        issue = self.seed(action_items("PR #1"))
        issue["title"] = "내가 바꾼 제목"
        self.assertEqual(oi.find_inbox_issue(self.fake)["number"], 50)
        self.assertEqual(self.sync(action_items("PR #1"))["action"], "unchanged")
        self.assertEqual(len(self.fake.issues), 1)                                           # 새 이슈를 만들지 않는다
        self.assertEqual(self.fake.find(50)["title"], "내가 바꾼 제목")                       # 제목은 사람이 정한 대로 둔다

    def test_renaming_and_unlabelling_makes_it_a_stranger_to_the_inbox_and_a_new_one_is_made(self):
        issue = self.seed(action_items("PR #1"), labels=())
        issue["title"] = "내가 바꾼 제목"
        self.assertIsNone(oi.find_inbox_issue(self.fake))
        self.assertEqual(self.sync(action_items("PR #1"))["action"], "created")
        self.assertEqual(len(self.fake.issues), 2)

    def test_issue_without_the_label_is_found_by_title_among_bot_issues(self):
        self.seed(action_items("PR #1"), labels=())
        self.fake.issues.append(h.make_watchdog(9))
        self.assertEqual(oi.find_inbox_issue(self.fake)["number"], 50)
        self.assertEqual(len(self.fake.log), 2)
        self.assertEqual(self.fake.log[1][2], {"state": "all", "creator": "github-actions[bot]", "per_page": 100})

    def test_a_missing_issue_is_none(self):
        self.fake.issues.append(h.make_issue(3, "다른 이슈"))
        self.assertIsNone(oi.find_inbox_issue(self.fake))

    def test_open_issue_wins_over_closed_and_lowest_number_wins_among_equals(self):
        self.seed([], state="closed", number=40)
        self.seed([], number=60)
        self.seed([], number=55)
        self.assertEqual(oi.find_inbox_issue(self.fake)["number"], 55)
        self.fake.issues = [i for i in self.fake.issues if i["state"] == "closed"]
        self.assertEqual(oi.find_inbox_issue(self.fake)["number"], 40)

    def test_same_title_from_a_stranger_is_ignored_and_ours_is_created(self):
        self.seed([], login="stranger", assoc="NONE", number=7)
        self.assertIsNone(oi.find_inbox_issue(self.fake))
        result = self.sync(action_items("PR #1"))
        self.assertEqual(result["action"], "created")
        self.assertEqual(self.fake.find(7)["body"], inbox.build_body(inbox.render([], URL), []))     # 낯선 이슈는 건드리지 않는다

    def test_owner_authored_issue_is_reused(self):
        self.seed([], login="octo", assoc="OWNER", number=8)
        self.assertEqual(oi.find_inbox_issue(self.fake)["number"], 8)

    def test_pull_requests_with_the_same_title_are_not_issues(self):
        pr = h.make_issue(9, inbox.ISSUE_TITLE, "", labels=(inbox.LABEL,), pull=True)
        self.fake.issues.append(pr)
        self.assertIsNone(oi.find_inbox_issue(self.fake))

    # --- 연습
    def test_dry_run_reads_but_never_writes(self):
        result = self.sync(action_items("PR #1"), dry=True)
        self.assertEqual((result["action"], result["comment"], result["new"]), ("would_create", "dry", 1))
        self.assertEqual(self.fake.writes(), [])
        self.assertTrue(self.fake.paths())                                   # 읽기는 했다(할 일을 알려 주려고)
        self.seed(action_items("PR #1"))
        self.assertEqual(self.sync(action_items("PR #1"), dry=True)["action"], "unchanged")
        self.assertEqual(self.sync(action_items("PR #1", "새 일"), dry=True)["action"], "would_update")
        self.assertEqual(self.fake.writes(), [])

    def test_describe_covers_every_action_and_comment_state(self):
        for action in oi._RESULT_TEXT:
            for comment in oi._COMMENT_TEXT:
                text = oi.describe({"action": action, "number": 5, "new": 2, "comment": comment})
                self.assertIn("#5", text)
                self.assertIn("2건", text)
        self.assertNotIn("#", oi.describe({"action": "would_create", "number": None, "new": 0, "comment": "none"}))


# ----------------------------------------------------------------------------
# 전체 실행
# ----------------------------------------------------------------------------
class RunTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.summary = self.tmp / "summary.md"
        self.out = []

    def world(self, histories=None, workflows=("chanceblog.yml", "blogger.yml")):
        root = h.make_root(self.tmp / "repo", histories=histories, workflows=workflows)
        fake = h.FakeGitHub()
        fake.issues = [h.make_watchdog(9)]
        fake.pulls = [h.make_pull_raw(15, title="워치독 보강", sha="c" * 40)]
        fake.details = {15: {"mergeable": True, "mergeable_state": "clean"}}
        fake.check_runs = {"c" * 40: [h.make_check("validate")]}
        fake.runs = {name: [h.make_run(i, ago(hours=1 + i), name=f"{name} 이름")] for i, name in enumerate(workflows, start=1)}
        return fake, root

    def run_script(self, fake, root, env=None, now=NOW):
        environ = dict(ENV, GITHUB_STEP_SUMMARY=str(self.summary), **(env or {}))
        return oi.run(environ, fake, now, root, self.out.append, sleep=lambda seconds: None)         # 시험은 실제로 기다리지 않는다

    def summary_text(self):
        return self.summary.read_text(encoding="utf-8") if self.summary.exists() else ""

    def everything_printed(self, fake):
        return "\n".join(self.out) + self.summary_text() + json.dumps(fake.log, ensure_ascii=False) + json.dumps(fake.issues, ensure_ascii=False)

    def test_happy_path_creates_the_issue_and_writes_the_same_markdown_to_the_summary(self):
        fake, root = self.world(histories={"history.json": [{"date": "2026-10-25", "slot": 9}]})
        code = self.run_script(fake, root)
        self.assertEqual(code, 0)
        issue = [i for i in fake.issues if i["title"] == inbox.ISSUE_TITLE][0]
        visible = issue["body"].split("\n\n<!-- ops-inbox:")[0]
        summary = self.summary_text()
        self.assertTrue(summary.startswith(visible.rstrip()))
        self.assertIn("### 이번 점검", summary)
        self.assertIn("점검 시각: 2026-10-25 15:00 KST", summary)
        self.assertIn("이슈를 새로 만들었습니다", summary)
        for needle in ("워치독 알림 — chance: STALE", "PR #15 병합하면 됩니다", "Chance_Blog: 마지막 글 2026-10-25 09시 슬롯(KST)"):
            self.assertIn(needle, visible)
        self.assertIn("[점검] 지금 해야 할 일 2건 · 확인하면 좋은 것 0건 · 참고 2건 (조회 실패 0건, GitHub API 호출 ", self.out[0])
        self.assertTrue(fake.comments[issue["number"]][0].startswith("@octo "))

    PLATFORM_WARNING = ("Node.js 20 is deprecated. The following actions target Node.js 20 but are being forced to run on Node.js 24: "
                        "actions/checkout@v4, actions/setup-python@v5.")
    PLATFORM_NOTICE = "The ubuntu-latest label will migrate to Ubuntu 26 beginning October 19, 2026."

    def add_platform_run(self, fake, file, run_id, job_id, hours):
        run = h.make_run(run_id, ago(hours=hours), name=f"{file} 실행 이름", path=f".github/workflows/{file}")
        fake.runs.setdefault(file, []).append(run)
        fake.runs[file].sort(key=lambda r: r["created_at"], reverse=True)
        fake.jobs[run_id] = [{"id": job_id}]
        fake.annotations[job_id] = [h.make_annotation(self.PLATFORM_WARNING), h.make_annotation(self.PLATFORM_NOTICE, "notice")]

    def test_a_run_of_another_workflow_does_not_make_the_inbox_rewrite_the_issue(self):
        fake, root = self.world(workflows=("chanceblog.yml", "blogger.yml", "pages.yml"))
        fake.runs = {"chanceblog.yml": [], "blogger.yml": [], "pages.yml": []}
        self.add_platform_run(fake, "chanceblog.yml", 11, 111, 3)
        self.add_platform_run(fake, "blogger.yml", 12, 112, 2)
        self.assertEqual(self.run_script(fake, root), 0)
        body = self.inbox_issue(fake)["body"]
        self.assertIn("플랫폼 경고 2종", body)
        writes = len(fake.writes())
        self.add_platform_run(fake, "pages.yml", 13, 113, 0.1)         # 다른 워크플로가 방금(가장 최근에) 돌았고 같은 안내가 달렸다
        self.assertEqual(self.run_script(fake, root), 0)
        self.assertEqual(len(fake.writes()), writes)                   # 이슈를 다시 쓰지 않는다
        self.assertEqual(self.inbox_issue(fake)["body"], body)
        self.assertIn("변경 없음", self.summary_text())

    def test_workflow_names_in_the_issue_come_from_the_checked_out_files_not_from_run_names(self):
        fake, root = self.world(workflows={"chanceblog.yml": 'name: "Chance 글 자동 작성·게시"\non: push\n', "blogger.yml": "name: Blogger 글 자동 작성\n"})
        fake.runs["chanceblog.yml"] = [h.make_run(5, ago(hours=1), "failure", name="Chance 기존 글 이미지 교체 · 연습(저장 안 함)")]
        self.assertEqual(self.run_script(fake, root), 0)
        body = self.inbox_issue(fake)["body"]
        self.assertIn("워크플로 실패 — Chance 글 자동 작성·게시", body)
        self.assertNotIn("이미지 교체", body)
        self.assertTrue(all(path.endswith("/runs") for path in fake.paths() if path.startswith("/actions/workflows")))      # 이름을 읽느라 API 를 더 부르지 않는다

    def test_a_workflow_file_without_a_readable_name_is_shown_by_its_file_name(self):
        fake, root = self.world(workflows={"chanceblog.yml": "on: push\n", "blogger.yml": "name: Blogger 글 자동 작성\n"})
        fake.runs["chanceblog.yml"] = [h.make_run(5, ago(hours=1), "failure", name="Chance 기존 글 이미지 교체 · 연습(저장 안 함)")]
        self.run_script(fake, root)
        body = self.inbox_issue(fake)["body"]
        self.assertIn("워크플로 실패 — chanceblog.yml", body)
        self.assertNotIn("이미지 교체", body)

    def test_fork_pull_request_runs_never_become_items_and_are_not_read_for_annotations(self):
        fake, root = self.world(workflows=("chanceblog.yml",))
        fork_bad = h.make_run(22, ago(minutes=5), "failure", event="pull_request", head_repo="stranger/blog")
        fork_ok = h.make_run(23, ago(minutes=4), "success", event="pull_request", head_repo="stranger/blog")
        fake.runs = {"chanceblog.yml": [fork_ok, fork_bad, h.make_run(21, ago(hours=3))]}
        fake.jobs[23] = [{"id": 233}]
        fake.annotations[233] = [h.make_annotation("포크의 경고")]
        self.run_script(fake, root)
        body = self.inbox_issue(fake)["body"]
        self.assertNotIn("워크플로 실패", body)
        self.assertNotIn("포크의 경고", body)
        self.assertFalse(any("/runs/22/" in path or "/runs/23/" in path for path in fake.paths()))

    def test_pull_request_runs_of_this_repository_still_count_end_to_end(self):
        fake, root = self.world(workflows=("chanceblog.yml",))
        own_pr_bad = h.make_run(24, ago(minutes=2), "failure", event="pull_request", head_repo=h.REPO)
        fork_ok = h.make_run(23, ago(minutes=4), "success", event="pull_request", head_repo="stranger/blog")
        fake.runs = {"chanceblog.yml": [own_pr_bad, fork_ok, h.make_run(21, ago(hours=3))]}
        self.run_script(fake, root)
        body = self.inbox_issue(fake)["body"]
        self.assertIn("워크플로 실패", body)                         # 이 저장소의 PR 이 일으킨 실패는 센다(포크 실행의 성공은 가리지 못한다)
        self.assertIn(f"{URL}/actions/runs/24", body)

    def test_a_pull_whose_mergeable_value_was_not_computed_yet_is_judged_in_the_same_check(self):
        fake, root = self.world()
        fake.details[15] = [{"mergeable": None, "mergeable_state": "unknown"}, {"mergeable": True, "mergeable_state": "clean"}]
        slept = []
        environ = dict(ENV, GITHUB_STEP_SUMMARY=str(self.summary))
        self.assertEqual(oi.run(environ, fake, NOW, root, self.out.append, sleep=slept.append), 0)
        self.assertIn("PR #15 병합하면 됩니다", self.summary_text())
        self.assertEqual(slept, [oi.PULL_RETRY_WAIT_SECONDS])

    def test_second_run_is_silent(self):
        fake, root = self.world()
        self.run_script(fake, root)
        writes = len(fake.writes())
        self.assertEqual(self.run_script(fake, root), 0)
        self.assertEqual(len(fake.writes()), writes)
        self.assertIn("변경 없음", self.summary_text())

    def test_summary_is_appended_not_overwritten(self):
        self.summary.write_text("앞선 단계의 요약\n", encoding="utf-8")
        fake, root = self.world()
        self.run_script(fake, root)
        self.assertTrue(self.summary_text().startswith("앞선 단계의 요약"))

    def test_unwritable_summary_path_does_not_break_the_run(self):
        fake, root = self.world()
        self.summary.mkdir()
        self.assertEqual(self.run_script(fake, root), 0)
        self.assertTrue(any("실행 요약 쓰기 실패" in line for line in self.out))

    def test_without_a_summary_file_variable_nothing_is_written(self):
        fake, root = self.world()
        code = oi.run(dict(ENV), fake, NOW, root, self.out.append)
        self.assertEqual(code, 0)
        self.assertFalse(self.summary.exists())

    def test_dry_run_writes_nothing_to_github_but_reports_the_plan(self):
        fake, root = self.world()
        for flag in ("true", "1", "YES"):
            fake.log.clear()
            self.assertEqual(self.run_script(fake, root, {"INBOX_DRY_RUN": flag}), 0)
            self.assertEqual(fake.writes(), [], flag)
        self.assertEqual([i for i in fake.issues if i["title"] == inbox.ISSUE_TITLE], [])
        self.assertIn("(연습) 이슈를 새로 만들 예정", self.summary_text())
        self.assertIn("연습 실행이라 이슈·코멘트를 쓰지 않았습니다", self.summary_text())
        fake.log.clear()
        self.run_script(fake, root, {"INBOX_DRY_RUN": "false"})
        self.assertTrue(fake.writes())

    def test_without_a_token_it_prints_read_only_and_never_touches_the_inbox_issue(self):
        fake, root = self.world()
        env = {k: v for k, v in ENV.items() if k != "GITHUB_TOKEN"}
        code = oi.run(env, fake, NOW, root, self.out.append)
        self.assertEqual(code, 0)
        self.assertEqual(fake.writes(), [])
        self.assertFalse(any(p == "/issues" and params.get("labels") for m, p, params in fake.log))
        self.assertTrue(any("토큰이 없어 읽기 전용" in line for line in self.out))
        self.assertTrue(any("# 확인 필요 모음" in line for line in self.out))
        # 정확한 문구: 열린 이슈 목록(워치독 알림용)은 읽지만 모음 이슈는 읽지도 쓰지도 않는다
        self.assertTrue(any(p == "/issues" and params.get("state") == "open" for m, p, params in fake.log))
        line = next(line for line in self.out if "토큰이 없어 읽기 전용" in line)
        self.assertIn("열린 이슈 목록은 읽었지만 모음 이슈는 읽지도 쓰지도 않았습니다", line)
        self.assertIn("열린 이슈 목록(워치독 알림용)은 읽지만 모음 이슈는 읽지도 쓰지도 않는다", oi.__doc__)

    def test_whitespace_only_token_counts_as_no_token(self):
        fake, root = self.world()
        env = dict(ENV, GITHUB_TOKEN="   ")
        self.assertEqual(oi.run(env, fake, NOW, root, self.out.append), 0)
        self.assertEqual(fake.writes(), [])

    def test_missing_or_malformed_repository_is_a_config_error_that_calls_nothing(self):
        fake, root = self.world()
        for repo in (None, "", "no-slash", "../x", "a/b/c"):
            env = dict(ENV)
            env.pop("GITHUB_REPOSITORY")
            if repo is not None:
                env["GITHUB_REPOSITORY"] = repo
            self.assertEqual(oi.run(env, fake, NOW, root, self.out.append), 2, repo)
        self.assertEqual(fake.log, [])
        self.assertTrue(any("GITHUB_REPOSITORY" in line for line in self.out))

    def inbox_issue(self, fake):
        return [i for i in fake.issues if i["title"] == inbox.ISSUE_TITLE][0]

    def test_every_source_can_fail_without_stopping_the_run(self):
        fake, root = self.world()
        fake.fail = [(r"GET /issues\?state=open", api_error(502, "HTTP 502: Bad Gateway")),
                     (r"GET /pulls\?", api_error(502, "HTTP 502: Bad Gateway")),
                     (r"GET /actions/(workflows|runs)", api_error(502, "HTTP 502: Bad Gateway"))]
        self.assertEqual(self.run_script(fake, root), 0)
        body = self.inbox_issue(fake)["body"]
        for label in ("열린 이슈 목록", "열린 PR 목록", "워크플로 실행 기록", "승인 대기 실행"):
            self.assertIn(f"조회 실패 — {label}", body)
        self.assertIn("조회 실패 — 열린 PR 목록", self.summary_text())

    def test_failed_sources_show_as_check_items_in_the_issue_body(self):
        fake, root = self.world()
        fake.fail = [(r"GET /pulls\?", api_error(502, "HTTP 502: Bad Gateway"))]
        self.assertEqual(self.run_script(fake, root), 0)
        body = self.inbox_issue(fake)["body"]
        self.assertIn("## 확인하면 좋은 것", body)
        self.assertIn("조회 실패 — 열린 PR 목록", body)
        self.assertIn("HTTP 502", body)
        self.assertNotIn("PR #15", body)

    def test_a_single_pull_detail_failure_keeps_the_other_sources_and_names_the_pull(self):
        fake, root = self.world()
        fake.fail = [(r"GET /pulls/15$", api_error(500, "HTTP 500: boom"))]
        self.assertEqual(self.run_script(fake, root), 0)
        body = self.inbox_issue(fake)["body"]
        self.assertIn("PR #15 상태 확인 중", body)
        self.assertIn("조회하지 못했습니다(HTTP 500: boom)", body)
        self.assertIn("조회 실패 — PR 검사·병합 상태", body)
        self.assertIn("워치독 알림 — chance: STALE", body)

    def test_corrupt_history_is_a_check_item_and_other_items_remain(self):
        fake, root = self.world(histories={"history.json": "{깨짐"})
        self.assertEqual(self.run_script(fake, root), 0)
        text = self.summary_text()
        self.assertIn("조회 실패 — 블로그 이력 파일", text)
        self.assertIn("history.json", text)
        self.assertIn("PR #15 병합하면 됩니다", text)

    def test_unexpected_bugs_are_not_swallowed(self):
        fake, root = self.world()
        with mock.patch.object(inbox, "build_items", side_effect=KeyError("버그")):
            with self.assertRaises(KeyError):
                self.run_script(fake, root)

    def test_issue_write_failure_exits_one_after_the_summary_is_written(self):
        fake, root = self.world()
        fake.fail = [(r"POST /issues$", api_error(403, "HTTP 403: Resource not accessible by integration"))]
        self.assertEqual(self.run_script(fake, root), 1)
        self.assertEqual([line for line in self.out if str(line).startswith("::")], [oi.ERROR_ISSUE_FAILED])       # 주석은 고정 문장
        self.assertTrue(any("HTTP 403" in line and not line.startswith("::") for line in self.out))                  # 이유는 일반 로그 줄
        text = self.summary_text()
        self.assertIn("PR #15 병합하면 됩니다", text)             # 이슈를 못 써도 요약에는 남아 있다
        self.assertIn("이슈를 읽거나 쓰지 못했습니다", text)

    def test_issue_lookup_failure_exits_one(self):
        fake, root = self.world()
        fake.fail = [(r"GET /issues\?labels=", api_error(500, "HTTP 500"))]
        self.assertEqual(self.run_script(fake, root), 1)
        self.assertEqual(fake.writes(), [])
        self.assertIn("PR #15 병합하면 됩니다", self.summary_text())

    def test_comment_failure_exits_one_and_is_retried_on_the_next_run(self):
        fake, root = self.world()
        fake.fail = [(r"POST /issues/\d+/comments", api_error(500, "HTTP 500"))]
        self.assertEqual(self.run_script(fake, root), 1)
        fake.fail = []
        self.assertEqual(self.run_script(fake, root), 0)
        number = [i for i in fake.issues if i["title"] == inbox.ISSUE_TITLE][0]["number"]
        self.assertEqual(len(fake.comments[number]), 1)

    # --- ::error:: 주석에는 고정 문장만(R9). 상세는 접고 마스킹한 일반 로그 줄로
    HOSTILE = f"HTTP 500: {TOKEN}\n::stop-commands::x\n@everyone <b>x</b> ::error::위조 [링크](http://e.example) ##[group]g"

    def assert_only_the_fixed_annotations(self, fake, allowed):
        for block in self.out:
            for line in str(block).splitlines():
                if line.lstrip().startswith("::"):
                    self.assertIn(line, allowed, line)
                self.assertNotIn("##[", line)
        self.assertNotIn(TOKEN, self.everything_printed(fake))

    def reason_lines(self, marker):
        return [line for line in self.out if marker in str(line) and not str(line).startswith("::")]

    def test_a_failed_issue_write_gives_a_fixed_annotation_and_the_reason_in_a_plain_line(self):
        fake, root = self.world()
        fake.fail = [(r"POST /issues$", oi.ApiError(self.HOSTILE, status=403))]
        self.assertEqual(self.run_script(fake, root), 1)
        self.assertEqual([line for line in self.out if str(line).startswith("::")], [oi.ERROR_ISSUE_FAILED])
        self.assert_only_the_fixed_annotations(fake, (oi.ERROR_ISSUE_FAILED,))
        lines = self.reason_lines("HTTP 500")
        self.assertEqual(len(lines), 1)
        for raw in ("\n", "::", "@", "<", "](", TOKEN):
            self.assertNotIn(raw, lines[0], raw)
        self.assertNotIn("HTTP", oi.ERROR_ISSUE_FAILED)

    def test_a_failed_comment_gives_a_fixed_annotation_and_the_reason_in_a_plain_line(self):
        fake, root = self.world()
        fake.fail = [(r"POST /issues/\d+/comments", oi.ApiError(self.HOSTILE, status=500))]
        self.assertEqual(self.run_script(fake, root), 1)
        self.assertEqual([line for line in self.out if str(line).startswith("::")], [oi.ERROR_COMMENT_FAILED])
        self.assert_only_the_fixed_annotations(fake, (oi.ERROR_COMMENT_FAILED,))
        lines = self.reason_lines("HTTP 500")
        self.assertEqual(len(lines), 1)
        for raw in ("\n", "::", "@", "<", "](", TOKEN):
            self.assertNotIn(raw, lines[0], raw)
        self.assertNotIn("HTTP", oi.ERROR_COMMENT_FAILED)

    def test_post_comment_alone_gives_the_same_fixed_annotation_and_one_plain_reason_line(self):
        fake, out = h.FakeGitHub(), []
        fake.fail = [(r"POST /issues/5/comments", oi.ApiError(self.HOSTILE, status=500))]
        self.assertFalse(oi.post_comment(fake, 5, "본문", out.append))
        self.assertEqual(out[0], oi.ERROR_COMMENT_FAILED)
        self.assertEqual(len(out), 2)
        self.assertNotIn("::", out[1])
        self.assertTrue(oi.post_comment(h.FakeGitHub(), 5, "본문", out.append))
        self.assertEqual(len(out), 2)

    def test_a_failed_label_is_logged_as_one_plain_folded_line(self):
        fake, root = self.world()
        fake.fail = [(r"POST /labels", oi.ApiError(self.HOSTILE, status=403))]
        self.assertEqual(self.run_script(fake, root), 0)
        self.assert_only_the_fixed_annotations(fake, ())
        lines = self.reason_lines("라벨")
        self.assertEqual(len(lines), 1)
        for raw in ("\n", "::", "@", "<", TOKEN):
            self.assertNotIn(raw, lines[0], raw)
        self.assertIn("HTTP 500", lines[0])

    def test_every_printed_line_that_starts_with_a_workflow_command_is_a_fixed_sentence(self):
        for pattern, error, expected in ((r"POST /issues$", oi.ApiError(self.HOSTILE, status=403), (oi.ERROR_ISSUE_FAILED,)),
                                         (r"GET /issues\?labels=", oi.ApiError(self.HOSTILE, status=500), (oi.ERROR_ISSUE_FAILED,)),
                                         (r"POST /issues/\d+/comments", oi.ApiError(self.HOSTILE, status=500), (oi.ERROR_COMMENT_FAILED,)),
                                         (r"GET /actions/runs\?", oi.ApiError(self.HOSTILE, status=500), ()),
                                         (r"GET /pulls\?", oi.ApiError(self.HOSTILE, status=500), ())):
            self.out.clear()
            fake, root = self.world()
            fake.fail = [(pattern, error)]
            self.run_script(fake, root)
            self.assert_only_the_fixed_annotations(fake, expected)

    def test_blogger_secrets_problem_becomes_an_action_with_names_only(self):
        history = [h.make_entry("generated_unpublished", ago(hours=30), [h.SECRETS_REASON]),
                   h.make_entry("generated_unpublished", ago(hours=6), [h.SECRETS_REASON])]
        fake, root = self.world(histories={"blogger_history.json": history})
        self.run_script(fake, root)
        text = self.summary_text()
        self.assertIn("Blogger (macat0722) 게시 설정(시크릿) 필요", text)
        self.assertIn("BLOGGER_REFRESH_TOKEN", text)
        self.assertIn(f"{URL}/settings/secrets/actions", text)

    def test_pause_variable_becomes_an_action(self):
        fake, root = self.world()
        self.run_script(fake, root, {"PIPELINE_PAUSE": "true"})
        self.assertIn("자동 발행이 멈춰 있습니다", self.summary_text())
        fake2, root2 = self.world()
        self.run_script(fake2, root2, {"PIPELINE_PAUSE": ""})
        self.assertNotIn("자동 발행이 멈춰 있습니다", self.summary_text().split("### 이번 점검")[-1])

    def test_default_branch_variable_is_used_for_run_lookups(self):
        fake, root = self.world()
        self.run_script(fake, root, {"DEFAULT_BRANCH": "trunk"})
        run_calls = [params for m, p, params in fake.log if p.endswith("/runs") and "workflows" in p]
        self.assertTrue(run_calls)
        self.assertTrue(all(params["branch"] == "trunk" for params in run_calls))
        fake2, root2 = self.world()
        self.run_script(fake2, root2, {"DEFAULT_BRANCH": ""})
        self.assertTrue(all(params["branch"] == "main" for m, p, params in fake2.log if "workflows" in p))

    def test_owner_defaults_to_the_repository_owner_part(self):
        fake, root = self.world()
        env = {"GITHUB_REPOSITORY": h.REPO, "GITHUB_TOKEN": TOKEN}
        oi.run(env, fake, NOW, root, self.out.append)
        issue = [i for i in fake.issues if i["title"] == inbox.ISSUE_TITLE][0]
        self.assertEqual(issue["assignees"], ["octo"])

    def test_the_token_never_appears_in_any_output_log_summary_or_issue(self):
        fake, root = self.world()
        fake.fail = [(r"GET /actions/runs\?", api_error(500, f"HTTP 500: {TOKEN}"))]
        self.run_script(fake, root)
        self.assertNotIn(TOKEN, self.everything_printed(fake))

    def test_printed_lines_cannot_start_workflow_commands_except_the_intended_error(self):
        fake, root = self.world()
        fake.issues = [h.make_watchdog(9, message="::error::위조\n::add-mask::x"), h.make_issue(77, "[Watchdog] ::stop-commands::", "심각도: critical")]
        fake.pulls[0]["title"] = "::warning::가짜 제목\n##[group]x"
        self.run_script(fake, root)
        for block in self.out:
            for line in str(block).splitlines():
                self.assertFalse(line.lstrip().startswith("::"), line)
                self.assertNotIn("##[", line)

    def test_api_call_cap_comes_from_the_environment_with_sane_bounds(self):
        low, high = oi.MIN_API_CALLS, oi.MAX_API_CALLS
        self.assertEqual((low, high), (24, 1000))
        self.assertEqual(oi._int_env("40", 150, low, high), 40)
        for edge in ("24", "1000", " 24 "):
            self.assertEqual(oi._int_env(edge, 150, low, high), int(edge), edge)
        for bad in (None, "", "abc", "23", "14", "9", "5", "4", "1001", "-3", "0", "2.5"):
            self.assertEqual(oi._int_env(bad, 150, low, high), 150, bad)
            self.assertIsNone(oi._int_env(bad, None, low, high), bad)

    def test_the_smallest_cap_keeps_the_whole_write_reserve(self):
        """하한이 너무 낮으면(옛 5) reserve 가 cap // 3 으로 줄어 쓰기가 실패하거나 알림이 유실된다. 하한에서도 reserve 는 그대로 WRITE_RESERVE 다."""
        self.assertGreaterEqual(oi.MIN_API_CALLS, 3 * oi.WRITE_RESERVE)
        self.assertGreaterEqual(oi.MIN_API_CALLS - oi.WRITE_RESERVE, 16)           # 읽기에 쓸 수 있는 호출이 최소 16회는 남는다

    def test_a_rejected_call_cap_is_mentioned_in_the_log_and_a_good_one_is_not(self):
        fake, root = self.world()
        for value, rejected in (("9", True), ("23", True), ("abc", True), ("24", False), ("1000", False), ("", False)):
            self.out.clear()
            self.run_script(fake, root, {"INBOX_MAX_API_CALLS": value, "INBOX_DRY_RUN": "true"})
            lines = [line for line in self.out if "INBOX_MAX_API_CALLS" in str(line)]
            self.assertEqual(len(lines), 1 if rejected else 0, value)
            if rejected:
                self.assertIn(f"{oi.MIN_API_CALLS}~{oi.MAX_API_CALLS}", lines[0])
                self.assertIn(f"{oi.MAX_CALLS_WITH_TOKEN}회", lines[0])

    def test_the_real_client_gets_the_documented_call_budget_and_write_reserve(self):
        class Stop(Exception):
            pass

        built = []

        def construct(*args, **kwargs):
            built.append((args, kwargs))
            raise Stop

        fake, root = self.world()
        with_token = {"GITHUB_TOKEN": TOKEN}
        cases = (                                   # (환경변수, 호출 상한, 쓰기용 reserve, 클라이언트에 넘기는 토큰)
            (with_token, 150, 8, TOKEN), ({}, 25, 0, None),
            (dict(with_token, INBOX_MAX_API_CALLS="30"), 30, 8, TOKEN), (dict(with_token, INBOX_MAX_API_CALLS="24"), 24, 8, TOKEN),
            ({"INBOX_MAX_API_CALLS": "40"}, 40, 0, None), ({"INBOX_MAX_API_CALLS": "24"}, 24, 0, None),
            (dict(with_token, INBOX_MAX_API_CALLS="1000"), 1000, 8, TOKEN),
            (dict(with_token, INBOX_MAX_API_CALLS="23"), 150, 8, TOKEN), (dict(with_token, INBOX_MAX_API_CALLS="9"), 150, 8, TOKEN),
            (dict(with_token, INBOX_MAX_API_CALLS="5"), 150, 8, TOKEN), (dict(with_token, INBOX_MAX_API_CALLS="4"), 150, 8, TOKEN),
            (dict(with_token, INBOX_MAX_API_CALLS="1001"), 150, 8, TOKEN), ({"INBOX_MAX_API_CALLS": "23"}, 25, 0, None))   # 범위(24~1000) 밖의 값은 기본값으로
        for extra, max_calls, reserve, token in cases:
            built.clear()
            with mock.patch.object(oi, "GitHubClient", side_effect=construct):
                with self.assertRaises(Stop):
                    oi.run(dict({"GITHUB_REPOSITORY": h.REPO}, **extra), None, NOW, root, self.out.append)
            args, kwargs = built[0]
            self.assertEqual((args, kwargs["max_calls"], kwargs["reserve"]), ((h.REPO, token), max_calls, reserve), extra)

    def test_the_smallest_allowed_call_cap_still_leaves_room_for_the_worst_case_writes(self):
        names = tuple(f"w{n}.yml" for n in range(14))
        fake, root = self.world(workflows=names)
        fake.runs = {name: [] for name in names}
        fake.reject_assignees = True                           # 담당자 거부 → 이슈를 두 번 만든다(쓰기 최악)
        fake.max_calls, fake.reserve = oi.MIN_API_CALLS, oi.WRITE_RESERVE
        self.assertEqual(self.run_script(fake, root), 0)       # 읽기가 상한에 걸려도 이슈 쓰기는 끝까지 한다
        self.assertLessEqual(fake.calls, oi.MIN_API_CALLS)
        issue = self.inbox_issue(fake)
        self.assertEqual(len(fake.comments[issue["number"]]), 1)
        self.assertEqual(inbox.parse_marker(issue["body"]).items, ("pr:15:ready", "watchdog:9"))      # 알린 id 를 적는 마지막 쓰기까지 됐다
        self.assertIn("조회 실패 — 워크플로 실행 기록", issue["body"])

    def test_main_with_the_real_client_and_no_network_degrades_instead_of_crashing(self):
        env = {"GITHUB_REPOSITORY": h.REPO}
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("offline")) as opened, \
                mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
            code = oi.main()
        self.assertEqual(code, 0)
        printed = stdout.getvalue()
        self.assertIn("토큰이 없어 읽기 전용", printed)
        self.assertIn("조회 실패", printed)
        self.assertGreaterEqual(opened.call_count, 4)
        for call in opened.call_args_list:
            self.assertEqual(call.args[0].get_method(), "GET")
            self.assertFalse(call.args[0].has_header("Authorization"))
        self.assertLessEqual(opened.call_count, 25)

    def test_the_anonymous_call_cap_is_respected_against_a_chatty_fake_world(self):
        fake, root = self.world()
        fake.max_calls = 25
        env = {"GITHUB_REPOSITORY": h.REPO}
        self.assertEqual(oi.run(env, fake, NOW, root, self.out.append), 0)
        self.assertLessEqual(fake.calls, 25)


# ----------------------------------------------------------------------------
# 워크플로 파일과 다른 워크플로·스크립트와의 상호작용
# ----------------------------------------------------------------------------
def one_item(items):
    assert len(items) == 1, [i.id for i in items]
    return items[0]


def load_workflow(name):
    data = yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))
    if True in data and "on" not in data:               # YAML 1.1 은 키 on 을 True 로 읽는다
        data["on"] = data.pop(True)
    return data


class WorkflowFileTest(unittest.TestCase):
    def setUp(self):
        self.wf = load_workflow("ops-inbox.yml")
        self.step = [s for s in self.wf["jobs"]["inbox"]["steps"] if "run" in s][0]

    def test_names_are_korean_and_tell_what_it_does(self):
        hangul = r"[가-힣]"
        self.assertEqual(self.wf["name"], "확인 필요 모음")
        self.assertRegex(self.wf["run-name"], hangul)
        self.assertRegex(self.wf["jobs"]["inbox"]["name"], hangul)
        for step in self.wf["jobs"]["inbox"]["steps"]:
            if "name" in step:
                self.assertRegex(step["name"], hangul)
        self.assertRegex(self.wf["on"]["workflow_dispatch"]["inputs"]["dry_run"]["description"], hangul)

    def test_run_name_only_uses_the_event_kind_and_the_dry_run_flag(self):
        for body in re.findall(r"\$\{\{(.*?)\}\}", self.wf["run-name"]):
            code = re.sub(r"'(?:[^']|'')*'", "''", body)
            refs = set(re.findall(r"[A-Za-z_][A-Za-z0-9_\-]*(?:\.[A-Za-z0-9_\-]+)+", code))
            self.assertLessEqual(refs, {"github.event_name", "inputs.dry_run"})

    def test_triggers_are_a_two_hourly_schedule_and_manual_dispatch_only(self):
        self.assertEqual(set(self.wf["on"]), {"schedule", "workflow_dispatch"})
        self.assertNotIn("workflow_run", self.wf["on"])                 # 다른 워크플로 이름에 기대지 않는다
        self.assertEqual([entry["cron"] for entry in self.wf["on"]["schedule"]], ["40 */2 * * *"])
        fields = self.wf["on"]["schedule"][0]["cron"].split()
        self.assertEqual(len(fields), 5)
        dry = self.wf["on"]["workflow_dispatch"]["inputs"]["dry_run"]
        self.assertEqual((dry["type"], dry["default"]), ("boolean", False))

    def test_permissions_are_minimal(self):
        self.assertEqual(self.wf["permissions"], {"contents": "read", "actions": "read", "checks": "read",
                                                   "pull-requests": "read", "issues": "write"})
        self.assertNotIn("permissions", self.wf["jobs"]["inbox"])        # job 에서 권한을 늘리지 않는다

    def test_one_run_at_a_time_and_never_cancelled(self):
        self.assertEqual(self.wf["concurrency"], {"group": "ops-inbox", "cancel-in-progress": False})
        self.assertLessEqual(self.wf["jobs"]["inbox"]["timeout-minutes"], 15)

    def test_read_time_limit_and_write_reserve_fit_inside_the_job_timeout(self):
        """읽기 시간 상한 + 쓰기 단계 최악(호출 7회 × 호출당 20초에서 끊김)이 잡 제한 안에 끝나야 하고, 쓰기용으로 남긴 호출이 최악 호출 수 이상이어야 한다."""
        worst_write_calls = 7           # 이슈 찾기 2 + 라벨 1 + 이슈 만들기 2(담당자 거부 때 한 번 더) + 코멘트 1 + 본문 고치기 1
        timeout_seconds = self.wf["jobs"]["inbox"]["timeout-minutes"] * 60
        self.assertLess(oi.MAX_READ_SECONDS + worst_write_calls * 20, timeout_seconds)
        self.assertGreaterEqual(oi.WRITE_RESERVE, worst_write_calls)

    def test_checkout_does_not_keep_credentials_and_python_is_3_12(self):
        steps = self.wf["jobs"]["inbox"]["steps"]
        checkout = [s for s in steps if str(s.get("uses", "")).startswith("actions/checkout@")][0]
        self.assertIs(checkout["with"]["persist-credentials"], False)
        python = [s for s in steps if str(s.get("uses", "")).startswith("actions/setup-python@")][0]
        self.assertEqual(python["with"]["python-version"], "3.12")

    def test_environment_passes_the_pause_variable_dry_run_flag_branch_and_the_workflow_token(self):
        env = self.step["env"]
        self.assertEqual(env["PIPELINE_PAUSE"], "${{ vars.PIPELINE_PAUSE }}")
        self.assertEqual(env["GITHUB_TOKEN"], "${{ secrets.GITHUB_TOKEN }}")
        self.assertIn("inputs.dry_run", env["INBOX_DRY_RUN"])
        self.assertIn("workflow_dispatch", env["INBOX_DRY_RUN"])
        self.assertEqual(env["DEFAULT_BRANCH"], "${{ github.event.repository.default_branch }}")
        source = (_bootstrap.ROOT / "scripts" / "ops_inbox.py").read_text(encoding="utf-8")
        for name in env:                                                  # 따옴표 모양(큰·작은)과 무관하게 스크립트가 그 이름을 읽는지
            self.assertRegex(source, "[\"']" + name + "[\"']", f"스크립트가 읽지 않는 환경변수 {name}")

    def test_only_the_workflow_token_is_used_and_nothing_is_interpolated_into_the_shell(self):
        text = (WORKFLOWS / "ops-inbox.yml").read_text(encoding="utf-8")
        self.assertEqual(self.step["run"].strip(), "python scripts/ops_inbox.py")
        self.assertNotIn("${{", self.step["run"])
        self.assertEqual(text.count("secrets."), text.count("secrets.GITHUB_TOKEN"))
        for forbidden in ("|| true", "continue-on-error", "pull_request_target", "write-all", "git push", "gh "):
            self.assertNotIn(forbidden, text, forbidden)

    def test_the_inbox_script_has_no_dependencies_to_install(self):
        text = (WORKFLOWS / "ops-inbox.yml").read_text(encoding="utf-8")
        self.assertNotIn("pip install", text)
        # 스크립트와, 스크립트가 (직접·간접으로) 가져오는 저장소 모듈은 표준 라이브러리만 최상위에서 가져온다(함수 안의 지연 import 는 부를 때만 필요)
        for rel in ("scripts/ops_inbox.py", "pipeline/inbox.py", "pipeline/console.py", "pipeline/llm.py", "pipeline/registry.py",
                    "pipeline/state.py", "pipeline/secret_patterns.py"):
            tree = ast.parse((_bootstrap.ROOT / rel).read_text(encoding="utf-8"))
            imported = set()
            for node in tree.body:
                if isinstance(node, ast.Import):
                    imported |= {alias.name.split(".")[0] for alias in node.names}
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    imported.add(node.module.split(".")[0])
            self.assertLessEqual(imported - {"pipeline"}, set(sys.stdlib_module_names), rel)


class AnnotationSourceTest(unittest.TestCase):
    """R9 를 소스에서 고정한다: 줄 머리가 '::' 인 문자열(워크플로 명령)은 고정 문장이어야 한다 — 값을 끼운 f-string 이면 안 된다."""

    def test_workflow_command_strings_in_the_script_are_fixed_sentences(self):
        tree = ast.parse((_bootstrap.ROOT / "scripts" / "ops_inbox.py").read_text(encoding="utf-8"))
        commands = []
        for node in ast.walk(tree):
            if isinstance(node, ast.JoinedStr):
                first = node.values[0] if node.values else None
                if isinstance(first, ast.Constant) and str(first.value).lstrip().startswith("::"):
                    self.fail(f"{node.lineno}번째 줄: 값을 끼운 f-string 이 워크플로 명령으로 시작합니다")
            elif isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.lstrip().startswith("::"):
                commands.append(node.value)
        self.assertEqual(sorted(commands), sorted([oi.ERROR_COMMENT_FAILED, oi.ERROR_ISSUE_FAILED]))
        for text in commands:
            self.assertTrue(text.startswith("::error::"), text)
            self.assertNotIn("\n", text)


class GuideMatchesCodeTest(unittest.TestCase):
    """docs/OPS_INBOX.md 가 말하는 값·동작이 코드와 같은지(값을 바꾸면 문서도 고친다)."""

    def setUp(self):
        self.doc = (_bootstrap.ROOT / "docs" / "OPS_INBOX.md").read_text(encoding="utf-8")

    def test_the_wait_before_asking_again_matches_the_guide(self):
        self.assertIn(f"{oi.PULL_RETRY_WAIT_SECONDS}초 뒤", self.doc)

    def test_call_cap_and_reserve(self):
        self.assertIn(f"{oi.MIN_API_CALLS}~{oi.MAX_API_CALLS}", self.doc)
        self.assertIn(f"한 번에 최대 {oi.MAX_CALLS_WITH_TOKEN}회", self.doc)
        self.assertIn(f"쓰기용 {oi.WRITE_RESERVE}회", self.doc)

    def test_the_no_token_wording_is_exact(self):
        self.assertIn("열린 이슈 목록(워치독 알림용)은 읽지만 모음 이슈는 읽지도 쓰지도 않", self.doc)
        self.assertNotIn("이슈는 건드리지 않음", self.doc)

    def test_the_rules_changed_by_this_fix_are_in_the_table(self):
        for phrase in ("워크플로 파일의 최상위 `name`", "포크", "action_required", "변경 범위 검사", "3초 뒤"):
            self.assertIn(phrase, self.doc, phrase)


class InteractionWithOtherAutomationTest(unittest.TestCase):
    """이 이슈(작성자 github-actions 봇, 라벨 ops-inbox, 제목 '[운영] 확인 필요 모음')를 다른 자동화가 처리 대상으로 오인하지 않는지."""

    def test_issue_edit_workflow_does_not_react_to_the_inbox_issue(self):
        data = load_workflow("issue-edit.yml")
        condition = data["jobs"]["edit"]["if"]
        prefixes = re.findall(r"startsWith\(github\.event\.issue\.title, '([^']*)'\)", condition)
        self.assertTrue(prefixes)
        for prefix in prefixes:
            self.assertFalse(inbox.ISSUE_TITLE.startswith(prefix), prefix)
        labels = re.findall(r"contains\(github\.event\.issue\.labels\.\*\.name, '([^']*)'\)", condition)
        self.assertEqual(labels, ["blog-control"])
        self.assertNotIn(inbox.LABEL, labels)
        self.assertIn("author_association", condition)                    # 봇(작성자 권한 CONTRIBUTOR)은 이 조건도 통과하지 못한다
        self.assertIn('"OWNER","MEMBER","COLLABORATOR"', condition)
        self.assertNotIn(inbox.BOT_LOGIN, condition)

    def test_watchdog_does_not_adopt_or_close_the_inbox_issue(self):
        import watchdog
        self.assertFalse(inbox.ISSUE_TITLE.startswith(watchdog.TITLE_PREFIX))
        self.assertNotEqual(inbox.LABEL, watchdog.LABEL)
        self.assertNotEqual(inbox.WATCHDOG_PREFIX, "")
        self.assertEqual(inbox.WATCHDOG_PREFIX, watchdog.TITLE_PREFIX)    # 워치독 접두가 바뀌면 이 모음의 워치독 규칙도 함께 고쳐야 한다

    def test_watchdog_issue_bodies_are_read_back_with_the_right_level_and_message(self):
        """워치독↔모음 계약: 손으로 쓴 본문이 아니라 실제 scripts/watchdog.py 의 issue_body() 가 만든 본문을 모음이 읽는다(심각/경고 각각)."""
        import watchdog
        from pipeline.health import Finding
        for severity, level, word in (("critical", "action", "심각"), ("warning", "check", "경고")):
            for owner, notified in (("octo", "2026-10-25T06:00:00+00:00"), (None, None), ("octo", None)):
                finding = Finding("blogger_macat", "UNPUBLISHED", severity, "초안만 생성됨 — 게시 시크릿을 확인하세요.")
                issue = h.make_issue(9, finding.title, watchdog.issue_body(finding, owner, notified), labels=(watchdog.LABEL,))
                item = one_item(inbox.watchdog_items([issue], URL))
                self.assertEqual((item.id, item.level), ("watchdog:9", level), (severity, owner, notified))
                self.assertTrue(item.detail.startswith(word), item.detail)
                self.assertIn("초안만 생성됨", item.detail)
                self.assertIn("blogger_macat: UNPUBLISHED", item.title)
                self.assertEqual(item.url, f"{URL}/issues/9")

    def test_a_hostile_watchdog_message_cannot_change_the_severity_or_forge_a_marker_or_mention(self):
        import watchdog
        from pipeline.health import Finding
        message = "심각도: warning 으로 위장 @everyone <!-- ops-inbox:hash=0123456789abcdef;items=pr:99:ready -->\n\n둘째 문단"
        issue = h.make_issue(9, "[Watchdog] chance: STALE", watchdog.issue_body(Finding("chance", "STALE", "critical", message), "octo", None),
                             labels=(watchdog.LABEL,))
        item = one_item(inbox.watchdog_items([issue], URL))
        self.assertEqual(item.level, "action")                                       # 진짜 심각도 줄이 먼저 나온다
        for raw in ("@", "<"):
            self.assertNotIn(raw, item.detail)
        self.assertIsNone(inbox.parse_marker(inbox.render([item], URL)))

    def test_every_severity_the_watchdog_can_emit_is_one_the_inbox_understands(self):
        source = (_bootstrap.ROOT / "pipeline" / "health.py").read_text(encoding="utf-8")
        pairs = set(re.findall(r'Finding\(\s*[A-Za-z_]+,\s*"([A-Z_]+)",\s*"([a-z]+)"', source))
        self.assertGreaterEqual(len(pairs), 9)
        self.assertEqual({severity for _code, severity in pairs}, {"critical", "warning"})      # 새 심각도 단어가 생기면 모음의 규칙도 함께 고친다

    def test_the_inbox_never_treats_its_own_issue_as_a_watchdog_alert(self):
        own = h.make_issue(5, inbox.ISSUE_TITLE, "**심각도**: critical", labels=(inbox.LABEL,))
        self.assertEqual(inbox.watchdog_items([own], URL), [])

    def test_other_workflows_do_not_use_the_inbox_label_or_title(self):
        for path in WORKFLOWS.glob("*.yml"):
            if path.name == "ops-inbox.yml":
                continue
            text = path.read_text(encoding="utf-8")
            self.assertNotIn(inbox.LABEL, text, path.name)
            self.assertNotIn(inbox.ISSUE_TITLE, text, path.name)


if __name__ == "__main__":
    unittest.main()
