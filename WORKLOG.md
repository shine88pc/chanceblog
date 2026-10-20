# Chance_Blog Work Log (AI 인수인계 로그)

> **이 파일은 AI가 작업을 시작하기 전에 반드시 최신 항목을 읽어야 하는 인수인계 로그입니다.**  
> 사용자가 별도로 지시하지 않아도, 이 저장소에서 작업하는 모든 AI는 `AI_COLLAB.md`와 함께 이 파일을 먼저 확인해야 합니다.

최신 항목이 위에 오도록 **최신순**으로 작성합니다.

---

## [2026-10-20] Grok – Blogger 분기 프롬프트 확정

**작업자**: Grok  
**대상**: Blogger  
**목적**: Chance_Blog와 명확히 분리된 Blogger용 콘텐츠 생성 프롬프트를 확정하고 공식 문서로 등록

### 변경 사항
- `.github/editorial/BLOGGER_PROMPT.md` 신규 생성 (확정본)
  - 기본 프롬프트 (복붙용)
  - 주제 유형별 세부 가이드
  - Chance_Blog와의 차별점 표
  - 제목 규칙 및 주의사항
- `AI_COLLAB.md` 업데이트
  - 프롬프트 파일 링크 추가
  - 구현 우선순위 1번 완료 표시

### 프롬프트 핵심
- 톤: 친근·실용 (학술·분석 금지)
- 구조: 도입 → 팁 3~5개 → 체크리스트 → 마무리
- 길이: 1,200~2,000자
- 출력: 제목 / 라벨 / HTML 내용

### 다음 AI에게 남기는 주의사항
1. Blogger 글 생성 시 반드시 `.github/editorial/BLOGGER_PROMPT.md`를 따를 것
2. `대상: Blogger` 명시 필수
3. 다음 단계는 `blogger_generator.py` 초안 작성

### 남은 이슈 / 다음 단계
- `blogger_generator.py` 초안 작성
- 게시 방식 확정 (Sheets vs Blogger API)
- GitHub Actions 연동
- Chance_Blog AdSense 승인 모니터링

---

## [2026-10-20] Grok – Blogger 자동화 구조 설계 완료

**작업자**: Grok  
**대상**: 공통 (Blogger 자동화 설계)  
**목적**: Chance_Blog 기존 자동화의 연장선으로 Blogger 자동화 파이프라인 구조를 공식 설계하고 AI_COLLAB.md에 반영

### 변경 사항
- `AI_COLLAB.md`에 **§3. Blogger 자동화 구조** 신규 섹션 추가
  - 전체 파이프라인 (공통 주제 → Chance_Blog / Blogger 분기)
  - Blogger용 생성 규칙 (톤, 구조, 금지 사항)
  - 게시 방식 단계적 적용 (단기 Sheets → 중기 Blogger API)
  - 목표 파일/모듈 구조 (`blogger_generator.py` 등)
  - 스케줄 제안 및 구현 우선순위
- 우선순위 항목을 “설계 완료 → 구현 단계”로 업데이트

### 설계 요약
1. Blogger는 독립 시스템이 아니라 **Chance_Blog 엔진의 연장선**
2. 공통 주제 선정 후 관점·형식·깊이를 다르게 분기
3. 단기: Sheets + Apps Script / 중기: GitHub Actions + Blogger API
4. 하루 1회 수준 스케줄 권장, 주제 충돌 방지 기록 필요

### 다음 AI에게 남기는 주의사항
1. Blogger 관련 작업 시 반드시 `대상: Blogger` 명시
2. Chance_Blog 글을 복사·수정해서 Blogger에 올리는 행위 금지
3. 다음 구현 단계는 `blogger_generator.py` 초안 또는 분기 프롬프트 확정
4. AdSense 승인 대기 중이므로 Chance_Blog 쪽 광고/정책 변경은 신중히

### 남은 이슈 / 다음 단계
- Blogger용 분기 프롬프트 확정
- `blogger_generator.py` 초안 작성
- 게시 방식 최종 선택 (Sheets vs Blogger API)
- GitHub Actions 연동 설계
- Chance_Blog AdSense 승인 모니터링

---

## [2026-10-20] Grok – 듀얼 블로그 전략 확정 (Chance_Blog + Blogger)

**작업자**: Grok  
**목적**: Blogger(macat0722.blogspot.com)를 건강·음식·생활 중심을 유지하면서 주제를 확장하고, Chance_Blog와 균형 있게 성장시키는 전략을 공식화

### 결정 사항
- **방향 C 확정**: Blogger는 건강·음식·생활 중심을 유지하면서 주제를 넓힌다.
- **균형 성장**: 두 블로그를 한쪽만 우선하지 않고 함께 키운다.
- **콘텐츠 분리 원칙**: 동일한 글을 올리지 않는다. 비슷한 주제라도 관점·형식·깊이를 다르게 작성한다.

### 변경 사항
- `AI_COLLAB.md`에 듀얼 블로그 체제, 역할 분담, 콘텐츠 생성 규칙, 작업 시 대상 명시 의무를 추가
- 이 로그에 전략 확정 기록

### 다음 AI에게 남기는 주의사항
1. 글 생성/수정 시 반드시 `대상: Chance_Blog` / `대상: Blogger` / `대상: 공통(주제만)` 중 하나를 명시할 것
2. 같은 내용을 양쪽 블로그에 올리는 행위는 금지
3. Blogger 관련 작업도 이 WORKLOG에 기록할 것 (Blogger는 별도 Git 저장소가 없음)
4. AdSense 승인 대기 중이므로 Chance_Blog 쪽 광고·정책 관련 변경은 신중히

### 남은 이슈 / 다음 단계
- Blogger API 연동 준비 (인증, 게시 스크립트 설계)
- Blogger용 콘텐츠 생성 프롬프트/가이드라인 구체화
- 공통 주제 발굴 → 양쪽 분기 생성 파이프라인 설계
- Chance_Blog AdSense 승인 결과 모니터링

---

## [2026-10-20] Grok – AI 자동 읽기 강제 체계 강화

**작업자**: Grok  
**목적**: 사용자가 "AI_COLLAB.md와 WORKLOG.md를 읽고 시작해"라고 말하지 않아도, 모든 AI가 자동으로 이 파일들을 먼저 읽도록 강제

### 변경 사항
- `README.md` 신규 생성 — 저장소 최상단에 AI 강제 읽기 경고 배치
- `AI_COLLAB.md` 상단 문구를 더 강하게 수정 (사용자가 언급하지 않아도 필독)
- `WORKLOG.md` 상단에도 동일 취지의 안내 추가

### 다음 AI에게 남기는 주의사항
1. 이 저장소에 들어오면 사용자가 따로 말하지 않아도 `README.md` → `AI_COLLAB.md` → `WORKLOG.md` 순으로 읽는 것이 기본 규칙임
2. AdSense 승인 대기 중이므로 광고 코드와 privacy 관련 문구는 신중하게 다룰 것
3. 작업이 끝나면 이 로그에 새 항목을 추가하는 것을 잊지 말 것

### 남은 이슈 / 확인할 점
- AdSense 승인 결과 대기 중
- 콘텐츠 양과 품질 지속 점검 필요

---

## [2026-10-20] Grok – AI 협업 체계 구축

**작업자**: Grok  
**목적**: 여러 AI가 동시에 작업해도 코드가 꼬이지 않도록 필수 지침과 인수인계 로그 생성

### 변경 사항
- `AI_COLLAB.md` 신규 생성 (모든 AI가 작업 전 필독)
- `WORKLOG.md` 신규 생성 (지속적인 인수인계용)

### 현재 프로젝트 상태 요약
- AdSense 검토 요청 완료 상태
- `index.html` head에 AdSense 스크립트 삽입됨 (`ca-pub-6035749437698387`)
- `privacy.md`, `about.md` 정책 페이지 존재
- 메인 랜딩은 커스텀 `index.html` (Tailwind + JS 기반)
- 글은 `_posts/` 아래에 한국어/영어 카테고리로 분리되어 있음

### 다음 AI에게 남기는 주의사항
1. 작업 시작 전 `AI_COLLAB.md`와 이 로그의 최신 항목을 반드시 읽을 것
2. AdSense 승인 대기 중이므로 광고 코드나 privacy 문구를 함부로 변경하지 말 것
3. `index.html`은 용량이 크므로 부분 수정 시 변경 범위를 명확히 기록할 것
4. 작업 후에는 이 로그에 새 항목을 추가할 것

### 남은 이슈 / 확인할 점
- AdSense 승인 결과 대기 중
- 콘텐츠 양과 품질이 승인 기준을 충족하는지 지속 점검 필요
- 모바일/반응형 및 광고 배치 최적화는 승인 후 진행 권장

---

## 로그 작성 가이드 (모든 AI 공통)

새 항목을 추가할 때 아래 형식을 지켜주세요.

```markdown
## [YYYY-MM-DD] AI이름 – 작업 제목

**작업자**: GPT / Grok / Claude 등  
**대상**: Chance_Blog / Blogger / 공통  
**목적**: 한 줄 요약

### 변경 사항
- 파일명과 변경 내용

### 다음 AI에게 남기는 주의사항
1. ...

### 남은 이슈 / 확인할 점
- ...
```
