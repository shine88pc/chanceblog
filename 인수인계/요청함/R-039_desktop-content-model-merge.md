---
id: R-039
kind: merge
title: 새 저장소 네 번째 코드(원고와 발행 상태의 규칙) 병합 부탁 — 순서와 규칙만 담았습니다
summary: 새 저장소 chanceblog-desktop 의 네 번째 코드 묶음(하나의 원고와 플랫폼별 발행 상태 — 승인 없이는 올라가지 않고, 원고를 고치면 승인이 풀리고, 공개되면 되돌리지 않는 규칙)을 올렸습니다. 병합: 그 저장소 노란 배너 ai/claude/desktop-content-model → Create pull request(제목 그대로) → 검사 4개 초록이면 병합 → Confirm.
urgency: 보통
created: 2026-10-30
---

# R-039 · 새 저장소 — 네 번째 코드(원고·발행 상태 규칙) 병합 부탁

R-035 와 R-038 병합을 확인했습니다(새 저장소 PR #4 11:59, chanceblog PR #86 12:12 — 둘 다 병합된 내용이 올린 것과 같고 검사가 초록입니다).

## 무엇인가
프로그램이 다루는 **글 한 편(원고)** 과 **플랫폼마다의 진행 상태**의 규칙입니다. 화면·저장·실제 발행은 다음 묶음이고, 여기서는 "무엇이 어떤 순서로만 일어날 수 있는가"를 코드와 시험으로 못 박았습니다.
- **플랫폼 5개**: GitHub Pages · Blogger 영문 · Blogger 한글 · 네이버 A · 네이버 B. 글 하나에 이 다섯 개의 진행 상태가 따로 붙습니다.
- **진행 순서**: 네이버는 정해 주신 대로 `NOT_STARTED → DRAFT_GENERATED → REVIEW_REQUIRED → READY_TO_COPY → COPY_COMPLETED → PUBLISHED_MANUAL`(실패는 `PUBLISH_FAILED`). Pages 는 승인 뒤 `COMMITTED → PUSHED → PUBLISHED`, Blogger 는 승인 뒤 `DRAFT_SAVED(초안 저장) → PUBLISHED_MANUAL`(공개는 운영자가 Blogger 에서). 순서를 건너뛰는 것은 막힙니다.
- **승인 없이는 올라가지 않습니다.** 승인은 **지금 원고로 만든 글**에만 줄 수 있고, **원고를 고치면 검토·승인이 풀려** 처음부터 다시 봅니다(이미 올라간 것은 그대로 둡니다).
- **공개로 기록하려면 발행 주소가 있어야** 하고(https, 로그인 정보 없음, 네이버는 blog.naver.com 주소), **공개된 상태는 되돌리지 않습니다**(공개 취소는 사람이 플랫폼에서 합니다).
- 규칙을 어기면 쉬운 말의 오류 안내(오류 코드)로 거절하고 **아무것도 바꾸지 않습니다**. 오류 안내 문서에 코드 4개가 더해져 모두 41개가 됐습니다.
- 저장할 때의 모양(JSON)은 엄격해서, 모르는 칸·빠진 칸·앞뒤가 안 맞는 값은 거절합니다.

## 지금 상태
- **끝난 것**: 시험 128개 통과(앞 묶음 94 + 이번 34), 검사 4개(Windows·Ubuntu × Python 3.10·3.12) 초록. 코드·문서를 일부러 30곳 망가뜨려 봐도 시험이 모두 잡았습니다. 새 저장소의 앞선 코드 4건은 병합 뒤 **별도 검토자**(제가 쓰지 않은 AI)가 따로 검토하고 있고, 결과가 오면 고칠 것을 다음 묶음에 반영합니다.
- **들어 있는 것**: 코드 2개(`content/status.py`·`content/model.py`)와 시험, 문서(구조 문서 §9 상태 표·오류 안내). 외부 연결·시크릿·새 설치 항목은 없습니다.
- **곧**: 다음 묶음은 Chance 와 같은 형식의 글 만들기(미리보기 — 실제 Chance 글로 형식을 고정)입니다.

## 하실 일 (병합, 2분)
1. 새 저장소 첫 화면(https://github.com/shine88pc/chanceblog-desktop) 맨 위 노란 **"ai/claude/desktop-content-model had recent pushes" — Compare & pull request** 배너를 누릅니다. 배너가 안 보이면 이 주소를 엽니다: https://github.com/shine88pc/chanceblog-desktop/compare/main...ai/claude/desktop-content-model?quick_pull=1
2. **제목은 그대로 두고** 초록 **Create pull request**.
3. 화면 맨 아래 검사 4개가 모두 초록(All checks have passed)이 될 때까지 기다린 뒤 **Merge pull request(또는 Squash and merge) → Confirm**. **Delete branch 는 누르지 않습니다.**

병합하셨는지는 제가 직접 확인합니다.

## 병합 뒤 일어나는 일
공개 사이트·블로그 발행·기존 자동 실행에는 아무 영향이 없습니다. 새 저장소 `main` 에 코드와 시험이 생길 뿐입니다.

## 안 될 때
빨간 ✗ 이거나 'conflicts' 가 보이면 병합하지 말고, [답하기] → 요청 번호 **R-039** → 답변 '문제' 를 고르고 메모에 화면에 보이는 문구를 적어 주세요.
