---
name: telegram-latency-findings-2026-11-11
description: "운영자 '텔레그램 메시지를 더 빨리 확인' 요청(2026-11-11 13:00)에 대한 측정·결론 — 예약 수신 실행은 실제 6시간 간격(중앙값 356분), 푸시로 도는 길이 빠름, 이슈 감시 추가, 나머지는 현 상태 유지(운영자: 문제 있으면 유지, 급하면 이슈 직접 등록)"
metadata:
  node_type: memory
  type: project
  originSessionId: 921b6032-bba9-4b52-8c2d-b24e5509c445
  modified: 2026-11-11T04:00:18.210Z
---

**운영자 요청:** 텔레그램으로 보낸 운영자 메시지를 더 빨리 확인했으면 좋겠다 — 다른 문제가 있으면 지금처럼 유지, 급하면 이슈로 직접 등록하겠다.
**측정(2026-11-11, 공개 REST):** `[공통] 텔레그램 수신 가져오기`(`.github/workflows/telegram-inbox.yml`)는 `schedule: '*/10 * * * *'` 인데 **실제 예약 실행 간격이 중앙값 356분·평균 350분·최대 621분**(11-08–11-11 최근 27회) — GitHub 가 이 저장소의 예약 실행을 늦춘다. 같은 워크플로는 **`ai/claude/**` 브랜치에 푸시할 때마다 즉시** 돈다(내 요청·병합 가지 푸시가 사실상 수신 주기). 같은 푸시에 `guardrails`(어느 브랜치든 push 면 도는 5분 CI)·`ai-request`(알림)도 돈다. 이슈(`issues: opened`)는 즉시 이벤트(`operator-reply.yml`).
**내가 한 것(위험 0):** 내 쪽 감지 지연을 줄이는 **이슈 감시 Monitor** `python -X utf8 C:/work/ai/scratch/watch_issues.py`(90초마다 ETag 조회 — 304 는 REST 한도를 안 씀 — 라벨 텔레그램수신·운영자응답이거나 작성자 shine88pc 인 새 이슈 한 줄씩 출력, 30분마다 재무장·재부팅 뒤 다시 켬). 이전에는 시간당 크론이 후보일 때만 보았다.
**안 한 것(다른 문제):** ① 빈 커밋 푸시로 수신 워크플로를 깨우기('poke') — 푸시마다 5분 CI·알림 워크플로가 같이 돌고 커밋·브랜치가 쌓임 ② `workflow_dispatch` API 호출 — `gh` CLI 없음, git 자격 증명 관리자 토큰을 꺼내 쓰지 않음(운영자 승인 없이는 안 함) ③ cron 주기를 5분으로 줄이기 — `.github/` 변경(T3)이고 지연 원인이 GitHub 의 스케줄 지연이라 효과가 작음. **결론: 현 상태 유지 + 이슈 감시만 추가**, 급한 건 운영자가 이슈로 직접(이슈는 즉시 이벤트 + 내 감시가 약 2분 안에 잡음). 이 채팅 세션에 직접 쓰면 가장 빠르다.
**How to apply:** 재부팅·세션 재시작 뒤 이슈 감시 Monitor 를 다시 켠다(TOP-RESUME). 새 이슈가 알림으로 오면 번호·제목만 보고 해당 이슈를 열어 처리(비밀 값은 읽지 말고 마스킹). [[operator-telegram-requests-only]] [[telegram-push-channel]]
