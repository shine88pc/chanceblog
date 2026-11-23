"""운영 호스트 규칙 표(egress.OPS_RULES)의 api.github.com 경로를 코드가 실제로 부르는 꼴로 좁혔다(BP-S1-7, 결함 D-417) — 좁힌 뒤에도 코드가 부르는 경로는 전부 허용되고, 부르지 않는 쓰기 경로는 거부된다. 네트워크 없이 돈다.

배경: 예전 규칙은 `/repos/{저장소}/(issues|labels|pulls|commits|actions|check-runs)` 뒤에 어떤 조각이든 받아 병합(pulls/N/merge)·변수 쓰기(actions/variables/…)·시크릿 쓰기(actions/secrets/…)가 허용 안에 들어 있었다.
코드가 실제로 부르는 것은 이슈·라벨·PR 만들기와 조회·워크플로 dispatches 뿐이고 병합·변수·시크릿 쓰기는 0건이라 지금은 위험이 아니었다 — 다만 이 표는 '허용 목록'처럼 읽혀 누가 호출 관문에 연결하면 그 길이 열린다.
이 시험은 두 가지를 지킨다: ① 호출부 일곱 파일에서 코드가 만드는 경로 꼴을 AST 로 뽑아 모두 허용인지 본다(새 호출이 규칙 밖이면 이 시험이 빨개져 규칙을 일부러 고치게 한다) ② 명시한 실제 호출 목록은 허용, 병합·변수·시크릿 같은 쓰기는 거부.
(거부 경로의 긴 목록은 tests/test_egress.py 의 DENIED_PATHS.)
"""
import ast
import re
import unittest

import _bootstrap
from pipeline import egress

ROOT = _bootstrap.ROOT
OWN = "owner1/repo1"
CALL_SITE_FILES = ("pipeline/drafts.py", "pipeline/operator_loop.py", "pipeline/publishers/issue_package.py", "pipeline/draft_flow.py",
                   "scripts/github_status.py", "scripts/ops_inbox.py", "scripts/watchdog.py")
# 코드가 만드는 경로 꼴(저장소 안 경로의 머리 낱말이나 /rate_limit) — 문장·설명 글은 통째로 맞지 않아 걸리지 않는다
PATH_SHAPE = re.compile(r"^/(?:repos/\{\}/)?(?:(?:issues|labels|pulls|commits|actions|check-runs)(?:/[A-Za-z0-9_.{}%\-]*)*|rate_limit)$")

# 지금 코드가 실제로 부르는 경로(2026-11-23 호출부를 grep 으로 확인): 이슈 목록·만들기·상세·고치기·댓글·라벨, 라벨 목록·만들기·하나, PR 목록·만들기·상세, 커밋 상세와 검사 실행, Actions 실행 조회·
# 작업 목록·워크플로별 실행, 워크플로 dispatches, 검사 실행 주석, 한도 조회
REAL_CALLS = (
    "/repos/{o}/issues", "/repos/{o}/issues/12", "/repos/{o}/issues/12/comments", "/repos/{o}/issues/12/labels",
    "/repos/{o}/labels", "/repos/{o}/labels/some-label",
    "/repos/{o}/pulls", "/repos/{o}/pulls/12",
    "/repos/{o}/commits/main", "/repos/{o}/commits/0123abcd/check-runs",
    "/repos/{o}/actions/runs", "/repos/{o}/actions/runs/9/jobs", "/repos/{o}/actions/workflows/chanceblog.yml/runs", "/repos/{o}/actions/workflows/pages.yml/dispatches",
    "/repos/{o}/check-runs/5/annotations",
    "/rate_limit",
)
# 코드가 부르지 않는 쓰기 경로(병합·리뷰·변수·시크릿·실행 취소/재실행·워크플로 켜고 끄기)
NOT_CALLED = (
    "/repos/{o}/pulls/12/merge", "/repos/{o}/pulls/12/reviews",
    "/repos/{o}/actions/variables", "/repos/{o}/actions/variables/PIPELINE_PAUSE", "/repos/{o}/actions/secrets", "/repos/{o}/actions/secrets/GEMINI_API_KEY",
    "/repos/{o}/actions/runs/9/cancel", "/repos/{o}/actions/runs/9/rerun", "/repos/{o}/actions/workflows/pages.yml/disable", "/repos/{o}/actions/workflows/pages.yml/enable",
    "/repos/{o}/git/refs", "/repos/{o}/contents/README.md", "/repos/{o}/merges", "/repos/{o}/branches/main/protection",
)


def allowed(path, purpose="ops_repo", own=OWN):
    try:
        egress.check_url("https://api.github.com" + path.format(o=own if own else "x/y"), purpose, None, own)
    except egress.EgressDenied:
        return False
    return True


def code_path_templates(rel):
    """파일 안의 문자열(보통 문자열과 f-문자열)에서 GitHub 경로 꼴을 뽑는다. f-문자열의 값 자리는 `{}`, 질의(?…)는 뗀다."""
    found = set()
    tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
    pieces = {id(part) for node in ast.walk(tree) if isinstance(node, ast.JoinedStr) for part in node.values}      # f-문자열의 글자 조각은 따로 보지 않는다(통째로 JoinedStr 로 본다)
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) in pieces:
                continue
            template = node.value
        elif isinstance(node, ast.JoinedStr):
            template = "".join(part.value if isinstance(part, ast.Constant) else "{}" for part in node.values)
        else:
            continue
        template = template.split("?", 1)[0]
        if template.endswith("/"):
            template += "x"                              # `"/labels/" + 이름` 처럼 뒤에 값이 이어지는 머리
        if PATH_SHAPE.match(template):
            found.add(template)
    return found


def url_of(template):
    if template.startswith("/repos/{}"):
        path = "/repos/" + OWN + template[len("/repos/{}"):]
    elif template.startswith("/rate_limit"):
        path = template
    else:
        path = "/repos/" + OWN + template
    return path.replace("{}", "12")


class OpsRulesNarrowedTest(unittest.TestCase):
    def test_every_path_the_code_really_calls_is_still_allowed(self):
        for path in REAL_CALLS:
            with self.subTest(path=path):
                self.assertTrue(allowed(path), path)

    def test_the_write_paths_the_code_never_calls_are_denied_for_every_purpose(self):
        purposes = ("ops_repo", "ops_notify", "ops_publish", "ops_llm", "ops_auth", "fact", "feed", "page", "resolve", "web", "ops", "")
        for path in NOT_CALLED:
            for purpose in purposes:
                with self.subTest(path=path, purpose=purpose):
                    self.assertFalse(allowed(path, purpose), (path, purpose))

    def test_a_path_with_extra_pieces_after_a_known_one_is_denied(self):
        """예전 규칙은 알려진 경로 뒤에 어떤 조각이든 받았다 — 이제 알려진 꼴 그대로만 받는다."""
        for extra in ("/merge", "/x", "/x/y", "/..", "/%2e%2e", "/"):
            for base in ("/repos/{o}/pulls/12", "/repos/{o}/issues/12/comments", "/repos/{o}/labels/some-label", "/repos/{o}/check-runs/5/annotations", "/repos/{o}/commits/0123abcd/check-runs",
                         "/repos/{o}/actions/runs/9/jobs", "/repos/{o}/actions/workflows/a.yml/runs"):
                with self.subTest(path=base + extra):
                    self.assertFalse(allowed(base + extra), base + extra)

    def test_the_rule_table_has_only_the_known_shapes_and_the_rate_limit(self):
        rule = next(rule for rule in egress.OPS_RULES if rule.host == "api.github.com")
        self.assertEqual(rule.purposes, ("ops_repo",))
        repo_shapes = [pattern for pattern in rule.paths if pattern.startswith("/repos/{repo}/")]
        self.assertEqual(len(repo_shapes), 7)
        self.assertIn("/rate_limit", rule.paths)
        for pattern in repo_shapes:
            self.assertNotIn("merge", pattern)
            self.assertNotIn("(?:/[^/]+)*", pattern)           # 예전의 '뒤에 무엇이든' 꼴이 남아 있지 않다


class CallSiteCrossCheckTest(unittest.TestCase):
    """호출부 일곱 파일이 만드는 경로 꼴이 모두 규칙 안인가 — 새 호출 경로가 생겨 규칙 밖이면 이 시험이 알린다(규칙을 일부러 고치게)."""

    def test_the_scan_finds_the_known_shapes_in_the_call_sites(self):
        found = set()
        for rel in CALL_SITE_FILES:
            found |= code_path_templates(rel)
        for needle in ("/issues", "/pulls", "/labels", "/rate_limit", "/issues/{}/comments", "/actions/workflows/{}/dispatches", "/commits/{}/check-runs", "/check-runs/{}/annotations"):
            self.assertTrue(any(needle == template or template.endswith(needle) for template in found), (needle, sorted(found)))
        self.assertGreaterEqual(len(found), 15, sorted(found))

    def test_every_path_shape_the_call_sites_build_is_allowed(self):
        for rel in CALL_SITE_FILES:
            templates = code_path_templates(rel)
            for template in sorted(templates):
                with self.subTest(file=rel, template=template):
                    url = url_of(template)
                    try:
                        egress.check_url("https://api.github.com" + url, "ops_repo", None, OWN)
                    except egress.EgressDenied as exc:
                        self.fail(f"{rel} 가 만드는 경로 꼴 {template} 이 운영 규칙 밖입니다({exc}) — 코드가 이 경로를 정말 부르면 egress.OPS_RULES 에 그 꼴을 더하고, 아니면 호출을 지웁니다")

    def test_the_scan_notices_a_shape_the_rule_does_not_allow(self):
        """탐지기 자체가 살아 있다는 증명: 규칙 밖 꼴(병합)을 가짜 소스에서 뽑으면 거부된다."""
        tree = ast.parse("path = f'/pulls/{n}/merge'")
        template = "".join(part.value if isinstance(part, ast.Constant) else "{}" for part in tree.body[0].value.values)
        self.assertTrue(PATH_SHAPE.match(template))
        with self.assertRaises(egress.EgressDenied):
            egress.check_url("https://api.github.com" + url_of(template), "ops_repo", None, OWN)


if __name__ == "__main__":
    unittest.main()
