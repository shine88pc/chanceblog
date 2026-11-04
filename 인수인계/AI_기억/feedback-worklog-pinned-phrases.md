---
name: feedback-worklog-pinned-phrases
description: "블로그 저장소 `인수인계/작업내용.md` 를 고칠 때는 먼저 `grep -rn 작업내용 tests`(시험이 문서 낱말을 못박음) — 2026-11-04 R-121 첫 가지가 '수정분 재검증' 낱말을 지워 검사 빨강"
metadata:
  node_type: memory
  type: feedback
  originSessionId: (세션 번호)
  modified: 2026-11-04T08:12:45.392Z
---

`인수인계/작업내용.md`(단일 현황 문서)의 낱말·문구 일부를 **시험이 못박고 있다**(문서 표류 방지 시험). 낡은 줄을 정정하려고 문구를 바꾸거나 지우면 가드레일 '단위 테스트' 가 빨갛게 된다 — 로컬에서 문서 시험 몇 개만 돌려서는 못 잡는 경우가 있다(`test_agent_docs`·`test_glossary_docs`·`test_workflow_names` 는 통과했는데 `test_chance_credit_fix` 가 실패했다).

**Why:** 2026-11-04 R-121(현황 문서 갱신) 첫 가지 `ai/claude/r121-state-docs-1` 이 U3 행의 '수정분 재검증 뒤 병합 부탁' 문구를 '병합 완료'로 정정하며 `test_chance_credit_fix.py:611-613` 가 찾는 낱말('수정분 재검증')을 모두 지워 push 검사가 2분 21초 만에 빨강이 됐다. 원인은 로그인 없이는 실패한 시험 이름이 안 보여(주석에는 마지막 줄뿐) 시험 파일에서 `작업내용` 을 grep 해 찾았다. 낱말을 되살린 `-2` 가지로 해결(병합 16:51).

**How to apply:** 작업내용.md 를 고치기 전 `grep -rn 작업내용 tests` 로 못박힌 낱말을 확인하고 지키거나, 정정이 꼭 필요하면 그 시험의 기대도 같은 변경에서 고친다. 지금 알려진 것: '수정분 재검증'·'재시도 간격을 늘릴지'·'1차 독립 검증'(test_chance_credit_fix), 'Unsplash 사진 출처·ixid(U3'·'홈페이지 기본 썸네일 4장'·'기존 글'(test_chance_credit), 'Blogger 대표 사진' 2회 이상(test_main_image_run), t1 시험은 '최종 가지를 push 한 직후(병합 전'·"텔레그램 수신 '예약 읽기'". 문서 변경 가지는 push 후 CI 초록을 확인한 다음에만 병합 부탁(이미 하던 대로). 푸시 검사 실패 원인을 로그 없이 찾는 법: 주석(`run_annotations.py`)에서 실패 단계 이름 → 관련 시험 파일 grep → 로컬에서 그 모듈 실행. 관련: [[feedback-precheck-ci-before-merge-request]] [[resume-after-reboot]]
