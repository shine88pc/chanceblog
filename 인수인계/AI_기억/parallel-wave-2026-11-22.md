---
name: parallel-wave-2026-11-22
description: "2026-11-22 운영자 채팅 지시로 13갈래 병렬 구현(5일 공백 만회) — 갈래·규칙·병합 순서·CPU 포화 대책, 이어받는 세션이 먼저 볼 것"
metadata:
  node_type: memory
  type: project
  originSessionId: (세션 번호)
  modified: 2026-11-21T23:24:00.203Z
---

2026-11-22 06:39 세션 재개(11-17 23:00 강제 재부팅 뒤 5일 공백). 운영자 채팅 지시: "오늘은 최대한 에이전트 투입해서 5일간의 공백을 당겨서 작업 진행". 그래서 구현자 에이전트 13명 + 조사 1명을 동시에 돌렸다.

- 갈래(작업 폴더 `C:/work/ai/<…>`·가지 `ai/claude/NO-MERGE-<…>-wip`): 앱 L2·L3·L4·L5·L8, 글자 읽기 OCR B1(라운드 2)·B2(화면)·B3(초안 연결)·D(빌드 흐름 초안), 블로그 L6·L7·AP6a(F072)·AP6b(F113), 조사 AP-A. 지시서 `audit6/improve/wave2/BRIEF_*.md`·공통 `GENERAL.md`·검증 공통 `VERIFY_GENERAL.md`, 상태는 `C:/work/ai/이관_상태.md` 맨 아래 최신 노트와 `scratch/lanes.py`.
- 절차(바뀌지 않음): 구현자는 WIP 커밋만 → 총괄이 `NO-MERGE-*` 푸시·CI → 독립 검증 S(안전)·Q(규칙·시험) → 병합 가지 `M###` 한 커밋 → 병합 부탁(운영자는 한 번에 하나만 병합) → 병합 뒤 `병합완료 확인` 알림. 병합 순서 계획: 앱 L8→L2→L3→L4→L5, 블로그 L6→L7(앱·블로그는 병행 가능).
- CPU 100% 포화 대책: 전체 시험·ci_shard 는 `qt_lock.py --name heavy -- <명령>` 로 한 번에 하나, Qt 시험은 이름 없는 `qt_lock.py`. 시간 재는 시험이 바쁜 PC 에서 흔들리면 사실만 보고하고 시험을 느슨하게 하지 않는다.
- 크론은 세션 전용이고 7일 뒤 만료(현재 `658756fa`, 11-22 06:40 생성 → 11-29 전에 다시 만든다). 같은 이름의 중복 크론이 있으면 하나만 남긴다(11-22 에 옛 것 삭제).

**Why:** 운영자가 5일 공백을 하루에 당겨 달라고 했고, 병합은 운영자만 하므로 병렬 구현·검증 파이프라인을 미리 채워 두는 것이 가장 빠르다.
**How to apply:** 새 세션은 `이관_상태.md` 최신 노트를 읽고 `lanes.py` 로 갈래 상태를 본 뒤 끝난 갈래부터 검증·병합 절차로 넘긴다. 운영자 승인 규칙은 [[approval-answers-need-valid-form]]·[[operator-wants-fewer-confirmations]]·[[operator-reports-via-messages-not-chat]] 그대로이고, 글자 읽기는 [[photo-analysis-local-only-directive]] 를 따른다.
