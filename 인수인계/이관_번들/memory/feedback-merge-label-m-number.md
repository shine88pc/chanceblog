---
name: feedback-merge-label-m-number
description: "운영자 2026-11-06 ~18:45 채팅 — 병합 화면(GitHub)에서 '병합해도 되는 것'을 M 번호로 알아보게: PR 제목 `[M###] …`·가지 `ai/claude/M###-슬러그`, 병합하면 안 되는 가지는 `NO-MERGE`. 요청 가지 이름이 `ai/claude/NO-MERGE-operator-requests` 로 바뀜. R-176 부터 도구가 강제"
metadata:
  node_type: memory
  type: feedback
  originSessionId: 921b6032-bba9-4b52-8c2d-b24e5509c445
  modified: 2026-11-06T09:55:31.964Z
---

**지시(운영자 채팅, 2026-11-06 ~18:45):** 텔레그램 병합 요청은 `M001` 로 오는데 GitHub 병합 화면에는 `[R175] … ai/claude/r175-p3-topic-store-2` 로 보여 헷갈린다. 처음 의도는 병합 단계에서 **`[M001] 커밋명`** 으로 보여 "M 이면 병합하면 되는 것"으로 바로 판단하는 것이었다. 가지 이름도 `ai/claude/M001-p3-topic-store-2` 꼴로 별도 요청 번호(R-nnn)를 확인하지 않아도 판단하게. **병합하면 안 되는 것은 다른 식으로 표시**하고, 병합해야 하는 것에는 `M001` 을 넣어 표시.

**Why:** 운영자는 비개발자이고 폰/PC GitHub 화면에서 제목·가지 이름만 보고 판단한다. R 번호는 내부 작업 ID 일 뿐 병합 화면에 나오면 혼란.

**How to apply (2026-11-06 18:5x 적용 완료):**
- **병합 가지 이름 = `ai/claude/M###-<슬러그>`**, **한 커밋 제목(=PR 제목) = `[M###] <제목> [대상: …]`**. M 번호는 `next_notice_no.py` 가 정하는 다음 병합 알림 번호이고 **가지를 만들기 전에** 정한다(`python -X utf8 W\next_notice_no.py --repo W\wt_r30 --dir W\wt_r30 --local`). 여러 병합 가지를 미리 올릴 땐 M 번호를 순서대로 예약(예: M002=P4a·M003=WP-A·M004=WP-B) — 요청 파일은 병합 순서대로 나중에 만든다(자동 번호가 같은 값을 주는지 확인).
- **`W\make_request.py` 가 R-176 부터 강제**한다: 병합 요청의 `pr_title` 이 `[<no>] ` 로 시작하지 않거나 가지 이름이 `ai/claude/<no>-…` 가 아니면 요청 파일을 만들지 않는다(R-175 의 `[R-175]` 는 예외). 이 강제는 W 도구에만 있고 저장소 사본(`인수인계/도구/work/make_request.py`)·문서(`PR_병합_방법.md`·`운영자_요청함_사용법.md`)에는 아직 반영 안 됨 → 다음 블로그 PR 에 묶어 갱신할 것.
- 요청 파일 `id`·파일 이름은 그대로 `R-nnn_…`(작업 ID). 텔레그램 병합 알림 머리는 `🔀 M###` 이고 'PR 제목' 줄에 `[M###] …` 가 그대로 나온다. 요청 `title` 도 `[M###] 병합 부탁 — …` 꼴로.
- **병합하면 안 되는 가지는 이름에 `NO-MERGE`**: 블로그 요청 가지는 **`ai/claude/operator-requests-2` → `ai/claude/NO-MERGE-operator-requests` 로 이름을 바꿨다**(18:51; 새 이름 push 는 알림 0건 — 같은 커밋이 옛 이름에도 있어 '다른 브랜치에도 있어 알리지 않음' 규칙으로 걸러짐, 그 뒤 옛 이름 삭제). 진단용 임시 가지도 `ai/claude/NO-MERGE-…` 로. 미리 CI 만 돌리려는 가지도 병합 가지면 처음부터 `M###-…`(번호 예약)로 만든다. 푸시는 항상 명시적으로 `git push origin ai/claude/NO-MERGE-operator-requests`(wt_r30 의 현재 가지, 업스트림 없음).
- 크론은 id 가 `9eceb613`(`7 * * * *`)으로 새로 만들었고 `W\cron_status_prompt_v3.txt`·크론 본문에 새 가지 이름과 이 규칙을 반영했다.
- 답변 양식 `대상번호` 는 확인 요청 번호(`001`)나 `r176` 같은 요청 번호만 받고 `M002`·`P012` 는 거절한다(`parse_target`) — 병합 알림에 문제를 알리려면 요청 번호가 필요한데 폰 메시지엔 R 번호가 안 나온다(알려진 틈 — 운영자가 불편해하면 `M###` 도 받게 하는 개선을 제안).
- 관련: [[feedback-merge-request-format]] [[telegram-notification-standard-2026-11-06]] [[feedback-precheck-ci-before-merge-request]]
