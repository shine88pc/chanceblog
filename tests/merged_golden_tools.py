"""병합완료 확인(`kind: merged`) 추가가 **다른 종류의 알림과 옛 요청 파일의 읽기를 바꾸지 않았음**을 '옛 코드의 출력과 바이트까지 같다'로 못박는 결정적 표본(골든) 도구 — tests/test_merged_notice_requests.py 가 쓴다.

왜 이렇게 하나: 알림 코드는 운영자 알림 **전부**(진행 현황·병합 요청·확인 요청·옛 모양)가 지나는 길이다. 새 종류를 더하면서 다른 종류의 폰 글·단추·요청 파일 판정이 한 글자라도 달라지면 안 된다.
그래서 이 변경을 하기 직전의 코드(main 299fda3)로 같은 표본을 돌려 출력의 지문(sha256)과 눈으로 읽을 수 있는 글 몇 개를 `tests/merged_golden_data.py` 에 적어 두고, 시험이 지금 코드의 출력을 그것과 견준다.
표본은 코드로 만든 결정적 목록이다(무작위 없음 — 파이썬 해시 시드와 무관). 줄 끝(CRLF)·경로·시각·환경에 기대지 않는다(리눅스 CI 와 같은 결과).

이 도구는 `pipeline` 을 직접 가져오지 않고 모듈을 인자로 받는다(옛 코드의 `pipeline` 과 지금 코드의 `pipeline` 에 같은 표본을 돌릴 수 있게). 시험 도우미(notice_helpers·operator_loop_helpers·notify_helpers)는 가져오는 쪽 저장소의 것이다.

골든을 일부러 바꿔야 할 때(다른 종류의 알림 모양을 의식적으로 고치는 변경): `python tests/merged_golden_tools.py` 를 저장소 루트에서 실행하면 지금 코드의 지문과 글이 JSON 으로 나온다 —
`tests/merged_golden_data.py` 의 값을 그것으로 바꾸고 변경 이유를 커밋 메시지에 적는다. 표본에서 일부러 뺀 것: 앞머리 `result` 칸(병합완료 확인이 쓰는 새 칸 — 다른 종류에 쓰면 이제 거절이고 전에는 모르는 칸이었다)과 `kind: merged`.
"""
import hashlib
import json
import sys
import tempfile
from pathlib import Path

import notice_helpers as nth
import operator_loop_helpers as oh

KINDS = ("merge", "run", "confirm", "decision", "info")           # 병합완료 확인(merged)을 더하기 전부터 있던 요청 종류 다섯
ZW = chr(0x200B)
CONSTANT_AT_RECORDING = 173                                       # 골든을 만들 때 상수 NOTICE_NO_REQUIRED_FROM_R 의 값 — 시험은 이 값으로 고정해 돌린다(상수를 올려도 골든이 깨지지 않게)

PROGRESS = dict(nth.PROGRESS)
MERGE = dict(nth.MERGE)
ASK = {**nth.ASK, "summary": "무엇을 할까요"}


def nasty():
    """한 줄 칸에 넣어 보는 값들(소독·표시 규칙을 건드리는 것)."""
    return ["", "   ", "평범한 한 줄", "@owner 에게 R-090 확인 <b>굵게</b> & 끝", "「R-090」 인용과 `R-091` 코드", "https://example.com/a?b=c 와 tg://resolve",
            "줄\n바꿈\r\n있음", "보이지" + ZW + "않는 글자", "AIza" + "x" * 35 + " 비밀 모양", "가" * 260, "[R-090] 꼬리표 제목", "key=value token=abc"]


def digest(items):
    raw = json.dumps(items, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def outcome(function, *args, **kwargs):
    """함수 결과 또는 던진 예외(종류와 첫 인자)를 JSON 으로 쓸 수 있는 값으로."""
    try:
        return ["ok", function(*args, **kwargs)]
    except Exception as exc:  # noqa: BLE001 - 표본 도구: 어떤 예외든 종류와 첫 인자(그리고 있으면 code)만 적는다
        return ["err", type(exc).__name__, str(exc.args[0]) if exc.args else "", str(getattr(exc, "code", ""))]


# ---- 폰 글(notify.format_notice·format_ai_request) ----------------------------------------------------------
def notice_message_cases(notify):
    out = []
    for key in ("now", "changed", "next", "eta", "waiting", "check"):
        for value in nasty():
            out.append(outcome(notify.format_notice, "P012", {**PROGRESS, key: value}))
    for key in PROGRESS:
        out.append(outcome(notify.format_notice, "P012", {name: value for name, value in PROGRESS.items() if name != key}))
    for at in ("2026-11-06 12:07", "2026-11-06", "2026-13-06 12:07", "2026-11-31 12:07", "", None):
        out.append(outcome(notify.format_notice, "P012", {**PROGRESS, "at": at}))
    titles = ["[R-160] 5채널 전략 'P2b' — 후보 조립 [대상: 공통]", "<b>굵게</b> & <i>x</i>", "@owner 제목 R-160", "https://example.com/x", "가" * 200, "가" * 400, "AIza" + "x" * 35, "", "a" + ZW + "b",
              " 앞뒤 공백 ", '"따옴표로 감싼 제목"', "key=value"]
    for title in titles:
        out.append(outcome(notify.format_notice, "M007", {**MERGE, "pr_title": title}))
    for key in ("repo", "target", "verify", "state"):
        for value in nasty():
            out.append(outcome(notify.format_notice, "M007", {**MERGE, key: value}))
    for key in MERGE:
        out.append(outcome(notify.format_notice, "M007", {name: value for name, value in MERGE.items() if name != key}))
    options = [None, "", "하나", "가 / 나", "가 / 나 / 다 / 라 / 마", "가 / 나 / 다 / 라 / 마 / 바", "가 /  / 나", "<b>가</b> / @나", "가" * 80 + " / 나"]
    marks = [None, "", "0", "1", "2", "5", "6", "x", "01"]
    for option in options:
        for default in marks:
            for approve in marks:
                fields = {"summary": "무엇을 할까요"}
                for name, value in (("options", option), ("default", default), ("approve", approve)):
                    if value is not None:
                        fields[name] = value
                out.append(outcome(notify.format_notice, "003", fields))
    for value in nasty():
        out.append(outcome(notify.format_notice, "003", {**ASK, "summary": value}))
    base = {"P012": PROGRESS, "M007": MERGE, "003": ASK}
    for no, fields in base.items():
        for urgency in ("보통", "급함", "x", None):
            for work in ("", "R-160", "r160", "bad", None):
                for pr in (None, 5, True, 0, "x"):
                    for more in (0, 2, -1, "x"):
                        out.append(outcome(notify.format_notice, no, fields, urgency=urgency, work=work, pr=pr, more=more))
    for no in ("", "P1", "P0012", "M50", "0003", "x", None, "P000", "1000", "P9999", "P10000"):
        out.append(outcome(notify.format_notice, no, PROGRESS))
    return out


def ai_request_message_cases(notify):
    out = []
    values = nasty()
    for kind in KINDS:
        for title in values:
            for summary in values[:6] + values[8:10]:
                for urgency in ("보통", "급함"):
                    out.append(outcome(notify.format_ai_request, "R-001", kind, title, summary, urgency=urgency))
        for urgency in ("보통", "급함", "높음", "", None):
            for pr in (None, 7, True, 0, "x", 10 ** 7):
                for more in (0, 3, -1, "x"):
                    out.append(outcome(notify.format_ai_request, "R-090", kind, "제목", "요약", urgency=urgency, pr=pr, more=more))
    for request_id in ("R-001", "r001", "R-1", "R-0001", "", None):
        out.append(outcome(notify.format_ai_request, request_id, "decision", "제목", "요약"))
    for kind in ("bogus", "", None, "MERGE"):
        out.append(outcome(notify.format_ai_request, "R-001", kind, "제목", "요약"))
    return out


# ---- 단추 -------------------------------------------------------------------------------------------------
def button_cases(ol):
    out = []
    fields_of = {"": (), "P012": (), "M007": (("repo", ol.BLOG_REPO),), "M008": (("repo", "shine88pc/chanceblog-desktop"),), "003": ()}
    for kind in KINDS:
        for no in fields_of:
            for pr in (None, 5):
                for ref in ("ai/claude/x", "ai/claude/한글 이름", "ai/claude/NO-MERGE-operator-requests"):
                    request = ol.Request("R-166", kind, "t", "s", "보통", pr, "", "R-166_notice.md", no, "", fields_of[no], "")
                    out.append([list(item) for item in ol.request_buttons(request, ref, "main")])
    return out


# ---- 요청 파일 읽기(parse_request) ----------------------------------------------------------------------------
def front(kind, shape, extra, number):
    """요청 파일 글(앞머리 + 본문): shape 는 옛 모양(old)·번호 유형(P·M·ask)."""
    title = f"[R-{number:03d}] 제목"
    lines = [f"id: R-{number:03d}", *([f"kind: {kind}"] if kind is not None else []), f"title: {title}", "summary: 요약 한 줄"]
    if shape == "P":
        lines += ["no: P012", *(f"{key}: {value}" for key, value in PROGRESS.items())]
    elif shape == "M":
        lines += ["no: M007", *(f"{key}: {value}" for key, value in MERGE.items())]
    elif shape == "ask":
        lines += ['no: "003"', *(f"{key}: {value}" for key, value in nth.ASK.items())]
    if extra is not None:
        lines.append(extra)
    return "---\n" + "\n".join(lines) + "\n---\n본문\n"


def extra_lines():
    """앞머리에 한 줄씩 덧붙여 보는 칸들 — 알려진 모든 칸의 알맞은 값·틀린 값, 모르는 칸, 빈 줄·주석·깨진 줄. (`result` 는 일부러 뺐다 — 이 파일 머리말 참고)"""
    good = ["urgency: 급함", "urgency: 보통", "pr: 57", "created: 2026-11-12", "no: P013", 'no: "004"', "no: M008", "work: R-160", "at: 2026-11-06 12:07", "now: 지금", "changed: 없음", "next: 다음",
            "eta: 곧", "waiting: 없음", "check: 이상 없음", "repo: a/b", "target: 대상", "pr_title: [R-1] 제목", "verify: 검증", "state: 승인 대기", "options: 가 / 나", "default: 1",
            "approve: 2"]
    bad = ["urgency: x", "pr: x", "pr: 0", "created: x", "created: 2026-13-40", "no: x", "no: P0012", "no: M50", "work: x", "at: x", "repo: x", "options: 하나", "default: 9", "approve: 0",
           "pr_title: " + "가" * 201, "now: " + "가" * 201, "title: 두 번째 제목", "kind: info", "owner: x", "Owner: x", "key=value", "# 주석", "", "   ", "이상한 줄", "now : 띄어쓴 키"]
    return [None, *good, *bad]


def parse_cases(ol):
    out = []
    kinds = [*KINDS, "bogus", None]
    for kind in kinds:
        for shape in ("old", "P", "M", "ask"):
            for extra in extra_lines():
                for number in (1, 172, 173, 266):
                    text = front(kind, shape, extra, number)
                    name = f"R-{number:03d}_sample.md"
                    result = []
                    for strict in (True, False):
                        try:
                            request = ol.parse_request(name, text, strict=strict)
                            result.append(["ok", list(request)])
                        except ol.RequestError as exc:
                            result.append(["err", exc.code])
                    out.append(result)
    return out


def verdict(ol, name, text):
    """실제 요청 파일 한 개의 판정: (엄격한 읽기의 문제 코드 또는 빈 글, 런타임 읽기 결과의 지문 8자리)."""
    try:
        ol.parse_request(name, text, strict=True)
        strict = ""
    except ol.RequestError as exc:
        strict = exc.code
    try:
        loose = ["ok", list(ol.parse_request(name, text, strict=False))]
    except ol.RequestError as exc:
        loose = ["err", exc.code]
    return strict, digest(loose)[:8]


# ---- 알림 보내기 끝에서 끝까지(run_requests) -----------------------------------------------------------------
def e2e_scenarios():
    """(이름, {요청 파일 이름: 글}, 옵션) 목록. 옵션 holders 가 있으면 알림 번호 겹침 확인(git grep)을 가짜로 흉내 낸다."""
    n = nth.notice_text
    old = oh.request_text
    scenarios = []
    for kind in KINDS:
        scenarios.append((f"old-{kind}", {nth.name_of(165): old(id="R-165", kind=kind, title="옛 요청", summary="옛 요약", urgency="급함", pr="57")}, {}))
    scenarios += [
        ("progress", {nth.name_of(170): n(number=170, no="P012", work="R-160", fields={**PROGRESS, "check": "이상 없음"}, urgency="급함", pr="57")}, {}),
        ("merge-desktop", {nth.name_of(171): n(number=171, no="M007", pr="57")}, {}),
        ("merge-blog-pr", {nth.name_of(172): n(number=172, no="M008", pr="57", fields={**MERGE, "repo": "shine88pc/chanceblog"})}, {}),
        ("ask", {nth.name_of(173): n(number=173, no="003", kind="decision", summary="무엇을 할까요", fields=nth.ASK, pr="57")}, {}),
        ("ask-run", {nth.name_of(174): n(number=174, no="004", kind="run", fields={})}, {}),
        ("mixed", {nth.name_of(165): old(id="R-165", kind="decision"), nth.name_of(166): n(number=166, no="P012"), nth.name_of(167): n(number=167, no="M007")}, {}),
        ("overflow", {nth.name_of(166 + index): n(number=166 + index, no=f"P{index + 1:03d}") for index in range(5)}, {}),
        ("fallback-missing-now", {nth.name_of(166): n(number=166, no="P012", drop=("now",))}, {}),
        ("fallback-kind-mismatch", {nth.name_of(166): n(number=166, no="P012", kind="merge")}, {}),
        ("fallback-bad-no", {nth.name_of(166): n(number=166, no="X1")}, {}),
        ("refused-pr-title", {nth.name_of(166): n(number=166, no="M001", fields={**MERGE, "pr_title": "[R-1] " + "AIza" + "x" * 35}), nth.name_of(167): n(number=167, no="M002")}, {}),
        ("duplicate-number", {nth.name_of(170, "mine"): n(number=170, no="P012")}, {"holders": [("refs/remotes/origin/ai/claude/other-1", f"{oh.DIR}{nth.name_of(169, 'theirs')}", "no: P012")]}),
        ("duplicate-number-merge", {nth.name_of(171, "mine"): n(number=171, no="M007")}, {"holders": [("refs/remotes/origin/main", f"{oh.DIR}{nth.name_of(160, 'old')}", "no: M007")]}),
        ("no-duplicate-other-type", {nth.name_of(170, "mine"): n(number=170, no="P012")}, {"holders": [("refs/remotes/origin/main", f"{oh.DIR}{nth.name_of(167, 'y')}", "no: M012")]}),
    ]
    return scenarios


def run_e2e(ol):
    """e2e_scenarios 를 가짜 git·가짜 텔레그램으로 돌려 (종료 코드, 로그 줄, 보낸 본문들)을 모은다."""
    out = []
    with tempfile.TemporaryDirectory() as tmp:
        for label, files, options in e2e_scenarios():
            holders = options.get("holders")
            if holders is None:
                git = oh.RequestGit.with_requests(files)
            else:
                git = nth.NoticeGit(tree=oh.paths(*files), files=files, refs=["refs/remotes/origin/HEAD", "refs/remotes/origin/main", "refs/remotes/origin/ai/claude/other-1"], holders=holders)
            code, lines, net, _ = oh.run_cli("requests", environ=oh.requests_env(), runner=git, root=Path(tmp))
            out.append([label, code, lines, net.bodies()])
    return out


# ---- 모아서 ----------------------------------------------------------------------------------------------
def all_digests(notify, ol):
    """표본 다섯 묶음의 지문. 상수 NOTICE_NO_REQUIRED_FROM_R 은 골든을 만들 때의 값으로 고정해 읽는다(올려도 골든이 깨지지 않게)."""
    saved = ol.NOTICE_NO_REQUIRED_FROM_R
    ol.NOTICE_NO_REQUIRED_FROM_R = CONSTANT_AT_RECORDING
    try:
        return {"notice_messages": digest(notice_message_cases(notify)), "ai_request_messages": digest(ai_request_message_cases(notify)), "buttons": digest(button_cases(ol)),
                "parse_verdicts": digest(parse_cases(ol)), "e2e": digest(run_e2e(ol))}
    finally:
        ol.NOTICE_NO_REQUIRED_FROM_R = saved


def case_counts(notify, ol):
    return {"notice_messages": len(notice_message_cases(notify)), "ai_request_messages": len(ai_request_message_cases(notify)), "buttons": len(button_cases(ol)),
            "parse_verdicts": len(parse_cases(ol)), "e2e": len(e2e_scenarios())}


def text_goldens(notify, ol):
    """눈으로 읽을 수 있는 정확한 글 — 다른 종류의 폰 글(진행 현황·병합 요청·확인 요청·옛 모양)과 단추."""
    out = {
        "progress": notify.format_notice("P012", {**PROGRESS, "check": "이상 없음"}, urgency="급함", work="R-160", pr=57),
        "progress-plain": notify.format_notice("P012", PROGRESS),
        "merge-desktop": notify.format_notice("M007", MERGE),
        "merge-blog": notify.format_notice("M008", {**MERGE, "repo": "shine88pc/chanceblog", "state": "병합 대기"}, pr=57, more=2),
        "ask-options": notify.format_notice("003", nth.ASK | {"summary": "무엇을 할까요"}, work="R-165"),
        "ask-plain": notify.format_notice("004", {"summary": "자유롭게 답해 주세요"}),
    }
    for kind in KINDS:
        out["old-" + kind] = notify.format_ai_request("R-001", kind, "제목", "요약", urgency="급함", pr=5, more=1)
    request = ol.Request("R-166", "merge", "t", "s", "보통", 5, "", "R-166_notice.md", "M007", "", (("repo", ol.BLOG_REPO),), "")
    out["buttons-merge-blog"] = json.dumps([list(item) for item in ol.request_buttons(request, "ai/claude/x", "main")], ensure_ascii=False)
    old_request = ol.Request("R-001", "decision", "t", "s", "보통", None, "", "R-001_x.md")
    out["buttons-old-decision"] = json.dumps([list(item) for item in ol.request_buttons(old_request, "ai/claude/x", "main")], ensure_ascii=False)
    return out


if __name__ == "__main__":
    from pipeline import notify as _notify
    from pipeline import operator_loop as _ol
    json.dump({"digests": all_digests(_notify, _ol), "counts": case_counts(_notify, _ol), "text_goldens": text_goldens(_notify, _ol)}, sys.stdout, ensure_ascii=False, indent=1, sort_keys=True)
