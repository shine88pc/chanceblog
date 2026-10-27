"""발행 중단·반복 실패 감시 규칙 (순수 함수: I/O 없음 → 단위 테스트 가능).

풀오토는 '조용히 멈추는 것'이 가장 큰 위험이다. 이 모듈은 상태(이력·마지막 커밋·최근 실행 결과)를
받아 사람이 개입해야 하는 상황만 Finding 으로 돌려준다. 이슈 생성은 scripts/watchdog.py 가 맡는다.
"""
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from pipeline.state import KST

# 파이프라인이 살아 있고 산출물을 만든 상태. generated_unpublished 도 포함한다
# (게시 시크릿이 없어도 초안은 만들어지며, 미게시는 UNPUBLISHED 가 따로 알린다). package_issued 는 티스토리·네이버 초안 패키지(GitHub 이슈)를
# 만든 상태다(pipeline/run.py): 글을 만든 날이므로 STALE·NO_ACTIVITY 를 가린다.
OK_STATUSES = {"posted", "draft", "draft_uploaded", "generated_unpublished", "package_issued"}
# 실제로 독자에게 가는(또는 Blogger 초안함에 올라간) 상태. 저장소 파일로만 남은 초안(draft, generated_unpublished)은 제외한다.
# NO_POSTS_DAY 는 이것만 센다(초안이 쌓이는 것을 '글이 나왔다'로 오해하지 않기 위해).
# draft_uploaded 는 Blogger '초안 모드'(mode draft + 게시용 시크릿 → 초안을 Blogger 초안함에 올림, pipeline/run.py 가 기록한다)의
# 상태 이름이다. '글이 나온 날'로 센다(tests/test_health_daily.py 가 글이 있는 날/없는 날로 고정한다). 이름을 지우거나 바꾸면
# 그 테스트가 실패해야 한다. 주의: Blogger 화면에서 초안을 방치해도 이 감시는 모른다(초안 방치 경고는 별도 작업).
# package_issued 도 같은 부류다(운영자에게 초안 이슈가 갔다). 이슈를 열어 둔 채 방치하는 것도 이 감시는 모른다(초안 현황판 몫).
REAL_POST_STATUSES = {"posted", "draft_uploaded", "package_issued"}
FAIL_STATUSES = {"publish_failed", "llm_failed"}
REJECT_STREAK = 5
PAGES_GRACE_MINUTES = 30
# 글 커밋 시각은 러너 시계, Pages 실행 생성 시각은 GitHub 서버 시계다. 정상 배포는 커밋 2~3초 뒤에 시작하므로 두 시계가
# 2초만 어긋나도 '배포가 커밋보다 먼저'로 보여 PAGES_NOT_DEPLOYED(심각)를 오판한다. 비교에 이만큼 여유를 둔다.
PAGES_CLOCK_SKEW_SECONDS = 120


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


def entry_time(entry, end_of_day=True):
    """이력 항목의 시각. generated_at 이 없으면 date 의 KST 하루 끝(오탐을 줄이려고 보수적으로).
    end_of_day=False 면 날짜만 있는 항목은 시각을 알 수 없으므로 None(커밋 시각처럼 정확한 값이 따로 있을 때)."""
    value = entry.get("generated_at")
    if isinstance(value, str) and value:
        try:
            return _aware(datetime.fromisoformat(value.replace("Z", "+00:00")))
        except ValueError:
            pass
    value = entry.get("date")
    if end_of_day and isinstance(value, str) and value:
        try:
            day = date.fromisoformat(value[:10])
            return datetime(day.year, day.month, day.day, 23, 59, 59, tzinfo=KST)
        except ValueError:
            return None
    return None


def entry_day(entry):
    """이력 항목이 속한 KST 날짜(없으면 None)."""
    value = entry.get("date")
    if isinstance(value, str) and value:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            pass
    when = entry_time(entry)
    return when.astimezone(KST).date() if when else None


def post_days_from_history(entries, drafts_count=True):
    """실제로 글이 나온 KST 날짜 집합(상태 없는 옛 항목은 정상 발행으로 본다).
    승인 흐름(flow=pr)의 이력 항목은 초안을 만든 날에 생기고 글은 병합할 때 main 에 올라간다. 글 커밋 날짜를 따로 알 때는 drafts_count=False 로
    초안 항목을 빼서 '병합하지 않은 초안'이 글이 나온 날로 세어지지 않게 한다."""
    days = set()
    for e in entries:
        if e.get("status", "posted") in REAL_POST_STATUSES and (drafts_count or e.get("flow") != "pr"):
            day = entry_day(e)
            if day:
                days.add(day)
    return days


def _parse_utc(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        return _aware(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except ValueError:
        return None


def _waiting_message(pending, now):
    """승인 대기 초안 문구: 대기 N건과 가장 오래된 초안이 기다린 시간(하루 넘으면 일, 아니면 시간)."""
    ages = [now - t for t in (_parse_utc(d.get("created_at")) for d in pending if isinstance(d, dict)) if t is not None]
    waited = ""
    if ages:
        hours = max(max(ages).total_seconds(), 0) / 3600
        waited = f"(가장 오래된 것 {int(hours // 24)}일 전)" if hours >= 24 else f"(가장 오래된 것 {int(hours)}시간 전)"
    return (f"승인(PR 병합)을 기다리는 초안이 {len(pending)}건 있습니다{waited}. 새 글이 안 나온 것은 멈춤이 아니라 승인 대기입니다 — "
            "병합하면 공개, 닫으면 폐기됩니다. 오래 두면 글감이 낡습니다.")


def evaluate(blog, history, now, last_content_commit=None, recent_runs=(), post_days=None, pages_runs=None, pending_drafts=None):
    """한 블로그의 문제 목록. recent_runs 는 최신순 [{'conclusion': ..}, ...].
    post_days: 새 글이 나온 KST 날짜 집합(없으면 이력에서 계산, jekyll-git 은 '글 파일이 추가된 커밋'에서 구해 넘긴다).
    pages_runs: Pages 배포 워크플로의 최근 완료 실행(최신순, {'conclusion','created_at'}). 없으면 배포 검사를 하지 않는다.
    pending_drafts: 승인 흐름(publish_flow: pr)에서 열려 있는 초안 PR 목록([{'created_at': ISO}, ...]). 없거나 비어 있으면 아무것도 바꾸지 않는다.
    있으면 '글이 안 나옴'(STALE·NO_POSTS_DAY)을 멈춤이 아니라 승인 대기로 보고 DRAFT_WAITING(경고)으로 바꾼다."""
    if blog.get("mode") == "off":
        return []
    key = blog["key"]
    cfg = blog.get("health", {})
    gap_hours = cfg.get("max_gap_hours", 48)
    streak_n = cfg.get("max_failure_streak", 3)
    now = _aware(now)
    entries = [e for e in history if isinstance(e, dict)]
    findings = []

    # 1) 발행 중단 (글 파일이 추가된 커밋 시각처럼 정확한 값이 있으면 날짜만 있는 항목의 '그날 23:59' 가정은 쓰지 않는다)
    ok_times = [entry_time(e, end_of_day=last_content_commit is None)
                for e in entries if e.get("status", "posted") in OK_STATUSES]
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
    # 게시가 목적(mode auto)인데 가장 최근 실행이 저장소 초안만 남겼으면 첫 번째부터 알린다(예전에는 3회 연속).
    # 사유는 이력에 적힌 것을 한 줄로 인용한다.
    if blog.get("mode") == "auto" and statuses and statuses[-1] == "generated_unpublished":
        last_entry = [e for e in entries if e.get("status")][-1]
        reasons = last_entry.get("reasons") or []
        why = " ".join(str(reasons[0]).split())[:200] if reasons else "사유 기록 없음"
        findings.append(Finding(key, "UNPUBLISHED", "warning",
                                f"가장 최근 실행이 게시하지 않고 저장소 초안만 남겼습니다(사유: {why}). "
                                "게시 시크릿(BLOGGER_*) 미등록이 원인일 수 있습니다(HANDLER.md §10)."))

    # 2-1) 닫힌 KST 하루 단위: 어제 새 글이 0건이면 경고, 그제도 0건이면 심각. 오늘 이미 새 글이 나왔으면 회복된 것이다.
    #      (STALE 이 이미 울리면 같은 원인이므로 중복 알림을 만들지 않는다.)
    if blog.get("mode") == "auto" and not any(f.code in ("STALE", "NO_ACTIVITY") for f in findings):
        days = set(post_days) if post_days is not None else set()
        days |= post_days_from_history(entries, drafts_count=post_days is None)
        today = now.astimezone(KST).date()
        yesterday, before = today - timedelta(days=1), today - timedelta(days=2)
        if days and today not in days and yesterday not in days:
            if before not in days:
                findings.append(Finding(key, "NO_POSTS_DAY", "critical",
                                        f"이틀 연속({before}, {yesterday}) 새 글이 0건입니다. 워크플로가 초록이어도 글이 안 나온 것입니다. "
                                        "실행 요약의 [SKIP] 사유를 확인하세요."))
            else:
                findings.append(Finding(key, "NO_POSTS_DAY", "warning",
                                        f"어제({yesterday}) 새 글이 0건입니다. 워크플로가 초록이어도 글이 안 나온 것입니다. "
                                        "실행 요약의 [SKIP] 사유를 확인하세요."))

    # 2-1-1) 승인 흐름(publish_flow: pr): 새 글이 안 나온 것이 멈춤이 아니라 승인 대기일 수 있다. 열린 초안 PR 이 있으면 '글이 안 나옴'
    #        (STALE·NO_POSTS_DAY)을 치명 경고 대신 DRAFT_WAITING(확인 수준)으로 바꾼다. 최근 글이 있으면(위 두 경고가 없으면) 아무것도 하지 않는다.
    #        초안이 없거나 목록을 읽지 못했으면(pending_drafts 가 비었거나 None) 그대로 STALE·NO_POSTS_DAY 가 울린다 — 정말 멈춘 것일 수 있다.
    if blog.get("publish_flow") == "pr" and pending_drafts:
        if any(f.code in ("STALE", "NO_POSTS_DAY") for f in findings):
            findings = [f for f in findings if f.code not in ("STALE", "NO_POSTS_DAY")]
            findings.append(Finding(key, "DRAFT_WAITING", "warning", _waiting_message(pending_drafts, now)))

    # 2-2) 사이트 배포: 글 커밋 뒤 일정 시간이 지났는데 성공한 Pages 실행이 없거나, 최근 실행이 실패(D-24형)
    if pages_runs is not None and blog.get("platform") == "jekyll-git":
        runs = [r for r in pages_runs if r.get("conclusion") in ("success", "failure")]
        if last_content_commit is not None:
            committed = _aware(last_content_commit)
            if now - committed > timedelta(minutes=PAGES_GRACE_MINUTES):
                # created_at 을 읽을 수 없는 성공 실행은 '지금'으로 본다(응답 형식 문제로 정상 배포를 미배포로 오판하지 않는다).
                earliest = committed - timedelta(seconds=PAGES_CLOCK_SKEW_SECONDS)
                deployed = any(r["conclusion"] == "success" and (_parse_utc(r.get("created_at")) or now) >= earliest
                               for r in runs)
                if not deployed:
                    findings.append(Finding(key, "PAGES_NOT_DEPLOYED", "critical",
                                            f"글 커밋({committed.astimezone(KST):%Y-%m-%d %H:%M} KST) 뒤 "
                                            f"{PAGES_GRACE_MINUTES}분이 지났는데 성공한 '[공통] 사이트 자동 배포' 실행이 없습니다. "
                                            "새 글이 공개 사이트에 올라가지 않았을 수 있습니다."))
        if runs and runs[0]["conclusion"] == "failure":
            findings.append(Finding(key, "PAGES_FAILED", "warning",
                                    "가장 최근 '[공통] 사이트 자동 배포' 실행이 실패했습니다(예: 문서 속 Liquid 구문 사고, D-24). "
                                    "이전 성공 배포는 계속 공개되지만 새 글은 올라가지 않을 수 있습니다."))

    # 3) 워크플로 실행 결과 연속 실패
    done = [r for r in recent_runs if r.get("conclusion") in ("success", "failure")]
    if len(done) >= streak_n and all(r["conclusion"] == "failure" for r in done[:streak_n]):
        findings.append(Finding(key, "RUN_FAIL_STREAK", "critical",
                                f"워크플로가 최근 {streak_n}회 연속 실패했습니다. Actions 로그를 확인하세요."))
    return findings
