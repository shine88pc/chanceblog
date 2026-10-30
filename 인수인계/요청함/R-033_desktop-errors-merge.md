---
id: R-033
kind: merge
title: 새 저장소 첫 코드(오류 코드 안내) 병합 부탁 — 코드 하나, 시크릿·외부 연결 없음
summary: 새 저장소 chanceblog-desktop 의 첫 코드 묶음(실패를 오류 코드 하나로 모아 쉬운 문구로 보여 주는 부분, 시험 포함)을 올렸습니다. 병합: 그 저장소 노란 배너 ai/claude/desktop-errors → Create pull request(제목 그대로) → 검사 4개 초록이면 병합(R-030 때처럼) → Confirm. R-029(네이버)와 순서는 상관없습니다.
urgency: 보통
created: 2026-10-30
---

# R-033 · 새 저장소 — 첫 코드(오류 코드 안내) 병합 부탁

R-030 병합 확인했습니다(PR #1, 10:44, 검사 초록, 내용이 올린 것과 같음). 감사합니다.

## 무엇인가
프로그램 안에서 어떤 실패가 나든 **오류 코드 하나**로 모아, 화면에는 원인과 하실 일을 쉬운 말로 보여 주는 부분입니다(AI 를 쓰지 않는 규칙 방식). 예를 들면:
- Blogger 로그인 만료(HTTP 401) → "Blogger 로그인이 만료되었습니다" + **다시 로그인** 안내
- Git 올리기 실패 → 권한(로그인) 문제인지 인터넷 문제인지 나눠서 안내
- 배포(Actions) 실패 → 실패한 **워크플로·잡 이름**을 보여 줌
- 파일 저장 실패 → **저장 경로**와 권한 확인 안내
- 호출 한도 초과 → **다시 시도할 수 있는 시각**을 보여 줌(한도를 우회하지 않음)
문구와 코드의 정본은 문서(`docs/TROUBLESHOOTING.md`, 35개 코드)이고, 코드 쪽 목록은 그 표에서 스크립트가 **자동으로 만듭니다**. 문서만 고치고 다시 만들지 않으면 시험이 실패해서 둘이 어긋나지 않습니다. 표에 없는 실패는 '예상하지 못한 오류' 안내로 받아 안내 화면이 또 실패하지 않게 합니다.

## 지금 상태
- **끝난 것**: 시험 50개 모두 통과, 검사 4개(Windows·Ubuntu × Python 3.10·3.12) 초록. 일부러 코드·문서를 19곳 망가뜨려 봐도 시험이 모두 잡았습니다.
- **들어 있는 것**: 오류 코드 카탈로그·문구 만들기 코드(`src/chanceblog_desktop/errors/`), 문서에서 카탈로그를 만드는 스크립트(`scripts/sync_errors.py`), 시험, 문서 몇 줄. 외부 연결·시크릿·새 설치 항목은 없습니다.
- **곧**: 이어서 올릴 코드 묶음은 ① chanceblog 의 검사 코드를 원본 그대로 가져다 쓰는 부분 ② 연결한 chanceblog 저장소를 확인하고 최신으로 맞추는 부분(GitHub Pages 발행의 바탕)입니다. 한 번에 하나씩 병합을 부탁드립니다.

## 하실 일 (병합, 2분)
1. 새 저장소 첫 화면(https://github.com/shine88pc/chanceblog-desktop) 맨 위 노란 **"ai/claude/desktop-errors had recent pushes" — Compare & pull request** 배너를 누릅니다. 배너가 안 보이면 이 주소를 엽니다: https://github.com/shine88pc/chanceblog-desktop/compare/main...ai/claude/desktop-errors?quick_pull=1
2. **제목은 그대로 두고** 초록 **Create pull request**.
3. 화면 맨 아래 검사 4개가 모두 초록(All checks have passed)이 될 때까지 기다린 뒤 **Merge pull request(또는 Squash and merge) → Confirm**. **Delete branch 는 누르지 않습니다.**

병합하셨는지는 제가 직접 확인합니다.

## 병합 뒤 일어나는 일
공개 사이트·블로그 발행·기존 자동 실행에는 아무 영향이 없습니다. 새 저장소 `main` 에 코드와 시험이 생길 뿐입니다.

## 안 될 때
빨간 ✗ 이거나 'conflicts' 가 보이면 병합하지 말고, [답하기] → 요청 번호 **R-033** → 답변 '문제' 를 고르고 메모에 화면에 보이는 문구를 적어 주세요.
