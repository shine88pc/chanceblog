# AI 기억 사본 (인수인계/AI_기억)

> 이 폴더는 **옛 PC 의 AI 세션이 쌓아 둔 기억 파일(메모리)** 가운데 새 세션에게 아직 쓸모 있는 것을 저장소로 옮겨 둔 **사본**입니다(2026-11-04, PC 이전 준비 — 요청 R-136). 운영자가 PC 를 바꾸고 이전 PC 의 로컬 파일을 모두 지우면 AI 의 개인 기억이 사라지기 때문입니다.
> **정본이 아닙니다.** 저장소의 규칙 문서(`AGENTS.md`·`docs/AGENT_RUNBOOK.md`·`docs/SECURITY_GUARDRAILS.md`)와 `인수인계/작업내용.md`·실제 저장소 상태가 이 사본과 다르면 **그쪽이 이깁니다**(옛 기억은 쓴 시점의 사실입니다).

## 쓰는 법
1. 새 세션은 아래 **A 표**(상시 지시·정책)를 처음에 한 번 훑고, **B 표**(요구서 요약·명세)는 해당 일이 닿을 때 해당 파일만 엽니다.
2. 새 세션에 자체 메모리 기능이 있으면 필요한 것을 옮겨 두어도 됩니다(안 옮겨도 이 폴더가 있으니 됩니다).
3. 파일 안의 `S`·`scratchpad`·`KCY` 는 **옛 PC 의 작업 폴더**를 뜻합니다 — 새 PC 에서는 `W`([`인수인계/도구/README.md`](../도구/README.md) §1)에 해당합니다. `(옛 PC …)` 로 바뀐 곳은 옛 경로였습니다.
4. 이 폴더의 파일은 **고치지 않는 기록 사본**입니다. 새로 알게 된 규칙은 정본 문서(`docs/AGENT_RUNBOOK.md`·`인수인계/작업내용.md`)에 씁니다.
5. 요구서 원문(운영자가 첨부했던 파일)은 **이 저장소에 없습니다**(운영자 지시 — 원문은 저장소 금지). 필요하면 운영자에게 다시 첨부를 부탁합니다(목록은 `인수인계/작업내용.md` §0-4).

## A. 먼저 읽을 것 — 상시 지시·정책

| 파일 | 한 줄 |
|---|---|
| [user-profile.md](./user-profile.md) | 운영자 프로필 — 비개발자, 한국어, 회사 PC |
| [blog-project-principles.md](./blog-project-principles.md) | 프로젝트 원칙 — 풀오토·저장소가 진실·여러 AI 하나의 목표·보안/광고 표면 보호 |
| [quiet-mode-defaults.md](./quiet-mode-defaults.md) | 조용히 일하기·기본값으로 결정·현황 알림(업무 알람은 메세지로) 규칙 |
| [operator-telegram-requests-only.md](./operator-telegram-requests-only.md) | 운영자는 텔레그램 요청(R-번호)만 처리 — GitHub 알림·배너는 무시 |
| [approval-scope-and-site-checks.md](./approval-scope-and-site-checks.md) | T3 승인은 목록 항목에만 유효, 사이트 변경은 병합 전 실제 Jekyll 빌드 비교 |
| [prohibited-sources-policy.md](./prohibited-sources-policy.md) | 약관·표기·robots.txt 가 막는 소스는 접근하지 않는다 |
| [feedback-merge-request-format.md](./feedback-merge-request-format.md) | 병합 부탁 요청 파일 형식(링크 금지·`[R-nnn]` 제목·한 커밋 가지) |
| [feedback-precheck-ci-before-merge-request.md](./feedback-precheck-ci-before-merge-request.md) | 병합 부탁은 검사가 이미 초록일 때만 |
| [feedback-merge-ready-no-wait.md](./feedback-merge-ready-no-wait.md) | PR 을 만들자마자 병합만 하면 되게(블로그 PR 이벤트 검사 구조) |
| [feedback-merge-check-self.md](./feedback-merge-check-self.md) | 운영자가 병합했는지는 AI 가 직접 확인(보고 요구 금지) |
| [handover-single-work-file.md](./handover-single-work-file.md) | 작업 내용은 `인수인계/작업내용.md` 한 파일 — 새 현황 문서 금지 |
| [feedback-worklog-pinned-phrases.md](./feedback-worklog-pinned-phrases.md) | `작업내용.md` 를 고치기 전 시험이 못박은 낱말 확인(`grep -rn 작업내용 tests`) |
| [feedback-progress-updates.md](./feedback-progress-updates.md) | 긴 작업 중 재촉받으면 한 줄 상태 문장(알림 아님) |
| [dev-environment-notes.md](./dev-environment-notes.md) | 개발 환경 — autocrlf·push·커밋 메시지 인코딩·검증 명령·Actions 로그 읽는 법 |
| [dev-tools-permission-2026-11-03.md](./dev-tools-permission-2026-11-03.md) | 개발 도구를 받아 써도 된다는 상시 허가와 범위(`C:\ccgui` 설치 목록) |
| [feedback-no-popup-windows.md](./feedback-no-popup-windows.md) | 화면(창) 확인은 꼭 필요한 검증에만·한 번에 하나 |
| [pr-flow-github-blocked.md](./pr-flow-github-blocked.md) | 내장 브라우저가 GitHub 를 막을 때의 PR 흐름 |

## B. 일이 닿을 때 읽을 것 — 요구서 요약·명세·분석

| 파일 | 한 줄 |
|---|---|
| [topic-strategy-r131-answers.md](./topic-strategy-r131-answers.md) | **5채널 주제 선정 전략** — R-131 답(A~H=1)·7조건·단계 P0~P5·설계 요약 |
| [topic-selection-strategy-v100.md](./topic-selection-strategy-v100.md) | 전략 문서 v1.0.0 요약 |
| [naver-api-hub-handoff-v100.md](./naver-api-hub-handoff-v100.md) | NAVER API HUB 핸드오프 — Search Trend 하나만, 일 100·월 27,000, Fail-Closed |
| [desktop-auto-draft-v031.md](./desktop-auto-draft-v031.md) | 요구서 v0.3.1 — 입력 없이 후보→초안→복사 |
| [gui-design-spec-ui-spec-v1.md](./gui-design-spec-ui-spec-v1.md) | 화면 명세 UI-SPEC v1.0.0 |
| [gui-polish-spec-v11-and-keys.md](./gui-polish-spec-v11-and-keys.md) | UI 정밀 보완 v1.1.0·키 보안·용도별 키 |
| [installer-personal-pc-migration.md](./installer-personal-pc-migration.md) | 설치 파일·개인 PC 이전 최종 단계 16항목 |
| [unsplash-integration-spec-v100.md](./unsplash-integration-spec-v100.md) · [unsplash-image-provider-analysis.md](./unsplash-image-provider-analysis.md) | Unsplash 연동 명세와 분석 |
| [ontology-review-2026-11-03.md](./ontology-review-2026-11-03.md) | 온톨로지 검토에서 적용한 것·적용하지 않은 것 |
| [operator-answers-r078-2026-11-03.md](./operator-answers-r078-2026-11-03.md) | R-078 에 대한 운영자 채팅 답(화면 도구 설치 허용 등) |
| [desktop-repo-chanceblog-desktop.md](./desktop-repo-chanceblog-desktop.md) | 데스크톱 저장소 역할·규칙·병합 방식 |
| [api-key-accounts-policy.md](./api-key-accounts-policy.md) | 한도를 늘릴 목적의 새 계정·키는 권하지 않음 |
| [blog-portfolio-plan.md](./blog-portfolio-plan.md) · [operator-requests-2026-10-25.md](./operator-requests-2026-10-25.md) | 블로그 포트폴리오·초기 운영자 요청 |
| [task-request-file-designation.md](./task-request-file-designation.md) · [handoff-md-is-rough-baseline-is-this-session.md](./handoff-md-is-rough-baseline-is-this-session.md) | 새 작업요청서는 채팅 지목 전에는 접수만 · 옛 핸드오프 md 는 개요 |

## 빠진 것
옛 PC 의 매시간 이어가기 로그(`resume-after-reboot` 등 수백 KB)·세션 상태·PPTX 작업 환경(이 저장소와 무관)은 옮기지 않았습니다. 현재 상태는 `인수인계/작업내용.md` §0, 도구는 [`인수인계/도구/README.md`](../도구/README.md) 입니다.
