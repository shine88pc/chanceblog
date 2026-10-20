# Chance_Blog Work Log (AI 인수인계 로그)

> **이 파일은 AI가 작업을 시작하기 전에 반드시 최신 항목을 읽어야 하는 인수인계 로그입니다.**  
> 사용자가 별도로 지시하지 않아도, 이 저장소에서 작업하는 모든 AI는 `AI_COLLAB.md`와 함께 이 파일을 먼저 확인해야 합니다.

최신 항목이 위에 오도록 **최신순**으로 작성합니다.

---

## [2026-10-20] Grok – blogger_generator.py 초안 추가

**작업자**: Grok  
**대상**: Blogger  
**목적**: Blogger용 분기 글 생성 스크립트 초안 작성

### 변경 사항
- `blogger_generator.py` 신규 추가
  - BLOGGER_PROMPT.md 프롬프트 로드
  - Gemini 호출 (모델 폴백)
  - 주제 선택 (환경변수 또는 내장 목록)
  - 제목/라벨/HTML 파싱
  - `blogger_history.json` 로그 기록
  - DRY_RUN 지원
  - 게시 API는 아직 미연동 (주석으로 자리만 확보)

### 사용법
```bash
export GEMINI_API_KEY=...
python blogger_generator.py

# 특정 주제
BLOGGER_TOPIC="스트레스 받을 때 1분 만에 할 수 있는 호흡법" python blogger_generator.py

# 스텁 테스트
DRY_RUN=1 python blogger_generator.py
```

### 다음 AI에게 남기는 주의사항
1. 현재는 **생성만** 하고 게시는 하지 않음
2. 다음 단계: 게시 방식 확정 (Sheets vs Blogger API) 후 연동
3. GitHub Actions 워크플로 추가는 게시 연동 후 진행 권장

### 남은 이슈 / 다음 단계
- 게시 방식 확정 및 연동
- GitHub Actions 스케줄 추가
- Chance_Blog 주제와 충돌 방지 로직 강화
- AdSense 승인 모니터링

---

## [2026-10-20] Grok – Blogger 분기 프롬프트 확정

**작업자**: Grok  
**대상**: Blogger  
**목적**: Chance_Blog와 명확히 분리된 Blogger용 콘텐츠 생성 프롬프트를 확정하고 공식 문서로 등록

### 변경 사항
- `.github/editorial/BLOGGER_PROMPT.md` 신규 생성 (확정본)
- `AI_COLLAB.md` 업데이트 (프롬프트 링크 + 우선순위 1번 완료)

### 다음 AI에게 남기는 주의사항
1. Blogger 글 생성 시 `.github/editorial/BLOGGER_PROMPT.md` 준수
2. `대상: Blogger` 명시 필수

### 남은 이슈 / 다음 단계
- `blogger_generator.py` 초안 작성
- 게시 방식 확정
- GitHub Actions 연동

---

## [2026-10-20] Grok – Blogger 자동화 구조 설계 완료

**작업자**: Grok  
**대상**: 공통  
**목적**: Blogger 자동화 파이프라인 구조 공식 설계

### 변경 사항
- `AI_COLLAB.md`에 §3. Blogger 자동화 구조 추가

---

## [2026-10-20] Grok – 듀얼 블로그 전략 확정 (Chance_Blog + Blogger)

**작업자**: Grok  
**목적**: 방향 C + 균형 성장 전략 공식화

---

## [2026-10-20] Grok – AI 자동 읽기 강제 체계 강화

**작업자**: Grok  
**목적**: README / AI_COLLAB / WORKLOG 자동 읽기 강제

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
