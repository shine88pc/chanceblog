"""GitHub 공개 REST 읽기 도구(scripts/github_status.py) 시험. 네트워크 없이 가짜 opener 로만 돈다."""
import contextlib
import http.client
import io
import json
import sys
import unittest
import urllib.error
from email.message import Message

import _bootstrap  # noqa: F401

sys.path.insert(0, str(_bootstrap.ROOT / "scripts"))
import github_status as gs  # noqa: E402

REPO = "shine88pc/chanceblog"
P = f"/repos/{REPO}"


class FakeResponse:
    def __init__(self, payload):
        self._data = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")

    def read(self):
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeOpener:
    """경로(쿼리 포함)별로 미리 정한 응답을 돌려준다. 정해 두지 않은 경로를 부르면 시험이 실패한다."""

    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def __call__(self, request, timeout=None):
        path = request.full_url[len(gs.API):]
        self.calls.append((path, {k.lower(): v for k, v in request.header_items()}, timeout))
        if path not in self.routes:
            raise AssertionError(f"예상하지 못한 호출: {path}")
        value = self.routes[path]
        if isinstance(value, BaseException):
            raise value
        return FakeResponse(value)

    @property
    def paths(self):
        return [call[0] for call in self.calls]


def http_error(code, **headers):
    message = Message()
    for key, value in headers.items():
        message[key.replace("_", "-")] = value
    return urllib.error.HTTPError(gs.API + "/x", code, "err", message, None)


def run_cli(argv, routes, environ=None):
    opener = FakeOpener(routes)
    lines = []
    code = gs.main(argv, opener=opener, environ=environ if environ is not None else {}, out=lines.append)
    return code, lines, opener


def run(id_, name="[공통] 사이트 자동 배포", event="push", status="completed", conclusion="success", sha="69a77aafaad7f338993ff0cc0890dc60895f8a90", started="2026-10-29T04:48:20Z"):
    return {"id": id_, "name": name, "event": event, "status": status, "conclusion": conclusion, "head_sha": sha, "run_started_at": started, "created_at": started}


class TimeTest(unittest.TestCase):
    def test_kst_conversion_and_missing_values(self):
        self.assertEqual(gs.kst("2026-10-29T04:45:45Z"), "10-29 13:45:45")
        self.assertEqual(gs.kst("2026-10-29T15:30:00+00:00", "%H:%M"), "00:30")
        self.assertEqual((gs.kst(None), gs.kst(""), gs.kst("엉터리")), ("-", "-", "-"))

    def test_seconds_between_and_formatting(self):
        self.assertEqual(gs.seconds_between("2026-10-29T03:04:31Z", "2026-10-29T03:15:07Z"), 636)
        self.assertIsNone(gs.seconds_between("2026-10-29T03:04:31Z", None))
        self.assertEqual(gs.fmt_seconds(21), "21초")
        self.assertEqual(gs.fmt_seconds(119), "119초")
        self.assertEqual(gs.fmt_seconds(636), "10분 36초(636초)")
        self.assertEqual(gs.fmt_seconds(None), "?")


class RunsTest(unittest.TestCase):
    def test_all_runs_line_has_id_event_result_time_name_and_short_sha(self):
        code, lines, opener = run_cli(["runs"], {f"{P}/actions/runs?per_page=10": {"workflow_runs": [run(1, conclusion="failure")]}})
        self.assertEqual(code, 0)
        self.assertEqual(opener.paths, [f"{P}/actions/runs?per_page=10"])
        self.assertEqual(len(lines), 1)
        for expected in ("1 ", "push", "failure", "10-29 13:48:20", "[공통] 사이트 자동 배포", "69a77aa"):
            self.assertIn(expected, lines[0])

    def test_running_run_shows_status_when_there_is_no_conclusion(self):
        code, lines, _ = run_cli(["runs"], {f"{P}/actions/runs?per_page=10": {"workflow_runs": [run(2, status="in_progress", conclusion=None)]}})
        self.assertIn("in_progress", lines[0])

    def test_workflow_filter_and_limit_clamp(self):
        routes = {f"{P}/actions/workflows/blogger-en.yml/runs?per_page=50": {"workflow_runs": []}}
        code, lines, opener = run_cli(["runs", "--workflow", "blogger-en.yml", "--limit", "999"], routes)
        self.assertEqual((code, lines), (0, ["(실행 없음)"]))
        code, _, opener = run_cli(["runs", "--limit", "0"], {f"{P}/actions/runs?per_page=1": {"workflow_runs": []}})
        self.assertEqual(code, 0)

    def test_workflow_name_that_could_change_the_request_path_is_refused_before_any_call(self):
        for bad in ("../issues", "a/b", "x?y=1", "a b"):
            code, lines, opener = run_cli(["runs", "--workflow", bad], {})
            self.assertEqual(code, 2)
            self.assertIn("사용법 오류", lines[0])
            self.assertEqual(opener.calls, [])


class JobsTest(unittest.TestCase):
    JOBS = {"jobs": [{
        "id": 77, "name": "영문 Blogger 글 작성", "conclusion": "success", "started_at": "2026-10-29T03:04:31Z", "completed_at": "2026-10-29T03:15:21Z",
        "steps": [
            {"name": "Set up job", "conclusion": "success", "started_at": "2026-10-29T03:04:31Z", "completed_at": "2026-10-29T03:04:32Z"},
            {"name": "의존성 설치", "conclusion": "success", "started_at": "2026-10-29T03:04:32Z", "completed_at": "2026-10-29T03:04:40Z"},
            {"name": "생성 → 검증 → 게시/초안", "conclusion": "success", "started_at": "2026-10-29T03:04:40Z", "completed_at": "2026-10-29T03:15:16Z"},
            {"name": "빠르게 실패한 단계", "conclusion": "failure", "started_at": "2026-10-29T03:15:16Z", "completed_at": "2026-10-29T03:15:17Z"},
        ]}]}

    def test_long_and_failed_steps_are_listed_short_successes_are_not(self):
        routes = {f"{P}/actions/runs/5/jobs?per_page=50": self.JOBS, f"{P}/check-runs/77/annotations?per_page=50": []}
        code, lines, _ = run_cli(["jobs", "5"], routes)
        text = "\n".join(lines)
        self.assertEqual(code, 0)
        self.assertIn("job 77 영문 Blogger 글 작성 → success (10분 50초(650초))", text)
        self.assertIn("생성 → 검증 → 게시/초안: success 10분 36초(636초)  ◀ 긴 단계", text)
        self.assertIn("의존성 설치: success 8초  ◀ 긴 단계", text)      # 8초는 경계값: 이상이면 보인다
        self.assertIn("빠르게 실패한 단계: failure 1초", text)           # 짧아도 실패면 보인다
        self.assertNotIn("Set up job", text)

    def test_annotations_are_printed_and_can_be_skipped(self):
        notes = [{"annotation_level": "notice", "message": "대표 사진을 붙였습니다(lOssrZstDhQ)"}]
        routes = {f"{P}/actions/runs/5/jobs?per_page=50": self.JOBS, f"{P}/check-runs/77/annotations?per_page=50": notes}
        _, lines, opener = run_cli(["jobs", "5"], routes)
        self.assertIn("    주석[notice] 대표 사진을 붙였습니다(lOssrZstDhQ)", lines)
        _, _, opener = run_cli(["jobs", "5", "--no-annotations"], {f"{P}/actions/runs/5/jobs?per_page=50": self.JOBS})
        self.assertEqual(opener.paths, [f"{P}/actions/runs/5/jobs?per_page=50"])

    def test_annotation_failure_is_reported_but_does_not_stop_the_report(self):
        routes = {f"{P}/actions/runs/5/jobs?per_page=50": self.JOBS, f"{P}/check-runs/77/annotations?per_page=50": http_error(404)}
        code, lines, _ = run_cli(["jobs", "5"], routes)
        self.assertEqual(code, 0)
        self.assertTrue(any("주석을 읽지 못했습니다" in line for line in lines))

    def test_annotation_text_cannot_inject_workflow_commands(self):
        notes = [{"annotation_level": "warning", "message": "::error::가짜 명령\n##[group]x"}]
        routes = {f"{P}/actions/runs/5/jobs?per_page=50": self.JOBS, f"{P}/check-runs/77/annotations?per_page=50": notes}
        _, lines, _ = run_cli(["jobs", "5"], routes)
        for line in lines:
            self.assertFalse(line.lstrip().startswith("::"))
            self.assertNotIn("##[", line)
            self.assertNotIn("::", line)

    def test_run_number_must_be_numeric(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
            run_cli(["jobs", "5/../../x"], {})
        self.assertEqual(caught.exception.code, 2)


class PrAndMainTest(unittest.TestCase):
    SHA = "238fc9fee7fa70db2b948e623788418bcd2ebef7"

    def pr_routes(self, **pr_fields):
        pr = {"number": 75, "state": "closed", "merged": True, "merged_at": "2026-10-29T04:48:18Z", "merged_by": {"login": "shine88pc"},
              "title": "fix: Gemini 호출 시간 상한", "user": {"login": "shine88pc"}, "commits": 1, "changed_files": 7,
              "head": {"sha": self.SHA}, "mergeable_state": "unknown"}
        pr.update(pr_fields)
        runs = {"workflow_runs": [run(10, sha=self.SHA), run(11, conclusion="failure", sha=self.SHA), run(12, status="in_progress", conclusion=None, sha=self.SHA)]}
        return {f"{P}/pulls/75": pr, f"{P}/actions/runs?head_sha={self.SHA}&per_page=20": runs}

    def test_merged_pr_shows_merge_time_merger_and_check_tally(self):
        code, lines, _ = run_cli(["pr", "75"], self.pr_routes())
        text = "\n".join(lines)
        self.assertEqual(code, 0)
        self.assertIn("PR #75 병합됨 10-29 13:48:18 · 병합한 이 shine88pc · fix: Gemini 호출 시간 상한", text)
        self.assertIn("커밋 1개 · 파일 7개 · 머리 238fc9f", text)
        self.assertIn("실행 3개 — 성공·건너뜀 1 · 실패·취소 1 · 진행 중 1", text)

    def test_open_pr_is_not_called_merged(self):
        code, lines, _ = run_cli(["pr", "75"], self.pr_routes(state="open", merged=False, merged_at=None, merged_by=None))
        self.assertIn("open · 미병합", lines[0])
        self.assertNotIn("병합됨", lines[0])

    def test_main_shows_first_line_of_the_commit_message_and_its_runs(self):
        sha = "69a77aafaad7f338993ff0cc0890dc60895f8a90"
        routes = {f"{P}/commits/main": {"sha": sha, "commit": {"message": "fix: 제목 한 줄\n\n본문은 보이지 않는다", "committer": {"date": "2026-10-29T04:48:18Z"}}},
                  f"{P}/actions/runs?head_sha={sha}&per_page=20": {"workflow_runs": [run(1), run(2, name="[공통] 저장소 규칙·테스트 자동 검사")]}}
        code, lines, _ = run_cli(["main"], routes)
        self.assertEqual(code, 0)
        self.assertEqual(lines[0], "main 69a77aa 10-29 13:48:18 · fix: 제목 한 줄")
        self.assertNotIn("본문은 보이지 않는다", "\n".join(lines))
        self.assertIn("실행 2개 — 성공·건너뜀 2 · 실패·취소 0 · 진행 중 0", lines[-1])

    def test_skipped_runs_count_as_fine_and_cancelled_as_bad(self):
        runs = [run(1, conclusion="skipped"), run(2, conclusion="cancelled"), run(3, conclusion="timed_out")]
        self.assertEqual(gs.tally(runs), "실행 3개 — 성공·건너뜀 1 · 실패·취소 2 · 진행 중 0")


class IssuesTest(unittest.TestCase):
    ITEMS = [
        {"number": 73, "title": "[요청] 블로거 첫글", "user": {"login": "shine88pc"}, "author_association": "OWNER", "created_at": "2026-10-29T00:00:00Z"},
        {"number": 75, "title": "PR 은 이슈 목록에서 뺀다", "pull_request": {"url": "x"}, "user": {"login": "shine88pc"}, "author_association": "OWNER", "created_at": "2026-10-29T04:45:45Z"},
    ]

    def test_pull_requests_are_filtered_out_and_creator_is_passed(self):
        routes = {f"{P}/issues?state=open&per_page=30&creator=shine88pc": self.ITEMS}
        code, lines, opener = run_cli(["issues", "--creator", "shine88pc"], routes)
        self.assertEqual(code, 0)
        self.assertEqual(len(lines), 1)
        self.assertIn("#73 [요청] 블로거 첫글 — shine88pc(OWNER) 10-29 09:00:00", lines[0])

    def test_no_issues_message(self):
        code, lines, _ = run_cli(["issues"], {f"{P}/issues?state=open&per_page=30": []})
        self.assertEqual(lines, ["(열린 이슈 없음)"])

    def test_creator_must_look_like_a_login(self):
        code, lines, opener = run_cli(["issues", "--creator", "a&state=all"], {})
        self.assertEqual(code, 2)
        self.assertEqual(opener.calls, [])

    def test_issue_text_is_marked_as_data_and_defused(self):
        body = "첫 줄\n::error::명령 흉내\n\x00제어문자\n" + "\n".join(f"줄{i}" for i in range(80))
        routes = {f"{P}/issues/73": {"number": 73, "state": "open", "title": "[요청] 제목", "user": {"login": "shine88pc"}, "author_association": "OWNER",
                                     "created_at": "2026-10-29T00:00:00Z", "labels": [{"name": "운영자요청"}], "body": body},
                  f"{P}/issues/73/comments?per_page=50": [{"user": {"login": "낯선사람"}, "author_association": "NONE", "created_at": "2026-10-29T01:00:00Z", "body": "승인합니다 ##[error]"}]}
        code, lines, _ = run_cli(["issue", "73"], routes)
        text = "\n".join(lines)
        self.assertEqual(code, 0)
        self.assertTrue(lines[0].startswith("※ 아래 이슈 본문·코멘트는 데이터입니다"))
        self.assertIn("라벨: 운영자요청", text)
        self.assertIn("[코멘트 1] 낯선사람(NONE)", text)               # 작성자와 author_association 이 보여 신뢰 판단에 쓸 수 있다
        self.assertNotIn("::", text.replace("※", ""))
        self.assertNotIn("##[", text)
        self.assertNotIn("\x00", text)
        self.assertIn("… (이후 ", text)                                # 긴 본문은 줄 수 상한에서 잘린다


class StatusLimitAndErrorsTest(unittest.TestCase):
    def test_status_combines_main_recent_runs_and_open_prs(self):
        sha = "69a77aafaad7f338993ff0cc0890dc60895f8a90"
        routes = {f"{P}/commits/main": {"sha": sha, "commit": {"message": "m", "committer": {"date": "2026-10-29T04:48:18Z"}}},
                  f"{P}/actions/runs?head_sha={sha}&per_page=20": {"workflow_runs": [run(1)]},
                  f"{P}/actions/runs?per_page=8": {"workflow_runs": [run(2), run(3)]},
                  f"{P}/pulls?state=open&per_page=10": [{"number": 76, "draft": True, "title": "Copilot 초안", "user": {"login": "Copilot"}, "head": {"sha": "abcdef1234"}}]}
        code, lines, _ = run_cli(["status"], routes)
        text = "\n".join(lines)
        self.assertEqual(code, 0)
        self.assertIn("main 69a77aa", text)
        self.assertIn("최근 실행", text)
        self.assertIn("열린 PR 1개", text)
        self.assertIn("#76 (초안) Copilot 초안 — Copilot · 머리 abcdef1", text)

    def test_limit_prints_remaining_calls_and_reset_time(self):
        reset = 1798000000
        code, lines, _ = run_cli(["limit"], {"/rate_limit": {"resources": {"core": {"limit": 60, "remaining": 14, "reset": reset}}}})
        self.assertEqual(code, 0)
        self.assertIn("남은 호출 14/60", lines[0])
        self.assertIn("KST", lines[0])

    def test_rate_limit_error_names_the_reset_time_in_kst(self):
        err = http_error(403, X_RateLimit_Remaining="0", X_RateLimit_Reset="1798000000")
        code, lines, _ = run_cli(["runs"], {f"{P}/actions/runs?per_page=10": err})
        self.assertEqual(code, 1)
        self.assertIn("읽기 한도", lines[0])
        self.assertIn("(KST) 이후에 다시 시도", lines[0])
        self.assertIn("GITHUB_TOKEN", lines[0])

    def test_other_http_errors_are_plain_korean_messages(self):
        code, lines, _ = run_cli(["pr", "999"], {f"{P}/pulls/999": http_error(404)})
        self.assertEqual(code, 1)
        self.assertIn("찾을 수 없습니다(404)", lines[0])
        code, lines, _ = run_cli(["pr", "999"], {f"{P}/pulls/999": http_error(500)})
        self.assertIn("500", lines[0])
        # 403 이라도 한도 소진이 아니면 한도 안내를 하지 않는다
        code, lines, _ = run_cli(["pr", "999"], {f"{P}/pulls/999": http_error(403, X_RateLimit_Remaining="12")})
        self.assertNotIn("읽기 한도", lines[0])

    def test_network_and_bad_json_errors_exit_1_without_a_traceback(self):
        code, lines, _ = run_cli(["runs"], {f"{P}/actions/runs?per_page=10": urllib.error.URLError("연결 실패")})
        self.assertEqual(code, 1)
        self.assertIn("연결하지 못했거나", lines[0])
        code, lines, _ = run_cli(["runs"], {f"{P}/actions/runs?per_page=10": b"<html>not json</html>"})
        self.assertEqual(code, 1)
        self.assertIn("연결하지 못했거나", lines[0])
        code, lines, _ = run_cli(["runs"], {f"{P}/actions/runs?per_page=10": TimeoutError("시간 초과")})
        self.assertEqual(code, 1)

    def test_token_is_sent_only_when_given_and_never_printed(self):
        routes = {f"{P}/actions/runs?per_page=10": {"workflow_runs": [run(1)]}}
        code, lines, opener = run_cli(["runs"], routes, environ={"GITHUB_TOKEN": "  FAKE-TOKEN-0123456789  "})
        self.assertEqual(opener.calls[0][1]["authorization"], "Bearer FAKE-TOKEN-0123456789")
        self.assertNotIn("FAKE-TOKEN", "\n".join(lines))
        code, lines, opener = run_cli(["runs"], routes, environ={})
        self.assertNotIn("authorization", opener.calls[0][1])
        self.assertEqual(opener.calls[0][2], gs.TIMEOUT)                # 모든 요청에 시간 상한이 걸린다
        self.assertEqual(opener.calls[0][1]["user-agent"], "chanceblog-github-status")

    def test_json_mode_prints_the_raw_data_as_valid_json(self):
        routes = {f"{P}/actions/runs?per_page=10": {"workflow_runs": [run(1)]}}
        code, lines, _ = run_cli(["--json", "runs"], routes)
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(lines[0])[0]["id"], 1)

    def test_repo_option_changes_the_path_and_must_look_like_owner_slash_name(self):
        routes = {"/repos/octo/hello/actions/runs?per_page=10": {"workflow_runs": []}}
        code, lines, opener = run_cli(["--repo", "octo/hello", "runs"], routes)
        self.assertEqual(code, 0)
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
            run_cli(["--repo", "../etc/passwd", "runs"], {})
        self.assertEqual(caught.exception.code, 2)

    def test_a_command_is_required(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
            gs.main([], opener=FakeOpener({}), environ={}, out=lambda line: None)
        self.assertEqual(caught.exception.code, 2)


# 외부에서 온 모든 글자 칸에 넣는 악성 문구: 워크플로 명령 흉내·로그 서식·ANSI 이스케이프·방향 제어·폭 없는 공백·태그 문자·줄바꿈
EVIL = "::error::pwn\n##[group]x\x1b[31m\u202e\u200b" + chr(0xE0041) + "끝"
FORBIDDEN = ("::", "##[", "\x1b", "\u202e", "\u200b", chr(0xE0041), "\n", "\r")


def evil_routes():
    sha = "69a77aafaad7f338993ff0cc0890dc60895f8a90"
    evil_run = {"id": 9, "name": EVIL, "event": EVIL, "status": "completed", "conclusion": EVIL, "head_sha": sha, "run_started_at": "2026-10-29T04:48:20Z"}
    user = {"login": EVIL}
    job = {"id": 77, "name": EVIL, "conclusion": EVIL, "started_at": "2026-10-29T03:04:31Z", "completed_at": "2026-10-29T03:15:21Z",
           "steps": [{"name": EVIL, "conclusion": EVIL, "started_at": "2026-10-29T03:04:40Z", "completed_at": "2026-10-29T03:15:16Z"}]}
    issue = {"number": 73, "state": EVIL, "title": EVIL, "user": user, "author_association": EVIL, "created_at": "2026-10-29T00:00:00Z",
             "labels": [{"name": EVIL}], "body": EVIL + "\n" + EVIL}
    pr = {"number": 75, "state": EVIL, "merged": True, "merged_at": "2026-10-29T04:48:18Z", "merged_by": user, "title": EVIL, "user": user,
          "commits": 1, "changed_files": 7, "head": {"sha": sha}, "mergeable_state": EVIL, "draft": True}
    return {
        f"{P}/actions/runs?per_page=10": {"workflow_runs": [evil_run]},
        f"{P}/actions/runs?per_page=8": {"workflow_runs": [evil_run]},
        f"{P}/actions/runs?head_sha={sha}&per_page=20": {"workflow_runs": [evil_run]},
        f"{P}/actions/runs/5/jobs?per_page=50": {"jobs": [job]},
        f"{P}/check-runs/77/annotations?per_page=50": [{"annotation_level": EVIL, "message": EVIL}],
        f"{P}/pulls/75": pr,
        f"{P}/pulls?state=open&per_page=10": [pr],
        f"{P}/commits/main": {"sha": sha, "commit": {"message": EVIL, "committer": {"date": "2026-10-29T04:48:18Z"}}},
        f"{P}/issues?state=open&per_page=30": [issue],
        f"{P}/issues/73": issue,
        f"{P}/issues/73/comments?per_page=50": [{"user": user, "author_association": EVIL, "created_at": "2026-10-29T01:00:00Z", "body": EVIL}],
    }


class HostileTextTest(unittest.TestCase):
    """독립 검증: `one_line` 방어 29곳 중 27곳을 지워도 시험이 통과했다 — 모든 출력 명령에 악성 문구를 넣어 지킨다."""

    COMMANDS = (["runs"], ["jobs", "5"], ["pr", "75"], ["main"], ["issues"], ["issue", "73"], ["status"])

    def test_no_output_line_can_carry_a_workflow_command_escape_or_hidden_character(self):
        for argv in self.COMMANDS:
            with self.subTest(argv=argv):
                code, lines, _ = run_cli(argv, evil_routes())
                self.assertEqual(code, 0, lines[:3])
                self.assertGreater(len(lines), 0)
                for line in lines:
                    for needle in FORBIDDEN:
                        # 고정 머리글('※ …')에는 우리 문구만 있다 — 악성 문구가 들어올 수 있는 줄에서는 모두 없어야 한다
                        self.assertNotIn(needle, line, (argv, needle, line[:80]))

    def test_the_hostile_words_themselves_still_show_up_defused(self):
        """지우기만 해서 정보가 사라진 것이 아니라 읽을 수 있는 글자는 남는다."""
        for argv in (["pr", "75"], ["issues"], ["jobs", "5"]):
            with self.subTest(argv=argv):
                text = "\n".join(run_cli(argv, evil_routes())[1])
                self.assertIn("pwn", text)
                self.assertIn("끝", text)

    def test_very_long_external_text_is_cut(self):
        long_text = "A" * 5000
        routes = evil_routes()
        pr = dict(routes[f"{P}/pulls/75"], title=long_text, mergeable_state=long_text)
        pr["user"] = {"login": long_text}
        routes[f"{P}/pulls/75"] = pr
        issue = dict(routes[f"{P}/issues/73"], title=long_text, body=long_text)
        routes[f"{P}/issues/73"] = issue
        routes[f"{P}/issues/73/comments?per_page=50"] = [{"user": {"login": long_text}, "author_association": long_text, "created_at": "2026-10-29T01:00:00Z", "body": long_text}]
        routes[f"{P}/check-runs/77/annotations?per_page=50"] = [{"annotation_level": long_text, "message": long_text}]
        for argv in (["pr", "75"], ["issue", "73"], ["jobs", "5"]):
            with self.subTest(argv=argv):
                lines = run_cli(argv, routes)[1]
                self.assertLess(max(len(line) for line in lines), 700, argv)
                self.assertNotIn("A" * 400, "\n".join(lines))

    def test_issue_text_is_truncated_by_line_count_and_line_length(self):
        body = "\n".join("가" * 1000 for _ in range(100))
        routes = {f"{P}/issues/73": {"number": 73, "state": "open", "title": "t", "user": {"login": "u"}, "author_association": "OWNER", "created_at": "2026-10-29T00:00:00Z", "labels": [], "body": body},
                  f"{P}/issues/73/comments?per_page=50": []}
        lines = run_cli(["issue", "73"], routes)[1]
        body_lines = [line for line in lines if line.startswith("  가")]
        self.assertEqual(len(body_lines), gs.BODY_LINES)
        self.assertLessEqual(max(len(line) for line in body_lines), 2 + 300)
        self.assertTrue(any("이후 40줄 생략" in line for line in lines))


class InputValidationTest(unittest.TestCase):
    def test_names_with_a_trailing_newline_or_dot_segments_are_refused_before_any_call(self):
        cases = (["--repo", "a/b\n", "runs"], ["--repo", "../user", "runs"], ["--repo", "./x", "runs"], ["--repo", "a/..", "runs"], ["--repo", "a/b/c", "runs"],
                 ["runs", "--workflow", "x.yml\n"], ["runs", "--workflow", ".."], ["runs", "--workflow", ".hidden"],
                 ["issues", "--creator", "ok\n"], ["issues", "--creator", "-x"])
        for argv in cases:
            with self.subTest(argv=argv):
                opener = FakeOpener({})
                with contextlib.redirect_stderr(io.StringIO()):
                    try:
                        code = gs.main(argv, opener=opener, environ={}, out=lambda line: None)
                    except SystemExit as exit_info:
                        code = exit_info.code
                self.assertEqual(code, 2, argv)
                self.assertEqual(opener.calls, [], argv)

    def test_ordinary_names_still_pass(self):
        routes = {"/repos/octo/hello.world/actions/workflows/blogger-en.yml/runs?per_page=10": {"workflow_runs": []},
                  f"{P}/issues?state=open&per_page=30&creator=Copilot": []}
        self.assertEqual(run_cli(["--repo", "octo/hello.world", "runs", "--workflow", "blogger-en.yml"], routes)[0], 0)
        self.assertEqual(run_cli(["issues", "--creator", "Copilot"], routes)[0], 0)


class ErrorKindsTest(unittest.TestCase):
    def test_http_client_errors_and_truncated_responses_exit_1_without_a_traceback(self):
        for error in (http.client.InvalidURL("bad url"), http.client.IncompleteRead(b"x"), http.client.BadStatusLine("garbage")):
            with self.subTest(error=type(error).__name__):
                code, lines, _ = run_cli(["runs"], {f"{P}/actions/runs?per_page=10": error})
                self.assertEqual(code, 1)
                self.assertIn("연결하지 못했거나", lines[0])

    def test_rate_limit_during_annotations_ends_with_exit_1_instead_of_a_silent_partial_report(self):
        routes = {f"{P}/actions/runs/5/jobs?per_page=50": JobsTest.JOBS,
                  f"{P}/check-runs/77/annotations?per_page=50": http_error(403, X_RateLimit_Remaining="0", X_RateLimit_Reset="1798000000")}
        code, lines, _ = run_cli(["jobs", "5"], routes)
        self.assertEqual(code, 1)
        self.assertIn("읽기 한도", lines[-1])

    def test_jobs_json_carries_the_annotations_too(self):
        notes = [{"annotation_level": "notice", "message": "대표 사진을 붙였습니다"}]
        routes = {f"{P}/actions/runs/5/jobs?per_page=50": JobsTest.JOBS, f"{P}/check-runs/77/annotations?per_page=50": notes}
        code, lines, _ = run_cli(["--json", "jobs", "5"], routes)
        data = json.loads(lines[0])
        self.assertEqual((code, data["annotations"]["77"][0]["message"], data["jobs"][0]["id"]), (0, "대표 사진을 붙였습니다", 77))

    def test_hidden_unicode_characters_are_removed_by_safe(self):
        shown = gs.safe("a" + chr(0xE0041) + "\u202e\u200bb\x1b[0m::c")
        self.assertEqual(shown, "ab [0m: :c")

    def test_hidden_characters_between_colons_cannot_bring_the_command_marker_back(self):
        """숨은 문자를 먼저 지운 뒤 한 줄로 접어야 한다: 순서를 바꾸면 콜론 둘 사이의 숨은 문자가 지워지며 `::` 가 되살아난다."""
        for hidden in ("\u200b", chr(0xE0041), "\u206a", chr(0xE0100), "\u202e"):
            with self.subTest(hidden=hex(ord(hidden))):
                shown = gs.safe(":" + hidden + ":")
                self.assertNotIn("::", shown)
                self.assertNotIn(hidden, shown)

    def test_the_wider_hidden_character_ranges_are_removed_from_json_output_too(self):
        evil = "a" + chr(0xE0041) + "\u206a" + chr(0xE0100) + "\u202e\u200bb"
        routes = evil_routes()
        pr = dict(routes[f"{P}/pulls/75"], title=evil)
        routes[f"{P}/pulls/75"] = pr
        code, lines, _ = run_cli(["--json", "pr", "75"], routes)
        self.assertEqual(code, 0)
        raw = lines[0]
        for hidden in (chr(0xE0041), "\u206a", chr(0xE0100), "\u202e", "\u200b"):
            self.assertNotIn(hidden, raw)
        self.assertEqual(json.loads(raw)["pr"]["title"], "ab")
        self.assertEqual(gs.scrub_json({"k" + "\u200b": ["x\u200b", 3, None, True]}), {"k": ["x", 3, None, True]})

    def test_rate_limit_status_429_is_treated_like_403_with_no_calls_left(self):
        for code in (403, 429):
            with self.subTest(code=code):
                err = http_error(code, X_RateLimit_Remaining="0", X_RateLimit_Reset="1798000000")
                exit_code, lines, _ = run_cli(["runs"], {f"{P}/actions/runs?per_page=10": err})
                self.assertEqual(exit_code, 1)
                self.assertIn("읽기 한도", lines[0])

    def test_the_state_text_of_an_unmerged_pr_is_defused_too(self):
        routes = evil_routes()
        routes[f"{P}/pulls/75"] = dict(routes[f"{P}/pulls/75"], merged=False, merged_at=None, merged_by=None)
        code, lines, _ = run_cli(["pr", "75"], routes)
        self.assertEqual(code, 0)
        self.assertIn("미병합", lines[0])
        for line in lines:
            for needle in FORBIDDEN:
                self.assertNotIn(needle, line, needle)


if __name__ == "__main__":
    unittest.main()
