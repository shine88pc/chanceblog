---
name: feedback-merge-request-format
description: "병합 부탁(요청 파일) 형식 — 링크 주소를 쓰지 않고, 병합할 PR 제목을 `[R-nnn] 짧은 이름`으로 눈에 띄게; 브랜치는 한 커밋으로 합쳐 제목이 기본값이 되게; 운영자는 모바일의 PC 버전 GitHub 로 병합; '알람 없이'는 세션 알람만 — 업무 알람은 메세지로(2026-11-02 정정)"
metadata:
  node_type: memory
  type: feedback
  originSessionId: (세션 번호)
  modified: 2026-11-02T09:57:22.624Z
---

**운영자 지시(2026-11-02, R-043·R-044 병합 뒤):** ① 요청 md 의 compare 링크 주소는 쓸모없다 — 운영자는 휴대폰에서 GitHub **PC 버전**으로 들어가 첫 화면 노란 배너(또는 Pull requests 탭)에서 병합한다. ② **병합 제목이 비슷한 것이 많아 실수할 수 있다** → 병합에 필요한 **제목만 명확히 구분**되게 쓴다. ③ "해당 세션 알람 없이 진행" = **Claude 세션(앱) 알람 없이**라는 뜻이었다(같은 날 운영자 정정) — 진행 상황·완료 예정 시각 같은 **업무 알람은 텔레그램 info 요청으로 보낸다**(채팅 질문·앱 푸시는 안 씀) — [[quiet-mode-defaults]] 의 '정정·상시 규칙' 참조.

**Why:** 전에는 같은 모양의 제목("Ai/claude/…")이 여러 PR 에 보였다. GitHub 는 **커밋이 하나인 브랜치의 PR 은 그 커밋 제목**을, 여러 개면 **브랜치 이름**(예: PR #98 "Ai/claude/operator fixes 1102")을 기본 제목으로 쓴다 — 그래서 R-044 는 의도한 제목이 안 보였다.

**How to apply (병합 부탁 `kind: merge`):** (1) 병합할 브랜치는 **커밋 한 개**로 합치고 그 제목을 `[R-nnn] 짧은 이름 — 이슈 #nn [대상: 공통]` 으로(맨 앞이 요청 번호, 모바일에서 잘리지 않게 앞 40자 안에 핵심) 쓴다. 브랜치 이름도 `ai/claude/rnnn-짧은이름` 으로 번호를 넣는다. (2) 요청 파일 앞머리 `title` 은 `[R-nnn] 병합 부탁 — …`, `summary` 첫머리에 `병합할 PR 제목 → 「…」 이 제목 하나만 병합합니다. 다른 제목의 PR 은 병합하지 마세요`. (3) 본문 맨 위에 **"병합할 제목 (이것 하나만)"** 인용 블록, "하실 일"은 링크 없이 '휴대폰에서 GitHub PC 버전 → 첫 화면 노란 배너 또는 Pull requests → 위 제목 하나 → Create pull request → 검사 초록 → Merge → Confirm, Delete branch 안 누름'. **http 주소를 요청 파일에 쓰지 않는다**(`scratchpad/make_request.py` 가 막는다). (4) 한 번에 한 요청만, 병합할 브랜치 말고 다른 브랜치를 미리 push 하지 않는다(노란 배너가 여럿 생겨 헷갈린다) — 검증용 임시 브랜치는 병합 부탁 전에 정리하거나 로컬에 둔다. (5) 관련 변경은 가능하면 한 요청으로 묶어 알림·병합 횟수를 줄인다(위험이 다른 것은 분리). 관련: [[telegram-push-channel]] [[operator-telegram-requests-only]] [[session-2026-11-02-state]]
