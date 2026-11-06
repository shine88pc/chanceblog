"""번호 있는 알림(TG-STD: 진행 현황 P001·병합 요청 M001·확인 요청 001)과 새 답변 양식(대상번호·선택·내용) 시험 공용 도구.

네트워크·실제 GitHub·실제 텔레그램은 쓰지 않는다. 가짜 GitHub 는 operator_loop_helpers.FakeGitHub 에 '이슈 목록 읽기'(앞서 올라온 답 찾기)를 더한 것이고,
텔레그램은 notify_helpers.FakeNet 이다. 요청 파일 글·이슈 본문은 양식이 만드는 모양 그대로 지어 쓴다.
"""
import re
import subprocess

import _bootstrap
import operator_loop_helpers as oh
from notify_helpers import FakeResponse
from pipeline import operator_loop as ol

ROOT = _bootstrap.ROOT
OWNER, REPO = oh.OWNER, oh.REPO


# ---- 요청 파일 ----------------------------------------------------------------------------------
PROGRESS = {"at": "2026-11-06 12:07", "now": "5채널 주제 엔진 P3 독립 검증 중", "changed": "P3 구현·시험 통과", "next": "검증 통과 시 병합 요청", "eta": "11-06 15:00경(추정)",
            "waiting": "없음"}
MERGE = {"repo": "shine88pc/chanceblog-desktop", "target": "5채널 전략 P2b 후보 조립 부품", "pr_title": "[R-160] 5채널 전략 'P2b' — 후보 조립 순수 부품 [대상: 데스크톱]",
         "verify": "독립 검증 통과 · 검사 4칸 초록 · 변경 45개 파일"}
ASK = {"options": "지금부터 적용 / 새 번호 체계 병합 뒤부터 적용 / 바꾸지 않음", "default": "1", "approve": "2"}
KIND_OF = {"P": "info", "M": "merge", "": "decision"}                  # 번호 유형 → 기본 kind
BODY_OF = {"P": PROGRESS, "M": MERGE, "": ASK}


def notice_text(number=166, no="P001", kind=None, title="[R-166] 진행 현황", summary="현황 알림입니다", fields=None, urgency=None, work=None, pr=None, created="2026-11-06",
                drop=(), extra="", body="상세 설명\n"):
    """번호 있는 요청 파일 글. fields 를 주지 않으면 번호 유형에 맞는 표준 칸을 쓴다. drop 은 뺄 키, None 값 키는 줄 자체를 뺀다."""
    prefix = no[:1] if no[:1] in ("P", "M") else ""
    kind = kind or KIND_OF[prefix]
    fields = dict(BODY_OF[prefix] if fields is None else fields)
    pairs = [("id", f"R-{number:03d}"), ("kind", kind), ("title", title), ("summary", summary), ("urgency", urgency), ("pr", pr), ("created", created), ("no", no), ("work", work)]
    pairs += list(fields.items())
    lines = [f"{key}: {value}" for key, value in pairs if value is not None and key not in drop]
    return "---\n" + "\n".join(lines) + ("\n" + extra if extra else "") + "\n---\n" + body


def name_of(number=166, slug="notice"):
    return f"R-{number:03d}_{slug}.md"


def parse(text, number=166, strict=False):
    return ol.parse_request(name_of(number), text, strict=strict)


def code_of(text, number=166, strict=False):
    try:
        ol.parse_request(name_of(number), text, strict=strict)
    except ol.RequestError as exc:
        return exc.code
    return ""


# ---- 이슈 본문(새 답변 양식이 만드는 모양) ---------------------------------------------------------------
def answer_body(target="001", choice="선택 안 함", memo="", crlf=True, target_raw=None):
    """새 양식 `ai-answer.yml` 이 만드는 본문(`### 항목 제목` 아래에 값, 빈 선택 항목은 `_No response_`)."""
    shown = target if target_raw is None else target_raw
    body = f"### 대상번호\n\n{shown or '_No response_'}\n\n### 선택\n\n{choice or '_No response_'}\n\n### 내용\n\n{memo or '_No response_'}"
    return body.replace("\n", "\r\n") if crlf else body


class NoticeGitHub(oh.FakeGitHub):
    """FakeGitHub + `GET /issues`(앞서 올라온 답 찾기). issues: 목록이 돌려줄 이슈들(딕셔너리), list_failure: 목록을 읽을 때 낼 예외."""

    def __init__(self, issues=(), list_failure=None, **kwargs):
        super().__init__(**kwargs)
        self.issues, self.list_failure = list(issues), list_failure

    def _route(self, method, path, payload):
        if method == "GET" and path == "/issues":
            if self.list_failure is not None:
                raise self.list_failure
            return FakeResponse(200, self.issues)
        return super()._route(method, path, payload)


class NoticeGit(oh.RequestGit):
    """RequestGit + 알림 번호 겹침 확인이 부르는 git(`for-each-ref`·`grep -l -z -E`)을 흉내 낸다. refs: 원격 가지 ref 이름들, holders: [(ref, 경로, 앞머리 `no:` 줄)] — grep 은 주어진 ref 중에서
    그 줄이 정규식에 맞는 항목의 `ref:경로` 를 NUL 로 이어 돌려준다(없으면 종료 코드 1, 실제 git grep 과 같다). broken: 실패시킬 명령 이름 집합."""

    def __init__(self, *args, refs=(), holders=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.refs, self.holders = list(refs), list(holders)

    def grep_calls(self):
        return [args for args, _ in self.calls if args[1] == "grep"]

    def __call__(self, args, **kwargs):
        command = args[1]
        if command not in ("for-each-ref", "grep"):
            return super().__call__(args, **kwargs)
        self.calls.append((list(args), kwargs))
        if command in self.broken:
            return subprocess.CompletedProcess(args, 128, stdout=b"", stderr=b"fatal")
        if command == "for-each-ref":
            return subprocess.CompletedProcess(args, 0, stdout=("\n".join(self.refs) + "\n").encode("utf-8"), stderr=b"")
        pattern = args[args.index("-e") + 1]
        given = args[args.index("-e") + 2:args.index("--")]
        hits = [f"{ref}:{path}" for ref, path, line in self.holders if ref in given and re.search(pattern, line)]
        if not hits:
            return subprocess.CompletedProcess(args, 1, stdout=b"", stderr=b"")
        return subprocess.CompletedProcess(args, 0, stdout="".join(f"{hit}\0" for hit in hits).encode("utf-8"), stderr=b"")


def issue_item(number, body, title="[답변] ", login=OWNER, association="OWNER", pull_request=False):
    item = {"number": number, "title": title, "body": body, "user": {"login": login}, "author_association": association}
    if pull_request:
        item["pull_request"] = {"url": "https://example.invalid/pr"}
    return item


def answer_event(number=145, body=None, **kwargs):
    return oh.issue_event(number=number, title="[답변] ", body=answer_body() if body is None else body, **kwargs)
