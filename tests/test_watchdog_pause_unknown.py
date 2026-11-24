"""오타로 걸린 발행 정지도 워치독이 알린다(BP3, BP2 보고서 ⑦ b, 결함 D-432) 시험. 네트워크 없이 돈다.

배경: 저장소 변수 PIPELINE_PAUSE 의 값을 알 수 없으면(오타 등 — pipeline/pause.py) 모든 실행이 정지로 읽는다(D-412). 워치독은 그 값도 '일부러 멈춘 것' 과 같은 판정으로 조용히 끝나(알림 없음,
실행은 초록) 오타로 멈춘 것을 알아볼 길이 로그의 ::error:: 한 줄과 확인 필요 모음의 항목뿐이었다. 이제 워치독은 값을 구분한다:
 - 알려진 켜짐 값(1·true·yes·on 과 대소문자·공백 변형 — 일부러 멈춤): 예전 그대로 '[일시정지]' 한 줄·요약 한 줄로 조용히 끝난다(점검도 이슈도 없다).
 - 값을 알 수 없음: 조용히 있지 않는다 — 점검을 이어 가고(다른 알림도 그대로 울린다) ::error:: 한 줄을 남기며 공통 알림 `[Watchdog] 공통: PAUSE_UNKNOWN`(심각)을 하나 더한다.
 - 알려진 꺼짐 값·빈 값·변수 없음: 예전 그대로 정상 점검(알림 없음).
알림 문장·로그·요약·이슈 본문 어디에도 받은 값을 싣지 않는다(여러 줄이거나 '::' 로 시작해도 워크플로 명령이 되지 않게 — pause.error_line 과 같은 관례).
알 수 없는 값 갈래의 보조 출력 셋(::error:: 줄·실행 요약 머리 덩어리·알림 고정 문장)과 켜짐 값의 예전 두 줄은 문구를 이 시험에 글자로 적어 못박는다(BP3 독립 검증 Q 권고-1 — 코드의 상수·함수와 같은 곳을 읽어 견주면 그것을 같이 바꾼 변이가 통과한다).
"""
import io
import os
import re
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import _bootstrap
from pipeline import pause, terms_deadline
from pipeline.health import Finding

sys.path.insert(0, str(_bootstrap.ROOT / "scripts"))
import watchdog  # noqa: E402

ROOT = _bootstrap.ROOT
DOCS = ROOT / "docs"
OWNER = "octo"
NOW = datetime(2026, 11, 24, 3, 0, tzinfo=timezone.utc)
TITLE = "[Watchdog] 공통: PAUSE_UNKNOWN"
ON_VALUES = ("true", "TRUE", " true ", "1", "yes", "on", "On", "TrUe", " YES ", "\ton\n")
OFF_VALUES = ("false", "0", "no", "off", "False", " no ", "OFF")
BLANK_VALUES = ("", " ", "\t", "\n", "  ")
UNKNOWN_VALUES = ("enabled", "paused", "pause", "stop", "y", "ture", "truee", "2", "disabled", "none", "null", "maybe", "yes please", "0.0", "tru", "1 1")
CANARY = "CANARY_" + "x7q"                                        # 알 수 없는 값이면서 다른 글에 섞여 나올 수 없는 조각(받은 값이 어디에도 안 실리는지 본다 — 비밀이 잘못 들어간 경우를 흉내 낸 가짜 값)
INJECTION = "evil" + chr(10) + "::set-output name=x::y"           # 줄바꿈과 워크플로 명령을 품은 값
STALE = Finding("chance", "STALE", "critical", "마지막 활동 이후 65시간 경과")

# ---- 글자로 못박는 문구(코드에서 읽어 오지 않는다) ----
PINNED_ERROR_LINE = "::error::저장소 변수 PIPELINE_PAUSE 의 값을 알 수 없어 정지로 읽습니다(켜짐 1·true·yes·on, 꺼짐 0·false·no·off 또는 비움). 값을 고치거나 변수를 지우세요."      # 알 수 없는 값 갈래가 가장 먼저 찍는 줄(pause.error_line() 과 같다)
PINNED_UNKNOWN_SUMMARY = ("### 워치독 점검 결과 — 발행 정지 변수\n- **경고** 저장소 변수 PIPELINE_PAUSE 의 값을 알 수 없어 다른 실행은 정지로 읽고 있습니다(오타일 수 있습니다) — "
                          "일부러 멈춘 것으로 보지 않고 점검을 이어 가며 알림을 만듭니다.")                                                # 알 수 없는 값 갈래가 실행 요약 맨 앞에 남기는 덩어리
PINNED_ALERT_CLAUSES = (
    "저장소 변수 PIPELINE_PAUSE 의 값을 알 수 없어(켜짐은 1·true·yes·on, 꺼짐은 0·false·no·off 또는 비움)",
    "모든 발행 실행이 안전한 쪽인 정지로 읽고 멈춰 있습니다 — 오타일 수 있습니다.",
    "일부러 멈춘 것이면 값을 true 로 고치고, 다시 발행하려면 변수를 지우거나 false 로 바꾸세요.",
    "지우거나 false 로 바꾸면 다음 점검에서 이 알림이 자동으로 닫힙니다",
    "(true 로 고치면 일부러 멈춘 상태로 읽혀 워치독이 조용해지므로 이 알림은 직접 닫으세요).",
)
PINNED_ALERT_SENTENCE = " ".join(PINNED_ALERT_CLAUSES[:3]) + " " + PINNED_ALERT_CLAUSES[3] + PINNED_ALERT_CLAUSES[4]                                      # 알림 고정 문장 전체(이슈 본문·요약에 그대로 실린다)
PINNED_QUIET_LINE = "[일시정지] PIPELINE_PAUSE 가 켜져 있어 점검 알림을 만들지 않습니다."                                                                  # 켜짐 값의 예전 두 줄(기준 a39f2d6 과 같은 글자)
PINNED_QUIET_SUMMARY = "### 워치독 점검 결과\n- **일시정지** — 저장소 변수 PIPELINE_PAUSE 가 켜져 있어 알림을 만들지 않았습니다."


class FakeClient:
    def __init__(self, open_issues=()):
        self.open_issues = list(open_issues)
        self.created, self.assignees, self.comments, self.closed, self.updated, self.listed = [], [], [], [], [], []

    def list_open_issues(self):
        self.listed.append(1)
        return list(self.open_issues)

    def create_issue(self, title, body, assignees=None):
        self.created.append((title, body))
        self.assignees.append(assignees)

    def comment(self, number, body):
        self.comments.append((number, body))

    def close(self, number):
        self.closed.append(number)

    def update_body(self, number, body):
        self.updated.append((number, body))

    def calls(self):
        return [self.created, self.comments, self.closed, self.updated, self.listed]


class Result:
    def __init__(self, code, out, client, summary, collect_calls):
        self.code, self.out, self.client, self.summary, self.collect_calls = code, out, client, summary, collect_calls

    def error_lines(self):
        return [line for line in self.out.splitlines() if line.startswith("::error::") and "PIPELINE_PAUSE" in line]


def run_main(value, findings=(), open_issues=(), dry=False, token=True):
    """watchdog.main() 을 끝까지 돈다(레지스트리 읽기·점검은 가짜, GitHub 는 가짜 클라이언트). value 가 None 이면 변수가 없다."""
    client = FakeClient(open_issues)
    calls = []

    def fake_collect(*args, **kwargs):
        calls.append(1)
        return list(findings), []

    with tempfile.TemporaryDirectory() as tmp:
        summary = Path(tmp) / "summary.md"
        env = {"GITHUB_STEP_SUMMARY": str(summary)}
        if value is not None:
            env["PIPELINE_PAUSE"] = value
        if token:
            env.update(GITHUB_TOKEN="t" * 8, GITHUB_REPOSITORY=OWNER + "/blog", GITHUB_REPOSITORY_OWNER=OWNER)
        if dry:
            env["WATCHDOG_DRY_RUN"] = "1"
        buffer = io.StringIO()
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(watchdog, "load_registry", return_value={"blogs": []}), \
                mock.patch.object(watchdog, "validate_registry", return_value=[]), mock.patch.object(watchdog, "collect", side_effect=fake_collect), \
                mock.patch.object(watchdog, "GitHubClient", return_value=client), redirect_stdout(buffer):
            os.environ.update(env)
            code = watchdog.main()
        text = summary.read_text(encoding="utf-8") if summary.exists() else ""
    return Result(code, buffer.getvalue(), client, text, len(calls))


class KnownOnValuesStaySilentTest(unittest.TestCase):
    def test_a_known_on_value_ends_quietly_without_checks_or_issues(self):
        for value in ON_VALUES:
            with self.subTest(value=value):
                result = run_main(value, findings=[STALE])
                self.assertEqual(result.code, 0)
                self.assertIn("[일시정지] PIPELINE_PAUSE 가 켜져 있어 점검 알림을 만들지 않습니다.", result.out)      # 예전 문장 그대로
                self.assertEqual(result.collect_calls, 0)                                                              # 점검을 돌지 않는다
                self.assertEqual(result.client.calls(), [[], [], [], [], []])                                          # GitHub 를 읽지도 쓰지도 않는다
                self.assertEqual(result.error_lines(), [])
                self.assertNotIn("PAUSE_UNKNOWN", result.out + result.summary)
                self.assertIn("일시정지", result.summary)
                self.assertIn("켜져 있", result.summary)
                self.assertNotIn("알 수 없", result.summary)

    def test_the_quiet_run_writes_exactly_the_old_two_lines_word_for_word(self):
        for value in ON_VALUES:
            with self.subTest(value=value):
                result = run_main(value)
                self.assertEqual(result.out.strip(), PINNED_QUIET_LINE)                           # 기준 a39f2d6 의 문장과 같은 글자, 다른 줄이 없다
                self.assertEqual(result.summary, PINNED_QUIET_SUMMARY + "\n\n")                   # 요약도 그 한 덩어리뿐이다

    def test_the_quiet_run_is_the_same_with_or_without_a_token(self):
        for token in (True, False):
            result = run_main("true", token=token)
            self.assertEqual((result.code, result.collect_calls, result.error_lines()), (0, 0, []))


class UnknownValueAlertsTest(unittest.TestCase):
    def test_an_unknown_value_is_not_quiet_it_keeps_checking_and_adds_one_critical_alert(self):
        for value in UNKNOWN_VALUES:
            with self.subTest(value=value):
                result = run_main(value)
                self.assertEqual(result.collect_calls, 1)                                         # 점검을 이어 간다
                self.assertNotIn("[일시정지]", result.out)                                         # 일부러 멈춘 것으로 보지 않는다
                self.assertEqual(len(result.error_lines()), 1, result.out)                         # ::error:: 한 줄(받은 값 없이)
                self.assertEqual([title for title, _body in result.client.created], [TITLE])      # 공통 알림 하나
                self.assertEqual(result.client.assignees, [[OWNER]])                              # 담당자가 지정된다(다른 알림과 같다)
                self.assertIn("@" + OWNER, result.client.created[0][1])
                self.assertIn("PAUSE_UNKNOWN", result.client.created[0][1])
                self.assertIn("critical", result.client.created[0][1])

    def test_the_run_goes_red_for_a_new_alert_like_any_new_critical_finding(self):
        result = run_main("enabled")
        self.assertEqual(result.code, 1)
        self.assertIn("::error::새로 생긴 심각 건: " + TITLE, result.out)

    def test_an_alert_that_is_already_open_keeps_the_run_green_and_creates_nothing(self):
        finding = watchdog.pause_findings({"PIPELINE_PAUSE": "enabled"})[0]
        stamp = (NOW - timedelta(hours=2)).isoformat(timespec="seconds")
        issue = {"title": finding.title, "number": 7, "body": watchdog.issue_body(finding, OWNER, stamp), "created_at": (NOW - timedelta(days=3)).isoformat()}
        with mock.patch.object(watchdog, "datetime") as fake_datetime:
            fake_datetime.now.return_value = NOW
            fake_datetime.fromisoformat.side_effect = datetime.fromisoformat
            result = run_main("enabled", open_issues=[issue])
        self.assertEqual((result.code, result.client.created, result.client.closed), (0, [], []))
        self.assertEqual(len(result.error_lines()), 1)                                           # 로그의 ::error:: 한 줄은 실행마다 남는다

    def test_other_alerts_keep_ringing_next_to_the_new_one(self):
        result = run_main("enabled", findings=[STALE])
        self.assertEqual(sorted(title for title, _body in result.client.created), sorted([STALE.title, TITLE]))

    def test_a_dry_run_lists_the_alert_and_creates_nothing(self):
        for kwargs in ({"dry": True}, {"token": False}):
            result = run_main("enabled", **kwargs)
            self.assertEqual(result.code, 0)
            self.assertEqual(result.client.created, [])
            self.assertIn(TITLE, result.out)
            self.assertEqual(len(result.error_lines()), 1)

    def test_the_summary_says_the_value_was_unknown_and_never_says_the_pause_is_on(self):
        for value in UNKNOWN_VALUES:
            with self.subTest(value=value):
                result = run_main(value, dry=True)
                for needle in ("PIPELINE_PAUSE", "알 수 없", "정지로 읽", "PAUSE_UNKNOWN"):
                    self.assertIn(needle, result.summary, needle)
                self.assertNotIn("켜져 있", result.summary)
                self.assertNotIn("이상 없음", result.summary)

    def test_the_alert_sentence_is_the_fixed_one(self):
        result = run_main("enabled")
        body = result.client.created[0][1]
        self.assertIn(watchdog.PAUSE_FINDING_MESSAGE, body)
        self.assertIn("**블로그**: `공통` / **코드**: `PAUSE_UNKNOWN` / **심각도**: critical", body)


class UnknownValueAuxiliaryOutputsArePinnedTest(unittest.TestCase):
    """알림 밖의 보조 출력 셋을 문구까지 못박는다 — Q 검증의 변이 AD-05(요약 덩어리를 안 남김)·AD-06(알림 문장의 한 구절 삭제)·AD-09(::error:: 줄을 짧은 글로 바꿈)를 잡는다.
    기존 시험은 요약에서 낱말(PIPELINE_PAUSE·알 수 없·정지로 읽·PAUSE_UNKNOWN)만 봤는데 그 낱말이 요약 끝의 알림 문장에도 있어 덩어리가 없어도 통과했다."""

    def runs(self):
        for value in UNKNOWN_VALUES:
            for kwargs in ({}, {"dry": True}, {"token": False}):
                yield value, kwargs, run_main(value, **kwargs)

    def test_the_first_line_of_the_log_is_the_pinned_error_sentence(self):
        for value, kwargs, result in self.runs():
            with self.subTest(value=value, kwargs=kwargs):
                self.assertEqual(result.out.splitlines()[0], PINNED_ERROR_LINE)                    # 가장 먼저 찍히는 줄이 이 글자 그대로다
                self.assertEqual(result.error_lines()[0], PINNED_ERROR_LINE)

    def test_the_summary_opens_with_the_pinned_unknown_value_block(self):
        for value, kwargs, result in self.runs():
            with self.subTest(value=value, kwargs=kwargs):
                self.assertTrue(result.summary.startswith(PINNED_UNKNOWN_SUMMARY + "\n\n"), result.summary[:240])      # 요약 맨 앞의 덩어리 — 머리·'경고' 낱말·문장 전체
                self.assertEqual(result.summary.count("### 워치독 점검 결과 — 발행 정지 변수"), 1)                         # 한 번만 남는다
                self.assertIn("### 워치독 점검 결과\n", result.summary[len(PINNED_UNKNOWN_SUMMARY):])                    # 그 뒤에 보통의 점검 결과 요약이 이어진다

    def test_the_alert_sentence_in_the_issue_body_is_the_pinned_one_word_for_word(self):
        for value in ("enabled", CANARY, INJECTION):
            with self.subTest(value=value[:12]):
                result = run_main(value)
                self.assertIn(PINNED_ALERT_SENTENCE, result.client.created[0][1])
                self.assertEqual(result.client.created[0][1].count(PINNED_ALERT_CLAUSES[1]), 1)    # 오타 구절이 든 문장이 한 번

    def test_the_summary_table_carries_the_start_of_the_pinned_alert_sentence(self):
        result = run_main("enabled", dry=True)
        self.assertIn(PINNED_ALERT_SENTENCE[:300], result.summary)                                  # 요약 표는 문장의 앞 300자를 싣는다(render_summary)


class NoValueEchoTest(unittest.TestCase):
    def test_the_received_value_is_nowhere_in_the_output_the_summary_or_the_issue(self):
        for value in (CANARY, INJECTION):
            with self.subTest(value=value[:12]):
                result = run_main(value)
                everything = "\n".join([result.out, result.summary] + [body for _title, body in result.client.created] + [body for _number, body in result.client.comments])
                marker = "x7q" if value == CANARY else "evil"
                self.assertNotIn(marker, everything)
                self.assertNotIn("set-output", everything)
                self.assertEqual(len(result.error_lines()), 1, result.out)
                self.assertTrue(result.client.created)                                              # 알림은 그대로 나간다

    def test_no_line_of_the_output_starts_a_workflow_command_other_than_the_two_known_ones(self):
        result = run_main(INJECTION)
        commands = [line for line in result.out.splitlines() if line.startswith("::")]
        self.assertEqual(len(commands), 2, commands)                       # 값 알림 한 줄 + 새 심각 건 한 줄
        self.assertTrue(commands[0].startswith("::error::") and "PIPELINE_PAUSE" in commands[0])
        self.assertTrue(commands[1].startswith("::error::새로 생긴 심각 건: "))


class OffAndEmptyValuesStayNormalTest(unittest.TestCase):
    def test_known_off_values_blank_values_and_no_variable_run_the_normal_check(self):
        for value in OFF_VALUES + BLANK_VALUES + (None,):
            with self.subTest(value=value):
                result = run_main(value)
                self.assertEqual(result.code, 0)
                self.assertEqual(result.collect_calls, 1)
                self.assertIn("이상 없음", result.out)
                self.assertEqual(result.client.created, [])
                self.assertEqual(result.error_lines(), [])
                self.assertNotIn("PAUSE_UNKNOWN", result.out + result.summary)
                self.assertNotIn("[일시정지]", result.out)

    def test_a_normal_run_with_an_ordinary_finding_is_unchanged(self):
        result = run_main("false", findings=[STALE])
        self.assertEqual([title for title, _body in result.client.created], [STALE.title])
        self.assertEqual(result.code, 1)


class PauseFindingsTest(unittest.TestCase):
    def test_only_an_unknown_value_makes_a_finding(self):
        for value in ON_VALUES + OFF_VALUES + BLANK_VALUES:
            self.assertEqual(watchdog.pause_findings({"PIPELINE_PAUSE": value}), [], value)
        self.assertEqual(watchdog.pause_findings({}), [])
        for value in UNKNOWN_VALUES:
            found = watchdog.pause_findings({"PIPELINE_PAUSE": value})
            self.assertEqual(len(found), 1, value)
            self.assertEqual((found[0].blog, found[0].code, found[0].severity), (terms_deadline.FINDING_BLOG, "PAUSE_UNKNOWN", "critical"))
            self.assertEqual(found[0].title, TITLE)
            self.assertEqual(found[0].message, watchdog.PAUSE_FINDING_MESSAGE)

    def test_the_fixed_alert_sentence_is_the_pinned_one_word_for_word(self):
        """문구를 이 시험에 글자로 적어 못박는다 — Q 검증 변이 AD-06('오타일 수 있습니다' 한 구절 삭제)은 낱말 몇 개만 보던 옛 시험에 살아남았다. 구절마다 따로 보고(실패 메시지가 어느 구절인지 알려 준다) 전체도 같아야 한다."""
        text = watchdog.PAUSE_FINDING_MESSAGE
        for clause in PINNED_ALERT_CLAUSES:
            self.assertIn(clause, text, clause)
        self.assertEqual(text, PINNED_ALERT_SENTENCE)

    def test_the_shared_error_line_is_the_pinned_one_word_for_word(self):
        self.assertEqual(pause.error_line(), PINNED_ERROR_LINE)                                    # 읽는 모든 곳이 부르는 pipeline/pause.py 의 한 줄 — 같은 글자
        self.assertEqual(pause.error_line("[태그] "), "::error::[태그] " + PINNED_ERROR_LINE[len("::error::"):])

    def test_the_fixed_sentence_names_the_variable_the_reading_and_the_fix_without_saying_the_pause_is_on(self):
        text = watchdog.PAUSE_FINDING_MESSAGE
        for needle in ("PIPELINE_PAUSE", "알 수 없", "정지로 읽", "true", "false", "지우"):
            self.assertIn(needle, text, needle)
        self.assertNotIn("켜져 있", text)
        self.assertNotIn("\n", text)
        self.assertEqual(pause.state({"PIPELINE_PAUSE": "enabled"}), pause.UNKNOWN)      # 같은 판정을 쓴다 — 읽는 곳은 pipeline/pause.py 하나


class DocumentTest(unittest.TestCase):
    OPS = (DOCS / "OPS_INBOX.md").read_text(encoding="utf-8")
    GUIDE = (DOCS / "ACTIONS_GUIDE.md").read_text(encoding="utf-8")
    PUBLISH = (DOCS / "PUBLISH_PATHS.md").read_text(encoding="utf-8")
    DEFECTS = (DOCS / "DEFECT_REGISTER.md").read_text(encoding="utf-8")
    SOURCE = (ROOT / "scripts" / "watchdog.py").read_text(encoding="utf-8")

    def test_the_guide_has_a_row_for_the_new_code(self):
        row = next(line for line in self.GUIDE.splitlines() if line.startswith("| `PAUSE_UNKNOWN` |"))
        self.assertEqual(row.count("|"), 5)                                                  # 네 칸 — 칸 안에 세로선이 없다
        for needle in ("심각", "`PIPELINE_PAUSE`", "`공통`", "받은 값은 싣지 않음", "`true`", "`false`"):
            self.assertIn(needle, row, needle)

    def test_the_inbox_guide_and_the_publish_paths_say_the_watchdog_alerts_on_an_unknown_value(self):
        self.assertIn("워치독은 알 수 없는 값을 알립니다", self.OPS)
        self.assertNotIn("워치독은 일부러 조용합니다", self.OPS)
        self.assertIn("`[Watchdog] 공통: PAUSE_UNKNOWN`", self.OPS)
        item = next(line for line in self.PUBLISH.splitlines() if line.startswith("23. **발행 정지 변수의 값은"))
        self.assertIn("워치독은 알려진 켜짐 값일 때만 조용하다", item)
        self.assertIn("`[Watchdog] 공통: PAUSE_UNKNOWN`", item)
        self.assertNotIn("알림을 만들지 않는 것은 일부러 멈춘 것과 같은 판정이다", item)

    def test_the_script_header_describes_both_behaviors(self):
        head = self.SOURCE[:self.SOURCE.index('"""', 3)]
        self.assertIn("PAUSE_UNKNOWN", head)
        self.assertIn("켜짐 1·true·yes·on", head)

    def test_the_defect_row_d432_exists_once_with_six_cells_and_is_solved(self):
        rows = [line for line in self.DEFECTS.splitlines() if line.startswith("| **D-432** |")]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].count("|"), 7)
        self.assertIn("**해결**", rows[0])
        for needle in ("PAUSE_UNKNOWN", "BP2", "tests/test_watchdog_pause_unknown.py", "확인 032", "scripts/watchdog.py"):
            self.assertIn(needle, rows[0], needle)
        self.assertNotIn(chr(126), rows[0])
        self.assertIsNone(re.search(r"https?://", rows[0]))


if __name__ == "__main__":
    unittest.main()
