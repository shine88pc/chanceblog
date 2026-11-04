---
name: feedback-precheck-ci-before-merge-request
description: "운영자 지시(2026-11-03 15시): 병합 부탁은 자동 검사(CI)가 이미 끝나 전부 초록인 상태로만 보낸다 — 운영자가 PR 을 만든 뒤 13분 기다리거나 빨간 검사로 [답변] 이슈를 쓰는 일이 없게(데스크톱 ci.yml 은 push 검사만, D-28)"
metadata:
  node_type: memory
  type: feedback
  originSessionId: (세션 번호)
  modified: 2026-11-03T06:16:25.500Z
---

**운영자 지시(2026-11-03 15시경, 채팅):** "최종 병합만 진행할 수 있게 미리 CI 검사가 진행되도록 해줘." 검사가 생각보다 길어(데스크톱 Windows 칸 13~14분) 병합 전에 계속 접속해 지켜봐야 하고, 검사가 실패하면 이슈로 다시 확인 요청을 해야 하는 번거로움을 없애 달라는 것.

**Why (실측):** R-071 은 내가 병합 브랜치를 push 해 사전 검사를 16분 돌려 4칸 초록을 확인했는데도(13:10~13:26), 운영자가 PR 을 만들자(14:04) `ci.yml` 의 `pull_request` 이벤트가 **같은 커밋을 13분 더 돌려** 14:18 까지 기다리셨다. R-068 은 그 PR 검사가 빨강이라 [답변] '문제' 이슈가 왔다. 데스크톱 CI 는 Windows 칸의 시험 단계가 약 800초(ubuntu 는 160초)라 길다. 블로그 `guardrails.yml` 은 PR 에서만(약 2분)·main push 에서만 돌아 사전 push 검사가 없다.

**How to apply:**
1. 병합 부탁(`kind: merge`)은 병합 브랜치를 push 한 뒤 **그 커밋의 자동 검사가 끝나 전부 초록**인 것을 AI 가 직접 확인한 다음에만 보낸다(`scratch/wait_ci.py` 또는 Monitor; 웹 목록 JSON 으로 API 한도 없이). **요청 파일 생성기 `make_request.py` 가 이를 강제한다**(`kind: merge` 는 마지막 인자 `소유자/저장소:브랜치` 필수, 머리 커밋의 실행이 모두 끝나 초록이어야 파일 생성; 예 `S\r075_fill.py`). 빨강이면 운영자에게 묻지 말고 AI 가 먼저 고친다(새 브랜치 이름, force push 금지, 병합 브랜치는 한 커밋 유지). 검사 장애(GitHub 지연)면 병합 부탁을 보류하고 진행 알림(info)에 한 줄.
2. **[적용됨 — R-075 병합 2026-11-03 16:36, PR #11: 만든 지 40초 만에 `mergeable_state: clean`, `pull_request` 실행 없음, 운영자는 PR 생성 2분 44초 뒤 병합]** 데스크톱 `ci.yml` 에서 `pull_request` 트리거를 뺐다(D-28, 시간 제한 30분, T2 — 독립 검증 + 병합 부탁 1건) → PR 을 만들어도 검사가 다시 안 돌고 push 검사 결과(4칸)가 PR 화면에 바로 보인다(GitHub 은 PR 화면에 머리 커밋의 모든 검사를 보여 준다). **병합된 지금부터** 요청문 '하실 일'은 "PR 만들기 → 초록 4칸이 바로 보임 → Merge → Confirm" 으로 바꾼다(요청문 틀 `make_request.py` 문구도).
3. 블로그는 별도 후속(T2): `guardrails.yml` 에 `ai/claude/**` push 검사를 더하되 `alert` 잡은 main 에서만, `ops-inbox` 가 AI 브랜치 실패를 운영자 인박스로 올리지 않는지·`tests/test_agent_docs.py`·`tests/test_notify_main_check.py`·문서 표(AGENT_RUNBOOK·ACTIONS_GUIDE·ARCHITECTURE)를 함께 확인한다. `pull_request` 는 병합 대상 트리(봇 글 포함) 검사라 남긴다(PR 검사 약 2분).
4. 새 규칙 문구는 저장소에도 남긴다(데스크톱 AGENTS.md·DECISIONS D-28, 블로그 AGENT_RUNBOOK·요청함 README 는 다음 문서 PR).
관련: [[feedback-merge-request-format]] [[operator-telegram-requests-only]] [[resume-after-reboot]]
