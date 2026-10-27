"""텔레그램 알림 — 새 글 발행·초안 발행 대기·확인 필요를 휴대폰으로 알린다(표준 라이브러리만, Python 3.10 이상).

운영자가 GitHub 화면을 열지 않아도 '새 글이 올라갔다', 'Blogger 초안이 올라와 게시를 기다린다', '확인할 일이 생겼다'를 휴대폰 알림으로 받게 하는 알림 계층이다.
운영자용 설명서: .github/editorial/TELEGRAM_SETUP.md / 구조·실패 격리: docs/ARCHITECTURE.md §4-4 / 토큰 취급 규칙: docs/SECURITY_GUARDRAILS.md G-C11

설정: 환경변수 TELEGRAM_BOT_TOKEN·TELEGRAM_CHAT_ID(GitHub Secrets → 단계의 env). 둘 중 하나라도 비면 **비활성**이다 — 아무것도 보내지 않고 성공으로 끝난다.

원칙
  1. 알림은 보조다. 어떤 경우에도 예외를 호출한 쪽으로 던지지 않고 Result(ok·sent·status·reason·detail)를 돌려준다. 글 게시·초안 업로드·점검 이슈의 결과와
     종료 코드는 알림 때문에 바뀌지 않는다.
  2. **토큰·채팅 ID 는 로그·예외·출력·명령 줄 어디에도 나오지 않는다.** 이 서비스는 토큰이 요청 주소의 경로(https://api.telegram.org/bot<토큰>/sendMessage)에
     들어가므로, 연결 오류 문구를 그대로 출력하면 주소와 함께 토큰이 공개 Actions 로그로 샌다(requests 의 예외 문자열이 요청 주소를 담는 것이 전형적인 사고다).
     그래서 (a) 모든 예외를 잡아 **클래스 이름만** 쓰고 예외 문구·요청 객체·원 예외(`__cause__`)는 어디에도 싣지 않으며,
     (b) 텔레그램이 준 오류 설명(description)과 호출한 쪽에 돌려주는 모든 글은 토큰·채팅 ID(와 URL 인코딩 형태·토큰 절반)를 글자 그대로 지우고
     비밀 모양 패턴(llm.mask)으로 한 번 더 가린 뒤에만 내보내며, (c) 토큰은 요청 주소 말고는 어디에도 쓰지 않는다(헤더·본문·명령 줄에 넣지 않는다).
  3. 길이·전송량 상한: 본문 3,800자(UTF-16 단위로 보수적으로 계산, 텔레그램 한도는 4,096), 한 실행(프로세스)에서 5통, 통 사이 1.1초.
  4. 외부·AI 유래 글(제목·출처 이름)은 소독해서 쓴다: 비밀 모양 가리기 → 보이지 않는 문자·제어 문자 제거 → 한 줄로 접기('::'·'##[' 풀어 씀) → 길이 제한 →
     (HTML 알림이면) 글 속 https://…·tg://… 를 글자로만(defang_urls: ':' 를 전각 콜론으로) → &·<·> 이스케이프. 주소는 허용 목록(allowed_url)만
     링크·버튼으로 쓰고 나머지는 글자로만 둔다.
  5. 재시도: 429 는 retry_after(최대 10초)만큼 기다려 한 번, 네트워크 오류·5xx 는 한 번. HTML 알림이 400(엔티티 해석 실패)이면 서식 없이 한 번 더,
     버튼이 거부되면(400 BUTTON…) 버튼 없이 한 번 더. 그 밖의 오류(400·401·403·404)는 다시 시도하지 않는다.

명령 줄: python -m pipeline.notify <chance-published [--commit HEAD] | test | status>
  외부 값(제목·토큰)을 명령 줄 인자로 받지 않는다 — 글은 git 커밋의 파일에서, 토큰은 환경변수에서만 읽는다.
  종료 코드: 0 정상(건너뜀 포함, chance-published 는 전송이 실패해도 0 — 실패는 ::warning:: 로 드러난다) / 1 test 가 실패 / 2 사용법 오류
"""
import argparse
import html
import importlib.util
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import namedtuple
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from pipeline.console import md_cell, one_line, safe_output
from pipeline.llm import mask

ROOT = Path(__file__).resolve().parent.parent

ENV_TOKEN = "TELEGRAM_BOT_TOKEN"
ENV_CHAT = "TELEGRAM_CHAT_ID"
API_BASE = "https://api.telegram.org"
TIMEOUT_SECONDS = 15            # 요청 하나의 소켓 제한
RETRY_AFTER_MAX = 10            # 429 의 retry_after 를 기다리는 시간의 상한(초)
NETWORK_RETRY_WAIT = 2          # 네트워크 오류·5xx 뒤 다시 시도하기 전의 대기(초)
TEXT_LIMIT = 3800               # 본문 길이 상한(UTF-16 단위). 텔레그램의 한도는 4,096(엔티티 해석 뒤 길이)이라 여유를 둔다
MAX_MESSAGES = 5                # 한 실행(프로세스)에서 보내는 통 수 상한
SEND_GAP_SECONDS = 1.1          # 통 사이 간격(같은 채팅에는 초당 1통이 안전하다)
MAX_RESPONSE_BYTES = 65536      # 응답 본문은 이만큼만 읽는다
DESCRIPTION_LIMIT = 120         # 텔레그램이 준 오류 설명을 로그에 싣는 길이
TITLE_LIMIT = 120
SHORT_LIMIT = 60
WHERE_LIMIT = 200
LINE_LIMIT = 160
MAX_BUTTONS = 4
RAW_CAP_FACTOR, RAW_CAP_MIN = 10, 2000   # clean_text 가 읽는 원문의 상한: max(limit × 10, 2000)자
MAX_LINES = 10                  # 확인 필요 모음 알림의 줄 수 상한(코멘트와 같은 8개 항목 + '… 외 N건' 한 줄에 여유)
URL_LIMIT = 600
GIT_TIMEOUT = 30
MAX_NEW_FILES = 10              # 한 커밋에서 알리는 새 글 파일의 상한(그 이상은 이상 징후)

SKIP_LINE = "텔레그램 알림: 건너뜀(시크릿 없음)"
WARNING_LINE = ("::warning::텔레그램 알림을 보내지 못했습니다. 이유는 바로 앞 로그 줄에 있고, "
                "Actions 의 '[공통] 텔레그램 알림 시험' 으로 연결을 점검할 수 있습니다(글 게시에는 영향이 없습니다).")
ERROR_LINE = "::error::텔레그램 알림 시험이 실패했습니다. 이유와 조치는 실행 요약과 바로 앞 로그 줄에 있습니다."

# 알림 문구의 그림 문자(소스에는 코드 포인트로만 적는다 — 어떤 콘솔·편집기에서도 깨지지 않게)
OK_MARK, PIN_MARK, MEMO_MARK, WAIT_MARK = (chr(0x2705), chr(0x1F4CC), chr(0x1F4DD), chr(0x23F3))
FLAGS = {"ko": chr(0x1F1F0) + chr(0x1F1F7), "en": chr(0x1F1FA) + chr(0x1F1F8)}
# 새 글 알림은 Pages 배포를 요청한 직후에 오고 주소 버튼이 같이 간다. 배포가 퍼지기 전에 열면 공개 CDN 이 그 404 를 최대 약 18분 보관해 독자에게도 한동안
# 404 가 돌아올 수 있다(docs/DEFECT_REGISTER.md D-41) — 그래서 문구로 3분 뒤에 열어 보게 한다.
DEPLOY_WAIT_NOTE = "사이트 배포가 끝나기까지 약 3분 걸립니다. 일찍 열면 404 가 최대 약 18분 보관될 수 있으니 3분 뒤에 열어 보세요."

# ---- 결과 -------------------------------------------------------------------
# ok: 문제가 없었다(보냈거나, 일부러 건너뜀) / sent: 실제로 전달됨 / status: HTTP 상태(없으면 None) / reason: 아래 분류 코드 / detail: 소독한 한 줄 설명
Result = namedtuple("Result", "ok sent status reason detail")

SENT, DISABLED, NOT_APPLICABLE = "sent", "disabled", "not_applicable"
BAD_TOKEN, BAD_CHAT, EMPTY_TEXT = "invalid_token", "invalid_chat_id", "empty_text"
UNAUTHORIZED, FORBIDDEN, NOT_FOUND = "unauthorized", "forbidden", "not_found"
CHAT_NOT_FOUND, BAD_REQUEST, PARSE_ERROR, BUTTON_ERROR = "chat_not_found", "bad_request", "parse_error", "button_error"
RATE_LIMITED, SERVER_ERROR, NETWORK, TIMEOUT = "rate_limited", "server_error", "network", "timeout"
BAD_RESPONSE, LIMIT, INTERNAL_ERROR = "bad_response", "limit", "internal_error"

# 운영자에게 보여 주는 원인 설명(실행 요약·로그). 값(토큰·채팅 ID)은 어디에도 없다
REASON_TEXT = {
    SENT: "보냈습니다",
    DISABLED: "시크릿이 없어 건너뜀",
    NOT_APPLICABLE: "알릴 내용이 없어 건너뜀",
    BAD_TOKEN: "봇 토큰 모양이 올바르지 않습니다(숫자:영문숫자 모양이어야 합니다. 앞뒤 공백·따옴표·`bot` 글자가 섞이지 않았는지 확인)",
    BAD_CHAT: "채팅 ID 모양이 올바르지 않습니다(숫자여야 합니다. 앞뒤 공백·따옴표가 섞이지 않았는지 확인)",
    EMPTY_TEXT: "보낼 글이 비어 있습니다",
    UNAUTHORIZED: "토큰이 틀렸거나 폐기됐습니다(401) — BotFather 에서 토큰을 확인하고 시크릿을 새 값으로 바꾸세요",
    NOT_FOUND: "봇을 찾을 수 없습니다(404) — 토큰을 끝까지 복사했는지 확인하세요",
    CHAT_NOT_FOUND: "채팅 ID 가 틀렸습니다(400 chat not found) — 휴대폰에서 봇에게 먼저 /start 를 보내고 올바른 채팅 ID 를 등록하세요",
    FORBIDDEN: "봇이 이 채팅에 보낼 수 없습니다(403) — 휴대폰에서 봇에게 /start 를 보냈는지, 봇을 차단하거나 대화를 지우지 않았는지 확인하세요",
    BAD_REQUEST: "텔레그램이 요청을 거부했습니다(400)",
    PARSE_ERROR: "텔레그램이 글의 서식을 해석하지 못했습니다(400)",
    BUTTON_ERROR: "텔레그램이 버튼 주소를 거부했습니다(400)",
    RATE_LIMITED: "너무 자주 보내 잠시 막혔습니다(429) — 잠시 뒤 다시 시도하세요",
    SERVER_ERROR: "텔레그램 서버 오류입니다(5xx) — 일시적일 수 있습니다",
    NETWORK: "텔레그램에 연결하지 못했습니다(네트워크 오류) — 일시적일 수 있습니다",
    TIMEOUT: "텔레그램이 제한 시간 안에 답하지 않았습니다 — 일시적일 수 있습니다",
    BAD_RESPONSE: "텔레그램의 응답을 읽을 수 없습니다",
    LIMIT: f"한 실행에서 보내는 통 수 상한({MAX_MESSAGES}통)에 도달했습니다",
    INTERNAL_ERROR: "알림 모듈 안에서 예기치 않은 오류가 났습니다",
}

# ---- 입력 소독 ---------------------------------------------------------------
_TOKEN_RE = re.compile(r"[0-9]{3,20}:[A-Za-z0-9_\-]{20,100}")
_CHAT_RE = re.compile(r"-?[0-9]{1,20}|@[A-Za-z][A-Za-z0-9_]{3,31}")
# 글자 순서를 뒤집거나 보이지 않게 만드는 문자(소프트 하이픈·폭 없는 공백·방향 제어·단어 결합자·BOM). 소스에는 보이지 않는 문자를 넣지 않으려고 코드 포인트로 쓴다(pipeline/inbox.py 와 같다).
_INVISIBLE_CODEPOINTS = (0x00AD, *range(0x200B, 0x2010), *range(0x202A, 0x202F), *range(0x2060, 0x2065), *range(0x2066, 0x206A), 0xFEFF)
_INVISIBLE_RE = re.compile("[" + "".join(chr(code) for code in _INVISIBLE_CODEPOINTS) + "]")
_SURROGATE_RE = re.compile("[" + chr(0xD800) + "-" + chr(0xDFFF) + "]")       # 짝 없는 서로게이트는 UTF-8 로 인코딩할 수 없다
_URL_SCHEME_RE = re.compile(r"(?i)\b(https?|ftp|tg)://")
_URL_CHARS_RE = re.compile(r"[A-Za-z0-9\-._~:/?#@!$&'()*+,;=%]+")
_FULLWIDTH_COLON = chr(0xFF1A)

# 링크·버튼으로 쓸 수 있는 주소(호스트, 경로 접두). 나머지는 글자로만 둔다 — 제목·출처 같은 외부 글이 알림에 낚시 링크를 끼우지 못하게 한다.
ALLOWED_URLS = (
    ("shine88pc.github.io", "/"),
    ("github.com", "/shine88pc/chanceblog"),
    ("www.blogger.com", "/"),
)


def clean_text(value, limit=TITLE_LIMIT):
    """외부·AI 유래 글을 알림에 넣을 한 줄로 소독한다: 비밀 모양 가리기 → 보이지 않는 문자·서로게이트 제거 → 한 줄로 접기(제어 문자는 공백,
    '::'·'##[' 풀어 씀) → limit 자 이하(넘으면 끝에 '…'). HTML 알림에는 이 결과를 escape_html 에 한 번 더 통과시켜 쓴다(자른 뒤에 이스케이프해야
    '&amp;' 같은 문자 참조가 중간에서 잘리지 않는다)."""
    raw = ("" if value is None else str(value))[:max(limit * RAW_CAP_FACTOR, RAW_CAP_MIN)]       # 아주 긴 글(수 MB)에 정규식을 돌리지 않게 보이는 부분보다 넉넉히만 읽는다
    raw = _SURROGATE_RE.sub("", _INVISIBLE_RE.sub("", mask(raw)))
    return one_line(raw, limit)


def escape_html(text):
    """텔레그램 HTML 모드에서 글자로 보일 값의 이스케이프: &·<·> 만 바꾼다(그 밖의 태그는 400 이 난다)."""
    return html.escape(str(text), quote=False)


def defang_urls(text):
    """글 속 주소(http·https·ftp·tg)가 링크가 되지 않게 ':' 를 전각 콜론으로 바꾼다. 허용 목록 밖 주소를 글자로만 보여 줄 때 쓴다."""
    return _URL_SCHEME_RE.sub(lambda match: match.group(1) + _FULLWIDTH_COLON + "//", str(text))


def safe_text(value, limit=TITLE_LIMIT):
    """HTML 알림에 글자로 넣을 외부·AI 유래 글(제목·출처·라벨): clean_text → defang_urls(글 속 https://…·tg://… 를 텔레그램이 링크로 바꾸지 못하게) →
    escape_html. 링크는 allowed_url 을 통과한 주소만 코드가 직접 건다."""
    return escape_html(defang_urls(clean_text(value, limit)))


def allowed_url(url, extra_prefixes=()):
    """링크·버튼으로 써도 되는 주소면 그 주소를, 아니면 빈 문자열. 허용: https 이고 호스트·경로 접두가 ALLOWED_URLS(또는 코드가 직접 준 extra_prefixes)에
    들어맞는 것. 사용자 정보(@)·포트·백슬래시·공백·따옴표·꺾쇠·제어 문자·'..' 경로 조각이 있으면 거절한다(허용 호스트로 보이게 속이는 주소와
    href 속성을 끊는 문자를 막는다). extra_prefixes 는 레지스트리의 블로그 주소처럼 **코드가 아는 신뢰할 수 있는 값**만 넘긴다(외부 글을 넘기지 않는다)."""
    text = "" if url is None else str(url)
    if not text or len(text) > URL_LIMIT or not _URL_CHARS_RE.fullmatch(text):
        return ""
    try:
        parts = urllib.parse.urlsplit(text)
        host = parts.hostname
    except ValueError:
        return ""
    # netloc 이 호스트 이름과 똑같아야 한다: 사용자 정보(`허용호스트@다른곳`)나 포트(`:8443`)가 있으면 둘이 달라 거절된다. 백슬래시·공백·따옴표는 위 글자 허용 목록이 이미 거른다.
    if parts.scheme != "https" or not host or parts.netloc.lower() != host:
        return ""
    segments = urllib.parse.unquote(parts.path).split("/")
    if any(segment in (".", "..") for segment in segments):
        return ""
    allowed = list(ALLOWED_URLS)
    for prefix in extra_prefixes or ():
        try:
            extra = urllib.parse.urlsplit(str(prefix))
        except ValueError:
            continue
        if extra.scheme == "https" and extra.hostname and extra.port is None:
            allowed.append((extra.hostname, extra.path.rstrip("/") or "/"))
    for allowed_host, allowed_path in allowed:
        if host != allowed_host:
            continue
        if allowed_path == "/" or parts.path == allowed_path or parts.path.startswith(allowed_path.rstrip("/") + "/"):
            return text
    return ""


def utf16_len(text):
    """텔레그램이 세는 글자 수에 가까운 UTF-16 코드 단위 수(이모지·희귀 한자는 2). 한글은 1."""
    return len(str(text).encode("utf-16-le", "surrogatepass")) // 2


def fit_text(text, limit=TEXT_LIMIT):
    """UTF-16 단위로 limit 이하가 되게 자르고, 잘리면 끝에 '…' 를 붙인다(코드 포인트 단위로 자르므로 서로게이트 쌍이 갈라지지 않는다)."""
    text = str(text)
    if utf16_len(text) <= limit:
        return text
    kept, used = [], 0
    for char in text:
        step = 2 if ord(char) > 0xFFFF else 1
        if used + step > limit - 1:
            break
        kept.append(char)
        used += step
    return "".join(kept).rstrip() + "…"


def html_to_plain(text):
    """HTML 알림에서 태그를 걷고 문자 참조를 풀어 쓴 평문(서식 해석이 거부됐을 때나 너무 길 때의 안전망)."""
    return html.unescape(re.sub(r"<[^>]*>", "", str(text)))


def _pairs(buttons):
    out = []
    for item in buttons or ():
        if isinstance(item, (tuple, list)) and len(item) == 2:
            out.append((item[0], item[1]))
    return out


# ---- 전송 한도(한 실행 안에서 공유) ----------------------------------------------
class Budget:
    """한 프로세스에서 보내는 통 수와 마지막 전송 시각. 기본 인스턴스를 모든 Notifier 가 나눠 쓴다(루프 버그가 채팅을 도배하지 못하게)."""

    def __init__(self, limit=MAX_MESSAGES, gap=SEND_GAP_SECONDS):
        self.limit, self.gap = limit, gap
        self.reset()

    def reset(self):
        self.used, self.last = 0, None


_DEFAULT_BUDGET = Budget()


def reset_budget():
    """기본 한도를 처음 상태로(시험이 쓴다)."""
    _DEFAULT_BUDGET.reset()


Reply = namedtuple("Reply", "kind status body headers")     # kind: ok | http | timeout | network


class Notifier:
    """텔레그램 전송기. 환경변수(또는 넘겨 받은 environ)에서 토큰·채팅 ID 를 읽는다. 값은 이 객체 안에만 있고 repr·str·결과·출력에 나오지 않는다.

    opener(request, timeout=…)·sleep(초)·clock() 은 시험이 가짜로 바꿔 끼운다(기본: urllib.request.urlopen·time.sleep·time.monotonic).
    모든 공개 메서드는 예외를 던지지 않고 Result 를 돌려준다."""

    def __init__(self, environ=None, opener=None, sleep=None, clock=None, budget=None):
        environ = os.environ if environ is None else environ
        self._token = str(environ.get(ENV_TOKEN) or "").strip()
        self._chat = str(environ.get(ENV_CHAT) or "").strip()
        self._opener, self._sleep, self._clock = opener, sleep, clock
        self.budget = budget if budget is not None else _DEFAULT_BUDGET

    def __repr__(self):
        return f"<Notifier enabled={self.enabled}>"

    __str__ = __repr__

    @property
    def enabled(self):
        """토큰과 채팅 ID 가 모두 있으면 True(모양이 맞는지는 보낼 때 본다)."""
        return bool(self._token and self._chat)

    # ---- 비밀 지우기 ---------------------------------------------------------
    def _secret_forms(self):
        forms = set()
        for raw in (self._token, self._chat):
            if len(raw) >= 4:
                forms.update({raw, urllib.parse.quote(raw, safe=""), urllib.parse.quote(raw), urllib.parse.quote_plus(raw)})
        bot_id, _, secret = self._token.partition(":")
        forms.update(part for part in (bot_id, secret) if len(part) >= 6)
        return sorted(forms, key=len, reverse=True)

    def scrub(self, text):
        """text 에서 토큰·채팅 ID(와 URL 인코딩 형태·토큰의 숫자·비밀 절반)를 글자 그대로 지우고, 비밀 모양 패턴(llm.mask)으로 한 번 더 가린다."""
        out = "" if text is None else str(text)
        for form in self._secret_forms():
            out = re.sub(re.escape(form), "***", out, flags=re.IGNORECASE)
        return mask(out)

    def _result(self, ok, sent, status, reason, detail=""):
        return Result(bool(ok), bool(sent), status, reason, one_line(self.scrub(detail), DESCRIPTION_LIMIT))

    # ---- 전송 ------------------------------------------------------------------
    def send_message(self, text, parse_mode=None, buttons=None, silent=False, extra_prefixes=()):
        """한 통을 보낸다. parse_mode 는 None(평문) 또는 'HTML'. buttons: [(라벨, 주소), …](허용 목록의 주소만 버튼이 된다, 최대 4개, 한 줄).
        silent=True 면 소리 없는 알림. 항상 Result 를 돌려준다(예외 없음)."""
        try:
            return self._send(text, parse_mode, buttons, silent, tuple(extra_prefixes or ()))
        except Exception as exc:  # noqa: BLE001 - 알림은 보조다: 어떤 예외도 호출한 쪽으로 보내지 않는다(클래스 이름만 남긴다)
            return self._result(False, False, None, INTERNAL_ERROR, type(exc).__name__)

    def _send(self, text, parse_mode, buttons, silent, extra_prefixes):
        if not self.enabled:
            return Result(True, False, None, DISABLED, "")
        if not _TOKEN_RE.fullmatch(self._token):
            return self._result(False, False, None, BAD_TOKEN)
        if not _CHAT_RE.fullmatch(self._chat):
            return self._result(False, False, None, BAD_CHAT)
        if parse_mode not in (None, "HTML"):
            raise ValueError("parse_mode")
        body = "" if text is None else str(text)
        body = _SURROGATE_RE.sub("", body)
        if not body.strip():
            return self._result(False, False, None, EMPTY_TEXT)
        if self.budget.used >= self.budget.limit:
            return self._result(False, False, None, LIMIT)
        self._wait_turn()
        self.budget.used += 1
        payload = self._payload(body, parse_mode, buttons, silent, extra_prefixes)
        try:
            return self._deliver(payload)
        finally:
            self.budget.last = self._now()

    def _now(self):
        return (self._clock or time.monotonic)()

    def _pause(self, seconds):
        if seconds > 0:
            (self._sleep or time.sleep)(seconds)

    def _wait_turn(self):
        if self.budget.last is not None:
            self._pause(self.budget.gap - (self._now() - self.budget.last))

    def _payload(self, body, parse_mode, buttons, silent, extra_prefixes):
        if parse_mode == "HTML" and utf16_len(body) > TEXT_LIMIT:      # 우리 문구는 이보다 훨씬 짧다 — 길면 서식을 버리고 평문으로(태그를 자르다 깨지 않게)
            body, parse_mode = html_to_plain(body), None
        chat = int(self._chat) if re.fullmatch(r"-?[0-9]+", self._chat) else self._chat
        payload = {"chat_id": chat, "text": fit_text(body), "link_preview_options": {"is_disabled": True}}
        if parse_mode:
            payload["parse_mode"] = parse_mode
        if silent:
            payload["disable_notification"] = True
        row = []
        for label, url in _pairs(buttons)[:MAX_BUTTONS]:
            safe = allowed_url(url, extra_prefixes)
            text = clean_text(label, 30)
            if safe and text:
                row.append({"text": text, "url": safe})
        if row:
            payload["reply_markup"] = {"inline_keyboard": [row]}
        return payload

    def _request(self, payload):
        url = f"{API_BASE}/bot{self._token}/sendMessage"
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8", "replace")
        return urllib.request.Request(url, data=data, method="POST",
                                      headers={"Content-Type": "application/json; charset=utf-8", "User-Agent": "chanceblog-notify"})

    @staticmethod
    def _read_json(response):
        try:
            raw = response.read(MAX_RESPONSE_BYTES)
            data = json.loads(raw.decode("utf-8", "replace"))
        except Exception:  # noqa: BLE001 - 읽을 수 없는 본문은 '본문 없음'으로 본다(내용·예외 문구를 쓰지 않는다)
            return None
        return data if isinstance(data, dict) else None

    def _post(self, payload):
        """요청 한 번. 예외는 모두 분류(timeout·network)로 바꾸고 문구를 버린다."""
        opener = self._opener or urllib.request.urlopen
        try:
            response = opener(self._request(payload), timeout=TIMEOUT_SECONDS)
        except urllib.error.HTTPError as exc:
            body, headers = self._read_json(exc), getattr(exc, "headers", None)
            status = getattr(exc, "code", None)
            try:
                exc.close()
            except Exception:  # noqa: BLE001
                pass
            return Reply("http", status if isinstance(status, int) else None, body, headers)
        except (socket.timeout, TimeoutError):
            return Reply("timeout", None, None, None)
        except urllib.error.URLError as exc:
            reason = getattr(exc, "reason", None)
            return Reply("timeout" if isinstance(reason, (socket.timeout, TimeoutError)) else "network", None, None, None)
        except Exception:  # noqa: BLE001 - OSError·http.client 오류·잘못된 주소(ValueError) 등: 문구에 요청 주소가 들어 있을 수 있어 버린다
            return Reply("network", None, None, None)
        try:
            status = getattr(response, "status", None)
            if status is None:
                status = response.getcode()
            body = self._read_json(response)
            headers = getattr(response, "headers", None)
        except Exception:  # noqa: BLE001
            return Reply("network", None, None, None)
        finally:
            try:
                response.close()
            except Exception:  # noqa: BLE001
                pass
        return Reply("ok", status if isinstance(status, int) else None, body, headers)

    @staticmethod
    def _description(reply):
        body = reply.body if isinstance(reply.body, dict) else {}
        value = body.get("description")
        return value if isinstance(value, str) else ""

    def _classify(self, reply):
        """응답 → (reason, 설명). 보냈으면 (SENT, '')."""
        if reply.kind == "timeout":
            return TIMEOUT, ""
        if reply.kind == "network":
            return NETWORK, ""
        description = self._description(reply)
        if reply.kind == "ok":
            ok = isinstance(reply.body, dict) and reply.body.get("ok") is True
            return (SENT, "") if reply.status == 200 and ok else (BAD_RESPONSE, description)
        status, lowered = reply.status, description.lower()
        if status == 400:
            if "chat not found" in lowered:
                return CHAT_NOT_FOUND, description
            if "parse entities" in lowered or "unsupported start tag" in lowered:
                return PARSE_ERROR, description
            if "button" in lowered:
                return BUTTON_ERROR, description
            return BAD_REQUEST, description
        if status == 401:
            return UNAUTHORIZED, description
        if status == 403:
            return FORBIDDEN, description
        if status == 404:
            return NOT_FOUND, description
        if status == 429:
            return RATE_LIMITED, description
        if isinstance(status, int) and status >= 500:
            return SERVER_ERROR, description
        return BAD_REQUEST, description

    @staticmethod
    def _retry_after(reply):
        """429 응답의 기다릴 시간(초): 본문의 parameters.retry_after, 없으면 Retry-After 헤더, 둘 다 없으면 1. 1~RETRY_AFTER_MAX 로 맞춘다."""
        value = None
        body = reply.body if isinstance(reply.body, dict) else {}
        params = body.get("parameters")
        if isinstance(params, dict):
            value = params.get("retry_after")
        if value is None and reply.headers is not None:
            try:
                value = reply.headers.get("Retry-After")
            except Exception:  # noqa: BLE001
                value = None
        try:
            seconds = int(float(value))
        except (TypeError, ValueError, OverflowError):
            seconds = 1
        return max(1, min(seconds, RETRY_AFTER_MAX))

    def _deliver(self, payload):
        """요청을 보내고 재시도·대체 전송을 한다. 요청은 최대 5번(처음 1 + 429 1 + 네트워크·5xx 1 + 서식 없이 1 + 버튼 없이 1)."""
        used = {"rate": False, "net": False, "parse": False, "button": False}
        while True:
            reply = self._post(payload)
            reason, description = self._classify(reply)
            if reason == SENT:
                return self._result(True, True, reply.status, SENT)
            if reason == RATE_LIMITED and not used["rate"]:
                used["rate"] = True
                self._pause(self._retry_after(reply))
                continue
            if reason in (NETWORK, TIMEOUT, SERVER_ERROR) and not used["net"]:
                used["net"] = True
                self._pause(NETWORK_RETRY_WAIT)
                continue
            if reason == PARSE_ERROR and payload.get("parse_mode") and not used["parse"]:
                used["parse"] = True
                payload = {**payload, "text": fit_text(html_to_plain(payload["text"]))}
                payload.pop("parse_mode", None)
                continue
            if reason == BUTTON_ERROR and payload.get("reply_markup") and not used["button"]:
                used["button"] = True
                payload = {key: value for key, value in payload.items() if key != "reply_markup"}
                continue
            return self._result(False, False, reply.status, reason, description or "")

    # ---- 이벤트별 알림 ---------------------------------------------------------
    def notify_chance_published(self, posts, run_info=None):
        """Chance 새 글(한·영 한 쌍) 발행 알림. posts: [{lang, title, category, source_name, url}, …] — url 은 예상 공개 주소(허용 목록이면 링크).
        run_info: {run_url(실행 기록 주소)·sha} 선택. 보낼 글이 없으면 NOT_APPLICABLE."""
        try:
            ordered = sorted((p for p in posts or () if isinstance(p, dict)), key=lambda p: 0 if p.get("lang") == "ko" else 1)
            if not ordered:
                return Result(True, False, None, NOT_APPLICABLE, "")
            text, buttons = format_chance_published(ordered, run_info or {})
            return self.send_message(text, parse_mode="HTML", buttons=buttons)
        except Exception as exc:  # noqa: BLE001
            return self._result(False, False, None, INTERNAL_ERROR, type(exc).__name__)

    def notify_draft_waiting(self, channel_label, title, where, url=None, extra_prefixes=()):
        """'발행 대기' 알림(티스토리·네이버 초안 패키지, Chance 승인 대기, Blogger 초안 공통): 어느 채널의 어떤 글을 어디서 무엇을 하면 되는지."""
        try:
            text = (f"{MEMO_MARK} <b>발행 대기</b> — {safe_text(channel_label, SHORT_LIMIT)}: {safe_text(title)}\n"
                    f"→ {safe_text(where, WHERE_LIMIT)}")
            buttons = [("열기", url)] if url else []
            return self.send_message(text, parse_mode="HTML", buttons=buttons, extra_prefixes=extra_prefixes)
        except Exception as exc:  # noqa: BLE001
            return self._result(False, False, None, INTERNAL_ERROR, type(exc).__name__)

    def notify_blogger_result(self, result_code, title, url=None, blog_label="Blogger", extra_prefixes=()):
        """Blogger 러너의 결과를 알린다. draft_uploaded → '초안함에 올라옴, 확인·게시', posted(published) → '게시됨'.
        그 밖의 결과(실패·저장소 파일만 저장 등)는 보내지 않는다 — 실패는 확인 필요 모음과 Actions 실패 알림이 맡는다."""
        try:
            label = defang_urls(clean_text(blog_label, SHORT_LIMIT)) or "Blogger"
            if result_code == "draft_uploaded":
                return self.notify_draft_waiting(label, title, "초안함에 올라왔습니다 — Blogger 대시보드 → 초안에서 확인하고 게시하세요",
                                                 url="https://www.blogger.com/")
            if result_code in ("posted", "published"):
                text = f"{OK_MARK} <b>게시됨</b> — {escape_html(label)}: {safe_text(title)}"
                return self.send_message(text, parse_mode="HTML", buttons=[("글 보기", url)] if url else [], extra_prefixes=extra_prefixes)
            return Result(True, False, None, NOT_APPLICABLE, "")
        except Exception as exc:  # noqa: BLE001
            return self._result(False, False, None, INTERNAL_ERROR, type(exc).__name__)

    def notify_ops_alert(self, item_lines, inbox_url, count=None):
        """확인 필요 모음의 '새로 해야 할 일'을 평문 한 통으로. item_lines: 항목 제목 줄들(외부 글이 섞여 있으니 여기서 한 번 더 소독한다)."""
        try:
            lines = []
            for line in item_lines or ():
                cleaned = defang_urls(clean_text(line, LINE_LIMIT))
                if cleaned:
                    lines.append(cleaned)
                if len(lines) >= MAX_LINES:
                    break
            if not lines:
                return Result(True, False, None, NOT_APPLICABLE, "")
            number = count if isinstance(count, int) and not isinstance(count, bool) and count > 0 else len(lines)
            text = f"{PIN_MARK} 확인 필요 모음 — 새로 해야 할 일 {number}건\n" + "\n".join(f"• {line}" for line in lines)
            return self.send_message(text, buttons=[("확인 필요 모음 열기", inbox_url)] if inbox_url else [])
        except Exception as exc:  # noqa: BLE001
            return self._result(False, False, None, INTERNAL_ERROR, type(exc).__name__)

    def notify_test(self, now=None):
        """연결 확인 한 통(평문)."""
        try:
            kst = (now or datetime.now(timezone.utc)).astimezone(timezone(timedelta(hours=9)))
            text = (f"{OK_MARK} 알림 연결 확인\n챈스블로그의 새 글·발행 대기·확인 필요 알림이 이 채팅으로 옵니다.\n"
                    f"시험 시각: {kst:%Y-%m-%d %H:%M} KST")
            return self.send_message(text)
        except Exception as exc:  # noqa: BLE001
            return self._result(False, False, None, INTERNAL_ERROR, type(exc).__name__)


# ---- 메시지 모양(순수 함수: 네트워크 없이 시험한다) ------------------------------------
def format_chance_published(posts, run_info):
    """새 글 알림의 (HTML 글, 버튼 목록). posts 는 한글 글이 앞."""
    lines = [f"{OK_MARK} <b>새 글이 발행됐습니다</b>"]
    categories, source, links, buttons = [], "", [], []
    for post in posts:
        lang = "ko" if post.get("lang") == "ko" else "en"
        lines.append(f"{FLAGS[lang]} {safe_text(post.get('title'))}")
        category = defang_urls(clean_text(post.get("category"), SHORT_LIMIT))
        if category and category not in categories:
            categories.append(category)
        source = source or defang_urls(clean_text(post.get("source_name"), SHORT_LIMIT))
        url = allowed_url(post.get("url"))
        if url:
            links.append(escape_html(url))
            buttons.append(("한글 글" if lang == "ko" else "English", url))
        elif post.get("url"):
            links.append(escape_html(defang_urls(clean_text(post.get("url"), LINE_LIMIT))) + " (허용 목록 밖 주소라 링크로 걸지 않았습니다)")
    lines.append("")
    if categories:
        lines.append(f"분야: {escape_html(' · '.join(categories))}")
    if source:
        lines.append(f"출처: {escape_html(source)}")
    lines.append(f"{WAIT_MARK} {DEPLOY_WAIT_NOTE}")
    lines.extend(links)
    run_url = allowed_url(run_info.get("run_url"))
    if run_url:
        lines.append(f'실행 기록: <a href="{html.escape(run_url, quote=True)}">열기</a>')
    return "\n".join(lines), buttons


# ---- 모듈 수준 함수(작업 지시의 공개 이름) ------------------------------------------------
def send_message(text, parse_mode=None, buttons=None, silent=False, notifier=None):
    return (notifier or Notifier()).send_message(text, parse_mode=parse_mode, buttons=buttons, silent=silent)


def notify_chance_published(posts, run_info=None, notifier=None):
    return (notifier or Notifier()).notify_chance_published(posts, run_info)


def notify_draft_waiting(channel_label, title, where, url=None, notifier=None):
    """호출 자리: 티스토리·네이버 초안 패키지(작업 C)와 Chance 승인 대기(작업 E)가 초안을 만든 직후 이 함수를 부른다(총괄이 병합 뒤 잇는다)."""
    return (notifier or Notifier()).notify_draft_waiting(channel_label, title, where, url=url)


def notify_blogger_result(result_code, title, url=None, blog_label="Blogger", extra_prefixes=(), notifier=None):
    return (notifier or Notifier()).notify_blogger_result(result_code, title, url=url, blog_label=blog_label, extra_prefixes=extra_prefixes)


def notify_ops_alert(item_lines, inbox_url, count=None, notifier=None):
    return (notifier or Notifier()).notify_ops_alert(item_lines, inbox_url, count=count)


def notify_test(notifier=None, now=None):
    return (notifier or Notifier()).notify_test(now=now)


def describe(result):
    """호출한 쪽의 로그에 남길 한 줄 설명(분류·HTTP 상태·소독한 설명). 값(토큰·채팅 ID)은 없다."""
    text = REASON_TEXT.get(result.reason, result.reason)
    extra = ", ".join(part for part in (f"HTTP {result.status}" if result.status else "", result.detail) if part)
    return text + (f" [{extra}]" if extra else "")


def log_result(result, out, label="텔레그램 알림"):
    """다른 프로그램(Blogger 러너·점검 모음)이 자기 로그에 알림 결과를 남긴다. 비활성·해당 없음은 아무것도 쓰지 않는다(시크릿이 없을 때 기존 출력이 그대로이도록).
    보냈으면 한 줄, 실패면 원인 한 줄과 고정 문장 ::warning::(확인 필요 모음이 초록 실행의 경고로 모은다)."""
    if result.reason in (DISABLED, NOT_APPLICABLE):
        return
    if result.sent:
        out(f"[참고] {label}: 보냈습니다")
        return
    out(f"[참고] {label}을 보내지 못했습니다 — {describe(result)}")
    out(WARNING_LINE)


# ---- 새 글 찾기(chance-published) ----------------------------------------------------------
_NAME_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})-(.+)\.md$")
_PAIR_RE = re.compile(r"^(KR|EN)-(\d{6})$")
_FM_KEYS = ("title", "lang", "category", "source_name", "published", "date", "permalink", "slug")
_FM_LINE = re.compile(r"""^(?P<q>["']?)(?P<key>[A-Za-z_][A-Za-z0-9_-]*)(?P=q)[ \t]*:(?:[ \t]+(?P<value>.*))?$""")
_FALSE_WORDS = frozenset({"false", "no", "off", "null", "~"})
_COMMIT_RE = re.compile(r"HEAD|[0-9a-fA-F]{7,40}")
_BOM = chr(0xFEFF)


class GitError(Exception):
    """git 호출 실패. 문구에는 외부 값이 없고 이유 분류만 있다."""


def _scalar(raw):
    """front matter 한 줄 스칼라 값 → 문자열. 읽을 수 없는 모양(블록·목록·앵커)이면 None."""
    raw = (raw or "").strip()
    if not raw:
        return None
    quote = raw[0]
    if quote in "\"'":
        i = 1
        while i < len(raw):
            char = raw[i]
            if quote == '"' and char == "\\":
                i += 2
                continue
            if char == quote:
                if quote == "'" and raw[i + 1:i + 2] == "'":
                    i += 2
                    continue
                break
            i += 1
        else:
            return None
        inner = raw[1:i]
        if quote == "'":
            return inner.replace("''", "'")
        try:
            return json.loads('"' + inner + '"')
        except ValueError:
            return inner
    if quote in "|>[{&*!%@`#":
        return None
    comment = re.search(r"\s#", raw)
    return (raw[:comment.start()] if comment else raw).strip() or None


def parse_front_matter(text):
    """글 맨 앞 front matter 에서 제목·언어·분야·출처 이름·공개 여부·날짜·permalink·slug 만 읽는다(한 줄 `키: 값` 모양만). 없으면 {}."""
    lines = str(text).lstrip(_BOM).splitlines()
    if not lines or lines[0].rstrip() != "---":
        return {}
    found = {}
    for line in lines[1:]:
        if line.rstrip() in ("---", "..."):
            break
        match = _FM_LINE.match(line)
        if match and match.group("key") in _FM_KEYS:
            key, value = match.group("key"), _scalar(match.group("value"))
            if key == "published" and value is None and not re.sub(r"(?:^|\s)#.*$", "", match.group("value") or "").strip():
                value = "null"      # `published:` 처럼 비면 YAML null 이고 Jekyll 은 그 글을 공개하지 않는다
            found[key] = value
    return found


def is_unpublished(front):
    value = front.get("published")
    return value is not None and str(value).lower() in _FALSE_WORDS


def _git(root, *args, runner=subprocess.run):
    try:
        done = runner(["git", *args], cwd=str(root), capture_output=True, timeout=GIT_TIMEOUT, check=False)
    except (OSError, subprocess.SubprocessError):
        raise GitError("git 을 실행하지 못했습니다") from None
    if done.returncode != 0:
        raise GitError("git 명령이 실패했습니다")
    return done.stdout


def added_posts(root, commit, runner=subprocess.run):
    """commit 이 새로 더한 `_posts/**.md` 파일 경로 목록(앞 MAX_NEW_FILES 개). 부모 커밋이 없으면(얕은 복제의 맨 끝 등) GitError —
    그때 diff-tree 는 저장소 전체를 '새 파일'로 보여 수십 편을 새 글로 오인하게 된다."""
    parents = _git(root, "rev-list", "--parents", "-n", "1", commit, runner=runner).decode("utf-8", "replace").split()
    if len(parents) < 2:
        raise GitError("부모 커밋이 없어 새 글을 가릴 수 없습니다")
    raw = _git(root, "diff-tree", "--no-commit-id", "--name-status", "-r", "-z", commit, runner=runner).decode("utf-8", "replace")
    tokens = raw.split("\0")
    paths = []
    for index in range(0, len(tokens) - 1, 2):
        status, path = tokens[index], tokens[index + 1]
        name = path.rsplit("/", 1)[-1]
        if status == "A" and path.startswith("_posts/") and _NAME_RE.match(name):
            paths.append(path)
    return paths[:MAX_NEW_FILES]


def read_blob(root, commit, path, runner=subprocess.run):
    """commit 시점의 파일 앞부분(front matter 를 읽는 만큼). 작업 트리가 아니라 git 객체에서 읽는다(심볼릭 링크로 밖의 파일을 읽지 않게)."""
    return _git(root, "cat-file", "blob", f"{commit}:{path}", runner=runner)[:65536].decode("utf-8", "replace")


_PAGES = None


def _pages_module():
    """주소 계산은 scripts/verify_pages_deploy.py 의 검증된 구현(배포 확인이 열어 보는 주소와 같은 규칙)을 쓴다. 파일 경로로 직접 읽어 sys.path 를
    건드리지 않고(같은 이름의 다른 패키지가 끼어들 수 없다), 못 읽으면 None — 그때는 주소 없이 알린다."""
    global _PAGES
    if _PAGES is None:
        try:
            spec = importlib.util.spec_from_file_location("_chanceblog_verify_pages_deploy", ROOT / "scripts" / "verify_pages_deploy.py")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            _PAGES = module
        except Exception:  # noqa: BLE001
            _PAGES = False
    return _PAGES or None


def site_base(root):
    """`_config.yml` 의 url·baseurl 로 만든 사이트 주소(끝 슬래시 포함). 못 읽으면 빈 문자열."""
    try:
        text = (Path(root) / "_config.yml").read_text(encoding="utf-8", errors="replace")[:262144].lstrip(_BOM)
    except OSError:
        return ""
    values = {}
    for line in text.splitlines():
        match = re.match(r"^(url|baseurl)[ \t]*:(?:[ \t]+(.*))?$", line)
        if match:
            values[match.group(1)] = _scalar(match.group(2))
    base = (values.get("url") or "").rstrip("/")
    if not base:
        return ""
    path = (values.get("baseurl") or "").strip("/")
    return base + "/" + (path + "/" if path else "")


def expected_post_url(root, path, front, base=None):
    """새 글의 예상 공개 주소(배포 전이라 아직 열리지 않을 수 있다). 계산할 수 없으면 빈 문자열."""
    pages = _pages_module()
    base = site_base(root) if base is None else base
    match = _NAME_RE.match(path.rsplit("/", 1)[-1])
    if pages is None or not base or not match:
        return ""
    try:
        file_date = date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        keep = {key: front[key] for key in ("published", "date", "permalink", "slug") if key in front}
        post = pages.Post(path, path.rsplit("/", 1)[-1], file_date, match.group(4), keep)
        config = pages.read_site_config(root)
        url, _why = pages.expected_url(base, post, config, pages.site_timezone(config))
    except Exception:  # noqa: BLE001
        return ""
    return url or ""


def collect_new_posts(root, commit, runner=subprocess.run):
    """commit 이 새로 올린 공개 글을 (날짜·시각) 쌍으로 묶어 돌려준다: [[{lang, title, category, source_name, url}, …], …].
    `published: false` 글은 사이트에 열리지 않으므로 알리지 않는다."""
    base = site_base(root)
    groups = {}
    for path in added_posts(root, commit, runner=runner):
        front = parse_front_matter(read_blob(root, commit, path, runner=runner))
        if not front or is_unpublished(front):
            continue
        name = path.rsplit("/", 1)[-1]
        match = _NAME_RE.match(name)
        pair = _PAIR_RE.match(match.group(4))
        lang = front.get("lang") if front.get("lang") in ("ko", "en") else ("ko" if pair and pair.group(1) == "KR" else "en")
        key = (match.group(1) + match.group(2) + match.group(3), pair.group(2) if pair else name)
        groups.setdefault(key, []).append({
            "lang": lang, "title": front.get("title") or "", "category": front.get("category") or "",
            "source_name": front.get("source_name") or "", "url": expected_post_url(root, path, front, base)})
    return [groups[key] for key in sorted(groups)]


def _run_info(environ):
    """Actions 가 주는 공개 값으로 실행 기록 주소를 만든다(허용 목록을 통과해야 링크가 된다)."""
    repo, run_id = str(environ.get("GITHUB_REPOSITORY") or ""), str(environ.get("GITHUB_RUN_ID") or "")
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9._-]{1,100}", repo) and re.fullmatch(r"[0-9]{1,20}", run_id):
        return {"run_url": f"https://github.com/{repo}/actions/runs/{run_id}"}
    return {}


# ---- 명령 줄 -------------------------------------------------------------------------
def _write_summary(environ, text, out):
    target = environ.get("GITHUB_STEP_SUMMARY")
    if not target:
        return
    try:
        with open(target, "a", encoding="utf-8") as fh:
            fh.write(text.rstrip() + "\n\n")
    except OSError as exc:
        out(f"[참고] 실행 요약 쓰기 실패({type(exc).__name__})")


def _say(out, notifier, text):
    out(notifier.scrub(text))


def run_chance_published(commit, notifier, root, out, environ, runner=subprocess.run):
    if not notifier.enabled:
        out(SKIP_LINE)
        return 0
    try:
        groups = collect_new_posts(root, commit, runner=runner)
    except GitError as exc:
        _say(out, notifier, f"텔레그램 알림: 새 글을 찾지 못해 보내지 않았습니다 — {exc}")
        out(WARNING_LINE)
        return 0
    if not groups:
        out("텔레그램 알림: 이 커밋에 새로 공개되는 글이 없어 보내지 않았습니다")
        return 0
    info = _run_info(environ)
    failed = 0
    for posts in groups:
        result = notifier.notify_chance_published(posts, info)
        if result.sent:
            out(f"텔레그램 알림: 새 글 {len(posts)}편을 알렸습니다")
        else:
            failed += 1
            _say(out, notifier, f"텔레그램 알림: 새 글 알림을 보내지 못했습니다 — {describe(result)}")
    if failed:
        out(WARNING_LINE)
    return 0


def run_status(notifier, environ, out):
    names = (ENV_TOKEN, ENV_CHAT)
    present = {name: bool(str(environ.get(name) or "").strip()) for name in names}
    rows = [f"| `{name}` | {'등록됨' if present[name] else '없음'} |" for name in names]
    for name in names:
        out(f"{name}: {'등록됨' if present[name] else '없음'}")
    ready = all(present.values())
    _write_summary(environ, "### 텔레그램 시크릿 등록 여부\n\n| 시크릿 이름 | 상태 |\n|---|---|\n" + "\n".join(rows) + "\n\n"
                   + ("두 시크릿이 모두 등록돼 있어 다음 단계에서 시험 메시지를 보냅니다(값은 이 화면에 나오지 않습니다)." if ready else
                      "**시크릿이 모두 등록돼 있지 않아 시험 메시지를 보내지 않습니다.** 저장소 Settings → Secrets and variables → Actions 에서 "
                      "위 두 이름을 등록한 뒤 다시 실행하세요(`.github/editorial/TELEGRAM_SETUP.md`)."), out)
    target = environ.get("GITHUB_OUTPUT")
    if target:
        try:
            with open(target, "a", encoding="utf-8") as fh:
                fh.write(f"ready={'true' if ready else 'false'}\n")
        except OSError as exc:
            out(f"[참고] 단계 출력 쓰기 실패({type(exc).__name__})")
    return 0


def run_test(notifier, environ, out, now=None):
    if not notifier.enabled:
        out(SKIP_LINE)
        _write_summary(environ, "### 텔레그램 알림 시험\n\n- 결과: **시크릿 없음** — 시험 메시지를 보내지 않았습니다.", out)
        return 0
    result = notifier.notify_test(now=now)
    if result.sent:
        out("텔레그램 알림 시험: 성공 — 휴대폰에서 '알림 연결 확인' 메시지를 확인하세요")
        _write_summary(environ, "### 텔레그램 알림 시험\n\n- 결과: **성공** — 휴대폰 텔레그램에 '알림 연결 확인' 메시지가 도착했는지 확인하세요. "
                                "도착하지 않으면 휴대폰의 텔레그램 알림 설정(방해 금지 모드 등)과 봇 대화방 알림을 확인하세요.", out)
        return 0
    out(notifier.scrub(f"텔레그램 알림 시험: 실패 — {describe(result)}"))
    out(ERROR_LINE)
    _write_summary(environ, "### 텔레그램 알림 시험\n\n- 결과: **실패**\n"
                            f"- 분류: `{result.reason}`" + (f" · HTTP {result.status}" if result.status else "") + "\n"
                            f"- 원인과 조치: {md_cell(REASON_TEXT.get(result.reason, result.reason), 300)}\n"
                            + (f"- 텔레그램이 준 설명: {md_cell(result.detail, 160)}\n" if result.detail else "")
                            + "- 값(토큰·채팅 ID)은 이 화면에 나오지 않습니다. 시크릿을 고쳤다면 이 워크플로를 다시 실행하세요.", out)
    return 1


USAGE_ERROR_LINE = "사용법 오류: 이 명령은 chance-published [--commit HEAD|커밋 해시]·test·status 만 받습니다(제목·토큰 같은 값은 명령 줄이 아니라 git·환경변수에서만 읽습니다)"


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        """argparse 의 기본 오류는 잘못 넘긴 인자를 그대로 메시지에 싣는다 — 실수로 명령 줄에 넘긴 값(토큰 같은)이 로그에 남지 않게 고정 문장만 낸다."""
        self.print_usage(sys.stderr)
        sys.stderr.write(USAGE_ERROR_LINE + "\n")
        raise SystemExit(2)


def build_parser():
    parser = _Parser(prog="python -m pipeline.notify", description="텔레그램 알림(새 글·발행 대기·확인 필요)")
    sub = parser.add_subparsers(dest="event", required=True)
    published = sub.add_parser("chance-published", help="방금 push 한 커밋이 올린 Chance 새 글(한·영 한 쌍)을 알린다")
    published.add_argument("--commit", default="HEAD", help="HEAD 또는 커밋 해시(7~40자리 16진수). 제목 같은 외부 값은 받지 않는다")
    sub.add_parser("test", help="연결 확인 메시지 한 통을 보낸다")
    sub.add_parser("status", help="시크릿 두 개가 등록돼 있는지(이름별 등록됨/없음)만 알린다")
    return parser


def main(argv=None, environ=None, out=print, root=None, runner=subprocess.run, opener=None, sleep=None, clock=None, budget=None, now=None):
    safe_output()
    environ = os.environ if environ is None else environ
    args = build_parser().parse_args(argv)
    notifier = Notifier(environ, opener=opener, sleep=sleep, clock=clock, budget=budget)
    root = Path(root) if root is not None else ROOT
    try:
        if args.event == "status":
            return run_status(notifier, environ, out)
        if args.event == "test":
            return run_test(notifier, environ, out, now=now)
        if not _COMMIT_RE.fullmatch(args.commit):
            out("[사용법 오류] --commit 은 HEAD 또는 7~40자리 16진수 커밋 해시여야 합니다")
            return 2
        return run_chance_published(args.commit, notifier, root, out, environ, runner=runner)
    except Exception as exc:  # noqa: BLE001 - 알림은 보조다: 예기치 않은 오류도 클래스 이름만 남기고 끝낸다(예외 문구에 주소가 있을 수 있다)
        out(f"텔레그램 알림: 예기치 않은 오류({type(exc).__name__}) — 글 게시에는 영향이 없습니다")
        out(WARNING_LINE)
        return 1 if args.event == "test" else 0


if __name__ == "__main__":
    sys.exit(main())
