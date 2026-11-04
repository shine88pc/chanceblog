"""텔레그램 수신 — 운영자가 봇에게 보낸 글을 저장소 이슈로 옮긴다('예약 읽기', 표준 라이브러리만, Python 3.10 이상).

배경: 운영자는 휴대폰 텔레그램으로 알림을 받고(pipeline/notify.py), 거꾸로 봇에게 글을 보내 AI 에게 전하고 싶어 한다(이슈 #119, 요청 r103 → 운영자가 이슈 #120 으로
'① 예약 읽기' 를 승인). 웹훅·상시 서버 없이, 저장소의 자동 실행(`[공통] 텔레그램 수신 가져오기`)이 정해진 때마다 봇에 온 새 글을 `getUpdates` 로 읽어
'텔레그램에서 온 글' 이슈로 만든다. AI 는 그 이슈를 공개 REST 로 읽는다(작성자 `github-actions[bot]` + 라벨 `텔레그램수신` + 본문 맨 위 표지 `telegram-inbox:v1` 셋이 모두 있을 때만).
설명서: docs/TELEGRAM_INBOX.md / 규칙: docs/SECURITY_GUARDRAILS.md G-S10(접수일 뿐 승인이 아니다)·G-S9(승인은 소유자 `[답변]` 양식만)·G-C12(토큰 비노출)

원칙
  1. **접수일 뿐 승인이 아니다.** 이 채널은 글을 이슈로 옮기기만 한다. 승인이 필요한 일(광고·사이트·자동 발행 설정·비밀)은 이 글만으로 진행하지 않는다 — 승인은 소유자 계정이
     `[답변]` 양식으로 올린 것만 인정한다(G-S9, 바뀌지 않았다). 글이 `r103 승인 1` 처럼 요청 번호로 시작하면 본문에 '답변 후보' 한 줄을 덧붙이지만 참고용이다.
  2. **허용 조건은 하나다**: `message.chat.type == "private"` 이고 `message.chat.id` 와 `message.from.id` 가 둘 다 `TELEGRAM_CHAT_ID` 와 같을 때만(`from.is_bot` 이 참이면 제외). 다른 사람·그룹·채널 글,
     `edited_message`·콜백, 글이 아닌 것은 이슈를 만들지 않고 남에게는 아무 답도 하지 않는다(스팸 반사 금지).
  3. **받은 글은 데이터다.** 공개 이슈의 인용 블록에 넣기 전에 소독한다(보이지 않는 문자·제어 문자 제거, `@`·`<`·`>`·엔티티 모양의 `&` 무력화, 비밀 모양·토큰·채팅 ID 가리기,
     3,000자 제한 — 비밀 가리기는 소독 뒤에 한 번 더 한다). 표지(`<!-- telegram-inbox:v1 update_id=… -->`)는 코드가 맨 위에 직접 쓰고 원문 속 `<!--` 는 남지 않는다. 원문·응답 JSON 은 로그에 찍지 않는다.
     다른 곳에서 전달된 글(forward_*·via_bot)은 본문에 '운영자가 쓴 글이 아닙니다' 한 줄을 붙이고 '답변 후보' 는 달지 않는다.
  4. **멱등·순서·확인**: 이슈를 만들기 전에 같은 `update_id` 표지가 든 이슈(라벨 `텔레그램수신`, 열림·닫힘, 작성자가 봇인 것만)를 찾아 있으면 건너뛴다. 이슈 만들기가 끝난 글까지만
     `offset`(=마지막+1)을 올려 텔레그램이 확인하게 하고, 실패하면 확인하지 않아 다음 실행이 다시 시도한다. 한 번에 최대 5통, 이슈 사이 1초.
  5. **토큰은 요청 주소의 경로에 들어간다**(https://api.telegram.org/bot<토큰>/getUpdates). 모든 예외를 잡아 분류(종류·HTTP 상태)만 남기고 예외 문구·요청 객체·응답 본문을 어디에도 쓰지 않는다.
     `requests` 를 쓰지 않는다. 글이 비밀 모양이면 `***` 로 가린다. `::add-mask::` 같은 것에 기대지 않는다.
  6. 비밀(`TELEGRAM_BOT_TOKEN`·`TELEGRAM_CHAT_ID`)이 없으면 건너뜀·종료 0. 오류는 구분해 한 줄(원인 안내)만 남긴다: 401·404(토큰)·409(웹훅이 설정됨 — 그대로 둔다, `deleteWebhook` 을 부르지 않는다)는
     종료 1(실행 실패로만 드러남 — 이슈도 텔레그램 알림도 만들지 않는다), 429(`retry_after`)·네트워크·5xx 는 일시 문제라 경고만 남기고 종료 0.

명령 줄: python -m pipeline.telegram_inbox   (인자를 받지 않는다 — 값은 환경변수 GITHUB_TOKEN·GITHUB_REPOSITORY·TELEGRAM_BOT_TOKEN·TELEGRAM_CHAT_ID·GITHUB_STEP_SUMMARY 에서만 읽는다)
  종료 코드: 0 정상(건너뜀·일시 문제 포함) / 1 설정·권한 문제(토큰·웹훅·GitHub 권한) 또는 예기치 않은 오류 / 2 사용법 오류
"""
import argparse
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from collections import namedtuple
from datetime import datetime, timedelta, timezone

from pipeline import notify
from pipeline import operator_loop as loop
from pipeline.console import INVISIBLE_RE, clean_secret, md_cell, safe_output

ENV_GITHUB = "GITHUB_TOKEN"
API_BASE = notify.API_BASE
TIMEOUT_SECONDS = notify.TIMEOUT_SECONDS                     # 요청 하나의 소켓 제한(알림 모듈과 같은 15초)
RETRY_AFTER_MAX = notify.RETRY_AFTER_MAX                     # 429 의 retry_after 를 기다리는 시간의 상한(초)
NETWORK_RETRY_WAIT = notify.NETWORK_RETRY_WAIT               # 네트워크 오류·5xx 뒤 다시 시도하기 전의 대기(초)
MAX_RESPONSE_BYTES = 4_000_000                               # getUpdates 응답은 이만큼만 읽는다(5통 × 글 4,096자 × 엔티티가 많아도 1MB 안쪽 — 낯선 사람이 엔티티로 부풀려도 한 묶음이 4MB 를 넘기 어렵게 5통만 받는다)
UPDATES_LIMIT = 5                                            # getUpdates 한 번에 받는 통 수(텔레그램 한도 100 보다 훨씬 작게 — 한 실행의 이슈 상한 MAX_ISSUES 와 같다. 독립 검증 R3)
MAX_ISSUES = 5                                               # 한 실행에서 이슈로 옮기는 글의 상한(나머지는 다음 실행)
ISSUE_GAP_SECONDS = 1.0                                      # 이슈 만들기 사이 간격
MAX_SIDE_REPLIES = 3                                         # /start·/help·글 아닌 형식에 답하는 통 수 상한(한 실행) — 그 이상은 조용히 넘긴다
MAX_MESSAGES = MAX_ISSUES + MAX_SIDE_REPLIES                 # 한 실행의 텔레그램 전송 통 수 상한(접수 확인 + 답)
QUOTE_LIMIT = 3000                                           # 이슈 인용 블록에 싣는 원문의 상한(글자)
CLEAN_CAP = 20000                                            # 소독을 돌리는 원문의 상한(그 뒤는 '생략' 글자 수에만 센다 — 1MB 글에 정규식을 돌리지 않는다)
TITLE_PREFIX = "[텔레그램] "
TITLE_LIMIT = 40                                             # 제목에 싣는 첫 줄의 글자 수
SEARCH_PAGES, SEARCH_PER_PAGE = 3, 100                       # 중복 확인 때 읽는 이슈 목록(최근 것부터 최대 300건)
LABEL = "텔레그램수신"
LABEL_COLOR = "0e8a16"
LABEL_DESCRIPTION = "운영자가 텔레그램 봇에게 보낸 글(접수일 뿐 승인이 아님)"
MARKER_VERSION = "v1"
MARKER_FORMAT = "<!-- telegram-inbox:" + MARKER_VERSION + " update_id={} -->"
MARKER_RE = re.compile(r"<!-- telegram-inbox:" + MARKER_VERSION + r" update_id=([0-9]{1,15}) -->")
TOKEN_RE = re.compile(r"[0-9]{3,20}:[A-Za-z0-9_\-]{20,100}")           # pipeline/notify.py 의 _TOKEN_RE 와 같은 모양(시험이 대조한다)
CHAT_ID_RE = re.compile(r"[0-9]{1,16}")                                # 개인 대화의 채팅 ID(양의 정수). `@이름` 꼴은 개인 대화의 비교에 쓸 수 없다
BOT_LOGIN = loop.BOT_LOGIN

FULLWIDTH_AT, FULLWIDTH_LT, FULLWIDTH_GT = chr(0xFF20), chr(0xFF1C), chr(0xFF1E)
_ESCAPES = str.maketrans({"@": FULLWIDTH_AT, "<": FULLWIDTH_LT, ">": FULLWIDTH_GT})
_LINE_BREAKS_RE = re.compile("\r\n|[\r\x0b\x0c\x85\u2028\u2029]")
_ENTITY_RE = re.compile(r"&(?=#?[A-Za-z0-9]{1,32};)")                 # `&#64;`·`&lt;` 처럼 글자 참조로 읽힐 `&` 만(보통의 `A & B` 는 그대로)
_DROPPED_CATEGORIES = frozenset({"Cc", "Cf", "Cs"})                    # 제어 문자(탭은 먼저 공백으로)·서식 문자(방향 제어·태그 문자 포함)·짝 없는 서로게이트
_COMMAND_RE = re.compile(r"/(?:start|help)(?:[@" + FULLWIDTH_AT + r"][A-Za-z0-9_]{1,64})?(?:\s|$)", re.IGNORECASE)      # 소독한 글(`@` 가 전각 `＠`)에서 찾으므로 둘 다 받는다
_KST = timezone(timedelta(hours=9))

# ---- 안내 문구(텔레그램·이슈 본문에 쓰는 고정 문장 — 외부 글은 하나도 섞이지 않는다) ------------------------------------------
USAGE_TEXT = ("이 봇은 챈스블로그의 알림 봇입니다. 여기로 보낸 글은 저장소의 공개 이슈([텔레그램] 제목)로 옮겨져 AI 가 읽습니다 — 비밀번호·키·개인정보는 보내지 마세요. "
              "옮겨 오는 일은 정해진 때에 하므로 수십 분에서 몇 시간 늦을 수 있습니다. 접수는 승인이 아닙니다: 승인이 필요한 일은 알림에 적힌 번호(r001 같은 번호)의 "
              "[답하기] 양식으로 답해 주세요. `r103 승인 1` 처럼 번호로 시작하는 글도 접수만 합니다.")
NON_TEXT_TEXT = "글만 받을 수 있어요 — 사진·음성·파일은 가져오지 않습니다."
ISSUE_NOTICE = ("**텔레그램으로 받은 글입니다** — 허용된 운영자 계정(비공개 대화)에서 온 것을 확인했습니다. **접수일 뿐 승인이 아닙니다.**\n"
                "이 이슈는 공개입니다 — 비밀번호·키·개인정보는 보내지 마세요(이미 보냈다면 바로 폐기·재발급하세요).")
CANDIDATE_NOTE = ("※ 위 답변 후보는 참고용이고 승인이 아닙니다. 승인은 소유자 계정이 `[답변]` 양식(알림의 `[답하기]`)으로 올리고 요청 번호가 맞을 때만 인정됩니다(G-S9).")
SECRET_NOTE = "※ 비밀 값처럼 보이는 글자는 `***` 로 가렸습니다."
FORWARDED_NOTE = "※ 이 글은 다른 곳에서 전달된 글(또는 봇을 거친 글)입니다 — 운영자가 쓴 글이 아닙니다. 운영자 계정이 보냈다는 것만 확인했습니다."

# ---- 실행 줄(고정 문장 — 값이 없다) -----------------------------------------------------------------------------------
SKIP_LINE = "텔레그램 수신: 건너뜀(시크릿 없음)"
NO_GITHUB_LINE = "텔레그램 수신: GITHUB_TOKEN 이 없어 읽지 않습니다(읽기 전용 실행 — 텔레그램의 글은 그대로 남아 다음 실행이 읽습니다)"
NONE_LINE = "텔레그램 수신: 새 글이 없습니다"
BAD_TOKEN_LINE = "텔레그램 수신: 봇 토큰 모양이 올바르지 않습니다(숫자:영문숫자 모양이어야 합니다. 앞뒤 공백·따옴표·`bot` 글자가 섞이지 않았는지 확인)"
BAD_CHAT_LINE = ("텔레그램 수신: 채팅 ID 가 양의 정수가 아닙니다(그룹·채널의 음수 ID 와 `@이름` 꼴은 개인 대화 읽기에 쓸 수 없습니다. "
                 "앞뒤 공백·따옴표가 섞이지 않았는지도 확인)")
USAGE_ERROR_LINE = "사용법 오류: 이 명령은 인자를 받지 않습니다(값은 명령 줄이 아니라 환경변수에서만 읽습니다)"
UNEXPECTED_LINE = "텔레그램 수신: 예기치 않은 오류({name}) — 코드 문제일 수 있어 AI 에게 알려 주세요(텔레그램의 글은 그대로 남아 다음 실행이 읽습니다)"
WARNING_LINE = "::warning::텔레그램 수신을 끝내지 못했습니다. 이유는 바로 앞 로그 줄에 있습니다(텔레그램의 글은 확인하지 않은 채 남아 다음 실행이 다시 읽습니다)."
ERROR_LINE = "::error::텔레그램 수신이 설정 문제로 멈췄습니다. 원인과 조치는 바로 앞 로그 줄과 docs/TELEGRAM_INBOX.md 에 있습니다."
# 텔레그램 getUpdates 실패 분류 → (원인 안내, 종료 코드). 1 = 설정 문제(실행 실패로만 드러난다), 0 = 일시 문제(다음 실행이 다시 읽는다)
POLL_FAILURES = {
    "unauthorized": ("봇 토큰이 틀렸거나 폐기됐습니다(401) — BotFather 에서 토큰을 확인하고 시크릿을 새 값으로 바꾸세요", 1),
    "not_found": ("봇을 찾을 수 없습니다(404) — 토큰을 끝까지 복사했는지 확인하세요", 1),
    "webhook": ("이 봇에는 웹훅이 설정돼 있어 getUpdates 로 읽을 수 없습니다(409) — 웹훅과 동시에 쓸 수 없습니다. 웹훅 해제는 텔레그램의 `deleteWebhook` 호출이고, "
                "이 워크플로는 웹훅을 만들지도 지우지도 않습니다 — 웹훅이 필요 없다면 AI 에게 알려 해제를 맡기세요", 1),
    "conflict": ("같은 봇의 글을 다른 곳에서 동시에 읽고 있습니다(409) — 한 곳에서만 읽을 수 있습니다", 1),
    "bad_request": ("텔레그램이 요청을 거부했습니다(400·403 등) — 토큰·권한을 확인하세요", 1),
    "rate_limited": ("텔레그램이 잠시 막았습니다(429) — 다음 실행에서 다시 읽습니다", 0),
    "server_error": ("텔레그램 서버 오류입니다(5xx) — 일시적일 수 있어 다음 실행에서 다시 읽습니다", 0),
    "network": ("텔레그램에 연결하지 못했습니다(네트워크 오류) — 일시적일 수 있어 다음 실행에서 다시 읽습니다", 0),
    "timeout": ("텔레그램이 제한 시간 안에 답하지 않았습니다 — 일시적일 수 있어 다음 실행에서 다시 읽습니다", 0),
    "bad_response": ("텔레그램의 응답을 읽을 수 없습니다 — 일시적일 수 있어 다음 실행에서 다시 읽습니다", 0),
}

Poll = namedtuple("Poll", "ok updates reason status wait")          # reason: ok 또는 POLL_FAILURES 의 키, wait: 429 의 retry_after(초, 아니면 0)
Incoming = namedtuple("Incoming", "update_id kind text sent forwarded", defaults=(False,))        # kind: skip(허용 밖) | other(운영자 본인이 보낸 글 아닌 형식) | text, forwarded: 전달·봇 경유 글
FORWARD_KEYS = ("forward_origin", "forward_from", "forward_from_chat", "forward_from_message_id", "forward_signature", "forward_sender_name", "forward_date", "is_automatic_forward", "via_bot")
Candidate = namedtuple("Candidate", "request_id answer choice memo_chars")


# ---- 텔레그램 getUpdates ------------------------------------------------------------------------------------------
def _read_json(response):
    try:
        raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            return None
        data = json.loads(raw.decode("utf-8", "replace"))
    except Exception:  # noqa: BLE001 - 읽을 수 없는 본문은 '본문 없음'으로 본다(내용·예외 문구를 쓰지 않는다)
        return None
    return data if isinstance(data, dict) else None


def _retry_after(body, headers):
    """429 응답의 기다릴 시간(초): 본문의 parameters.retry_after, 없으면 Retry-After 헤더, 둘 다 없으면 1. 1~RETRY_AFTER_MAX 로 맞춘다(notify.Notifier 와 같다)."""
    value = None
    params = body.get("parameters") if isinstance(body, dict) else None
    if isinstance(params, dict):
        value = params.get("retry_after")
    if value is None and headers is not None:
        try:
            value = headers.get("Retry-After")
        except Exception:  # noqa: BLE001
            value = None
    try:
        seconds = int(float(value))
    except (TypeError, ValueError, OverflowError):
        seconds = 1
    return max(1, min(seconds, RETRY_AFTER_MAX))


def classify(kind, status, body):
    """응답 한 번 → 분류 코드('ok' 또는 POLL_FAILURES 의 키). 텔레그램이 준 설명 글은 웹훅 여부를 가릴 때만 읽고 어디에도 쓰지 않는다."""
    if kind in ("timeout", "network"):
        return kind
    description = body.get("description") if isinstance(body, dict) and isinstance(body.get("description"), str) else ""
    if kind == "ok":
        good = isinstance(body, dict) and body.get("ok") is True and isinstance(body.get("result"), list)
        return "ok" if status == 200 and good else "bad_response"
    if status == 401:
        return "unauthorized"
    if status == 404:
        return "not_found"
    if status == 409:
        return "webhook" if "webhook" in description.lower() else "conflict"
    if status == 429:
        return "rate_limited"
    if isinstance(status, int) and status >= 500:
        return "server_error"
    return "bad_request"


class Telegram:
    """getUpdates 호출기. 토큰은 요청 주소의 경로에만 쓰고 repr·결과·출력에 나오지 않는다(notify.Notifier 와 같은 규칙: 모든 예외를 분류로 바꾸고 문구를 버린다)."""

    def __init__(self, token, opener=None, sleep=None, base=API_BASE):
        self._token, self._opener, self._sleep, self._base = token, opener, sleep, base

    def __repr__(self):
        return "<Telegram>"

    __str__ = __repr__

    def _request(self, payload):
        url = f"{self._base}/bot{self._token}/getUpdates"
        return urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), method="POST",
                                      headers={"Content-Type": "application/json; charset=utf-8", "User-Agent": "chanceblog-telegram-inbox"})

    def _once(self, payload):
        """요청 한 번 → (종류 ok|http|timeout|network, 상태, 본문 dict 또는 None, 헤더). 예외는 모두 분류로 바꾸고 문구를 버린다."""
        opener = self._opener or urllib.request.urlopen
        try:
            response = opener(self._request(payload), timeout=TIMEOUT_SECONDS)
        except urllib.error.HTTPError as exc:
            body, headers, status = _read_json(exc), getattr(exc, "headers", None), getattr(exc, "code", None)
            try:
                exc.close()
            except Exception:  # noqa: BLE001
                pass
            return "http", status if isinstance(status, int) else None, body, headers
        except (TimeoutError, OSError) as exc:        # socket.timeout 은 TimeoutError, URLError 는 OSError — 연결 오류의 문구에 요청 주소가 들어 있을 수 있어 버린다
            reason = getattr(exc, "reason", exc)
            return ("timeout" if isinstance(reason, TimeoutError) else "network"), None, None, None
        except Exception:  # noqa: BLE001 - http.client 오류·잘못된 주소(ValueError) 등
            return "network", None, None, None
        try:
            status = getattr(response, "status", None)
            if status is None:
                status = response.getcode()
            body, headers = _read_json(response), getattr(response, "headers", None)
        except Exception:  # noqa: BLE001
            return "network", None, None, None
        finally:
            try:
                response.close()
            except Exception:  # noqa: BLE001
                pass
        return "ok", status if isinstance(status, int) else None, body, headers

    def get_updates(self, offset=None, limit=UPDATES_LIMIT):
        """새 글을 읽는다. offset 이 있으면 그보다 작은 번호의 글은 텔레그램이 '확인됨' 으로 보고 지운다 — 그래서 이 호출이 확인과 다음 묶음 읽기를 겸한다.
        429 는 retry_after(최대 10초)만큼 기다려 한 번, 네트워크 오류·5xx 는 한 번 다시 시도한다. 항상 Poll 을 돌려준다(예외 없음)."""
        payload = {"limit": limit, "timeout": 0, "allowed_updates": ["message"]}
        if offset is not None:
            payload["offset"] = offset
        waited_rate = waited_net = False
        while True:
            kind, status, body, headers = self._once(payload)
            reason = classify(kind, status, body)
            if reason == "ok":
                return Poll(True, body["result"], "ok", status, 0)
            wait = _retry_after(body, headers) if reason == "rate_limited" else 0
            if reason == "rate_limited" and not waited_rate:
                waited_rate = True
                self._pause(wait)
                continue
            if reason in ("network", "timeout", "server_error") and not waited_net:
                waited_net = True
                self._pause(NETWORK_RETRY_WAIT)
                continue
            return Poll(False, [], reason, status, wait)

    def _pause(self, seconds):
        if seconds > 0:
            (self._sleep or time.sleep)(seconds)


# ---- 받은 글 읽기·소독 -----------------------------------------------------------------------------------------------
def _plain_int(value):
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def read_update(update, chat_id):
    """update 한 개를 Incoming 으로. 번호(update_id)를 읽을 수 없는 항목은 확인할 수도 없어 None.
    허용 조건(하나): private 대화이고 chat.id 와 from.id 가 둘 다 chat_id. 그 밖(다른 사람·그룹·채널·edited_message·콜백 …)은 skip — 이슈도 답도 없다."""
    update_id = _plain_int(update.get("update_id")) if isinstance(update, dict) else None
    if update_id is None or update_id < 0:
        return None
    message = update.get("message")
    chat = message.get("chat") if isinstance(message, dict) else None
    sender = message.get("from") if isinstance(message, dict) else None
    if not (isinstance(chat, dict) and isinstance(sender, dict) and chat.get("type") == "private"
            and _plain_int(chat.get("id")) == chat_id and _plain_int(sender.get("id")) == chat_id
            and sender.get("is_bot") is not True):          # 봇이 보낸 글은 운영자 글이 아니다(실제로는 일어날 수 없는 입력이지만 비용 0 의 방어)
        return Incoming(update_id, "skip", "", None)
    text = message.get("text")
    if isinstance(text, str) and text.strip():
        forwarded = any(message.get(key) for key in FORWARD_KEYS)       # 전달된 글·봇을 거친 글은 운영자가 쓴 글이 아니다 — 본문에 그렇게 표시한다
        return Incoming(update_id, "text", text, _plain_int(message.get("date")), forwarded)
    return Incoming(update_id, "other", "", None)


def neutralize(text):
    """공개 이슈에 인용할 글의 소독(받은 글은 데이터다): 줄바꿈 꼴을 `\\n` 으로, 보이지 않는 문자·제어 문자·서식 문자 제거(탭은 공백), 글자 참조로 읽힐 `&` 를 `&amp;` 로,
    `@`·`<`·`>` 를 전각으로(멘션·HTML·가짜 표지 `<!-- … -->` 가 되지 않게), 빈 줄 3개 이상을 2개로. 코드 펜스·마크다운 링크의 글자(백틱·대괄호·소괄호)는 건드리지 않는다."""
    text = _LINE_BREAKS_RE.sub("\n", str(text)).replace("\t", " ")
    text = INVISIBLE_RE.sub("", text)
    text = "".join(ch for ch in text if ch == "\n" or unicodedata.category(ch) not in _DROPPED_CATEGORIES)
    text = _ENTITY_RE.sub("&amp;", text).translate(_ESCAPES)
    return re.sub(r"\n{3,}", "\n\n", text).strip("\n")


def prepare_text(text, scrub):
    """원문 → (소독한 글, 인용에 싣지 못한 글자 수, 비밀을 가렸는가). 큰 글에 정규식을 돌리지 않으려고 앞 CLEAN_CAP 자만 소독하고 나머지는 생략 글자 수에만 센다.
    비밀 가리기(scrub: 토큰·채팅 ID 글자 그대로 + 비밀 모양 패턴)는 자르기 전에 한다 — 경계에 걸친 값이 반쪽만 남지 않게. 소독(neutralize)이 보이지 않는 문자를 지운 **뒤에야** 이어 붙는 비밀
    (토큰·키 한가운데에 폭 없는 공백을 끼운 글 — 채팅 앱에서 복사하면 섞인다)이 있으므로 소독 뒤에 한 번 더 가린다(독립 검증 M1)."""
    raw = str(text)
    head, rest = raw[:CLEAN_CAP], len(raw) - min(len(raw), CLEAN_CAP)
    masked = scrub(head)
    cleaned = neutralize(masked)
    again = scrub(cleaned)             # 보이지 않는 문자를 지운 뒤에야 이어 붙는 비밀 모양을 한 번 더 가린다
    return again, rest, masked != head or again != cleaned


def build_title(clean):
    """제목: `[텔레그램] ` + 소독한 글의 첫 줄 앞 40자(넘으면 `…`). 한 줄로 접는다. 내용이 없으면 `(내용 없음)`."""
    first = next((" ".join(line.split()) for line in clean.split("\n") if line.strip()), "") or "(내용 없음)"
    if len(first) > TITLE_LIMIT:
        first = first[:TITLE_LIMIT].rstrip() + "…"
    return TITLE_PREFIX + first


_CHOICE_ITEM = r"[A-Za-z0-9가-힣]{1,3}(?:=[A-Za-z0-9가-힣]{1,3})?"
_CHOICE_RE = re.compile(_CHOICE_ITEM + r"(?:," + _CHOICE_ITEM + r"){0,4}")
_ANSWER_WORDS = tuple(short for short, _full in loop.ANSWER_OPTIONS)


def answer_candidate(clean):
    """글이 요청 번호로 시작하면 Candidate(정본 번호, 답 낱말 또는 '', 선택 또는 '', 메모 글자 수)를, 아니면 None.
    번호 읽기는 운영자 요청함과 한곳이다 — `r103`·`R103`·`r-103`·`R-103`·`r 103` 꼴(loop.REQUEST_INPUT_RE·normalize_request_id), 답 낱말은 양식의 선택지(loop.ANSWER_OPTIONS)의 짧은 말.
    번호 바로 뒤가 글자·숫자·밑줄이면(`r1034`·`r103x`) 번호가 아니다. 참고용이고 승인이 아니다 — 읽은 값(검증된 번호·낱말·선택)과 메모 글자 수만 본문에 싣는다."""
    text = clean.lstrip()
    found = loop.REQUEST_INPUT_RE.match(text)
    if found is None:
        return None
    after = text[found.end():]
    if after and not (after[0].isspace() or after[0] in ".,:;!?)"):
        return None
    request_id = loop.normalize_request_id(found.group(0))
    if not notify.REQUEST_ID_RE.fullmatch(request_id):
        return None
    rest = after.lstrip(" \t\n.,:;!?)")
    parts = rest.split(None, 1)
    word = parts[0].rstrip(".,!?)") if parts else ""
    if word not in _ANSWER_WORDS:
        return Candidate(request_id, "", "", 0)
    rest = parts[1] if len(parts) > 1 else ""
    parts = rest.split(None, 1)
    choice = ""
    if parts and _CHOICE_RE.fullmatch(parts[0].rstrip(".")):
        choice, rest = parts[0].rstrip("."), (parts[1] if len(parts) > 1 else "")
    return Candidate(request_id, word, choice, len(rest.strip()))


def candidate_line(candidate):
    """본문에 싣는 '답변 후보' 한 줄(값은 코드가 검증한 것뿐). 번호는 운영자에게 보이는 꼴 `r103`."""
    shown = notify.display_id(candidate.request_id)
    if not candidate.answer:
        return (f"요청 번호 후보(참고용): **{shown}** — 답변 낱말({'·'.join(_ANSWER_WORDS)})이 바로 뒤에 없어 답으로 읽지 않았습니다.")
    memo = f"메모 있음({candidate.memo_chars}자)" if candidate.memo_chars else "메모 없음"
    return (f"답변 후보(참고용): 요청 **{shown}** · 답 **{candidate.answer}**" + (f" · 선택 **{candidate.choice}**" if candidate.choice else "") + f" · {memo}")


def sent_line(timestamp):
    """텔레그램이 알려 준 보낸 시각(KST). 읽을 수 없으면 빈 문자열."""
    if timestamp is None or not 0 < timestamp < 4102444800:
        return ""
    try:
        moment = datetime.fromtimestamp(timestamp, _KST)
    except (OverflowError, OSError, ValueError):
        return ""
    return f"보낸 시각: {moment:%Y-%m-%d %H:%M} KST(텔레그램 기준 — 이슈는 예약 실행이 가져온 뒤에 만들어져 늦을 수 있습니다)"


def build_body(update_id, sent, clean, omitted, masked, candidate, forwarded=False):
    """이슈 본문: 표지(코드가 맨 위에 직접) → 안내 → (전달된 글이라는 말) → 보낸 시각 → 인용 블록의 원문 → (비밀을 가렸다는 말) → (답변 후보와 승인 아님 한 줄)."""
    shown = clean[:QUOTE_LIMIT]
    omitted += len(clean) - len(shown)
    lines = [("> " + line) if line else ">" for line in shown.split("\n")]
    if omitted:
        lines.append(f"> …(이하 {omitted}자 생략)")
    parts = [MARKER_FORMAT.format(update_id), ISSUE_NOTICE]
    if forwarded:
        parts.append(FORWARDED_NOTE)
    stamp = sent_line(sent)
    if stamp:
        parts.append(stamp)
    parts.append("\n".join(lines))
    if masked:
        parts.append(SECRET_NOTE)
    if candidate is not None:
        parts.append(candidate_line(candidate) + "\n" + CANDIDATE_NOTE)
    return "\n\n".join(parts) + "\n"


# ---- GitHub 이슈 ---------------------------------------------------------------------------------------------------
def list_inbox_issues(api):
    """라벨 텔레그램수신 이슈(열림·닫힘, 최근 것부터 최대 SEARCH_PAGES 쪽)에서 표지가 든 것 → {update_id: 이슈 번호}.
    **작성자가 봇이고 본문 맨 앞이 표지인 것만** 인정한다 — 낯선 사람이 표지를 흉내 낸 이슈로 진짜 글을 건너뛰게 만들 수 없다. PR 은 건너뛴다."""
    found = {}
    for page in range(1, SEARCH_PAGES + 1):
        items = api.request("GET", "/issues", params={"labels": LABEL, "state": "all", "sort": "created", "direction": "desc",
                                                      "per_page": SEARCH_PER_PAGE, "page": page})
        if not isinstance(items, list):
            raise loop.GitHubError("응답이 목록이 아닙니다")
        for item in items:
            user = item.get("user") if isinstance(item, dict) else None
            number = item.get("number") if isinstance(item, dict) else None
            if (not isinstance(user, dict) or user.get("login") != BOT_LOGIN or "pull_request" in item
                    or not isinstance(number, int) or isinstance(number, bool)):
                continue
            marker = MARKER_RE.match(str(item.get("body") or ""))
            if marker:
                found.setdefault(int(marker.group(1)), number)
        if len(items) < SEARCH_PER_PAGE:
            break
    return found


def ensure_label(api):
    """라벨이 없으면 만든다(있으면 422 — 그대로 둔다)."""
    try:
        api.request("POST", "/labels", payload={"name": LABEL, "color": LABEL_COLOR, "description": LABEL_DESCRIPTION}, retry=False)
    except loop.GitHubError as exc:
        if exc.status != 422:
            raise


def create_issue(api, update_id, title, body, sleep):
    """이슈를 **한 번만** 만든다(자동 재시도 없음). 만들어졌는지 모호한 실패(응답 유실·시간 초과·5xx·번호 없는 응답)는 같은 표지를 한 번 찾아 있으면 그 번호를 쓰고 없으면 실패로 올린다
    (같은 글이 둘이 되지 않게). 거절(4xx)은 만들어지지 않은 것이라 그대로 올린다. 돌려주는 값: 이슈 번호."""
    try:
        issue = api.request("POST", "/issues", payload={"title": title, "body": body, "labels": [LABEL]}, retry=False)
        number = issue.get("number") if isinstance(issue, dict) else None
        if isinstance(number, bool) or not isinstance(number, int) or number < 1:
            raise loop.GitHubError("응답에 이슈 번호가 없습니다")
    except loop.GitHubError as exc:
        if isinstance(exc.status, int) and 400 <= exc.status < 500:
            raise
        sleep(loop.RETRY_WAIT)
        existing = list_inbox_issues(api).get(update_id)
        if existing is None:
            raise
        return existing
    names = [str(item.get("name")) for item in issue.get("labels") or () if isinstance(item, dict)]
    if LABEL not in names:        # 라벨이 조용히 빠지면 중복 확인·AI 읽기가 이 이슈를 못 찾는다 — 한 번 붙여 본다(실패해도 이슈는 남는다)
        try:
            api.request("POST", f"/issues/{number}/labels", payload={"labels": [LABEL]}, retry=False)
        except loop.GitHubError:
            pass
    return number


# ---- 실행 ----------------------------------------------------------------------------------------------------------
GITHUB_HINT = "GITHUB_TOKEN 의 권한(issues: write)과 저장소 이름·라벨을 확인하세요"


class Stats:
    """한 번의 실행이 한 일의 개수(글 내용은 들어 있지 않다)."""

    def __init__(self):
        self.created, self.duplicates, self.ignored, self.replies, self.reply_failures = [], 0, 0, 0, 0


def ack_text(number):
    """접수 확인 한 줄: 이슈 번호·비밀 금지·승인은 [답하기] 양식으로. 값은 이슈 번호(정수)뿐이다."""
    return f"{notify.OK_MARK} 접수했습니다(이슈 #{int(number)}) · 비밀·키는 보내지 마세요 · 승인은 [답하기] 양식으로"


class Inbox:
    """한 번의 실행: 새 글을 읽고, 글마다 처리하고, 처리를 끝낸 글까지만 텔레그램에 확인한다."""

    problem = ""

    def __init__(self, notifier, poll, api, chat_id, say, sleep):
        self.notifier, self.poll, self.api, self.chat_id, self.say, self.sleep = notifier, poll, api, chat_id, say, sleep
        self.stats = Stats()
        self.known = None                  # {update_id: 이슈 번호} — 만들 글이 처음 나왔을 때 한 번만 읽는다(새 글이 없는 실행은 GitHub 를 부르지 않는다)
        self.label_ready = False
        self.handled = None                # 처리를 끝낸 가장 큰 update_id
        self.confirmed = None              # 텔레그램에 확인한(offset 을 올린) 가장 큰 update_id
        self.confirm_failed = False
        self.exit_code = 0

    # -- 실패 -----------------------------------------------------------------------------------------------------
    def poll_failed(self, reason):
        text, code = POLL_FAILURES[reason]
        self.say(f"텔레그램 수신: {text}")
        self.say(ERROR_LINE if code else WARNING_LINE)
        self.exit_code = max(self.exit_code, code)
        self.problem = text

    def github_failed(self, exc):
        persistent = isinstance(exc.status, int) and 400 <= exc.status < 500 and exc.status != 429
        self.say(f"텔레그램 수신: GitHub 이슈 처리에 실패했습니다 — {exc}" + (f" · {GITHUB_HINT}" if persistent else " · 일시적일 수 있어 다음 실행에서 다시 시도합니다"))
        self.say(ERROR_LINE if persistent else WARNING_LINE)
        self.exit_code = max(self.exit_code, 1 if persistent else 0)
        self.problem = "GitHub 이슈를 만들지 못했습니다(" + (f"HTTP {exc.status}" if isinstance(exc.status, int) else "연결 오류") + ")"

    # -- 글 하나 ----------------------------------------------------------------------------------------------------
    def reply(self, text):
        """/start·/help·글 아닌 형식에 한 줄로 답한다. 한 실행에 MAX_SIDE_REPLIES 통까지 — 그 이상은 조용히 넘긴다(도배 금지). 실패해도 글은 처리된 것으로 본다."""
        if self.stats.replies >= MAX_SIDE_REPLIES:
            return
        self.stats.replies += 1
        result = self.notifier.send_message(text)
        if not result.sent:
            self.stats.reply_failures += 1
            self.say(f"텔레그램 수신: 안내 답을 보내지 못했습니다 — {notify.describe(result)}")

    def handle(self, incoming):
        """글 하나를 처리한다. True 면 처리를 끝낸 것(확인해도 된다), False 면 멈춘다(실패 — 이 글과 뒤의 글은 확인하지 않는다)."""
        if incoming.kind == "skip":
            self.stats.ignored += 1
            return True
        if incoming.kind == "other":
            self.reply(NON_TEXT_TEXT)
            return True
        clean, rest, masked = prepare_text(incoming.text, self.notifier.scrub)
        if not clean.strip():              # 보이는 글자가 하나도 없는 글(보이지 않는 문자뿐) — 글이 아닌 것으로 본다
            self.reply(NON_TEXT_TEXT)
            return True
        if _COMMAND_RE.match(clean.lstrip()):
            self.reply(USAGE_TEXT)
            return True
        try:
            if self.known is None:
                self.known = list_inbox_issues(self.api)
            if incoming.update_id in self.known:
                self.stats.duplicates += 1     # 앞선 실행이 이슈를 만들고 확인 직전에 멈췄다 — 같은 글을 다시 만들지 않는다
                return True
            if not self.label_ready:
                ensure_label(self.api)
                self.label_ready = True
            if self.stats.created:
                self.sleep(ISSUE_GAP_SECONDS)
            candidate = None if incoming.forwarded else answer_candidate(clean)      # 전달된 글은 운영자가 쓴 글이 아니라 '답변 후보'로 읽지 않는다
            number = create_issue(self.api, incoming.update_id, build_title(clean),
                                  build_body(incoming.update_id, incoming.sent, clean, rest, masked, candidate, incoming.forwarded), self.sleep)
        except loop.GitHubError as exc:
            self.github_failed(exc)
            return False
        self.known[incoming.update_id] = number
        self.stats.created.append(number)
        result = self.notifier.send_message(ack_text(number), buttons=[("이슈 열기", f"{notify.REPO_URL}/issues/{number}")])
        if not result.sent:
            self.say(f"텔레그램 수신: 접수 확인을 보내지 못했습니다(이슈 #{number} 은 만들어졌습니다) — {notify.describe(result)}")
        return True

    def process(self, batch):
        """묶음 하나를 번호 순서대로 처리한다. True 면 묶음을 끝까지 처리했다. False 면 멈춘다(실패 또는 이슈 상한)."""
        items = {}
        for raw in batch:
            incoming = read_update(raw, self.chat_id)
            if incoming is not None and (self.handled is None or incoming.update_id > self.handled):     # 이미 처리한 번호가 되풀이돼 오면(서버가 offset 을 무시) 다시 처리하지 않는다
                items.setdefault(incoming.update_id, incoming)
        if not items:      # 새로 처리할 글이 없다(번호를 읽을 수 있는 글이 하나도 없거나 같은 묶음이 되풀이됐다) — 확인할 수 없으니 같은 묶음을 되풀이해 읽지 않는다
            return False
        for update_id in sorted(items):
            if not self.handle(items[update_id]):
                return False
            self.handled = update_id
            if len(self.stats.created) >= MAX_ISSUES:
                return False
        return True

    # -- 전체 -----------------------------------------------------------------------------------------------------
    def run(self):
        first = self.poll.get_updates()
        if not first.ok:
            self.poll_failed(first.reason)
            return
        batch = first.updates
        while batch and self.process(batch):
            following = self.poll.get_updates(self.handled + 1)         # 이 호출이 handled 까지를 확인하고 다음 묶음을 준다
            if not following.ok:
                self.confirm_failed = True
                self.poll_failed(following.reason)
                return
            self.confirmed, batch = self.handled, following.updates
        # 멈췄거나(실패·상한) 끝났다: 처리한 글 중 아직 확인하지 않은 것이 있으면 그것만 확인한다(받은 글은 버린다)
        if self.handled is not None and self.confirmed != self.handled and not self.confirm_failed:
            last = self.poll.get_updates(self.handled + 1, limit=1)
            if last.ok:
                self.confirmed = self.handled
            else:
                self.confirm_failed = True
                self.poll_failed(last.reason)


def summarize(environ, inbox, say):
    """실행 요약(개수와 원인 안내뿐 — 글 내용·번호 외의 값은 없다)과 로그 한 줄."""
    stats = inbox.stats
    created = ", ".join(f"#{number}" for number in stats.created) or "없음"
    say(f"텔레그램 수신: 이슈 {len(stats.created)}건 만듦({created}) · 이미 있어 건너뜀 {stats.duplicates} · 허용 밖이라 무시 {stats.ignored} · 안내 답 {stats.replies}통")
    rows = [f"- 만든 이슈: {created}", f"- 이미 이슈가 있어 건너뜀: {stats.duplicates}건", f"- 허용 밖이라 무시(다른 사람·그룹·수정·콜백): {stats.ignored}건",
            f"- 안내 답(/start·/help·글 아닌 형식): {stats.replies}통"]
    if inbox.problem:
        rows.append(f"- **문제**: {md_cell(inbox.problem, 300)} — 원인과 조치는 docs/TELEGRAM_INBOX.md")
    if inbox.confirm_failed:
        rows.append("- 확인(offset)을 올리지 못한 글은 다음 실행이 다시 읽고, 같은 글의 이슈가 이미 있으면 건너뜁니다")
    notify.write_summary(environ, "### 텔레그램 수신 가져오기\n\n" + "\n".join(rows), say)


def run_inbox(environ, out, api=None, opener=None, sleep=None, clock=None, budget=None, base=API_BASE):
    """새 글을 읽어 이슈로 옮긴다. 종료 코드를 돌려준다(모듈 설명 6번)."""
    sleep = sleep or time.sleep
    token, chat = clean_secret(environ.get(notify.ENV_TOKEN)), clean_secret(environ.get(notify.ENV_CHAT))
    if not token or not chat:
        out(SKIP_LINE)
        return 0
    notifier = notify.Notifier(environ, opener=opener, sleep=sleep, clock=clock, budget=budget if budget is not None else notify.Budget(limit=MAX_MESSAGES))

    def say(text):
        out(notifier.scrub(text))      # 모든 출력은 토큰·채팅 ID 를 한 번 더 지운 뒤에 나간다

    if not TOKEN_RE.fullmatch(token):
        say(BAD_TOKEN_LINE)
        return 1
    if not CHAT_ID_RE.fullmatch(chat) or int(chat) < 1:
        say(BAD_CHAT_LINE)
        return 1
    github_token = str(environ.get(ENV_GITHUB) or "").strip()
    if api is None and not github_token:
        say(NO_GITHUB_LINE)
        return 0
    api = api or loop.GitHub(environ.get("GITHUB_REPOSITORY"), github_token, sleep=sleep)
    inbox = Inbox(notifier, Telegram(token, opener=opener, sleep=sleep, base=base), api, int(chat), say, sleep)
    inbox.run()
    stats = inbox.stats
    if not (stats.created or stats.duplicates or stats.ignored or stats.replies or inbox.problem):
        say(NONE_LINE)
    else:
        summarize(environ, inbox, say)
    return inbox.exit_code


# ---- 명령 줄 -------------------------------------------------------------------------------------------------------
class _Parser(argparse.ArgumentParser):
    def error(self, message):
        """argparse 의 기본 오류는 잘못 넘긴 인자를 그대로 메시지에 싣는다 — 실수로 명령 줄에 넘긴 값(토큰 같은)이 로그에 남지 않게 고정 문장만 낸다."""
        self.print_usage(sys.stderr)
        sys.stderr.write(USAGE_ERROR_LINE + "\n")
        raise SystemExit(2)


def build_parser():
    return _Parser(prog="python -m pipeline.telegram_inbox", description="봇에게 온 운영자의 텔레그램 글을 저장소 이슈로 옮긴다(인자 없음 — 값은 환경변수에서만 읽는다)")


def main(argv=None, environ=None, out=print, opener=None, sleep=None, clock=None, budget=None, api=None, base=API_BASE):
    safe_output()
    environ = os.environ if environ is None else environ
    build_parser().parse_args(argv)
    try:
        return run_inbox(environ, out, api=api, opener=opener, sleep=sleep, clock=clock, budget=budget, base=base)
    except Exception as exc:  # noqa: BLE001 - 예외 문구에 요청 주소(토큰)가 있을 수 있어 클래스 이름만 남긴다
        out(UNEXPECTED_LINE.format(name=type(exc).__name__))
        out(ERROR_LINE)
        return 1


if __name__ == "__main__":
    sys.exit(main())
