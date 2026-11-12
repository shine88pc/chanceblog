"""확인 필요 모음 이슈(#22)의 2026-11-11 11:16 본문을 만든 입력을 고정 표본으로 다시 만든다(시험과 저장소 밖 전·후 비교 도구가 함께 쓴다).

그날 본문: 지금 해야 할 일 8건(Blogger 초안 둘 '게시 대기'·병합이 끝난 가지 M029·M034·M038·M048 의 승인 대기 넷·병합이 끝난 PR #176·일부러 켜 둔 일시정지)·확인 2건(네이버 초안 #88·#103)·참고 5건.
실행 번호·시각·제목은 그 본문의 값이다. 가지 이름의 뒷부분은 본문에 잘려 있어(40자) 비슷한 이름으로 채웠다 — 판정에는 쓰이지 않는다(가지 이름은 같기만 하면 된다).
각 승인 대기의 head 커밋 앞 일곱 글자는 모음이 묶는 열쇠(approve:<7자>)이고 저장소의 실제 커밋과 같다.
"""
from datetime import datetime, timedelta, timezone

import _bootstrap
import ops_inbox_helpers as h
from pipeline import inbox

REPO = "shine88pc/chanceblog"
KST = timezone(timedelta(hours=9))
NOW = datetime(2026, 11, 11, 11, 16, tzinfo=KST).astimezone(timezone.utc)


def iso(year, month, day, hour, minute):
    return h.iso(datetime(year, month, day, hour, minute, tzinfo=KST))


# (실행 번호, 가지, 커밋 앞 7자, 만든 시각 KST, 제목)
APPROVALS = (
    (42583165462, "ai/claude/M029-pages-about-privacy-contact", "87fc678", (2026, 11, 9, 17, 2), "[M029] 소개·개인정보·문의 페이지와 홈 안내 문구를 지금 사실에 맞게 고침(스타일 보완 포함)"),
    (42604200608, "ai/claude/M034-lock-publish-path", "b27b3fb", (2026, 11, 9, 19, 50), "[M034] 제한 재개 잠금(resume_lock)·공개 경로 전수조사·수동 그림자 실행 워크플로 — 스위치는 꺼진 채(켜는 것은 별도 승인)"),
    (42729416599, "ai/claude/M038-lock-hardening-weekly", "8076dcf", (2026, 11, 10, 9, 35), "[M038] 제한 재개 잠금 보강 — 키 검사 강화와 주간 상한"),
    (42944581397, "ai/claude/M048-fact-gate-s2bg", "7f2dfdf", (2026, 11, 11, 11, 14), "[M048] 품질 관문이 계산 글(Fact)을 평가하게 하는 최소 수정(S2BG)"),
)
MERGED_PULL = 176
MERGED_BRANCH = "ai/claude/M048-fact-gate-s2bg"
NAVER_DRAFTS = (
    (88, "[초안][네이버] 봄맞이 대청소를 방별로 나눠 끝내는 분할 계획표 만들기", (2026, 10, 30, 22, 12)),
    (103, "[초안][네이버] 가을 여행 전 집을 비울 때 확인하는 가전과 가스 쓰레기 정돈법", (2026, 11, 3, 1, 17)),
)
WORKFLOW_NAMES = {"pr-scope-check.yml": "[공통] PR 변경 범위 검사"}


def blogs():
    """실제 레지스트리의 모양대로 — Chance(자동 공개)·Blogger 영문·한글(초안)·네이버(정지)."""
    return [
        h.channel_blog("chance", "Chance", "jekyll-git", "auto", name="Chance_Blog", publish_flow="direct"),
        h.channel_blog("blogger_macat", "Blogger 영문", "blogger", "draft", name="Blogger (macat0722)", url="https://macat0722.blogspot.com/", history="blogger_history.json"),
        h.channel_blog("blogger_kcyoon", "Blogger 한글", "blogger", "draft", name="Blogger (kcyoon)", url="https://kcyoon.blogspot.com/", history="blogger_ko_history.json"),
        h.channel_blog("naver_life_tips", "네이버", "naver", "off", name="네이버 (계절·생활 팁)", note="운영자 결정(2026-11-03): 데스크톱 프로그램으로 이관을 마칠 때까지 잠정 중단합니다."),
    ]


def histories():
    return {
        "chance": [{"date": "2026-11-08", "slot": 18}],
        "blogger_macat": [h.make_entry("draft_uploaded", "2026-11-08T17:45:50+09:00", post_id="2842475330937894399")],
        "blogger_kcyoon": [h.make_entry("draft_uploaded", "2026-11-08T19:38:44+09:00", post_id="5197439892375631981")],
    }


def published():
    """공개 피드에서 읽은 글 번호(초안 둘은 아직 공개되지 않았다 — 본문이 '게시 대기'로 알린 이유)."""
    return {"blogger_macat": frozenset({"1"}), "blogger_kcyoon": frozenset({"2"})}


def approval_runs(repo=REPO):
    out = []
    for run_id, branch, sha7, when, title in APPROVALS:
        run = h.make_approval_run(run_id, branch=branch, sha=sha7 + "0" * 33, created=iso(*when), title=title)
        run["head_repository"] = {"full_name": repo}            # 실제 실행 객체처럼 head 저장소는 이 저장소다(승인 대기 규칙이 포크 PR 의 실행을 따로 보므로) — 시험이 쓰는 저장소 이름을 넘긴다
        out.append(run)
    return out


def drafts():
    return [h.make_draft(number, title, "네이버", created=iso(*when)) for number, title, when in NAVER_DRAFTS]


def pull_open_and_green():
    """본문이 '병합하면 됩니다'로 알린 그 순간의 PR #176(열림·검사 통과)."""
    raw = h.make_pull_raw(MERGED_PULL, title="[M048] 품질 관문이 계산 글(Fact)을 평가하게 하는 최소 수정(S2BG)", login="github-actions[bot]", user_type="Bot", assoc="CONTRIBUTOR",
                          created=iso(2026, 11, 11, 11, 13), ref=MERGED_BRANCH, sha="7f2dfdf" + "0" * 33)
    return inbox.normalize_pull(raw, {"mergeable": True, "mergeable_state": "clean", "state": "open", "merged": False}, [h.make_check("validate")])


def pull_merged():
    """지금의 PR #176(병합 끝남)."""
    raw = h.make_pull_raw(MERGED_PULL, title="[M048] 품질 관문이 계산 글(Fact)을 평가하게 하는 최소 수정(S2BG)", login="github-actions[bot]", user_type="Bot", assoc="CONTRIBUTOR",
                          created=iso(2026, 11, 11, 11, 13), ref=MERGED_BRANCH, sha="7f2dfdf" + "0" * 33)
    return inbox.normalize_pull(raw, {"mergeable": None, "mergeable_state": "unknown", "state": "closed", "merged": True}, [h.make_check("validate")])


def base_kwargs():
    """옛 Snapshot 에도 있는 칸만(전·후 비교 도구가 옛 코드에도 넘긴다)."""
    return dict(now=NOW, repo=REPO, blogs=blogs(), histories=histories(), published=published(), approvals=approval_runs(), drafts=drafts(), paused=True,
                workflow_names=dict(WORKFLOW_NAMES))
