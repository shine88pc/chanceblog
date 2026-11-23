"""병합 알림 자동화 — 병합 부탁 알림(`[공통] 병합 부탁 알림 자동 보내기`)과 병합완료 확인 알림(`[공통] 병합완료 확인 알림 자동 보내기`)의 계산·문장·발송.
(표준 라이브러리만, Python 3.10 이상)

배경: 운영자는 병합 부탁이 오면 휴대폰에서 PR 을 병합하고, 병합이 끝나면 '제대로 들어갔는지' 확인 알림을 받는다. 지금은 AI 가 요청 파일(`인수인계/요청함/R-번호_이름.md`)을 push 해서 같은
알림을 보낸다. 운영자 확인 031 의 보기 2 승인(2026-11-23)으로 GitHub 쪽 워크플로 둘이 같은 알림을 자동으로 보낼 수 있게 했다 — 단 **꺼진 채로** 병합한다(켬 상태 파일 `pipeline/auto_notice.json`).
설명: docs/SECURITY_GUARDRAILS.md G-A13·G-A14, docs/ARCHITECTURE.md §4-6-4, 운영자용 안내 인수인계/운영자_요청함_사용법.md.

켬 상태 `pipeline/auto_notice.json` — `{"mode": "off"}` 한 줄이고 값은 셋뿐이다.
  off  기본. 워크플로는 곧바로 끝난다(GitHub 를 부르지 않고 텔레그램 시크릿도 읽지 않는다).
  dry  모든 계산을 하고 보낼 문장을 실행 요약(`$GITHUB_STEP_SUMMARY`)에만 남긴다. 텔레그램 호출 0, 시크릿 읽기 0.
  on   보낼 문장을 만들고 발송 단계가 텔레그램으로 보낸다.
파일이 없거나 읽지 못하거나 값이 셋 밖이거나 다른 키가 있으면 off 다(안전한 쪽). dry→on 으로 바꾸는 것은 별도 병합 부탁(T3)이다.

명령 줄: python -m pipeline.auto_notice <merge-ready | merge-confirm | send>   (값은 명령 줄이 아니라 환경변수로만 받는다)
  merge-ready    워크플로 `workflow_run`(병합 부탁 PR 자동 만들기가 끝남)의 값으로 '열린 PR 이 있고 머리 커밋이 같고 검사가 모두 초록' 일 때 병합 부탁 문장을 만든다.
  merge-confirm  워크플로 `workflow_run`(main 의 가드레일 검사가 끝남)의 값으로 `[M번호]` 병합 커밋을 확인해 정상·이상 문장을 만든다.
  send           앞 단계가 만든 문장 파일을 다시 검사한 뒤 텔레그램으로 보낸다(시크릿은 이 단계의 env 에만 있다).
  환경변수: GITHUB_REPOSITORY·RUNNER_TEMP·GITHUB_STEP_SUMMARY·GITHUB_OUTPUT(러너), GITHUB_TOKEN(읽기 권한), NOTICE_RUN_ID·NOTICE_RUN_BRANCH·NOTICE_RUN_SHA·NOTICE_RUN_EVENT·
  NOTICE_RUN_CONCLUSION·NOTICE_RUN_REPO·NOTICE_DEFAULT_BRANCH(워크플로가 `github.event.workflow_run.*` 에서 env 로 넘긴 값), TELEGRAM_BOT_TOKEN·TELEGRAM_CHAT_ID(send 만).

원칙
  1. **가지 이름·PR 제목·본문·커밋 제목은 AI 가 쓴 글이다.** 값은 env 로만 받고 여기서 모양을 거른다(가지 `ai/claude/M번호-영문`·커밋 40자리 소문자 16진수·제목 `[M번호] ` 머리·200자·제어 문자·`@`·주소·비밀 모양).
     걸리면 보내지 않고 요약에 고정 문장만 남긴다. 로그·요약에는 제목·본문 원문을 찍지 않는다(dry 의 보낼 문장은 거른 뒤의 값이라 예외).
  2. **가지(PR 머리)의 코드는 내려받지도 실행하지도 않는다.** 이 모듈은 기본 가지(main)의 것이다. GitHub 는 읽기(GET)만, 기존 클라이언트(operator_loop.GitHub — 외부 접속 등록은 거기 한 곳)로 부른다.
  3. 텔레그램은 pipeline/notify.py 의 규칙을 그대로 쓴다(토큰 비노출·재시도·통 수 상한). 새 HTTP 코드를 만들지 않는다. 본문은 평문이다.
  4. 알림은 보조다. 읽기 실패·모양 불일치·전송 실패는 경고 한 줄 뒤 종료 코드 0 이다(알림이 안 가는 쪽이 이상한 알림이 가는 쪽보다 낫다 — AI 의 요청 파일 알림이 아직 병행한다).
"""
import argparse
import json
import os
import re
import sys
import time
import unicodedata
from collections import namedtuple
from pathlib import Path

from pipeline import notify, operator_loop
from pipeline.console import safe_output
from pipeline.llm import mask
from pipeline.secret_patterns import find_secrets

ROOT = Path(__file__).resolve().parent.parent
STATE_FILE = ROOT / "pipeline" / "auto_notice.json"
STATE_MAX_BYTES = 1024

MODE_OFF, MODE_DRY, MODE_ON = "off", "dry", "on"
MODES = (MODE_OFF, MODE_DRY, MODE_ON)

READY, CONFIRM, SEND = "merge-ready", "merge-confirm", "send"
MESSAGE_FILE = "auto-notice-message.txt"          # 판정 단계가 `$RUNNER_TEMP` 에 쓰고 발송 단계가 읽는다
OUTPUT_KEY, OUTPUT_YES = "send", "yes"            # 판정 단계가 `$GITHUB_OUTPUT` 에 쓰는 것은 이 고정 한 줄뿐이다

MESSAGE_LIMIT = 800                               # 한 통의 글자 수 상한(텔레그램 한도 4,096 에 한참 못 미친다 — 휴대폰에서 한눈에 읽는 길이)
READY_TITLE_LIMIT = 80                            # 병합 부탁 제목 줄의 PR 제목 부분(`[M번호] ` 뺀 것)
POINT_LINES = 5                                   # 병합 부탁 본문의 요점 줄 수 상한
POINT_LIMIT = 120                                 # 요점 줄 하나의 글자 수 상한
POINT_SCAN_LINES = 400                            # 요점 줄을 고르려고 본문에서 읽는 줄 수의 상한 — 앞쪽에서 고르므로 이만 읽으면 되고, 아주 긴 본문이 일을 늘리지 못한다
PR_TITLE_LIMIT = 200                              # PR 제목 전체 상한(auto-pr.yml 과 같다)
REASON_LIMIT = 100                                # 병합완료 확인 이상의 사유 한 줄
PER_PAGE = 100
FILE_PAGES_MAX = 3                                # PR 파일 목록은 100개씩 세 쪽(300개)까지 — 그 이상이면 파일 비교를 하지 않는다
FILES_CAP = 300
CHECK_RETRIES = 3                                 # 끝나지 않은 검사가 있으면 이만큼 더 확인한다
CHECK_WAIT = 20                                   # 확인 사이에 쉬는 초 — 전부 합쳐 1분

GUARDRAILS_PATH = ".github/workflows/guardrails.yml"      # 병합 가지의 검사. 실행 기록의 path 는 `…yml@refs/heads/…` 꼴이라 `@` 앞만 본다
READY_HEADING = "[공통] 병합 부탁 알림 자동 보내기"
CONFIRM_HEADING = "[공통] 병합완료 확인 알림 자동 보내기"

REPO_RE = re.compile(r"[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}")
BRANCH_RE = re.compile(r"ai/claude/(M[0-9]{3,4})-[A-Za-z0-9._-]{1,80}")
DEFAULT_BRANCH_RE = re.compile(r"[A-Za-z0-9._/-]{1,100}")
SHA_RE = re.compile(r"[0-9a-f]{40}")
RUN_ID_RE = re.compile(r"[1-9][0-9]{0,17}")
TITLE_HEAD_RE = re.compile(r"\[(M[0-9]{3,4})\] ")          # 제목 맨 앞 `[M번호] ` — match 로 앞에서만 본다
CONCLUSION_WORDS = frozenset({"success", "failure", "cancelled", "skipped", "timed_out", "action_required", "neutral", "stale", "startup_failure"})

# 글자 규칙(알림 표준 TG-STD): 링크 주소·물결표·`@멘션` 이 없다. 아래 정규식은 검사용이고 글을 바꾸지 않는다(물결표만 줄표로 바꿔 싣는다).
_WEB_TLDS = ("com", "net", "org", "io", "dev", "app", "co", "kr", "me", "ly", "gg", "xyz", "info", "biz", "edu", "gov", "ai", "to", "cc", "tv", "us", "uk", "de", "jp", "cn", "ru", "fm", "site",
             "online", "top", "shop", "link", "click", "page", "cloud", "tech", "store")
_ADDRESS_RE = re.compile(
    r"[A-Za-z][A-Za-z0-9+.-]*://"                                           # 주소 머리(웹·텔레그램·ftp …)
    r"|(?<![A-Za-z0-9])www\."
    r"|(?<![A-Za-z0-9])(?:mailto|tel|tg|sms|file|data|javascript|ftp|ssh|git):(?=\S)"      # 공백 없이 이어지는 것만(영문 '파일: x' 같은 머리글은 주소가 아니다)
    r"|(?<![0-9])[0-9]{1,3}(?:\.[0-9]{1,3}){3}(?![0-9])"                    # IPv4
    r"|(?<![A-Za-z0-9_-])[A-Za-z0-9][A-Za-z0-9-]*(?:\.[A-Za-z0-9-]+)*\.(?:" + "|".join(_WEB_TLDS) + r")(?![A-Za-z0-9-])",
    re.IGNORECASE)
_TILDE_CHARS = {ord(chr(0x7E)): chr(0x2013), 0xFF5E: chr(0x2013), 0x301C: chr(0x2013), 0x223C: chr(0x2013)}      # 물결표 넷(ASCII·전각·파동 줄표·틸드 연산자) → 줄표
_TRAILER_RE = re.compile(r"(?i)^(?:co-authored-by|signed-off-by|reviewed-by|acked-by|tested-by|reported-by|ad-surface-approved|change-id)\s*:")
_LIST_MARK_RE = re.compile(r"^(?:[-*+•]\s+|[0-9]{1,3}[.)]\s+)+")
_QUOTE_MARK_RE = re.compile(r"^>+\s*")

TITLE_SEPARATOR = " — "
READY_LABEL = "병합 부탁"
CHECK_LINE = "검사: 초록"
CONFIRM_OK, CONFIRM_BAD = "정상", "이상"

# 보내지 않은 이유(고정 문장 — 요약·로그에는 이것과 번호·정수만 쓴다). 두 번째 값은 경고(::warning::)로 드러낼 만한 이상 상황인가.
REASONS = {
    "input_shape": ("입력 값(저장소·가지·커밋·실행 번호·결론)의 모양이 예상과 달라 알리지 않았습니다", True),
    "not_push": ("push 로 시작한 실행이 아니라 알리지 않았습니다", False),
    "fork": ("이 저장소의 실행이 아니라(포크) 알리지 않았습니다", False),
    "run_not_success": ("앞선 자동 PR 실행이 성공으로 끝나지 않아 알리지 않았습니다", False),
    "run_cancelled": ("검사 실행이 취소되거나 건너뛰어져 판정을 미룹니다(다음 검사가 이어받습니다)", False),
    "api_error": ("GitHub 응답을 읽지 못해 알리지 않았습니다", True),
    "api_shape": ("GitHub 응답의 모양이 예상과 달라 알리지 않았습니다", True),
    "no_pr": ("이 가지의 열린 PR 이 없어 알리지 않았습니다", False),
    "many_pr": ("이 가지의 열린 PR 이 둘 이상이라 알리지 않았습니다", False),
    "pr_mismatch": ("PR 의 머리 커밋·작성 가지·대상 가지가 이 실행과 달라 알리지 않았습니다", False),
    "pr_draft": ("초안 PR 이라 알리지 않았습니다", False),
    "title_shape": ("제목이 [M번호] 로 시작하지 않거나 가지의 번호와 달라 알리지 않았습니다", False),
    "title_problem": ("제목에 보낼 수 없는 글자(제어 문자·주소·멘션·비밀 모양)가 있거나 너무 길어 알리지 않았습니다", True),
    "checks_missing": ("가드레일 검사 실행을 찾지 못해 알리지 않았습니다", False),
    "checks_pending": ("아직 끝나지 않은 검사가 있어 알리지 않았습니다", False),
    "checks_failed": ("초록이 아닌 검사가 있어 알리지 않았습니다", False),
    "message_problem": ("만든 문장이 보내기 규칙에 맞지 않아 알리지 않았습니다", True),
    "not_merge_commit": ("제목이 [M번호] 로 시작하는 병합 커밋이 아니라 알리지 않았습니다", False),
    "pr_count": ("이 커밋에 연결된 병합된 PR 이 하나가 아니라 알리지 않았습니다", False),
    "too_large": ("변경 파일이 너무 많아 비교하지 못해 알리지 않았습니다", False),
}
MODE_OFF_LINE = "병합 알림 자동: 켬 상태가 꺼짐(off)이라 아무것도 하지 않습니다"
USAGE_ERROR_LINE = "사용법 오류: 이 명령은 merge-ready·merge-confirm·send 만 받습니다(값은 명령 줄이 아니라 환경변수로만 받습니다)"
UNEXPECTED_LINE = "병합 알림 자동: 예기치 않은 오류({name}) — 병합·검사·알림 흐름에는 영향이 없습니다"
UNEXPECTED_WARNING = "::warning::병합 알림 자동 처리 중 예기치 않은 오류가 났습니다. 병합·검사에는 영향이 없습니다(코드 버그일 수 있어 AI 에게 알려 주세요)."


class Skip(Exception):
    """알리지 않고 끝내는 길. code 는 REASONS 의 키 — 문장에는 외부 값이 없다."""

    def __init__(self, code):
        super().__init__(code)
        self.code = code


Verdict = namedtuple("Verdict", "text notes")        # text: 보낼 문장(비었으면 없음) / notes: 요약에 남길 고정 문장 목록
Inputs = namedtuple("Inputs", "repo run_id branch sha event conclusion run_repo default_branch")


# ---- 켬 상태 -------------------------------------------------------------------------------------------
def _no_duplicate_keys(pairs):
    keys = [key for key, _value in pairs]
    if len(set(keys)) != len(keys):
        raise ValueError("duplicate key")
    return dict(pairs)


def read_mode(path=None):
    """켬 상태 파일을 읽어 `off`·`dry`·`on` 중 하나를 돌려준다. 파일이 없거나 크거나 JSON 이 아니거나 키가 `mode` 하나가 아니거나 값이 셋 밖(대소문자·공백 포함)이면 `off`(안전한 쪽)."""
    target = STATE_FILE if path is None else Path(path)
    try:
        if target.stat().st_size > STATE_MAX_BYTES:
            return MODE_OFF
        data = json.loads(target.read_text(encoding="utf-8"), object_pairs_hook=_no_duplicate_keys)
    except (OSError, ValueError, RecursionError):
        return MODE_OFF
    if isinstance(data, dict) and set(data) == {"mode"} and isinstance(data["mode"], str) and data["mode"] in MODES:
        return data["mode"]
    return MODE_OFF


# ---- 글 거르기 -----------------------------------------------------------------------------------------
def _folded(text):
    """검사용 사본(NFKC — 전각 골뱅이·전각 주소 머리·전각 물결표도 ASCII 꼴로). 글을 바꾸지 않고 검사에만 쓴다."""
    return unicodedata.normalize("NFKC", text)


def line_problem(text):
    """한 줄을 알림에 글자 그대로 싣을 수 있는가 — 비었으면 빈 문자열, 아니면 이유 코드: empty·control(제어·서식·보이지 않는 글자)·secret(비밀 모양)·mention(`@`)·address(주소 모양)·tilde(물결표).
    제목·요점 줄·전체 문장이 같은 규칙을 쓴다. 줄 바꿈이 든 글은 control 이다(줄마다 따로 부른다)."""
    value = text if isinstance(text, str) else ""
    problem = notify.pr_title_problem(value)
    if problem in ("empty", "control"):
        return problem
    if problem or find_secrets(value) or mask(value) != value:
        return "secret"
    folded = _folded(value)
    if "@" in value or "@" in folded:
        return "mention"
    if _ADDRESS_RE.search(value) or _ADDRESS_RE.search(folded):
        return "address"
    if chr(0x7E) in value or chr(0x7E) in folded:
        return "tilde"
    return ""


def clean_inline(text):
    """AI 가 쓴 한 줄을 알림용으로 다듬는다: 마크다운 강조·백틱을 걷고, 물결표는 줄표로, 연속 공백은 하나로. 비밀·주소·멘션은 걸러내지 않는다(line_problem 이 판정한다)."""
    value = (text if isinstance(text, str) else "").translate(_TILDE_CHARS)
    value = value.replace("**", "").replace("`", "")
    return " ".join(value.split())


def shorten(text, limit):
    """limit 글자를 넘으면 앞 limit-1 글자 + `…` (총 limit 글자)."""
    return text if len(text) <= limit else text[:limit - 1].rstrip() + chr(0x2026)


def point_lines(body, limit_lines=POINT_LINES, limit_chars=POINT_LIMIT):
    """PR 본문(커밋 본문)의 앞쪽 요점 줄 — 빈 줄·제목 줄(`#`)·구분선·'Co-authored-by:' 같은 꼬리표를 건너뛰고, 글머리 기호·강조를 걷고, 줄마다 limit_chars 로 줄인다.
    보낼 수 없는 줄(제어·비밀·멘션·주소)은 그 줄만 버린다(본문 전체를 버리지 않는다). 최대 limit_lines 줄이고, 본문은 앞 POINT_SCAN_LINES(400)줄만 읽는다."""
    text = body if isinstance(body, str) else ""
    points = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")[:POINT_SCAN_LINES]:
        stripped = raw.strip()
        if not stripped or stripped.startswith("#") or _TRAILER_RE.match(stripped):
            continue
        line = clean_inline(_LIST_MARK_RE.sub("", _QUOTE_MARK_RE.sub("", stripped)))
        if not any(char.isalnum() for char in line):
            continue
        line = shorten(line, limit_chars)
        if line_problem(line):
            continue
        points.append(line)
        if len(points) == limit_lines:
            break
    return points


# ---- 문장 만들기 ----------------------------------------------------------------------------------------
def ready_tail(number):
    return f"병합은 Pull requests 에서 제목 맨 앞이 [{number}] 인 PR 하나만 하세요. 알림이 없는 열린 PR 은 아직 병합하지 마세요."


def _ready_text(head, points, number):
    sections = [head]
    if points:
        sections.append("\n".join("- " + point for point in points))
    sections.extend([CHECK_LINE, ready_tail(number)])
    return "\n\n".join(sections)


def compose_ready(number, title, body):
    """병합 부탁 문장: 제목 줄 `[M번호] 병합 부탁 — <PR 제목에서 `[M번호] ` 뺀 것(80자)>`, 요점 줄(최대 5줄·줄당 120자 — 전체 800자 안에서 앞쪽부터), `검사: 초록`, 고정 꼬리.
    번호는 알림 번호 모양(notify.notice_type 이 병합 요청)이고 title 은 그 번호로 시작해야 한다 — 아니면 Skip. 보낼 수 없는 글자가 제목에 있으면 Skip(title_problem)."""
    if notify.notice_type(number) != notify.NOTICE_MERGE:
        raise Skip("title_shape")
    found = TITLE_HEAD_RE.match(title if isinstance(title, str) else "")
    if found is None or found.group(1) != number:
        raise Skip("title_shape")
    if len(title) > PR_TITLE_LIMIT:
        raise Skip("title_problem")
    rest = clean_inline(title[found.end():])
    if line_problem(rest) or line_problem(title.translate(_TILDE_CHARS)):
        raise Skip("title_problem")
    head = f"[{number}] {READY_LABEL}{TITLE_SEPARATOR}{shorten(rest, READY_TITLE_LIMIT)}"
    chosen = []
    for point in point_lines(body):
        if len(_ready_text(head, chosen + [point], number)) > MESSAGE_LIMIT:
            break
        chosen.append(point)
    return _ready_text(head, chosen, number)


def compose_confirm(number, problems, extra=""):
    """병합완료 확인 문장: 정상이면 제목 한 줄(`[M번호] 병합완료 확인 - 정상`, 참고할 일이 있으면 한 줄 더), 이상이면 제목 + 사유 한 줄(첫 문제 + 나머지 개수, 100자 안).
    problems 는 코드가 정한 고정 문장 목록이다."""
    result = CONFIRM_BAD if problems else CONFIRM_OK
    lines = [notify.merged_title(number, result)]
    if problems:
        reason = problems[0] + (f" (외 {len(problems) - 1}건)" if len(problems) > 1 else "")
        lines.append(shorten(reason, REASON_LIMIT))
    elif extra:
        lines.append(shorten(extra, REASON_LIMIT))
    return "\n".join(lines)


def message_problem(text):
    """보낼 문장이 규칙에 맞는가 — 맞으면 빈 문자열, 아니면 이유 코드. 판정 단계가 만든 직후와 발송 단계가 보내기 직전에 같은 함수를 부른다.
    검사: 비지 않음·800자 이하·모든 줄이 line_problem 통과(빈 줄 제외)·첫 줄이 정해진 두 모양 중 하나(번호는 병합 요청 번호)이고 그 모양의 나머지 줄 구조(병합 부탁은 `검사: 초록` 한 줄과 고정 꼬리가 맨 끝,
    병합완료 확인은 최대 한 줄 더)가 맞음."""
    if not isinstance(text, str) or not text.strip():
        return "empty"
    if len(text) > MESSAGE_LIMIT:
        return "too_long"
    lines = text.split("\n")
    for line in lines:
        if line and line_problem(line):
            return "line"
    first = lines[0]
    ready = re.fullmatch(r"\[(M[0-9]{3,4})\] " + READY_LABEL + TITLE_SEPARATOR + r".+", first)
    confirm = re.fullmatch(r"\[(M[0-9]{3,4})\] 병합완료 확인 - (?:정상|이상)", first)
    found = ready or confirm
    if found is None or notify.notice_type(found.group(1)) != notify.NOTICE_MERGE:
        return "shape"
    number = found.group(1)
    if ready:
        # 구조: 제목 / 빈 줄 / (요점 줄들) / 빈 줄 / 검사 줄 / 빈 줄 / 고정 꼬리 — 요점이 없으면 앞의 빈 줄이 하나뿐이다
        if len(lines) < 5 or lines[1] != "" or lines[-4] != "" or lines[-3] != CHECK_LINE or lines[-2] != "" or lines[-1] != ready_tail(number):
            return "shape"
        points = lines[2:-4]
        if len(points) > POINT_LINES or not all(line.startswith("- ") and 2 < len(line) <= POINT_LIMIT + 2 for line in points):
            return "shape"
        return ""
    if len(lines) > 2 or (len(lines) == 2 and not lines[1]):
        return "shape"
    if first.endswith(CONFIRM_BAD) and len(lines) != 2:
        return "shape"
    return ""


# ---- 입력(env) ------------------------------------------------------------------------------------------
def read_inputs(environ, kind):
    """워크플로가 env 로 넘긴 값을 모양을 거르며 읽는다. 어긋나면 Skip. 병합 부탁은 가지가 `ai/claude/M번호-…` 여야 하고, 병합완료 확인은 가지가 기본 가지여야 한다.
    실행의 저장소(NOTICE_RUN_REPO)가 이 저장소와 같고 이벤트가 push 여야 한다(포크·다른 이벤트의 실행은 알리지 않는다)."""
    def get(name):
        return str(environ.get(name) or "")

    repo, default_branch = get("GITHUB_REPOSITORY"), get("NOTICE_DEFAULT_BRANCH")
    branch, sha, run_id = get("NOTICE_RUN_BRANCH"), get("NOTICE_RUN_SHA"), get("NOTICE_RUN_ID")
    conclusion, run_repo, event = get("NOTICE_RUN_CONCLUSION"), get("NOTICE_RUN_REPO"), get("NOTICE_RUN_EVENT")
    if not (REPO_RE.fullmatch(repo) and DEFAULT_BRANCH_RE.fullmatch(default_branch) and SHA_RE.fullmatch(sha) and set(sha) != {"0"}
            and RUN_ID_RE.fullmatch(run_id) and conclusion in CONCLUSION_WORDS):
        raise Skip("input_shape")
    if kind == READY:
        if BRANCH_RE.fullmatch(branch) is None:
            raise Skip("input_shape")
    elif branch != default_branch:
        raise Skip("input_shape")
    if event != "push":
        raise Skip("not_push")
    if run_repo.lower() != repo.lower():
        raise Skip("fork")
    return Inputs(repo, int(run_id), branch, sha, event, conclusion, run_repo, default_branch)


# ---- GitHub 읽기(GET 만) ---------------------------------------------------------------------------------
class Reader:
    """GitHub REST 읽기 전용 껍질 — `api.request("GET", …)` 한 가지만 부른다(쓰기 메서드는 이 모듈에 없다). api 는 operator_loop.GitHub 모양(request(method, path, params=…))이고
    시험은 가짜로 바꿔 끼운다. 실패는 Skip("api_error")."""

    def __init__(self, api):
        self._api = api

    def get(self, path, **params):
        try:
            return self._api.request("GET", path, params=params or None)
        except operator_loop.GitHubError:
            raise Skip("api_error") from None


def _obj(value):
    return value if isinstance(value, dict) else None


def _list(value):
    return value if isinstance(value, list) else None


def _text(value):
    return value if isinstance(value, str) else ""


def _int(value):
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _need(value):
    """GitHub 응답에서 읽은 값이 None(모양 불일치)이면 Skip(api_shape)."""
    if value is None:
        raise Skip("api_shape")
    return value


def runs_state(runs, run_id):
    """같은 가지·같은 커밋의 push 실행 목록이 '모두 끝나 초록' 인지: ok(모두 성공이고 가드레일 실행이 있음)·pending(끝나지 않은 것이 있음)·failed(끝났는데 성공이 아닌 것이 있음 —
    skipped·neutral·cancelled 도 초록이 아니다)·missing(가드레일 실행이 없음). 이 실행을 일으킨 자동 PR 실행(run_id)은 이벤트가 이미 결론을 알려 주므로 뺀다(막 끝난 실행이 목록에 아직
    진행 중으로 보이는 틈을 피한다). 항목 모양이 틀리면 Skip(api_shape)."""
    pending = failed = guardrails = False
    for item in runs:
        run = _need(_obj(item))
        if run.get("id") == run_id:
            continue
        if run.get("status") != "completed":
            pending = True
        elif run.get("conclusion") != "success":
            failed = True
        elif _text(run.get("path")).split("@", 1)[0] == GUARDRAILS_PATH:
            guardrails = True
    if failed:
        return "failed"
    if pending:
        return "pending"
    return "ok" if guardrails else "missing"


def evaluate_ready(inputs, reader, sleep=time.sleep):
    """병합 부탁: 이 가지의 열린 PR 이 하나이고(머리 커밋 = 이 실행의 커밋·작성 가지·대상 = 기본 가지·같은 저장소·초안 아님·제목이 가지 번호로 시작) 그 커밋의 push 검사가 모두 끝나 초록일 때만
    문장을 만든다. 아니면 Skip. 끝나지 않은 검사만 남았으면 CHECK_WAIT 초 간격으로 CHECK_RETRIES 번 더 본다."""
    if inputs.conclusion != "success":
        raise Skip("run_not_success")
    number = BRANCH_RE.fullmatch(inputs.branch).group(1)
    owner = inputs.repo.split("/", 1)[0]
    prs = _need(_list(reader.get("/pulls", state="open", head=f"{owner}:{inputs.branch}", base=inputs.default_branch, per_page=5)))
    if not prs:
        raise Skip("no_pr")
    if len(prs) > 1:
        raise Skip("many_pr")
    pr = _need(_obj(prs[0]))
    head, base = _need(_obj(pr.get("head"))), _need(_obj(pr.get("base")))
    head_repo = _obj(head.get("repo")) or {}
    count = _need(_int(pr.get("number")))
    if count < 1:
        raise Skip("api_shape")
    if pr.get("state") != "open" or head.get("sha") != inputs.sha or head.get("ref") != inputs.branch or base.get("ref") != inputs.default_branch \
            or _text(head_repo.get("full_name")).lower() != inputs.repo.lower():
        raise Skip("pr_mismatch")
    if pr.get("draft") is True:
        raise Skip("pr_draft")
    text = compose_ready(number, _text(pr.get("title")), pr.get("body"))
    for attempt in range(CHECK_RETRIES + 1):
        listing = _need(_obj(reader.get("/actions/runs", branch=inputs.branch, head_sha=inputs.sha, event="push", per_page=PER_PAGE)))
        state = runs_state(_need(_list(listing.get("workflow_runs"))), inputs.run_id)
        if state != "pending" or attempt == CHECK_RETRIES:
            break
        sleep(CHECK_WAIT)
    if state != "ok":
        raise Skip({"pending": "checks_pending", "failed": "checks_failed", "missing": "checks_missing"}[state])
    return Verdict(text, [f"열린 PR #{count} 하나이고 머리 커밋이 이 실행의 커밋과 같음", "이 커밋의 push 검사가 모두 끝나 초록(가드레일 포함)"])


def _tree(commit, shape_code="api_shape"):
    """`GET /commits/{sha}` 응답의 트리 해시(40자리 소문자 16진수) — 모양이 틀리면 Skip."""
    inner = _need(_obj(_need(_obj(commit)).get("commit")))
    tree = _text(_need(_obj(inner.get("tree"))).get("sha"))
    if SHA_RE.fullmatch(tree) is None:
        raise Skip(shape_code)
    return tree


def _names(entries):
    names = set()
    for entry in _need(_list(entries)):
        name = _text(_need(_obj(entry)).get("filename"))
        if not name:
            raise Skip("api_shape")
        names.add(name)
    return names


def _confirm_words(conclusion):
    return conclusion if conclusion in CONCLUSION_WORDS else "알 수 없음"


def evaluate_confirm(inputs, reader):
    """병합완료 확인: main 의 가드레일 검사가 끝난 커밋의 제목이 `[M번호] ` 로 시작하고 그 커밋에 연결된 병합된 PR 이 정확히 하나일 때만 문장을 만든다(아니면 Skip).
    확인 ① 병합 커밋의 부모 수(squash 는 1, 병합 커밋 방식 2 도 허용 — 2 면 문장에 한 줄 적음) ② 병합 커밋의 트리가 PR 머리 커밋의 트리와 같은지 — 같으면 '트리 일치', 다르면(main 이 앞서가면 생김)
    트리 비교를 빼고 변경 파일 수·이름 집합이 PR 과 같은지로 대신 확인 ③ 이 main 커밋의 가드레일 결론이 success. 문제가 없으면 정상, 있으면 이상 + 사유 한 줄. 검사가 취소·건너뜀이면 판정을 미룬다."""
    if inputs.conclusion in ("cancelled", "skipped"):
        raise Skip("run_cancelled")
    commit = _need(_obj(reader.get(f"/commits/{inputs.sha}")))
    inner = _need(_obj(commit.get("commit")))
    first = _text(inner.get("message")).split("\n", 1)[0].rstrip("\r")
    found = TITLE_HEAD_RE.match(first)
    if found is None:
        raise Skip("not_merge_commit")
    number = found.group(1)
    if notify.notice_type(number) != notify.NOTICE_MERGE:
        raise Skip("title_shape")
    parents = _need(_list(commit.get("parents")))
    pulls = _need(_list(reader.get(f"/commits/{inputs.sha}/pulls", per_page=10)))
    merged = [item for item in pulls if isinstance(item, dict) and item.get("merged_at") and item.get("merge_commit_sha") == inputs.sha]
    if len(merged) != 1:
        raise Skip("pr_count")
    count = _need(_int(merged[0].get("number")))
    if count < 1:
        raise Skip("api_shape")
    detail = _need(_obj(reader.get(f"/pulls/{count}")))
    problems, notes, extra = [], [f"병합된 PR #{count} 하나가 이 커밋에 연결됨"], ""
    if inputs.conclusion != "success":
        problems.append(f"main 검사(가드레일)가 성공으로 끝나지 않았습니다(결론: {_confirm_words(inputs.conclusion)})")
    notes.append("main 가드레일 결론: " + _confirm_words(inputs.conclusion))
    if len(parents) not in (1, 2):
        problems.append(f"병합 커밋의 부모가 {len(parents)}개입니다(1개 또는 2개여야 합니다)")
    else:
        notes.append(f"병합 커밋의 부모 {len(parents)}개" + ("(squash)" if len(parents) == 1 else "(병합 커밋 방식)"))
        extra = "참고: 병합 커밋의 부모가 2개입니다(병합 커밋 방식)" if len(parents) == 2 else ""
    if detail.get("merged") is not True or detail.get("merge_commit_sha") != inputs.sha:
        problems.append("PR 의 병합 커밋이 이 커밋과 다릅니다")
    if _text(_need(_obj(detail.get("base"))).get("ref")) != inputs.default_branch:
        problems.append("병합된 PR 의 대상 가지가 기본 가지가 아닙니다")
    pr_found = TITLE_HEAD_RE.match(_text(detail.get("title")))
    if pr_found is None or pr_found.group(1) != number:
        problems.append("커밋 제목과 PR 제목의 번호가 다릅니다")
    head_sha = _text(_need(_obj(detail.get("head"))).get("sha"))
    if SHA_RE.fullmatch(head_sha) is None:
        raise Skip("api_shape")
    merge_tree = _tree(commit)
    head_tree = _tree(reader.get(f"/commits/{head_sha}"))
    if merge_tree == head_tree:
        notes.append("트리 일치(병합 커밋과 PR 머리 커밋의 트리가 같음)")
    else:
        changed = _need(_int(detail.get("changed_files")))
        if changed < 1 or changed > FILES_CAP:
            raise Skip("too_large")
        merged_names = _names(commit.get("files"))
        pr_names = set()
        for page in range(1, FILE_PAGES_MAX + 1):
            entries = _need(_list(reader.get(f"/pulls/{count}/files", per_page=PER_PAGE, page=page)))
            pr_names |= _names(entries)
            if len(entries) < PER_PAGE:
                break
        if len(pr_names) != changed:
            raise Skip("api_shape")                    # PR 이 알려 준 변경 파일 수와 목록이 어긋나면 비교할 수 없다
        if pr_names != merged_names:
            problems.append(f"변경 파일이 PR 과 다릅니다(PR {len(pr_names)}개, 병합 {len(merged_names)}개)")
        else:
            notes.append(f"트리 비교 생략(main 이 앞섬) — 변경 파일 {len(pr_names)}개의 이름 집합이 PR 과 같음")
    return Verdict(compose_confirm(number, problems, extra), notes)


# ---- 실행 요약·출력·문장 파일 -----------------------------------------------------------------------------
def append_lines(path, lines):
    """파일 끝에 줄들을 덧붙인다(요약·출력 파일). 경로가 비었거나 쓸 수 없으면 조용히 건너뛴다 — 알림은 보조다."""
    if not path:
        return
    try:
        with open(path, "a", encoding="utf-8", newline="\n") as handle:
            handle.write("\n".join(lines) + "\n")
    except OSError:
        pass


def message_path(environ):
    """문장 파일의 경로(`$RUNNER_TEMP/auto-notice-message.txt`) — RUNNER_TEMP 가 없으면 None(파일을 쓰지도 읽지도 않는다)."""
    temp = str(environ.get("RUNNER_TEMP") or "")
    return Path(temp) / MESSAGE_FILE if temp else None


def clear_message(environ):
    """지난 실행·앞 단계의 낡은 문장 파일이 남아 발송되지 않게 판정 단계가 먼저 지운다."""
    target = message_path(environ)
    try:
        if target is not None:
            target.unlink()
    except OSError:
        pass


def fence(text):
    """요약에 넣을 코드 블록. 글에서 백틱을 이미 걷었으므로(clean_inline) 석 줄 울타리가 깨지지 않는다."""
    return ["```text", *text.split("\n"), "```"]


def _build_reader(environ):
    token = str(environ.get("GITHUB_TOKEN") or "").strip()
    if not token:
        raise Skip("api_error")
    return Reader(operator_loop.GitHub(str(environ.get("GITHUB_REPOSITORY") or ""), token))


def run_decide(kind, environ, out, reader=None, sleep=time.sleep, state_file=None):
    """판정 단계(시크릿 없음): 켬 상태가 off 면 곧바로 끝, 아니면 값을 거르고 GitHub 를 읽어 문장을 만든다. dry 는 문장을 요약에만, on 은 문장 파일과 출력 `send=yes` 를 남긴다."""
    mode = read_mode(state_file)
    heading = READY_HEADING if kind == READY else CONFIRM_HEADING
    summary_path = environ.get("GITHUB_STEP_SUMMARY")
    lines = [f"### {heading}", f"- 켬 상태: {mode}"]
    if mode == MODE_OFF:
        out(MODE_OFF_LINE)
        append_lines(summary_path, lines + ["- 결과: 꺼져 있어 아무것도 하지 않았습니다"])
        return 0
    clear_message(environ)
    try:
        inputs = read_inputs(environ, kind)
        lines.append(f"- 번호: {BRANCH_RE.fullmatch(inputs.branch).group(1)}" if kind == READY else f"- 대상: {inputs.default_branch} 의 검사 결과")
        reader = reader or _build_reader(environ)
        verdict = evaluate_ready(inputs, reader, sleep) if kind == READY else evaluate_confirm(inputs, reader)
        if message_problem(verdict.text):
            raise Skip("message_problem")
    except Skip as skip:
        sentence, loud = REASONS[skip.code]
        out(f"병합 알림 자동: {sentence}")
        if loud:
            out(f"::warning::병합 알림 자동: {sentence}.")
        append_lines(summary_path, lines + [f"- 결과: {sentence}"])
        return 0
    lines.extend(f"- 확인: {note}" for note in verdict.notes)
    if mode == MODE_DRY:
        out("병합 알림 자동: dry — 보낼 문장을 만들었고 실행 요약에만 남깁니다(텔레그램은 부르지 않습니다)")
        append_lines(summary_path, lines + ["- 결과: 보낼 문장을 만들었습니다(dry 라 보내지 않음). 보낼 문장(거른 뒤의 값):", "", *fence(verdict.text)])
        return 0
    target = message_path(environ)
    try:
        if target is None:
            raise OSError("RUNNER_TEMP")
        target.write_text(verdict.text, encoding="utf-8", newline="\n")
    except OSError:
        out("병합 알림 자동: 문장을 파일로 남기지 못해 보내지 않습니다")
        out("::warning::병합 알림 자동: 문장 파일을 쓰지 못해 알리지 않았습니다.")
        append_lines(summary_path, lines + ["- 결과: 문장 파일을 쓰지 못해 보내지 않았습니다"])
        return 0
    append_lines(environ.get("GITHUB_OUTPUT"), [f"{OUTPUT_KEY}={OUTPUT_YES}"])
    out("병합 알림 자동: 보낼 문장을 만들었습니다(발송 단계가 보냅니다)")
    append_lines(summary_path, lines + ["- 결과: 보낼 문장을 만들었습니다(on — 발송 단계가 텔레그램으로 보냅니다)"])
    return 0


def run_send(environ, out, notifier=None, state_file=None):
    """발송 단계(텔레그램 시크릿은 이 단계의 env 에만): 켬 상태가 on 일 때만, 앞 단계의 문장 파일을 message_problem 으로 다시 검사한 뒤 평문으로 한 통 보낸다. 실패는 경고뿐(종료 0)."""
    summary_path = environ.get("GITHUB_STEP_SUMMARY")
    if read_mode(state_file) != MODE_ON:
        out("병합 알림 자동: 켬 상태가 on 이 아니라 보내지 않습니다")
        append_lines(summary_path, ["- 발송: 켬 상태가 on 이 아니라 보내지 않았습니다"])
        return 0
    target = message_path(environ)
    try:
        if target is None or target.stat().st_size > MESSAGE_LIMIT * 4:
            raise OSError("message file")
        text = target.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        out("병합 알림 자동: 보낼 문장 파일을 읽지 못해 보내지 않습니다")
        out("::warning::병합 알림 자동: 문장 파일을 읽지 못해 알리지 않았습니다.")
        append_lines(summary_path, ["- 발송: 문장 파일을 읽지 못해 보내지 않았습니다"])
        return 0
    if message_problem(text):
        out("병합 알림 자동: 문장이 보내기 규칙에 맞지 않아 보내지 않습니다")
        out("::warning::병합 알림 자동: 문장이 보내기 규칙에 맞지 않아 알리지 않았습니다.")
        append_lines(summary_path, ["- 발송: 문장이 보내기 규칙에 맞지 않아 보내지 않았습니다"])
        return 0
    notifier = notifier or notify.Notifier(environ)
    result = notifier.send_message(text)
    if result.sent:
        out("병합 알림 자동: 텔레그램으로 보냈습니다")
        append_lines(summary_path, ["- 발송: 텔레그램으로 보냈습니다"])
        return 0
    detail = notify.describe(result)
    out(f"병합 알림 자동: 텔레그램으로 보내지 못했습니다 — {detail}")
    out("::warning::병합 알림 자동: 텔레그램 전송에 실패했습니다. 이유는 바로 앞 로그 줄에 있습니다(병합·검사에는 영향이 없습니다).")
    append_lines(summary_path, ["- 발송: 텔레그램으로 보내지 못했습니다(이유는 로그 참고)"])
    return 0


# ---- 명령 줄 -------------------------------------------------------------------------------------------
class _Parser(argparse.ArgumentParser):
    def error(self, message):
        """argparse 의 기본 오류는 잘못 넘긴 인자를 그대로 메시지에 싣는다 — 실수로 명령 줄에 넘긴 값이 로그에 남지 않게 고정 문장만 낸다."""
        self.print_usage(sys.stderr)
        sys.stderr.write(USAGE_ERROR_LINE + "\n")
        raise SystemExit(2)


def build_parser():
    parser = _Parser(prog="python -m pipeline.auto_notice", description="병합 알림 자동화(병합 부탁·병합완료 확인)")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser(READY, help="열린 PR·머리 커밋·검사가 모두 맞으면 병합 부탁 문장을 만든다")
    sub.add_parser(CONFIRM, help="main 의 [M번호] 병합 커밋을 확인해 병합완료 확인 문장을 만든다")
    sub.add_parser(SEND, help="앞 단계가 만든 문장을 다시 검사한 뒤 텔레그램으로 보낸다(켬 상태 on 일 때만)")
    return parser


def main(argv=None, environ=None, out=print, reader=None, notifier=None, sleep=time.sleep, state_file=None):
    safe_output()
    environ = os.environ if environ is None else environ
    args = build_parser().parse_args(argv)
    try:
        if args.command == SEND:
            return run_send(environ, out, notifier=notifier, state_file=state_file)
        return run_decide(args.command, environ, out, reader=reader, sleep=sleep, state_file=state_file)
    except Exception as exc:  # noqa: BLE001 - 알림은 보조다: 예기치 않은 오류도 클래스 이름만 남기고 끝낸다(예외 문구에 값이 있을 수 있다)
        out(UNEXPECTED_LINE.format(name=type(exc).__name__))
        out(UNEXPECTED_WARNING)
        return 0


if __name__ == "__main__":
    sys.exit(main())
