---
name: handover-single-work-file
description: 사용자 지시 — 작업 내용은 저장소 인수인계 폴더의 md 한 파일(인수인계/작업내용.md)로 관리하고 계속 갱신한다
metadata:
  node_type: memory
  type: feedback
  originSessionId: (세션 번호)
  modified: 2026-10-25T23:42:15.803Z
---

사용자(2026-10-26 채팅): "작업 내용에 대해서는 인수인계 폴더에 md 파일 하나로 관리해서 지속 업데이트하는 걸로 해줘". 저장소 `shine88pc/chanceblog`의 `인수인계/작업내용.md`가 그 파일이다(PR #28로 신설, AGENTS.md §4·docs/SESSION_START.md §4에 규칙 반영).

**Why:** 사용자는 비개발자이고 문서가 흩어져(WORKLOG·SESSION_START §5·§6·REQUEST_BRIEFING §8·HANDLER §0) 현황을 한 번에 보기 어렵다. 회사 PC라 파일을 반출할 수 없어 저장소가 유일한 인수인계 통로다.
**How to apply:** 작업을 시작·병합하거나 검증 결과·사용자 결정이 나올 때와 하루 마감 때 그 파일의 §1~§6과 맨 위 "마지막 갱신"을 고친다. 새 현황·일지 문서를 따로 만들지 않는다. WORKLOG.md는 AI끼리 보는 기술 증거 기록으로만 남긴다. PR #27(Chance 출처 개편) 병합 뒤에 SESSION_START §5·§6, REQUEST_BRIEFING §8, HANDLER §0의 현황 중복을 이 파일로 모으고 거기에는 링크만 남기는 정리를 이어서 한다(같은 줄을 건드려 #27과 충돌해서 미룸). 관련: [[task-delivery-order]] [[user-profile]]
