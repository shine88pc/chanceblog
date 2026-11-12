"""운영자 요청함 — AI 가 운영자에게 요청·확인·결정을 텔레그램으로 보내고(requests), 운영자가 GitHub 이슈 양식으로 한 응답을 접수 확인한다(ack).
(표준 라이브러리만, Python 3.10 이상)

배경: 운영자는 공용 PC·휴대폰으로 가끔만 들어오고, AI 는 GitHub 화면(PR 만들기·병합·Actions 실행·설정·댓글)을 쓸 수 없어 막히는 일이 생긴다. 그럴 때 AI 는
저장소에 요청 파일(`인수인계/요청함/R-001_짧은-영문-설명.md`)을 `ai/claude/**` 브랜치로 push 하고, push 로 도는 워크플로(`[공통] AI 요청 텔레그램 알림`)가 그 파일의 제목·요약을
운영자 휴대폰 텔레그램으로 보낸다. 운영자는 GitHub 의 New issue 메뉴에서 양식(`[답변]` 결정·확인에 답하기, `[요청]` 새 일 맡기기)으로 답하고, 이슈가 열리면 워크플로
(`[공통] 운영자 응답 접수`)가 접수 확인(이슈 코멘트 + 텔레그램)을 보낸다. AI 세션은 그 이슈를 공개 REST 로 감시해 이어서 진행한다.
설명: docs/ARCHITECTURE.md §4-6 / 운영자용 안내: 인수인계/운영자_요청함_사용법.md / 규칙: docs/SECURITY_GUARDRAILS.md G-S9(응답 이슈 신뢰)·G-C13(푸시 알림 워크플로)

원칙
  1. **이슈의 제목·본문·요청 파일의 글은 모두 외부 입력이다.** 이슈 글은 `run:`·명령 줄·`$GITHUB_OUTPUT`·`::워크플로 명령` 어디에도 넣지 않고 이 파이썬 코드가 이벤트 JSON 파일에서 읽는다.
     코멘트와 텔레그램에는 **검증을 통과한 값**(요청 번호 `R-` 세 자리·양식의 답 선택지·짧은 선택 글자·이슈 번호)만 쓴다. 메모 글은 되풀이하지 않는다(글자 수만).
  2. **접수는 소유자만.** 이슈 작성자가 저장소 소유자이고(`user.login`) 작성자 권한이 OWNER(`author_association`)일 때만 한다. 둘 중 하나라도 아니면 아무것도 하지 않는다
     (코멘트·라벨·텔레그램 없음, 로그 한 줄). 양식 밖의 빈 이슈·요청서 파일·이슈 코멘트는 승인이 아니다(AGENTS.md).
  3. 텔레그램은 pipeline/notify.py 의 규칙을 그대로 쓴다(소독·허용 주소·토큰 비노출·통 수 상한·실패 격리). 새 HTTP 코드를 따로 만들지 않는다. GitHub REST 는 urllib 만, 토큰은
     Authorization 헤더에만 쓰고 오류 문구에 요청 객체·토큰을 싣지 않으며(클래스 이름·HTTP 상태·짧은 설명뿐), 응답 크기·시간에 상한이 있고 재시도는 한 번이다.
  4. 알림·접수는 보조다. 실패는 `::warning::` 한 줄뿐이고 종료 코드는 0(사용법 오류만 2) — 푸시·병합·이슈를 막지 않는다.
  5. 요청 번호는 안쪽 기록과 보이는 글의 꼴이 다르다(2026-11-04 운영자 요청): 파일 이름·앞머리 id·로그·실행 요약은 정본 `R-001`, 운영자가 읽는 글(텔레그램·접수 코멘트·양식·사용법)은 `r001`(notify.display_id).
     운영자가 양식에 쓰는 번호는 `r001`·`R001`·`r-001`·`R-001`·`r 001` 어느 꼴이든 normalize_request_id 가 정본으로 맞춘다(정본 모양은 여전히 notify.REQUEST_ID_RE 가 지킨다).
  6. **알림 번호(TG-STD, 운영자 승인 2026-11-06 계획 R-165)**: 요청 파일 앞머리 `no`(진행 현황 `P001`·병합 요청 `M001`·확인 요청은 숫자만 `001`, 유형마다 따로 늘어남)가 있는 파일은 유형별 칸으로
     표준 메시지(notify.format_notice)가 가고, 없는 옛 파일(요청 번호가 아래 상수 NOTICE_NO_REQUIRED_FROM_R 보다 작은 것)은 옛 모양 그대로다. 요청 번호 `R-nnn`·파일 이름·`id` 는 작업 식별자로 그대로다. 운영자의 답은 새 양식(`ai-answer.yml`:
     대상번호·선택·내용)도 읽는다 — **대상번호만 올린 답은 '확인함'이고 승인이 아니다**(승인은 선택이 그 확인 요청의 `approve` 보기와 같을 때만, 그 요청 파일에 적힌 항목에 한해 — G-S9).
     새 양식의 모양 오류는 폰으로도 회신한다(소유자 판정을 통과한 이슈에만). 옛 `[답변]` 양식(요청 번호)은 옛 R 번호 요청을 위해 함께 둔다.

명령 줄: python -m pipeline.operator_loop <requests | ack>   (외부 값을 인자로 받지 않는다 — 값은 환경변수·git·이벤트 JSON 파일에서만 읽는다)
  requests  환경변수 BEFORE_SHA·AFTER_SHA·DEFAULT_BRANCH(워크플로가 env 로 넘김)·GITHUB_REF_NAME(러너)·TELEGRAM_BOT_TOKEN·TELEGRAM_CHAT_ID
  ack       환경변수 GITHUB_EVENT_PATH·GITHUB_EVENT_NAME·GITHUB_REPOSITORY·GITHUB_REPOSITORY_OWNER(러너)·GITHUB_TOKEN·TELEGRAM_BOT_TOKEN·TELEGRAM_CHAT_ID
"""
import argparse
import http.client
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import namedtuple
from datetime import date
from pathlib import Path

from pipeline import notify
from pipeline.console import one_line, safe_output
from pipeline.llm import mask

ROOT = Path(__file__).resolve().parent.parent

# ---- 요청 파일 ---------------------------------------------------------------------------------
REQUEST_DIR = "인수인계/요청함"
GUIDE_PATH = "인수인계/운영자_요청함_사용법.md"
REQUEST_NAME_RE = re.compile(r"R-([0-9]{3})_([a-z0-9]+(?:-[a-z0-9]+)*)\.md")      # 요청 번호 + 영문 소문자·숫자·하이픈 슬러그
SLUG_MAX = 60
BASE_KEYS = ("id", "kind", "title", "summary", "urgency", "pr", "created")          # 옛 파일(R-001~)의 앞머리 키 — 이것만 있는 파일은 옛 모양 그대로 읽힌다
# 알림 번호 칸(TG-STD, 운영자 승인 2026-11-06 R-165): `no` 가 있는 파일만 새 규칙·새 메시지 모양을 쓴다. 유형별 칸은 번호 유형(진행 현황 P·병합 요청 M·확인 요청 숫자)마다 정해져 있다.
NOTICE_KEYS = ("no", "work")                                                          # no 알림 번호(P012·M007·003) · work 이 알림이 속한 작업 번호(R-160)
PROGRESS_KEYS = ("at", "now", "changed", "next", "eta", "waiting", "check")           # 진행 현황: 기준 시각(KST)·현재 진행·직전 보고 이후·다음 계획·예상 완료·확인/승인 대기·(선택) 점검 한 줄
MERGE_KEYS = ("repo", "target", "pr_title", "verify", "state")                        # 병합 요청: 저장소·병합 대상·실제 PR 제목(글자 그대로)·검증 결과·(선택) 상태
ASK_KEYS = ("options", "default", "approve")                                          # 확인 요청: (선택) 보기 · 기본 보기 번호 · 승인으로 읽는 보기 번호
MERGED_KIND = notify.MERGED_KIND
MERGED_KEYS = ("result",)                                                             # 병합완료 확인(kind: merged, 운영자 요청 2026-11-12): 결과 `정상`·`이상`
MERGED_LABEL_COMPACT = "".join(notify.REQUEST_KIND_LABELS[MERGED_KIND].split())          # 사유(summary)에 이 글자가 있으면 거절(공백은 세지 않는다 — merged_summary_label)
MERGED_ALLOWED = ("id", "kind", "title", "summary", "no", "result", "created")        # 병합완료 확인 파일의 앞머리에 쓸 수 있는 칸 전부 — 긴급도·PR·작업 번호·다른 알림 유형의 칸은 오류(짧은 확인 알림에 덧붙일 칸이 없다)
REQUEST_KEYS = (*BASE_KEYS, *NOTICE_KEYS, *PROGRESS_KEYS, *MERGE_KEYS, *ASK_KEYS, *MERGED_KEYS)   # 앞머리에서 읽는 키(그 밖의 키는 런타임에서 무시, 검증기에서는 오류)
NOTICE_ALLOWED = {notify.NOTICE_PROGRESS: PROGRESS_KEYS, notify.NOTICE_MERGE: MERGE_KEYS, notify.NOTICE_ASK: ASK_KEYS}
NOTICE_REQUIRED = {notify.NOTICE_PROGRESS: ("at", "now", "changed", "next", "eta", "waiting"), notify.NOTICE_MERGE: ("repo", "target", "pr_title", "verify"), notify.NOTICE_ASK: ()}
NOTICE_LIMITS = {**{key: limit for key, _label, limit in notify.PROGRESS_ITEMS}, "check": notify.CHECK_LIMIT, "target": notify.TARGET_LIMIT, "verify": notify.VERIFY_LIMIT,
                 "state": notify.STATE_LIMIT}                                         # 글자 수 상한(검증기만 강제 — 런타임은 받고 보낼 때 줄인다). PR 제목(notify.PR_TITLE_LIMIT)은 줄이지 않는다
NOTICE_NO_REQUIRED_FROM_R = 173          # 이 번호 이상의 요청 파일에는 `no` 가 필요하다(검증기 REQ-1). 그보다 작은 번호의 옛 모양 파일은 옛 모양 그대로 통과한다. 병합 직전에 '새 체계의 첫 요청 번호'(모든 원격 가지의 옛 모양 파일 최대 번호 + 1 이상)로 **여기 한 곳만** 고친다 — 문서는 이 상수를 이름으로만 가리키고 숫자를 적지 않는다(tests/test_notice_requests.py 가 확인)
URGENCIES = ("보통", "급함")
TITLE_MAX = notify.REQUEST_TITLE_LIMIT
SUMMARY_MAX = notify.REQUEST_SUMMARY_LIMIT
MAX_FRONT_LINES = 40            # 앞머리는 이 줄 수 안에서 닫혀야 한다
MAX_LINE_CHARS = 2000           # 앞머리 한 줄의 글자 수 상한(읽는 양을 묶는다)
MAX_REQUEST_MESSAGES = 3        # 한 푸시에서 보내는 요청 알림 통 수(그 이상은 마지막 통에 '… 외 N건')
MAX_CANDIDATES = 30             # 새 요청 파일 후보를 읽는 수의 상한
_KEY_LINE_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_-]*)[ \t]*:[ \t]*(.*)")
_DATE_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_PR_RE = re.compile(r"[1-9][0-9]{0,6}")
_BOM = chr(0xFEFF)

# no·work·fields·notice_error 는 새 칸이다(옛 파일은 기본값: 빈 글·빈 목록). fields: 번호 유형에 맞는 검증된 앞머리 값의 (키, 값) 쌍들(+ 확인 요청이면 summary) — notify.format_notice 가 읽는다.
# notice_error: 런타임이 새 칸의 문제를 만나 옛 모양(제목·요약)으로 보내기로 한 이유 코드(PROBLEMS 의 키). 문제가 없으면 빈 글.
Request = namedtuple("Request", "id kind title summary urgency pr created name no work fields notice_error", defaults=("", "", (), ""))

# 요청 파일 문제 분류 → 설명(검증기·로그가 쓴다. 외부 값은 없다)
PROBLEMS = {
    "bad_name": "파일 이름이 `R-001_짧은-영문-설명.md` 모양이 아닙니다(요청 번호 `R-` 세 자리, 영문 소문자·숫자·하이픈 슬러그)",
    "no_front_matter": "파일 맨 앞이 `---` 한 줄로 시작하는 앞머리가 아닙니다",
    "unclosed": f"앞머리를 닫는 `---` 줄이 첫 {MAX_FRONT_LINES}줄 안에 없습니다",
    "bad_line": "앞머리에 `키: 값` 한 줄 모양이 아닌 줄이 있습니다(값은 한 줄로 쓰고, 줄 앞에 공백을 두지 마세요)",
    "long_line": f"앞머리의 한 줄이 {MAX_LINE_CHARS}자를 넘습니다",
    "duplicate_key": "같은 키가 앞머리에 두 번 있습니다",
    "unknown_key": f"모르는 키가 있습니다(쓸 수 있는 키: {', '.join(REQUEST_KEYS)})",
    "bad_id": "id 가 `R-001` 모양(`R-` 와 숫자 세 자리)이 아닙니다",
    "id_mismatch": "id 가 파일 이름의 요청 번호와 다릅니다",
    "bad_kind": f"kind 는 {', '.join(notify.REQUEST_KIND_LABELS)} 중 하나여야 합니다",
    "bad_urgency": f"urgency 는 {', '.join(URGENCIES)} 중 하나여야 합니다",
    "bad_pr": "pr 은 PR 번호(양의 정수)여야 합니다",
    "bad_created": "created 는 `2026-10-28` 같은 날짜여야 합니다",
    "missing_id": "id 가 없습니다",
    "missing_kind": "kind 가 없습니다",
    "missing_title": "title 이 없거나 비어 있습니다",
    "missing_summary": "summary 가 없거나 비어 있습니다",
    "long_title": f"title 이 {TITLE_MAX}자를 넘습니다",
    "long_summary": f"summary 가 {SUMMARY_MAX}자를 넘습니다",
    "unreadable": "git 에서 파일 내용을 읽지 못했습니다",
    # 알림 번호 칸(TG-STD) — 문구에 외부 값은 없다
    "bad_no": "no 는 알림 번호 모양이 아닙니다(진행 현황 `P001`·병합 요청 `M001`·확인 요청은 숫자만 `001` — 숫자는 `001`~`999` 세 자리 또는 `1000`~`9999` 네 자리이고, 앞에 0 을 더 붙인 `P0012`·`0003` 이나 000 은 없습니다)",
    "no_kind_mismatch": "no 의 유형이 kind 와 맞지 않습니다(info 는 `P`, merge 는 `M`, decision·confirm·run 은 숫자만)",
    "no_required": f"R-{NOTICE_NO_REQUIRED_FROM_R} 부터의 요청 파일에는 알림 번호 `no` 가 필요합니다(`인수인계/도구/work/next_notice_no.py` 로 다음 번호를 구합니다)",
    "notice_keys_without_no": "알림 칸(work·at·now·…·repo·target·pr_title·…·options 등)은 `no` 와 함께만 쓸 수 있습니다",
    "foreign_key": "이 알림 유형에 쓰지 않는 칸이 있습니다(진행 현황: at·now·changed·next·eta·waiting·check / 병합 요청: repo·target·pr_title·verify·state / 확인 요청: options·default·approve)",
    "bad_work": "work 는 작업 번호 `R-160` 모양이어야 합니다",
    "bad_at": "at 는 `2026-11-06 12:07`(KST, 존재하는 날짜·시각) 모양이어야 합니다",
    "bad_repo": "repo 는 `소유자/저장소` 모양이어야 합니다",
    "bad_options": f"options 는 ` / ` 로 이은 보기 2~{notify.OPTIONS_MAX}개(각 보기는 비지 않고 {notify.OPTION_LIMIT}자 이하)여야 합니다",
    "bad_default": "default 는 보기 번호(1~보기 수)여야 하고 options 가 있어야 합니다",
    "bad_approve": "approve 는 보기 번호(1~보기 수)여야 하고 options 가 있어야 합니다",
    "approve_is_default": "approve(승인으로 읽는 보기)는 default(답이 없을 때 진행하는 보기)와 같을 수 없습니다 — 침묵이 승인이 되지 않게",
    "pr_title_control": "pr_title 에 제어 문자·보이지 않는 글자·줄 바꿈이 있습니다(글자 그대로 눈으로 같은지 볼 수 없습니다)",
    "pr_title_secret": "pr_title 에 비밀 값처럼 보이는 글자가 있습니다(PR 제목은 고치지 않고 그대로만 보내므로 보낼 수 없습니다)",
    "long_pr_title": f"pr_title 이 {notify.PR_TITLE_LIMIT}자를 넘습니다(PR 제목은 줄이지 않고 그대로 보냅니다 — PR 제목을 줄이세요)",
    # 병합완료 확인(kind: merged, 운영자 요청 2026-11-12) — 문구에 외부 값은 없다
    "bad_result": "result 는 `정상` 또는 `이상` 이어야 합니다",
    "missing_result": "`result` 칸이 없거나 비어 있습니다(병합완료 확인에는 필요합니다 — `정상` 또는 `이상`)",
    "merged_title_mismatch": "title 은 정확히 `[M050] 병합완료 확인 - 정상` 꼴(번호와 결과가 `no`·`result` 와 같은 값)이어야 합니다",
    "long_merged_summary": (f"병합완료 확인의 summary 는 정상이면 {notify.MERGED_SUMMARY_LIMITS[notify.MERGED_OK]}자, "
                            f"이상이면 {notify.MERGED_SUMMARY_LIMITS[notify.MERGED_BAD]}자 이하 한 줄이어야 합니다"),
    "merged_unpaired": "병합완료 확인의 `no` 와 같은 번호(M 번호)를 쓰는 병합 부탁(`kind: merge`) 요청 파일이 이 요청함에 없습니다 — 짝 없는 병합완료 확인은 보내지 않습니다",
    "merged_duplicate": "같은 병합 부탁(같은 M 번호)의 병합완료 확인이 이미 있습니다 — 하나만 둡니다(이상을 알린 뒤 고친 결과는 다른 알림(`info`)으로 보냅니다 — 알림은 새로 더해진 파일만 고르므로 파일을 고쳐도 다시 가지 않습니다)",
    "merged_summary_label": "병합완료 확인의 summary(사유)에는 `병합완료 확인` 글자를 쓰지 않습니다 — 폰의 둘째 줄이 제목 줄처럼 읽힙니다",
}
for _key in ("at", "now", "changed", "next", "eta", "waiting", "repo", "target", "pr_title", "verify"):
    PROBLEMS["missing_" + _key] = f"`{_key}` 칸이 없거나 비어 있습니다(이 알림 유형에는 필요합니다)"
for _key, _limit in NOTICE_LIMITS.items():
    PROBLEMS["long_" + _key] = f"`{_key}` 가 {_limit}자를 넘습니다"


class RequestError(ValueError):
    """요청 파일 하나가 형식에 맞지 않을 때. code 는 PROBLEMS 의 키다(문구에는 외부 값이 없다)."""

    def __init__(self, code):
        super().__init__(PROBLEMS.get(code, code))
        self.code = code


def problem_text(code):
    return PROBLEMS.get(code, "알 수 없는 문제입니다")


def _unquote(raw):
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
        return raw[1:-1]
    return raw


def parse_request(name, text, strict=False):
    """요청 파일 한 개(이름·내용)를 읽어 Request 로 돌려준다. 맞지 않으면 RequestError(code).

    앞머리는 파일 맨 앞 `---` 줄과 닫는 `---` 줄 사이의 `키: 값` 한 줄들이다(YAML 해석기를 쓰지 않는다 — 블록·목록·앵커·태그를 읽지 않는다). 줄은 `\\n` 으로만 나눈다(U+2028 같은
    다른 줄 바꿈 문자로 줄을 위조하지 못하게). 값은 한 줄이고 양 끝이 같은 따옴표면 벗긴다(이스케이프는 풀지 않는다). id 는 파일 이름의 요청 번호와 같아야 한다.
    strict=False(런타임): 모르는 키는 무시하고 title·summary 가 길면 그대로 받는다(보낼 때 safe_text 가 줄인다 — 알림을 잃지 않는다).
    strict=True(검증기): 모르는 키·긴 title·summary 도 오류다(AI 가 올리기 전에 실수를 잡는다). 본문(닫는 `---` 뒤)은 읽지 않는다."""
    match = REQUEST_NAME_RE.fullmatch(str(name))
    if match is None or len(match.group(2)) > SLUG_MAX:
        raise RequestError("bad_name")
    lines = str(text).lstrip(_BOM).replace("\r\n", "\n").split("\n")
    if lines[0].rstrip() != "---":
        raise RequestError("no_front_matter")
    close = next((index for index in range(1, min(len(lines), MAX_FRONT_LINES + 1)) if lines[index].rstrip() == "---"), None)
    if close is None:
        raise RequestError("unclosed")
    values = {}
    for line in lines[1:close]:
        if len(line) > MAX_LINE_CHARS:
            raise RequestError("long_line")
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        found = _KEY_LINE_RE.fullmatch(line)
        if found is None:
            raise RequestError("bad_line")
        key = found.group(1)
        if key not in REQUEST_KEYS:
            if strict:
                raise RequestError("unknown_key")
            continue
        if key in values:
            raise RequestError("duplicate_key")
        values[key] = found.group(2).strip() if key == "pr_title" else _unquote(found.group(2).strip())       # PR 제목은 따옴표까지 제목의 글자다 — 벗기지 않는다
    for key in ("id", "kind", "title", "summary"):
        if key not in values:
            raise RequestError("missing_" + key)
    request_id = values["id"]
    if not notify.REQUEST_ID_RE.fullmatch(request_id):
        raise RequestError("bad_id")
    if request_id != "R-" + match.group(1):
        raise RequestError("id_mismatch")
    if values["kind"] not in notify.REQUEST_KIND_LABELS:
        raise RequestError("bad_kind")
    for key in ("title", "summary"):
        if not notify.clean_text(values[key], 10 ** 6):
            raise RequestError("missing_" + key)
    if strict and len(values["title"]) > TITLE_MAX:
        raise RequestError("long_title")
    if strict and len(values["summary"]) > SUMMARY_MAX:
        raise RequestError("long_summary")
    urgency = values.get("urgency", URGENCIES[0])
    if urgency not in URGENCIES:
        raise RequestError("bad_urgency")
    pr = values.get("pr")
    if pr is not None and not _PR_RE.fullmatch(pr):
        raise RequestError("bad_pr")
    created = values.get("created", "")
    if created:
        try:
            if not _DATE_RE.fullmatch(created):
                raise ValueError(created)
            date.fromisoformat(created)
        except ValueError:
            raise RequestError("bad_created") from None
    no, work, fields, notice_error = "", "", (), ""
    title, summary = values["title"], values["summary"]
    problem = notice_problem(values, values["kind"], int(match.group(1)), strict)
    if problem and strict:
        raise RequestError(problem)
    if problem:
        notice_error = problem                  # 런타임: 새 칸이 맞지 않으면 알림을 잃지 않으려고 옛 모양(제목·요약)으로 보낸다 — 이유는 run_requests 가 로그에 남긴다
        if values["kind"] == MERGED_KIND:       # 병합완료 확인만은 옛 모양으로 보내지 않는다: 틀린 파일의 제목(`- 정상` 인데 result 는 이상)이 폰에 그대로 나가 거짓 '정상' 이 되지 않게 글을 비워 돌려준다(D1)
            title = summary = ""                # (폰에는 run_requests 가 요청 번호만 든 고정 문구 notify.format_merged_unreadable 을 보낸다)
    elif "no" in values:
        no, work = values["no"], values.get("work", "")
        if values["kind"] == MERGED_KIND:
            fields = (("result", values["result"]), ("summary", values["summary"]))          # 병합완료 확인: 결과와(이상일 때 폰에 싣는) 사유 한 줄
        else:
            wanted = (*NOTICE_ALLOWED[notify.notice_type(no)], *(["summary"] if notify.notice_type(no) == notify.NOTICE_ASK else []))
            fields = tuple((key, values[key]) for key in (*wanted,) if key in values)
    return Request(request_id, values["kind"], title, summary, urgency, int(pr) if pr else None, created, str(name), no, work, fields, notice_error)


def notice_problem(values, kind, number, strict):
    """앞머리의 알림 칸(`no`·`work`·유형별 칸)이 맞는지 — 문제 코드(PROBLEMS 의 키)를 돌려주고 없으면 빈 글. values 는 앞머리 값(글), kind 는 이미 검증한 요청 종류, number 는 파일 이름의 요청 번호(정수).

    `no` 가 없는 파일은 옛 모양이다(새 칸이 하나라도 있으면 문제, strict 이고 번호가 NOTICE_NO_REQUIRED_FROM_R 이상이면 `no` 가 필요). `no` 가 있으면 번호 모양·kind 와의 유형 일치(info=P·merge=M·그 밖=숫자)·유형별 필수 칸·다른 유형의 칸 금지·값 모양을 본다.
    kind 가 merged(병합완료 확인, 2026-11-12)이면 위 유형별 규칙을 거치지 않고 전용 규칙(_merged_problem)으로 본다.
    strict=True(검증기)는 글자 수 상한과 PR 제목의 안전(제어·보이지 않는 글자·비밀 모양·200자)까지 본다 — 런타임은 받고 보낼 때 줄이되 PR 제목은 줄이지 않고 notify 가 보낼 수 없으면 보내지 않는다."""
    present = [key for key in values if key in (*NOTICE_KEYS, *PROGRESS_KEYS, *MERGE_KEYS, *ASK_KEYS, *MERGED_KEYS)]
    if kind == MERGED_KIND:                                  # 병합완료 확인은 칸이 따로 정해진 새 종류라 아래 유형별 규칙을 거치지 않는다(`result` 는 다른 종류에서는 `foreign_key`)
        return _merged_problem(values, strict)
    if "no" not in values:
        if present:
            return "notice_keys_without_no"
        return "no_required" if strict and number >= NOTICE_NO_REQUIRED_FROM_R else ""
    no = values["no"]
    kind_type = notify.notice_type(no)
    if not kind_type:
        return "bad_no"
    if kind_type != notify.NOTICE_KIND_TYPES[kind]:
        return "no_kind_mismatch"
    if any(key != "work" and key != "no" and key not in NOTICE_ALLOWED[kind_type] for key in present):
        return "foreign_key"
    for key in NOTICE_REQUIRED[kind_type]:
        value = values.get(key, "")
        if not (value.strip() if key == "pr_title" else notify.clean_text(value, 10 ** 6)):
            return "missing_" + key
    if "work" in values and not notify.REQUEST_ID_RE.fullmatch(values["work"]):
        return "bad_work"
    if kind_type == notify.NOTICE_PROGRESS:
        try:
            notify.notice_stamp(values["at"])
        except ValueError:
            return "bad_at"
    elif kind_type == notify.NOTICE_MERGE:
        if _REPO_RE.fullmatch(values["repo"]) is None:
            return "bad_repo"
        if strict:
            title_problem = notify.pr_title_problem(values["pr_title"], limit=notify.PR_TITLE_LIMIT)
            if title_problem:
                return {"too_long": "long_pr_title", "control": "pr_title_control", "secret": "pr_title_secret"}.get(title_problem, "missing_pr_title")
    else:
        problem = _ask_problem(values, strict)
        if problem:
            return problem
    if strict:
        for key, limit in NOTICE_LIMITS.items():
            if len(values.get(key, "")) > limit:
                return "long_" + key
    return ""


def _merged_problem(values, strict):
    """병합완료 확인(`kind: merged`)의 문제 코드(없으면 빈 글). `no` 는 확인하는 병합 요청의 M 번호이고(요청 번호와 무관하게 늘 필요 — 새 종류다) `result` 는 `정상`·`이상`이며, 쓸 수 있는 칸은
    MERGED_ALLOWED 뿐이다(긴급도·PR·작업 번호·다른 알림 유형의 칸은 foreign_key). `title` 은 번호·결과로 정해진 글(notify.merged_title)과 글자 그대로 같아야 하고, strict 이면 summary 가
    정상 60자·이상 100자 이하여야 한다. summary(사유)에는 `병합완료 확인` 글자(공백 없이 비교)를 쓸 수 없다 — 제목 꼴 사유가 폰의 둘째 줄에서 첫 줄과 어긋나 보이는 것을 막는다(두 읽기 모두).
    같은 번호의 병합 요청이 있는지·병합완료 확인이 하나뿐인지는 다른 파일을 봐야 해서 이 함수가 아니라 merged_pairing_problems(검증기 REQ-1)가 본다."""
    if "no" not in values:
        return "no_required"
    no = values["no"]
    kind_type = notify.notice_type(no)
    if not kind_type:
        return "bad_no"
    if kind_type != notify.NOTICE_KIND_TYPES[MERGED_KIND]:
        return "no_kind_mismatch"
    if any(key not in MERGED_ALLOWED for key in values):
        return "foreign_key"
    result = values.get("result", "")
    if not notify.clean_text(result, 10 ** 6):
        return "missing_result"
    if result not in notify.MERGED_RESULTS:
        return "bad_result"
    if values["title"] != notify.merged_title(no, result):
        return "merged_title_mismatch"
    if MERGED_LABEL_COMPACT in "".join(values["summary"].split()):
        return "merged_summary_label"
    if strict and len(values["summary"]) > notify.MERGED_SUMMARY_LIMITS[result]:
        return "long_merged_summary"
    return ""


def merged_pairing_problems(entries):
    """요청함의 요청 파일들(entries: [(파일 이름, Request)] — 읽는 데 성공한 것만, 검증기 REQ-1 이 넘긴다)에서 병합완료 확인(kind: merged)의 짝 규칙을 본다 → [(파일 이름, 문제 코드)](entries 의 순서).
    ① 같은 M 번호를 쓰는 병합 요청(`kind: merge`)이 있어야 한다(merged_unpaired) ② 같은 M 번호의 병합완료 확인은 하나뿐이다 — 둘째부터 merged_duplicate(첫째가 이긴다).
    번호가 없는 것(옛 모양으로 폴백한 파일)은 보지 않는다."""
    merge_numbers = {request.no for _name, request in entries if request.kind == "merge" and request.no}
    problems, seen = [], set()
    for name, request in entries:
        if request.kind != MERGED_KIND or not request.no:
            continue
        if request.no not in merge_numbers:
            problems.append((name, "merged_unpaired"))
        if request.no in seen:
            problems.append((name, "merged_duplicate"))
        seen.add(request.no)
    return problems


def _ask_problem(values, strict):
    """확인 요청의 보기 칸(options·default·approve)의 문제 코드. options 는 있으면 2~5개이고 비지 않아야 한다. default·approve 는 보기 번호이고 서로 달라야 한다."""
    options = notify.split_options(values.get("options"))
    if "options" in values and (not 2 <= len(options) <= notify.OPTIONS_MAX or any(not option for option in options)
                                or (strict and any(len(option) > notify.OPTION_LIMIT for option in options))):
        return "bad_options"
    numbers = {}
    for key in ("default", "approve"):
        if key in values:
            if re.fullmatch(r"[1-5]", values[key]) is None or int(values[key]) > len(options):
                return "bad_" + key
            numbers[key] = int(values[key])
    if "default" in numbers and numbers["default"] == numbers.get("approve"):
        return "approve_is_default"
    return ""


# ---- 새 요청 파일 고르기 --------------------------------------------------------------------------
_SHA_RE = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")
_ZERO_RE = re.compile(r"0{40}|0{64}")
_BRANCH_RE = re.compile(r"[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)*")


def valid_branch(name, prefix=""):
    """git 브랜치 이름으로 안전한 모양인가(영문·숫자·`._-`·`/` 뿐, `-` 로 시작하지 않음, `..`·`.` 로 시작하는 조각·`.lock` 끝 조각 없음, 120자 이하, 선택적 접두사)."""
    if (not isinstance(name, str) or not name.startswith(prefix) or name.startswith("-") or len(name) > 120 or _BRANCH_RE.fullmatch(name) is None
            or ".." in name):
        return False
    return not any(part.startswith(".") or part.endswith(".lock") for part in name.split("/"))


def _paths_from(raw, directory=REQUEST_DIR):
    """`-z` 로 받은 git 경로 출력에서 요청 파일 경로만(정확히 `인수인계/요청함/<요청 파일 이름>`)."""
    found = set()
    for token in raw.decode("utf-8", "replace").split("\0"):
        folder, _, base = token.rpartition("/")
        if folder == directory and REQUEST_NAME_RE.fullmatch(base):
            found.add(base)
    return found


def request_name_sets(root, before, after, default_branch, ref_name, runner=subprocess.run):
    """(트리 차이로 본 더해진 요청 파일 이름 집합, 커밋 차이로 본 집합) 둘. 구할 수 없으면 notify.GitError — 호출한 쪽은 보내지 않고 경고한다(중복·도배 방지).

    새 파일은 두 가지를 모두 만족하는 것(둘의 교집합 — new_request_names)이다:
      ① 트리 차이: `git diff --diff-filter=A <기준> <AFTER>` 에서 '더해진' 것(수정만 된 파일·이름만 바뀐 파일은 빠진다). 기준은 BEFORE 이고, 새 브랜치 첫 push 처럼 BEFORE 가
         전부 0 이면 `merge-base(origin/<기본 브랜치>, AFTER)` 다(얕은 복제면 기준을 믿을 수 없어 GitError).
      ② 커밋 차이: AFTER 에서 도달할 수 있지만 BEFORE·**이 브랜치 말고 다른 모든 원격 브랜치**(기본 브랜치 포함)에서는 도달할 수 없는 커밋이 더한 것. main 을 이 브랜치에
         합치거나(merge) 이미 알린 다른 브랜치를 합치거나 그런 브랜치에서 새 브랜치를 만들어도 그 브랜치들이 가져온 요청 파일을 다시 알리지 않는다. 같은 내용의 리베이스·강제 push 는
         ①이 거른다(BEFORE 트리에 이미 있는 파일).
    트리 차이에만 있고 커밋 차이로 걸러진 파일은 '다른 브랜치에도 있어 알리지 않은' 파일이다(request_name_selection 이 따로 돌려주고 run_requests 가 로그에 남긴다 — 요청 파일을 가진
    커밋이 든 두 브랜치를 한꺼번에 push 하면 둘 다 서로가 가졌다고 보고 아무도 알리지 않는 경우를 눈에 띄게 하려는 것, 독립 검증 N-1).
    BEFORE·AFTER·기본 브랜치·이 브랜치 이름은 호출한 쪽이 모양을 검증했어야 하고(여기서도 한 번 더 본다) git 인자의 맨 앞이 `-` 가 될 수 없다."""
    if not (isinstance(after, str) and _SHA_RE.fullmatch(after)) or _ZERO_RE.fullmatch(after):
        raise notify.GitError("AFTER_SHA 가 올바른 커밋 번호가 아닙니다")
    if not (isinstance(before, str) and (_SHA_RE.fullmatch(before) or _ZERO_RE.fullmatch(before))):
        raise notify.GitError("BEFORE_SHA 가 올바른 커밋 번호가 아닙니다")
    if not valid_branch(default_branch) or not valid_branch(ref_name, "ai/claude/"):
        raise notify.GitError("브랜치 이름이 올바르지 않습니다")
    if _ZERO_RE.fullmatch(before):
        shallow = notify.run_git(root, "rev-parse", "--is-shallow-repository", runner=runner).decode("utf-8", "replace").strip()
        if shallow != "false":
            raise notify.GitError("얕은 복제라 새 브랜치의 기준 커밋을 구할 수 없습니다")
        start = notify.run_git(root, "merge-base", f"origin/{default_branch}", after, runner=runner).decode("utf-8", "replace").strip()
        if not _SHA_RE.fullmatch(start):
            raise notify.GitError("새 브랜치의 기준 커밋을 구하지 못했습니다")
        already = []
    else:
        start, already = before, [f"^{before}"]
    pathspec = REQUEST_DIR + "/"
    by_tree = _paths_from(notify.run_git(root, "diff", "--name-only", "--diff-filter=A", "-M", "-z", start, after, "--", pathspec, runner=runner))
    by_commit = _paths_from(notify.run_git(root, "log", "--diff-filter=A", "--name-only", "-M", "-z", "--format=", after, *already,
                                           "--not", f"--exclude=origin/{ref_name}", "--remotes=origin", "--", pathspec, runner=runner))
    return by_tree, by_commit


def new_request_names(root, before, after, default_branch, ref_name, runner=subprocess.run):
    """이번 push 가 **새로 더한** 요청 파일 이름 목록(정렬, 최대 MAX_CANDIDATES) — request_name_sets 의 두 집합의 교집합. 구할 수 없으면 notify.GitError."""
    by_tree, by_commit = request_name_sets(root, before, after, default_branch, ref_name, runner=runner)
    return sorted(by_tree & by_commit)[:MAX_CANDIDATES]


def request_name_selection(root, before, after, default_branch, ref_name, runner=subprocess.run):
    """(새 요청 파일 이름 목록, 트리 차이에는 있지만 커밋 차이로 걸러진 — 다른 브랜치에도 있어 알리지 않는 — 이름 목록). 각각 정렬·최대 MAX_CANDIDATES."""
    by_tree, by_commit = request_name_sets(root, before, after, default_branch, ref_name, runner=runner)
    return sorted(by_tree & by_commit)[:MAX_CANDIDATES], sorted(by_tree - by_commit)[:MAX_CANDIDATES]


# ---- 알림 보내기(requests) ---------------------------------------------------------------------------
REQUESTS_SKIP_LINE = "AI 요청 알림: 건너뜀(시크릿 없음)"
REQUESTS_NONE_LINE = "AI 요청 알림: 이 푸시에 새 요청 파일이 없어 보내지 않았습니다"
REQUESTS_SKIPPED_LINE = "AI 요청 알림: 다른 브랜치에도 있어 알리지 않은 요청 파일: {ids}"
MAX_SKIPPED_IDS = 10            # 위 줄에 싣는 요청 번호 수(넘으면 '외 N건')
REQUEST_WARNING_LINE = ("::warning::텔레그램 알림을 보내지 못했습니다. 이유는 바로 앞 로그 줄에 있고, Actions 의 '[공통] 텔레그램 알림 시험' 으로 연결을 점검할 수 있습니다"
                        "(푸시·병합에는 영향이 없습니다).")
REQUEST_PROBLEM_WARNING = "::warning::요청 파일을 읽지 못해 알리지 않은 것이 있습니다. 이유는 바로 앞 로그 줄에 있습니다(파일은 그대로이니 고쳐서 다시 push 하세요)."
GIT_WARNING = "::warning::새 요청 파일을 가려내지 못해 알림을 보내지 않았습니다(중복·도배를 막으려는 것입니다). 이유는 바로 앞 로그 줄에 있습니다."
NOTICE_FALLBACK_WARNING = ("::warning::요청 파일의 알림 칸(no·at·now 등)이 맞지 않아 번호 없는 옛 모양으로 보낸 알림이 있습니다. 이유는 바로 앞 로그 줄에 있습니다"
                           "(파일을 고쳐 새 번호로 다시 보내세요).")
MERGED_UNREADABLE_LINE = "AI 요청 알림: {name} 은 병합완료 확인 파일의 칸이 맞지 않아 파일의 제목·요약·결과를 싣지 않고 고정 문구로 보냅니다 — {problem}"
MERGED_UNREADABLE_WARNING = ("::warning::병합완료 확인 요청 파일의 칸이 맞지 않아 내용 없이 고정 문구로 보낸 알림이 있습니다. 이유는 바로 앞 로그 줄에 있습니다"
                             "(파일을 고쳐도 다시 알리지 않으니 확인 결과는 다른 알림(info)으로 보내세요).")


def skipped_line(names):
    """'다른 브랜치에도 있어 알리지 않은 요청 파일' 로그 한 줄. 이름은 이미 정규식을 통과한 값이라 앞의 요청 번호(R-001)만 싣는다(최대 MAX_SKIPPED_IDS 개, 넘으면 '외 N건')."""
    ids = sorted({name.split("_", 1)[0] for name in names})
    shown = ", ".join(ids[:MAX_SKIPPED_IDS]) + (f" 외 {len(ids) - MAX_SKIPPED_IDS}건" if len(ids) > MAX_SKIPPED_IDS else "")
    return REQUESTS_SKIPPED_LINE.format(ids=shown)


def blob_url(ref, path):
    """저장소 파일 화면 주소(경로는 한글이라 퍼센트 인코딩한다). 텔레그램 버튼으로 쓰려면 notify.allowed_url 을 통과해야 한다."""
    return f"{notify.REPO_URL}/blob/{urllib.parse.quote(ref, safe='/')}/{urllib.parse.quote(path, safe='/')}"


BLOG_REPO = notify.REPO_URL.split("github.com/", 1)[1]          # `shine88pc/chanceblog` — 허용 주소가 가리키는 저장소(다른 저장소의 PR 은 이 주소로 열 수 없다)


def request_buttons(request, ref_name, default_branch):
    """요청 알림의 버튼(최대 4). 옛 파일(`no` 없음): ① 요청 열기(그 파일, 이 브랜치) ② PR 열기(pr 이 있을 때) ③ 답하기(새 이슈 양식 고르기) ④ 사용법(기본 브랜치).
    번호 있는 파일(TG-STD): 확인 요청은 ① 답하기(새 답변 양식 `ai-answer.yml` 바로 열기)로 시작하고, 진행 현황·병합 요청은 답할 일이 없어 답하기가 없다.
    병합 요청의 저장소가 이 블로그 저장소가 아니면(예: 데스크톱) PR 열기를 달지 않는다 — 주소가 블로그 저장소의 같은 번호 PR 을 가리켜 틀리고 허용 주소도 아니다. 주소는 코드가 만든다.
    병합완료 확인(`merged`, 2026-11-12)은 정상이면 단추가 없고(제목 한 줄뿐) 이상이면 '요청 열기' 하나이며, 칸이 맞지 않아 고정 문구로 가는 파일(번호 없음)도 '요청 열기' 하나다."""
    if request.kind == MERGED_KIND:                          # 병합완료 확인(2026-11-12): 정상은 제목 한 줄뿐 단추 없음, 이상·칸이 틀린 파일은 내용을 읽으러 가는 '요청 열기' 하나
        if request.no and dict(request.fields).get("result") == notify.MERGED_OK:
            return []
        return [("요청 열기", blob_url(ref_name, f"{REQUEST_DIR}/{request.name}"))]
    kind = notify.notice_type(request.no) if request.no else ""
    fields = dict(request.fields)
    buttons = [("답하기", notify.NEW_ANSWER_URL)] if kind == notify.NOTICE_ASK else []
    buttons.append(("요청 열기", blob_url(ref_name, f"{REQUEST_DIR}/{request.name}")))
    if request.pr and not (kind == notify.NOTICE_MERGE and fields.get("repo") != BLOG_REPO):
        buttons.append(("PR 열기", f"{notify.REPO_URL}/pull/{request.pr}"))
    if not kind:
        buttons.append(("답하기", notify.NEW_ISSUE_URL))
    buttons.append(("사용법", blob_url(default_branch, GUIDE_PATH)))
    return buttons


NOTICE_DUPLICATE_LINE = ("AI 요청 알림: 알림 번호 {no} 를 다른 요청 파일({names})도 원격 가지에서 쓰고 있습니다 — 번호가 겹쳤습니다(알림은 그대로 보냈습니다). "
                         "`인수인계/도구/work/next_notice_no.py` 로 번호를 다시 정해 새 요청 번호의 새 파일로 알리세요")
NOTICE_DUPLICATE_WARNING = "::warning::알림 번호가 다른 요청 파일과 겹쳤습니다(알림은 보냈습니다). 이유는 바로 앞 로그 줄에 있습니다."
MAX_GREP_REFS = 40              # git grep 한 번에 주는 원격 가지 수(명령 줄 길이)
MAX_DUPLICATE_NAMES = 5         # 겹친 파일 이름을 로그에 싣는 수


def other_files_with_notice_no(root, no, name, runner=subprocess.run):
    """이 알림 번호(`no`)를 **이름이 다른** 요청 파일이 원격 가지(`refs/remotes/origin`)에서 쓰고 있는지 — 겹친 파일 이름 목록(정렬, 최대 MAX_DUPLICATE_NAMES). 로그 경고용이라
    알아내지 못하면(git 실패·읽을 수 없는 출력) 빈 목록이고 어떤 경우에도 알림을 막지 않는다. 같은 파일이 다른 가지에도 있는 것(이 가지에서 만든 가지)은 겹침이 아니다.
    앞머리 `no: P012`·`no: "003"`·`no: '003'` 줄만 찾는다(정규식으로 값 전체가 같을 때만 — `P0123` 은 `P012` 와 다르다)."""
    try:
        listing = notify.run_git(root, "for-each-ref", "--format=%(refname)", "refs/remotes/origin", runner=runner).decode("utf-8", "replace").split()
        refs = [ref for ref in listing if ref != "refs/remotes/origin/HEAD" and _BRANCH_RE.fullmatch(ref.replace("refs/remotes/", "", 1))]
        pattern = "^no: *[\"']?" + re.escape(no) + "[\"']? *$"
        found = set()
        for start in range(0, len(refs), MAX_GREP_REFS):
            done = runner(["git", "grep", "-l", "-z", "-E", "-e", pattern, *refs[start:start + MAX_GREP_REFS], "--", REQUEST_DIR], cwd=str(root), capture_output=True,
                          timeout=notify.GIT_TIMEOUT, check=False)
            if done.returncode != 0:                      # 1 = 찾은 것 없음, 그 밖은 읽지 못함 — 둘 다 겹침을 알릴 근거가 없다
                continue
            for token in done.stdout.decode("utf-8", "replace").split("\0"):
                base = token.rpartition("/")[2]
                if base != name and REQUEST_NAME_RE.fullmatch(base):
                    found.add(base)
        return sorted(found)[:MAX_DUPLICATE_NAMES]
    except Exception:  # noqa: BLE001 - 경고용 조회라 어떤 오류도 알림을 막지 않는다(예외 문구는 쓰지 않는다)
        return []


def run_requests(environ, notifier, root, out, runner=subprocess.run):
    """push 한 커밋이 새로 더한 요청 파일을 텔레그램으로 알린다. 종료 코드는 항상 0(실패·건너뜀은 로그 한 줄과 `::warning::`)."""
    if not notifier.enabled:
        out(REQUESTS_SKIP_LINE)
        return 0
    before, after = str(environ.get("BEFORE_SHA") or "").strip(), str(environ.get("AFTER_SHA") or "").strip()
    default_branch = str(environ.get("DEFAULT_BRANCH") or "").strip() or "main"
    ref_name = str(environ.get("GITHUB_REF_NAME") or "").strip()
    try:
        names, skipped = request_name_selection(root, before, after, default_branch, ref_name, runner=runner)
    except notify.GitError as exc:
        out(notifier.scrub(f"AI 요청 알림: 새 요청 파일을 찾지 못해 보내지 않았습니다 — {exc}"))
        out(GIT_WARNING)
        return 0
    if skipped:
        out(skipped_line(skipped))                       # 요청 파일을 가진 커밋이 든 두 브랜치를 한꺼번에 push 하면 아무도 알리지 못할 수 있다 — 그 일이 로그에 보이게
    if not names:
        out(REQUESTS_NONE_LINE)
        return 0
    requests, bad = [], 0
    for name in names:
        try:
            requests.append(parse_request(name, notify.read_blob(root, after, f"{REQUEST_DIR}/{name}", runner=runner)))
        except RequestError as exc:
            bad += 1
            out(f"AI 요청 알림: {name} 을 알리지 못했습니다 — {problem_text(exc.code)}")
        except notify.GitError:
            bad += 1
            out(f"AI 요청 알림: {name} 을 알리지 못했습니다 — {problem_text('unreadable')}")
    if bad:
        out(REQUEST_PROBLEM_WARNING)
    sending = sorted(requests, key=lambda request: request.name)
    shown, hidden = sending[:MAX_REQUEST_MESSAGES], len(sending) - MAX_REQUEST_MESSAGES
    failed, lines, fallbacks, duplicates, unreadables = 0, [], 0, 0, 0
    for index, request in enumerate(shown):
        more = hidden if index == len(shown) - 1 and hidden > 0 else 0
        buttons = request_buttons(request, ref_name, default_branch)
        unreadable = request.kind == MERGED_KIND and bool(request.notice_error)     # 병합완료 확인으로 읽혔지만 칸이 맞지 않는 파일 — 옛 모양(제목·요약)이 아니라 고정 문구만 보낸다(D1: 거짓 '정상' 방지)
        if unreadable:
            unreadables += 1
            out(MERGED_UNREADABLE_LINE.format(name=request.name, problem=problem_text(request.notice_error)))
        elif request.notice_error:                       # 새 칸이 맞지 않아도 알림을 잃지 않는다 — 옛 모양(제목·요약)으로 보내고 이유를 남긴다
            fallbacks += 1
            out(f"AI 요청 알림: {request.name} 의 알림 칸이 맞지 않아 옛 모양(제목·요약)으로 보냅니다 — {problem_text(request.notice_error)}")
        if unreadable:
            result = notifier.notify_merged_unreadable(request.id, buttons=buttons, more=more)
        elif request.no and request.kind == MERGED_KIND:           # 병합완료 확인(2026-11-12): 정상은 제목 한 줄, 이상은 제목 + 사유 한 줄
            result = notifier.notify_merged(request.no, dict(request.fields), buttons=buttons, more=more)
        elif request.no:
            result = notifier.notify_notice(request.no, dict(request.fields), urgency=request.urgency, work=request.work, pr=request.pr, buttons=buttons, more=more)
        else:
            result = notifier.notify_ai_request(request.id, request.kind, request.title, request.summary, urgency=request.urgency, pr=request.pr, buttons=buttons, more=more)
        if result.sent:
            numbered = f" (알림 번호 {request.no})" if request.no else ""
            out(f"AI 요청 알림: {request.id} 을 알렸습니다{numbered}")
            lines.append(f"- {request.id}: 알렸습니다{numbered}")
        else:
            failed += 1
            out(notifier.scrub(f"AI 요청 알림: {request.id} 을 보내지 못했습니다 — {notify.describe(result)}"))
            lines.append(f"- {request.id}: 보내지 못했습니다({result.reason})")
        if request.no and request.kind != MERGED_KIND:   # 알림 번호가 다른 가지의 다른 요청 파일과 겹쳤는지(로그 경고만 — 알림은 이미 보냈고 이 확인은 알림을 막지 않는다)
                                                         # (병합완료 확인은 짝인 병합 요청과 같은 M 번호를 쓰므로 여기서 겹침으로 세지 않는다 — 짝·중복은 검증기 REQ-1 이 본다)
            twins = other_files_with_notice_no(root, request.no, request.name, runner=runner)
            if twins:
                duplicates += 1
                out(NOTICE_DUPLICATE_LINE.format(no=request.no, names=", ".join(twins)))
    if hidden > 0:
        out(f"AI 요청 알림: 한 푸시에 {MAX_REQUEST_MESSAGES}통까지만 보내 {hidden}건은 마지막 통의 '… 외 {hidden}건' 한 줄로 알렸습니다")
    if failed:
        out(REQUEST_WARNING_LINE)
    if fallbacks:
        out(NOTICE_FALLBACK_WARNING)
    if unreadables:
        out(MERGED_UNREADABLE_WARNING)
    if duplicates:
        out(NOTICE_DUPLICATE_WARNING)
    if lines:
        notify.write_summary(environ, "### AI 요청 텔레그램 알림\n\n" + "\n".join(lines), out)
    return 0


# ---- 응답 이슈(양식) 정의: 양식 파일(.github/ISSUE_TEMPLATE/*.yml)과 이 값이 같아야 한다(검증기 FORM-1) --------------------------------
LABEL_REPLY = "운영자응답"
LABEL_TASK = "운영자요청"
REPLY_TITLE_PREFIX = "[답변] "
TASK_TITLE_PREFIX = "[요청] "
LABEL_STYLES = {LABEL_REPLY: ("1d76db", "운영자가 AI 의 요청에 답한 이슈(양식 [답변])"),
                LABEL_TASK: ("5319e7", "운영자가 AI 에게 맡긴 새 일(양식 [요청])")}
ACK_MARK = "<!-- ack:v1 -->"            # 접수 코멘트의 맨 앞 표지(멱등 검사). 사람이 같은 글을 써도 작성자가 봇이어야 인정한다
BOT_LOGIN = "github-actions[bot]"
# (필드 id, 이슈 본문의 항목 제목) — 이슈 양식이 만드는 `### 제목` 과 글자 그대로 같아야 한다
REPLY_FIELDS = (("request_id", "요청 번호"), ("answer", "답변"), ("choice", "선택"), ("memo", "메모"))
REPLY_REQUIRED = ("request_id", "answer")
REPLY_FIELD_TYPES = {"request_id": "input", "answer": "dropdown", "choice": "input", "memo": "textarea"}
FORM_NOTICE = "비밀번호·토큰·키 값은 절대 쓰지 마세요"       # 두 양식 맨 위 안내 글에 있어야 하는 문장(검증기 FORM-1)
# 답 선택지: (짧은 말, 양식 드롭다운에 보이는 전체 문구). 첫째는 가장 안전한 `보류` 이고 양식이 그것을 미리 선택해 둔다(`default: 0`) — 필수 드롭다운이 첫 선택지를 미리 보여 주더라도
# 요청 번호만 쓰고 올린 이슈가 `승인` 이 되지 않게(독립 검증 N-3). 승인 규칙의 문장은 docs/SECURITY_GUARDRAILS.md G-S9.
ANSWER_OPTIONS = (("보류", "보류 — 나중에 다시 물어 주세요"), ("거절", "거절 — 하지 마세요"), ("승인", "승인 — 제안한 대로 진행해 주세요"),
                  ("했어요", "했어요 — 제가 직접 처리했습니다"), ("문제", "문제 — 아래 메모를 보세요"))
ANSWER_DEFAULT_INDEX = 0
ANSWER_DIRECT_NOTICE = "올리기 전에 반드시 직접 고르세요"   # `[답변]` 양식 맨 위 안내 글에 있어야 하는 문장(검증기 FORM-1)
REPLY_FORM_NAME = "AI 요청에 답하기(결정·확인) (이전 R 번호용)"      # 옛 `[답변]` 양식의 메뉴 이름 — 새 알림은 새 양식만 안내한다(TG-STD). 옛 R 번호 요청을 위해 한동안 함께 둔다
# 새 `[답변]` 양식 `ai-answer.yml`(TG-STD, 운영자 승인 2026-11-06 R-165) — 휴대폰에서 3칸으로 답한다: `대상번호: 001` / `선택: ②` / `내용: …`. 같은 제목 머리 `[답변] `·같은 라벨 `운영자응답` 이라 AI 의 읽기 절차가 그대로 동작한다.
# 대상번호만 필수다. 대상번호만 올린 답은 '확인함'이고 **승인이 아니다** — 선택 칸은 `선택 안 함` 이 미리 선택돼 있고(안전값), 승인은 소유자 계정이 이 양식으로 올리고 대상번호가 AI 가 보낸
# 확인 요청 번호와 같고 선택이 그 요청 파일의 `approve` 보기와 같을 때만 그 요청 파일에 적힌 항목에 한해 인정된다(docs/SECURITY_GUARDRAILS.md G-S9).
ANSWER_FORM_NAME = "AI 확인 요청에 답하기(대상번호)"
ANSWER_FIELDS = (("target", "대상번호"), ("choice", "선택"), ("memo", "내용"))
ANSWER_REQUIRED = ("target",)
ANSWER_FIELD_TYPES = {"target": "input", "choice": "dropdown", "memo": "textarea"}
CHOICE_NONE = "선택 안 함"
CHOICE_OPTIONS = (CHOICE_NONE, *notify.CIRCLED_DIGITS)             # 선택 드롭다운의 선택지(양식과 글자 그대로 같아야 한다) — 첫째(`선택 안 함`)가 미리 선택된다
CHOICE_DEFAULT_INDEX = 0
TARGET_EXAMPLE = "001"                                            # 양식 `대상번호` 칸의 예시(placeholder)·설명의 번호(검증기 FORM-1)
TARGET_NOTICE = f"텔레그램 확인 요청 맨 위의 `{TARGET_EXAMPLE}` 같은 숫자"      # 새 양식 맨 위 안내 글에 있어야 하는 문구(검증기 FORM-1)
ANSWER_NOT_APPROVAL_NOTICE = "`선택 안 함` 이나 대상번호만 올린 답은 승인이 아닙니다"   # 새 양식 맨 위 안내 글에 있어야 하는 문장(검증기 FORM-1)
_CHOICE_SYMBOLS = {**{symbol: index + 1 for index, symbol in enumerate(notify.CIRCLED_DIGITS)},
                   **{chr(0x2776 + index): index + 1 for index in range(notify.OPTIONS_MAX)}}     # ①~⑤ 와 ❶~❺ — 원문자는 같은 숫자로 읽는다
# 대상번호·선택을 읽다 틀렸을 때 폰·코멘트에 쓰는 고정 문장(이슈 글을 되풀이하지 않는다)
TARGET_PROBLEMS = {
    "empty": "`대상번호`가 필요합니다(텔레그램 확인 요청 맨 위의 숫자 3자리, 예: 001)",
    "short": "`대상번호`는 숫자 3자리로 써 주세요(예: 001)",
    "two": "`대상번호`에는 번호를 하나만 쓸 수 있습니다(번호 하나당 이슈 하나)",
    "type": "`대상번호`에는 숫자만인 확인 요청 번호를 써 주세요(P·M 으로 시작하는 번호는 답하는 번호가 아닙니다)",
    "format": "`대상번호` 모양이 맞지 않습니다(알림에 적힌 번호 그대로 숫자만 — 세 자리 예: 001, 1000번부터는 네 자리. 앞에 0 을 더 붙이지 마세요)",
}
FOREIGN_LABELS_PROBLEM = "새 양식에 없는 항목({labels})이 있습니다"
MIXED_FORMS_PROBLEM = "두 양식의 항목(`요청 번호`와 `대상번호`)이 섞여 있습니다"
# `[요청]` 양식(새 일 맡기기)은 T3 승인이 아니다(독립 검증 B-1): 번호 없는 새 일 요청이라 논의·준비·T1·T2 범위의 진행만 정한다. T3 가 필요하면 AI 가 번호 있는 `decision` 요청(R-번호)으로 다시 묻는다.
# 필드 id(`approval`)와 Submission.approval_yes 는 그대로 두고 뜻만 '진행 범위'다: no = 논의·준비까지만, yes = 구현·시험까지(T1·T2).
TASK_FIELDS = (("what", "해 주었으면 하는 일"), ("done", "끝났다고 볼 기준"), ("urgency", "긴급도"), ("approval", "진행 범위"))
TASK_REQUIRED = ("what", "approval")
TASK_FIELD_TYPES = {"what": "textarea", "done": "textarea", "urgency": "dropdown", "approval": "dropdown"}
TASK_URGENCY_OPTIONS = ("보통", "급함", "천천히")
TASK_APPROVAL_OPTIONS = (("no", "논의·준비까지만"), ("yes", "구현·시험까지 진행(T1·T2) — T3 는 따로 번호 있는 요청으로 묻습니다"))
TASK_DEFAULT_INDEX = 0                                   # `urgency`·`approval` 모두 첫 선택지(보통·논의·준비까지만)가 미리 선택된다
TASK_FORM_NOT_T3 = "이 양식은 T3 승인이 아닙니다"          # `[요청]` 양식 맨 위 안내 글에 있어야 하는 문장(검증기 FORM-1)
# 요청 번호 표기(2026-11-04 운영자 요청, 이슈 #110 메모): 보이는 글에는 `r001`(소문자 r + 숫자 세 자리, 하이픈 없음)로 적는다. 안쪽 기록(파일 이름·앞머리 id·로그)은 정본 `R-001` 그대로.
REQUEST_ID_EXAMPLE = notify.display_id("R-001")                                       # 양식·안내의 예시 번호 `r001`(검증기 FORM-1 이 양식의 placeholder·안내와 대조한다)
REQUEST_ID_NOTICE = f"텔레그램 메시지 맨 위의 `{REQUEST_ID_EXAMPLE}` 같은 번호"        # `[답변]` 양식 맨 위 안내 글에 있어야 하는 문구(검증기 FORM-1)
TASK_FORM_NUMBERED_ASK = f"번호 있는 `결정 부탁`(`{REQUEST_ID_EXAMPLE}` 같은 번호)으로 따로 묻고"      # `[요청]` 양식 안내 글·접수 코멘트·사용법이 같은 문구로 말한다(검증기 FORM-1·문서 시험)
CHOICE_RE = re.compile(r"[A-Za-z0-9가-힣]{1,3}")
_NO_RESPONSE = ("_no response_", "no response")
MAX_EVENT_BYTES = 2_000_000

# kind: reply(옛 `[답변]`) | task(`[요청]`) | answer(새 `[답변]` 양식 — target 은 확인 요청 번호 `003` 또는 옛 요청 번호 `R-149`, choice_no 는 선택 기호 1~5·없으면 0, answer·choice 는 비어 있다 — 새 양식은 승인 낱말이 없다)
Submission = namedtuple("Submission", "kind request_id answer choice choice_invalid memo_chars urgency approval_yes target choice_no", defaults=("", 0))
Refusal = namedtuple("Refusal", "code problems")
# 거절 사유: no_owner 저장소 소유자를 모름 / not_owner 작성자가 소유자가 아님 / not_owner_association 작성자 권한이 OWNER 가 아님 / not_form 제목이 양식 이슈가 아님 / bad_shape 양식 모양이 다름
REFUSAL_LINES = {
    "no_owner": "접수하지 않음: 저장소 소유자를 알 수 없습니다",
    "not_owner": "접수하지 않음: 저장소 소유자 계정이 올린 이슈가 아닙니다(코멘트·라벨·텔레그램 없음)",
    "not_owner_association": "접수하지 않음: 작성자 권한이 소유자(OWNER)가 아닙니다(코멘트·라벨·텔레그램 없음)",
    "not_form": "접수하지 않음: 제목이 [답변]·[요청] 양식 이슈가 아닙니다",
}
_LOGIN_RE = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})")
_REPO_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}/(?!\.{1,2}$)[A-Za-z0-9._-]{1,100}")


def parse_sections(body, labels):
    """이슈 양식이 만든 본문(`### 항목 제목` 아래에 값)에서 labels(허용한 항목 제목)만 경계로 인정해 {제목: 값}과 두 번 나온 제목 목록을 돌려준다.
    메모 칸 안에 `### 요청 번호` 같은 줄을 심어 값을 바꾸려는 시도는 '두 번 나온 제목'이 되어 거절된다. 빈 선택 항목(`_No response_`)은 빈 문자열이다."""
    sections, duplicates, current = {}, [], None
    for line in str(body or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        found = re.fullmatch(r"###[ \t]+(.+?)[ \t]*", line)
        if found and found.group(1) in labels:
            label = found.group(1)
            if label in sections:
                duplicates.append(label)
                current = None
            else:
                sections[label] = []
                current = label
            continue
        if current is not None:
            sections[current].append(line)
    values = {}
    for label, buf in sections.items():
        value = "\n".join(buf).strip()
        values[label] = "" if value.lower() in _NO_RESPONSE else value
    return values, sorted(set(duplicates))


def _label_problems(values, duplicates, fields, required):
    problems = [f"`{label}` 항목이 두 번 나옵니다" for label in duplicates]
    for field_id, label in fields:
        if field_id in required and label not in values:
            problems.append(f"`{label}` 항목이 없습니다")
    return problems


REQUEST_INPUT_RE = re.compile(r"[rR][ -]?([0-9]{3})")       # 운영자가 쓸 수 있는 꼴: r090·R090·r-090·R-090·r 090(공백 한 칸) — 숫자는 ASCII 세 자리뿐


def normalize_request_id(raw):
    """운영자가 양식에 쓴 요청 번호를 정본 `R-001` 꼴로 맞춘다 — 앞뒤 공백을 떼고, `r001`·`R001`·`r-001`·`R-001`·`r 001`(공백 한 칸) 꼴 전체가 맞을 때만 바꾼다(2026-11-04 운영자 요청, 이슈 #110 메모 '요청번호 작성 방법 수정 / r090 형태로 변경 - 삭제' / 2026-10-28 운영자의 첫 응답이 `r-002` 로 올라와 거절된 일이 있었다). 그 밖의 모양(전각 `ｒ`·다른 하이픈·자리 수 틀림·그 밖의 안쪽 공백·탭·줄 바꿈·보이지 않는 문자·`r-001 메모` 등)은
    그대로 두어 REQUEST_ID_RE 가 거절한다(옛 동작 유지: `r-` 로 시작하는 나머지 꼴은 앞의 `r` 만 대문자로 바꿔 둔다 — 어차피 거절된다). 정규화는 신뢰 판정(작성자·권한) 뒤에만 일어나고 값은 비교·표시에만 쓴다."""
    text = str(raw).strip()
    found = REQUEST_INPUT_RE.fullmatch(text)
    if found:
        return "R-" + found.group(1)
    if text[:2] == "r-":
        return "R-" + text[2:]
    return text


_TYPED_NO_RE = re.compile(r"[PpMm][ -]?[0-9]{3,4}")                  # 진행 현황·병합 요청 번호 — 답하는 번호가 아니다
_NUMBERISH_RE = re.compile(r"(?:[PpMmRr][ -]?)?[0-9]{1,4}")
_TARGET_SPLIT_RE = re.compile(r"[\s,/·]+")


def parse_target(raw):
    """새 양식 `대상번호` 칸의 값을 읽는다 → (종류, 값, 문제 코드). 종류는 `ask`(확인 요청 번호 `001`, 표준 ASCII 숫자 `001`~`999`·`1000`~`9999` — `0003` 처럼 앞에 0 을 더 붙인 글자는 번호가 아니다) 또는 `request`(옛 요청 번호 — `r149`·`R-149` 등
    normalize_request_id 와 같은 꼴, 값은 정본 `R-149`), 문제가 있으면 종류·값은 빈 글이고 코드는 TARGET_PROBLEMS 의 키다: empty(비었음)·short(1~2자리)·two(번호 둘 이상)·
    type(`P012`·`M007` — 답하는 번호가 아님)·format(그 밖의 모든 모양: 전각·원문자·`#001`·`001.`·`001 메모`·자리 수 초과·`000`·앞 0 이 더 붙은 `0003`). 앞뒤 공백만 봐주고 번호는 ASCII 만 읽는다 —
    잘못 읽어 엉뚱한 요청에 답이 붙는 것을 막는 옛 원칙(`r90`·전각 `ｒ` 거절)과 같다. 신뢰 판정(작성자·권한) 뒤에만 쓴다."""
    text = str(raw or "").strip()
    if not text:
        return "", "", "empty"
    if notify.notice_type(text) == notify.NOTICE_ASK:
        return "ask", text, ""
    if _TYPED_NO_RE.fullmatch(text):
        return "", "", "type"
    found = REQUEST_INPUT_RE.fullmatch(text)
    if found:
        return "request", "R-" + found.group(1), ""
    if re.fullmatch(r"[0-9]{1,2}", text):
        return "", "", "short"
    parts = [part for part in _TARGET_SPLIT_RE.split(text) if part]
    if len(parts) >= 2 and all(_NUMBERISH_RE.fullmatch(part) for part in parts):
        return "", "", "two"
    return "", "", "format"


def parse_choice(raw):
    """새 양식 `선택` 칸의 값을 읽는다 → (선택 기호 번호, 문제 코드). `선택 안 함`·빈칸 = (0, ''), `①`~`⑤`·`❶`~`❺`·`1`~`5`·`2.`·`2)`·`2번` = 같은 번호, 그 밖(전각 숫자·`A`·`두번째`·`6`)은
    (0, 'invalid') — 선택은 버리고 접수는 한다(AI 가 본문을 읽는다). 틀린 선택이 승인 보기와 같아지는 일은 없다."""
    text = str(raw or "").strip()
    if text in ("", CHOICE_NONE):
        return 0, ""
    if text in _CHOICE_SYMBOLS:
        return _CHOICE_SYMBOLS[text], ""
    found = re.fullmatch(r"([1-5])(?:[.)]|번)?", text)
    if found:
        return int(found.group(1)), ""
    return 0, "invalid"


_ANSWER_LABELS = [label for _, label in ANSWER_FIELDS]
_ALL_ANSWER_LABELS = list(dict.fromkeys([*_ANSWER_LABELS, *(label for _, label in REPLY_FIELDS)]))        # 두 양식의 항목 제목 전부(어느 양식인지 가릴 때)


def answer_form_kind(body):
    """`[답변]` 이슈 본문이 어느 양식의 모양인지: `new`(항목 `### 대상번호` 가 있고 `### 요청 번호` 는 없음) · `old`(`### 요청 번호` 만 있음) · `mixed`(둘 다 있음 — 메모 칸에 가짜 제목을 심은 글 포함) ·
    `none`(둘 다 없음). 항목 제목은 양식이 만든 `### 제목` 한 줄만 인정한다(parse_sections)."""
    values, duplicates = parse_sections(body, _ALL_ANSWER_LABELS)
    found = set(values) | set(duplicates)
    has_new, has_old = dict(ANSWER_FIELDS)["target"] in found, dict(REPLY_FIELDS)["request_id"] in found
    return "mixed" if has_new and has_old else "new" if has_new else "old" if has_old else "none"


def _parse_answer(body):
    """새 양식 본문 → Submission(kind `answer`) 또는 Refusal(bad_shape, 고정 문장 목록). 대상번호만 필수. 새 양식에 없는 항목(`답변`·`메모`)이나 두 번 나온 항목은 모양 오류다 —
    내용 칸에 가짜 `### 대상번호`·`### 선택` 같은 줄을 심어 값을 바꾸려는 시도를 거절한다."""
    values, duplicates = parse_sections(body, _ALL_ANSWER_LABELS)
    label_of = dict(ANSWER_FIELDS)
    problems = [f"`{label}` 항목이 두 번 나옵니다" for label in duplicates]
    foreign = [label for label in _ALL_ANSWER_LABELS if label in values and label not in _ANSWER_LABELS]
    if foreign:
        problems.append(FOREIGN_LABELS_PROBLEM.format(labels=", ".join(f"`{label}`" for label in foreign)))
    target_kind, target, target_problem = parse_target(values.get(label_of["target"], ""))
    if target_problem:
        problems.append(TARGET_PROBLEMS[target_problem])
    if problems:
        return Refusal("bad_shape", tuple(problems))
    raw_choice = values.get(label_of["choice"], "")
    choice_no, choice_problem = parse_choice(raw_choice)
    return Submission("answer", target if target_kind == "request" else "", "", "", bool(choice_problem), len(values.get(label_of["memo"], "")), "", False, target, choice_no)


def parse_reply(title, body, login, association, owner):
    """응답·요청 이슈 하나를 판정한다 → Submission(접수할 것) 또는 Refusal(사유 코드, 양식 문제 목록).

    신뢰 판정(먼저): 작성자 login 이 저장소 소유자와 같고(ASCII 영문 대소문자만 무시 — login 이 GitHub 계정 이름 모양(`_LOGIN_RE`)이 아니면 비교하기 전에 거절) author_association 이 정확히 `OWNER` 여야
    한다 — 둘 다 이벤트 JSON 의 값이고 이슈 본문·제목의 글은 보지 않는다. 유니코드 접기(`casefold`)는 쓰지 않는다: `ſhine88pc`(U+017F) 같은 글자가 `shine88pc` 로 접혀 통과하는 일이 없게(독립 검증 N-6).
    그다음 제목이 `[답변]`(요청에 답하기)·`[요청]`(새 일 맡기기)로 시작해야 하고, 본문의 항목 제목(양식이 만든 `### …`)으로 값을 읽어 **검증된 값만** 담는다:
    요청 번호는 정본 `R-` 와 숫자 세 자리이고 `r001`·`R001`·`r-001`·`r 001` 같은 운영자 표기도 정본으로 읽는다(normalize_request_id), 답은 양식의 선택지 전체 문구와 글자 그대로 같아야 하고(짧은 말로 바꿔 담는다), 선택은 영문·숫자·한글 1~3자(아니면 표시하지 않음 표시), 메모는 글자 수만 담는다.
    `[요청]` 은 접수만 한다 — T3 승인이 아니다(독립 검증 B-1): 진행 범위(논의·준비까지 / 구현·시험까지)만 읽는다.
    `[답변]` 은 본문 항목 제목으로 두 양식을 가른다(answer_form_kind): `### 대상번호` 가 있으면 새 양식(대상번호·선택·내용 — Submission kind `answer`, 승인 낱말이 없다), `### 요청 번호` 가 있으면 옛 양식(위 설명 그대로),
    둘 다 있으면 모양 오류, 둘 다 없으면 옛 분기가 옛 문구로 거절한다."""
    owner_name = str(owner or "")
    if not _LOGIN_RE.fullmatch(owner_name):
        return Refusal("no_owner", ())
    if not (isinstance(login, str) and _LOGIN_RE.fullmatch(login)) or login.lower() != owner_name.lower():
        return Refusal("not_owner", ())
    if association != "OWNER":
        return Refusal("not_owner_association", ())
    head = str(title or "")
    if head.startswith(REPLY_TITLE_PREFIX.rstrip()):
        form = answer_form_kind(body)                   # 본문 제목으로 어느 양식인지 가린다: `### 대상번호` = 새 양식, `### 요청 번호` = 옛 양식, 둘 다 있으면 모양 오류, 둘 다 없으면 옛 분기가 옛 문구로 거절
        if form == "new":
            return _parse_answer(body)
        if form == "mixed":
            return Refusal("bad_shape", (MIXED_FORMS_PROBLEM,))
        values, duplicates = parse_sections(body, [label for _, label in REPLY_FIELDS])
        label_of = dict(REPLY_FIELDS)
        problems = _label_problems(values, duplicates, REPLY_FIELDS, REPLY_REQUIRED)
        request_id = normalize_request_id(values.get(label_of["request_id"], ""))
        if label_of["request_id"] in values and not notify.REQUEST_ID_RE.fullmatch(request_id):
            problems.append("`요청 번호` 값이 `r001` 처럼 `r` 와 숫자 세 자리가 아닙니다")
        word = next((short for short, full in ANSWER_OPTIONS if full == values.get(label_of["answer"], "")), "")
        if label_of["answer"] in values and not word:
            problems.append("`답변` 값이 양식의 선택지가 아닙니다")
        if problems:
            return Refusal("bad_shape", tuple(problems))
        raw_choice = values.get(label_of["choice"], "")
        choice = raw_choice.strip().rstrip(".)").strip()
        invalid = bool(raw_choice) and CHOICE_RE.fullmatch(choice) is None
        return Submission("reply", request_id, word, "" if invalid else choice, invalid, len(values.get(label_of["memo"], "")), "", False)
    if head.startswith(TASK_TITLE_PREFIX.rstrip()):
        values, duplicates = parse_sections(body, [label for _, label in TASK_FIELDS])
        label_of = dict(TASK_FIELDS)
        problems = _label_problems(values, duplicates, TASK_FIELDS, TASK_REQUIRED)
        if label_of["what"] in values and not values[label_of["what"]]:
            problems.append("`해 주었으면 하는 일` 이 비어 있습니다")
        approval = next((key for key, full in TASK_APPROVAL_OPTIONS if full == values.get(label_of["approval"], "")), "")
        if label_of["approval"] in values and not approval:
            problems.append("`진행 범위` 값이 양식의 선택지가 아닙니다")
        urgency = values.get(label_of["urgency"], "") or TASK_URGENCY_OPTIONS[0]
        if urgency not in TASK_URGENCY_OPTIONS:
            problems.append("`긴급도` 값이 양식의 선택지가 아닙니다")
        if problems:
            return Refusal("bad_shape", tuple(problems))
        return Submission("task", "", "", "", False, len(values.get(label_of["what"], "")), urgency, approval == "yes")
    return Refusal("not_form", ())


# ---- 접수 코멘트 ------------------------------------------------------------------------------------
ACK_TAIL = ("AI 세션이 이 이슈를 감시해 이어서 진행하며 결과는 텔레그램으로 알립니다. (AI 가 켜져 있지 않으면 다음 세션에서 처리됩니다)\n"
            "비밀번호·토큰·키 값은 이 이슈에 쓰지 마세요(이미 썼다면 바로 폐기·재발급하세요).")


def _compose(head, notes):
    """접수 코멘트: 맨 앞 표지, 한 줄 요약, 안내 꼬리, (있으면) 덧붙임 목록."""
    return f"{ACK_MARK}\n{head}\n\n{ACK_TAIL}" + ("\n\n" + "\n".join(notes) if notes else "")


def reply_comment(sub, known_request):
    """`[답변]` 접수 코멘트(마크다운). 값은 모두 검증을 통과한 것이다 — 요청 번호 모양·양식의 답 선택지·선택 글자(영문·숫자·한글 1~3자)·메모 글자 수.
    known_request 가 거짓이면 중립 사실 진술 한 줄을 더한다 — 요청 파일은 병합 전 작업 브랜치에 있는 것이 보통이라 이 저장소 기본 브랜치에서 안 보이는 것이 정상일 수 있고,
    그래서 '번호를 다시 확인하세요' 같은 불안을 주는 말은 쓰지 않는다(독립 검증 N-2). 접수는 늘 한다."""
    shown = notify.display_id(sub.request_id)                       # 운영자에게는 `r001` 꼴(안쪽 기록은 정본 R-001)
    head = f"접수했습니다 — 요청 **{shown}** · 답: **{sub.answer}**" + (f" · 선택: **{sub.choice}**" if sub.choice else "") + "."
    notes = []
    if sub.memo_chars:
        notes.append(f"- 메모: 있음({sub.memo_chars}자) — AI 가 이슈 본문에서 읽습니다(여기에는 되풀이하지 않습니다).")
    if sub.choice_invalid:
        notes.append("- 선택 칸의 값이 형식(영문·숫자·한글 1~3자)에 맞지 않아 표시하지 않았습니다. AI 가 이슈 본문에서 읽습니다.")
    if not known_request:
        notes.append(f"- 요청 번호 {shown} 은 AI 가 자기가 보낸 요청과 대조해 처리합니다"
                     "(요청 파일이 병합 전 브랜치에만 있으면 이 저장소 기본 브랜치에서는 보이지 않으며 정상일 수 있습니다).")
    return _compose(head, notes)


def task_comment(sub):
    """`[요청]` 접수 코멘트. 이슈 본문의 글은 되풀이하지 않는다(긴급도·진행 범위는 양식의 선택지 값). `[요청]` 은 T3 승인이 아니라고 분명히 적는다(독립 검증 B-1)."""
    head = (f"접수했습니다 — 새 일 요청 · 긴급도: **{sub.urgency}** · 진행 범위: "
            + ("**구현까지(T3 제외)**" if sub.approval_yes else "**논의·준비까지만**") + ".")
    notes = [f"- 이 양식은 T3 승인이 아닙니다. T3(광고 표면·시크릿·계정·삭제·`mode` 변경·새 플랫폼 등)가 필요하면 AI 가 {TASK_FORM_NUMBERED_ASK}, "
             "그때 `[답변]` 양식으로 답해 주세요."] if sub.approval_yes else []
    return _compose(head, notes)


OLD_TARGET_NOTE = (f"- 옛 R 번호 요청에는 새 양식으로 승인할 수 없습니다 — 이 답은 접수만 합니다. 승인은 `{REPLY_FORM_NAME}` 양식으로 올려 주세요.")
NUMBER_CHECK_NOTE = "- 이 번호가 AI 가 보낸 요청의 번호와 맞는지는 이 접수가 알 수 없습니다(접수 워크플로는 요청 파일이 없는 기본 브랜치만 봅니다) — AI 가 이슈를 읽을 때 대조하고, 번호가 틀렸으면 폰으로 알립니다."
SHAPE_TAIL = (f"이 이슈는 닫고, Issues → New issue 에서 **{ANSWER_FORM_NAME}**(옛 R 번호 요청이면 **{REPLY_FORM_NAME}**, 새 일 맡기기면 **AI 에게 새 일 맡기기(작업 요청)**) "
              "양식을 골라 다시 올려 주세요. 빈 이슈나 양식 밖의 글은 승인으로 보지 않습니다.")


def answer_comment(sub, replaced=None):
    """새 양식 `[답변]`(대상번호) 접수 코멘트(마크다운). 값은 모두 검증을 통과한 것이다 — 번호 모양·선택 기호(①~⑤)·이슈 번호·내용 글자 수. 내용 글은 되풀이하지 않는다.
    선택이 없으면 '확인함(승인 아님)'이고, replaced(같은 번호에 앞서 올린 답의 이슈 번호)가 있으면 가장 나중 답이 이긴다는 말을 덧붙인다. 옛 R 번호(`R-149`)면 새 양식으로 승인할 수 없다고 적는다."""
    old = sub.target.startswith("R-")
    shown = notify.display_id(sub.target) if old else sub.target                 # 옛 번호는 운영자에게 `r149` 꼴
    head = (f"접수했습니다 — 요청 **{shown}**(이전 R 번호)" if old else f"접수했습니다 — 확인 요청 **{shown}**")
    head += (f" · 선택: **{notify.CIRCLED_DIGITS[sub.choice_no - 1]}**" if sub.choice_no else " · 확인함(승인 아님)")
    head += (f" · 내용: 있음({sub.memo_chars}자)" if sub.memo_chars else "") + "."
    notes = []
    if replaced is not None:
        notes.append(f"- 이 번호에 앞서 올린 답(이슈 #{replaced})이 있어 이 답이 그것을 대체합니다 — 가장 나중 답이 이깁니다(앞 이슈는 지우지 않습니다).")
    if sub.memo_chars:
        notes.append("- 내용 글은 AI 가 이슈 본문에서 읽습니다(여기에는 되풀이하지 않습니다).")
    if sub.choice_invalid:
        notes.append(f"- 선택 칸의 값이 양식의 선택지(`{CHOICE_NONE}`·①~⑤)가 아니라 표시하지 않았습니다. AI 가 이슈 본문에서 읽습니다.")
    if old:
        notes.append(OLD_TARGET_NOTE)
    elif sub.choice_no:
        notes.append("- 승인은 그 확인 요청에 승인 보기로 적힌 번호를 직접 고른 경우에만 인정됩니다. AI 가 요청 파일과 대조해 확인합니다.")
    else:
        notes.append("- 대상번호만 올린 답은 '확인함' 일 뿐 승인이 아닙니다.")
    if not sub.choice_no:
        notes.append(NUMBER_CHECK_NOTE)
    return _compose(head, notes)


def shape_comment(problems):
    """양식 모양이 달라 처리하지 못했다는 코멘트. 문제 목록은 코드가 정한 고정 문구뿐이다(이슈 글을 되풀이하지 않는다). 새 양식(대상번호)을 먼저 안내한다."""
    return f"{ACK_MARK}\n양식 모양이 달라 처리하지 못했습니다 — " + "; ".join(problems) + ".\n\n" + SHAPE_TAIL


# ---- GitHub REST(표준 라이브러리) -----------------------------------------------------------------------
API_ROOT = "https://api.github.com"
API_TIMEOUT = 20
MAX_API_BYTES = 2_000_000
RETRY_WAIT = 2
_TRANSIENT = {429, 500, 502, 503, 504}


class GitHubError(Exception):
    """GitHub REST 호출 실패. 문구에는 토큰·요청 객체가 없고 HTTP 상태·클래스 이름·GitHub 가 준 짧은 설명(가린 것)뿐이다. status 는 응답이 없으면 None."""

    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


class GitHub:
    """저장소 범위 GitHub REST 클라이언트. repo 는 `소유자/이름`, token 은 GITHUB_TOKEN(권한 issues: write). opener(request, timeout=…)·sleep(초)은 시험이 가짜로 바꿔 끼운다."""

    def __init__(self, repo, token, opener=None, sleep=time.sleep):
        self.repo, self._token, self._open, self._sleep = str(repo or "").strip(), str(token or "").strip(), opener or urllib.request.urlopen, sleep
        self.calls = 0

    def _scrub(self, text):
        out = mask(text)
        return out.replace(self._token, "***") if len(self._token) >= 6 else out

    def _detail(self, exc):
        try:
            data = json.loads(exc.read(4096).decode("utf-8", "replace"))
            return one_line(self._scrub(str(data.get("message") or "")), 120) if isinstance(data, dict) else ""
        except (OSError, ValueError, AttributeError, RecursionError):
            return ""

    def request(self, method, path, payload=None, params=None, retry=True):
        """한 번 부르고 JSON 을 돌려준다(본문이 없으면 None). 일시 오류(429·5xx·연결 오류)는 retry 일 때 한 번 다시 시도한다. 실패는 GitHubError."""
        if not _REPO_RE.fullmatch(self.repo):
            raise GitHubError("저장소 이름(GITHUB_REPOSITORY)이 `소유자/이름` 모양이 아닙니다")
        url = f"{API_ROOT}/repos/{self.repo}{path}" + (("?" + urllib.parse.urlencode(params)) if params else "")
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "chanceblog-operator-loop",
                   "Authorization": f"Bearer {self._token}"}
        data = None
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        attempts = 2 if retry else 1
        for attempt in range(attempts):
            self.calls += 1
            try:
                with self._open(urllib.request.Request(url, data=data, method=method, headers=headers), timeout=API_TIMEOUT) as resp:
                    raw = resp.read(MAX_API_BYTES + 1)
            except urllib.error.HTTPError as exc:
                status, detail = exc.code, self._detail(exc)
                limited = status == 403 and "rate limit" in detail.lower()
                if (status in _TRANSIENT or limited) and attempt + 1 < attempts:
                    self._sleep(RETRY_WAIT)
                    continue
                raise GitHubError(f"HTTP {status}" + (f": {detail}" if detail else ""), status) from None
            except (urllib.error.URLError, http.client.HTTPException, OSError, UnicodeDecodeError) as exc:
                if attempt + 1 < attempts:
                    self._sleep(RETRY_WAIT)
                    continue
                raise GitHubError(f"연결 오류({type(exc).__name__})") from None
            if len(raw) > MAX_API_BYTES:
                raise GitHubError("응답이 너무 큽니다")
            if not raw:
                return None
            try:
                return json.loads(raw.decode("utf-8"))
            except (ValueError, RecursionError):
                raise GitHubError("응답이 JSON 이 아닙니다") from None
        raise GitHubError("재시도 초과")


def has_ack(api, number):
    """이 이슈에 접수 코멘트가 이미 있는가: 맨 앞 표지가 ACK_MARK 이고 **작성자가 봇**(github-actions[bot])인 코멘트가 있을 때만 있다고 본다(낯선 사람이 표지를 흉내 내 접수를 막지 못하게).
    코멘트는 첫 100개만 본다."""
    items = api.request("GET", f"/issues/{number}/comments", params={"per_page": 100})
    for item in items if isinstance(items, list) else ():
        user = item.get("user") if isinstance(item, dict) else None
        if isinstance(user, dict) and user.get("login") == BOT_LOGIN and str(item.get("body") or "").startswith(ACK_MARK):
            return True
    return False


def post_ack(api, number, text, sleep=time.sleep):
    """접수 코멘트를 한 번만 단다(멱등): 이미 있으면 달지 않고 False, 달았으면 True. 만들어졌는지 모호한 실패(응답 유실·5xx·연결 오류)는 같은 요청을 그대로 되풀이하지 않고
    표지를 다시 찾아 있으면 달린 것으로 본다(코멘트가 둘이 되지 않게). 읽기 자체가 실패하면 달린 코멘트가 없다고 보고 단다(중복이 접수 누락보다 낫다)."""
    try:
        if has_ack(api, number):
            return False
    except GitHubError:
        pass
    try:
        api.request("POST", f"/issues/{number}/comments", payload={"body": text}, retry=False)
        return True
    except GitHubError as exc:
        if isinstance(exc.status, int) and 400 <= exc.status < 500 and exc.status != 429:
            raise                                   # 거절됨 — 만들어지지 않았다
        sleep(RETRY_WAIT)
        try:
            if has_ack(api, number):
                return True                         # 응답만 잃었고 코멘트는 만들어졌다
        except GitHubError:
            pass
        raise


def ensure_label(api, name):
    """라벨이 없으면 만든다(있으면 422 — 그대로 둔다)."""
    color, description = LABEL_STYLES[name]
    try:
        api.request("POST", "/labels", payload={"name": name, "color": color, "description": description})
    except GitHubError as exc:
        if exc.status != 422:
            raise


EARLIER_PER_PAGE = 100          # 앞서 올라온 답을 찾을 때 읽는 이슈 수(최근 것부터 한 쪽)


def earlier_answer(api, number, target, owner, out):
    """같은 대상번호에 **앞서** 올라온 소유자의 새 양식 답 중 가장 나중 이슈 번호(없으면 None) — 가장 나중 답이 이기고 앞 답은 지우지 않는다(접수 코멘트·폰이 '대체합니다' 로 알린다).
    라벨 `운영자응답` 이슈를 `creator=<소유자>` 로 읽고(최근 100건), 각 이슈를 접수 때와 같은 parse_reply 로 다시 판정한다 — 작성자 login·`author_association` 이 소유자가 아니거나 모양이 틀린 이슈·
    이 이슈 자신과 그보다 뒤 번호·PR 은 세지 않는다. 읽기에 실패하면 None 으로 두고 접수는 계속한다(로그 한 줄)."""
    try:
        items = api.request("GET", "/issues", params={"creator": owner, "labels": LABEL_REPLY, "state": "all", "sort": "created", "direction": "desc",
                                                      "per_page": EARLIER_PER_PAGE})
    except GitHubError as exc:
        out(f"운영자 응답 접수: 앞서 올라온 답을 확인하지 못했습니다 — {exc}")
        return None
    best = None
    for item in items if isinstance(items, list) else ():
        if not isinstance(item, dict) or "pull_request" in item:
            continue
        earlier, user = item.get("number"), item.get("user")
        if isinstance(earlier, bool) or not isinstance(earlier, int) or earlier >= number:
            continue
        found = parse_reply(item.get("title"), item.get("body"), user.get("login") if isinstance(user, dict) else None, item.get("author_association"), owner)
        if isinstance(found, Submission) and found.kind == "answer" and found.target == target and (best is None or earlier > best):
            best = earlier
    return best


# ---- 응답 접수(ack) ------------------------------------------------------------------------------------
ACK_WARNING ="::warning::운영자 응답 접수 중 일부를 하지 못했습니다. 이유는 바로 앞 로그 줄에 있습니다(이슈는 그대로이고 AI 가 읽습니다)."


def read_event(environ):
    """GITHUB_EVENT_PATH 의 이벤트 JSON 을 읽는다(러너가 주는 파일). 없거나 크거나 JSON 이 아니면 None."""
    path = str(environ.get("GITHUB_EVENT_PATH") or "")
    if not path:
        return None
    try:
        with open(path, "rb") as fh:
            raw = fh.read(MAX_EVENT_BYTES + 1)
        data = json.loads(raw.decode("utf-8")) if len(raw) <= MAX_EVENT_BYTES else None
    except (OSError, ValueError, RecursionError):
        return None
    return data if isinstance(data, dict) else None


def known_request_ids(root):
    """저장소(체크아웃한 기본 브랜치)의 `인수인계/요청함/` 에 있는 요청 번호 집합(경고 정보로만 쓴다)."""
    folder = Path(root) / REQUEST_DIR
    try:
        names = os.listdir(folder)
    except OSError:
        return set()
    return {"R-" + match.group(1) for name, match in ((name, REQUEST_NAME_RE.fullmatch(name)) for name in names) if match and (folder / name).is_file()}


def _owner_of(environ):
    owner = str(environ.get("GITHUB_REPOSITORY_OWNER") or "").strip()
    return owner or str(environ.get("GITHUB_REPOSITORY") or "").split("/")[0].strip()


def run_ack(environ, notifier, root, out, api=None, sleep=time.sleep):
    """열린 이슈 한 개를 접수한다. 종료 코드는 항상 0. 소유자가 아니면 아무것도 하지 않는다(로그 한 줄). 순서: 판정 → 라벨 → 코멘트(한 번) → 텔레그램(이번에 코멘트를 새로 단 때만)."""
    event = read_event(environ)
    if event is None or environ.get("GITHUB_EVENT_NAME") != "issues" or event.get("action") != "opened":
        out("운영자 응답 접수: 이 실행은 새로 열린 이슈 이벤트가 아니어서 아무것도 하지 않습니다")
        return 0
    issue = event.get("issue")
    issue = issue if isinstance(issue, dict) else {}
    number = issue.get("number")
    user = issue.get("user") if isinstance(issue.get("user"), dict) else {}
    result = parse_reply(issue.get("title"), issue.get("body"), user.get("login"), issue.get("author_association"), _owner_of(environ))
    if isinstance(result, Refusal) and result.code in REFUSAL_LINES:
        out(f"운영자 응답 접수: {REFUSAL_LINES[result.code]}")
        return 0
    if isinstance(number, bool) or not isinstance(number, int) or number < 1:
        out("운영자 응답 접수: 이슈 번호를 읽지 못해 아무것도 하지 않습니다")
        return 0
    token = str(environ.get("GITHUB_TOKEN") or "").strip()
    if not token:
        out("운영자 응답 접수: GITHUB_TOKEN 이 없어 라벨·코멘트·알림을 하지 않습니다(읽기 전용)")
        return 0
    api = api or GitHub(environ.get("GITHUB_REPOSITORY"), token, sleep=sleep)
    is_reply = str(issue.get("title") or "").startswith(REPLY_TITLE_PREFIX.rstrip())
    form = answer_form_kind(issue.get("body")) if is_reply else ""        # new | old | mixed | none — 새 양식(대상번호)의 모양 오류만 폰으로도 회신한다(옛 양식·번호 없는 글·`[요청]` 은 옛 동작 그대로)
    new_form = form in ("new", "mixed")
    failures = 0
    label = LABEL_REPLY if is_reply else LABEL_TASK
    present = {str(item.get("name")) for item in issue.get("labels") or () if isinstance(item, dict)}
    if label not in present:
        try:
            ensure_label(api, label)
            api.request("POST", f"/issues/{number}/labels", payload={"labels": [label]})
            out(f"운영자 응답 접수: 이슈 #{number} 에 라벨 {label} 을 붙였습니다")
        except GitHubError as exc:
            failures += 1
            out(f"운영자 응답 접수: 라벨을 붙이지 못했습니다 — {exc}")
    replaced = None
    if isinstance(result, Refusal):
        text, summary = shape_comment(result.problems), f"- 이슈 #{number}: 양식 모양이 달라 처리하지 못했다는 코멘트를 달았습니다"
    elif result.kind == "reply":
        text = reply_comment(result, result.request_id in known_request_ids(root))
        summary = f"- 이슈 #{number}: 요청 {result.request_id} · 답 {result.answer} 을 접수했습니다"
    elif result.kind == "answer":
        replaced = earlier_answer(api, number, result.target, _owner_of(environ), out)
        text = answer_comment(result, replaced)
        summary = f"- 이슈 #{number}: 대상번호 {result.target} 의 답을 접수했습니다(선택 {result.choice_no or '없음'})" + (f" · 이슈 #{replaced} 을 대체" if replaced else "")
    else:
        text, summary = task_comment(result), f"- 이슈 #{number}: 새 일 요청을 접수했습니다(긴급도 {result.urgency})"
    try:
        posted = post_ack(api, number, text, sleep=sleep)
    except GitHubError as exc:
        out(f"운영자 응답 접수: 접수 코멘트를 달지 못했습니다 — {exc}")
        out(ACK_WARNING)
        return 0
    if not posted:
        out(f"운영자 응답 접수: 이슈 #{number} 에는 접수 코멘트가 이미 있어 다시 달지 않습니다")
        return 0
    out(f"운영자 응답 접수: 이슈 #{number} 에 접수 코멘트를 달았습니다")
    notify.write_summary(environ, "### 운영자 응답 접수\n\n" + summary, out)
    refused = isinstance(result, Refusal)
    if refused and not new_form:
        return 0                                       # 옛 양식·`[요청]` 의 모양 오류는 코멘트만(옛 동작 그대로)
    if not notifier.enabled:
        out(notify.SKIP_LINE)
    else:
        buttons = [("이슈 열기", f"{notify.REPO_URL}/issues/{number}")]
        if refused:                                    # 새 양식 오류도 폰으로(TG-STD) — 소유자 판정을 통과한 이슈에만(위에서 이미 거름), 고정 문장만
            reason = result.problems[0]
            sent = notifier.notify_answer_error(number, reason, buttons=buttons)
        elif result.kind == "reply":
            sent = notifier.notify_reply_received(result.request_id, result.answer, number, choice=result.choice, buttons=buttons)
        elif result.kind == "answer":
            sent = notifier.notify_answer_received(result.target, result.choice_no, number, replaced=replaced, buttons=buttons)
        else:
            sent = notifier.notify_task_received(number, result.urgency, result.approval_yes, buttons=buttons)
        if sent.sent:
            out("운영자 응답 접수: 텔레그램으로 " + ("접수하지 못했다는 회신을 보냈습니다" if refused else "접수를 알렸습니다"))
        else:
            failures += 1
            out(notifier.scrub(f"운영자 응답 접수: 텔레그램 알림을 보내지 못했습니다 — {notify.describe(sent)}"))
    if failures:
        out(ACK_WARNING)
    return 0


# ---- 명령 줄 -------------------------------------------------------------------------------------------
USAGE_ERROR_LINE = "사용법 오류: 이 명령은 requests·ack 만 받습니다(값은 명령 줄이 아니라 환경변수·git·이벤트 파일에서만 읽습니다)"
UNEXPECTED_LINE = "운영자 요청함: 예기치 않은 오류({name}) — 푸시·병합·이슈에는 영향이 없습니다"


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        """argparse 의 기본 오류는 잘못 넘긴 인자를 그대로 메시지에 싣는다 — 실수로 명령 줄에 넘긴 값이 로그에 남지 않게 고정 문장만 낸다."""
        self.print_usage(sys.stderr)
        sys.stderr.write(USAGE_ERROR_LINE + "\n")
        raise SystemExit(2)


def build_parser():
    parser = _Parser(prog="python -m pipeline.operator_loop", description="운영자 요청함(AI 의 요청 알림·응답 이슈 접수)")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("requests", help="push 한 커밋이 새로 더한 요청 파일(인수인계/요청함/)을 텔레그램으로 알린다")
    sub.add_parser("ack", help="새로 열린 응답·요청 이슈(소유자만)를 접수 확인한다(이슈 코멘트·라벨·텔레그램)")
    return parser


def main(argv=None, environ=None, out=print, root=None, runner=subprocess.run, opener=None, sleep=None, clock=None, budget=None, api=None):
    safe_output()
    environ = os.environ if environ is None else environ
    args = build_parser().parse_args(argv)
    notifier = notify.Notifier(environ, opener=opener, sleep=sleep, clock=clock, budget=budget)
    root = Path(root) if root is not None else ROOT
    try:
        if args.command == "requests":
            return run_requests(environ, notifier, root, out, runner=runner)
        return run_ack(environ, notifier, root, out, api=api, sleep=sleep or time.sleep)
    except Exception as exc:  # noqa: BLE001 - 알림·접수는 보조다: 예기치 않은 오류도 클래스 이름만 남기고 끝낸다(예외 문구에 주소·값이 있을 수 있다)
        out(UNEXPECTED_LINE.format(name=type(exc).__name__))
        out("::warning::운영자 요청함 처리 중 예기치 않은 오류가 났습니다. 푸시·병합·이슈에는 영향이 없습니다(코드 버그일 수 있어 AI 에게 알려 주세요).")
        return 0


if __name__ == "__main__":
    sys.exit(main())
