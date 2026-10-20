# Chance_Blog Work Log (AI 인수인계 로그)

> **이 파일은 AI가 작업을 시작하기 전에 반드시 최신 항목을 읽어야 하는 인수인계 로그입니다.**  
> 필독 순서: **HANDLER.md** → **AI_COLLAB.md** → **이 파일 최신 항목**

최신 항목이 위에 오도록 **최신순**으로 작성합니다.

---

## [2026-10-20] Grok – HANDLER.md 신설 (폴더 통합·멀티 AI 규칙)

**작업자**: Grok  
**대상**: 공통  
**목적**: 여러 AI·로컬 폴더 불일치 문제를 막기 위한 중앙 핸들러 문서 작성 및 필독 체계 강화

### 변경 사항
- **HANDLER.md** 신규
  - 완료 작업 현황
  - 조치 필요 사항 (P0 로컬 폴더 1개로 통합, VS Code 동기화, Secrets, 주제 충돌 등)
  - 작업 전 필수 확인 파일 목록
  - 작업 후 WORKLOG/HANDLER 기록 의무
  - 금지 사항
  - **GPT 복붙용 인수인계 문** 포함
- **README.md** — 필독 순서에 HANDLER.md를 1번으로 추가

### 사용자·다음 AI 조치 (P0)
1. GitHub `main`을 clone/pull 한 **공식 폴더 하나만** 사용
2. VS Code는 그 폴더만 Open Folder
3. 작업 전 `git pull`, 작업 후 커밋·push
4. `client_secret.json`은 공식 폴더 루트, 커밋 금지
5. GPT 세션 시작 시 HANDLER.md §8 블록 전달 권장

### 다음 AI에게 남기는 주의사항
1. 작업 시작 전 HANDLER → AI_COLLAB → WORKLOG 필수
2. 로컬 경로를 추측하지 말고 사용자가 연 폴더가 git remote 공식 저장소인지 확인
3. Blogger API Secrets는 사용자 등록 전제

### 남은 이슈
- 로컬 폴더 통합 (사용자)
- Blogger Secrets / token 발급 (사용자)
- 주제 충돌 방지, 초안 품질, AdSense

---

## [2026-10-20] Grok – Blogger API 코드 연동 완료 (Secrets 대기)

**작업자**: Grok  
**대상**: Blogger  
**목적**: API 게시 코드·가이드·워크플로 구현. 실게시는 Secrets 후.

---

## [2026-10-20] Grok – Blogger 생성 워크플로·초안·전략·프롬프트

이전 항목: blogger.yml, blogger_generator, BLOGGER_PROMPT, 듀얼 전략, AI 협업 체계.

---

## 로그 작성 가이드 (모든 AI 공통)

```markdown
## [YYYY-MM-DD] AI이름 – 작업 제목

**작업자**: GPT / Grok / Claude 등  
**대상**: Chance_Blog / Blogger / 공통  
**목적**: 한 줄 요약

### 변경 사항
- ...

### 다음 AI에게 남기는 주의사항
1. ...

### 남은 이슈 / 확인할 점
- ...
```
