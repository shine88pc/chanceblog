# AI 기억 사본 (인수인계/AI_기억)

> 이 폴더는 **옛 PC 의 AI 세션이 쌓아 둔 기억 파일(메모리)** 가운데 새 세션에게 아직 쓸모 있는 것을 저장소로 옮겨 둔 **사본**입니다(2026-11-04, PC 이전 준비 — 요청 R-136). 운영자가 PC 를 바꾸고 이전 PC 의 로컬 파일을 모두 지우면 AI 의 개인 기억이 사라지기 때문입니다.
> **정본이 아닙니다.** 저장소의 규칙 문서(`AGENTS.md`·`docs/AGENT_RUNBOOK.md`·`docs/SECURITY_GUARDRAILS.md`)와 `인수인계/작업내용.md`·실제 저장소 상태가 이 사본과 다르면 **그쪽이 이깁니다**(옛 기억은 쓴 시점의 사실입니다).

## 쓰는 법
1. 새 세션은 아래 **A 표**(상시 지시·정책)와 **A-2 표**(2026-11-16 이후의 상시 지시 — 2026-11-23 사본)를 처음에 한 번 훑고, **B 표**(요구서 요약·명세)는 해당 일이 닿을 때 해당 파일만 엽니다.
2. 새 세션에 자체 메모리 기능이 있으면 필요한 것을 옮겨 두어도 됩니다(안 옮겨도 이 폴더가 있으니 됩니다).
3. 파일 안의 `S`·`scratchpad`·`KCY` 는 **옛 PC 의 작업 폴더**를 뜻합니다 — 새 PC 에서는 `W`([`인수인계/도구/README.md`](../도구/README.md) §1)에 해당합니다. `(옛 PC …)` 로 바뀐 곳은 옛 경로였습니다.
4. 이 폴더의 파일은 **고치지 않는 기록 사본**입니다. 새로 알게 된 규칙은 정본 문서(`docs/AGENT_RUNBOOK.md`·`인수인계/작업내용.md`)에 씁니다.
5. 요구서 원문(운영자가 첨부했던 파일)은 **이 저장소에 없습니다**(운영자 지시 — 원문은 저장소 금지). 필요하면 운영자에게 다시 첨부를 부탁합니다(목록은 `인수인계/작업내용.md` §0-4).
6. **사람 이름·메일은 쓰지 않고 역할 말로 쓴다** — '운영자'·'저장소 소유자'·'운영자 계정'. 이 폴더 글을 새로 쓰거나 개인 표현을 바꿀 때 지킨다(위 4번 '고치지 않는 기록 사본'의 유일한 예외는 개인을 알아볼 수 있는 표현을 중립 말로 바꾸는 일이다 — 2026-11-22 확인 015 의 12번으로 이 폴더 세 파일의 이름·메일을 바꿨다). 공개 이력의 과거분은 지우지 못한다 — 효과는 앞으로의 파일에만 있다. 공개 연락처 메일이나 도구의 고정 작성자 값이 이 폴더에 다시 나오면 `tests/test_personal_expressions.py` 가 빨개진다.

## A. 먼저 읽을 것 — 상시 지시·정책

| 파일 | 한 줄 |
|---|---|
| [user-profile.md](./user-profile.md) | 운영자 프로필 — 비개발자, 한국어, 회사 PC |
| [blog-project-principles.md](./blog-project-principles.md) | 프로젝트 원칙 — 풀오토·저장소가 진실·여러 AI 하나의 목표·보안/광고 표면 보호 |
| [quiet-mode-defaults.md](./quiet-mode-defaults.md) | 조용히 일하기·기본값으로 결정·현황 알림(업무 알람은 메세지로) 규칙 — **사본의 '07~23시·밤에는 안 보냄'은 옛 값이다(2026-11-05 야간 전송 제한 삭제, 정본 문서가 우선)** |
| [operator-telegram-requests-only.md](./operator-telegram-requests-only.md) | 운영자는 텔레그램 요청(R-번호)만 처리 — GitHub 알림·배너는 무시 |
| [approval-scope-and-site-checks.md](./approval-scope-and-site-checks.md) | T3 승인은 목록 항목에만 유효, 사이트 변경은 병합 전 실제 Jekyll 빌드 비교 |
| [prohibited-sources-policy.md](./prohibited-sources-policy.md) | 약관·표기·robots.txt 가 막는 소스는 접근하지 않는다 |
| [feedback-merge-request-format.md](./feedback-merge-request-format.md) | 병합 부탁 요청 파일 형식(링크 금지·`[M###]` 제목·한 커밋 가지 — 연결 파일 본문은 11-02 판이라 옛 `[R-nnn]` 표기, 현행은 작업내용 §0-2 3번) |
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

## A-2. 2026-11-16 이후 새로 쌓인 상시 지시 — 2026-11-23 사본

위 A 표는 2026-11-04 사본이고 이 표의 9개는 그 뒤(2026-11-16–23)에 쌓인 운영자 상시 지시·정책의 사본입니다(2026-11-23 새 PC 이어받기 보강 MIG1 이 옛 PC 의 AI 기억 폴더에서 개인 정보를 가려 옮김 — 윈도 계정 이름·메일·세션 번호·회사 계정 세부는 일반 말로 바꿨고, ASCII 물결표 두 곳은 en dash 로, 확인 021 로 없앤 옛 답변 양식의 메뉴 이름 한 곳은 풀어 쓴 말로 고침 — 시험이 옛 메뉴 이름이 새로 생기는 것을 막는다). 이 표의 파일 안 `C:/work/ai` 는 옛 PC 의 작업 폴더 W 의 이름이고 `scratch/…` 는 W 아래 도구입니다(도구 README 9-2). 정본이 아니고 정본은 `인수인계/작업내용.md` §0-2 와 `docs/AGENT_RUNBOOK.md` §8 입니다.

| 파일 | 한 줄 |
|---|---|
| [approval-answers-need-valid-form.md](./approval-answers-need-valid-form.md) | 확인 요청 답은 새 양식(대상번호+선택)·채팅 번호 답만 승인 — 이슈에 접수 봇의 거절 답글이 있으면 승인이 아님(2026-11-16 확인 019·020 사건: 승인으로 읽기 전에 봇 답글 확인) |
| [blog-slots-limit-on-hold.md](./blog-slots-limit-on-hold.md) | 블로그 연결 수 한도(확인 025)는 운영자가 ④ 보류 — 다시 묻지 않고 기다림, 설계서는 보관 |
| [low-ai-cost-operations.md](./low-ai-cost-operations.md) | AI 사용량 점검 결론과 확인 031(R-463)·운영자 채팅 승인(새 알림 워크플로 둘)·경제 모드는 프로그램 완성을 운영자가 확인한 뒤 시작 — `docs/AGENT_RUNBOOK.md` §8 의 근거 |
| [operator-merges-on-pr-open.md](./operator-merges-on-pr-open.md) | 운영자는 `[M###]` PR 이 열리면 병합 부탁 알림 전에도 몇 분 안에 병합하기도 한다(M070·M084) — 알림에 다가올 M 번호를 쓰지 말고 CI 초록 직후 부탁을 보낸다 |
| [operator-reports-via-messages-not-chat.md](./operator-reports-via-messages-not-chat.md) | 알릴 것은 세션 채팅이 아니라 텔레그램 알림(요청 파일)으로(2026-11-16 23시 지시) |
| [operator-wants-fewer-confirmations.md](./operator-wants-fewer-confirmations.md) | 요청은 '방향'이고 세부·기본값은 추천안으로 알아서 진행, 번호 있는 확인은 방향 이탈·대규모·T3 일 때만(2026-11-16 22:59 지시) |
| [parallel-wave-2026-11-22.md](./parallel-wave-2026-11-22.md) | 11-22 13갈래 병렬 구현(5일 공백 만회) — 갈래·절차·heavy 잠금·크론 만료, 이어받는 세션이 먼저 볼 것 |
| [pc-shared-moderate-performance.md](./pc-shared-moderate-performance.md) | 공용 PC 탄력 운영(2026-11-23) — 낮엔 중간, 저녁엔 더, `scratch/pc_load.py` 로 권고 에이전트 수 확인(개인 PC 에서의 값은 미정) |
| [photo-analysis-local-only-directive.md](./photo-analysis-local-only-directive.md) | 사진 분석 로컬 한정 지시(2026-11-16) — 확인 018 = 사진은 PC 밖으로 안 나감, 글자 읽기(OCR)는 이 PC 안에서만, 다운로드·설치·병합·비용은 별도 승인, 확인 026–030 의 승인 범위 |

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
옛 PC 의 매시간 이어가기 로그(`resume-after-reboot` 등 수백 KB)·세션 상태·PPTX 작업 환경(이 저장소와 무관)은 옮기지 않았습니다. 현재 상태는 `인수인계/작업내용.md` 의 §0-A 카드와 §0-1, 도구는 [`인수인계/도구/README.md`](../도구/README.md) 입니다.
2026-11-23 의 A-2 표 사본에도 일부러 넣지 않은 것이 있습니다 — 블로그·앱 프로젝트와 무관한 개인 업무 기억 둘과, 11-15 이관 때의 옛 인수 스냅샷(그 뒤 상태가 작업내용·요청 가지에 다 있어 낡았습니다)입니다. 개인 정보(윈도 계정 이름·메일·세션 번호·회사 계정 세부)가 든 곳은 일반 말로 바꿔 옮겼습니다.
