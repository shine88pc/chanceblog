"""병합 알림 자동화(`pipeline/auto_notice.py`) 단위 시험 — 켬 상태 읽기·입력 거르기·글 거르기·문장 만들기·두 알림의 판정(가짜 GitHub 응답)·판정 단계와 발송 단계·명령 줄·정적 성질.

GitHub 와 텔레그램은 한 번도 부르지 않는다: GitHub 는 `request(method, path, payload, params, retry)` 를 가진 가짜(`FakeApi` — 부른 것을 모두 기록해 GET 뿐인지 본다),
텔레그램은 `notify_helpers.FakeNet`(가짜 urlopen)과 런타임에 조합한 가짜 값이다. 이 시험이 고정하는 것:
 1. 켬 상태: 파일이 없거나 이상하면 off, off 에서는 환경변수(시크릿 포함)도 GitHub 도 건드리지 않는다. dry 는 문장을 요약에만, on 은 문장 파일과 출력 한 줄만 남긴다.
 2. 신뢰 경계: 가지·SHA·제목·글자 모양 거르기(주소·`@`·물결표·제어 문자·비밀 모양), 로그·요약에는 제목·본문 원문이 없다, GitHub 는 GET 만 부른다.
 3. 문장 규칙: 병합 부탁(제목 80자·요점 5줄×120자·800자 안·고정 꼬리)과 병합완료 확인(정상 한 줄·이상 사유 한 줄 100자 안).
 4. 판정: 병합 부탁은 열린 PR·머리 커밋·검사 모두 초록일 때만, 병합완료 확인은 [M번호] 병합 커밋·연결된 PR 하나·부모 수·트리 일치/파일 집합·main 검사 결론.
"""
import ast
import contextlib
import copy
import io
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import _bootstrap
import notify_helpers as nh
from pipeline import auto_notice as an
from pipeline import notify
from pipeline import operator_loop as ol

ROOT = _bootstrap.ROOT
MODULE = ROOT / "pipeline" / "auto_notice.py"
STATE = ROOT / "pipeline" / "auto_notice.json"

REPO = "octo/blog"
BRANCH = "ai/claude/M105-merge-notice"
NUMBER = "M105"
SHA = "a" * 39 + "1"
OTHER_SHA = "b" * 39 + "2"
HEAD_SHA = "c" * 39 + "3"
TREE = "d" * 39 + "4"
OTHER_TREE = "e" * 39 + "5"
RUN_ID = 4242
PR_NUMBER = 248
TITLE = "[M105] 병합 알림 자동화 — 워크플로 둘과 파이썬 보조 [대상: 공통]"
BODY = ("앞서 병합된 묶음의 다음 단계다. 변경 등급 T3 — 켬 상태는 off 로 낸다.\n"
        "- **워크플로 둘**: 병합 부탁 알림과 병합완료 확인 알림을 자동으로 보낸다.\n"
        "- 시험: 새 시험을 더했다\n"
        "\n"
        "Co-authored-by: Claude Sonnet 5.5 <noreply@anthropic.com>\n")
TILDE, AT = chr(0x7E), chr(0x40)
SCHEME = "ht" + "tps://"                                  # 주소 모양 글은 조립해서 쓴다(새 글에 웹 주소를 두지 않는다)
GITHUB_TOKEN_SHAPE = "gh" + "p_" + "A" * 36


# ----------------------------------------------------------------------------
# 가짜 GitHub
# ----------------------------------------------------------------------------
class Seq:
    """부를 때마다 차례로 하나씩(모자라면 마지막 것을 반복) 돌려주는 응답 묶음."""

    def __init__(self, *items):
        self.items, self.used = list(items), 0

    def next(self):
        item = self.items[min(self.used, len(self.items) - 1)]
        self.used += 1
        return item


class FakeApi:
    """operator_loop.GitHub 모양의 가짜. routes: {경로 또는 (경로, 쪽): 응답(JSON 값)·Exception·Seq}. 모든 호출을 (method, path, params, payload) 로 기록한다."""

    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def request(self, method, path, payload=None, params=None, retry=True):
        self.calls.append((method, path, dict(params or {}), payload))
        keyed = (path, (params or {}).get("page"))
        if keyed in self.routes:
            value = self.routes[keyed]
        elif path in self.routes:
            value = self.routes[path]
        else:
            raise ol.GitHubError("HTTP 404", 404)
        if isinstance(value, Seq):
            value = value.next()
        if isinstance(value, Exception):
            raise value
        return copy.deepcopy(value)

    def paths(self):
        return [call[1] for call in self.calls]

    def methods(self):
        return {call[0] for call in self.calls}


def pr_item(**over):
    item = {"number": PR_NUMBER, "state": "open", "draft": False, "title": TITLE, "body": BODY,
            "head": {"ref": BRANCH, "sha": SHA, "repo": {"full_name": REPO}}, "base": {"ref": "main"}}
    item.update(over)
    return item


def run_item(run_id, path=".github/workflows/guardrails.yml", status="completed", conclusion="success"):
    return {"id": run_id, "path": path + "@refs/heads/" + BRANCH, "status": status, "conclusion": conclusion, "event": "push"}


def good_runs():
    return [run_item(11), run_item(12, ".github/workflows/ai-request.yml"), run_item(13, ".github/workflows/telegram-inbox.yml"),
            run_item(RUN_ID, ".github/workflows/auto-pr.yml", status="in_progress", conclusion=None)]       # 이 실행을 일으킨 자동 PR 실행(목록에는 아직 진행 중으로 보일 수 있다)


def ready_routes(prs=None, runs=None):
    return {"/pulls": [pr_item()] if prs is None else prs, "/actions/runs": {"workflow_runs": good_runs() if runs is None else runs}}


def ready_env(**over):
    env = {"GITHUB_REPOSITORY": REPO, "NOTICE_RUN_ID": str(RUN_ID), "NOTICE_RUN_BRANCH": BRANCH, "NOTICE_RUN_SHA": SHA, "NOTICE_RUN_EVENT": "push",
           "NOTICE_RUN_CONCLUSION": "success", "NOTICE_RUN_REPO": REPO, "NOTICE_DEFAULT_BRANCH": "main", "GITHUB_TOKEN": "CANARY_read_token"}
    env.update(over)
    return env


def confirm_env(**over):
    return ready_env(NOTICE_RUN_BRANCH="main", **over)


def commit_obj(sha=SHA, message="[M105] 병합 알림 자동화 — 워크플로 둘과 파이썬 보조 [대상: 공통] (#248)\n\n본문", parents=(OTHER_SHA,), tree=TREE, files=("a.py", "b.md")):
    item = {"sha": sha, "commit": {"message": message, "tree": {"sha": tree}}, "parents": [{"sha": parent} for parent in parents]}
    if files is not None:
        item["files"] = [{"filename": name} for name in files]
    return item


def pull_item(number=PR_NUMBER, merge_sha=SHA, merged=True):
    return {"number": number, "merged_at": "2026-11-23T05:00:00Z" if merged else None, "merge_commit_sha": merge_sha}


def pr_detail(**over):
    item = {"number": PR_NUMBER, "merged": True, "merge_commit_sha": SHA, "title": TITLE, "changed_files": 2, "base": {"ref": "main"}, "head": {"sha": HEAD_SHA}}
    item.update(over)
    return item


def confirm_routes(extra=None, **over):
    """기본 경로 표(트리 일치) 위에 extra(경로 또는 (경로, 쪽) 키의 표)와 over(문자열 키워드)를 덮어쓴다."""
    routes = {f"/commits/{SHA}": commit_obj(), f"/commits/{SHA}/pulls": [pull_item()], f"/pulls/{PR_NUMBER}": pr_detail(), f"/commits/{HEAD_SHA}": commit_obj(HEAD_SHA, "[M105] x", (OTHER_SHA,), TREE)}
    routes.update(extra or {})
    routes.update(over)
    return routes


def no_sleep(_seconds):
    return None


class SpyEnv(dict):
    """읽은 환경변수 이름을 기록하는 환경 — 어떤 단계가 무엇을 읽었는지(시크릿을 읽지 않았는지) 본다."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.reads = []

    def get(self, name, default=None):
        self.reads.append(name)
        return super().get(name, default)

    def __getitem__(self, name):
        self.reads.append(name)
        return super().__getitem__(name)

    def __contains__(self, name):
        self.reads.append(name)
        return super().__contains__(name)


# ----------------------------------------------------------------------------
# 켬 상태
# ----------------------------------------------------------------------------
class ModeFileTest(unittest.TestCase):
    def read(self, text, raw=None):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "auto_notice.json"
            path.write_bytes(raw if raw is not None else text.encode("utf-8"))
            return an.read_mode(path)

    def test_the_repository_file_is_off_and_is_exactly_one_key(self):
        self.assertEqual(json.loads(STATE.read_text(encoding="utf-8")), {"mode": "off"})
        self.assertEqual(an.read_mode(), "off")
        self.assertEqual(an.read_mode(STATE), "off")

    def test_the_three_values_are_read_as_they_are(self):
        for mode in ("off", "dry", "on"):
            with self.subTest(mode):
                self.assertEqual(self.read(json.dumps({"mode": mode})), mode)
                self.assertEqual(self.read('{"mode":"' + mode + '"}\n'), mode)

    def test_anything_odd_means_off(self):
        odd = ["", "   ", "{", "[]", "null", "1", '"on"', '{"mode": 1}', '{"mode": null}', '{"mode": ["on"]}', '{"mode": true}', '{}',
               '{"Mode": "on"}', '{"mode": "ON"}', '{"mode": "On"}', '{"mode": " on"}', '{"mode": "on "}', '{"mode": "on\\n"}', '{"mode": "dry-run"}', '{"mode": "yes"}',
               '{"mode": "on", "extra": 1}', '{"mode": "on", "mode": "on"}', '{"mode": "off", "mode": "on"}', '{"mode": "on",}', "mode: on", "on", "{'mode': 'on'}",
               '{"mode": "on"} {"mode": "on"}', '{"mode": "on"}\x00']
        for text in odd:
            with self.subTest(text):
                self.assertEqual(self.read(text), "off")

    def test_a_missing_directory_a_binary_file_a_bom_and_a_huge_file_mean_off(self):
        self.assertEqual(an.read_mode(Path(tempfile.gettempdir()) / "no_such_dir_auto_notice" / "x.json"), "off")
        self.assertEqual(self.read("", raw=b"\xff\xfe\x00\x01"), "off")
        self.assertEqual(self.read("", raw=b"\xef\xbb\xbf" + b'{"mode": "on"}'), "off")           # BOM 이 붙은 파일도 이상한 값이다
        self.assertEqual(self.read("", raw=b'{"mode": "on"}' + b" " * 2000), "off")                # 1KB 가 넘으면 읽지 않는다
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(an.read_mode(tmp), "off")                                               # 폴더를 가리켜도 off

    def test_the_path_defaults_to_the_repository_file_not_the_working_directory(self):
        self.assertEqual(an.STATE_FILE, ROOT / "pipeline" / "auto_notice.json")


# ----------------------------------------------------------------------------
# 글 거르기
# ----------------------------------------------------------------------------
class LineProblemTest(unittest.TestCase):
    def test_plain_korean_lines_pass(self):
        for text in ("워크플로 둘을 더했다", "변경 등급 T3 — 켬 상태는 off 로 낸다.", "docs/ARCHITECTURE.md 에 절을 더했다", "auto-pr.yml 과 validate_repo.py 는 그대로", "시험 9,829개 → 9,900개",
                     "Python 3.12 와 3.10 둘 다", "결함 D-398 부터 D-405", "v1.2.3 으로 올림", "node.js 와 next.js 는 쓰지 않는다", "파일: 하나", "data: 하나"):
            with self.subTest(text):
                self.assertEqual(an.line_problem(text), "")

    def test_each_problem_has_its_own_code(self):
        cases = [("", "empty"), ("   ", "empty"), ("a\nb", "control"), ("a\tb", "control"), ("a\x00b", "control"), ("a" + chr(0x200B) + "b", "control"), ("a" + chr(0x202E) + "b", "control"),
                 ("담당 " + AT + "someone", "mention"), ("메일 someone" + AT + "example", "mention"), ("전각 " + chr(0xFF20) + "someone", "mention"),
                 (SCHEME + "evil.example/x", "address"), ("ht" + "tp://evil.example", "address"), ("tg://resolve?domain=x", "address"), ("ftp://x", "address"),
                 ("www.evil.example", "address"), ("github.com 에 있다", "address"), ("evil.io/path", "address"), ("see example.com요", "address"),
                 ("mailto:x", "address"), ("javascript:alert(1)", "address"), ("data:text/html,x", "address"), ("접속 10.0.0.1 로", "address"),
                 ("ｈｔｔｐ：／／evil.example", "address"), ("ｗｗｗ．evil.example", "address"),
                 ("약 10" + TILDE + "20개", "tilde"), ("전각 10" + chr(0xFF5E) + "20", "tilde"),
                 ("키 " + nh.TOKEN, "secret"), ("토큰 " + GITHUB_TOKEN_SHAPE, "secret")]
        for text, code in cases:
            with self.subTest(text[:30]):
                self.assertEqual(an.line_problem(text), code)

    def test_a_secret_split_by_invisible_characters_is_caught_not_as_a_clean_line(self):
        split = nh.TOKEN[:8] + chr(0x200B) + nh.TOKEN[8:]
        self.assertNotEqual(an.line_problem("키 " + split), "")

    def test_non_text_values_are_empty(self):
        for value in (None, 5, [], b"x"):
            self.assertEqual(an.line_problem(value), "empty")


class CleanAndPointsTest(unittest.TestCase):
    def test_clean_inline_strips_markup_and_replaces_tildes_with_en_dashes(self):
        self.assertEqual(an.clean_inline("  **굵게**   `코드`  약 10" + TILDE + "20  "), "굵게 코드 약 10" + chr(0x2013) + "20")
        for tilde in (TILDE, chr(0xFF5E), chr(0x301C), chr(0x223C)):
            self.assertNotIn(tilde, an.clean_inline("a" + tilde + "b"))
        self.assertEqual(an.clean_inline(None), "")

    def test_shorten_keeps_exactly_the_limit_in_characters(self):
        self.assertEqual(an.shorten("가" * 80, 80), "가" * 80)
        self.assertEqual(an.shorten("가" * 81, 80), "가" * 79 + chr(0x2026))
        self.assertEqual(len(an.shorten("가" * 500, 120)), 120)
        self.assertEqual(an.shorten("", 5), "")

    def test_points_skip_trailers_headings_blank_lines_and_rules(self):
        body = "# 요약\n\n- 첫째 줄\n* 둘째 줄\n1. 셋째 줄\n> 인용 줄\n---\n***\nCo-authored-by: 누구 <x>\nSigned-off-by: 누구\nad-surface-approved: 사유\n마지막 줄\n"
        self.assertEqual(an.point_lines(body), ["첫째 줄", "둘째 줄", "셋째 줄", "인용 줄", "마지막 줄"])

    def test_points_take_at_most_five_lines_of_at_most_120_characters(self):
        body = "\n".join(f"- 줄 {index} " + "가" * 200 for index in range(1, 9))
        points = an.point_lines(body)
        self.assertEqual(len(points), 5)
        self.assertTrue(all(len(point) == 120 and point.endswith(chr(0x2026)) for point in points))
        self.assertTrue(points[0].startswith("줄 1 ") and points[4].startswith("줄 5 "))
        self.assertEqual(an.point_lines(body, limit_lines=2), points[:2])

    def test_a_bad_line_is_dropped_alone_and_the_rest_is_kept(self):
        body = "\n".join(["- 좋은 줄 하나", "- 담당 " + AT + "someone", "- 주소 " + SCHEME + "evil.example", "- 비밀 " + nh.TOKEN, "- 제어" + chr(0x200B) + "문자", "- 좋은 줄 둘"])
        self.assertEqual(an.point_lines(body), ["좋은 줄 하나", "좋은 줄 둘"])

    def test_points_never_contain_tildes_or_markup(self):
        body = "- **굵게** 약 10" + TILDE + "20 `코드`\n- 다른 " + chr(0xFF5E) + " 줄"
        for point in an.point_lines(body):
            self.assertNotRegex(point, r"[`*]")
            self.assertNotIn(TILDE, point)
            self.assertNotIn(chr(0xFF5E), point)

    def test_only_the_first_400_lines_are_read_so_a_huge_body_cannot_add_work(self):
        """요점은 앞쪽 줄에서 고르므로 본문은 앞 400줄만 읽는다 — 앞 399줄이 모두 걸러져도 400째 줄은 읽고, 401째 줄은 읽지 않는다. 아주 긴 본문(6만 줄)도 일이 늘지 않는다."""
        bad = "@" + "x"
        self.assertEqual(an.POINT_SCAN_LINES, 400)
        self.assertEqual(an.point_lines("\n".join([bad] * 399 + ["- 좋은 줄"])), ["좋은 줄"])
        self.assertEqual(an.point_lines("\n".join([bad] * 400 + ["- 좋은 줄"])), [])
        huge = ("@x\n" * 60000) + "- 좋은 줄\n"
        started = time.monotonic()
        self.assertEqual(an.point_lines(huge), [])
        self.assertLess(time.monotonic() - started, 20)                              # 아주 넉넉한 상한 — 병목이 생기는 변경만 잡는다

    def test_adversarial_long_lines_are_checked_in_bounded_time(self):
        for text in ("a." * 60, "a" * 120, "-" * 120, "a-" * 60 + ".com", "1" * 120, ("a." * 40) + "z" * 40, "http" * 30, "@" * 120):
            started = time.monotonic()
            an.line_problem(text)
            self.assertLess(time.monotonic() - started, 5, text[:20])

    def test_crlf_cr_and_odd_bodies(self):
        self.assertEqual(an.point_lines("- 하나\r\n- 둘\r\n"), ["하나", "둘"])
        self.assertEqual(an.point_lines("- 하나\r- 둘"), ["하나", "둘"])
        for value in (None, "", "   \n\n", 5, [], b"x"):
            self.assertEqual(an.point_lines(value), [])


# ----------------------------------------------------------------------------
# 문장
# ----------------------------------------------------------------------------
TAIL = "병합은 Pull requests 에서 제목 맨 앞이 [M105] 인 PR 하나만 하세요. 알림이 없는 열린 PR 은 아직 병합하지 마세요."


class ComposeReadyTest(unittest.TestCase):
    def test_the_message_has_the_fixed_shape(self):
        text = an.compose_ready(NUMBER, TITLE, BODY)
        self.assertEqual(text, "[M105] 병합 부탁 — 병합 알림 자동화 — 워크플로 둘과 파이썬 보조 [대상: 공통]\n\n"
                               "- 앞서 병합된 묶음의 다음 단계다. 변경 등급 T3 — 켬 상태는 off 로 낸다.\n"
                               "- 워크플로 둘: 병합 부탁 알림과 병합완료 확인 알림을 자동으로 보낸다.\n"
                               "- 시험: 새 시험을 더했다\n\n검사: 초록\n\n" + TAIL)
        self.assertEqual(an.message_problem(text), "")
        self.assertEqual(an.ready_tail(NUMBER), TAIL)

    def test_the_title_part_is_cut_at_80_characters(self):
        rest80, rest81 = "가" * 80, "가" * 81
        first80 = an.compose_ready(NUMBER, f"[M105] {rest80}", "").split("\n")[0]
        first81 = an.compose_ready(NUMBER, f"[M105] {rest81}", "").split("\n")[0]
        self.assertEqual(first80, "[M105] 병합 부탁 — " + rest80)
        self.assertEqual(first81, "[M105] 병합 부탁 — " + "가" * 79 + chr(0x2026))

    def test_without_a_body_there_are_no_bullets_and_the_message_is_still_valid(self):
        for body in (None, "", "\n\n", "Co-authored-by: x\n"):
            with self.subTest(repr(body)):
                text = an.compose_ready(NUMBER, TITLE, body)
                self.assertNotIn("\n- ", text)
                self.assertEqual(an.message_problem(text), "")
                self.assertEqual(text.split("\n")[1:], ["", "검사: 초록", "", TAIL])

    def test_the_whole_message_fits_in_800_characters_and_points_are_dropped_from_the_end(self):
        body = "\n".join(f"- 줄{index} " + "나" * 200 for index in range(1, 6))
        long_title = "[M105] " + "다" * 150
        full = an.compose_ready(NUMBER, "[M105] 짧은 제목", body)
        self.assertLessEqual(len(full), an.MESSAGE_LIMIT)
        self.assertEqual(an.message_problem(full), "")
        crowded = an.compose_ready(NUMBER, long_title[:200], body)
        self.assertLessEqual(len(crowded), an.MESSAGE_LIMIT)
        kept = [line for line in crowded.split("\n") if line.startswith("- ")]
        self.assertEqual(kept, [line for line in full.split("\n") if line.startswith("- ")][:len(kept)])      # 남는 줄은 항상 앞쪽 줄이다
        self.assertEqual(an.message_problem(crowded), "")

    def test_the_budget_boundary_is_exact(self):
        """요점 줄을 하나 더 넣어 정확히 상한과 같아지면 넣고, 한 글자라도 넘으면 뺀다(상한을 시험 안에서만 바꿔 경계를 정확히 건드린다)."""
        head = "[M105] 병합 부탁 — 제목"
        points = ["가" * 50, "나" * 60, "다" * 70, "라" * 80]
        body = "\n".join("- " + point for point in points)
        for kept in (1, 2, 3, 4):
            exact = len(an._ready_text(head, points[:kept], NUMBER))
            for limit, expected in ((exact, kept), (exact - 1, kept - 1), (exact + 1, kept)):
                with self.subTest(kept=kept, limit=limit):
                    with mock.patch.object(an, "MESSAGE_LIMIT", limit):
                        text = an.compose_ready(NUMBER, "[M105] 제목", body)
                        self.assertEqual(len([line for line in text.split("\n") if line.startswith("- ")]), expected)
                        self.assertLessEqual(len(text), limit)
                        self.assertEqual(an.message_problem(text), "")

    def test_five_full_length_points_under_the_real_limit(self):
        """실제 상한(800자)에서 제목 80자 + 요점 5줄(줄당 120자)은 정확히 계산한 대로 들어가거나(들어가면 5줄) 마지막 줄부터 빠진다."""
        body = "\n".join("- " + chr(0xAC00 + index) * 120 for index in range(5))
        text = an.compose_ready(NUMBER, "[M105] " + "제" * 80, body)
        points = [line for line in text.split("\n") if line.startswith("- ")]
        full = len(an._ready_text(text.split("\n")[0], [chr(0xAC00 + index) * 120 for index in range(5)], NUMBER))
        self.assertEqual(len(points), 5 if full <= an.MESSAGE_LIMIT else 4)
        self.assertLessEqual(len(text), an.MESSAGE_LIMIT)

    def test_a_title_that_cannot_be_sent_stops_the_message(self):
        bad = {"mention": "[M105] 담당 " + AT + "someone", "address": "[M105] " + SCHEME + "evil.example", "secret": "[M105] 키 " + nh.TOKEN, "control": "[M105] 제목\x01숨김",
               "empty": "[M105] ", "blank": "[M105]    ", "long": "[M105] " + "가" * 194, "invisible": "[M105] 제목" + chr(0x200B)}
        for label, title in bad.items():
            with self.subTest(label):
                with self.assertRaises(an.Skip) as caught:
                    an.compose_ready(NUMBER, title, BODY)
                self.assertEqual(caught.exception.code, "title_problem")

    def test_a_title_of_200_characters_is_allowed_and_201_is_not(self):
        self.assertEqual(an.message_problem(an.compose_ready(NUMBER, "[M105] " + "가" * 193, "")), "")
        with self.assertRaises(an.Skip):
            an.compose_ready(NUMBER, "[M105] " + "가" * 194, "")

    def test_a_title_must_start_with_the_same_number(self):
        for title in ("그냥 제목", "[M106] 다른 번호", "[M105]붙어 있음", "[m105] 소문자", " [M105] 앞 공백", "[M0105] 네 자리 앞 0", "[M1050] 다른 번호", "[R-105] 요청 번호", None, 5):
            with self.subTest(str(title)):
                with self.assertRaises(an.Skip) as caught:
                    an.compose_ready(NUMBER, title, BODY)
                self.assertEqual(caught.exception.code, "title_shape")

    def test_a_number_that_is_not_a_merge_notice_number_is_refused(self):
        for number in ("M000", "M0105", "M10", "P105", "105", "m105", "M12345", "", None):
            with self.subTest(str(number)):
                with self.assertRaises(an.Skip):
                    an.compose_ready(number, f"[{number}] 제목", BODY)

    def test_tildes_in_the_title_become_en_dashes_and_never_reach_the_message(self):
        text = an.compose_ready(NUMBER, "[M105] 약 10" + TILDE + "20개 " + chr(0xFF5E), "- 본문 " + TILDE + " 줄")
        self.assertNotIn(TILDE, text)
        self.assertNotIn(chr(0xFF5E), text)
        self.assertIn("10" + chr(0x2013) + "20개", text)

    def test_markdown_and_backticks_are_stripped_from_the_title(self):
        text = an.compose_ready(NUMBER, "[M105] **굵게** `코드` 제목", "")
        self.assertEqual(text.split("\n")[0], "[M105] 병합 부탁 — 굵게 코드 제목")

    def test_a_body_with_bad_lines_still_gives_a_valid_message(self):
        body = "- " + SCHEME + "evil.example\n- 담당 " + AT + "a\n- 좋은 줄\n- 비밀 " + nh.TOKEN
        text = an.compose_ready(NUMBER, TITLE, body)
        self.assertEqual(an.message_problem(text), "")
        self.assertIn("- 좋은 줄", text)
        for needle in ("evil", AT, nh.TOKEN):
            self.assertNotIn(needle, text)


class ComposeConfirmTest(unittest.TestCase):
    def test_ok_is_one_line(self):
        self.assertEqual(an.compose_confirm(NUMBER, []), "[M105] 병합완료 확인 - 정상")
        self.assertEqual(an.compose_confirm("M1234", []), "[M1234] 병합완료 확인 - 정상")

    def test_ok_with_a_note_has_a_second_line(self):
        text = an.compose_confirm(NUMBER, [], "참고: 병합 커밋의 부모가 2개입니다(병합 커밋 방식)")
        self.assertEqual(text.split("\n"), ["[M105] 병합완료 확인 - 정상", "참고: 병합 커밋의 부모가 2개입니다(병합 커밋 방식)"])
        self.assertEqual(an.message_problem(text), "")

    def test_bad_is_the_title_plus_one_reason_line_within_100_characters(self):
        text = an.compose_confirm(NUMBER, ["이유 하나"])
        self.assertEqual(text, "[M105] 병합완료 확인 - 이상\n이유 하나")
        many = an.compose_confirm(NUMBER, ["첫 이유", "둘째", "셋째"])
        self.assertEqual(many.split("\n")[1], "첫 이유 (외 2건)")
        long = an.compose_confirm(NUMBER, ["가" * 300, "x"])
        self.assertEqual(len(long.split("\n")[1]), an.REASON_LIMIT)
        self.assertEqual(an.message_problem(long), "")

    def test_a_bad_number_is_refused(self):
        for number in ("M000", "P105", "105", "M0105", "", None):
            with self.subTest(str(number)):
                with self.assertRaises(ValueError):
                    an.compose_confirm(number, [])


class MessageProblemTest(unittest.TestCase):
    def test_valid_messages_pass(self):
        for text in (an.compose_ready(NUMBER, TITLE, BODY), an.compose_ready("M1234", "[M1234] 제목", ""), an.compose_confirm(NUMBER, []), an.compose_confirm(NUMBER, ["이유"])):
            self.assertEqual(an.message_problem(text), "", text)

    def test_every_broken_variant_is_refused(self):
        ready = an.compose_ready(NUMBER, TITLE, BODY)
        lines = ready.split("\n")
        broken = {
            "empty": "", "blank": "  \n ", "none": None, "number": 5,
            "too long": ready + "\n" + "가" * 800,
            "trailing newline": ready + "\n",
            "leading newline": "\n" + ready,
            "wrong first line dash": ready.replace("병합 부탁 — ", "병합 부탁 - ", 1),
            "no first line text": "[M105] 병합 부탁 — \n\n검사: 초록\n\n" + TAIL,
            "other label": ready.replace("병합 부탁", "병합 요청", 1),
            "bad number": ready.replace("[M105]", "[M000]", 1),
            "leading zero number": ready.replace("[M105]", "[M0105]", 1).replace("[M105] 인", "[M0105] 인"),
            "no check line": "\n".join(line for line in lines if line != "검사: 초록"),
            "check line changed": ready.replace("검사: 초록", "검사: 빨강"),
            "tail changed": ready.replace("하나만", "둘만"),
            "tail number changed": ready.replace("[M105] 인 PR", "[M106] 인 PR"),
            "tail missing": "\n".join(lines[:-2]),
            "extra line after tail": ready + "\n추가",
            "point without dash": "\n".join(lines[:2] + ["줄 하나"] + lines[2:]),
            "six points": "\n".join(lines[:2] + ["- 여섯째"] * 4 + lines[2:]),
            "point too long": "\n".join(lines[:2] + ["- " + "가" * 130] + lines[2:]),
            "empty point": "\n".join(lines[:2] + ["- "] + lines[2:]),
            "mention": ready.replace("시험: 새 시험을", "시험: " + AT + "누구 새 시험을"),
            "address": ready.replace("시험: 새 시험을", "시험: " + SCHEME + "evil.example 새 시험을"),
            "secret": ready.replace("시험: 새 시험을", "시험: " + nh.TOKEN + " 새 시험을"),
            "tilde": ready.replace("시험: 새 시험을", "시험: 10" + TILDE + "20 새 시험을"),
            "control": ready.replace("시험: 새 시험을", "시험:\x01 새 시험을"),
            "carriage return": ready.replace("\n", "\r\n"),
            "zero width": ready.replace("시험:", "시" + chr(0x200B) + "험:"),
            "confirm bad without reason": "[M105] 병합완료 확인 - 이상",
            "confirm three lines": "[M105] 병합완료 확인 - 정상\n하나\n둘",
            "confirm blank second line": "[M105] 병합완료 확인 - 정상\n",
            "confirm unknown result": "[M105] 병합완료 확인 - 보류",
            "confirm wrong dash": "[M105] 병합완료 확인 — 정상",
            "confirm bad number": "[M000] 병합완료 확인 - 정상",
            "plain text": "그냥 글",
            "ready-looking confirm": "[M105] 병합 부탁 — 제목",
        }
        for label, text in broken.items():
            with self.subTest(label):
                self.assertNotEqual(an.message_problem(text), "", repr(text)[:80])


# ----------------------------------------------------------------------------
# 입력(env)
# ----------------------------------------------------------------------------
class ReadInputsTest(unittest.TestCase):
    def test_valid_values_are_read(self):
        found = an.read_inputs(ready_env(), an.READY)
        self.assertEqual(found, an.Inputs(REPO, RUN_ID, BRANCH, SHA, "push", "success", REPO, "main"))
        again = an.read_inputs(confirm_env(), an.CONFIRM)
        self.assertEqual((again.branch, again.default_branch), ("main", "main"))

    def test_the_repository_comparison_ignores_case(self):
        self.assertEqual(an.read_inputs(ready_env(NOTICE_RUN_REPO="OCTO/Blog"), an.READY).run_repo, "OCTO/Blog")

    def test_odd_values_stop_with_input_shape(self):
        zero = "0" * 40
        cases = [("GITHUB_REPOSITORY", ""), ("GITHUB_REPOSITORY", "no-slash"), ("GITHUB_REPOSITORY", "a/b c"), ("GITHUB_REPOSITORY", REPO + "\n"), ("GITHUB_REPOSITORY", "a/b/c"),
                 ("NOTICE_RUN_SHA", ""), ("NOTICE_RUN_SHA", zero), ("NOTICE_RUN_SHA", "A" * 40), ("NOTICE_RUN_SHA", "a" * 39), ("NOTICE_RUN_SHA", "a" * 41), ("NOTICE_RUN_SHA", SHA + "\n"),
                 ("NOTICE_RUN_SHA", "g" + "a" * 39), ("NOTICE_RUN_ID", ""), ("NOTICE_RUN_ID", "0"), ("NOTICE_RUN_ID", "-5"), ("NOTICE_RUN_ID", "12a"), ("NOTICE_RUN_ID", "1" * 19),
                 ("NOTICE_RUN_ID", "٣٣"), ("NOTICE_RUN_CONCLUSION", ""), ("NOTICE_RUN_CONCLUSION", "SUCCESS"), ("NOTICE_RUN_CONCLUSION", "success\n"), ("NOTICE_RUN_CONCLUSION", "ok"),
                 ("NOTICE_DEFAULT_BRANCH", ""), ("NOTICE_DEFAULT_BRANCH", "main;x"), ("NOTICE_DEFAULT_BRANCH", "ma in"), ("NOTICE_DEFAULT_BRANCH", "m" * 101)]
        for name, value in cases:
            with self.subTest(f"{name}={value[:12]!r}"):
                with self.assertRaises(an.Skip) as caught:
                    an.read_inputs(ready_env(**{name: value}), an.READY)
                self.assertEqual(caught.exception.code, "input_shape")

    def test_the_merge_branch_must_match_the_rule_as_a_whole(self):
        bad = ["ai/claude/NO-MERGE-operator-requests", "ai/claude/M04-short", "ai/claude/M005-", "ai/claude/M005-한글", "ai/claude/M005-x;touch", "ai/claude/M005-x y", "ai/claude/M005-x/y",
               "xai/claude/M005-x", "ai/claude/M005-x\n", "ai/claude/M00005-x", "ai/codex/M005-x", "main", "", "ai/claude/M005-" + "a" * 81]
        for branch in bad:
            with self.subTest(branch[:40]):
                with self.assertRaises(an.Skip) as caught:
                    an.read_inputs(ready_env(NOTICE_RUN_BRANCH=branch), an.READY)
                self.assertEqual(caught.exception.code, "input_shape")
        for branch in ("ai/claude/M005-x", "ai/claude/M1234-a.b_c-d", "ai/claude/M005-" + "a" * 80):
            self.assertEqual(an.read_inputs(ready_env(NOTICE_RUN_BRANCH=branch), an.READY).branch, branch)

    def test_the_confirmation_branch_must_be_the_default_branch(self):
        for branch in (BRANCH, "feature", "main2", "Main", "main\n", ""):
            with self.subTest(branch):
                with self.assertRaises(an.Skip) as caught:
                    an.read_inputs(ready_env(NOTICE_RUN_BRANCH=branch), an.CONFIRM)
                self.assertEqual(caught.exception.code, "input_shape")
        with self.assertRaises(an.Skip):
            an.read_inputs(confirm_env(NOTICE_DEFAULT_BRANCH="develop"), an.CONFIRM)          # 기본 가지가 main 이 아니면 main 의 실행은 해당 없다

    def test_other_events_and_forks_are_not_notified(self):
        for event in ("pull_request", "workflow_dispatch", "schedule", "workflow_run", "push\n", "", "PUSH"):
            with self.subTest(event):
                with self.assertRaises(an.Skip) as caught:
                    an.read_inputs(ready_env(NOTICE_RUN_EVENT=event), an.READY)
                self.assertIn(caught.exception.code, ("not_push", "input_shape"))
        for run_repo in ("", "other/blog", "octo/blog2", "octo/blo", "evil/blog"):
            with self.subTest(run_repo):
                with self.assertRaises(an.Skip) as caught:
                    an.read_inputs(ready_env(NOTICE_RUN_REPO=run_repo), an.READY)
                self.assertEqual(caught.exception.code, "fork")

    def test_missing_names_are_odd_values(self):
        env = ready_env()
        del env["NOTICE_RUN_SHA"]
        with self.assertRaises(an.Skip):
            an.read_inputs(env, an.READY)


# ----------------------------------------------------------------------------
# 검사 목록 판정
# ----------------------------------------------------------------------------
class RunsStateTest(unittest.TestCase):
    def test_all_green_with_guardrails_is_ok(self):
        self.assertEqual(an.runs_state(good_runs(), RUN_ID), "ok")

    def test_anything_not_success_is_failed_even_skipped_and_neutral(self):
        for conclusion in ("failure", "cancelled", "skipped", "neutral", "timed_out", "action_required", "stale", "startup_failure", None, ""):
            with self.subTest(str(conclusion)):
                runs = good_runs() + [run_item(99, ".github/workflows/x.yml", conclusion=conclusion)]
                self.assertEqual(an.runs_state(runs, RUN_ID), "failed")

    def test_unfinished_runs_are_pending_and_a_failure_beats_pending(self):
        for status in ("queued", "in_progress", "waiting", "requested", "pending", None, ""):
            with self.subTest(str(status)):
                runs = good_runs() + [run_item(99, ".github/workflows/x.yml", status=status, conclusion=None)]
                self.assertEqual(an.runs_state(runs, RUN_ID), "pending")
        both = good_runs() + [run_item(98, status="in_progress", conclusion=None), run_item(99, conclusion="failure")]
        self.assertEqual(an.runs_state(both, RUN_ID), "failed")

    def test_guardrails_must_be_present_and_identified_by_the_file_before_the_at_sign(self):
        self.assertEqual(an.runs_state([], RUN_ID), "missing")
        self.assertEqual(an.runs_state([run_item(12, ".github/workflows/ai-request.yml")], RUN_ID), "missing")
        self.assertEqual(an.runs_state([run_item(12, ".github/workflows/guardrails.yml.bak")], RUN_ID), "missing")
        self.assertEqual(an.runs_state([run_item(12, "other/.github/workflows/guardrails.yml")], RUN_ID), "missing")
        plain = {"id": 5, "path": ".github/workflows/guardrails.yml", "status": "completed", "conclusion": "success"}
        self.assertEqual(an.runs_state([plain], RUN_ID), "ok")                       # `@가지` 꼬리가 없는 꼴도 같은 파일이다

    def test_the_run_that_woke_us_up_is_excluded_whatever_the_list_says_about_it(self):
        for status, conclusion in (("in_progress", None), ("completed", "failure"), ("queued", None)):
            runs = [run_item(11), run_item(RUN_ID, ".github/workflows/auto-pr.yml", status=status, conclusion=conclusion)]
            self.assertEqual(an.runs_state(runs, RUN_ID), "ok", (status, conclusion))
        self.assertEqual(an.runs_state([run_item(11), run_item(RUN_ID + 1, ".github/workflows/auto-pr.yml", status="in_progress", conclusion=None)], RUN_ID), "pending")

    def test_a_malformed_item_is_a_shape_problem(self):
        for item in (None, "x", 5, [], ):
            with self.subTest(repr(item)):
                with self.assertRaises(an.Skip) as caught:
                    an.runs_state(good_runs() + [item], RUN_ID)
                self.assertEqual(caught.exception.code, "api_shape")


# ----------------------------------------------------------------------------
# 병합 부탁 판정
# ----------------------------------------------------------------------------
class EvaluateReadyTest(unittest.TestCase):
    def evaluate(self, routes=None, sleep=no_sleep, **env):
        api = FakeApi(ready_routes() if routes is None else routes)
        verdict = an.evaluate_ready(an.read_inputs(ready_env(**env), an.READY), an.Reader(api), sleep)
        return verdict, api

    def skipped(self, routes=None, sleep=no_sleep, **env):
        with self.assertRaises(an.Skip) as caught:
            self.evaluate(routes, sleep, **env)
        return caught.exception.code

    def test_the_happy_path_makes_the_message_and_only_reads(self):
        verdict, api = self.evaluate()
        self.assertEqual(verdict.text, an.compose_ready(NUMBER, TITLE, BODY))
        self.assertEqual(api.methods(), {"GET"})
        self.assertEqual(api.calls[0][1:3], ("/pulls", {"state": "open", "head": "octo:" + BRANCH, "base": "main", "per_page": 5}))
        self.assertEqual(api.calls[1][1:3], ("/actions/runs", {"branch": BRANCH, "head_sha": SHA, "event": "push", "per_page": 100}))
        self.assertEqual(len(api.calls), 2)
        self.assertTrue(all(call[3] is None for call in api.calls))                       # 보내는 본문이 없다
        self.assertEqual(verdict.notes[0], f"열린 PR #{PR_NUMBER} 하나이고 머리 커밋이 이 실행의 커밋과 같음")      # 요약에 남는 확인 문장은 고정 문장과 PR 번호뿐이다
        self.assertTrue(all(TITLE not in note and AT not in note for note in verdict.notes))

    def test_a_run_that_did_not_succeed_is_not_notified_and_nothing_is_read(self):
        for conclusion in ("failure", "cancelled", "timed_out", "skipped", "neutral", "action_required", "stale", "startup_failure"):
            with self.subTest(conclusion):
                api = FakeApi(ready_routes())
                with self.assertRaises(an.Skip) as caught:
                    an.evaluate_ready(an.read_inputs(ready_env(NOTICE_RUN_CONCLUSION=conclusion), an.READY), an.Reader(api), no_sleep)
                self.assertEqual((caught.exception.code, api.calls), ("run_not_success", []))

    def test_no_open_pull_request_or_more_than_one(self):
        self.assertEqual(self.skipped(ready_routes(prs=[])), "no_pr")
        self.assertEqual(self.skipped(ready_routes(prs=[pr_item(), pr_item(number=249)])), "many_pr")

    def test_the_pull_request_must_match_this_run(self):
        cases = {"other head commit": pr_item(head={"ref": BRANCH, "sha": OTHER_SHA, "repo": {"full_name": REPO}}),
                 "other head branch": pr_item(head={"ref": "ai/claude/M105-other", "sha": SHA, "repo": {"full_name": REPO}}),
                 "fork head": pr_item(head={"ref": BRANCH, "sha": SHA, "repo": {"full_name": "evil/blog"}}),
                 "deleted fork": pr_item(head={"ref": BRANCH, "sha": SHA, "repo": None}),
                 "other base": pr_item(base={"ref": "develop"}),
                 "closed": pr_item(state="closed")}
        for label, pr in cases.items():
            with self.subTest(label):
                self.assertEqual(self.skipped(ready_routes(prs=[pr])), "pr_mismatch")
        self.assertEqual(self.skipped(ready_routes(prs=[pr_item(draft=True)])), "pr_draft")

    def test_a_missing_draft_field_is_not_a_draft(self):
        pr = pr_item()
        del pr["draft"]
        self.assertEqual(self.evaluate(ready_routes(prs=[pr]))[0].text, an.compose_ready(NUMBER, TITLE, BODY))

    def test_the_title_rules_apply_to_the_pull_request_title(self):
        self.assertEqual(self.skipped(ready_routes(prs=[pr_item(title="제목")])), "title_shape")
        self.assertEqual(self.skipped(ready_routes(prs=[pr_item(title="[M106] 다른 번호")])), "title_shape")
        self.assertEqual(self.skipped(ready_routes(prs=[pr_item(title=None)])), "title_shape")
        for title in ("[M105] 담당 " + AT + "x", "[M105] " + SCHEME + "evil.example", "[M105] 키 " + nh.TOKEN, "[M105] " + "가" * 300, "[M105] "):
            with self.subTest(title[:20]):
                self.assertEqual(self.skipped(ready_routes(prs=[pr_item(title=title)])), "title_problem")

    def test_a_missing_or_odd_body_gives_a_message_without_points(self):
        for body in (None, "", 5, ["x"]):
            verdict = self.evaluate(ready_routes(prs=[pr_item(body=body)]))[0]
            self.assertEqual(an.message_problem(verdict.text), "")

    def test_the_checks_must_all_be_finished_and_green(self):
        self.assertEqual(self.skipped(ready_routes(runs=good_runs() + [run_item(90, ".github/workflows/telegram-inbox.yml", conclusion="failure")])), "checks_failed")
        self.assertEqual(self.skipped(ready_routes(runs=good_runs() + [run_item(90, ".github/workflows/ai-request.yml", conclusion="skipped")])), "checks_failed")
        self.assertEqual(self.skipped(ready_routes(runs=[run_item(12, ".github/workflows/ai-request.yml")])), "checks_missing")
        self.assertEqual(self.skipped(ready_routes(runs=[])), "checks_missing")

    def test_unfinished_checks_are_waited_for_at_most_three_more_times(self):
        pending = {"workflow_runs": good_runs() + [run_item(90, ".github/workflows/ai-request.yml", status="in_progress", conclusion=None)]}
        sleeps = []
        api = FakeApi({"/pulls": [pr_item()], "/actions/runs": pending})
        with self.assertRaises(an.Skip) as caught:
            an.evaluate_ready(an.read_inputs(ready_env(), an.READY), an.Reader(api), sleeps.append)
        self.assertEqual(caught.exception.code, "checks_pending")
        self.assertEqual(sleeps, [an.CHECK_WAIT] * an.CHECK_RETRIES)
        self.assertEqual(api.paths().count("/actions/runs"), an.CHECK_RETRIES + 1)
        self.assertEqual((an.CHECK_WAIT, an.CHECK_RETRIES), (20, 3))

    def test_a_check_that_finishes_while_waiting_lets_the_message_through(self):
        done = {"workflow_runs": good_runs()}
        pending = {"workflow_runs": good_runs() + [run_item(90, ".github/workflows/ai-request.yml", status="queued", conclusion=None)]}
        sleeps = []
        api = FakeApi({"/pulls": [pr_item()], "/actions/runs": Seq(pending, pending, done)})
        verdict = an.evaluate_ready(an.read_inputs(ready_env(), an.READY), an.Reader(api), sleeps.append)
        self.assertEqual(verdict.text, an.compose_ready(NUMBER, TITLE, BODY))
        self.assertEqual(sleeps, [20, 20])

    def test_a_failure_while_waiting_stops_at_once(self):
        sleeps = []
        api = FakeApi({"/pulls": [pr_item()], "/actions/runs": Seq({"workflow_runs": good_runs() + [run_item(90, status="in_progress", conclusion=None)]},
                                                                    {"workflow_runs": good_runs() + [run_item(90, conclusion="failure")]})})
        with self.assertRaises(an.Skip) as caught:
            an.evaluate_ready(an.read_inputs(ready_env(), an.READY), an.Reader(api), sleeps.append)
        self.assertEqual((caught.exception.code, sleeps), ("checks_failed", [20]))

    def test_unreadable_answers_are_errors_not_notices(self):
        self.assertEqual(self.skipped({"/pulls": ol.GitHubError("HTTP 500", 500), "/actions/runs": {"workflow_runs": []}}), "api_error")
        self.assertEqual(self.skipped({"/pulls": [pr_item()], "/actions/runs": ol.GitHubError("연결 오류(OSError)")}), "api_error")
        self.assertEqual(self.skipped({"/pulls": [pr_item()]}), "api_error")                      # 없는 경로는 404 → 읽기 실패

    def test_wrongly_shaped_answers_are_shape_problems(self):
        shapes = [({"/pulls": {"x": 1}, "/actions/runs": {}}, "api_shape"), ({"/pulls": None, "/actions/runs": {}}, "api_shape"), ({"/pulls": ["x"], "/actions/runs": {}}, "api_shape"),
                  ({"/pulls": [{"number": PR_NUMBER}], "/actions/runs": {}}, "api_shape"), ({"/pulls": [pr_item(number="x")], "/actions/runs": {}}, "api_shape"),
                  ({"/pulls": [pr_item(number=0)], "/actions/runs": {}}, "api_shape"), ({"/pulls": [pr_item(number=True)], "/actions/runs": {}}, "api_shape"),
                  ({"/pulls": [pr_item(head=None)], "/actions/runs": {}}, "api_shape"), ({"/pulls": [pr_item()], "/actions/runs": []}, "api_shape"),
                  ({"/pulls": [pr_item()], "/actions/runs": {"workflow_runs": "x"}}, "api_shape"), ({"/pulls": [pr_item()], "/actions/runs": {"workflow_runs": [5]}}, "api_shape")]
        for routes, code in shapes:
            with self.subTest(str(routes)[:60]):
                self.assertEqual(self.skipped(routes), code)


# ----------------------------------------------------------------------------
# 병합완료 확인 판정
# ----------------------------------------------------------------------------
class EvaluateConfirmTest(unittest.TestCase):
    def evaluate(self, routes=None, **env):
        api = FakeApi(confirm_routes() if routes is None else routes)
        verdict = an.evaluate_confirm(an.read_inputs(confirm_env(**env), an.CONFIRM), an.Reader(api))
        return verdict, api

    def skipped(self, routes=None, **env):
        with self.assertRaises(an.Skip) as caught:
            self.evaluate(routes, **env)
        return caught.exception.code

    def test_equal_trees_are_ok_and_only_reads_happen(self):
        verdict, api = self.evaluate()
        self.assertEqual(verdict.text, "[M105] 병합완료 확인 - 정상")
        self.assertEqual(api.methods(), {"GET"})
        self.assertEqual(api.paths(), [f"/commits/{SHA}", f"/commits/{SHA}/pulls", f"/pulls/{PR_NUMBER}", f"/commits/{HEAD_SHA}"])
        self.assertTrue(any("트리 일치" in note for note in verdict.notes))
        self.assertTrue(any("부모 1개(squash)" in note for note in verdict.notes))

    def test_two_parents_are_allowed_and_written_in_the_message(self):
        verdict, _ = self.evaluate(confirm_routes({f"/commits/{SHA}": commit_obj(parents=(OTHER_SHA, HEAD_SHA))}))
        self.assertEqual(verdict.text.split("\n"), ["[M105] 병합완료 확인 - 정상", "참고: 병합 커밋의 부모가 2개입니다(병합 커밋 방식)"])

    def test_zero_or_three_parents_are_bad(self):
        for parents in ((), (OTHER_SHA, HEAD_SHA, TREE)):
            with self.subTest(len(parents)):
                verdict, _ = self.evaluate(confirm_routes({f"/commits/{SHA}": commit_obj(parents=parents)}))
                self.assertEqual(verdict.text.split("\n")[0], "[M105] 병합완료 확인 - 이상")
                self.assertIn(f"부모가 {len(parents)}개입니다", verdict.text)

    def test_the_main_check_conclusion_decides_ok_or_bad(self):
        for conclusion in ("failure", "timed_out", "action_required", "neutral", "stale", "startup_failure"):
            with self.subTest(conclusion):
                verdict, _ = self.evaluate(NOTICE_RUN_CONCLUSION=conclusion)
                self.assertEqual(verdict.text.split("\n")[0], "[M105] 병합완료 확인 - 이상")
                self.assertIn(f"결론: {conclusion}", verdict.text)
        for conclusion in ("cancelled", "skipped"):
            with self.subTest(conclusion):
                api = FakeApi(confirm_routes())
                with self.assertRaises(an.Skip) as caught:
                    an.evaluate_confirm(an.read_inputs(confirm_env(NOTICE_RUN_CONCLUSION=conclusion), an.CONFIRM), an.Reader(api))
                self.assertEqual((caught.exception.code, api.calls), ("run_cancelled", []))     # 판정을 미루고 GitHub 도 부르지 않는다

    def test_a_commit_that_is_not_a_merge_commit_is_skipped_after_one_read(self):
        for message in ("글 자동 게시 2026-11-23", "[R-001] 요청", "[M105]붙어 있음", "[m105] x", " [M105] x", "", "Merge pull request #5 from x/y\n\n[M105] 제목"):
            with self.subTest(message[:20]):
                api = FakeApi(confirm_routes({f"/commits/{SHA}": commit_obj(message=message)}))
                with self.assertRaises(an.Skip) as caught:
                    an.evaluate_confirm(an.read_inputs(confirm_env(), an.CONFIRM), an.Reader(api))
                self.assertEqual((caught.exception.code, api.paths()), ("not_merge_commit", [f"/commits/{SHA}"]))

    def test_a_merge_number_that_is_not_a_notice_number_is_refused(self):
        for message in ("[M000] x", "[M0105] x"):
            with self.subTest(message):
                self.assertEqual(self.skipped(confirm_routes({f"/commits/{SHA}": commit_obj(message=message)})), "title_shape")

    def test_the_commit_title_may_use_crlf(self):
        verdict, _ = self.evaluate(confirm_routes({f"/commits/{SHA}": commit_obj(message="[M105] 제목 (#248)\r\n\r\n본문")}))
        self.assertEqual(verdict.text, "[M105] 병합완료 확인 - 정상")

    def test_exactly_one_merged_pull_request_must_be_linked(self):
        cases = {"none": [], "unmerged": [pull_item(merged=False)], "other merge commit": [pull_item(merge_sha=OTHER_SHA)], "two": [pull_item(), pull_item(number=249)],
                 "junk": ["x", 5, None]}
        for label, pulls in cases.items():
            with self.subTest(label):
                self.assertEqual(self.skipped(confirm_routes({f"/commits/{SHA}/pulls": pulls})), "pr_count")
        one_extra = [pull_item(), pull_item(number=250, merged=False), pull_item(number=251, merge_sha=OTHER_SHA)]
        self.assertEqual(self.evaluate(confirm_routes({f"/commits/{SHA}/pulls": one_extra}))[0].text, "[M105] 병합완료 확인 - 정상")      # 병합된 것이 하나면 다른 항목은 무시한다

    def test_the_pull_request_details_must_agree(self):
        cases = {"not merged": (pr_detail(merged=False), "PR 의 병합 커밋이 이 커밋과 다릅니다"),
                 "other merge commit": (pr_detail(merge_commit_sha=OTHER_SHA), "PR 의 병합 커밋이 이 커밋과 다릅니다"),
                 "other base": (pr_detail(base={"ref": "develop"}), "대상 가지가 기본 가지가 아닙니다"),
                 "other number": (pr_detail(title="[M106] 다른 번호"), "커밋 제목과 PR 제목의 번호가 다릅니다"),
                 "no number": (pr_detail(title="제목"), "커밋 제목과 PR 제목의 번호가 다릅니다")}
        for label, (detail, reason) in cases.items():
            with self.subTest(label):
                verdict, _ = self.evaluate(confirm_routes({f"/pulls/{PR_NUMBER}": detail}))
                self.assertEqual(verdict.text.split("\n")[0], "[M105] 병합완료 확인 - 이상")
                self.assertIn(reason, verdict.text)

    def test_different_trees_with_the_same_changed_files_are_ok_and_the_tree_check_is_skipped(self):
        routes = confirm_routes({f"/commits/{HEAD_SHA}": commit_obj(HEAD_SHA, "x", (OTHER_SHA,), OTHER_TREE),
                                   (f"/pulls/{PR_NUMBER}/files", 1): [{"filename": "a.py"}, {"filename": "b.md"}]})
        verdict, api = self.evaluate(routes)
        self.assertEqual(verdict.text, "[M105] 병합완료 확인 - 정상")
        self.assertTrue(any("트리 비교 생략(main 이 앞섬)" in note for note in verdict.notes))
        self.assertEqual(api.methods(), {"GET"})
        self.assertIn(f"/pulls/{PR_NUMBER}/files", api.paths())

    def test_different_trees_with_different_files_are_bad(self):
        routes = confirm_routes({f"/commits/{HEAD_SHA}": commit_obj(HEAD_SHA, "x", (OTHER_SHA,), OTHER_TREE),
                                   (f"/pulls/{PR_NUMBER}/files", 1): [{"filename": "a.py"}, {"filename": "c.md"}]})
        verdict, _ = self.evaluate(routes)
        self.assertEqual(verdict.text.split("\n"), ["[M105] 병합완료 확인 - 이상", "변경 파일이 PR 과 다릅니다(PR 2개, 병합 2개)"])

    def test_extra_files_in_the_merge_commit_are_bad(self):
        routes = confirm_routes({f"/commits/{SHA}": commit_obj(files=("a.py", "b.md", "c.txt")), f"/commits/{HEAD_SHA}": commit_obj(HEAD_SHA, "x", (OTHER_SHA,), OTHER_TREE),
                                   (f"/pulls/{PR_NUMBER}/files", 1): [{"filename": "a.py"}, {"filename": "b.md"}]})
        verdict, _ = self.evaluate(routes)
        self.assertIn("변경 파일이 PR 과 다릅니다(PR 2개, 병합 3개)", verdict.text)

    def test_the_file_list_is_read_page_by_page_up_to_three_pages(self):
        names = [f"f{index}.py" for index in range(250)]
        routes = confirm_routes({f"/commits/{SHA}": commit_obj(files=tuple(names)), f"/pulls/{PR_NUMBER}": pr_detail(changed_files=250),
                                   f"/commits/{HEAD_SHA}": commit_obj(HEAD_SHA, "x", (OTHER_SHA,), OTHER_TREE),
                                   (f"/pulls/{PR_NUMBER}/files", 1): [{"filename": n} for n in names[:100]], (f"/pulls/{PR_NUMBER}/files", 2): [{"filename": n} for n in names[100:200]],
                                   (f"/pulls/{PR_NUMBER}/files", 3): [{"filename": n} for n in names[200:]]})
        verdict, api = self.evaluate(routes)
        self.assertEqual(verdict.text, "[M105] 병합완료 확인 - 정상")
        self.assertEqual([call[2].get("page") for call in api.calls if call[1].endswith("/files")], [1, 2, 3])

    def test_more_than_300_changed_files_cannot_be_compared(self):
        routes = confirm_routes({f"/pulls/{PR_NUMBER}": pr_detail(changed_files=301), f"/commits/{HEAD_SHA}": commit_obj(HEAD_SHA, "x", (OTHER_SHA,), OTHER_TREE)})
        self.assertEqual(self.skipped(routes), "too_large")
        for changed in (0, -1):
            routes = confirm_routes({f"/pulls/{PR_NUMBER}": pr_detail(changed_files=changed), f"/commits/{HEAD_SHA}": commit_obj(HEAD_SHA, "x", (OTHER_SHA,), OTHER_TREE)})
            self.assertEqual(self.skipped(routes), "too_large")

    def test_a_file_count_that_disagrees_with_the_list_is_a_shape_problem(self):
        routes = confirm_routes({f"/pulls/{PR_NUMBER}": pr_detail(changed_files=5), f"/commits/{HEAD_SHA}": commit_obj(HEAD_SHA, "x", (OTHER_SHA,), OTHER_TREE),
                                   (f"/pulls/{PR_NUMBER}/files", 1): [{"filename": "a.py"}, {"filename": "b.md"}]})
        self.assertEqual(self.skipped(routes), "api_shape")

    def test_equal_trees_need_no_file_lists(self):
        _, api = self.evaluate()
        self.assertNotIn(f"/pulls/{PR_NUMBER}/files", api.paths())

    def test_several_problems_are_summarised_in_one_reason_line(self):
        routes = confirm_routes({f"/commits/{SHA}": commit_obj(parents=()), f"/pulls/{PR_NUMBER}": pr_detail(merged=False)})
        verdict, _ = self.evaluate(routes, NOTICE_RUN_CONCLUSION="failure")
        lines = verdict.text.split("\n")
        self.assertEqual(len(lines), 2)
        self.assertRegex(lines[1], r"\(외 [0-9]+건\)$")
        self.assertLessEqual(len(lines[1]), an.REASON_LIMIT)

    def test_unreadable_or_wrongly_shaped_answers_are_not_notices(self):
        self.assertEqual(self.skipped({}), "api_error")
        self.assertEqual(self.skipped(confirm_routes({f"/commits/{SHA}": ol.GitHubError("HTTP 500", 500)})), "api_error")
        self.assertEqual(self.skipped(confirm_routes({f"/commits/{SHA}/pulls": ol.GitHubError("HTTP 403", 403)})), "api_error")
        self.assertEqual(self.skipped(confirm_routes({f"/commits/{HEAD_SHA}": ol.GitHubError("연결 오류")})), "api_error")
        shapes = [{f"/commits/{SHA}": None}, {f"/commits/{SHA}": {"commit": None}}, {f"/commits/{SHA}": {"commit": {"message": "[M105] x"}}},
                  {f"/commits/{SHA}": dict(commit_obj(), parents=None)}, {f"/commits/{SHA}/pulls": {"x": 1}}, {f"/pulls/{PR_NUMBER}": None},
                  {f"/pulls/{PR_NUMBER}": pr_detail(head=None)}, {f"/pulls/{PR_NUMBER}": pr_detail(head={"sha": "nope"})}, {f"/pulls/{PR_NUMBER}": pr_detail(base=None)},
                  {f"/commits/{HEAD_SHA}": {"commit": {"tree": {}}}}, {f"/commits/{HEAD_SHA}": {"commit": {"tree": {"sha": "nope"}}}},
                  {f"/commits/{SHA}": dict(commit_obj(), commit={"message": "[M105] x", "tree": {"sha": "nope"}})},
                  {f"/pulls/{PR_NUMBER}": pr_detail(changed_files="2"), f"/commits/{HEAD_SHA}": commit_obj(HEAD_SHA, "x", (OTHER_SHA,), OTHER_TREE)},
                  {f"/commits/{SHA}": commit_obj(files=None), f"/commits/{HEAD_SHA}": commit_obj(HEAD_SHA, "x", (OTHER_SHA,), OTHER_TREE)}]
        for over in shapes:
            with self.subTest(str(over)[:70]):
                self.assertEqual(self.skipped(confirm_routes(**over)), "api_shape")


# ----------------------------------------------------------------------------
# 판정 단계 / 발송 단계
# ----------------------------------------------------------------------------
class StepTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)
        self.temp = self.dir / "runner"
        self.temp.mkdir()
        self.summary, self.output = self.dir / "summary.md", self.dir / "output.txt"
        self.state = self.dir / "state.json"
        self.out = []

    def mode(self, mode):
        self.state.write_text(json.dumps({"mode": mode}), encoding="utf-8")

    def env(self, base=None, **over):
        env = SpyEnv(ready_env() if base is None else base)
        env.update({"RUNNER_TEMP": str(self.temp), "GITHUB_STEP_SUMMARY": str(self.summary), "GITHUB_OUTPUT": str(self.output)})
        env.update(over)
        return env

    def decide(self, kind=an.READY, routes=None, env=None, reader=True):
        api = FakeApi((ready_routes() if kind == an.READY else confirm_routes()) if routes is None else routes)
        code = an.run_decide(kind, env if env is not None else self.env(), self.out.append, reader=an.Reader(api) if reader else None, sleep=no_sleep, state_file=self.state)
        return code, api

    def text(self, path):
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def message_file(self):
        return self.temp / an.MESSAGE_FILE

    # ---- off ----------------------------------------------------------------------------
    def test_off_ends_at_once_without_reading_secrets_github_or_the_token(self):
        self.mode("off")
        env = self.env()
        code, api = self.decide(env=env)
        self.assertEqual((code, self.out, api.calls), (0, [an.MODE_OFF_LINE], []))
        self.assertEqual(set(env.reads), {"GITHUB_STEP_SUMMARY"})                 # 시크릿·토큰·이벤트 값 어느 것도 읽지 않았다
        self.assertIn("꺼져", self.text(self.summary))
        self.assertEqual((self.text(self.output), self.message_file().exists()), ("", False))

    def test_a_missing_or_odd_state_file_is_off_for_both_kinds(self):
        for kind in (an.READY, an.CONFIRM):
            for content in (None, "garbage", '{"mode": "ON"}'):
                with self.subTest((kind, content)):
                    self.out.clear()
                    if content is None:
                        if self.state.exists():
                            self.state.unlink()
                    else:
                        self.state.write_text(content, encoding="utf-8")
                    code, api = self.decide(kind)
                    self.assertEqual((code, self.out, api.calls), (0, [an.MODE_OFF_LINE], []))

    def test_off_removes_nothing_and_writes_no_output_even_if_a_stale_file_exists(self):
        self.mode("off")
        self.message_file().write_text("낡은 문장", encoding="utf-8")
        self.decide()
        self.assertEqual(self.text(self.output), "")
        self.assertTrue(self.message_file().exists())                              # 꺼져 있으면 아무것도 건드리지 않는다

    # ---- dry ----------------------------------------------------------------------------
    def test_dry_writes_the_message_to_the_summary_only(self):
        self.mode("dry")
        code, api = self.decide()
        self.assertEqual(code, 0)
        text = an.compose_ready(NUMBER, TITLE, BODY)
        summary = self.text(self.summary)
        self.assertIn(text, summary)
        self.assertIn("```text", summary)
        self.assertEqual((self.text(self.output), self.message_file().exists()), ("", False))
        self.assertEqual(api.methods(), {"GET"})
        joined = "\n".join(self.out)
        for needle in ("워크플로 둘", "병합 알림 자동화", BODY[:10], "Co-authored"):
            self.assertNotIn(needle, joined)                                       # 로그에는 제목·본문이 없다
        self.assertIn("dry", joined)

    def test_dry_never_touches_the_telegram_names_or_the_output_file(self):
        self.mode("dry")
        env = self.env(TELEGRAM_BOT_TOKEN=nh.TOKEN, TELEGRAM_CHAT_ID=nh.CHAT)
        self.decide(env=env)
        self.assertNotIn("TELEGRAM_BOT_TOKEN", env.reads)
        self.assertNotIn("TELEGRAM_CHAT_ID", env.reads)
        self.assertNotIn("GITHUB_OUTPUT", env.reads)
        self.assertEqual(nh.leaks(self.text(self.summary), "\n".join(self.out)), [])

    def test_dry_with_a_problem_writes_a_fixed_sentence_instead(self):
        self.mode("dry")
        code, _ = self.decide(routes=ready_routes(prs=[]))
        self.assertEqual(code, 0)
        self.assertIn(an.REASONS["no_pr"][0], self.text(self.summary))
        self.assertNotIn("```", self.text(self.summary))

    # ---- on -----------------------------------------------------------------------------
    def test_on_writes_the_message_file_and_one_fixed_output_line(self):
        self.mode("on")
        code, api = self.decide()
        self.assertEqual(code, 0)
        self.assertEqual(self.message_file().read_text(encoding="utf-8"), an.compose_ready(NUMBER, TITLE, BODY))
        self.assertEqual(self.text(self.output), "send=yes\n")
        self.assertNotIn("워크플로 둘", self.text(self.summary))                    # 요약에는 제목·본문을 싣지 않는다(고정 문장만)
        self.assertNotIn("워크플로 둘", "\n".join(self.out))
        self.assertEqual(api.methods(), {"GET"})

    def test_on_confirm_makes_the_confirmation_message(self):
        self.mode("on")
        code, _ = self.decide(an.CONFIRM, env=self.env(confirm_env()))
        self.assertEqual(code, 0)
        self.assertEqual(self.message_file().read_text(encoding="utf-8"), "[M105] 병합완료 확인 - 정상")
        self.assertEqual(self.text(self.output), "send=yes\n")

    def test_a_stale_message_file_is_removed_before_deciding(self):
        for mode in ("dry", "on"):
            with self.subTest(mode):
                self.mode(mode)
                self.message_file().write_text("낡은 문장", encoding="utf-8")
                self.output.write_text("", encoding="utf-8")
                self.decide(routes=ready_routes(prs=[]))                              # 알릴 것이 없다
                self.assertFalse(self.message_file().exists())
                self.assertEqual(self.text(self.output), "")

    def test_on_without_a_place_for_the_file_does_not_send_and_warns(self):
        self.mode("on")
        env = self.env()
        del env["RUNNER_TEMP"]
        code, _ = self.decide(env=env)
        self.assertEqual(code, 0)
        self.assertEqual(self.text(self.output), "")
        self.assertTrue(any(line.startswith("::warning::") for line in self.out))

    def test_every_skip_has_a_fixed_sentence_in_log_and_summary_and_loud_ones_warn(self):
        self.mode("dry")
        cases = {"no_pr": ready_routes(prs=[]), "many_pr": ready_routes(prs=[pr_item(), pr_item(number=3)]), "pr_mismatch": ready_routes(prs=[pr_item(state="closed")]),
                 "checks_failed": ready_routes(runs=good_runs() + [run_item(9, conclusion="failure")]), "api_error": {"/pulls": ol.GitHubError("HTTP 500 " + "x" * 50)},
                 "api_shape": {"/pulls": {"x": 1}}, "title_problem": ready_routes(prs=[pr_item(title="[M105] 담당 " + AT + "x")])}
        for code_name, routes in cases.items():
            with self.subTest(code_name):
                self.out.clear()
                self.summary.write_text("", encoding="utf-8")
                code, _ = self.decide(routes=routes)
                sentence, loud = an.REASONS[code_name]
                self.assertEqual(code, 0)
                self.assertIn(f"병합 알림 자동: {sentence}", self.out)
                self.assertEqual(any(line.startswith("::warning::") for line in self.out), loud)
                self.assertIn(sentence, self.text(self.summary))
                self.assertNotIn("HTTP 500", "\n".join(self.out) + self.text(self.summary))      # GitHub 응답 원문은 찍지 않는다

    def test_a_missing_token_without_a_reader_is_an_api_error_with_a_warning(self):
        self.mode("dry")
        env = self.env()
        del env["GITHUB_TOKEN"]
        code, _ = self.decide(env=env, reader=False)
        self.assertEqual(code, 0)
        self.assertTrue(any(line.startswith("::warning::") for line in self.out))
        self.assertIn(an.REASONS["api_error"][0], self.text(self.summary))

    def test_input_problems_are_reported_without_echoing_the_values(self):
        self.mode("dry")
        evil = "ai/claude/M105-x;touch PWNED"
        code, api = self.decide(env=self.env(NOTICE_RUN_BRANCH=evil))
        self.assertEqual((code, api.calls), (0, []))
        self.assertNotIn("PWNED", "\n".join(self.out) + self.text(self.summary))
        self.assertTrue(any(line.startswith("::warning::") for line in self.out))

    def test_the_summary_and_log_never_contain_workflow_command_prefixes_from_the_inputs(self):
        self.mode("dry")
        for title in ("[M105] ::error::가짜 제목", "[M105] ##[group]가짜"):
            self.out.clear()
            self.summary.write_text("", encoding="utf-8")
            self.decide(routes=ready_routes(prs=[pr_item(title=title)]))
            self.assertNotIn("::error::가짜", "\n".join(self.out))
            self.assertNotIn("##[group]", "\n".join(self.out))

    def test_without_a_summary_path_nothing_breaks(self):
        self.mode("dry")
        env = self.env()
        del env["GITHUB_STEP_SUMMARY"]
        code, _ = self.decide(env=env)
        self.assertEqual(code, 0)

    # ---- 발송 단계 ----------------------------------------------------------------------------
    def make_notifier(self):
        net = nh.FakeNet()
        clock = nh.Clock()
        return notify.Notifier(dict(nh.ENV), opener=net, sleep=clock.sleep, clock=clock.clock, budget=notify.Budget()), net

    def write_message(self, text):
        self.message_file().write_text(text, encoding="utf-8", newline="\n")

    def send(self, env=None, notifier=None):
        return an.run_send(env if env is not None else self.env(), self.out.append, notifier=notifier, state_file=self.state)

    def test_send_is_refused_unless_the_mode_is_on_and_reads_no_secrets_then(self):
        class Boom:
            def send_message(self, *args, **kwargs):
                raise AssertionError("보내면 안 된다")

        for mode in ("off", "dry"):
            with self.subTest(mode):
                self.mode(mode)
                self.write_message(an.compose_ready(NUMBER, TITLE, BODY))
                env = self.env(TELEGRAM_BOT_TOKEN=nh.TOKEN, TELEGRAM_CHAT_ID=nh.CHAT)
                self.assertEqual(self.send(env, Boom()), 0)
                self.assertNotIn("TELEGRAM_BOT_TOKEN", env.reads)
                self.assertNotIn("TELEGRAM_CHAT_ID", env.reads)
                self.assertNotIn("RUNNER_TEMP", env.reads)
        self.state.unlink()
        self.assertEqual(self.send(self.env(), Boom()), 0)                         # 파일이 없으면 off

    def test_send_sends_the_checked_message_as_plain_text_once(self):
        self.mode("on")
        text = an.compose_ready(NUMBER, TITLE, BODY)
        self.write_message(text)
        notifier, net = self.make_notifier()
        self.assertEqual(self.send(notifier=notifier), 0)
        self.assertEqual(net.calls, 1)
        body = net.bodies()[0]
        self.assertEqual(body["text"], text)
        self.assertNotIn("parse_mode", body)                                       # 평문 — 서식·링크 해석 없음
        self.assertNotIn("reply_markup", body)
        self.assertEqual(body["link_preview_options"], {"is_disabled": True})
        self.assertIn("텔레그램으로 보냈습니다", "\n".join(self.out))
        self.assertEqual(nh.leaks("\n".join(self.out), self.text(self.summary)), [])

    def test_send_confirmation_messages_too(self):
        self.mode("on")
        for text in ("[M105] 병합완료 확인 - 정상", "[M105] 병합완료 확인 - 이상\n변경 파일이 PR 과 다릅니다(PR 2개, 병합 3개)"):
            with self.subTest(text[:20]):
                self.write_message(text)
                notifier, net = self.make_notifier()
                self.assertEqual(self.send(notifier=notifier), 0)
                self.assertEqual([body["text"] for body in net.bodies()], [text])

    def test_send_checks_the_message_again_and_refuses_what_decide_would_not_make(self):
        self.mode("on")
        good = an.compose_ready(NUMBER, TITLE, BODY)
        broken = {"extra line": good + "\n추가", "mention": good.replace("시험:", "시험: " + AT + "x"), "address": good.replace("시험:", "시험: " + SCHEME + "x.example"),
                  "secret": good.replace("시험:", "시험: " + nh.TOKEN), "plain": "그냥 글", "empty": "", "too long": good + "가" * 900, "tilde": good.replace("시험:", "시험: " + TILDE),
                  "other first line": "[M105] 병합 요청 — 제목", "confirm without reason": "[M105] 병합완료 확인 - 이상"}
        for label, text in broken.items():
            with self.subTest(label):
                self.out.clear()
                self.write_message(text)
                notifier, net = self.make_notifier()
                self.assertEqual(self.send(notifier=notifier), 0)
                self.assertEqual(net.calls, 0)
                self.assertTrue(any(line.startswith("::warning::") for line in self.out))

    def test_send_with_a_missing_oversized_or_binary_file_sends_nothing(self):
        self.mode("on")
        notifier, net = self.make_notifier()
        self.assertEqual(self.send(notifier=notifier), 0)                           # 파일이 없다
        self.message_file().write_bytes(b"x" * 5000)
        self.assertEqual(self.send(notifier=notifier), 0)                           # 너무 크다
        self.message_file().write_bytes(b"\xff\xfe\x00\x01")
        self.assertEqual(self.send(notifier=notifier), 0)                           # UTF-8 이 아니다
        env = self.env()
        del env["RUNNER_TEMP"]
        self.assertEqual(self.send(env, notifier), 0)                               # 둘 곳이 없다
        self.assertEqual(net.calls, 0)

    def test_a_failed_send_is_a_warning_and_a_zero_exit_without_leaking_the_secrets(self):
        self.mode("on")
        self.write_message(an.compose_ready(NUMBER, TITLE, BODY))
        net = nh.FakeNet(nh.http_error(401, "Unauthorized"))
        clock = nh.Clock()
        notifier = notify.Notifier(dict(nh.ENV), opener=net, sleep=clock.sleep, clock=clock.clock, budget=notify.Budget())
        self.assertEqual(self.send(notifier=notifier), 0)
        self.assertTrue(any(line.startswith("::warning::") for line in self.out))
        self.assertEqual(nh.leaks("\n".join(self.out), self.text(self.summary)), [])
        self.assertNotIn("워크플로 둘", "\n".join(self.out))

    def test_without_the_secrets_the_send_is_a_warning_not_a_crash(self):
        self.mode("on")
        self.write_message(an.compose_ready(NUMBER, TITLE, BODY))
        notifier = notify.Notifier({}, opener=nh.FakeNet(), budget=notify.Budget())
        self.assertEqual(self.send(notifier=notifier), 0)
        self.assertTrue(any(line.startswith("::warning::") for line in self.out))

    def test_the_send_step_builds_the_real_notifier_from_the_environment_when_none_is_given(self):
        self.mode("on")
        self.write_message("[M105] 병합완료 확인 - 정상")
        calls = []
        original = notify.Notifier

        class Recording(original):
            def __init__(self, environ=None, **kwargs):
                calls.append(environ)
                super().__init__(environ, opener=nh.FakeNet(), sleep=lambda s: None, clock=nh.Clock().clock, budget=notify.Budget())

        env = self.env(TELEGRAM_BOT_TOKEN=nh.TOKEN, TELEGRAM_CHAT_ID=nh.CHAT)
        with mock.patch.object(notify, "Notifier", Recording):
            self.assertEqual(self.send(env), 0)
        self.assertEqual(len(calls), 1)
        self.assertIs(calls[0], env)                                                # 환경을 그대로 넘긴다 — 시크릿은 이 단계의 env 에서만 읽는다
        self.assertIn("텔레그램으로 보냈습니다", "\n".join(self.out))

    # ---- 두 단계의 이어짐 ---------------------------------------------------------------------
    def test_what_decide_writes_in_on_mode_is_exactly_what_send_accepts(self):
        self.mode("on")
        for kind, routes, env in ((an.READY, ready_routes(), self.env()), (an.CONFIRM, confirm_routes(), self.env(confirm_env()))):
            with self.subTest(kind):
                self.output.write_text("", encoding="utf-8")
                self.decide(kind, routes=routes, env=env)
                self.assertEqual(self.text(self.output), "send=yes\n")
                notifier, net = self.make_notifier()
                self.out.clear()
                self.assertEqual(self.send(notifier=notifier), 0)
                self.assertEqual(net.calls, 1)
                self.assertEqual(net.bodies()[0]["text"], self.message_file().read_text(encoding="utf-8"))


# ----------------------------------------------------------------------------
# 명령 줄
# ----------------------------------------------------------------------------
class CommandLineTest(unittest.TestCase):
    def run_main(self, argv, **kwargs):
        err, out = io.StringIO(), []
        with contextlib.redirect_stderr(err):
            try:
                code = an.main(argv, out=out.append, **kwargs)
            except SystemExit as exc:
                code = exc.code
        return code, out, err.getvalue()

    def test_unknown_commands_and_extra_arguments_are_usage_errors_that_do_not_echo_them(self):
        for argv in (["bogus-value-xyz"], [], ["merge-ready", "extra-value-xyz"], ["send", "--flag-xyz"], ["merge-confirm", "--title", "xyz"]):
            with self.subTest(argv):
                code, out, err = self.run_main(argv)
                self.assertEqual(code, 2)
                self.assertIn(an.USAGE_ERROR_LINE, err)
                self.assertNotIn("xyz", err.replace("merge-ready,merge-confirm,send", ""))

    def test_the_three_commands_exist(self):
        parser = an.build_parser()
        for name in (an.READY, an.CONFIRM, an.SEND):
            self.assertEqual(parser.parse_args([name]).command, name)

    def test_main_with_off_state_exits_zero_for_all_three(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "s.json"
            state.write_text('{"mode": "off"}', encoding="utf-8")
            for name in (an.READY, an.CONFIRM, an.SEND):
                code, out, _ = self.run_main([name], environ={}, state_file=state)
                self.assertEqual(code, 0)

    def test_an_unexpected_error_is_a_warning_and_exit_zero_with_only_the_class_name(self):
        class Exploding:
            def request(self, *args, **kwargs):
                raise RuntimeError("비밀 문구 " + nh.TOKEN)

        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "s.json"
            state.write_text('{"mode": "dry"}', encoding="utf-8")
            code, out, _ = self.run_main([an.READY], environ=ready_env(), reader=an.Reader(Exploding()), state_file=state)
        self.assertEqual(code, 0)
        joined = "\n".join(out)
        self.assertIn("RuntimeError", joined)
        self.assertNotIn("비밀 문구", joined)
        self.assertEqual(nh.leaks(joined), [])
        self.assertTrue(any(line.startswith("::warning::") for line in out))


# ----------------------------------------------------------------------------
# 정적 성질
# ----------------------------------------------------------------------------
class StaticPropertiesTest(unittest.TestCase):
    def setUp(self):
        self.source = MODULE.read_text(encoding="utf-8")
        self.tree = ast.parse(self.source)

    def test_only_standard_library_modules_and_the_pipeline_helpers_are_imported(self):
        names = set()
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Import):
                names |= {alias.name for alias in node.names}
            elif isinstance(node, ast.ImportFrom):
                names.add(node.module or "")
        self.assertEqual(names, {"argparse", "json", "os", "re", "sys", "time", "unicodedata", "collections", "pathlib", "pipeline", "pipeline.console", "pipeline.llm", "pipeline.secret_patterns"})

    def test_no_network_process_or_file_deletion_shapes_of_its_own(self):
        for needle in ("urllib", "http.client", "socket", "subprocess", "urlopen", "os.system", "os.popen", "shutil", "eval(", "exec(", "__import__", "importlib", "getattr(", "os.remove", ".rmdir", "unlink(missing"):
            self.assertNotIn(needle, self.source, needle)

    def test_github_is_only_ever_asked_with_get(self):
        calls = [node for node in ast.walk(self.tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "request"]
        self.assertEqual(len(calls), 1)
        self.assertEqual([arg.value for arg in calls[0].args if isinstance(arg, ast.Constant)], ["GET"])
        for verb in ("POST", "PUT", "PATCH", "DELETE", "HEAD"):
            self.assertNotIn(f'"{verb}"', self.source)
            self.assertNotIn(f"'{verb}'", self.source)
        reader_methods = [node.name for node in ast.walk(self.tree) if isinstance(node, ast.FunctionDef)]
        self.assertNotIn("post", [name.lower() for name in reader_methods])

    def test_the_telegram_is_reached_only_through_the_notifier_and_in_plain_text(self):
        self.assertEqual(self.source.count("notify.Notifier("), 1)
        sends = [node for node in ast.walk(self.tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "send_message"]
        self.assertEqual(len(sends), 1)
        self.assertEqual(sends[0].keywords, [])                                     # parse_mode·buttons 를 주지 않는다(평문, 단추 없음)
        self.assertNotIn("parse_mode", self.source)

    def test_the_telegram_secret_names_are_only_in_docstrings_never_in_a_code_string(self):
        """이 모듈의 코드는 텔레그램 시크릿 이름을 문자열로 다루지 않는다 — 값은 notify.Notifier 가 환경에서 읽고, 이 모듈은 환경을 그대로 넘기기만 한다(독스트링 설명 제외)."""
        docstrings = set()
        for node in ast.walk(self.tree):
            if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef)) and node.body and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant):
                docstrings.add(id(node.body[0].value))
        strings = [node.value for node in ast.walk(self.tree) if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings]
        self.assertGreater(len(strings), 50)
        self.assertEqual([text for text in strings if "TELEGRAM" in text.upper() or "BOT_TOKEN" in text.upper()], [])
        names = {node.id for node in ast.walk(self.tree) if isinstance(node, ast.Name)}
        self.assertEqual([name for name in names if "TELEGRAM" in name.upper()], [])

    def test_the_new_text_has_no_tilde_web_address_or_personal_value(self):
        for path in (MODULE, STATE):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn(TILDE, text, path.name)
            self.assertNotRegex(text, r"https?://", path.name)

    def test_stdout_lines_use_only_fixed_sentences(self):
        """`out(` 으로 찍는 모든 글은 상수 문장이거나 고정 문장에 REASONS 의 문장·검증한 값(클래스 이름)만 끼운 f-문자열이다 — 제목·본문·GitHub 응답 변수를 찍는 줄이 없다."""
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "out":
                for arg in node.args:
                    names = {sub.id for sub in ast.walk(arg) if isinstance(sub, ast.Name)}
                    self.assertLessEqual(names, {"sentence", "detail", "MODE_OFF_LINE", "UNEXPECTED_LINE", "UNEXPECTED_WARNING", "exc", "type"}, ast.dump(arg)[:120])


if __name__ == "__main__":
    unittest.main()
