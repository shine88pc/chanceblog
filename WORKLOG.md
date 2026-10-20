# Chance_Blog Work Log (AI 인수인계 로그)

> **이 파일은 AI가 작업을 시작하기 전에 반드시 최신 항목을 읽어야 하는 인수인계 로그입니다.**  
> 사용자가 별도로 지시하지 않아도, 이 저장소에서 작업하는 모든 AI는 `AI_COLLAB.md`와 함께 이 파일을 먼저 확인해야 합니다.

최신 항목이 위에 오도록 **최신순**으로 작성합니다.

---

## [2026-10-20] Grok – Blogger 생성 전용 워크플로 + 초안 저장 (API 미연동)

**작업자**: Grok  
**대상**: Blogger  
**목적**: API 연동 전에 스케줄 생성·초안 저장이 돌아가도록 구성

### 변경 사항
- `.github/workflows/blogger.yml` 신규
  - 매일 UTC 02:00 (KST 11:00) 스케줄
  - workflow_dispatch로 수동 실행·주제 지정·DRY_RUN 가능
  - `blogger_generator.py` 실행 후 `blogger_history.json` / `_blogger_drafts/` 커밋
- `blogger_generator.py` 개선
  - `_blogger_drafts/`에 제목·본문 포함 마크다운 초안 저장
  - 수동 게시용으로 바로 사용 가능

### 사용 방법
1. Actions → **Blogger Generate (Draft Only)** → Run workflow
2. 또는 스케줄 대기 (매일 KST 11시)
3. 생성된 초안: `_blogger_drafts/*.md` → Blogger에 복사 게시

### 다음 AI에게 남기는 주의사항
1. **Blogger API는 의도적으로 미루어 둔 상태** — 요청 있을 때만 진행
2. `GEMINI_API_KEY` 시크릿이 있어야 실제 생성 가능 (없으면 DRY_RUN/스텁)
3. 주제 충돌 방지·API 게시는 아직 미구현

### 남은 이슈 / 다음 단계
- 주제 충돌 방지 (Chance_Blog history와 교차 확인)
- Blogger API 연동 (보류 중)
- AdSense 승인 모니터링

---

## [2026-10-20] Grok – Blogger 게시 방식 확정

**작업자**: Grok  
**대상**: Blogger  
**목적**: 공식 경로 = GitHub Actions + Blogger API (현재는 생성만)

---

## [2026-10-20] Grok – blogger_generator.py 초안 추가

**작업자**: Grok  
**대상**: Blogger  
**목적**: 분기 글 생성 스크립트

---

## [2026-10-20] Grok – Blogger 분기 프롬프트 확정

**작업자**: Grok  
**대상**: Blogger  
**목적**: BLOGGER_PROMPT.md

---

## [2026-10-20] Grok – Blogger 자동화 구조 설계 완료

**작업자**: Grok  
**대상**: 공통

---

## [2026-10-20] Grok – 듀얼 블로그 전략 확정

**작업자**: Grok  
**목적**: 방향 C + 균형 성장

---

## [2026-10-20] Grok – AI 자동 읽기 강제 체계 강화

**작업자**: Grok

---

## [2026-10-20] Grok – AI 협업 체계 구축

**작업자**: Grok

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
