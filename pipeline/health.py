"""발행 중단·반복 실패 감시 규칙 (순수 함수: I/O 없음 → 단위 테스트 가능).

풀오토는 '조용히 멈추는 것'이 가장 큰 위험이다. 이 모듈은 상태(이력·마지막 커밋·최근 실행 결과)를
받아 사람이 개입해야 하는 상황만 Finding 으로 돌려준다. 이슈 생성은 scripts/watchdog.py 가 맡는다.
"""
from dataclasses import dataclass
from datetime import date, datetime, timezone

from pipeline.state import KST

# 파이프라인이 살아 있고 산출물을 만든 상태. generated_unpublished 도 포함한다
# (게시 시크릿이 없어도 초안은 만들어지며, 미게시는 UNPUBLISHED 가 따로 알린다).
OK_STATUSES = {"posted", "draft", "generated_unpublished"}
FAIL_STATUSES = {"publish_failed", "llm_failed"}
REJECT_STREAK = 5


@dataclass(frozen=True)
class Finding:
    blog: str
    code: str
    severity: str  # "critical" | "warning"
    message: str

    @property
    def title(self):
        return f"[Watchdog] {self.blog}: {self.code}"


def _aware(dt):
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def entry_time(entry):
    """이력 항목의 시각. generated_at 이 없으면 date 의 KST 하루 끝(오탐을 줄이려고 보수적으로)."""
    value = entry.get("generated_at")
    if isinstance(value, str) and value:
        try:
            return _aware(datetime.fromisoformat(value.replace("Z", "+00:00")))
        except ValueError:
            pass
    value = entry.get("date")
    if isinstance(value, str) and value:
        try:
            day = date.fromisoformat(value[:10])
            return datetime(day.year, day.month, day.day, 23, 59, 59, tzinfo=KST)
        except ValueError:
            return None
    return None


def evaluate(blog, history, now, last_content_commit=None, recent_runs=()):
    """한 블로그의 문제 목록. recent_runs 는 최신순 [{'conclusion': ..}, ...]."""
    if blog.get("mode") == "off":
        return []
    key = blog["key"]
    cfg = blog.get("health", {})
    gap_hours = cfg.get("max_gap_hours", 48)
    streak_n = cfg.get("max_failure_streak", 3)
    now = _aware(now)
    entries = [e for e in history if isinstance(e, dict)]
    findings = []

    # 1) 발행 중단
    ok_times = [entry_time(e) for e in entries if e.get("status", "posted") in OK_STATUSES]
    candidates = [t for t in ok_times if t]
    if last_content_commit:
        candidates.append(_aware(last_content_commit))
    if not candidates:
        findings.append(Finding(key, "NO_ACTIVITY", "warning",
                                "발행/초안 기록이 전혀 없습니다. 워크플로가 한 번도 성공하지 않았을 수 있습니다."))
    else:
        last = max(candidates)
        hours = (now - last).total_seconds() / 3600
        if hours > gap_hours:
            findings.append(Finding(key, "STALE", "critical",
                                    f"마지막 활동({last.astimezone(KST):%Y-%m-%d %H:%M} KST) 이후 {hours:.0f}시간 경과 "
                                    f"(허용 {gap_hours}시간)."))

    # 2) 연속 실패 / 연속 게이트 탈락 / 시크릿 미등록
    statuses = [e.get("status") for e in entries if e.get("status")]
    if len(statuses) >= streak_n and all(s in FAIL_STATUSES for s in statuses[-streak_n:]):
        findings.append(Finding(key, "FAIL_STREAK", "critical",
                                f"최근 {streak_n}회 연속 실패({', '.join(statuses[-streak_n:])}). "
                                "LLM 키·할당량·OAuth 토큰(만료) 확인이 필요합니다."))
    if len(statuses) >= REJECT_STREAK and all(s == "rejected" for s in statuses[-REJECT_STREAK:]):
        findings.append(Finding(key, "REJECT_STREAK", "warning",
                                f"최근 {REJECT_STREAK}회 연속 게이트 탈락. 프롬프트·프로필 기준 점검이 필요합니다."))
    unpub_n = cfg.get("max_unpublished_days")
    if (unpub_n and blog.get("mode") == "auto" and len(statuses) >= unpub_n
            and all(s == "generated_unpublished" for s in statuses[-unpub_n:])):
        findings.append(Finding(key, "UNPUBLISHED", "warning",
                                f"최근 {unpub_n}회 모두 초안만 생성됐습니다. 게시 시크릿(BLOGGER_*) 미등록이 원인일 수 있습니다 "
                                "(HANDLER.md §10)."))

    # 3) 워크플로 실행 결과 연속 실패
    done = [r for r in recent_runs if r.get("conclusion") in ("success", "failure")]
    if len(done) >= streak_n and all(r["conclusion"] == "failure" for r in done[:streak_n]):
        findings.append(Finding(key, "RUN_FAIL_STREAK", "critical",
                                f"워크플로가 최근 {streak_n}회 연속 실패했습니다. Actions 로그를 확인하세요."))
    return findings
