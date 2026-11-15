---
name: feedback-merge-done-notice
description: "운영자 2026-11-11 채팅 — 병합 부탁을 보낸 뒤 병합 확인이 끝나면 간단한 '[M###] 병합완료' 알림(텔레그램 info)을 따로 보낸다"
metadata:
  node_type: memory
  type: feedback
  originSessionId: 921b6032-bba9-4b52-8c2d-b24e5509c445
  modified: 2026-11-11T04:00:07.929Z
---

**운영자 지시(2026-11-11 ~13:00 채팅):** "병합 요청 메세지 발송후에 병합 확인이 완료되면 간단하게 [M-xxx]병합완료 메세지를 보내줘".

**Why:** 병합 부탁(M###)은 텔레그램으로 오는데 병합 뒤 확인이 끝났다는 신호가 운영자 쪽에는 없어서(채팅에서만 알렸음) 한 건이 닫혔는지 알기 어렵다. 짧게 '끝났다'만 알려 달라는 뜻.
**How to apply:** 병합 확인(main 한 커밋 앞·트리 == 가지 트리·main 검사·배포 초록·공개 글 수/광고 스크립트 그대로)이 **끝난 즉시**(마일스톤 — 진행 현황 4시간 주기와 무관) `kind: info` 요청 파일을 만든다: `cd C:/work/ai && python -X utf8 make_info_request.py R-nnn merge-done-m### <초안 파일>` — **제목 `[M###] 병합완료`**(80자 이하)·summary 한 줄(main 앞 7자리·검사/배포 초록·공개 글 수 그대로·켜는 값 없음)·`work: R-<병합 부탁 번호>`·now/changed/next/waiting 은 한 줄씩 짧게(필수 칸), eta 는 생략 가능한지 확인. 도구 제약: **info 의 알림 번호는 P 유형**(`no: @NO@` → P###) — M 번호는 병합 부탁에만 쓰고 재사용 불가(`notice_tools.no_problem`). 요청 가지 `ai/claude/NO-MERGE-operator-requests` 에 validate_repo → commit_as_author → `git push origin ai/claude/NO-MERGE-operator-requests`(명시적) → `scratch/check_notify.py R-nnn`. 진행 현황 알림(P)과 같이 쓰는 번호 순서라 P 번호가 건너뛰어 보일 수 있음을 알아 둔다. 이미 확인·보고한 과거 병합(M047 은 P027 에 포함)은 소급하지 않고 M048 부터. [[feedback-merge-request-format]] [[feedback-merge-label-m-number]] [[telegram-notification-standard-2026-11-06]]

**★ 2026-11-12 정정(운영자 채팅 08:0x — 위 방식보다 최신, 우선):** 운영자가 "병합 완료 알림은 별도로 관리해주면 좋겠어 — Pxxx 으로 하지말고 다른 부제 없이 `[Mxxx] 병합완료 확인 - 정상 유무`(간단히)만 보낼 수 있게 수정해줘, 목적은 내가 진행한 병합이 제대로 되었나를 확인하는 용도" 라고 지시했다. → **P 번호를 먹는 `kind: info` 병합완료 알림(M049=P030·M050=P034)은 끝**. 새 요청 종류 `merged`(앞머리 id·kind·title·summary·no(=짝 병합 부탁의 M 번호)·result 정상/이상·created, 정상은 제목 한 줄만 텔레그램으로, 이상은 제목+사유 한 줄)를 만드는 **MDONE 레인**(구현 에이전트 `a3781d8e8a77dbb3a`, 지시서 `audit6/MDONE_BRIEF.md`, 작업 폴더 `wt_mdone`, 가지 `NO-MERGE-mdone-wip`, 결정 D-310~, 작업용 도구 `C:/work/ai/make_merged_notice.py`)을 시작했고, 구현·독립 검증·병합(M051) 뒤부터 병합 확인이 끝나면 `make_merged_notice.py R-nnn M### 정상|이상 [사유]` 로 보낸다. **그 전까지 새 병합이 생기면 병합완료 알림은 보류했다가(P 번호를 쓰지 않으려고) 새 종류가 병합된 뒤 한꺼번에 보낸다.** 제목 모양: `[M050] 병합완료 확인 - 정상` / `[M050] 병합완료 확인 - 이상`(이상이면 사유 한 줄). 이미 보낸 R-259·R-265 는 그대로(이관 없음).

**★★ 2026-11-12 13:52 — 새 방식 가동(가장 최신, 위 보류 규칙 종료):** MDONE 이 **M055 로 병합**(블로그 main 483b7f2, 13:35)되고 요청 가지(wt_r30 `ai/claude/NO-MERGE-operator-requests`)에 **main 을 합쳤다**(머지 커밋 5e1bfaf — 요청 가지는 11-06 컷오버 뒤 처음 합침, 충돌 0, 합친 뒤 규칙·시험 CI 초록). 그 뒤 첫 병합완료 확인 R-275(M054 정상)·R-276(M055 정상) 발송 — 알림 run #413·#414 경고 없음. **절차**: 병합 직접 확인이 **모두 끝난 뒤**(머지 커밋/한 커밋 앞·트리 일치·main 검사(+블로그는 배포)·보호 경로·블로그는 공개 글 38·사이트맵 45·피드 38·광고 1줄) `cd C:/work/ai && python -X utf8 make_merged_notice.py R-nnn M### 정상|이상 [이상 사유 한 줄]`(기본으로 wt_r30 코드로 엄격 검사 — 요청 가지에 새 코드가 없으면 만들지 않고 멈춤) → `wt_r30` `scripts/validate_repo.py` 오류 0건 → `commit_as_author.py`(제목 `docs: 운영자 요청 R-nnn — 병합완료 확인 M###: 정상 …`) → `git push origin ai/claude/NO-MERGE-operator-requests`(**한 푸시에 한 알림 — 다른 요청과 섞지 않기**, 3통 상한) → `scratch/check_notify.py R-nnn`. 같은 M 의 둘째 merged 는 거절(이상을 알린 뒤 고친 결과는 info 알림으로). 정상/이상은 내가 직접 확인한 값(도구가 검사 안 함). 그 전 병합 M051–M053 은 진행 현황 P037 로 알렸으므로 merged 로 소급하지 않음. [[session-2026-11-05-new-pc-resume]]
