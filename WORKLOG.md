# Chance_Blog Work Log (AI 인수인계 로그)

> **이 파일은 AI가 작업을 시작하기 전에 반드시 최신 항목을 읽어야 하는 인수인계 로그입니다.**  
> 사용자가 별도로 지시하지 않아도, 이 저장소에서 작업하는 모든 AI는 `AI_COLLAB.md`와 함께 이 파일을 먼저 확인해야 합니다.

최신 항목이 위에 오도록 **최신순**으로 작성합니다.

---

## [2026-10-20] Grok – Blogger 게시 방식 확정

**작업자**: Grok  
**대상**: Blogger  
**목적**: 게시 경로를 공식 확정하고 문서에 반영

### 결정 사항
- **공식 경로**: GitHub Actions + Blogger API
- **현재 단계**: `blogger_generator.py`로 생성만 수행 → `blogger_history.json` 기록 (수동 게시 가능)
- **다음 단계**: Blogger API OAuth(refresh token) 준비 후 자동 게시 함수 구현

### 선택 이유
- Chance_Blog와 동일한 실행 환경 유지
- 한 저장소에서 듀얼 파이프라인 관리
- Sheets 경유는 시스템 분리·수동 개입 증가로 장기적으로 비효율

### 필요한 Secrets (2단계)
- `GEMINI_API_KEY` (기존)
- `BLOGGER_BLOG_ID`
- `BLOGGER_CLIENT_ID`
- `BLOGGER_CLIENT_SECRET`
- `BLOGGER_REFRESH_TOKEN`

### 변경 사항
- `AI_COLLAB.md` §3.4 게시 방식 확정 반영
- 구현 우선순위 3번 완료 표시

### 다음 AI에게 남기는 주의사항
1. 게시 API 연동 전까지는 생성 결과만 저장하는 모드로 운영
2. Blogger API 연동 시 refresh token을 GitHub Secrets에만 보관할 것
3. 다음 작업: `blogger_generator.py`에 `post_to_blogger()` 함수 추가 또는 인증 가이드 작성

### 남은 이슈 / 다음 단계
- Blogger API 인증 준비 (Google Cloud OAuth)
- `post_to_blogger()` 구현
- `.github/workflows/blogger.yml` 추가
- 주제 충돌 방지 로직
- AdSense 승인 모니터링

---

## [2026-10-20] Grok – blogger_generator.py 초안 추가

**작업자**: Grok  
**대상**: Blogger  
**목적**: Blogger용 분기 글 생성 스크립트 초안 작성

### 변경 사항
- `blogger_generator.py` 신규 추가 (생성 + 로그, 게시 미연동)

---

## [2026-10-20] Grok – Blogger 분기 프롬프트 확정

**작업자**: Grok  
**대상**: Blogger  
**목적**: BLOGGER_PROMPT.md 확정

---

## [2026-10-20] Grok – Blogger 자동화 구조 설계 완료

**작업자**: Grok  
**대상**: 공통  
**목적**: 파이프라인 구조 공식 설계

---

## [2026-10-20] Grok – 듀얼 블로그 전략 확정

**작업자**: Grok  
**목적**: 방향 C + 균형 성장

---

## [2026-10-20] Grok – AI 자동 읽기 강제 체계 강화

**작업자**: Grok  
**목적**: README / AI_COLLAB / WORKLOG 강제 읽기

---

## [2026-10-20] Grok – AI 협업 체계 구축

**작업자**: Grok  
**목적**: AI_COLLAB.md, WORKLOG.md 최초 생성

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
