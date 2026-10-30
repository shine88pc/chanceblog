---
id: R-030
kind: merge
title: 새 저장소(chanceblog-desktop) 첫 뼈대 병합 부탁 — 문서와 시험 CI 뿐입니다
summary: 만들어 주신 새 저장소 chanceblog-desktop 에 첫 뼈대(규칙·구조·결정·오류 안내·릴리스·보안·이관 문서와 시험 CI)를 올렸습니다. 병합: 그 저장소 노란 배너 ai/claude/desktop-bootstrap → Create pull request(제목 그대로) → 검사 4개가 초록이면 Squash and merge → Confirm. 코드·시크릿은 없고 R-029 와 순서는 상관없습니다.
urgency: 보통
created: 2026-10-30
---

# R-030 · 새 저장소 chanceblog-desktop — 첫 뼈대 병합 부탁

## 무엇인가
운영자께서 직접 만들어 주신 새 저장소(https://github.com/shine88pc/chanceblog-desktop)에 **문서와 시험 CI 만** 올렸습니다. 프로그램 코드·키·시크릿은 없습니다. 오늘 정해 주신 방향(독립 프로그램, 기존 `chanceblog` 저장소 연결, 무료 AI 는 선택 보조·기본 꺼짐, AI 자동 전환 구조 제외, 오류는 규칙 기반 안내 우선)을 모두 반영했습니다.
- `README.md`·`AGENTS.md`·`CLAUDE.md`·`CHANGELOG.md`·`VERSION`: 어느 AI 도구든 이어받을 수 있는 규칙(두 저장소의 관계, 절대 규칙, 승인 단계). `AGENTS.md` 는 모든 AI 공통, `CLAUDE.md` 는 Claude 전용입니다.
- `docs/`: 구조(`ARCHITECTURE` — GitHub Pages 는 기존 chanceblog 로컬 저장소를 연결해 글을 만들고 기존 자동 배포를 그대로 쓴다, 선택 보조 AI 는 기본 꺼짐, AI 없이 되는 17개 기능)·결정 기록(`DECISIONS`)·플랫폼별 하는 것/안 하는 것(`PLATFORM_POLICY`, 티스토리 제외·격리)·**오류 코드와 안내 문구**(`TROUBLESHOOTING`)·설치와 자동 업데이트 방식(`RELEASE`)·보안(`SECURITY`)·개인 PC 준비(`MIGRATION`).
- `.env.example`: 변수 **이름만** 있고 값은 비어 있습니다. 실제 키 파일은 GitHub 에 올리지 않는 설정입니다.
- `.github/workflows/ci.yml`: 시험만 돌리는 검사(읽기 전용, 시크릿 없음 — Ubuntu·Windows × Python 3.10·3.12 네 가지).
- `tests/test_repo_layout.py`: 문서 링크·결정 번호·버전·비밀 방지 설정이 어긋나거나, 정하신 범위(AI 자동 전환 제외, GitHub Models 제외, 티스토리 격리, AI 없이 되는 기능 목록 등)가 문서에서 빠지면 실패하는 시험 21개. 문서를 일부러 29곳 망가뜨려 시험이 모두 잡는지도 확인했습니다.
`VERSION` 은 0.0.0 이고 설치 파일은 아직 없습니다. 운영자 호출·승인 요청은 계속 `chanceblog` 의 텔레그램 채널로 보내므로 새 저장소에는 텔레그램 시크릿을 두지 않았습니다.

## 하실 일 (병합, 2분)
1. 새 저장소 첫 화면(https://github.com/shine88pc/chanceblog-desktop) 맨 위 노란 **"ai/claude/desktop-bootstrap had recent pushes" — Compare & pull request** 배너를 누릅니다. 배너가 안 보이면 이 주소를 엽니다: https://github.com/shine88pc/chanceblog-desktop/compare/main...ai/claude/desktop-bootstrap?quick_pull=1
2. **제목은 그대로 두고** 초록 **Create pull request**.
3. 화면 맨 아래 검사 4개가 모두 초록(All checks have passed)이 될 때까지 기다린 뒤(보통 3~8분) **Squash and merge → Confirm squash and merge**. **Delete branch 는 누르지 않습니다.**

병합하셨는지는 제가 직접 확인합니다. `chanceblog` 쪽 R-029(네이버 연결)와는 서로 독립이라 순서는 상관없습니다.

## 병합 뒤 일어나는 일
- 새 저장소 `main` 에 문서와 CI 가 생깁니다. 공개 사이트·블로그 발행·기존 자동 실행에는 아무 영향이 없습니다.
- 이후 저는 새 저장소에 코드를 브랜치로 올리고(병합은 운영자) 같은 방식의 병합 부탁을 보냅니다. 첫 코드 묶음은 정해 주신 우선순위 순서의 맨 앞인 **앱 뼈대·로컬 콘텐츠 상태와 오류 코드 카탈로그**(문서의 오류 코드 표와 코드가 시험으로 서로 같은지 확인)입니다. 새 시크릿은 필요 없습니다.

## 확인사항 (지금 답하지 않아도 됩니다)
- **라이선스**(결정 D-13): 공개 저장소에 라이선스 파일이 없으면 코드는 '모든 권리 보유' 상태라 다른 사람이 복사·수정해 쓸 수 없습니다. 지금은 **정하지 않았습니다**(기본). 정하실 때는 "MIT 로 해 주세요"처럼 한 줄만 주세요(MIT 는 누구나 자유롭게 쓰고 고칠 수 있는 가장 흔한 조건이고, 무료 코드 서명 서비스를 쓰려면 이런 공개 라이선스가 필요합니다). 라이선스 선택은 승인이 필요한 일이라 말씀해 주시면 번호 있는 요청으로 한 번 더 확인합니다.
- **스마트 앱 컨트롤**: 개인 PC 에서 Windows 보안 → 앱 및 브라우저 컨트롤 → 스마트 앱 컨트롤이 '켬/평가/끔' 중 무엇인지 알려 주세요(켜져 있으면 서명 없는 프로그램이 막힙니다). 설치 파일이 나오기 전까지만 알려 주시면 됩니다.

## 안 될 때
빨간 ✗ 이거나 'conflicts' 가 보이면 병합하지 말고, [답하기] → 요청 번호 **R-030** → 답변 '문제' 를 고르고 메모에 화면에 보이는 문구를 적어 주세요.
