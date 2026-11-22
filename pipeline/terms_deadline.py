"""약관 점검 기한 경고 — 켜진 허용 목록 제공처의 점검 기한(snapshot.expires_at)이 가까워지면 미리 알리는 순수 규칙(L7, D-360, docs/OPS_INBOX.md §11).

허용 목록(pipeline/source_registry.json)에서 켜진(enabled) 제공처는 약관 점검 기한이 지나면 ACTIVE 가 아니라 자동 글감에서 빠진다(pipeline/source_registry.py 의 A4 — 기한 당일까지는 유효).
지금까지는 기한이 다가오는 것을 알리는 곳이 없었고 지난 뒤에도 운영 알림에는 뜨지 않았다(생성기의 Fact 분기가 FACT_NOT_READY 로 초록으로 조용히 끝날 뿐이다).
이 모듈은 남은 날 수를 계산해 경고가 필요한 제공처를 고른다 — 오늘은 값으로 받고(시계를 읽지 않는다), 파일·네트워크·환경 변수를 쓰지 않으며 표준 라이브러리만 쓴다.
파일 읽기와 알림은 부르는 쪽(scripts/ops_inbox.py·scripts/watchdog.py)이 맡는다.

상태(Notice.state)
  expiring  남은 날이 0 이상 WARN_DAYS(14) 이하다(기한 당일 포함). 아직 유효하다 — 미리 알린다.
  expired   기한이 어제 이전이다. 그 제공처는 이미 ACTIVE 가 아니다.
  missing   켜진 제공처인데 기한이 없거나 날짜로 읽을 수 없다. 기한을 확인할 수 없어 ACTIVE 가 될 수 없다(A4).
꺼진 제공처(enabled 가 참이 아님)는 기한이 있어도 대상이 아니다 — A4 와 같은 규칙이다.
"""
import datetime
import re
from collections import namedtuple

WARN_DAYS = 14                                      # 기한이 이 날 수 안으로 다가오면 미리 알린다(기한 당일은 0일 남음)
EXPIRING, EXPIRED, MISSING = "expiring", "expired", "missing"
FINDING_CODES = ("SOURCE_TERMS_EXPIRING", "SOURCE_TERMS_EXPIRED")      # 워치독 알림의 코드(scripts/watchdog.py) — 확인 필요 모음이 같은 사실을 두 줄로 싣지 않으려고 쓴다
FINDING_BLOG = "공통"                                # 워치독 알림의 '블로그' 자리(허용 목록은 블로그 하나의 것이 아니다)
NAME_LIMIT = 60
_DAY_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
_ID_RE = re.compile(r"[a-z][a-z0-9_]{1,63}")        # 허용 목록의 provider_id 모양(pipeline/source_registry.py 와 같다) — 이 모양이 아닌 항목은 목록 검증이 따로 거절한다

Notice = namedtuple("Notice", "provider_id name expires_at days_left state")


def parse_day(value):
    """날짜(date·datetime) 또는 YYYY-MM-DD 글자를 date 로. 없음·다른 모양·없는 날짜는 None. 파이썬 3.10 과 3.12 가 같게 읽도록 모양을 먼저 정규식으로 거른다(3.11 부터 fromisoformat 이 더 넓게 받는다)."""
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    if not isinstance(value, str) or not _DAY_RE.fullmatch(value):
        return None
    try:
        return datetime.date.fromisoformat(value)
    except ValueError:
        return None


def days_left(expires_at, today):
    """점검 기한까지 남은 날 수(기한 당일 0, 하루 지났으면 -1). 기한을 날짜로 읽을 수 없으면 None. today 를 날짜로 읽을 수 없으면 ValueError(부르는 쪽의 버그다 — 시계를 대신 읽지 않는다)."""
    now = parse_day(today)
    if now is None:
        raise ValueError("today 는 날짜(date 또는 YYYY-MM-DD)여야 합니다")
    day = parse_day(expires_at)
    return None if day is None else (day - now).days


def state_of(left, warn_days=WARN_DAYS):
    """남은 날 수 → 상태. 경고가 필요 없으면(기한이 warn_days 보다 멀다) None."""
    if left is None:
        return MISSING
    if left < 0:
        return EXPIRED
    return EXPIRING if left <= warn_days else None


def notices(providers, today, warn_days=WARN_DAYS):
    """켜진 제공처 가운데 경고가 필요한 것 → Notice 목록(만료·기한 없음 → 임박 순, 같으면 기한·이름 순 — 입력 순서와 무관하게 항상 같은 결과).
    providers 는 허용 목록 파일의 providers 배열(JSON 을 읽은 값)이다. 배열이 아니면 ValueError. 사전이 아닌 항목·provider_id 모양이 틀린 항목은 건너뛴다(목록 검증이 따로 거절한다).
    enabled 가 참(true)인 제공처만 본다 — 'true' 글자나 1 은 켜진 것이 아니다."""
    if not isinstance(providers, (list, tuple)):
        raise ValueError("providers 는 배열이어야 합니다")
    found = []
    for raw in providers:
        if not isinstance(raw, dict) or raw.get("enabled") is not True:
            continue
        provider_id = raw.get("provider_id")
        if not isinstance(provider_id, str) or not _ID_RE.fullmatch(provider_id):
            continue
        snapshot = raw.get("snapshot") if isinstance(raw.get("snapshot"), dict) else {}
        expires_at = snapshot.get("expires_at")
        left = days_left(expires_at, today)
        state = state_of(left, warn_days)
        if state is None:
            continue
        name = raw.get("name") if isinstance(raw.get("name"), str) else ""
        shown = expires_at if isinstance(expires_at, str) and left is not None else ""        # 날짜로 읽힌 글(숫자 열 자리)만 싣는다 — 읽을 수 없는 값은 파일의 글이라 알림에 옮기지 않는다
        found.append(Notice(provider_id, " ".join(name.split())[:NAME_LIMIT], shown, left, state))
    rank = {EXPIRED: 0, MISSING: 0, EXPIRING: 1}
    return sorted(found, key=lambda n: (rank[n.state], n.days_left if n.days_left is not None else -10 ** 9, n.expires_at, n.provider_id))


def left_text(notice):
    """남은 날 수의 사람이 읽는 글: '오늘이 마지막 날'·'3일 남음'·'2일 지남'·'기한 없음'."""
    if notice.days_left is None:
        return "기한 없음"
    if notice.days_left == 0:
        return "오늘이 마지막 날"
    return f"{notice.days_left}일 남음" if notice.days_left > 0 else f"{-notice.days_left}일 지남"
