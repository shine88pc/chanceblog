"""병합 알림 자동화(`pipeline/auto_notice.py`) 단위 시험 — 켬 상태 읽기·입력 거르기·글 거르기·문장 만들기·두 알림의 판정(가짜 GitHub 응답)·판정 단계와 발송 단계·명령 줄·정적 성질.

GitHub 와 텔레그램은 한 번도 부르지 않는다: GitHub 는 `request(method, path, payload, params, retry)` 를 가진 가짜(`FakeApi` — 부른 것을 모두 기록해 GET 뿐인지 본다),
텔레그램은 `notify_helpers.FakeNet`(가짜 urlopen)과 런타임에 조합한 가짜 값이다. 이 시험이 고정하는 것:
 1. 켬 상태: 파일이 없거나 이상하면 off, off 에서는 환경변수(시크릿 포함)도 GitHub 도 건드리지 않는다. dry 는 문장을 요약에만, on 은 문장 파일과 출력 한 줄만 남긴다.
 2. 신뢰 경계: 가지·SHA·제목·글자 모양 거르기(주소·`@`·물결표·제어 문자·비밀 모양), 로그·요약에는 제목·본문 원문이 없다, GitHub 는 GET 만 부른다.
 3. 문장 규칙: 병합 부탁(제목 80자·요점 5줄×120자·800자 안·고정 꼬리)과 병합완료 확인(정상 한 줄·이상 사유 한 줄 100자 안).
 4. 판정: 병합 부탁은 열린 PR·머리 커밋·검사 모두 초록일 때만, 병합완료 확인은 [M번호] 병합 커밋·연결된 PR 하나·부모 수·트리 일치/파일 집합·main 검사 결론.
 5. 병합 부탁의 변경 파일 읽기(독립 감사 BA-S2 R2·N6): 검사 정의(.github/·tests/·scripts/validate_repo.py·AGENTS.md·docs/SECURITY_GUARDRAILS.md)가 바뀐 PR 이면 고정 한 줄, 머리 커밋 7자리는 늘 — 문장·모양 검사·읽기 쪽 수.
"""
import ast
import base64
import contextlib
import copy
import io
import json
import os
import re
import runpy
import stat
import sys
import tempfile
import time
import unicodedata
import unittest
import urllib.error
import urllib.parse
import urllib.request
import warnings
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
TILDE, AT, DOT = chr(0x7E), chr(0x40), chr(0x2E)
BODY = ("앞서 병합된 묶음의 다음 단계다. 변경 등급 T3 — 켬 상태는 off 로 낸다.\n"
        "- **워크플로 둘**: 병합 부탁 알림과 병합완료 확인 알림을 자동으로 보낸다.\n"
        "- 시험: 새 시험을 더했다\n"
        "\n"
        "Co-authored-by: Claude Sonnet 5.5 <noreply" + AT + "anthropic" + DOT + "com>\n")       # 꼬리표 줄 — 메일 모양은 조립해서 쓴다
SCHEME = "ht" + "tps://"                                  # 주소 모양 글은 조립해서 쓴다(새 글에 웹 주소를 두지 않는다)
GITHUB_TOKEN_SHAPE = "gh" + "p_" + "A" * 36
SLACK_TOKEN_SHAPE = "xo" + "xb-" + "1" * 12                  # 비밀 모양 가짜 값도 조립한다(토큰 셋·키 셋 — 모두 find_secrets 가 비밀로 본다)
GOOGLE_KEY_SHAPE = "AI" + "za" + "B" * 35
AWS_KEY_SHAPE = "AK" + "IA" + "C" * 16
SK_KEY_SHAPE = "s" + "k-" + "D" * 40
TOKEN_SHAPES = (GITHUB_TOKEN_SHAPE, SLACK_TOKEN_SHAPE, nh.TOKEN)
KEY_SHAPES = (GOOGLE_KEY_SHAPE, AWS_KEY_SHAPE, SK_KEY_SHAPE)
DOT_LIKE = (chr(0x3002), chr(0xFF61), chr(0x2024), chr(0xFE52), chr(0xFF0E))      # 점처럼 읽히는 글자 다섯
SHORT_ADDRESSES = (("goo", "gl"), ("youtu", "be"), ("is", "gd"), ("lnkd", "in"), ("rb", "gy"), ("s", "id"), ("shorturl", "at"), ("bit", "ly"), ("t", "co"), ("tinyurl", "com"),
                   ("ow", "ly"), ("buff", "ly"), ("cutt", "ly"), ("tiny", "cc"), ("v", "gd"), ("t", "ly"), ("t", "me"), ("evil", "sh"), ("evil", "zip"), ("evil", "xyz"))   # 단축 주소·새 최상위 도메인 20개


def address(pair, suffix=""):
    return pair[0] + DOT + pair[1] + suffix


def b64(text):
    return an.encode_message(text)


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


DEFAULT_FILES = ("docs/ARCHITECTURE.md", "pipeline/auto_notice.py")             # 검사 정의가 아닌 평범한 변경 파일 둘


def ready_routes(prs=None, runs=None, files=None):
    """병합 부탁 판정이 읽는 경로 표: PR 목록·검사 실행 목록·PR 마다 변경 파일 목록(files — 파일 이름 목록이나 항목 목록, 기본은 DEFAULT_FILES)."""
    prs = [pr_item()] if prs is None else prs
    routes = {"/pulls": prs, "/actions/runs": {"workflow_runs": good_runs() if runs is None else runs}}
    for pr in prs if isinstance(prs, list) else ():
        number = pr.get("number") if isinstance(pr, dict) else None
        if isinstance(number, int) and not isinstance(number, bool):
            routes[f"/pulls/{number}/files"] = file_items(DEFAULT_FILES if files is None else files)
    return routes


def ready_env(**over):
    env = {"GITHUB_REPOSITORY": REPO, "NOTICE_RUN_ID": str(RUN_ID), "NOTICE_RUN_BRANCH": BRANCH, "NOTICE_RUN_SHA": SHA, "NOTICE_RUN_EVENT": "push",
           "NOTICE_RUN_CONCLUSION": "success", "NOTICE_RUN_REPO": REPO, "NOTICE_DEFAULT_BRANCH": "main", "GITHUB_TOKEN": "CANARY_read_token"}
    env.update(over)
    return env


def confirm_env(**over):
    return ready_env(NOTICE_RUN_BRANCH="main", **over)


def file_items(files):
    """파일 이름 목록 → GitHub `files` 항목 목록. 항목이 (이름, blob 해시) 쌍이면 `sha` 도 싣는다(이름만이면 blob 해시가 없는 응답 모양). 항목이 사전이면 그대로 둔다(previous_filename 같은 칸이 있는 응답 모양)."""
    return [(dict(item) if isinstance(item, dict) else {"filename": item[0], "sha": item[1]} if isinstance(item, tuple) else {"filename": item}) for item in files]


def commit_obj(sha=SHA, message="[M105] 병합 알림 자동화 — 워크플로 둘과 파이썬 보조 [대상: 공통] (#248)\n\n본문", parents=(OTHER_SHA,), tree=TREE, files=("a.py", "b.md")):
    item = {"sha": sha, "commit": {"message": message, "tree": {"sha": tree}}, "parents": [{"sha": parent} for parent in parents]}
    if files is not None:
        item["files"] = file_items(files)
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

    def test_the_size_limit_is_exactly_one_kilobyte(self):
        body = b'{"mode": "on"}'
        self.assertEqual(an.STATE_MAX_BYTES, 1024)
        self.assertEqual(self.read("", raw=body + b" " * (1024 - len(body))), "on")                 # 정확히 1,024바이트는 읽는다
        self.assertEqual(self.read("", raw=body + b" " * (1025 - len(body))), "off")                # 1바이트라도 넘으면 읽지 않는다

    def test_the_path_defaults_to_the_repository_file_not_the_working_directory(self):
        self.assertEqual(an.STATE_FILE, ROOT / "pipeline" / "auto_notice.json")

    def test_a_symbolic_link_is_never_followed_even_to_a_valid_on_file(self):
        """AN1-S-3: 링크는 diff 에 대상 경로만 보여 눈으로 놓치기 쉽다 — 링크면 가리키는 값이 on 이어도 off."""
        with tempfile.TemporaryDirectory() as tmp:
            real = Path(tmp) / "real.json"
            real.write_text('{"mode": "on"}', encoding="utf-8")
            link, broken = Path(tmp) / "link.json", Path(tmp) / "broken.json"
            try:
                link.symlink_to(real)
                broken.symlink_to(Path(tmp) / "gone.json")
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f"이 환경에서는 심볼릭 링크를 만들 수 없다({type(exc).__name__}) — 아래 가짜 stat 시험이 같은 길을 본다")
            self.assertEqual(an.read_mode(real), "on")
            self.assertEqual(an.read_mode(link), "off")
            self.assertEqual(an.read_mode(broken), "off")

    def test_anything_that_is_not_a_regular_file_is_off_without_reading_it(self):
        """링크를 만들 수 없는 PC 에서도 도는 시험: lstat 이 '링크·폴더·장치·파이프·소켓' 이라고 답하면 내용을 읽지 않고 off."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "on.json"
            path.write_text('{"mode": "on"}', encoding="utf-8")
            self.assertEqual(an.read_mode(path), "on")
            for kind in (stat.S_IFLNK, stat.S_IFDIR, stat.S_IFCHR, stat.S_IFBLK, stat.S_IFIFO, stat.S_IFSOCK):
                fake = os.stat_result((kind | 0o644, 0, 0, 1, 0, 0, 20, 0, 0, 0))
                with mock.patch.object(Path, "lstat", return_value=fake), mock.patch.object(Path, "read_text", side_effect=AssertionError("읽으면 안 된다")):
                    self.assertEqual(an.read_mode(path), "off", hex(kind))
            fake = os.stat_result((stat.S_IFREG | 0o644, 0, 0, 1, 0, 0, 20, 0, 0, 0))                # 보통 파일이면 읽는다(대조)
            with mock.patch.object(Path, "lstat", return_value=fake):
                self.assertEqual(an.read_mode(path), "on")

    def test_a_json_reader_recursion_error_means_off_and_never_escapes(self):
        """아주 깊게 중첩된 글에서 JSON 읽기는 파이썬 버전에 따라 RecursionError(3.10 은 1,000겹에서)나 JSONDecodeError(3.12 는 같은 크기에서)를 낸다 — 어느 쪽이든 off 이고 예외가 밖으로 나가지 않는다.
        1KB 상한 안에서는 3.12 가 RecursionError 에 닿지 못하므로 가짜로도 못박는다."""
        self.assertEqual(self.read("[" * 1000), "off")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "auto_notice.json"
            path.write_text('{"mode": "on"}', encoding="utf-8")
            with mock.patch.object(an.json, "loads", side_effect=RecursionError):
                self.assertEqual(an.read_mode(path), "off")
            self.assertEqual(an.read_mode(path), "on")                # 대조: 가짜를 거두면 다시 읽는다


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
                 ("www" + DOT + "evil" + DOT + "example", "address"), ("github" + DOT + "com 에 있다", "address"), ("evil" + DOT + "io/path", "address"), ("see example" + DOT + "com요", "address"),
                 ("mailto:x", "address"), ("javascript:alert(1)", "address"), ("data:text/html,x", "address"), ("접속 10.0.0.1 로", "address"),
                 ("ｈｔｔｐ：／／evil.example", "address"), ("ｗｗｗ．evil.example", "address"),
                 ("약 10" + TILDE + "20개", "tilde"), ("전각 10" + chr(0xFF5E) + "20", "tilde"),
                 ("키 " + nh.TOKEN, "secret"), ("토큰 " + GITHUB_TOKEN_SHAPE, "secret")]
        for text, code in cases:
            with self.subTest(text[:30]):
                self.assertEqual(an.line_problem(text), code)

    def test_each_secret_detector_alone_still_refuses_what_only_it_sees(self):
        """비밀 모양은 두 길로 거른다 — ① notify.pr_title_problem 이 로그용 가리개(llm.mask)가 글을 바꾸는지로 보는 것(낱말 경계 없는 `key=`·`token=`·`secret=` 꼴, 구글 키·토큰의 짧은 꼴)
        ② secret_patterns.find_secrets 가 전각·결합 글자로 쪼갠 키까지 보는 검사용 사본으로 보는 것. 한 길만 잡는 입력도 거절돼야 어느 한 길이 빠져도 새지 않는다(전제 단언 포함)."""
        from pipeline.llm import mask
        from pipeline.secret_patterns import find_secrets
        mask_only = ("key=hello", "다음 token=abc 로", "SECRET=x", "AI" + "za" + "a" * 20, "ya" + "29." + "b" * 20, "1/" + "/" + "c" * 20)
        for text in mask_only:
            with self.subTest(text[:12]):
                self.assertFalse(find_secrets(text))                  # 전제: find_secrets 는 이 입력을 못 본다
                self.assertNotEqual(mask(text), text)                 # 전제: 가리개는 본다
                self.assertEqual(an.line_problem(text), "secret")
        fullwidth = "".join(chr(ord(char) + 0xFEE0) for char in GITHUB_TOKEN_SHAPE)        # 전각 글자로 쓴 GitHub 토큰 모양
        self.assertEqual(mask(fullwidth), fullwidth)                  # 전제: 가리개는 전각 글자를 못 본다
        self.assertTrue(find_secrets(fullwidth))                      # 전제: 검사용 사본은 본다
        self.assertEqual(an.line_problem(fullwidth), "secret")

    def test_twenty_short_addresses_and_new_top_level_domains_are_addresses_in_every_common_form(self):
        """AN1-S-2: 주소는 목록이 아니라 구조(`낱말 점 영문 2–24자`)로 본다 — 단축 주소·새 최상위 도메인이 모두 거절된다."""
        self.assertEqual(len(SHORT_ADDRESSES), 20)
        for pair in SHORT_ADDRESSES:
            for form in (address(pair), address(pair, "/x"), "see " + address(pair, "요"), address(pair).upper(), "(" + address(pair) + ")", address(pair, ".") + " 끝", "앞 " + address(pair) + "/a/b?c=d"):
                with self.subTest(form):
                    self.assertEqual(an.line_problem(form), "address")

    def test_dots_that_look_like_dots_are_folded_before_the_address_check(self):
        """점처럼 읽히는 글자 다섯(U+3002·U+FF61·U+2024·U+FE52·U+FF0E)과 전각 글자로 쓴 주소도 거절된다."""
        for dot in DOT_LIKE:
            for pair in (("evil", "com"), ("goo", "gl"), ("evil", "zip")):
                with self.subTest((hex(ord(dot)), pair)):
                    self.assertEqual(an.line_problem(pair[0] + dot + pair[1]), "address")
                    self.assertEqual(an.line_problem("보기 " + pair[0] + dot + pair[1] + "/x"), "address")
        self.assertEqual(an.line_problem("".join(chr(ord(char) + 0xFEE0) for char in "goo") + chr(0xFF0E) + "".join(chr(ord(char) + 0xFEE0) for char in "gl")), "address")      # 전각 글자와 전각 점
        self.assertEqual(an._folded("a" + chr(0x3002) + "b" + chr(0xFF61) + "c"), "a.b.c")
        self.assertEqual(set(an._DOT_LIKE), {0x3002})                                    # 표에는 NFKC 가 접지 않는 U+3002 하나뿐 — 나머지 넷은 NFKC 가 이미 `.`(U+FF61 은 U+3002 를 거쳐)로 접는다
        for dot in DOT_LIKE[1:]:
            self.assertIn(unicodedata.normalize("NFKC", dot), (".", chr(0x3002)), hex(ord(dot)))
        self.assertEqual(an._folded("@" + TILDE), "@" + TILDE)                           # ASCII 골뱅이와 물결표는 접은 사본에도 그대로 있다 — line_problem 은 접은 사본 하나로 두 글자를 본다

    def test_file_names_versions_and_numbers_in_a_normal_body_are_not_addresses(self):
        """AN1-S-2: 새로 거절되면 안 되는 정상 본문 표본 — 파일 이름·번호·버전·숫자·약어(PR 본문·커밋 본문 흉내)."""
        samples = ("docs/ARCHITECTURE.md 에 절을 더했다", "tests/test_auto_notice.py 와 validate_repo.py 를 고쳤다", ".github/workflows/merge-ready-notice.yml 두 파일", "pipeline/auto_notice.json 은 off 로 낸다",
                   "WORKLOG.md 와 AGENTS.md 는 그대로", "README.md 를 읽는다", "requirements-dev.txt 에 한 줄", "_config.yml 의 exclude", "pages.json 두 파일", "node.js 와 next.js 는 쓰지 않는다",
                   "결함 D-398 부터 D-405 까지", "G-A13·G-A14 와 WF-16", "Python 3.12 와 3.10 둘 다 통과", "v1.2 에서 v1.2.3 으로", "3.12", "9,829개 중 10.5% 가 늘었다", "0.5초 안에 12.5MB 를 읽는다",
                   "1.5배 빠르다", "예: e.g. 이런 것, i.e. 이것, etc. 등등", "M105 병합 부탁 [M105]", "T3 변경 등급", "문장 끝이다. 다음 문장도 있다.", "끝.다음", "Co-authored-by 같은 꼬리표",
                   "pipeline/notify.py 의 Notifier 를 쓴다", "scripts/validate_repo.py 의 WF-16 규칙", "a.yaml b.toml c.cfg d.ini e.csv f.log g.png h.jpg i.svg j.pdf k.lock l.rst m.xml", "main.ts index.html style.css app.js",
                   "ci.yml 두 줄", "시험 122개 → 128개", "약 10" + chr(0x2013) + "20초", "Fig.1 과 No.5", "값 5.0rc1 과 py3.12 와 ps1")
        for sample in samples:
            with self.subTest(sample):
                self.assertEqual(an.line_problem(sample), "")

    def test_dotted_code_names_are_known_to_be_over_rejected_as_addresses(self):
        """알려진 과잉 거절(문서의 한계): 점 있는 코드 이름은 `낱말 점 영문` 꼴이라 주소로 본다 — 그 줄만 빠지고 제목이면 알림이 안 간다(안전한 쪽). 밑줄이 꼬리에 붙으면(`a.b_c`) 도메인이 아니다."""
        for text in ("notify.Notifier 를 쓴다", "os.path", "operator_loop.GitHub 클라이언트", "pipeline.notify 모듈", "github.event.workflow_run.head_branch 값"):
            with self.subTest(text):
                self.assertEqual(an.line_problem(text), "address")
        for text in ("pipeline.auto_notice 모듈", "a.bc_d", "x.event_name 값", "operator_loop.run_decide 함수"):
            with self.subTest(text):
                self.assertEqual(an.line_problem(text), "")

    def test_every_extension_in_the_allow_list_passes_and_the_domains_that_look_like_files_do_not(self):
        for extension in an._FILE_EXTENSIONS:
            self.assertEqual(an.line_problem("파일 이름" + DOT + extension), "", extension)
            self.assertEqual(an.line_problem("FILE" + DOT + extension.upper() + " 열기"), "", extension)
        self.assertNotIn("sh", an._FILE_EXTENSIONS)                         # 도메인이다 — 예외가 아니다
        self.assertNotIn("zip", an._FILE_EXTENSIONS)
        self.assertEqual(an.line_problem("evil" + DOT + "md" + DOT + "evil" + DOT + "com"), "address")      # 확장자 뒤에 도메인이 이어지면 도메인이다
        self.assertEqual(an.line_problem("파일" + DOT + "mdx"), "address")                                  # 목록에 없는 꼬리는 주소 모양(확장자 일부만 맞는 것은 예외가 아니다)
        self.assertEqual(an.line_problem("evil" + DOT + "xn--p1ai"), "address")                            # 퓨니코드 꼬리

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

    def test_a_secret_or_address_head_straddling_the_cut_drops_the_whole_line(self):
        """AN1-S-1: 요점 줄도 제목처럼 '거른 뒤 자름' — 120자 경계에 걸친 비밀·주소 머리의 앞부분이 알림에 실리지 않는다(토큰 셋·키 셋·주소 머리 셋 × 여러 경계)."""
        heads = ([("token", item) for item in TOKEN_SHAPES] + [("key", item) for item in KEY_SHAPES]
                 + [("address", SCHEME + "evil"), ("address", "www" + DOT + "evil" + DOT + "example"), ("address", address(("goo", "gl"), "/x"))])
        for kind, head in heads:
            for pad in (60, 90, 100, 105, 110, 115, 118, 119, 120, 121):
                line = "가" * pad + " " + head
                with self.subTest((kind, head[:6], pad)):
                    self.assertNotEqual(an.line_problem(line), "")                                       # 전제: 줄 전체는 걸린다
                    self.assertEqual(an.point_lines("- " + line), [])
                    self.assertEqual(an.point_lines("- 앞 줄\n- " + line + "\n- 뒷 줄"), ["앞 줄", "뒷 줄"])         # 그 줄만 빠진다
                    if head in (GITHUB_TOKEN_SHAPE, GOOGLE_KEY_SHAPE) and pad in (100, 105):
                        self.assertEqual(an.line_problem(an.shorten(line, an.POINT_LIMIT)), "")           # 전제: 자른 토막만 보면 통과했을 경계다(옛 동작은 이 토막의 앞 18자·13자를 알림에 실었다)
                    self.assertEqual(len(an.point_lines("- " + "가" * pad + " 끝")), 1)                   # 대조: 같은 길이의 깨끗한 줄은 남는다

    def test_a_line_longer_than_the_check_window_is_judged_by_its_first_600_characters_and_a_secret_beyond_is_never_shown(self):
        token = GITHUB_TOKEN_SHAPE
        self.assertEqual(an.POINT_CHECK_CHARS, 600)
        inside = "가" * (an.POINT_CHECK_CHARS - len(token) - 1) + " " + token                                       # 토큰이 600자 안에서 끝난다 → 전체가 보여 걸린다
        self.assertEqual((len(inside), an.point_lines("- " + inside)), (600, []))
        outside = "가" * (an.POINT_CHECK_CHARS - len(token)) + " " + token                                  # 토큰이 한 글자 밖에서 끝난다 → 앞 600자만 보면 토큰이 모자라 안 걸리고, 보이는 것은 앞 120자뿐이다
        self.assertEqual(an.point_lines("- " + outside), ["가" * (an.POINT_LIMIT - 1) + chr(0x2026)])
        far = "가" * 650 + " " + token
        self.assertEqual(an.point_lines("- " + far), ["가" * (an.POINT_LIMIT - 1) + chr(0x2026)])         # 보이는 글에는 비밀 글자가 없다

    def test_a_shape_made_by_the_cut_itself_is_dropped_too(self):
        """자른 뒤에도 한 번 더 거른다 — 자르기 전에는 깨끗했는데 자른 토막에 새로 생긴 모양(비밀 앞머리 같은 것)은 그 줄을 뺀다."""
        pad = "가" * 80
        line = pad + " " + GITHUB_TOKEN_SHAPE[:30] + "-" * 5 + "나" * 100                                  # 자르기 전 줄 전체에는 비밀 모양이 없다
        self.assertEqual(an.line_problem(line), "")
        original = an.shorten
        with mock.patch.object(an, "shorten", lambda text, limit: original(text, limit)[:90] + " " + GITHUB_TOKEN_SHAPE):      # 자른 결과에 비밀 모양이 생기는 경우를 흉내
            self.assertEqual(an.point_lines("- " + line), [])

    def test_very_long_lines_are_handled_in_bounded_time(self):
        """한 줄이 65,000자(GitHub PR 본문의 최대치)여도 앞 600자만 보므로 일이 늘지 않는다 — 점·하이픈·스킴 반복처럼 정규식을 괴롭히는 글 포함."""
        for text in ("a." * 32000, "a" * 65000, "a-" * 30000 + DOT + "co" + "m", "-" * 65000, "1." * 32000, "http" * 16000, "@" * 65000, ("가" * 300 + DOT) * 200, SCHEME * 8000, "x" * 64000 + "://"):
            started = time.monotonic()
            an.point_lines("- " + text)
            self.assertLess(time.monotonic() - started, 5, text[:12])

    def test_points_never_contain_tildes_or_markup(self):
        body = "- **굵게** 약 10" + TILDE + "20 `코드`\n- 다른 " + chr(0xFF5E) + " 줄"
        for point in an.point_lines(body):
            self.assertNotRegex(point, r"[`*]")
            self.assertNotIn(TILDE, point)
            self.assertNotIn(chr(0xFF5E), point)

    def test_every_tilde_look_alike_becomes_an_en_dash_and_nothing_else(self):
        """물결표 넷(ASCII·전각·파동 줄표·틸드 연산자)은 줄표(U+2013)로 바뀌어 실린다 — 지워지거나 다른 글자가 되지 않는다."""
        self.assertEqual(set(an._TILDE_CHARS), {ord(TILDE), 0xFF5E, 0x301C, 0x223C})
        for char in (TILDE, chr(0xFF5E), chr(0x301C), chr(0x223C)):
            with self.subTest(hex(ord(char))):
                self.assertEqual(an.clean_inline("10" + char + "20"), "10" + chr(0x2013) + "20")
                self.assertEqual(an.point_lines("- 약 10" + char + "20초"), ["약 10" + chr(0x2013) + "20초"])

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
HEADLINE = "머리 커밋 aaaaaaa — 병합 전에 PR 화면의 해시와 같은지 보세요"           # SHA("a" * 39 + "1")의 앞 7자리
DEFINITION = "⚠ 검사 정의가 바뀐 PR — 초록은 스스로 증명한 값입니다"


class ComposeReadyTest(unittest.TestCase):
    def test_the_message_has_the_fixed_shape(self):
        text = an.compose_ready(NUMBER, TITLE, BODY, SHA)
        self.assertEqual(text, "[M105] 병합 부탁 — 병합 알림 자동화 — 워크플로 둘과 파이썬 보조 [대상: 공통]\n\n"
                               "- 앞서 병합된 묶음의 다음 단계다. 변경 등급 T3 — 켬 상태는 off 로 낸다.\n"
                               "- 워크플로 둘: 병합 부탁 알림과 병합완료 확인 알림을 자동으로 보낸다.\n"
                               "- 시험: 새 시험을 더했다\n\n검사: 초록\n" + HEADLINE + "\n\n" + TAIL)
        self.assertEqual(an.message_problem(text), "")
        self.assertEqual(an.ready_tail(NUMBER), TAIL)
        flagged = an.compose_ready(NUMBER, TITLE, BODY, SHA, True)
        self.assertEqual(flagged, text.replace("검사: 초록\n", "검사: 초록\n" + DEFINITION + "\n"))       # 검사 정의가 바뀐 PR 이면 검사 줄 바로 다음에 고정 한 줄이 더해질 뿐이다
        self.assertEqual(an.message_problem(flagged), "")
        self.assertEqual(an.compose_ready(NUMBER, TITLE, BODY, SHA, False), text)                              # 기본값은 '바뀌지 않음'

    def test_the_title_part_is_cut_at_80_characters(self):
        rest80, rest81 = "가" * 80, "가" * 81
        first80 = an.compose_ready(NUMBER, f"[M105] {rest80}", "", SHA).split("\n")[0]
        first81 = an.compose_ready(NUMBER, f"[M105] {rest81}", "", SHA).split("\n")[0]
        self.assertEqual(first80, "[M105] 병합 부탁 — " + rest80)
        self.assertEqual(first81, "[M105] 병합 부탁 — " + "가" * 79 + chr(0x2026))

    def test_a_title_with_a_whitespace_control_character_is_refused_not_quietly_normalized(self):
        """제목의 탭·줄 바꿈·수직 탭 같은 공백형 제어 문자는 clean_inline 이 공백 하나로 접어 버린다 — 그래서 접기 전의 제목 전체도 한 번 거른다. 눈으로 같은 글인지 볼 수 없는 제목은 보내지 않는다
        (보이는 공백류는 하나로 접혀 통과한다 — 대조)."""
        controls = ("\t", "\n", "\r", "\x0b", "\x0c", "\x1c", "\x1d", "\x1e", "\x1f", "\x85", chr(0x2028), chr(0x2029))
        self.assertTrue(all(notify.pr_title_problem("가" + char + "나") == "control" for char in controls))          # 전제: 열두 글자 모두 제어로 본다
        for char in controls:
            title = "[M105] 가" + char + "나 제목"
            with self.subTest(hex(ord(char))):
                self.assertEqual(an.line_problem(an.clean_inline(title[len("[M105] "):])), "")                   # 전제: 접은 뒤의 글은 깨끗해 보인다
                with self.assertRaises(an.Skip) as caught:
                    an.compose_ready(NUMBER, title, BODY, SHA)
                self.assertEqual(caught.exception.code, "title_problem")
        for char in (chr(0xA0), chr(0x2003), chr(0x3000)):
            with self.subTest(hex(ord(char))):
                self.assertEqual(an.compose_ready(NUMBER, "[M105] 가" + char + "나", "", SHA).split("\n")[0], "[M105] 병합 부탁 — 가 나")

    def test_without_a_body_there_are_no_bullets_and_the_message_is_still_valid(self):
        for body in (None, "", "\n\n", "Co-authored-by: x\n"):
            with self.subTest(repr(body)):
                text = an.compose_ready(NUMBER, TITLE, body, SHA)
                self.assertNotIn("\n- ", text)
                self.assertEqual(an.message_problem(text), "")
                self.assertEqual(text.split("\n")[1:], ["", "검사: 초록", HEADLINE, "", TAIL])

    def test_the_whole_message_fits_in_800_characters_and_points_are_dropped_from_the_end(self):
        body = "\n".join(f"- 줄{index} " + "나" * 200 for index in range(1, 6))
        long_title = "[M105] " + "다" * 150
        full = an.compose_ready(NUMBER, "[M105] 짧은 제목", body, SHA)
        self.assertLessEqual(len(full), an.MESSAGE_LIMIT)
        self.assertEqual(an.message_problem(full), "")
        crowded = an.compose_ready(NUMBER, long_title[:200], body, SHA)
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
            exact = len(an._ready_text(head, points[:kept], NUMBER, SHA))
            for limit, expected in ((exact, kept), (exact - 1, kept - 1), (exact + 1, kept)):
                with self.subTest(kept=kept, limit=limit):
                    with mock.patch.object(an, "MESSAGE_LIMIT", limit):
                        text = an.compose_ready(NUMBER, "[M105] 제목", body, SHA)
                        self.assertEqual(len([line for line in text.split("\n") if line.startswith("- ")]), expected)
                        self.assertLessEqual(len(text), limit)
                        self.assertEqual(an.message_problem(text), "")

    def test_five_full_length_points_under_the_real_limit(self):
        """실제 상한(800자)에서 제목 80자 + 요점 5줄(줄당 120자)은 정확히 계산한 대로 들어가거나(들어가면 5줄) 마지막 줄부터 빠진다."""
        body = "\n".join("- " + chr(0xAC00 + index) * 120 for index in range(5))
        text = an.compose_ready(NUMBER, "[M105] " + "제" * 80, body, SHA)
        points = [line for line in text.split("\n") if line.startswith("- ")]
        full = len(an._ready_text(text.split("\n")[0], [chr(0xAC00 + index) * 120 for index in range(5)], NUMBER, SHA))
        self.assertEqual(len(points), 5 if full <= an.MESSAGE_LIMIT else 4)
        self.assertLessEqual(len(text), an.MESSAGE_LIMIT)

    def test_a_title_that_cannot_be_sent_stops_the_message(self):
        bad = {"mention": "[M105] 담당 " + AT + "someone", "address": "[M105] " + SCHEME + "evil.example", "secret": "[M105] 키 " + nh.TOKEN, "control": "[M105] 제목\x01숨김",
               "empty": "[M105] ", "blank": "[M105]    ", "long": "[M105] " + "가" * 194, "invisible": "[M105] 제목" + chr(0x200B)}
        for label, title in bad.items():
            with self.subTest(label):
                with self.assertRaises(an.Skip) as caught:
                    an.compose_ready(NUMBER, title, BODY, SHA)
                self.assertEqual(caught.exception.code, "title_problem")

    def test_a_shape_made_by_cutting_the_title_stops_the_message_too(self):
        """제목을 80자로 자르다가 꼬리가 끊겨 새로 생긴 도메인 꼴·비밀 꼴도 거른다(자르기 전 제목 전체에는 없던 모양) — 요점 줄의 '자른 뒤에도 한 번 더' 와 같은 규칙. 퍼징(씨앗 777)이 찾은 꼴이다."""
        for label, tail in (("address", "node" + DOT + "js" + "x" * 40), ("aws key", AWS_KEY_SHAPE[:4] + "C" * 40)):
            pad = "가" * (50 if label == "address" else 58) + ("" if label == "address" else " ")
            title = "[M105] " + pad + tail
            rest = title[len("[M105] "):]
            with self.subTest(label):
                self.assertEqual(an.line_problem(rest), "")                                           # 전제: 자르기 전 제목 전체에는 그 모양이 없다(영문 꼬리가 24자·16자를 넘는다)
                self.assertNotEqual(an.line_problem(an.shorten(rest, an.READY_TITLE_LIMIT)), "")      # 전제: 자른 뒤에는 그 모양이 된다
                with self.assertRaises(an.Skip) as caught:
                    an.compose_ready(NUMBER, title, BODY, SHA)
                self.assertEqual(caught.exception.code, "title_problem")
        ok = "[M105] " + "가" * 50 + "node" + DOT + "js 로 정리"                                           # 대조: 자르지 않아도 되는 정상 제목
        self.assertEqual(an.message_problem(an.compose_ready(NUMBER, ok, BODY, SHA)), "")

    def test_a_title_of_200_characters_is_allowed_and_201_is_not(self):
        self.assertEqual(an.message_problem(an.compose_ready(NUMBER, "[M105] " + "가" * 193, "", SHA)), "")
        with self.assertRaises(an.Skip):
            an.compose_ready(NUMBER, "[M105] " + "가" * 194, "", SHA)

    def test_a_title_must_start_with_the_same_number(self):
        for title in ("그냥 제목", "[M106] 다른 번호", "[M105]붙어 있음", "[m105] 소문자", " [M105] 앞 공백", "[M0105] 네 자리 앞 0", "[M1050] 다른 번호", "[R-105] 요청 번호", None, 5):
            with self.subTest(str(title)):
                with self.assertRaises(an.Skip) as caught:
                    an.compose_ready(NUMBER, title, BODY, SHA)
                self.assertEqual(caught.exception.code, "title_shape")

    def test_a_number_that_is_not_a_merge_notice_number_is_refused(self):
        for number in ("M000", "M0105", "M10", "P105", "105", "m105", "M12345", "", None):
            with self.subTest(str(number)):
                with self.assertRaises(an.Skip):
                    an.compose_ready(number, f"[{number}] 제목", BODY, SHA)

    def test_tildes_in_the_title_become_en_dashes_and_never_reach_the_message(self):
        text = an.compose_ready(NUMBER, "[M105] 약 10" + TILDE + "20개 " + chr(0xFF5E), "- 본문 " + TILDE + " 줄", SHA)
        self.assertNotIn(TILDE, text)
        self.assertNotIn(chr(0xFF5E), text)
        self.assertIn("10" + chr(0x2013) + "20개", text)

    def test_markdown_and_backticks_are_stripped_from_the_title(self):
        text = an.compose_ready(NUMBER, "[M105] **굵게** `코드` 제목", "", SHA)
        self.assertEqual(text.split("\n")[0], "[M105] 병합 부탁 — 굵게 코드 제목")

    def test_a_body_with_bad_lines_still_gives_a_valid_message(self):
        body = "- " + SCHEME + "evil.example\n- 담당 " + AT + "a\n- 좋은 줄\n- 비밀 " + nh.TOKEN
        text = an.compose_ready(NUMBER, TITLE, body, SHA)
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
        self.assertEqual(an.compose_confirm(NUMBER, [], an.NOTE_TWO_PARENTS), text)                      # 문자열 하나도, 목록도 받는다

    def test_ok_with_both_notes_has_one_line_per_note_in_the_fixed_order(self):
        text = an.compose_confirm(NUMBER, [], [an.NOTE_TWO_PARENTS, an.NOTE_NO_CONTENT])
        self.assertEqual(text.split("\n"), ["[M105] 병합완료 확인 - 정상", an.NOTE_TWO_PARENTS, an.NOTE_NO_CONTENT])
        self.assertEqual(an.message_problem(text), "")
        self.assertEqual(an.CONFIRM_NOTES, (an.NOTE_TWO_PARENTS, an.NOTE_NO_CONTENT))
        for note in an.CONFIRM_NOTES:
            self.assertIn("참고", note)
            self.assertEqual(an.line_problem(note), "")
            self.assertLessEqual(len(note), an.REASON_LIMIT)

    def test_bad_is_the_title_plus_one_reason_line_within_100_characters(self):
        """compose_confirm 은 받은 사유 글을 그대로 한 줄에 싣는다(고정 문장인지는 message_problem 이 본다 — 아래 시험)."""
        text = an.compose_confirm(NUMBER, ["이유 하나"])
        self.assertEqual(text, "[M105] 병합완료 확인 - 이상\n이유 하나")
        many = an.compose_confirm(NUMBER, ["첫 이유", "둘째", "셋째"])
        self.assertEqual(many.split("\n")[1], "첫 이유 (외 2건)")
        long = an.compose_confirm(NUMBER, ["가" * 300, "x"])
        self.assertEqual(len(long.split("\n")[1]), 100)                                                 # 상수를 읽지 않고 100자 그대로 — 사유 한 줄은 정확히 100자에서 잘린다
        self.assertEqual(an.REASON_LIMIT, 100)
        self.assertTrue(long.split("\n")[1].endswith(chr(0x2026)))
        self.assertNotEqual(an.message_problem(long), "")                                              # 고정 사유가 아닌 글은 보낼 수 없다

    def test_every_fixed_reason_fits_in_one_line_with_the_longest_suffix_and_is_a_valid_message(self):
        reasons = [an.REASON_CONCLUSION.format(word) for word in sorted(an.CONCLUSION_WORDS) + [an.UNKNOWN_CONCLUSION]] + [an.REASON_PARENTS.format(count) for count in (0, 3, 999999)] + [
            an.REASON_MERGE_COMMIT, an.REASON_BASE, an.REASON_NUMBER, an.REASON_FILES.format(0, 0), an.REASON_FILES.format(300, 300), an.REASON_FILES.format(123456, 654321)]
        for reason in reasons:
            for suffix in ("", " (외 1건)", " (외 5건)", " (외 99건)"):
                with self.subTest(reason + suffix):
                    line = reason + suffix
                    self.assertLessEqual(len(line), an.REASON_LIMIT)                                     # 줄여지지 않으니 고정 사유가 그대로 실린다
                    text = an.compose_confirm(NUMBER, [reason] + ["x"] * (int(suffix[4:-2]) if suffix else 0))
                    self.assertEqual(text.split("\n")[1], line)
                    self.assertEqual(an.message_problem(text), "")

    def test_a_bad_number_is_refused(self):
        for number in ("M000", "P105", "105", "M0105", "", None):
            with self.subTest(str(number)):
                with self.assertRaises(ValueError):
                    an.compose_confirm(number, [])


class MessageProblemTest(unittest.TestCase):
    def test_valid_messages_pass(self):
        for text in (an.compose_ready(NUMBER, TITLE, BODY, SHA), an.compose_ready("M1234", "[M1234] 제목", "", SHA), an.compose_confirm(NUMBER, []), an.compose_confirm(NUMBER, [an.REASON_BASE]),
                     an.compose_confirm(NUMBER, [], [an.NOTE_TWO_PARENTS]), an.compose_confirm(NUMBER, [], [an.NOTE_NO_CONTENT]), an.compose_confirm(NUMBER, [], list(an.CONFIRM_NOTES)),
                     an.compose_confirm(NUMBER, [an.REASON_FILES.format(2, 3), an.REASON_NUMBER, an.REASON_MERGE_COMMIT])):
            self.assertEqual(an.message_problem(text), "", text)

    def test_the_message_must_have_the_shape_the_code_makes_not_only_clean_characters(self):
        """AN1-S-5: 발송 job 의 재검사는 '글자가 깨끗한가' 에 더해 '문장 모양이 코드가 만드는 것과 같은가' 를 본다 — 깨끗한 글자로 된 임의 문장도 통과하지 못한다."""
        ok = "[M105] 병합완료 확인 - 정상"
        bad = "[M105] 병합완료 확인 - 이상"
        shapes = {
            "ok + free second line": ok + "\n임의 문장 승인했습니다",
            "ok + both notes in the wrong order": ok + "\n" + an.NOTE_NO_CONTENT + "\n" + an.NOTE_TWO_PARENTS,
            "ok + the same note twice": ok + "\n" + an.NOTE_TWO_PARENTS + "\n" + an.NOTE_TWO_PARENTS,
            "ok + note + free line": ok + "\n" + an.NOTE_TWO_PARENTS + "\n임의",
            "ok + note with a changed digit": ok + "\n" + an.NOTE_TWO_PARENTS.replace("2개", "3개"),
            "ok + a reason line": ok + "\n" + an.REASON_BASE,
            "bad + free reason": bad + "\n임의 사유 — 안전합니다",
            "bad + a note instead of a reason": bad + "\n" + an.NOTE_TWO_PARENTS,
            "bad + reason + extra line": bad + "\n" + an.REASON_BASE + "\n추가",
            "bad + two reasons": bad + "\n" + an.REASON_BASE + "\n" + an.REASON_NUMBER,
            "bad + reason with an unknown conclusion": bad + "\n" + an.REASON_CONCLUSION.format("great"),
            "bad + reason with a non-number": bad + "\n" + an.REASON_PARENTS.format("many"),
            "bad + reason with a 7-digit number": bad + "\n" + an.REASON_PARENTS.format(1234567),
            "bad + reason + malformed count": bad + "\n" + an.REASON_BASE + " (외 건)",
            "bad + reason + 3-digit count": bad + "\n" + an.REASON_BASE + " (외 100건)",
            "bad + reason + trailing text": bad + "\n" + an.REASON_BASE + " 괜찮습니다",
            "bad + reason cut short": bad + "\n" + an.REASON_BASE[:-3],
        }
        for label, text in shapes.items():
            with self.subTest(label):
                self.assertEqual(an.message_problem(text), "shape", text)

    def test_the_ready_message_is_rechecked_for_the_title_length_markup_and_spacing(self):
        """병합 부탁은 제목 부분 80자 상한·요점 줄의 백틱·`**`·정리되지 않은 공백도 발송 job 이 다시 거른다(compose 만 지키던 규칙)."""
        good = an.compose_ready(NUMBER, TITLE, BODY, SHA)
        self.assertEqual(an.message_problem(good), "")
        head = "[M105] 병합 부탁 — "
        lines = good.split("\n")
        self.assertEqual(an.message_problem("\n".join([head + "가" * 80] + lines[1:])), "")
        self.assertEqual(an.message_problem("\n".join([head + "가" * 81] + lines[1:])), "shape")
        for label, text in {"backtick in a point": good.replace("시험: 새 시험을", "시험: `새` 시험을"), "bold in a point": good.replace("시험: 새 시험을", "시험: **새** 시험을"),
                            "backtick in the title": good.replace("워크플로 둘", "`워크플로` 둘", 1), "double space in a point": good.replace("시험: 새", "시험:  새"),
                            "trailing space in a point": good.replace("새 시험을 더했다", "새 시험을 더했다 "), "leading space in the title": good.replace(head, head + " ", 1),
                            "tab in a point": good.replace("시험: 새", "시험:\t새")}.items():
            with self.subTest(label):
                self.assertNotEqual(an.message_problem(text), "", label)

    def test_every_broken_variant_is_refused(self):
        ready = an.compose_ready(NUMBER, TITLE, BODY, SHA)
        lines = ready.split("\n")
        broken = {
            "empty": "", "blank": "  \n ", "none": None, "number": 5,
            "too long": ready + "\n" + "가" * 800,
            "trailing newline": ready + "\n",
            "leading newline": "\n" + ready,
            "wrong first line dash": ready.replace("병합 부탁 — ", "병합 부탁 - ", 1),
            "no first line text": "[M105] 병합 부탁 — \n\n검사: 초록\n" + HEADLINE + "\n\n" + TAIL,
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

    def test_the_refusal_codes_empty_and_too_long_are_exact_and_the_longest_valid_message_is_exactly_the_limit(self):
        """코드마다 이유가 정확하다 — 빈 글·공백뿐인 글·문자열이 아닌 값은 empty, 800자를 넘으면 too_long(경계 800/801 — 줄을 나눠도 글자 수로 센다), 그 밖은 shape·line. 구조상 만들 수 있는
        가장 긴 병합 부탁(번호 4자리·제목 80자·요점 5줄×120자)은 정확히 800자라 too_long 은 모양이 맞는 문장을 거절하지 않고 모양이 틀린 긴 글에만 닿는다."""
        for value in ("", " ", "  \n \t", "\n", None, 5, b"x", ["a"]):
            with self.subTest(repr(value)):
                self.assertEqual(an.message_problem(value), "empty")
        self.assertEqual(an.message_problem("가" * 801), "too_long")
        self.assertEqual(an.message_problem("가" * 800), "shape")                 # 글자 수는 한도 안 — 모양이 틀려 거절
        self.assertEqual(an.message_problem("가\n" * 401), "too_long")             # 802자
        self.assertEqual(an.message_problem("가\n" * 400), "shape")                # 800자 — 길이는 한도 안, 모양이 틀려 거절
        points = "\n".join("- " + "나" * 120 for _ in range(5))
        for flagged in (False, True):
            longest = an.compose_ready("M1234", "[M1234] " + "가" * 80, points, SHA, flagged)
            self.assertLessEqual(len(longest), an.MESSAGE_LIMIT)
            self.assertEqual(an.message_problem(longest), "")                                       # 만들 수 있는 가장 긴 문장도 상한 안이라 too_long 은 모양이 맞는 문장을 거절하지 않는다
            self.assertEqual(longest.count("\n- "), 4)                                              # 머리 커밋 줄(·검사 정의 변경 줄)이 800자 안에서 자리를 차지해 다섯째 요점이 먼저 빠진다
            head = longest.split("\n")[0]
            five = an._ready_text(head, ["나" * 120] * 5, "M1234", SHA, flagged)
            self.assertGreater(len(five), an.MESSAGE_LIMIT)
            self.assertEqual(an.message_problem(five), "too_long")                                  # 요점 다섯 줄을 다 넣은 문장은 코드가 만들지 않는 모양이라 상한에서 거절된다
            exact = [length for length in range(1, 121) if len(an._ready_text(head, ["나" * 120] * 4 + ["다" * length], "M1234", SHA, flagged)) == an.MESSAGE_LIMIT]
            self.assertEqual(len(exact), 1)                                                         # 요점 다섯째 줄 길이를 하나씩 바꿔 정확히 800자가 되는 길이를 찾는다(경계)
            at_limit = an._ready_text(head, ["나" * 120] * 4 + ["다" * exact[0]], "M1234", SHA, flagged)
            over = an._ready_text(head, ["나" * 120] * 4 + ["다" * (exact[0] + 1)], "M1234", SHA, flagged)
            self.assertEqual((len(at_limit), len(over), an.message_problem(at_limit), an.message_problem(over)), (an.MESSAGE_LIMIT, an.MESSAGE_LIMIT + 1, "", "too_long"))

    def test_a_point_line_is_valid_up_to_exactly_120_characters_and_at_most_five_points(self):
        """요점 줄의 경계는 정확하다 — `- ` 머리 뒤 120자까지 통과하고 121자부터 거절, 요점 다섯 줄까지 통과하고 여섯 줄부터 거절(상수가 아니라 글자 수 그대로)."""
        base = an.compose_ready(NUMBER, TITLE, "", SHA).split("\n")               # 제목·빈 줄·검사 줄·머리 커밋 줄·빈 줄·고정 꼬리

        def with_points(points):
            return "\n".join(base[:2] + points + [""] + base[2:])
        self.assertEqual((an.POINT_LIMIT, an.POINT_LINES), (120, 5))
        self.assertEqual(an.message_problem(with_points(["- " + "가" * 120])), "")
        self.assertEqual(an.message_problem(with_points(["- " + "가" * 121])), "shape")
        self.assertEqual(an.message_problem(with_points(["- 가"] * 5)), "")
        self.assertEqual(an.message_problem(with_points(["- 가"] * 6)), "shape")

    def test_a_clean_free_line_in_any_place_of_the_ready_message_is_refused(self):
        """AN1-S-5: 병합 부탁의 줄 자리는 모두 고정이다 — 제목 다음 빈 줄·요점 뒤 빈 줄·검사 줄 뒤 빈 줄을 깨끗한 임의 한 줄로 바꾸거나 어느 자리에든 한 줄을 끼워도(그 자리들은 요점 검사 밖이라
        글자 규칙만으로는 통과한다) 모양 검사가 거절한다."""
        free = "임의 문장 승인했습니다"
        self.assertEqual(an.line_problem(free), "")                                # 전제: 끼우는 줄은 글자로는 깨끗하다
        for label, body in {"with points": BODY, "without points": ""}.items():
            ready = an.compose_ready(NUMBER, TITLE, body, SHA)
            lines = ready.split("\n")
            self.assertEqual(an.message_problem(ready), "", label)
            variants = {f"replace blank line {index}": lines[:index] + [free] + lines[index + 1:] for index, line in enumerate(lines) if line == ""}
            variants.update({f"insert at {index}": lines[:index] + [free] + lines[index:] for index in range(1, len(lines) + 1)})
            self.assertGreaterEqual(lines.count(""), 2)                           # 전제: 빈 줄이 (요점이 없어도) 둘 이상 있다 — 자리마다 바꿔 본다
            self.assertEqual(len(variants), lines.count("") + len(lines))
            for name, changed in variants.items():
                with self.subTest((label, name)):
                    self.assertEqual(an.message_problem("\n".join(changed)), "shape")


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
        self.assertEqual(verdict.text, an.compose_ready(NUMBER, TITLE, BODY, SHA))
        self.assertEqual(api.methods(), {"GET"})
        self.assertEqual(api.calls[0][1:3], ("/pulls", {"state": "open", "head": "octo:" + BRANCH, "base": "main", "per_page": 5}))
        self.assertEqual(api.calls[1][1:3], (f"/pulls/{PR_NUMBER}/files", {"per_page": 100, "page": 1}))                          # PR 머리를 확인한 바로 뒤, 검사 실행을 기다리기 전에 변경 파일을 읽는다
        self.assertEqual(api.calls[2][1:3], ("/actions/runs", {"branch": BRANCH, "head_sha": SHA, "event": "push", "per_page": 100}))
        self.assertEqual(len(api.calls), 3)
        self.assertTrue(all(call[3] is None for call in api.calls))                       # 보내는 본문이 없다
        self.assertEqual(verdict.notes[0], f"열린 PR #{PR_NUMBER} 하나이고 머리 커밋이 이 실행의 커밋과 같음")      # 요약에 남는 확인 문장은 고정 문장과 PR 번호뿐이다
        self.assertTrue(all(TITLE not in note and AT not in note for note in verdict.notes))

    def test_a_pull_request_number_below_one_is_a_shape_problem_and_one_itself_is_fine(self):
        for number in (0, -1, -250):
            with self.subTest(number):
                self.assertEqual(self.skipped(ready_routes(prs=[pr_item(number=number)])), "api_shape")
        verdict, _ = self.evaluate(ready_routes(prs=[pr_item(number=1)]))
        self.assertEqual(verdict.notes[0], "열린 PR #1 하나이고 머리 커밋이 이 실행의 커밋과 같음")

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
        self.assertEqual(self.evaluate(ready_routes(prs=[pr]))[0].text, an.compose_ready(NUMBER, TITLE, BODY, SHA))

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
        api = FakeApi({**ready_routes(), "/actions/runs": pending})
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
        api = FakeApi({**ready_routes(), "/actions/runs": Seq(pending, pending, done)})
        verdict = an.evaluate_ready(an.read_inputs(ready_env(), an.READY), an.Reader(api), sleeps.append)
        self.assertEqual(verdict.text, an.compose_ready(NUMBER, TITLE, BODY, SHA))
        self.assertEqual(sleeps, [20, 20])

    def test_a_failure_while_waiting_stops_at_once(self):
        sleeps = []
        api = FakeApi({**ready_routes(), "/actions/runs": Seq({"workflow_runs": good_runs() + [run_item(90, status="in_progress", conclusion=None)]},
                                                                    {"workflow_runs": good_runs() + [run_item(90, conclusion="failure")]})})
        with self.assertRaises(an.Skip) as caught:
            an.evaluate_ready(an.read_inputs(ready_env(), an.READY), an.Reader(api), sleeps.append)
        self.assertEqual((caught.exception.code, sleeps), ("checks_failed", [20]))

    def test_unreadable_answers_are_errors_not_notices(self):
        self.assertEqual(self.skipped({"/pulls": ol.GitHubError("HTTP 500", 500), "/actions/runs": {"workflow_runs": []}}), "api_error")
        self.assertEqual(self.skipped({**ready_routes(), "/actions/runs": ol.GitHubError("연결 오류(OSError)")}), "api_error")
        self.assertEqual(self.skipped({"/pulls": [pr_item()], f"/pulls/{PR_NUMBER}/files": file_items(DEFAULT_FILES)}), "api_error")      # 없는 경로는 404 → 읽기 실패
        no_files = ready_routes()
        del no_files[f"/pulls/{PR_NUMBER}/files"]
        self.assertEqual(self.skipped(no_files), "api_error")                                    # 변경 파일 목록을 못 읽으면(404) 알리지 않는다
        self.assertEqual(self.skipped({**ready_routes(), f"/pulls/{PR_NUMBER}/files": ol.GitHubError("HTTP 500", 500)}), "api_error")

    def test_an_empty_list_of_changed_files_is_not_read_as_no_definition_change(self):
        """독립 시험 검증 Q: 읽기는 성공했는데 변경 파일이 0건이면 '검사 정의가 바뀐 PR: 아니오' 로 읽어 보내지 않는다 — 바뀐 파일 없는 열린 PR 은 모양이 이상하므로 알리지 않는다(api_shape, 닫힌 쪽)."""
        self.assertEqual(self.skipped(ready_routes(files=[])), "api_shape")
        verdict, _ = self.evaluate(ready_routes(files=["docs/a.md"]))                         # 대조: 파일이 하나라도 있으면 알린다
        self.assertEqual(verdict.text, an.compose_ready(NUMBER, TITLE, BODY, SHA))

    def test_wrongly_shaped_answers_are_shape_problems(self):
        shapes = [({"/pulls": {"x": 1}, "/actions/runs": {}}, "api_shape"), ({"/pulls": None, "/actions/runs": {}}, "api_shape"), ({"/pulls": ["x"], "/actions/runs": {}}, "api_shape"),
                  ({"/pulls": [{"number": PR_NUMBER}], "/actions/runs": {}}, "api_shape"), ({"/pulls": [pr_item(number="x")], "/actions/runs": {}}, "api_shape"),
                  ({"/pulls": [pr_item(number=0)], "/actions/runs": {}}, "api_shape"), ({"/pulls": [pr_item(number=True)], "/actions/runs": {}}, "api_shape"),
                  ({"/pulls": [pr_item(head=None)], "/actions/runs": {}}, "api_shape"), ({**ready_routes(), "/actions/runs": []}, "api_shape"),
                  ({**ready_routes(), "/actions/runs": {"workflow_runs": "x"}}, "api_shape"), ({**ready_routes(), "/actions/runs": {"workflow_runs": [5]}}, "api_shape"),
                  ({**ready_routes(), f"/pulls/{PR_NUMBER}/files": {"x": 1}}, "api_shape"), ({**ready_routes(), f"/pulls/{PR_NUMBER}/files": None}, "api_shape"),
                  ({**ready_routes(), f"/pulls/{PR_NUMBER}/files": [5]}, "api_shape"), ({**ready_routes(), f"/pulls/{PR_NUMBER}/files": [{"sha": "x"}]}, "api_shape"),
                  ({**ready_routes(), f"/pulls/{PR_NUMBER}/files": [{"filename": ""}]}, "api_shape"), ({**ready_routes(), f"/pulls/{PR_NUMBER}/files": [{"filename": 5}]}, "api_shape")]
        for routes, code in shapes:
            with self.subTest(str(routes)[:60]):
                self.assertEqual(self.skipped(routes), code)


# ----------------------------------------------------------------------------
# 검사 정의가 바뀐 PR 표시와 머리 커밋 7자리(독립 감사 BA-S2 R2·N6, 결함 D-467)
# ----------------------------------------------------------------------------
def many_files(count, prefix="docs/f"):
    return [f"{prefix}{index:03d}.md" for index in range(count)]


class CheckDefinitionPathsTest(unittest.TestCase):
    """touches_check_definition: 검사 정의는 `.github/`·`tests/` 아래와 `scripts/validate_repo.py`·`AGENTS.md`·`docs/SECURITY_GUARDRAILS.md` 뿐이다 — 이 경로가 바뀐 PR 의 초록은 바뀐 규칙으로 낸 값이다
    (push 로 도는 검사는 push 한 커밋의 파일 그대로 돈다). 비슷하게 생긴 이름은 검사 정의가 아니다(경로는 글자 그대로 견준다)."""

    DEFINITION_PATHS = (".github/workflows/guardrails.yml", ".github/workflows/merge-ready-notice.yml", ".github/ISSUE_TEMPLATE/ai-task.yml", ".github/CODEOWNERS", "scripts/validate_repo.py",
                        "tests/test_auto_notice.py", "tests/sub/helper.py", "tests/__init__.py", "tests/_bootstrap.py", "AGENTS.md", "docs/SECURITY_GUARDRAILS.md")
    PLAIN_PATHS = ("docs/ARCHITECTURE.md", "pipeline/auto_notice.py", "scripts/github_status.py", "scripts/validate_repo.pyc", "scripts/validate_repo.py.bak", "scripts/validate_repo_helpers.py",
                   "scripts/sub/validate_repo.py", "xtests/a.py", "mytests/a.py", "tests", ".github", ".githubx/a.yml", "a/.github/b.yml", "a/tests/b.py", "AGENTS.md.bak", "docs/AGENTS.md",
                   "sub/AGENTS.md", "docs/SECURITY_GUARDRAILS.md.old", "docs/security_guardrails.md", "docs/SECURITY_GUARDRAILS.txt", "Tests/a.py", "TESTS/a.py", "WORKLOG.md", "README.md",
                   "인수인계/작업내용.md")

    def test_the_lists_are_exactly_these_and_nothing_else(self):
        self.assertEqual(an.CHECK_DEFINITION_FILES, ("scripts/validate_repo.py", "AGENTS.md", "docs/SECURITY_GUARDRAILS.md"))
        self.assertEqual(an.CHECK_DEFINITION_DIRS, (".github/", "tests/"))

    def test_every_definition_path_is_found_alone_and_among_plain_ones(self):
        for path in self.DEFINITION_PATHS:
            with self.subTest(path):
                self.assertTrue(an.touches_check_definition({path}))
                self.assertTrue(an.touches_check_definition({path, *self.PLAIN_PATHS}))
                self.assertTrue(an.touches_check_definition([path]))                                   # 목록·집합·튜플 어느 것이든

    def test_lookalikes_and_plain_paths_are_not_definitions_alone_or_together(self):
        for path in self.PLAIN_PATHS:
            with self.subTest(path):
                self.assertFalse(an.touches_check_definition({path}))
        self.assertFalse(an.touches_check_definition(set(self.PLAIN_PATHS)))
        self.assertFalse(an.touches_check_definition(set()))
        self.assertFalse(an.touches_check_definition([]))


class ReadPrPathsTest(unittest.TestCase):
    """read_pr_paths: 병합완료 확인과 같은 `GET /pulls/{번호}/files`(100개씩·세 쪽까지). 다 읽었다고 말할 수 없으면 Skip, 이름을 바꾼 파일은 옛 이름도 센다."""

    PATH = f"/pulls/{PR_NUMBER}/files"

    def read(self, routes):
        api = FakeApi(routes)
        return an.read_pr_paths(an.Reader(api), PR_NUMBER), api

    def pages(self, *page_files):
        return {(self.PATH, number): file_items(files) for number, files in enumerate(page_files, 1)}

    def skipped(self, routes):
        with self.assertRaises(an.Skip) as caught:
            self.read(routes)
        return caught.exception.code

    def test_a_short_listing_is_read_with_one_request(self):
        paths, api = self.read({self.PATH: file_items(["a.md", "b/c.py"])})
        self.assertEqual(paths, {"a.md", "b/c.py"})
        self.assertEqual([(call[0], call[1], call[2], call[3]) for call in api.calls], [("GET", self.PATH, {"per_page": 100, "page": 1}, None)])

    def test_an_empty_listing_is_an_empty_set_and_a_single_request(self):
        paths, api = self.read({self.PATH: []})
        self.assertEqual((paths, len(api.calls)), (set(), 1))

    def test_a_renamed_file_counts_with_both_names_and_so_does_a_removed_one(self):
        entries = [{"filename": "docs/x.md", "previous_filename": "tests/test_x.py", "status": "renamed"}, {"filename": "tests/test_y.py", "status": "removed"},
                   {"filename": "a.md", "previous_filename": 5}, {"filename": "b.md", "previous_filename": ""}, {"filename": "c.md", "previous_filename": None}]
        paths, _ = self.read({self.PATH: entries})
        self.assertEqual(paths, {"docs/x.md", "tests/test_x.py", "tests/test_y.py", "a.md", "b.md", "c.md"})
        self.assertTrue(an.touches_check_definition(paths))
        moved_out, _ = self.read({self.PATH: [{"filename": "docs/x.md", "previous_filename": "tests/test_x.py"}]})
        self.assertTrue(an.touches_check_definition(moved_out))                                       # 시험을 tests/ 밖으로 옮겨 지우는 길도 검사 정의 변경이다
        self.assertFalse(an.touches_check_definition({"docs/x.md"}))                                  # 옛 이름을 안 보면 보이지 않던 것(대조)

    def test_full_pages_are_followed_until_a_short_one_with_each_page_number_asked_once(self):
        first, second, third = many_files(100, "a/"), many_files(100, "b/"), many_files(5, "c/")
        paths, api = self.read(self.pages(first, second, third))
        self.assertEqual(paths, set(first) | set(second) | set(third))
        self.assertEqual([call[2]["page"] for call in api.calls], [1, 2, 3])
        self.assertTrue(all(call[1] == self.PATH and call[2]["per_page"] == 100 for call in api.calls))

    def test_exactly_three_full_pages_are_complete_only_if_the_next_page_is_empty(self):
        first, second, third = many_files(100, "a/"), many_files(100, "b/"), many_files(100, "c/")
        paths, api = self.read(self.pages(first, second, third, []))
        self.assertEqual((len(paths), [call[2]["page"] for call in api.calls]), (300, [1, 2, 3, 4]))
        self.assertEqual(self.skipped(self.pages(first, second, third, ["d/one.md"])), "too_large")      # 300개를 넘는 PR — 다 읽었다고 말할 수 없다
        self.assertEqual(self.skipped(self.pages(first, second, third, many_files(100, "d/"))), "too_large")

    def test_a_definition_file_on_the_last_page_is_still_found(self):
        first, second = many_files(100, "a/"), many_files(100, "b/")
        third = many_files(99, "c/") + ["tests/test_late.py"]
        paths, _ = self.read(self.pages(first, second, third, []))
        self.assertTrue(an.touches_check_definition(paths))
        self.assertFalse(an.touches_check_definition(self.read(self.pages(first, second, many_files(100, "c/"), []))[0]))

    def test_the_request_count_is_bounded_even_for_an_endless_listing(self):
        endless = {self.PATH: file_items(many_files(100))}                          # 쪽 번호와 상관없이 늘 가득 찬 응답
        api = FakeApi(endless)
        with self.assertRaises(an.Skip) as caught:
            an.read_pr_paths(an.Reader(api), PR_NUMBER)
        self.assertEqual((caught.exception.code, len(api.calls)), ("too_large", an.FILE_PAGES_MAX + 1))

    def test_wrong_shapes_and_failed_reads_are_skips_not_crashes(self):
        for label, value, code in (("not a list", {"x": 1}, "api_shape"), ("none", None, "api_shape"), ("number item", [5], "api_shape"), ("no filename", [{"sha": "x"}], "api_shape"),
                                   ("empty filename", [{"filename": ""}], "api_shape"), ("number filename", [{"filename": 5}], "api_shape"), ("string", "x", "api_shape"),
                                   ("http error", ol.GitHubError("HTTP 500", 500), "api_error")):
            with self.subTest(label):
                self.assertEqual(self.skipped({self.PATH: value}), code)
        self.assertEqual(self.skipped({}), "api_error")                             # 없는 경로는 404 → 읽기 실패


class ReadyDefinitionLineTest(unittest.TestCase):
    """evaluate_ready: 변경 파일에 검사 정의가 있으면 문장에 DEFINITION 한 줄이 붙고, 머리 커밋 7자리는 늘 붙는다. 변경 파일은 PR 머리를 확인한 바로 뒤·검사 실행을 기다리기 전에 읽는다."""

    def evaluate(self, files=None, **env):
        api = FakeApi(ready_routes(files=files))
        verdict = an.evaluate_ready(an.read_inputs(ready_env(**env), an.READY), an.Reader(api), no_sleep)
        return verdict, api

    def test_plain_files_give_the_head_line_and_no_definition_line(self):
        verdict, _ = self.evaluate()
        lines = verdict.text.split("\n")
        self.assertIn(HEADLINE, lines)
        self.assertNotIn(DEFINITION, lines)
        self.assertEqual(verdict.text, an.compose_ready(NUMBER, TITLE, BODY, SHA, False))
        self.assertEqual(an.message_problem(verdict.text), "")

    def test_each_definition_file_adds_exactly_one_definition_line_right_after_the_check_line(self):
        for path in CheckDefinitionPathsTest.DEFINITION_PATHS:
            with self.subTest(path):
                verdict, _ = self.evaluate(["docs/ARCHITECTURE.md", path])
                lines = verdict.text.split("\n")
                self.assertEqual(lines.count(DEFINITION), 1)
                self.assertEqual(lines[lines.index("검사: 초록") + 1], DEFINITION)
                self.assertEqual(lines[lines.index(DEFINITION) + 1], HEADLINE)                       # 검사 줄 → 정의 변경 줄 → 머리 커밋 줄
                self.assertEqual(verdict.text, an.compose_ready(NUMBER, TITLE, BODY, SHA, True))
                self.assertEqual(an.message_problem(verdict.text), "")

    def test_a_file_moved_out_of_the_tests_folder_is_flagged_through_its_old_name(self):
        verdict, _ = self.evaluate([{"filename": "docs/x.md", "previous_filename": "tests/test_x.py", "status": "renamed"}])
        self.assertIn(DEFINITION, verdict.text.split("\n"))

    def test_the_summary_notes_say_whether_the_definition_changed_with_fixed_sentences_only(self):
        plain, _ = self.evaluate()
        flagged, _ = self.evaluate([".github/workflows/guardrails.yml"])
        self.assertEqual(plain.notes[2], "PR 의 변경 파일을 읽음 — 검사 정의가 바뀐 PR: 아니오")
        self.assertEqual(flagged.notes[2], "PR 의 변경 파일을 읽음 — 검사 정의가 바뀐 PR: 예(문장에 경고 한 줄)")
        for note in plain.notes + flagged.notes:
            self.assertNotIn("guardrails", note)                                                     # 파일 이름은 요약에 싣지 않는다(고정 문장과 번호·정수만)
            self.assertNotIn(TITLE, note)

    def test_the_files_are_read_right_after_the_pull_request_and_before_the_checks(self):
        _, api = self.evaluate()
        self.assertEqual(api.paths(), ["/pulls", f"/pulls/{PR_NUMBER}/files", "/actions/runs"])
        self.assertEqual(api.methods(), {"GET"})

    def test_the_files_are_not_read_when_the_pull_request_is_not_usable(self):
        for label, routes in {"no pr": ready_routes(prs=[]), "two prs": ready_routes(prs=[pr_item(), pr_item(number=249)]), "closed": ready_routes(prs=[pr_item(state="closed")]),
                              "other head": ready_routes(prs=[pr_item(head={"ref": BRANCH, "sha": OTHER_SHA, "repo": {"full_name": REPO}})]), "draft": ready_routes(prs=[pr_item(draft=True)])}.items():
            with self.subTest(label):
                api = FakeApi(routes)
                with self.assertRaises(an.Skip):
                    an.evaluate_ready(an.read_inputs(ready_env(), an.READY), an.Reader(api), no_sleep)
                self.assertEqual(api.paths(), ["/pulls"])

    def test_a_listing_that_cannot_be_read_to_the_end_sends_nothing(self):
        routes = ready_routes()
        routes[f"/pulls/{PR_NUMBER}/files"] = file_items(many_files(100))
        api = FakeApi(routes)
        with self.assertRaises(an.Skip) as caught:
            an.evaluate_ready(an.read_inputs(ready_env(), an.READY), an.Reader(api), no_sleep)
        self.assertEqual(caught.exception.code, "too_large")
        self.assertNotIn("/actions/runs", api.paths())                                               # 검사 실행도 보지 않고 끝난다
        self.assertIn("too_large", an.REASONS)

    def test_the_head_line_carries_the_first_seven_characters_of_the_run_commit(self):
        other = "0123456789abcdef0123456789abcdef01234567"
        head = {"ref": BRANCH, "sha": other, "repo": {"full_name": REPO}}
        api = FakeApi(ready_routes(prs=[pr_item(head=head)]))
        verdict = an.evaluate_ready(an.read_inputs(ready_env(NOTICE_RUN_SHA=other), an.READY), an.Reader(api), no_sleep)
        self.assertIn("머리 커밋 0123456 — 병합 전에 PR 화면의 해시와 같은지 보세요", verdict.text.split("\n"))
        self.assertNotIn("0123456789", verdict.text)                                                 # 7자리만 — 전체 해시는 싣지 않는다
        self.assertEqual(an.message_problem(verdict.text), "")

    def test_the_budget_counts_the_definition_line_too(self):
        """검사 정의 변경 줄도 800자 안에 든다: 그 줄이 없을 때 정확히 800자인 요점 다섯 줄은, 그 줄이 있으면 다섯째 요점이 빠져 800자 안에 든다(글자 수 계산이 그 줄을 빼먹으면 800자를 넘겨 발송 단계가 거절한다)."""
        title = "[M1234] " + "가" * 80
        head = "[M1234] 병합 부탁 — " + "가" * 80
        base = ["나" * 120 for _ in range(4)]
        fits = [length for length in range(1, 121) if len(an._ready_text(head, base + ["다" * length], "M1234", SHA, False)) == an.MESSAGE_LIMIT]
        self.assertEqual(len(fits), 1)
        body = "\n".join("- " + point for point in base + ["다" * fits[0]])
        plain = an.compose_ready("M1234", title, body, SHA, False)
        flagged = an.compose_ready("M1234", title, body, SHA, True)
        self.assertEqual((len(plain), plain.count("\n- ")), (an.MESSAGE_LIMIT, 5))                 # 경고 줄이 없으면 다섯 줄이 정확히 800자
        self.assertLessEqual(len(flagged), an.MESSAGE_LIMIT)
        self.assertEqual(flagged.count("\n- "), 4)                                                  # 경고 줄이 있으면 다섯째 요점이 빠진다
        self.assertEqual((an.message_problem(plain), an.message_problem(flagged)), ("", ""))

    def test_compose_ready_refuses_a_commit_that_is_not_a_full_lowercase_hash(self):
        for sha in (None, 5, "", "a" * 39, "a" * 41, "A" * 40, "g" * 40, "a" * 39 + "\n", " " + "a" * 39, ["a" * 40]):
            with self.subTest(repr(sha)):
                with self.assertRaises(an.Skip) as caught:
                    an.compose_ready(NUMBER, TITLE, BODY, sha)
                self.assertEqual(caught.exception.code, "input_shape")

    def test_the_head_line_is_the_first_seven_characters_whatever_the_hash(self):
        for sha, seven in (("0" * 40, "0000000"), ("f" * 40, "fffffff"), ("0123456789abcdef" * 2 + "01234567", "0123456"), ("abcdef0" + "1" * 33, "abcdef0")):
            with self.subTest(seven):
                self.assertEqual(an.head_line(sha), f"머리 커밋 {seven} — 병합 전에 PR 화면의 해시와 같은지 보세요")
                self.assertIn(an.head_line(sha), an.compose_ready(NUMBER, TITLE, BODY, sha).split("\n"))

    def test_the_new_fixed_lines_pass_the_character_rules_and_have_no_tilde_or_address(self):
        for line in (an.DEFINITION_LINE, an.head_line(SHA), an.head_line("0123456789abcdef0123456789abcdef01234567")):
            with self.subTest(line):
                self.assertEqual(an.line_problem(line), "")
                self.assertEqual(line, " ".join(line.split()))
                self.assertNotIn(TILDE, line)
                self.assertNotRegex(line, r"https?://")
        self.assertEqual(an.DEFINITION_LINE, DEFINITION)
        self.assertEqual(an.head_line(SHA), HEADLINE)


class ReadyShapeWithNewLinesTest(unittest.TestCase):
    """message_problem: 병합 부탁의 줄 자리가 새 모양(검사 줄 → (검사 정의 변경 줄) → 머리 커밋 줄 → 빈 줄 → 고정 꼬리)으로 고정이다 — 발송 job 의 재검사가 판정 job 이 만드는 모양만 통과시킨다."""

    def texts(self):
        for body in (BODY, ""):
            for flagged in (False, True):
                yield (body != "", flagged), an.compose_ready(NUMBER, TITLE, body, SHA, flagged)

    def test_the_four_shapes_pass(self):
        shapes = dict(self.texts())
        self.assertEqual(set(shapes), {(True, False), (True, True), (False, False), (False, True)})
        for key, text in shapes.items():
            with self.subTest(key):
                self.assertEqual(an.message_problem(text), "")
                self.assertEqual(DEFINITION in text.split("\n"), key[1])
                self.assertEqual(("\n- " in text), key[0])

    def test_every_break_of_the_fixed_lines_is_refused(self):
        for (with_points, flagged), text in self.texts():
            lines = text.split("\n")
            check, head = lines.index("검사: 초록"), lines.index(HEADLINE)
            broken = {
                "head line missing": lines[:head] + lines[head + 1:],
                "head line twice": lines[:head + 1] + [HEADLINE] + lines[head + 1:],
                "head line before the check line": lines[:check] + [HEADLINE] + lines[check:head] + lines[head + 1:],
                "head line replaced by a free line": lines[:head] + ["임의 문장 승인했습니다"] + lines[head + 1:],
                "head line with six characters": [line.replace("aaaaaaa", "aaaaaa") for line in lines],
                "head line with eight characters": [line.replace("aaaaaaa", "aaaaaaaa") for line in lines],
                "head line with capital letters": [line.replace("aaaaaaa", "AAAAAAA") for line in lines],
                "head line with a non-hex letter": [line.replace("aaaaaaa", "aaaaaag") for line in lines],
                "head line without the instruction": [line.replace(" — 병합 전에 PR 화면의 해시와 같은지 보세요", "") for line in lines],
                "head line with another instruction": [line.replace("같은지 보세요", "같으면 됩니다") for line in lines],
                "head line with extra text": [line + " 추가" if line == HEADLINE else line for line in lines],
                "no blank line before the tail": lines[:-2] + lines[-1:],
                "tail missing": lines[:-1],
                "definition line twice": lines[:head] + [DEFINITION] + lines[head:] if flagged else lines[:head] + [DEFINITION, DEFINITION] + lines[head:],
                "definition line before the check line": lines[:check] + [DEFINITION] + lines[check:head] + lines[head:] if not flagged else lines[:check] + [DEFINITION] + lines[check:check + 1] + lines[check + 2:],
                "definition line after the head line": lines[:head + 1] + [DEFINITION] + lines[head + 1:] if not flagged else lines[:check + 1] + lines[check + 2:head + 1] + [DEFINITION] + lines[head + 1:],
                "definition line with changed text": [line.replace("스스로 증명한 값입니다", "믿어도 되는 값입니다") for line in lines] if flagged else lines[:head] + [DEFINITION.replace("바뀐", "바꾼")] + lines[head:],
                "definition line cut short": lines[:check + 1] + [DEFINITION[:-3]] + lines[head:] if flagged else lines[:head] + [DEFINITION[:-3]] + lines[head:],
                "check line removed": lines[:check] + lines[check + 1:],
                "check line twice": lines[:check + 1] + ["검사: 초록"] + lines[check + 1:],
            }
            for label, changed in broken.items():
                with self.subTest((with_points, flagged, label)):
                    self.assertNotEqual("\n".join(changed), text, label)                              # 변이는 글을 실제로 바꾼다
                    self.assertNotEqual(an.message_problem("\n".join(changed)), "", label)

    def test_a_blank_line_that_the_code_never_writes_is_refused_even_without_points(self):
        """요점이 없을 때 제목 뒤 빈 줄이 둘이면(코드가 만들지 않는 모양) 거절한다 — 옛 검사는 이 빈 줄 하나를 놓쳤다."""
        text = an.compose_ready(NUMBER, TITLE, "", SHA)
        lines = text.split("\n")
        self.assertEqual(lines[:2], [lines[0], ""])
        self.assertEqual(an.message_problem("\n".join(lines[:2] + [""] + lines[2:])), "shape")
        with_points = an.compose_ready(NUMBER, TITLE, BODY, SHA).split("\n")
        self.assertEqual(an.message_problem("\n".join(with_points[:2] + [""] + with_points[2:])), "shape")        # 요점 앞에 빈 줄 하나 더
        index = with_points.index("검사: 초록")
        self.assertEqual(an.message_problem("\n".join(with_points[:index] + [""] + with_points[index:])), "shape")  # 검사 줄 앞에 빈 줄 하나 더

    def test_points_must_still_start_with_a_dash_and_stay_within_five_lines_of_120_characters(self):
        for flagged in (False, True):
            base = an.compose_ready(NUMBER, TITLE, "", SHA, flagged).split("\n")

            def with_points(points):
                return "\n".join(base[:2] + points + [""] + base[2:])
            self.assertEqual(an.message_problem(with_points(["- 가"] * 5)), "")
            self.assertEqual(an.message_problem(with_points(["- 가"] * 6)), "shape")
            self.assertEqual(an.message_problem(with_points(["- " + "가" * 120])), "")
            self.assertEqual(an.message_problem(with_points(["- " + "가" * 121])), "shape")
            self.assertEqual(an.message_problem(with_points(["줄 하나"])), "shape")
            self.assertEqual(an.message_problem(with_points([DEFINITION])), "shape")                  # 점 자리에 정의 변경 줄을 넣어도 안 된다

    def test_the_other_character_rules_still_reach_the_new_lines(self):
        """모든 줄이 line_problem 과 공백 정리를 거친다 — 새 고정 줄도 예외가 아니다(주소·멘션·물결표·제어 문자·두 칸 공백이 섞이면 거절)."""
        text = an.compose_ready(NUMBER, TITLE, BODY, SHA, True)
        for label, changed in {"mention in the definition line": text.replace("PR — 초록", "PR " + AT + "누구 — 초록"), "address in the head line": text.replace("보세요", SCHEME + "evil.example 보세요"),
                               "tilde in the head line": text.replace("보세요", TILDE + " 보세요"), "double space in the definition line": text.replace("바뀐 PR", "바뀐  PR"),
                               "control in the head line": text.replace("해시와", "해시\x01와"), "zero width in the definition line": text.replace("정의가", "정" + chr(0x200B) + "의가")}.items():
            with self.subTest(label):
                self.assertNotEqual(an.message_problem(changed), "", label)


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
        self.assertEqual(verdict.text.split("\n"), ["[M105] 병합완료 확인 - 정상", an.NOTE_NO_CONTENT])               # blob 해시가 없는 응답 — 이름만 견주고 '내용 비교 생략' 을 적는다
        self.assertTrue(any("트리 비교 생략(main 이 앞섬)" in note and "내용 비교 생략" in note for note in verdict.notes))
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
        self.assertEqual(verdict.text.split("\n"), ["[M105] 병합완료 확인 - 정상", an.NOTE_NO_CONTENT])
        self.assertEqual([call[2].get("page") for call in api.calls if call[1].endswith("/files")], [1, 2, 3])
        blobs = {name: f"{index:040x}" for index, name in enumerate(names)}                                       # 같은 곳에 blob 해시를 실으면 세 쪽 모두 견주고 내용까지 같음
        with_blobs = confirm_routes({f"/commits/{SHA}": commit_obj(files=tuple((n, blobs[n]) for n in names)), f"/pulls/{PR_NUMBER}": pr_detail(changed_files=250),
                                       f"/commits/{HEAD_SHA}": commit_obj(HEAD_SHA, "x", (OTHER_SHA,), OTHER_TREE),
                                       (f"/pulls/{PR_NUMBER}/files", 1): file_items((n, blobs[n]) for n in names[:100]), (f"/pulls/{PR_NUMBER}/files", 2): file_items((n, blobs[n]) for n in names[100:200]),
                                       (f"/pulls/{PR_NUMBER}/files", 3): file_items((n, blobs[n]) for n in names[200:])})
        verdict, _ = self.evaluate(with_blobs)
        self.assertEqual(verdict.text, "[M105] 병합완료 확인 - 정상")
        self.assertTrue(any("250개의 이름과 내용(blob)이 PR 과 같음" in note for note in verdict.notes))

    def test_exactly_300_files_are_read_in_three_full_pages_and_no_fourth_page_is_asked_for(self):
        """상한(300개)과 같을 때: 100개씩 세 쪽이 모두 가득 차도 네 번째 쪽은 부르지 않는다 — 부르면 가짜 GitHub 이 404 라 판정이 멈춘다."""
        names = [f"f{index}.py" for index in range(300)]
        pages = {(f"/pulls/{PR_NUMBER}/files", number): [{"filename": n} for n in names[(number - 1) * 100:number * 100]] for number in (1, 2, 3)}
        routes = confirm_routes({f"/commits/{SHA}": commit_obj(files=tuple(names)), f"/pulls/{PR_NUMBER}": pr_detail(changed_files=300),
                                   f"/commits/{HEAD_SHA}": commit_obj(HEAD_SHA, "x", (OTHER_SHA,), OTHER_TREE)} | pages)
        verdict, api = self.evaluate(routes)
        self.assertEqual(verdict.text.split("\n"), ["[M105] 병합완료 확인 - 정상", an.NOTE_NO_CONTENT])
        self.assertEqual([call[2].get("page") for call in api.calls if call[1].endswith("/files")], [1, 2, 3])
        self.assertEqual((an.FILE_PAGES_MAX, an.PER_PAGE, an.FILES_CAP), (3, 100, 300))

    def blob_routes(self, merged, pr, **detail):
        """트리가 다른 병합(main 이 앞섬)에서 두 쪽의 파일 목록을 (이름, blob) 쌍으로 만든 경로 표. 쌍이 아니라 글자만 주면 blob 해시가 없는 항목이다."""
        return confirm_routes({f"/commits/{SHA}": commit_obj(files=merged), f"/commits/{HEAD_SHA}": commit_obj(HEAD_SHA, "x", (OTHER_SHA,), OTHER_TREE),
                               f"/pulls/{PR_NUMBER}": pr_detail(**detail), (f"/pulls/{PR_NUMBER}/files", 1): file_items(pr)})

    def test_blobs_that_are_all_equal_say_the_content_matches_and_add_no_note(self):
        """AN1-S-10: 두 응답의 파일마다 blob 해시가 모두 있고 같으면 이름뿐 아니라 내용까지 같다 — 문장에 '내용 비교 생략' 이 없다."""
        a, b = "a" * 40, "b" * 40
        verdict, api = self.evaluate(self.blob_routes((("a.py", a), ("b.md", b)), (("a.py", a), ("b.md", b))))
        self.assertEqual(verdict.text, "[M105] 병합완료 확인 - 정상")
        self.assertTrue(any("2개의 이름과 내용(blob)이 PR 과 같음" in note for note in verdict.notes))
        self.assertEqual(api.methods(), {"GET"})

    def test_a_differing_blob_keeps_ok_by_name_and_adds_the_content_note(self):
        """내용(blob)이 다른 파일은 main 이 같은 파일을 건드린 것으로 보고 이름만 확인한다 — 정상이되 문장에 '내용 비교 생략'(몇 개인지는 요약 줄에)."""
        a, b, c = "a" * 40, "b" * 40, "c" * 40
        verdict, _ = self.evaluate(self.blob_routes((("a.py", a), ("b.md", c)), (("a.py", a), ("b.md", b))))
        self.assertEqual(verdict.text.split("\n"), ["[M105] 병합완료 확인 - 정상", an.NOTE_NO_CONTENT])
        self.assertTrue(any("내용(blob)까지 같은 것은 1개, 나머지 1개는 내용 비교 생략" in note for note in verdict.notes))
        both = self.evaluate(confirm_routes({f"/commits/{SHA}": commit_obj(parents=(OTHER_SHA, HEAD_SHA), files=(("a.py", a), ("b.md", c))),
                                             f"/commits/{HEAD_SHA}": commit_obj(HEAD_SHA, "x", (OTHER_SHA,), OTHER_TREE), (f"/pulls/{PR_NUMBER}/files", 1): file_items((("a.py", a), ("b.md", b)))}))[0]
        self.assertEqual(both.text.split("\n"), ["[M105] 병합완료 확인 - 정상", an.NOTE_TWO_PARENTS, an.NOTE_NO_CONTENT])         # 부모 둘 참고가 먼저

    def test_a_missing_or_malformed_blob_on_either_side_falls_back_to_names_and_adds_the_content_note(self):
        a, b = "a" * 40, "b" * 40
        weird = ("nope", "A" * 40, "a" * 39, "a" * 41, 5, None, "", ["a" * 40], " " + "a" * 39)
        cases = {"missing on the merge side": ((("a.py", a), "b.md"), (("a.py", a), ("b.md", b))), "missing on the pull side": ((("a.py", a), ("b.md", b)), (("a.py", a), "b.md")),
                 "missing on both": (("a.py", "b.md"), ("a.py", "b.md"))}
        for value in weird:
            cases[f"malformed {value!r} on the merge side"] = ((("a.py", a), ("b.md", value)), (("a.py", a), ("b.md", b)))
            cases[f"malformed {value!r} on the pull side"] = ((("a.py", a), ("b.md", b)), (("a.py", a), ("b.md", value)))
        for label, (merged, pr) in cases.items():
            with self.subTest(label):
                verdict, _ = self.evaluate(self.blob_routes(merged, pr))
                self.assertEqual(verdict.text.split("\n"), ["[M105] 병합완료 확인 - 정상", an.NOTE_NO_CONTENT])
                self.assertTrue(any("내용 비교 생략" in note for note in verdict.notes))

    def test_different_names_are_bad_whatever_the_blobs_say(self):
        a = "a" * 40
        verdict, _ = self.evaluate(self.blob_routes((("a.py", a), ("c.md", a)), (("a.py", a), ("b.md", a))))
        self.assertEqual(verdict.text.split("\n"), ["[M105] 병합완료 확인 - 이상", "변경 파일이 PR 과 다릅니다(PR 2개, 병합 2개)"])
        self.assertEqual(an.message_problem(verdict.text), "")

    def test_equal_trees_ignore_the_blobs_and_every_verdict_text_is_a_valid_message(self):
        for text in (self.evaluate()[0].text, self.evaluate(NOTICE_RUN_CONCLUSION="failure")[0].text,
                     self.evaluate(confirm_routes({f"/commits/{SHA}": commit_obj(parents=(OTHER_SHA, HEAD_SHA))}))[0].text,
                     self.evaluate(self.blob_routes((("a.py", "a" * 40), ("b.md", "b" * 40)), (("a.py", "a" * 40), ("b.md", "c" * 40))))[0].text):
            self.assertEqual(an.message_problem(text), "", text)

    def test_more_than_300_changed_files_cannot_be_compared(self):
        routes = confirm_routes({f"/pulls/{PR_NUMBER}": pr_detail(changed_files=301), f"/commits/{HEAD_SHA}": commit_obj(HEAD_SHA, "x", (OTHER_SHA,), OTHER_TREE)})
        self.assertEqual(self.skipped(routes), "too_large")
        for changed in (0, -1):
            routes = confirm_routes({f"/pulls/{PR_NUMBER}": pr_detail(changed_files=changed), f"/commits/{HEAD_SHA}": commit_obj(HEAD_SHA, "x", (OTHER_SHA,), OTHER_TREE)})
            self.assertEqual(self.skipped(routes), "too_large")

    def test_a_single_changed_file_is_compared_like_any_other(self):
        """변경 파일이 정확히 1개인 PR 도 비교한다(0개 이하만 too_large) — 1개짜리 PR 이 흔하다."""
        verdict, api = self.evaluate(self.blob_routes((("a.py", "a" * 40),), (("a.py", "a" * 40),), changed_files=1))
        self.assertEqual(verdict.text, "[M105] 병합완료 확인 - 정상")
        self.assertIn(f"/pulls/{PR_NUMBER}/files", api.paths())

    def test_a_file_count_that_disagrees_with_the_list_is_a_shape_problem(self):
        routes = confirm_routes({f"/pulls/{PR_NUMBER}": pr_detail(changed_files=5), f"/commits/{HEAD_SHA}": commit_obj(HEAD_SHA, "x", (OTHER_SHA,), OTHER_TREE),
                                   (f"/pulls/{PR_NUMBER}/files", 1): [{"filename": "a.py"}, {"filename": "b.md"}]})
        self.assertEqual(self.skipped(routes), "api_shape")

    def test_equal_trees_need_no_file_lists(self):
        _, api = self.evaluate()
        self.assertNotIn(f"/pulls/{PR_NUMBER}/files", api.paths())

    def test_a_merged_pull_request_number_below_one_is_a_shape_problem_and_one_itself_is_fine(self):
        for number in (0, -1):
            with self.subTest(number):
                routes = confirm_routes({f"/commits/{SHA}/pulls": [pull_item(number=number)], f"/pulls/{number}": pr_detail(number=number)})
                self.assertEqual(self.skipped(routes), "api_shape")
        verdict, api = self.evaluate(confirm_routes({f"/commits/{SHA}/pulls": [pull_item(number=1)], "/pulls/1": pr_detail(number=1)}))
        self.assertEqual(verdict.text, "[M105] 병합완료 확인 - 정상")
        self.assertIn("/pulls/1", api.paths())

    def test_a_file_entry_without_a_usable_name_is_a_shape_problem_even_when_both_sides_agree_on_it(self):
        """이름이 비었거나 없거나 글자가 아닌 항목은 양쪽이 같아도 비교하지 않고 api_shape — 그냥 받으면 `` 키 하나로 접혀 '이름이 같다' 는 정상이 나온다."""
        a = "a" * 40
        for label, bad in {"empty name": {"filename": "", "sha": a}, "missing name": {"sha": a}, "number name": {"filename": 5, "sha": a}, "none name": {"filename": None}}.items():
            with self.subTest(label):
                entries = [{"filename": "a.py", "sha": a}, bad]
                merge_commit = commit_obj(files=None)
                merge_commit["files"] = copy.deepcopy(entries)
                routes = confirm_routes({f"/commits/{SHA}": merge_commit, f"/commits/{HEAD_SHA}": commit_obj(HEAD_SHA, "x", (OTHER_SHA,), OTHER_TREE),
                                           f"/pulls/{PR_NUMBER}": pr_detail(changed_files=2), (f"/pulls/{PR_NUMBER}/files", 1): copy.deepcopy(entries)})
                self.assertEqual(self.skipped(routes), "api_shape")

    def test_the_summary_notes_name_the_pull_request_the_conclusion_the_parents_and_the_tree(self):
        """요약에 남는 확인 문장은 고정 문장과 번호·개수뿐이고 순서가 정해져 있다(dry 요약을 읽는 운영자가 보는 것)."""
        verdict, _ = self.evaluate()
        self.assertEqual(verdict.notes, [f"병합된 PR #{PR_NUMBER} 하나가 이 커밋에 연결됨", "main 가드레일 결론: success", "병합 커밋의 부모 1개(squash)", "트리 일치(병합 커밋과 PR 머리 커밋의 트리가 같음)"])
        verdict, _ = self.evaluate(NOTICE_RUN_CONCLUSION="failure")
        self.assertIn("main 가드레일 결론: failure", verdict.notes)

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
# 판정 job / 발송 job
# ----------------------------------------------------------------------------
class StepTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)
        self.summary, self.output = self.dir / "summary.md", self.dir / "output.txt"
        self.state = self.dir / "state.json"
        self.out = []

    def mode(self, mode):
        self.state.write_text(json.dumps({"mode": mode}), encoding="utf-8")

    def env(self, base=None, **over):
        env = SpyEnv(ready_env() if base is None else base)
        env.update({"GITHUB_STEP_SUMMARY": str(self.summary), "GITHUB_OUTPUT": str(self.output)})
        env.update(over)
        return env

    def decide(self, kind=an.READY, routes=None, env=None, reader=True):
        api = FakeApi((ready_routes() if kind == an.READY else confirm_routes()) if routes is None else routes)
        code = an.run_decide(kind, env if env is not None else self.env(), self.out.append, reader=an.Reader(api) if reader else None, sleep=no_sleep, state_file=self.state)
        return code, api

    def text(self, path):
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def outputs(self):
        """출력 파일의 `이름=값` 줄들 → [(이름, 값), …]"""
        return [tuple(line.split("=", 1)) for line in self.text(self.output).splitlines()]

    # ---- off ----------------------------------------------------------------------------
    def test_off_ends_at_once_without_reading_secrets_github_or_the_token(self):
        self.mode("off")
        env = self.env()
        code, api = self.decide(env=env)
        self.assertEqual((code, self.out, api.calls), (0, [an.MODE_OFF_LINE], []))
        self.assertEqual(set(env.reads), {"GITHUB_STEP_SUMMARY"})                 # 시크릿·토큰·이벤트 값 어느 것도 읽지 않았다
        self.assertIn("꺼져", self.text(self.summary))
        self.assertEqual(self.text(self.output), "")

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

    def test_off_writes_nothing_to_the_output_even_if_the_output_file_already_has_lines(self):
        self.mode("off")
        self.output.write_text("old=1\n", encoding="utf-8")
        self.decide()
        self.assertEqual(self.text(self.output), "old=1\n")                       # 꺼져 있으면 아무것도 건드리지 않는다

    def test_the_summary_names_the_workflow_the_mode_and_the_subject_for_each_kind(self):
        """실행 요약의 첫 줄들 — 제목(어느 워크플로의 요약인가)·켬 상태·대상(병합 부탁은 번호, 병합완료 확인은 main 의 검사 결과). 글을 상수에서 읽지 않고 그대로 적는다."""
        for kind, base, heading, subject, note in ((an.READY, None, "### [공통] 병합 부탁 알림 자동 보내기", "- 번호: M105", f"- 확인: 열린 PR #{PR_NUMBER} 하나이고 머리 커밋이 이 실행의 커밋과 같음"),
                                                   (an.CONFIRM, confirm_env(), "### [공통] 병합완료 확인 알림 자동 보내기", "- 대상: main 의 검사 결과", "- 확인: main 가드레일 결론: success")):
            for mode in ("off", "dry", "on"):
                with self.subTest((kind, mode)):
                    self.mode(mode)
                    self.summary.write_text("", encoding="utf-8")
                    self.output.write_text("", encoding="utf-8")
                    self.decide(kind, env=None if base is None else self.env(base))
                    lines = self.text(self.summary).splitlines()
                    self.assertEqual(lines[:2], [heading, f"- 켬 상태: {mode}"])
                    if mode == "off":
                        self.assertNotIn(note, lines)
                    else:
                        self.assertEqual(lines[2], subject)
                        self.assertIn(note, lines)                                  # 확인 문장(verdict.notes)이 요약에 한 줄씩 실린다

    # ---- dry ----------------------------------------------------------------------------
    def test_dry_writes_the_message_to_the_summary_only(self):
        self.mode("dry")
        code, api = self.decide()
        self.assertEqual(code, 0)
        text = an.compose_ready(NUMBER, TITLE, BODY, SHA)
        summary = self.text(self.summary)
        self.assertIn(text, summary)
        self.assertIn("```text", summary)
        self.assertEqual(self.text(self.output), "")                              # 출력이 없어 발송 job 은 시작도 하지 않는다
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
    def test_on_writes_exactly_two_output_lines_the_fixed_send_line_and_the_message_as_one_base64_line(self):
        self.mode("on")
        code, api = self.decide()
        self.assertEqual(code, 0)
        text = an.compose_ready(NUMBER, TITLE, BODY, SHA)
        encoded = an.encode_message(text)
        self.assertEqual(self.text(self.output), f"send=yes\nmessage={encoded}\n")
        self.assertIsNotNone(re.fullmatch(r"[A-Za-z0-9+/]+={0,2}", encoded))
        self.assertEqual(an.decode_message(encoded), text)
        shown = "\n".join(self.out) + self.text(self.summary)
        for needle in ("워크플로 둘", encoded, encoded[:24]):
            self.assertNotIn(needle, shown)                                        # 로그·요약에는 문장도 그 base64 도 없다(고정 문장만)
        self.assertEqual(api.methods(), {"GET"})
        self.assertEqual(self.out, ["병합 알림 자동: 보낼 문장을 만들었습니다(발송 job 이 보냅니다)"])                  # 로그는 고정 문장 한 줄뿐
        self.assertIn("- 결과: 보낼 문장을 만들었습니다(on — 발송 job 이 텔레그램으로 보냅니다)", self.text(self.summary))

    def test_on_confirm_makes_the_confirmation_message(self):
        self.mode("on")
        code, _ = self.decide(an.CONFIRM, env=self.env(confirm_env()))
        self.assertEqual(code, 0)
        self.assertEqual(self.outputs(), [("send", "yes"), ("message", an.encode_message("[M105] 병합완료 확인 - 정상"))])

    def test_nothing_is_written_to_the_output_when_there_is_nothing_to_send(self):
        for mode in ("dry", "on"):
            with self.subTest(mode):
                self.mode(mode)
                self.output.write_text("", encoding="utf-8")
                self.decide(routes=ready_routes(prs=[]))                              # 알릴 것이 없다
                self.assertEqual(self.text(self.output), "")

    def test_on_without_a_usable_output_file_does_not_send_and_warns(self):
        self.mode("on")
        no_path = self.env()
        del no_path["GITHUB_OUTPUT"]
        for label, env in (("no path", no_path), ("unwritable", self.env(GITHUB_OUTPUT=str(self.dir / "missing-dir" / "output.txt")))):
            with self.subTest(label):
                self.out.clear()
                code, _ = self.decide(env=env)
                self.assertEqual(code, 0)
                self.assertEqual(self.out, ["병합 알림 자동: 출력 파일에 문장을 남기지 못해 보내지 않습니다", "::warning::병합 알림 자동: 출력 파일을 쓰지 못해 알리지 않았습니다."])
                self.assertIn("출력 파일을 쓰지 못해", self.text(self.summary))
        self.assertEqual(self.text(self.output), "")

    def test_a_message_that_fails_the_shape_check_is_never_written_or_shown_by_the_decide_step(self):
        """판정 job 이 문장을 만든 직후의 재검사(message_problem): 문장이 코드가 만드는 모양이 아니면 on 에서도 출력을 쓰지 않고 dry 에서도 문장을 요약에 싣지 않는다 — 고정 문장과 경고만 남는다
        (판정 쪽 버그가 문장을 깨뜨려도 출력·요약에는 새지 않는다 — 발송 job 의 재검사가 두 번째 관문이고 이것이 첫째다)."""
        bad = an.Verdict("`깨진` 문장\n\n검사: 초록", ["확인 하나"])
        self.assertNotEqual(an.message_problem(bad.text), "")                      # 전제: 이 문장은 모양 검사에 걸린다
        for kind, name, env in ((an.READY, "evaluate_ready", None), (an.CONFIRM, "evaluate_confirm", confirm_env())):
            for mode in ("on", "dry"):
                with self.subTest((kind, mode)):
                    self.mode(mode)
                    self.out.clear()
                    self.output.write_text("", encoding="utf-8")
                    self.summary.write_text("", encoding="utf-8")
                    with mock.patch.object(an, name, return_value=bad):
                        code, _ = self.decide(kind, env=None if env is None else self.env(env))
                    self.assertEqual(code, 0)
                    self.assertEqual(self.text(self.output), "")
                    self.assertIn(an.REASONS["message_problem"][0], self.text(self.summary))
                    self.assertNotIn("깨진", self.text(self.summary) + "\n".join(self.out))
                    self.assertNotIn("```", self.text(self.summary))
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

    LOUD_REASONS = {"input_shape", "api_error", "api_shape", "title_problem", "message_problem"}

    def test_the_reason_table_marks_exactly_the_abnormal_situations_as_loud_and_each_one_is_reported_that_way(self):
        """어떤 '보내지 않은 이유' 가 경고(::warning::)까지 올리는가는 정책이다 — 입력·GitHub 응답의 모양이 예상과 다르거나 제목·문장이 거르기 규칙에 걸린 이상 상황만 시끄럽고, 알릴 일이 없는 정상 상황은
        조용하다. 표를 읽어 기대값으로 쓰면 표를 바꿔도 통과하므로 기대하는 집합을 시험이 직접 갖는다. 모든 이유를 실제로 판정 단계에 흘려 로그·요약·경고를 본다."""
        self.assertEqual({code for code, (_sentence, loud) in an.REASONS.items() if loud}, self.LOUD_REASONS)
        self.assertEqual(len(an.REASONS), 20)
        self.mode("dry")
        for code, (sentence, _loud) in an.REASONS.items():
            with self.subTest(code):
                self.out.clear()
                self.summary.write_text("", encoding="utf-8")
                with mock.patch.object(an, "read_inputs", side_effect=an.Skip(code)):
                    self.assertEqual(self.decide()[0], 0)
                self.assertEqual(self.out[0], f"병합 알림 자동: {sentence}")
                self.assertEqual(any(line.startswith("::warning::") for line in self.out), code in self.LOUD_REASONS)
                self.assertIn(f"- 결과: {sentence}", self.text(self.summary))
                self.assertEqual(self.text(self.output), "")

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

    # ---- 발송 job -----------------------------------------------------------------------------
    def make_notifier(self):
        net = nh.FakeNet()
        clock = nh.Clock()
        return notify.Notifier(dict(nh.ENV), opener=net, sleep=clock.sleep, clock=clock.clock, budget=notify.Budget()), net

    def send_env(self, text, **over):
        """발송 job 의 환경: 판정 job 의 출력이 env 로 온 것(base64 한 줄) + 덮어쓸 값."""
        return self.env(**{an.MESSAGE_ENV: an.encode_message(text), **over})

    def send(self, env=None, notifier=None):
        return an.run_send(env if env is not None else self.env(), self.out.append, notifier=notifier, state_file=self.state)

    def test_send_is_refused_unless_the_mode_is_on_and_reads_neither_secrets_nor_the_message_then(self):
        class Boom:
            def send_message(self, *args, **kwargs):
                raise AssertionError("보내면 안 된다")

        for mode in ("off", "dry"):
            with self.subTest(mode):
                self.mode(mode)
                self.out.clear()
                self.summary.write_text("", encoding="utf-8")
                env = self.send_env(an.compose_ready(NUMBER, TITLE, BODY, SHA), TELEGRAM_BOT_TOKEN=nh.TOKEN, TELEGRAM_CHAT_ID=nh.CHAT)
                self.assertEqual(self.send(env, Boom()), 0)
                self.assertNotIn("TELEGRAM_BOT_TOKEN", env.reads)
                self.assertNotIn("TELEGRAM_CHAT_ID", env.reads)
                self.assertNotIn(an.MESSAGE_ENV, env.reads)
                self.assertEqual(self.out, ["병합 알림 자동: 켬 상태가 on 이 아니라 보내지 않습니다"])                 # 고정 문장 한 줄(경고 없음 — 정상 상황이다)
                self.assertEqual(self.text(self.summary), "- 발송: 켬 상태가 on 이 아니라 보내지 않았습니다\n")
        self.state.unlink()
        self.assertEqual(self.send(self.send_env("[M105] 병합완료 확인 - 정상"), Boom()), 0)      # 켬 상태 파일이 없으면 off

    def test_send_sends_the_checked_message_as_plain_text_once(self):
        self.mode("on")
        text = an.compose_ready(NUMBER, TITLE, BODY, SHA)
        notifier, net = self.make_notifier()
        self.assertEqual(self.send(self.send_env(text), notifier), 0)
        self.assertEqual(net.calls, 1)
        body = net.bodies()[0]
        self.assertEqual(body["text"], text)
        self.assertNotIn("parse_mode", body)                                       # 평문 — 서식·링크 해석 없음
        self.assertNotIn("reply_markup", body)
        self.assertEqual(body["link_preview_options"], {"is_disabled": True})
        self.assertEqual(self.out, ["병합 알림 자동: 텔레그램으로 보냈습니다"])
        self.assertEqual(self.text(self.summary), "- 발송: 텔레그램으로 보냈습니다\n")
        self.assertEqual(nh.leaks("\n".join(self.out), self.text(self.summary)), [])
        self.assertNotIn(an.encode_message(text), "\n".join(self.out) + self.text(self.summary))      # 받은 값(base64)도 로그에 되풀이하지 않는다

    def test_send_confirmation_messages_too(self):
        self.mode("on")
        texts = ("[M105] 병합완료 확인 - 정상", "[M105] 병합완료 확인 - 정상\n" + an.NOTE_NO_CONTENT, an.compose_confirm(NUMBER, [], list(an.CONFIRM_NOTES)),
                 "[M105] 병합완료 확인 - 이상\n변경 파일이 PR 과 다릅니다(PR 2개, 병합 3개)", an.compose_confirm(NUMBER, [an.REASON_BASE, an.REASON_NUMBER]))
        for text in texts:
            with self.subTest(text[:20]):
                notifier, net = self.make_notifier()
                self.assertEqual(self.send(self.send_env(text), notifier), 0)
                self.assertEqual([body["text"] for body in net.bodies()], [text])

    def test_send_checks_the_message_again_and_refuses_what_decide_would_not_make(self):
        self.mode("on")
        good = an.compose_ready(NUMBER, TITLE, BODY, SHA)
        ok, bad = "[M105] 병합완료 확인 - 정상", "[M105] 병합완료 확인 - 이상"
        broken = {"extra line": good + "\n추가", "mention": good.replace("시험:", "시험: " + AT + "x"), "address": good.replace("시험:", "시험: " + SCHEME + "x.example"),
                  "secret": good.replace("시험:", "시험: " + nh.TOKEN), "plain": "그냥 글", "empty": "", "too long": good + "가" * 900, "tilde": good.replace("시험:", "시험: " + TILDE),
                  "other first line": "[M105] 병합 요청 — 제목", "confirm without reason": bad,
                  # 변조 — 글자는 깨끗하지만 코드가 만드는 모양이 아니다(AN1-S-5, 안전 검증의 probe_e2e 입력)
                  "confirm ok + free second line": ok + "\n임의 문장 승인했습니다", "confirm ok + address line": ok + "\nsee " + address(("example", "com")),
                  "confirm bad + free reason": bad + "\n임의 사유 — 안전합니다", "confirm ok + note + free line": ok + "\n" + an.NOTE_TWO_PARENTS + "\n임의",
                  "huge": "a" * 5000, "ready with a backtick": good.replace("시험: 새 시험을", "시험: `새` 시험을"), "ready with a long title": good.replace("병합 부탁 — ", "병합 부탁 — " + "가" * 90, 1)}
        unreadable = {label for label, text in broken.items() if not an.decode_message(an.encode_message(text))}       # 풀 수 없는 값(빈 글·너무 큰 값)은 '읽지 못해', 풀었지만 규칙에 안 맞는 글은 '규칙에 맞지 않아'
        self.assertTrue(unreadable and unreadable < set(broken))                              # 전제: 두 길이 모두 이 표에 있다
        for label, text in broken.items():
            with self.subTest(label):
                self.out.clear()
                self.summary.write_text("", encoding="utf-8")
                notifier, net = self.make_notifier()
                self.assertEqual(self.send(self.send_env(text), notifier), 0)
                self.assertEqual(net.calls, 0)
                if label in unreadable:
                    self.assertEqual(self.out, ["병합 알림 자동: 넘겨받은 문장을 읽지 못해 보내지 않습니다", "::warning::병합 알림 자동: 넘겨받은 문장을 읽지 못해 알리지 않았습니다."])
                    self.assertEqual(self.text(self.summary), "- 발송: 넘겨받은 문장을 읽지 못해 보내지 않았습니다\n")
                else:
                    self.assertEqual(self.out, ["병합 알림 자동: 문장이 보내기 규칙에 맞지 않아 보내지 않습니다", "::warning::병합 알림 자동: 문장이 보내기 규칙에 맞지 않아 알리지 않았습니다."])
                    self.assertEqual(self.text(self.summary), "- 발송: 문장이 보내기 규칙에 맞지 않아 보내지 않았습니다\n")

    def test_send_with_a_missing_oversized_or_malformed_value_sends_nothing(self):
        self.mode("on")
        valid = an.encode_message("[M105] 병합완료 확인 - 정상")
        values = {"missing": None, "empty": "", "space inside": valid[:8] + " " + valid[8:], "trailing newline": valid + "\n", "newline inside": valid[:8] + "\n" + valid[8:], "not base64": "###" + valid,
                  "wrong padding": valid[:-1], "padding first": "====" + valid, "url-safe alphabet": valid[:8] + "-_" + valid[10:], "oversized": an.encode_message("a" * 5000),
                  "binary": base64.b64encode(b"\xff\xfe\x00\x01").decode("ascii"), "valid head then bad utf-8": base64.b64encode("[M105] 병합완료 확인 - 정상".encode("utf-8") + b"\xff").decode("ascii"),
                  "text that decodes but is not a message": base64.b64encode(b"hello").decode("ascii")}
        for label, value in values.items():
            with self.subTest(label):
                self.out.clear()
                self.summary.write_text("", encoding="utf-8")
                env = self.env()
                if value is not None:
                    env[an.MESSAGE_ENV] = value
                notifier, net = self.make_notifier()
                self.assertEqual(self.send(env, notifier), 0)
                self.assertEqual(net.calls, 0)
                if label == "text that decodes but is not a message":                          # 풀리지만 문장 모양이 아니다 — 다른 고정 문장
                    self.assertEqual(self.out[0], "병합 알림 자동: 문장이 보내기 규칙에 맞지 않아 보내지 않습니다")
                else:
                    self.assertEqual(self.out[0], "병합 알림 자동: 넘겨받은 문장을 읽지 못해 보내지 않습니다")
                self.assertTrue(any(line.startswith("::warning::") for line in self.out))

    def test_a_failed_send_is_a_warning_and_a_zero_exit_without_leaking_the_secrets(self):
        self.mode("on")
        net = nh.FakeNet(nh.http_error(401, "Unauthorized"))
        clock = nh.Clock()
        notifier = notify.Notifier(dict(nh.ENV), opener=net, sleep=clock.sleep, clock=clock.clock, budget=notify.Budget())
        self.assertEqual(self.send(self.send_env(an.compose_ready(NUMBER, TITLE, BODY, SHA)), notifier), 0)
        self.assertEqual(len(self.out), 2)
        self.assertTrue(self.out[0].startswith("병합 알림 자동: 텔레그램으로 보내지 못했습니다 — "))                    # 이유 한 줄(notify.describe — 시크릿 없음) 다음에 경고
        self.assertTrue(self.out[1].startswith("::warning::병합 알림 자동: 텔레그램 전송에 실패했습니다."))
        self.assertEqual(self.text(self.summary), "- 발송: 텔레그램으로 보내지 못했습니다(이유는 로그 참고)\n")
        self.assertEqual(nh.leaks("\n".join(self.out), self.text(self.summary)), [])
        self.assertNotIn("워크플로 둘", "\n".join(self.out))

    def test_without_the_secrets_the_send_is_a_warning_not_a_crash(self):
        self.mode("on")
        notifier = notify.Notifier({}, opener=nh.FakeNet(), budget=notify.Budget())
        self.assertEqual(self.send(self.send_env(an.compose_ready(NUMBER, TITLE, BODY, SHA)), notifier), 0)
        self.assertTrue(any(line.startswith("::warning::") for line in self.out))

    def test_the_send_step_builds_the_real_notifier_from_the_environment_when_none_is_given(self):
        self.mode("on")
        calls = []
        original = notify.Notifier

        class Recording(original):
            def __init__(self, environ=None, **kwargs):
                calls.append(environ)
                super().__init__(environ, opener=nh.FakeNet(), sleep=lambda s: None, clock=nh.Clock().clock, budget=notify.Budget())

        env = self.send_env("[M105] 병합완료 확인 - 정상", TELEGRAM_BOT_TOKEN=nh.TOKEN, TELEGRAM_CHAT_ID=nh.CHAT)
        with mock.patch.object(notify, "Notifier", Recording):
            self.assertEqual(self.send(env), 0)
        self.assertEqual(len(calls), 1)
        self.assertIs(calls[0], env)                                                # 환경을 그대로 넘긴다 — 시크릿은 이 job 의 env 에서만 읽는다
        self.assertIn("텔레그램으로 보냈습니다", "\n".join(self.out))

    # ---- 두 job 의 이어짐 ---------------------------------------------------------------------
    def test_what_decide_writes_in_on_mode_is_exactly_what_send_accepts(self):
        self.mode("on")
        for kind, routes, env in ((an.READY, ready_routes(), self.env()), (an.CONFIRM, confirm_routes(), self.env(confirm_env()))):
            with self.subTest(kind):
                self.output.write_text("", encoding="utf-8")
                self.decide(kind, routes=routes, env=env)
                written = self.outputs()
                self.assertEqual([key for key, _value in written], ["send", "message"])
                self.assertEqual(written[0], ("send", "yes"))
                notifier, net = self.make_notifier()
                self.out.clear()
                self.assertEqual(self.send(self.env(**{an.MESSAGE_ENV: written[1][1]}), notifier), 0)
                self.assertEqual(net.calls, 1)
                self.assertEqual(net.bodies()[0]["text"], an.decode_message(written[1][1]))

    def test_there_is_no_message_file_any_more_and_no_runner_temp_is_read(self):
        """두 job 은 러너가 다르다 — 파일이 아니라 출력(base64 한 줄)으로만 문장을 넘긴다."""
        self.assertFalse(hasattr(an, "MESSAGE_FILE"))
        self.assertFalse(hasattr(an, "message_path"))
        self.assertNotIn("RUNNER_TEMP", MODULE.read_text(encoding="utf-8"))


class TransportTest(unittest.TestCase):
    """AN1-S-4·S-13: 두 job 사이로 가는 문장은 base64 한 줄이다 — 줄 바꿈·따옴표·`::` 명령 머리·식이 끼어들 수 없고, 풀 때 모양과 크기를 엄격히 본다."""

    def test_the_encoded_value_is_one_line_of_the_safe_alphabet_for_every_kind_of_text(self):
        texts = ["[M105] 병합완료 확인 - 정상", an.compose_ready(NUMBER, TITLE, BODY, SHA), "한 줄\n두 줄\n\n네 줄", "따옴표 \" ' 와 ::error::x 와 ${{ secrets.X }} 와 %0A 와 \\n 와 `백틱`", "\x00\x1b[31m", "😀" * 50, "a"]
        for text in texts:
            with self.subTest(text[:12]):
                value = an.encode_message(text)
                self.assertIsNotNone(re.fullmatch(r"[A-Za-z0-9+/]+={0,2}", value))
                for char in ("\n", "\r", '"', "'", ":", "$", "{", "}", "%", " ", "\\", "`", "#", "<", ">"):
                    self.assertNotIn(char, value)
                self.assertEqual(an.decode_message(value), text)

    def test_the_boundaries_of_the_size_caps(self):
        self.assertEqual(an.MESSAGE_BYTES_LIMIT, 3200)
        self.assertEqual(an.MESSAGE_B64_LIMIT, 4268)
        at, over = "a" * an.MESSAGE_BYTES_LIMIT, "a" * (an.MESSAGE_BYTES_LIMIT + 1)
        self.assertEqual(an.decode_message(an.encode_message(at)), at)                         # 바이트 상한 정확히는 푼다
        self.assertEqual(len(an.encode_message(over)), an.MESSAGE_B64_LIMIT)                    # 길이는 한도 안인데
        self.assertEqual(an.decode_message(an.encode_message(over)), "")                       # 풀어 본 바이트 수가 한 바이트 넘어 거절
        longer = an.encode_message("a" * (an.MESSAGE_BYTES_LIMIT + 4))
        self.assertGreater(len(longer), an.MESSAGE_B64_LIMIT)
        with mock.patch.object(an.base64, "b64decode", side_effect=AssertionError("풀어 보면 안 된다")):
            self.assertEqual(an.decode_message(longer), "")                                    # 길이 한도를 넘는 값은 풀어 보지도 않는다
        self.assertEqual(an.decode_message("a" * 5000), "")                                    # 한도를 넘는 엉터리 값도 마찬가지

    def test_values_with_characters_outside_the_alphabet_are_refused_before_any_decoding(self):
        """글자 모양(영문·숫자·`+/=` 뿐, `=` 는 끝에 둘까지)은 풀어 보기 전에 거른다 — 디코더를 부르지도 않으므로 디코더의 오류 처리나 버전별 엄격함에 기대지 않는다."""
        valid = an.encode_message("[M105] 병합완료 확인 - 정상")
        for value in (valid + " ", " " + valid, valid + "\n", valid[:8] + "\n" + valid[8:], valid[:8] + "-" + valid[9:], valid[:8] + "_" + valid[9:], "====", "ＡＢＣＤ", "AAAA=AAAA", "=" + valid, valid + "===", "A" * 40 + "\r"):
            with self.subTest(repr(value)[:30]):
                with mock.patch.object(an.base64, "b64decode", side_effect=AssertionError("풀어 보면 안 된다")):
                    self.assertEqual(an.decode_message(value), "")
        with mock.patch.object(an.base64, "b64decode", wraps=base64.b64decode) as spy:
            self.assertEqual(an.decode_message(valid), "[M105] 병합완료 확인 - 정상")                    # 대조: 올바른 값은 디코더를 한 번 부른다
            self.assertEqual(spy.call_count, 1)

    def test_malformed_values_decode_to_nothing(self):
        valid = an.encode_message("[M105] 병합완료 확인 - 정상")
        self.assertEqual(an.decode_message(valid), "[M105] 병합완료 확인 - 정상")
        for value in (None, 5, [], b"abcd", "", " ", valid + " ", " " + valid, valid + "\n", "\n" + valid, valid[:-1], valid[:-2], "====", "!!!!", "A", "AAAAA", "ＡＢＣＤ", valid[:8] + "\n" + valid[8:], valid + "AAAA="):
            with self.subTest(repr(value)[:30]):
                self.assertEqual(an.decode_message(value), "")
        self.assertEqual(an.decode_message(base64.b64encode(b"\xff\xfe").decode("ascii")), "")      # UTF-8 이 아니다

    def test_write_outputs_appends_lines_and_refuses_values_with_line_breaks(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "out.txt"
            path.write_text("old=1\n", encoding="utf-8")
            self.assertTrue(an.write_outputs(str(path), [("send", "yes"), ("message", "QUJD")]))
            self.assertEqual(path.read_text(encoding="utf-8"), "old=1\nsend=yes\nmessage=QUJD\n")
            for pairs in ([("x", "a\nb")], [("x", "a\rb")], [("send", "yes"), ("x", "a\nb=c")]):
                self.assertFalse(an.write_outputs(str(path), pairs))
            self.assertEqual(path.read_text(encoding="utf-8"), "old=1\nsend=yes\nmessage=QUJD\n")      # 거절한 것은 아무것도 쓰지 않았다
            self.assertFalse(an.write_outputs("", [("a", "b")]))
            self.assertFalse(an.write_outputs(None, [("a", "b")]))
            self.assertFalse(an.write_outputs(str(Path(tmp) / "no-dir" / "o.txt"), [("a", "b")]))

    def test_the_message_is_never_printed_by_the_module(self):
        """로그에 문장이 그대로 찍히는 일이 없다 — 판정 job 은 출력 파일에만, 발송 job 은 텔레그램으로만 낸다(출력 줄은 고정 문장뿐: 정적 시험 StaticPropertiesTest 가 out( 인자를 본다)."""
        source = MODULE.read_text(encoding="utf-8")
        self.assertEqual(source.count("encode_message("), 2)                                    # 정의 한 곳과 판정 job 의 출력 한 곳
        self.assertNotRegex(source, r"out\([^)]*(?:verdict|text|encoded|raw)\b")


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
                self.assertIn("usage:", err)                                                   # 사용법 줄도 찍는다
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

    def test_main_sends_only_for_the_send_command_and_prepares_the_output_encoding_first(self):
        """send 명령만 발송 단계로 가고(판정 명령 둘은 알림 보내기 도구를 건드리지 않는다), 시작할 때 출력 인코딩을 먼저 맞춘다."""
        net, clock = nh.FakeNet(), nh.Clock()
        notifier = notify.Notifier(dict(nh.ENV), opener=net, sleep=clock.sleep, clock=clock.clock, budget=notify.Budget())
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "s.json"
            state.write_text('{"mode": "on"}', encoding="utf-8")
            env = {an.MESSAGE_ENV: an.encode_message("[M105] 병합완료 확인 - 정상")}
            self.assertEqual(self.run_main([an.SEND], environ=env, notifier=notifier, state_file=state)[0], 0)
            self.assertEqual([body["text"] for body in net.bodies()], ["[M105] 병합완료 확인 - 정상"])
            for name in (an.READY, an.CONFIRM):
                self.run_main([name], environ={}, notifier=notifier, state_file=state)           # 값이 없어 모양 오류로 끝난다 — 발송은 없다
            self.assertEqual(net.calls, 1)
            with mock.patch.object(an, "safe_output") as prepared:
                self.run_main([an.READY], environ={}, state_file=Path(tmp) / "no_such_state.json")
            prepared.assert_called_once_with()

    def test_the_module_runs_as_a_command_and_hands_back_the_exit_code(self):
        """`python -m pipeline.auto_notice <명령>` 진입점(모듈 꼬리의 `__main__` 부분)이 실제로 main 을 부르고 종료 코드를 그대로 돌려준다 — 같은 모듈을 `__main__` 으로 다시 실행해(runpy) 본다.
        환경은 비워 시크릿·GitHub 접근이 없고, 저장소의 켬 상태 파일은 off 라 고정 한 줄만 찍고 끝난다."""
        def run_as_main(*args):
            out, err = io.StringIO(), io.StringIO()
            with mock.patch.object(sys, "argv", ["auto_notice", *args]), mock.patch.dict(os.environ, {}, clear=True), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), warnings.catch_warnings():
                warnings.simplefilter("ignore")                                               # 이미 불러온 모듈을 다시 실행한다는 runpy 의 경고
                with self.assertRaises(SystemExit) as caught:
                    runpy.run_module("pipeline.auto_notice", run_name="__main__")
            return caught.exception.code, out.getvalue().strip(), err.getvalue()
        for name in (an.READY, an.CONFIRM):
            with self.subTest(name):
                self.assertEqual(run_as_main(name)[:2], (0, an.MODE_OFF_LINE))
        self.assertEqual(run_as_main(an.SEND)[:2], (0, "병합 알림 자동: 켬 상태가 on 이 아니라 보내지 않습니다"))
        code, _out, err = run_as_main("bogus-value-xyz")
        self.assertEqual(code, 2)
        self.assertIn(an.USAGE_ERROR_LINE, err)

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
# 실제 GitHub 클라이언트와의 이음매 — 네트워크 대신 가짜 urlopen
# ----------------------------------------------------------------------------
class RoutedUrlopen:
    """기존 클라이언트(operator_loop.GitHub)의 urlopen 자리에 끼우는 가짜. 요청 주소를 경로·쪽으로 풀어 routes(FakeApi 와 같은 표 — 값은 JSON 값·Exception·Seq)에서 응답을 골라 돌려준다.
    없는 경로는 HTTP 404. 받은 요청(메서드·주소·머리·본문)을 모두 기록한다."""

    def __init__(self, routes):
        self.routes, self.requests = routes, []

    def __call__(self, request, timeout=None):
        self.requests.append(request)
        parts = urllib.parse.urlsplit(request.full_url)
        prefix = f"/repos/{REPO}"
        path = parts.path[len(prefix):] if parts.path.startswith(prefix) else parts.path
        query = urllib.parse.parse_qs(parts.query)
        keyed = (path, int(query["page"][0]) if "page" in query else None)
        if keyed in self.routes:
            value = self.routes[keyed]
        elif path in self.routes:
            value = self.routes[path]
        else:
            raise urllib.error.HTTPError(request.full_url, 404, "Not Found", {}, io.BytesIO(b'{"message": "Not Found"}'))
        if isinstance(value, Seq):
            value = value.next()
        if isinstance(value, Exception):
            raise value
        return io.BytesIO(json.dumps(value).encode("utf-8"))


class RealClientGlueTest(unittest.TestCase):
    """판정 job 이 실제로 쓰는 길 — 가짜 API 대신 기존 클라이언트(operator_loop.GitHub)를 그대로 쓰고 urlopen 만 가짜로 바꿔, 보내는 요청의 모양(메서드·주소·쿼리·머리)과 오류 매핑을 본다.
    (GitHub 를 실제로 부르지 않고 확인할 수 있는 이음매는 여기까지다 — 응답 모양은 GitHub 문서의 모양을 가정한 것이고 첫 관측은 dry 로 한다.)"""

    TOKEN = "CANARY_read_token"

    def run_real(self, kind, env, routes, mode="on"):
        spy, out = RoutedUrlopen(routes), []
        with tempfile.TemporaryDirectory() as tmp:
            temp = Path(tmp)
            state = temp / "state.json"
            state.write_text(json.dumps({"mode": mode}), encoding="utf-8")
            environ = dict(env, GITHUB_OUTPUT=str(temp / "output.txt"), GITHUB_STEP_SUMMARY=str(temp / "summary.md"))
            with mock.patch.object(urllib.request, "urlopen", spy):
                code = an.main([kind], environ=environ, out=out.append, state_file=state, sleep=no_sleep)
            files = {name: (temp / name).read_text(encoding="utf-8") if (temp / name).is_file() else None for name in ("output.txt", "summary.md")}
        return code, out, files, spy

    @staticmethod
    def requests_of(spy):
        found = []
        for request in spy.requests:
            parts = urllib.parse.urlsplit(request.full_url)
            found.append((request.get_method(), parts.path, urllib.parse.parse_qs(parts.query)))
        return found

    def test_the_ready_path_sends_three_get_requests_with_the_expected_questions_and_the_read_token_only(self):
        code, out, files, spy = self.run_real(an.READY, ready_env(), ready_routes())
        self.assertEqual(code, 0)
        self.assertEqual(self.requests_of(spy), [
            ("GET", f"/repos/{REPO}/pulls", {"state": ["open"], "head": ["octo:" + BRANCH], "base": ["main"], "per_page": ["5"]}),
            ("GET", f"/repos/{REPO}/pulls/{PR_NUMBER}/files", {"per_page": ["100"], "page": ["1"]}),
            ("GET", f"/repos/{REPO}/actions/runs", {"branch": [BRANCH], "head_sha": [SHA], "event": ["push"], "per_page": ["100"]})])
        for request in spy.requests:
            self.assertTrue(request.full_url.startswith(ol.API_ROOT + "/repos/" + REPO + "/"))
            self.assertIsNone(request.data)                                                         # 본문이 없다 — 읽기뿐
            self.assertEqual(request.get_header("Authorization"), "Bearer " + self.TOKEN)
            self.assertEqual(request.get_header("Accept"), "application/vnd.github+json")
        lines = files["output.txt"].splitlines()                                                    # 출력은 두 줄뿐: send=yes 와 message=<base64 한 줄>
        self.assertEqual((len(lines), lines[0], lines[1][:8]), (2, "send=yes", "message="))
        text = an.decode_message(lines[1][len("message="):])
        self.assertEqual(an.message_problem(text), "")
        self.assertTrue(text.startswith("[M105] 병합 부탁 — "))
        self.assertNotIn(self.TOKEN, files["summary.md"] + "\n".join(out))
        self.assertNotIn(lines[1][len("message="):], files["summary.md"] + "\n".join(out))

    def test_the_confirm_path_sends_four_get_requests_and_writes_a_normal_confirmation(self):
        code, out, files, spy = self.run_real(an.CONFIRM, confirm_env(), confirm_routes())
        self.assertEqual(code, 0)
        self.assertEqual(self.requests_of(spy), [
            ("GET", f"/repos/{REPO}/commits/{SHA}", {}),
            ("GET", f"/repos/{REPO}/commits/{SHA}/pulls", {"per_page": ["10"]}),
            ("GET", f"/repos/{REPO}/pulls/{PR_NUMBER}", {}),
            ("GET", f"/repos/{REPO}/commits/{HEAD_SHA}", {})])
        self.assertTrue(all(request.data is None for request in spy.requests))
        self.assertEqual(files["output.txt"], "send=yes\nmessage=" + an.encode_message(notify.merged_title("M105", an.CONFIRM_OK)) + "\n")

    def test_an_unknown_route_is_http_404_and_ends_quietly_with_the_fixed_sentence_and_no_token_in_the_output(self):
        code, out, files, spy = self.run_real(an.READY, ready_env(), {})
        self.assertEqual(code, 0)
        self.assertEqual(len(spy.requests), 1)                                                      # 404 는 일시 오류가 아니라 다시 부르지 않는다
        self.assertIn(an.REASONS["api_error"][0], files["summary.md"])
        self.assertIsNone(files["output.txt"])
        self.assertNotIn(self.TOKEN, "\n".join(out) + files["summary.md"])
        self.assertTrue(any(line.startswith("::warning::") for line in out))                      # api_error 는 눈에 띄게(경고) 남는다

    def test_a_transient_server_error_is_retried_once_by_the_existing_client_and_other_errors_are_not_retried(self):
        bad = urllib.error.HTTPError("x", 502, "Bad Gateway", {}, io.BytesIO(b"{}"))
        spy = RoutedUrlopen({"/pulls": Seq(bad, [pr_item()])})
        reader = an.Reader(ol.GitHub(REPO, self.TOKEN, opener=spy, sleep=no_sleep))
        self.assertEqual(reader.get("/pulls", state="open"), [pr_item()])
        self.assertEqual(len(spy.requests), 2)
        missing = RoutedUrlopen({})
        with self.assertRaises(an.Skip) as caught:
            an.Reader(ol.GitHub(REPO, self.TOKEN, opener=missing, sleep=no_sleep)).get("/pulls")
        self.assertEqual((caught.exception.code, len(missing.requests)), ("api_error", 1))

    def test_dry_reads_with_the_real_client_but_leaves_no_output_and_off_never_calls_it(self):
        code, out, files, spy = self.run_real(an.READY, ready_env(), ready_routes(), mode="dry")
        self.assertEqual((code, len(spy.requests)), (0, 3))
        self.assertIsNone(files["output.txt"])
        self.assertIn("보낼 문장", files["summary.md"])
        code, out, files, spy = self.run_real(an.READY, ready_env(), ready_routes(), mode="off")
        self.assertEqual((code, spy.requests, files["output.txt"]), (0, [], None))

    def test_the_default_reader_wraps_the_existing_client_with_the_repository_and_the_read_token(self):
        reader = an._build_reader({"GITHUB_TOKEN": self.TOKEN, "GITHUB_REPOSITORY": REPO})
        self.assertIsInstance(reader, an.Reader)
        self.assertIsInstance(reader._api, ol.GitHub)
        self.assertEqual(reader._api.repo, REPO)
        for env in ({}, {"GITHUB_TOKEN": ""}, {"GITHUB_TOKEN": "   "}):
            with self.subTest(env):
                with self.assertRaises(an.Skip) as caught:
                    an._build_reader(env)
                self.assertEqual(caught.exception.code, "api_error")


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
        self.assertEqual(names, {"argparse", "base64", "binascii", "json", "os", "re", "stat", "sys", "time", "unicodedata", "collections", "pathlib", "pipeline", "pipeline.console", "pipeline.secret_patterns"})

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
