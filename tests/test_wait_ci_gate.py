"""AI 도구 사본의 검사 관문 시험 — `인수인계/도구/work/make_request.py` 의 `default_gate` 와 `인수인계/도구/work/scratch/wait_ci.py`.

배경(2026-11-07, 자동 PR 워크플로 `auto-pr.yml` 의 첫 실제 실행 관측): 봇(`GITHUB_TOKEN`)이 만든 PR 의 `pull_request` 워크플로 실행은 job 없이
'승인 대기(action_required)' 로 생긴다 — 블로그 PR #148 에서 `[공통] PR 변경 범위 검사` 가 만들어진 5초 뒤 그렇게 됐다. 병합 부탁 관문이 `action_required` 를
'초록이 아님'으로 세면 봇이 PR 을 만든 가지의 병합 부탁이 영영 만들어지지 않는다. 그래서 도구는 **알려진 하나**(위 이름의 승인 대기 — AI 가지 PR 에서는 그 검사의 job 이
조건으로 건너뛰어 승인해도 할 일이 없다)만 초록으로 센다. 다른 이름의 승인 대기·실패·취소·진행 중은 여전히 막아야 한다 — 이 시험이 그 경계를 못박는다.

네트워크·실제 GitHub·실제 git 은 없다(가짜 실행 목록·가짜 `git ls-remote`·가짜 웹 목록).
"""
import ast
import contextlib
import importlib.util
import inspect
import io
import re
import sys
import types
import unittest
from unittest import mock

import _bootstrap

ROOT = _bootstrap.ROOT
TOOLS = ROOT / "인수인계" / "도구"
WORK = TOOLS / "work"
WAIT_CI_PATH = WORK / "scratch" / "wait_ci.py"
sys.path.insert(0, str(WORK))
import make_request  # noqa: E402

KNOWN = "[공통] PR 변경 범위 검사"                                       # 봇 PR 에서 승인 대기로 남는 알려진 실행의 이름(워크플로 name)
OTHER = "[공통] 확인 필요 모음 갱신 · PR 변경(초안만 점검)"                 # 이 저장소의 다른 pull_request 워크플로
PUSH = "[공통] 저장소 규칙·테스트 자동 검사"
SHA = "a" * 40
BRANCH = "ai/claude/M012-docs-tools-1"
TARGET = f"shine88pc/chanceblog:{BRANCH}"


def load_wait_ci():
    """시험마다 새로 읽는다(다른 시험이 모듈 속 함수를 바꿔 놓아도 영향이 없게)."""
    spec = importlib.util.spec_from_file_location("wait_ci_under_test", WAIT_CI_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_run(name, status="completed", conclusion="success", ident=1, event="pull_request", timing="1m 2s"):
    """wait_ci.runs_for 가 돌려주는 실행 한 건의 모양."""
    return {"id": ident, "name": name, "event": event, "status": status, "conclusion": conclusion, "timing": timing}


# ==== run_ok — 무엇을 초록으로 세는가 ========================================================
class RunOkTest(unittest.TestCase):
    def setUp(self):
        self.wc = load_wait_ci()

    def test_success_skipped_and_neutral_count_as_green_whatever_the_name(self):
        for conclusion in ("success", "skipped", "neutral"):
            for name in (KNOWN, OTHER, PUSH, ""):
                self.assertTrue(self.wc.run_ok(make_run(name, conclusion=conclusion)), (conclusion, name))

    def test_the_known_pull_request_scope_check_waiting_for_approval_counts_as_green(self):
        self.assertTrue(self.wc.run_ok(make_run(KNOWN, conclusion="action_required")))

    def test_a_waiting_run_of_any_other_name_does_not_count_as_green(self):
        for name in (OTHER, PUSH, "[공통] 병합 부탁 PR 자동 만들기", "[Chance] 글 작성·게시 · 정기", "PR 변경 범위", ""):          # 이름 일부만 같은 것도 알려진 이름이 아니다
            self.assertFalse(self.wc.run_ok(make_run(name, conclusion="action_required")), name)

    def test_failures_and_cancellations_never_count_as_green_even_with_the_known_name(self):
        for conclusion in ("failure", "cancelled", "timed_out", "stale", "startup_failure", ""):          # 빈 값 = 아직 결론이 없음(진행 중)
            for name in (KNOWN, OTHER):
                self.assertFalse(self.wc.run_ok(make_run(name, conclusion=conclusion)), (conclusion, name))

    def test_a_waiting_run_without_a_name_never_counts_as_the_known_one(self):
        for run in ({"id": 1, "name": None, "status": "completed", "conclusion": "action_required"},
                    {"id": 1, "name": "", "status": "completed", "conclusion": "action_required"},
                    {"id": 1, "status": "completed", "conclusion": "action_required"}):                 # `name` 칸 자체가 없는 모양도 예외 없이 거짓
            self.assertFalse(self.wc.run_ok(run), run)

    def test_the_base_set_of_green_conclusions_did_not_grow(self):
        self.assertEqual(self.wc.OK_CONCLUSIONS, ("success", "skipped", "neutral"))
        self.assertEqual(self.wc.APPROVAL_PENDING_OK, (KNOWN,))                        # 예외는 알려진 하나뿐 — 늘리려면 이 시험도 이유와 함께 고친다

    def test_the_known_name_is_the_real_name_of_the_pull_request_scope_check_workflow(self):
        """워크플로 이름이 바뀌면 도구의 예외가 조용히 죽는다 — 그때 이 시험이 빨개져 도구 사본을 같이 고치게 한다."""
        text = (ROOT / ".github" / "workflows" / "pr-scope-check.yml").read_text(encoding="utf-8")
        found = re.search(r'^name:\s*"([^"]+)"', text, re.M)
        self.assertIsNotNone(found)
        self.assertEqual(self.wc.APPROVAL_PENDING_OK, (found.group(1),))

    def test_the_waiting_run_is_harmless_because_that_workflow_skips_ai_branch_pull_requests(self):
        """승인 대기를 '초록으로 센다'는 전제: AI 가지(`ai/claude/`)의 PR 에서는 그 검사의 job 이 조건으로 건너뛴다 — 이 조건이 사라지면 전제가 깨진다."""
        text = (ROOT / ".github" / "workflows" / "pr-scope-check.yml").read_text(encoding="utf-8")
        self.assertIn("!startsWith(github.head_ref, 'ai/claude/')", text)


# ==== 관문(make_request.default_gate) — 가짜 실행 목록 ==========================================
class GateTest(unittest.TestCase):
    def run_gate(self, runs, remote=None):
        """default_gate 를 가짜 `git ls-remote`(remote: 출력 글, 기본은 머리 SHA 한 줄)와 가짜 실행 목록으로 부른다. (돌려준 값, 종료 글·None, 출력, 목록 읽기 가짜)."""
        wc = load_wait_ci()
        remote = f"{SHA}\trefs/heads/{BRANCH}\n" if remote is None else remote
        out = io.StringIO()
        with mock.patch.dict(sys.modules, {"wait_ci": wc}), mock.patch.object(sys, "path", list(sys.path)), \
                mock.patch.object(wc, "runs_for", return_value=runs) as reader, \
                mock.patch.object(make_request.subprocess, "run", return_value=types.SimpleNamespace(stdout=remote, stderr="", returncode=0)), \
                contextlib.redirect_stdout(out):
            try:
                result, message = make_request.default_gate(TARGET, WORK), None
            except SystemExit as stop:
                result, message = None, str(stop.code)
        return result, message, out.getvalue(), reader

    def test_a_list_with_the_known_waiting_run_passes_the_gate(self):
        runs = [make_run(PUSH, event="push", ident=11, timing="2m 36s"),
                make_run("[공통] AI 요청 텔레그램 알림", event="push", ident=12, timing="9s"),
                make_run(KNOWN, conclusion="action_required", ident=13, timing="")]               # 봇이 만든 PR 의 승인 대기
        result, message, out, reader = self.run_gate(runs)
        self.assertIsNone(message, message)
        self.assertEqual(result, (SHA, runs))
        self.assertIn("검사 관문 통과", out)
        self.assertIn("실행 3건", out)
        reader.assert_called_once_with("shine88pc/chanceblog", BRANCH, SHA[:12])

    def test_a_waiting_run_of_another_name_blocks_the_gate_and_is_named_in_the_message(self):
        runs = [make_run(PUSH, event="push", ident=11), make_run(OTHER, conclusion="action_required", ident=14)]
        result, message, out, _reader = self.run_gate(runs)
        self.assertIsNone(result)
        self.assertIn("검사가 아직 끝나지 않았거나 초록이 아니다", message)
        self.assertIn("14(completed/action_required)", message)
        self.assertNotIn("11(", message)
        self.assertNotIn("검사 관문 통과", out)

    def test_the_known_waiting_run_does_not_hide_a_real_failure(self):
        runs = [make_run(PUSH, event="push", ident=11, conclusion="failure"), make_run(KNOWN, conclusion="action_required", ident=13)]
        result, message, _out, _reader = self.run_gate(runs)
        self.assertIsNone(result)
        self.assertIn("11(completed/failure)", message)
        self.assertNotIn("13(", message)                                                  # 막은 이유 목록에는 진짜 실패만 있다

    def test_cancelled_and_unfinished_runs_block_the_gate_even_with_the_known_name(self):
        for label, run in (("취소", make_run(KNOWN, conclusion="cancelled", ident=15)),
                           ("진행 중", make_run(KNOWN, status="in_progress", conclusion="", ident=16)),
                           ("대기열", make_run(KNOWN, status="queued", conclusion="", ident=17)),
                           ("완료가 아닌데 결론이 성공으로 남은 모양", make_run(PUSH, event="push", status="in_progress", conclusion="success", ident=20))):
            with self.subTest(label):
                result, message, _out, _reader = self.run_gate([make_run(PUSH, event="push", ident=11), run])
                self.assertIsNone(result)
                self.assertIn(f"{run['id']}(", message)

    def test_an_empty_list_and_a_missing_remote_branch_stop_the_gate(self):
        result, message, _out, _reader = self.run_gate([])
        self.assertIsNone(result)
        self.assertIn("목록에 없다", message)
        result, message, _out, reader = self.run_gate([make_run(PUSH, event="push")], remote="")
        self.assertIsNone(result)
        self.assertIn("원격에 브랜치가 없다", message)
        reader.assert_not_called()                                                         # 가지가 없으면 실행 목록을 읽지도 않는다


# ==== wait_ci.main — 기다리는 도구도 같은 규칙 ====================================================
class WaitMainTest(unittest.TestCase):
    def run_main(self, runs):
        wc = load_wait_ci()
        out = io.StringIO()
        with mock.patch.object(wc, "runs_for", return_value=runs), \
                mock.patch.object(sys, "argv", ["wait_ci.py", "shine88pc/chanceblog", BRANCH, SHA[:7], "1"]), \
                mock.patch.object(wc.time, "sleep", side_effect=AssertionError("모두 끝난 목록에서는 기다리지 않는다")), \
                contextlib.redirect_stdout(out):
            code = wc.main()
        return code, out.getvalue()

    def test_the_known_waiting_run_ends_the_wait_with_success(self):
        code, out = self.run_main([make_run(PUSH, event="push", ident=11), make_run(KNOWN, conclusion="action_required", ident=13)])
        self.assertEqual(code, 0, out)
        self.assertIn("모두 성공", out)

    def test_another_waiting_run_failures_and_cancellations_end_the_wait_with_a_failure(self):
        for label, run in (("다른 승인 대기", make_run(OTHER, conclusion="action_required", ident=14)),
                           ("실패", make_run(PUSH, event="push", conclusion="failure", ident=18)),
                           ("취소", make_run(PUSH, event="push", conclusion="cancelled", ident=19))):
            with self.subTest(label):
                code, out = self.run_main([make_run(PUSH, event="push", ident=11), run])
                self.assertEqual(code, 1, out)
                self.assertIn("실패·취소 있음", out)


# ==== 웹 목록 HTML 읽기(내장 JSON 이 없을 때의 대체) ===============================================
def html_row(state, ident, title, sha=SHA, branch=BRANCH, duration="2m 36s"):
    return (f'<div class="Box-row"><svg aria-label="{state}" role="img"></svg>'
            f'<a class="h4 Link--primary Link--underline" href="/o/r/actions/runs/{ident}">{title}</a>'
            f'<a href="/o/r/commit/{sha}">x</a>'
            f'<span class="d-inline-block branch-name" title="{branch}">b</span><span>{duration}</span></div>')


class HtmlReadTest(unittest.TestCase):
    def read(self, rows, sha=SHA[:12]):
        wc = load_wait_ci()
        with mock.patch.object(wc, "fetch", return_value="<html><body>" + "".join(rows) + "</body></html>"):
            return wc, wc._runs_for_html("o/r", BRANCH, sha)

    def test_states_map_to_the_same_status_and_conclusion_words_as_the_other_readers(self):
        rows = [html_row("completed successfully", 101, PUSH),
                html_row("action required", 102, KNOWN, duration=""),
                html_row("skipped", 103, OTHER),
                html_row("failed", 104, "[공통] 실패한 것"),
                html_row("cancelled", 105, "[공통] 취소된 것"),
                html_row("currently running", 106, "[공통] 도는 것"),
                html_row("queued", 107, "[공통] 기다리는 것")]
        _wc, found = self.read(rows)
        self.assertEqual([(r["id"], r["status"], r["conclusion"]) for r in found],
                         [(101, "completed", "success"), (102, "completed", "action_required"), (103, "completed", "skipped"),
                          (104, "completed", "failure"), (105, "completed", "cancelled"), (106, "in_progress", ""), (107, "queued", "")])
        self.assertEqual(found[0]["name"], PUSH)
        self.assertEqual(found[0]["timing"], "2m 36s")

    def test_the_action_required_label_feeds_the_same_rule_as_the_other_readers(self):
        wc, found = self.read([html_row("action required", 102, KNOWN), html_row("action required", 104, OTHER)])
        self.assertEqual([wc.run_ok(r) for r in found], [True, False])

    def test_rows_of_other_commits_and_other_branches_are_left_out(self):
        rows = [html_row("completed successfully", 101, PUSH),
                html_row("completed successfully", 201, PUSH, sha="b" * 40),
                html_row("completed successfully", 301, PUSH, branch="ai/claude/M099-other-1")]
        _wc, found = self.read(rows)
        self.assertEqual([r["id"] for r in found], [101])

    def test_a_page_without_state_labels_is_reported_as_unreadable(self):
        wc = load_wait_ci()
        with mock.patch.object(wc, "fetch", return_value="<html><body>아무 표시도 없는 쪽</body></html>"):
            with self.assertRaises(RuntimeError):
                wc._runs_for_html("o/r", BRANCH, SHA[:12])


# ==== 읽는 순서(웹 내장 JSON → 웹 HTML → 공개 REST) ===============================================
class ReaderOrderTest(unittest.TestCase):
    ROW = make_run(PUSH, event="push", ident=101)

    def order(self, web, html):
        wc = load_wait_ci()
        with mock.patch.object(wc, "_runs_for_web", **web) as web_reader, \
                mock.patch.object(wc, "_runs_for_html", **html) as html_reader, \
                mock.patch.object(wc, "_runs_for_rest", return_value=[self.ROW]) as rest_reader:
            found = wc.runs_for("o/r", BRANCH, SHA[:12])
        return found, (web_reader.call_count, html_reader.call_count, rest_reader.call_count)

    def test_the_web_json_is_used_first_and_an_empty_answer_is_not_a_reason_to_fall_back(self):
        self.assertEqual(self.order({"return_value": [self.ROW]}, {"return_value": []}), ([self.ROW], (1, 0, 0)))
        self.assertEqual(self.order({"return_value": []}, {"return_value": [self.ROW]}), ([], (1, 0, 0)))      # 읽었는데 아직 그 커밋의 실행이 없는 것 — 기다린다

    def test_the_html_list_is_tried_before_the_rest_limit_is_spent(self):
        self.assertEqual(self.order({"side_effect": RuntimeError("x")}, {"return_value": [self.ROW]}), ([self.ROW], (1, 1, 0)))

    def test_the_rest_reader_is_the_last_resort(self):
        self.assertEqual(self.order({"side_effect": RuntimeError("x")}, {"side_effect": RuntimeError("y")}), ([self.ROW], (1, 1, 1)))
        self.assertEqual(self.order({"side_effect": RuntimeError("x")}, {"return_value": []}), ([self.ROW], (1, 1, 1)))


# ==== 모양·문서 ===================================================================================
class ShapeAndDocumentTest(unittest.TestCase):
    def test_both_tool_files_read_without_syntax_errors_in_the_python_3_10_grammar(self):
        for path in (WORK / "make_request.py", WAIT_CI_PATH):
            source = path.read_text(encoding="utf-8")
            ast.parse(source, filename=path.name, feature_version=(3, 10))
            self.assertTrue(source.endswith("\n"), path.name)

    def test_the_tool_files_carry_no_hidden_control_characters(self):
        """편집 도구가 정규식의 단어 경계(역슬래시 b)를 진짜 백스페이스 글자로 바꿔 넣은 적이 있다(웹 목록 HTML 읽기의 걸린 시간 칸이 조용히 비었다) — 보이지 않는 제어 글자는 없어야 한다."""
        allowed = {chr(9), chr(10), chr(13)}
        for path in (WORK / "make_request.py", WAIT_CI_PATH):
            text = path.read_text(encoding="utf-8")
            bad = sorted({hex(ord(char)) for char in text if (ord(char) < 32 and char not in allowed) or ord(char) == 127})
            self.assertEqual(bad, [], path.name)

    def test_the_gate_and_the_waiter_use_the_same_rule_for_what_counts_as_green(self):
        wc = load_wait_ci()
        gate_source = inspect.getsource(make_request.default_gate)
        self.assertIn("wait_ci.run_ok(", gate_source)
        self.assertNotIn("OK_CONCLUSIONS", gate_source)                                     # 관문이 옛 집합을 직접 보면 승인 대기 예외가 관문에서만 빠진다
        main_source = inspect.getsource(wc.main)
        self.assertIn("run_ok(", main_source)
        self.assertNotIn("OK_CONCLUSIONS", main_source)

    def test_the_tool_readme_says_the_gate_counts_the_known_waiting_run_as_green(self):
        text = (TOOLS / "README.md").read_text(encoding="utf-8")
        for needle in ("`run_ok`", "`action_required`", "`[공통] PR 변경 범위 검사`", "tests/test_wait_ci_gate.py", "승인 대기"):
            self.assertIn(needle, text, needle)


if __name__ == "__main__":
    unittest.main()
