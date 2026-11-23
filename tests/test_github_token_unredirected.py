"""GitHub 토큰(Authorization)은 리다이렉트가 복사하지 않는 머리글로만 실린다(BP-S1-8, 결함 D-418) — 여섯 클라이언트 모두. 네트워크 없이 돈다(가짜 opener).

배경: urllib 의 기본 리다이렉트 처리기는 새 주소로 요청을 다시 만들 때 `Request.headers` 의 항목을 모두 복사한다 — Authorization 이 거기 있으면 토큰이 다른 호스트로도 간다(Unsplash 키는 이미
add_unredirected_header 로 막혀 있었다). 지금 부르는 GitHub API 경로는 같은 호스트로만 되돌릴 수 있어 위험은 아니었고 방어 한 겹이 비어 있던 것이다. 이제 여섯 곳(초안 올리기·운영자 응답·초안 패키지·
상태 도구·확인 필요 모음·워치독)이 토큰을 `unredirected_hdrs` 에만 싣는다 — 보낼 때는 실리고(get_header·header_items), 리다이렉트로 만든 새 요청에는 없다.
"""
import json
import sys
import unittest
import urllib.request

import _bootstrap

sys.path.insert(0, str(_bootstrap.ROOT / "scripts"))      # 상태 도구·확인 필요 모음·워치독 스크립트(scripts/)를 불러온다

import github_status  # noqa: E402
import ops_inbox  # noqa: E402
import watchdog  # noqa: E402
from pipeline import drafts, operator_loop  # noqa: E402
from pipeline.publishers import issue_package  # noqa: E402

TOKEN = "CANARY_" + "GITHUB_" + "TOKEN_" + "VALUE_0123456789"      # 조립한 가짜 토큰(소스에 비밀 모양 리터럴을 두지 않는다)
REPO = "owner1/repo1"


class FakeResponse:
    def __init__(self, body):
        self._body = body

    def read(self, *args):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class Recorder:
    """요청을 기록하는 가짜 opener(urlopen 과 같은 모양: opener(request, timeout=…))."""

    def __init__(self):
        self.requests = []

    def __call__(self, request, timeout=None):
        self.requests.append(request)
        return FakeResponse(b"[]")


def drafts_call(rec):
    drafts.GitHubClient(REPO, TOKEN, opener=rec).request("GET", "/issues")


def operator_call(rec):
    operator_loop.GitHub(REPO, TOKEN, opener=rec, sleep=lambda seconds: None).request("GET", "/issues")


def package_call(rec):
    issue_package.IssuePackagePublisher(REPO, TOKEN, opener=rec, sleep=lambda seconds: None)._request("GET", "/issues")


def status_call(rec):
    github_status.Client(REPO, opener=rec, token=TOKEN).get("/repos/" + REPO + "/issues")


def inbox_call(rec):
    ops_inbox.GitHubClient(REPO, TOKEN, opener=rec).request("GET", "/issues")


def watchdog_call(rec):
    watchdog.GitHubClient(TOKEN, REPO, opener=rec)._request("GET", "/repos/" + REPO + "/issues")


CLIENTS = {"초안 올리기(drafts)": drafts_call, "운영자 응답(operator_loop)": operator_call, "초안 패키지(issue_package)": package_call,
           "상태 도구(github_status)": status_call, "확인 필요 모음(ops_inbox)": inbox_call, "워치독(watchdog)": watchdog_call}


class TokenIsNotRedirectCopiedTest(unittest.TestCase):
    def capture(self, call):
        rec = Recorder()
        call(rec)
        self.assertEqual(len(rec.requests), 1)
        return rec.requests[0]

    def test_the_token_is_sent_but_only_in_the_header_slot_a_redirect_does_not_copy(self):
        for kind, call in CLIENTS.items():
            with self.subTest(client=kind):
                request = self.capture(call)
                self.assertEqual(request.get_header("Authorization"), f"Bearer {TOKEN}")             # 보낼 때는 실린다
                self.assertEqual(request.unredirected_hdrs.get("Authorization"), f"Bearer {TOKEN}")  # 복사하지 않는 칸에 있다
                self.assertNotIn("Authorization", request.headers)                                  # 복사하는 칸에는 없다
                self.assertIn(("Authorization", f"Bearer {TOKEN}"), request.header_items())          # 실제로 보낼 머리글 목록에는 든다

    def test_the_request_a_redirect_builds_for_another_host_has_no_token(self):
        for kind, call in CLIENTS.items():
            with self.subTest(client=kind):
                request = self.capture(call)
                new = urllib.request.HTTPRedirectHandler().redirect_request(request, None, 302, "Found", {}, "https://evil.example/steal")
                self.assertEqual(new.full_url, "https://evil.example/steal")
                self.assertTrue(new.get_header("User-agent"), kind)                                 # 복사할 머리글은 복사됐다(이 시험이 빈 그릇이 아니다)
                self.assertEqual([name for name, _value in new.header_items() if name.lower() == "authorization"], [], kind)
                self.assertNotIn(TOKEN, repr(new.header_items()))
                self.assertNotIn(TOKEN, repr(new.unredirected_hdrs))

    def test_the_other_headers_and_the_body_are_unchanged(self):
        """토큰만 옮겼다: 나머지 머리글(Accept·API 버전·User-Agent)은 그대로 복사하는 칸에 남는다."""
        for kind, call in CLIENTS.items():
            with self.subTest(client=kind):
                request = self.capture(call)
                lowered = {name.lower(): value for name, value in request.headers.items()}
                self.assertEqual(lowered.get("accept"), "application/vnd.github+json", kind)
                self.assertTrue(lowered.get("user-agent", "").startswith("chanceblog-"), kind)

    def test_a_request_with_a_body_keeps_its_content_type_and_still_hides_the_token(self):
        rec = Recorder()
        drafts.GitHubClient(REPO, TOKEN, opener=rec).request("POST", "/issues", {"title": "x"})
        request = rec.requests[0]
        self.assertEqual(json.loads(request.data.decode("utf-8")), {"title": "x"})
        self.assertEqual({name.lower(): value for name, value in request.headers.items()}.get("content-type"), "application/json")
        self.assertNotIn("Authorization", request.headers)

    def test_no_token_means_no_authorization_header_in_the_clients_that_allow_it(self):
        rec = Recorder()
        github_status.Client(REPO, opener=rec).get("/repos/" + REPO + "/issues")
        ops_inbox.GitHubClient(REPO, None, opener=rec).request("GET", "/issues")
        for request in rec.requests:
            self.assertEqual([name for name, _value in request.header_items() if name.lower() == "authorization"], [])

    def test_the_source_never_puts_the_token_in_a_headers_dict_again(self):
        """구조 확인: 여섯 파일 어디에도 `"Authorization"` 을 사전 머리글(headers=…)에 싣는 줄이 없다 — 모두 add_unredirected_header 다."""
        for rel in ("pipeline/drafts.py", "pipeline/operator_loop.py", "pipeline/publishers/issue_package.py", "scripts/github_status.py", "scripts/ops_inbox.py", "scripts/watchdog.py"):
            text = (_bootstrap.ROOT / rel).read_text(encoding="utf-8")
            with self.subTest(file=rel):
                self.assertIn('add_unredirected_header("Authorization"', text)
                self.assertNotIn('"Authorization": f"Bearer', text)
                self.assertNotIn('headers["Authorization"]', text)


if __name__ == "__main__":
    unittest.main()
