---
name: desktop-repo-chanceblog-desktop
description: "데스크톱 프로그램 전용 새 공개 저장소 shine88pc/chanceblog-desktop(운영자가 2026-10-30 직접 생성) — 역할, 규칙, 첫 뼈대 브랜치·병합 상태(R-030), 방향 정리(AI Router 제외·선택 보조 AI), 핵심 코드 vendoring, 운영자 호출 채널"
metadata:
  node_type: memory
  type: project
  originSessionId: (세션 번호)
  modified: 2026-10-30T13:07:40.733Z
---

**저장소**: https://github.com/shine88pc/chanceblog-desktop (공개, 기본 브랜치 `main`, 운영자가 2026-10-30 10:13 KST 에 직접 생성 — 결정 D-03 '새 저장소'). 처음 기본안이던 chanceblog 안 `desktop/` 폴더는 쓰지 않는다(그래서 `_config.yml` 광고 표면 수정 불필요).

**역할 분담**: chanceblog = 클라우드 자동 발행 파이프라인 + **규칙의 정본**(AGENTS.md·CHARTER·SECURITY_GUARDRAILS·AGENT_RUNBOOK) + **운영자 호출(텔레그램) 채널**. chanceblog-desktop = 개인 Windows PC 작업대(원고→검사→플랫폼별 변환→승인→내보내기) + GitHub Releases 설치·자동 업데이트. 새 저장소에는 텔레그램 시크릿·알림 워크플로를 두지 않는다 — 운영자에게 알릴 일은 chanceblog 의 요청 파일(`ai/claude/**` push)로. GitHub Pages 글은 앱이 **기존 chanceblog 로컬 clone 을 연결**해 만들고 기존 `pages.yml` 자동 배포를 그대로 쓴다(ARCHITECTURE §3).

**상태(2026-10-30 13:15)**: **PR #1~#5 병합 완료**(운영자가 요청 뒤 2~10분 안에 병합 — 병합 커밋 방식도 쓴다; 나는 매번 PR 상태·트리 동일·main 푸시 CI 를 직접 확인): #1 뼈대(R-030) · #2 오류 코드 카탈로그·문구 만들기(R-033) · #3 `vendor/pipeline/` 가져오기(R-034) · #4 `publish/gitrepo.py`(R-035) · #5 콘텐츠 모델 `content/status.py`·`content/model.py`(R-039, 12:32, 병합 커밋 0008c5b, 시험 128개, 오류 코드 41개). **R-041 발송(13:14)** — 브랜치 `ai/claude/desktop-pages-render`(e02d6e8: `render/pages.py` Chance 형식 글 만들기 + 실제 글 2편 fixture 로 글자 단위 고정, 시험 158개, 변이 34개 모두 잡힘, CI 초록)를 운영자가 병합할 차례. **다음 묶음 `ai/claude/desktop-review-fixes`**(583bac5, 단일 커밋, CI 초록): 별도 검토자(에이전트 a3e1238848dccf19a)가 main 을 독립 검토해 찾은 높음 0·중간 6·낮음 15 반영 — git 실행(시간 초과 때 프로세스 트리 종료·환경 고정·gc 끔)·오류 분류·origin(받기·올리기 주소 모두)·최신 받기가 내 파일 안 덮어씀·`--no-verify`·`security/mask.py`(로그 가리기)·vendor 전체 검사·sync_core 출처/병합/파일 종류 확인·core.py 경로·sync_errors 파서 엄격화·`clean_slot`·CI 액션 SHA 고정·`.gitignore`·문서 정리; 변이 점검 `scratchpad/mut_cd7.py`(병렬, 약 100개) 진행 중, 재검토 요청함. R-041 병합 확인 뒤 새 main 위로 rebase(CHANGELOG·ARCHITECTURE 충돌 가능) → CI → 요청 R-042. 그다음 후보: Pages 발행(연결한 chanceblog 에 쓰고 commit·push — T2, 독립 검증 필수)·SQLite 저장·Blogger·네이버 패키지·설치 파일. 요청 파일은 chanceblog 의 요청 전용 브랜치 `ai/claude/desktop-bootstrap-merge`(병합·삭제 금지)에 R-nnn 으로 더한다(worktree `scratchpad/wt_r30`). 운영 방식: 묶음마다 변이 점검·CI(py3.10·3.12 × Windows·Ubuntu) 초록 뒤 push → 요청 → 병합 확인; 같은 파일(CHANGELOG 등)을 건드리는 묶음은 앞 묶음 병합 뒤 새 main 위로 옮겨 충돌 없이 보낸다(운영자는 충돌을 못 푼다). 로컬 작업 clone 은 스크래치패드 `cd_repo`(임시, 변이 점검이 도는 동안은 브랜치를 바꾸지 말 것 — 다른 브랜치는 worktree `cd_wt_render` 등으로), 세션이 바뀌면 다시 clone. 작성자는 clone 로컬 설정 `강병수 <shine88pc@gmail.com>`.

**상태 갱신(2026-10-30 22:35 재부팅 직전 최종 — 위 13:15 상태보다 이쪽이 최신)**: R-041(render, e02d6e8)은 아직 미병합. 이후 묶음은 모두 만들어 CI 초록으로 올려 두었다 — 마크다운 948ea25·네이버 7833120·원고 저장소(store)·검토 반영(79df9c8, 독립 검토 4차·시험 309·변이 217)·**통합 브랜치 `ai/claude/desktop-batch-1`=c455375**(render 위 여섯 묶음 전부, 시험 680 — 옛 네 묶음 끝은 51b0cb6)·**발행 `ai/claude/desktop-pages-publish`=0340768**(T2 독립 검증 3차 완료·4차 확인 요청 중, 시험 650, 변이 122 모두 잡음)·**배포 확인 `ai/claude/desktop-pages-deploy`=c455375**(시험 680, 변이 56). 병합 부탁은 R-041 병합 뒤 **R-043 하나**로 묶어 보낸다(batch-1 을 c455375 로 옮기면 여섯 묶음). 병합 요청 순서·해시·재현 방법은 [[resume-2305-handoff]] 맨 위 '▶ 현재 상태와 남은 일' 블록이 정본(R-041 이 병합 커밋이면 batch-1 은 그대로, Squash 면 `git rebase --onto origin/main e02d6e8 c455375` — 모의 시험 확인).

**방향 정리(운영자 2026-10-30, 결정 D-12~D-19)**: AI Router·여러 공급자 자동 전환 제외(D-15), **GitHub Models 는 후보·설계에서 완전 제외**(시험으로 고정), 무료 AI 는 선택 보조 4가지(감시 결과 한 줄 요약·긴 오류 로그 설명·조치 추천·주간 요약)만 — 기본 꺼짐·최소 인터페이스(`NullAssistant`), 코드 수정·유지보수는 무료 AI 가 아니라 운영자가 필요할 때 돌리는 Claude Code 등(D-14), 기존 Gemini 기능은 삭제하지 않고 격리(D-16), 오류 안내는 규칙 기반(오류 코드 + 문구, D-17), AI 없이 되는 17개 기능(D-18), 보안 점검 결과(D-19), 개발 우선순위 12개(D-12), 라이선스 미정(D-13, 기본 제안 MIT).

**설계 요약**: 파이썬 코어 재사용 — chanceblog `pipeline/` 필요 모듈을 새 저장소 `vendor/pipeline/` 에 **원본 그대로** 복사 + `vendor/VENDOR.json`(출처·커밋·해시) + `scripts/sync_core.py` + 해시 시험(D-11, ARCHITECTURE §4). 틀은 PySide6 또는 pywebview + PyInstaller onedir + Velopack, 릴리스는 Actions 초안 → 운영자 Publish, 무서명 + Ed25519 매니페스트, 서명 키는 T3. **다음 코드 묶음(R-030 병합 뒤)**: 앱 뼈대·로컬 콘텐츠 상태 + 오류 코드 카탈로그(문서 TROUBLESHOOTING 과 시험으로 일치) + vendor/sync_core — 'AI 공급자 인터페이스'는 더 이상 다음 단계가 아니다. 개인 PC 의 Smart App Control 상태 확인 요청 중.

**Why:** 운영자는 비개발자이고 회사 PC → 개인 PC 이관 중이며, 어떤 AI 도구로도 이어받게 하려 한다. 관련: [[handoff-md-is-rough-baseline-is-this-session]] [[pending-after-r025-merge]]

**How to apply:** 새 저장소에서도 브랜치 `ai/<도구>/<주제>` → PR → 운영자 병합, main 직접 push 금지, 승인 항목(T3)은 chanceblog 요청 채널의 번호 있는 요청으로. 병합 부탁 순서는 R-029(네이버) ↔ R-030(뼈대, 서로 독립 — 이미 발송) → D-86 → 문서 묶음 → 코드 묶음 순으로 하되 같은 저장소 것은 한 번에 하나씩. 새 저장소 문서의 정본 번호(D-nn, ARCHITECTURE 절 번호)를 chanceblog 문서에서 인용할 때는 새 저장소에서 확인한 뒤 쓴다.
