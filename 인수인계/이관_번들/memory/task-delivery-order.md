---
name: task-delivery-order
description: KCY 작업요청서 3개의 전달 순서(4번 발행 복구 → 2번 Actions 가이드·보안 → 3번 콘텐츠 전략)와 PR 진행 방식 — 현재 상태·남은 일은 저장소의 인수인계/작업내용.md가 기준
metadata:
  node_type: memory
  type: project
  originSessionId: 6dd8f403-b855-4b67-ab8d-8eba60cc6b54
  modified: 2026-10-26T00:37:55.274Z
---

`<사용자폴더>\Desktop\KCY\작업진행확인.txt`가 정한 순서: ① `CLAUDE CODE TASK 4 PUBLISH RECOVERY.md`(발행 복구)를 먼저 하고 진단 보고를 사용자가 승인 ② `CLAUDE CODE TASK 2 ACTIONS GUIDE SECURITY.md`(Actions 가이드+보안)는 4번과 같이 계획(둘 다 워크플로 권한·토큰을 건드려 충돌을 줄이려는 것) ③ 복구가 끝난 뒤 `PLAN AND TASK 3 CONTENT STRATEGY.md`를 Phase 0부터. 파일명은 txt에서 밑줄이지만 실제 파일은 공백이다.

**Why:** 3번의 모든 Phase는 발행 복구가 끝났다는 전제다. 4번 1단계(진단)는 읽기 전용이고 승인 후에만 코드를 고친다.
**How to apply:** 현재 상태·진행 중 작업·승인 대기·사용자 몫은 저장소 **`인수인계/작업내용.md`**(사용자가 2026-10-26에 "md 파일 하나로 지속 업데이트"로 정함, [[handover-single-work-file]])와 `docs/SESSION_START.md` §5·§6이 기준이다 — 이 메모리에 상태를 복제하지 않는다(어긋난다). 새 세션은 거기부터 읽는다. 방식: 작은 T2 PR → 독립 검증(새 clone·diff와 직접 실행만 근거) → 지적 반영 → 변경분 재검증 → 스쿼시 병합 → 병합 직후 Actions 관측. 병합한 브랜치는 지우지 않는다. T3(공개 콘텐츠·신뢰 목록·광고 표면)는 사용자의 채팅 승인이 있어야 진행하고, 답이 없는 승인 대기 항목은 진행하지 않는다. 사용자 정책: 약관이 금지한 출처는 접근하지 않는다([[prohibited-sources-policy]]). 관련: [[blog-project-principles]]

2026-10-25: 10/18 커밋 cc0c212의 `123.txt`(구글 API 키 형식 문자열, b110f74에서 삭제했지만 공개 기록에 남음)가 검증 중 발견됐고, 사용자가 AI Studio에서 옛 키를 삭제·재발급한 뒤 GitHub `GEMINI_API_KEY` 시크릿을 직접 교체했다. BLOGGER_* 시크릿은 Blogger 초안 저장 모드가 생기기 전에는 등록하지 않기로 안내했다(등록하면 건강 글이 검수 없이 공개됨).
