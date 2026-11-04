---
name: feedback-merge-ready-no-wait
description: "운영자 2026-11-04 15:17 채팅 지시 — 병합 부탁은 PR 을 만들자마자 '병합만' 하면 되게(검사 대기·도는 중·건너뜀 표시 없이); 블로그 PR 이벤트 검사 구조 개선(wf) + R-116 기본값 승인"
metadata:
  node_type: memory
  type: feedback
  originSessionId: (세션 번호)
  modified: 2026-11-04T06:27:12.172Z
---

운영자가 채팅으로 "결정 요청(R-116) 기본값으로 진행해주고, CI 테스트가 일부 진행 누락되는 경우가 있어 병합만 바로 진행할수있도록 다시 점검해줘"(2026-11-04 15:17)라고 지시했다.

**Why:** 운영자는 모바일 PC 버전 GitHub 에서 PR 을 만든 뒤 병합만 한다. 블로그 저장소는 PR 을 만들면 `guardrails.yml` 의 `pull_request` 실행(약 2분)·`pr-scope-check.yml`(17초)이 새로 돌고 `ops-inbox.yml` 이 '건너뜀'으로 두 번 찍혀, 화면에 '도는 중'과 '건너뜀'이 보여 '일부 검사가 안 돈다'로 읽히고 병합까지 4~13분을 기다렸다(2026-11-04 점검: 실제 누락은 없었고 전부 성공, 데스크톱은 push 전용(D-28)이라 PR 만든 지 10초 안에 병합). 두 저장소 모두 main 보호 설정 없음(`protected=False`).

**How to apply:**
- 병합 부탁 문구(블로그)에 '검사를 기다리지 말고 바로 병합'(이미 끝난 미리 검사 초록이 기준, PR 화면에 새로 도는 것은 보조)을 쓴다. 데스크톱은 이미 그렇다.
- 구조 개선 'wf'(T3, 구현 에이전트 `a21884bf0c55a9dc5`, 지시서 `S\p23wf_brief.md`): `guardrails.yml` 을 push 전용(어느 브랜치든)으로 + push 시점에 `origin/main` 시험 병합 뒤 검증, `pr-scope-check.yml` 은 `ai/claude/` 머리 PR 건너뜀, `ops-inbox.yml` pull_request types 에서 opened·reopened 제거 → 독립 검증 → 병합 부탁(번호 J3). 검사 강도는 낮추지 않는다. 병합 직후 main 검사(guardrails main push)와 실패 텔레그램 알림은 그대로.
- R-116 기본값 승인: D=0 J=0 K=1 M=0 N=0 — gfix(F+A+B+C+E) 진행, K=1 은 소스 후보 조사(`a34c14924c81c6c9b`)만 하고 추가는 번호 요청으로 따로 승인.
관련: [[blog-project-principles]] [[feedback-precheck-ci-before-merge-request]] [[resume-after-reboot]]
