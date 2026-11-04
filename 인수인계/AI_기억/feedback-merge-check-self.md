---
name: merge-check-self
description: 운영자가 PR 을 직접 병합한 뒤 알려 주지 않아도 AI 가 GitHub 공개 REST 로 병합·검사 결과를 직접 확인한다(공용 PC라 계속 못 씀)
metadata:
  node_type: memory
  type: feedback
  originSessionId: (세션 번호)
  modified: 2026-10-27T04:31:47.526Z
---

운영자가 PR 을 병합했는지는 **AI 가 직접 확인**한다. 병합했다고 채팅에 알려 달라고 요구하지 않는다.

**Why:** 2026-10-27 사용자 지시: "병합 완료 여부를 직접 체크 하도록 하는게 좋겠어. 공용 PC라 계속 사용할 수가 없어". 사용자는 공용 PC 에서 짬짬이 접속해 링크를 눌러 병합만 하고 떠난다.

**How to apply:** PR 만들기 링크를 드린 직후 로그인 없는 공개 REST(`api.github.com/repos/shine88pc/chanceblog/pulls`·`commits`·`check-runs`)를 150초 간격으로 읽는 감시(Monitor, 최대 약 29분 → 끝나면 다시 켬)를 걸어 둔다. 병합이 감지되면 main 의 검사·배포 결과까지 확인하고 다음 묶음으로 넘어간다. 공개 API 로 볼 수 없는 것(저장소 설정·시크릿 등록 여부)만 사용자에게 묻는다. 안내 문서에도 "병합 뒤 따로 알리지 않아도 된다"고 쓴다. 관련: [[pr-flow-github-blocked]].
