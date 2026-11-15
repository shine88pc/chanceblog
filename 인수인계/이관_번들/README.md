# 이관 번들 — 빈 PC 에서 이어받기 (2026-11-15 14:30 이관용, 임시판)

> 이 폴더는 운영자 이슈 #200('다른 PC 로 이관할 수 있게 정리')과 11-15 14:2x 채팅('다른 공용 PC 도 빈 폴더에서 시작 — 필요한 것은 저장소를 통하게')에 따라 **이 PC(옛 PC) 에만 있던 도구·양식·지시서·기억 사본**을 저장소 가지 `ai/claude/NO-MERGE-migration-bundle` 에 모아 둔 것입니다. **병합 대상이 아니고(main 에 들어가지 않음) 임시판**입니다 — 도구의 정식·정리판은 'HANDOFF2' 묶음(`인수인계/도구/` 갱신)이 병합된 뒤 그쪽이 이깁니다. 비밀·키·토큰은 들어 있지 않고(검사함) 이 PC 사용자 이름·이메일은 치환했습니다.

## AI 자율 운영 계약 (운영자 11-15 14:3x 지시 — 가장 먼저 읽을 것)
운영자는 새 PC 에서 **프롬프트를 한 번 입력한 뒤에는 그 PC 를 확인할 수 없습니다.** 그래서 새 PC 의 AI 는 그 뒤로 **질문 없이 스스로 판단해 끝까지 진행**합니다.
1. **질문하지 않습니다**(채팅 질문 금지 — 아무도 읽지 못합니다). 새 결정은 `work/operator_delegation_rules.md` 의 우선순위(최신 운영자 결정 > 확정 문서 > 기존 기록 > 정상 동작 > 데이터 보존 > 보안 > 최소 변경 > 안전한 기본값)로 스스로 정하고 D-번호로 기록합니다. 멈추는 것은 그 규칙의 예외(비밀이 필요함·돌이킬 수 없는 삭제·T3 미승인 등)뿐이며, 그때도 그 일만 `BLOCKED` 로 두고 나머지는 계속합니다.
2. **운영자와의 소통은 텔레그램 알림(요청 파일 푸시)과 GitHub 이슈 `[답변]` 뿐**입니다. 진행 현황은 마지막 알림에서 110분 이상이면(변화가 없어도) 보내고, 병합 부탁은 한 번에 하나씩(검사가 초록일 때만·독립 검증 뒤에만) 보냅니다. 병합은 운영자가 휴대폰으로 합니다(AI 병합 기능은 꺼져 있음).
3. **푸시 권한이 있어야 일할 수 있습니다.** 운영자가 프롬프트를 주기 전에 이 PC 에서 GitHub 에 로그인(자격 증명)해 둡니다. 푸시가 안 되면 읽기·분석·초안까지만 하고, 5분 간격으로 다시 점검하며(로그인되면 이어서), 작업 폴더에 `이관_상태.md` 로 현재 상태를 적어 둡니다.
4. **결정 대기 항목은 아래 기본값대로** 진행합니다: 확인 017(이관 준비)은 '1 지금 시작'(처리됨) · 그림자 실행 3회차는 **운영자 몫**이라 AI 가 하지 않고 진행 현황마다 한 줄로 상기(11-16 이후 다른 날 하루 한 번) · AP13(홈 서랍 단추)은 지금 만들지 않음(사유·설계 위험은 앱 저장소 `docs/UI_DESIGN_SPEC.md` 13절) · AP15 값 칸 5곳은 그대로, 사진 188장은 다시 찍지 않음 · 정책 문서의 R5 두 가지(문서 낱말 면제·AI 규칙 문서 운영자 전용)는 '총괄(AI)의 판단 — 운영자 확인 대기'로 두고 켜는 변경 병합 부탁 때 쉬운 말로 설명 · `README.md` 읽는 순서 수정(T3)은 하지 않고 필요하면 확인 요청으로.
5. **자율 모드에서도 그대로인 것**: 비밀·키·개인 정보 금지 · T3 는 승인된 항목만 · 발행 일시정지 해제·광고·AdSense·워크플로·의존성·제공처 켜기·`workflow_dispatch` 는 운영자만 · main 직접 push 금지 · 두 PC 동시 가동 금지 · **폴더 삭제·로그아웃 같은 PC 정리는 AI 가 하지 않음**(운영자 몫).
6. **세션이 끊겨도 이어지도록 자주 푸시**합니다(작업 폴더 WIP 는 `NO-MERGE-…` 가지로, 진행 기록은 `COORDINATION.md`·요청 파일로). 새 PC 도 공용이라 갑자기 재시작될 수 있습니다 — 재시작 뒤에는 같은 한 문장으로 다시 시작하고 이 README 의 순서를 처음부터 따릅니다(이미 한 일은 건너뜀).

## 한눈에
- **두 PC 를 동시에 가동하지 않습니다.** 새 PC 의 AI 가 첫 보고(텔레그램 info)를 보낸 뒤에는 옛 PC 의 AI 세션이 알림·요청을 보내지 않습니다(요청 번호·가지 이름이 겹쳐 알림이 꼬임).
- 정본은 저장소입니다: `인수인계/작업내용.md` 맨 위 30초 카드(main) + 이 번들의 `state/COORDINATION.md`(지금 진행 상태·검증 결과·다음 순서 — 번들 가지에 계속 갱신됩니다).
- 이 번들은 운영자가 AI 에게 줄 **한 문장**(아래)으로 시작합니다.

## 운영자가 새 PC 에서 하실 일 (AI 에게 줄 한 문장)
새 PC 에서 Claude 앱(또는 AI 세션)을 열고 아래 한 문장을 입력합니다.
> **저장소 chanceblog 의 가지 ai/claude/NO-MERGE-migration-bundle 의 인수인계/이관_번들/README.md 를 읽고 그대로 이어서 진행해줘.**

(표준 문장 '저장소 chanceblog 의 인수인계/작업내용.md 맨 위 30초 카드부터 읽고 이어서 진행해줘.' 도 됩니다. 다만 표준 문장은 도구 최신본·작업 중 가지를 모르므로, 이번 이관에서는 위 문장을 먼저 쓰세요.)

## AI 가 빈 PC 에서 시작하는 순서
1. **필요한 프로그램 확인**: Git, 파이썬 3.12(가능하면 3.10 도 — CI 모양), 텍스트 편집은 AI 도구로. 없으면 운영자에게 설치를 부탁합니다(설치는 운영자 몫, AI 는 관리자 권한·시스템 설정을 바꾸지 않습니다).
2. **번들 받기**(로그인 불필요 — 공개 저장소):
   `git clone --branch ai/claude/NO-MERGE-migration-bundle --single-branch https://github.com/shine88pc/chanceblog.git <임시폴더>` 후 `<임시폴더>/인수인계/이관_번들/` 로 이동.
3. **작업 폴더 만들기**: `python bootstrap.py --work C:/work/ai --clone` (이 경로면 도구를 고칠 필요가 없습니다. 다른 경로를 쓰면 `--work <경로>` 와 `--python <파이썬 3.12 경로>` 를 주세요 — 복사된 도구 안의 경로를 바꿔 줍니다). `--clone` 은 저장소를 복제합니다: `W/wt_r30`(블로그 저장소, **요청 가지 `ai/claude/NO-MERGE-operator-requests` 가 체크아웃된 상태 — 여기서 절대 checkout·커밋하지 않습니다**)와 `W/cd_repo`(데스크톱 저장소).
4. **푸시 권한 점검**(쓰기 일을 하려면): 운영자가 이 PC 에서 GitHub 에 로그인(자격 증명 관리자 — AI 는 비밀번호·토큰을 다루지 않음)한 뒤 `GIT_TERMINAL_PROMPT=0 GCM_INTERACTIVE=false git -C W/wt_r30 push --dry-run --porcelain origin HEAD:refs/heads/ai/claude/preflight-test` 의 종료 코드 0 과 `[new branch]` 줄을 확인합니다(`docs/AGENT_RUNBOOK.md` J1 8번). 안 되면 **읽기·분석·초안까지만** 하고 운영자에게 알립니다(푸시·병합 부탁은 하지 않음).
5. **상태 읽기(읽기 전용)**: `state/COORDINATION.md` 를 끝까지 읽고, 저장소 main 의 `인수인계/작업내용.md` 맨 위 30초 카드와 §0-1 로 세 저장소 main 머리·열린 PR·요청 가지의 마지막 알림을 대조합니다(문서가 낡았으면 **실제가 이깁니다**).
6. **WIP 가지 받기**: 이 PC 에 있던 작업 중 가지는 모두 `NO-MERGE-…` 이름으로 원격에 올라가 있습니다 — 블로그 `ai/claude/NO-MERGE-mergepol1-wip`·`ai/claude/NO-MERGE-handoff2-wip`(있으면), 데스크톱 `ai/claude/NO-MERGE-app15-wip`. 필요하면 `git -C W/wt_r30 worktree add C:/work/ai/improve_wt_<이름> -b <가지> origin/<가지>` 식으로 작업 폴더를 만듭니다.
7. **첫 보고**: 요청 파일 도구로 텔레그램 `info` 한 건(`work/make_info_request.py`, 양식 `work/progress_draft_template.md` — 이관 완료·상태·열린 PR·하실 일). 번호는 `work/next_notice_no.py --repo W/wt_r30 --dir W/wt_r30 --local`.
8. **감시·크론**: 세션 안 크론(매시 7분 진행 현황 알림 — 문구 `work/cron_status_prompt_v3.txt`)과 감시기(`work/scratch/watch_heads2.sh`·`watch_issues.py`, 30분마다 만료 — 다시 켬)를 새로 만듭니다.
9. **이어서**: `state/COORDINATION.md` 의 '다음 순서'대로.

## 두 PC 의 AI 세션이 서로 넘겨받는 규칙 (핸드셰이크 — 운영자 11-15 14:2x 지시)
**배경**: 옛 PC(이 번들을 만든 PC)는 공용 PC 라 운영자가 떠나면 **그 세션은 다시 접속할 수 없고**, 마무리 때 그 PC 의 작업 폴더(KCY 등)는 삭제되고 GitHub 로그인도 로그아웃됩니다. 그래서 두 세션은 **저장소의 번들 가지(`ai/claude/NO-MERGE-migration-bundle`)를 우편함**으로 씁니다. 각 쪽은 **자기 파일만** 쓰고 상대 파일은 읽기만 합니다(푸시가 겹치지 않게).

| 파일(번들 가지의 `인수인계/이관_번들/state/`) | 쓰는 쪽 | 뜻 |
|---|---|---|
| `OLD_PC_STATUS.json` | **옛 PC 의 AI** | `state` = `PREPARING`(아직 올리는 중 — 기다림) → `READY_TO_HAND_OVER`(**이전 준비 완료 — 새 PC 의 AI 가 시작해도 됨**) → `HANDED_OVER`(새 PC 가 넘겨받음을 확인 — 옛 PC 는 더 이상 알림·요청을 보내지 않음) → `CLOSED`(옛 PC 정리 끝 — 폴더 삭제·로그아웃, 더 이상 쓰지 않음). `sequence` 는 갱신할 때마다 1 씩 늘고 `updated_at` 은 갱신 시각입니다. 아직 끝나지 않은 일(`in_flight_on_old_pc`)과 새 PC 가 할 일(`next_for_new_pc`)이 들어 있습니다. |
| `NEW_PC_ACK.json` | **새 PC 의 AI** | 양식 `NEW_PC_ACK.template.json`. 새 PC 의 AI 가 번들을 읽고 `state` = `STARTED`(시작함) → `TOOK_OVER`(첫 보고를 보내고 넘겨받음)로 적어 올립니다. 옛 PC 의 AI 가 살아 있으면 이 파일을 보고 `HANDED_OVER` 로 바꾸고 알림을 멈춥니다. |

**새 PC 의 AI**: ① 시작하면 `git ls-remote origin refs/heads/ai/claude/NO-MERGE-migration-bundle` 로 머리를 읽고 `OLD_PC_STATUS.json` 의 `state` 를 봅니다. `PREPARING` 이면 1–2분 간격으로 다시 읽으며 기다리고(그 사이 도구 받기·설치 같은 준비는 해도 됨), `READY_TO_HAND_OVER` 이면 진행합니다. ② 이 README 의 '빈 PC 에서 시작하는 순서'를 마친 뒤 `NEW_PC_ACK.json` 을 올립니다(`STARTED`). ③ 첫 보고(텔레그램 info, 제목에 **`이관 완료`** 포함)를 보낸 뒤 `TOOK_OVER` 로 바꿔 올립니다. ④ 이후 `OLD_PC_STATUS.json`·`COORDINATION.md` 에 새 내용이 올라오면(옛 PC 가 `CLOSED` 가 될 때까지 갱신될 수 있음) 읽고 반영합니다. **푸시 권한이 없으면 ACK 를 못 올리므로 운영자에게 알리고 읽기·분석·초안까지만 합니다.**
**옛 PC 의 AI**: 이전 준비가 끝나면 `READY_TO_HAND_OVER` 와 요청 가지의 알림(제목에 **`이전 준비 완료`**)을 남깁니다. 아직 도는 일(구현·검증 에이전트)의 결과는 도착하는 대로 WIP 가지와 `COORDINATION.md`·`OLD_PC_STATUS.json` 에 올립니다. 새 PC 의 ACK(`STARTED`/`TOOK_OVER`)를 보면 `HANDED_OVER` 로 바꾸고 알림을 멈춥니다. 운영자가 떠나기 전(또는 마무리 선언 때) 마지막으로 `CLOSED` 를 올리고, 폴더 삭제·로그아웃은 운영자 확인 뒤에 합니다.
**누가 일을 하나**: `ACK` 가 `TOOK_OVER` 가 되기 전까지의 진행 중인 일은 옛 PC, 그 뒤는 새 PC 입니다. 두 쪽이 동시에 알림·요청·병합 부탁을 보내지 않습니다.

## 이 번들에 있는 것
| 폴더·파일 | 내용 |
|---|---|
| `bootstrap.py` | W 만들기·경로 치환·저장소 복제·문법 검사 |
| `work/` | 이 PC 작업 폴더 W 의 거울: 요청 파일 도구(`make_request.py`·`make_info_request.py`·`make_merged_notice.py`·`next_notice_no.py`·`notice_tools.py`·`commit_as_author.py`)·병합 가지 도구·`run_shard_like.py`(앱 CI 조각 시험 도우미)·양식(`merge_request_template_v2.md` — 운영자가 정한 6항목 쉬운 설명, `progress_draft_template.md`)·크론 문구·`operator_delegation_rules.md`(새 결정은 멈추지 않고 우선순위로 정하는 규칙)·`scratch/`(CI 대기·알림 확인·라이브 값 확인·이슈 감시·머리 감시·상태 읽기·병합 검사 도구·그림자 결과 점검과 한 표 생성기)·`audit6/improve/`(구현자 지시서와 공통 규칙) |
| `memory/` | 이 PC 의 Claude 기억 폴더 사본(70KB 넘는 옛 이어가기 기록은 제외, 이 PC 사용자 이름·이메일 치환) — **정본이 아닙니다**(저장소 문서가 다르면 그쪽이 이김), 운영자 선호·결정의 배경으로만 읽습니다 |
| `state/COORDINATION.md` | 지금 진행 상태·검증 결과·다음 순서(번들 가지에 계속 갱신) |
| `state/RESUME_TOP.md` | 이 PC 의 이어받기 기록 맨 위 30줄 |

## 주의
- **비밀·키는 이 저장소에도 이 번들에도 없습니다.** 새 PC 에서는 운영자가 직접 인증합니다. 텔레그램·사이트 배포·감시는 GitHub 쪽 자동화라 PC 와 무관하게 계속 돕니다.
- 운영자 KCY 폴더 문서(요구서·전략 원문 등)는 저장소 금지·반출 불가라 번들에 없습니다(요약은 `memory/` 와 `인수인계/작업내용.md` 에). 필요하면 운영자에게 다시 첨부를 부탁합니다.
- 지시서의 `C:/work/ai`·`S`·`KCY` 는 이 PC 의 작업 폴더 이름입니다 — 새 PC 에서는 W 입니다.
- 두 PC 를 오가지 않습니다. 이 번들 가지는 병합하지 않습니다.
