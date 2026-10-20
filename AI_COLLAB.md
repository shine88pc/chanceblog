# AI Collaboration Guidelines (필수 읽기)

> **⛔ HARD REQUIREMENT FOR ALL AI AGENTS**
>
> You are currently working in the `shine88pc/chanceblog` repository.  
> **Before performing any action** (reading other files, editing, generating content, answering questions about the code, etc.), you **MUST**:
>
> 1. Read this entire `AI_COLLAB.md` file.
> 2. Read the latest entries in `WORKLOG.md`.
>
> This requirement applies **even if the human user did not mention these files**.  
> Skipping this step is considered a violation of the project rules and can cause conflicts with other AIs.

---

## 1. 프로젝트 개요 (듀얼 블로그 체제)

이 프로젝트는 **두 개의 블로그**를 균형 있게 성장시키는 것을 목표로 합니다.

| 블로그 | URL | 역할 | 핵심 톤 |
|--------|-----|------|---------|
| **Chance_Blog** | https://shine88pc.github.io/chanceblog/ | 교양형 매거진 | 근거·맥락·분야 연결 중심, 신중하고 분석적 |
| **Blogger** | https://macat0722.blogspot.com/ | 건강·음식·생활 중심의 실용 블로그 | 읽기 쉽고 실용적, 팁·리스트·일상 적용 가능 |

### 공통 원칙
- **동일한 글을 양쪽에 올리지 않는다.**
- 비슷한 주제를 다루더라도 **관점, 깊이, 형식, 사례를 다르게** 작성한다.
- 주제 풀은 공유하되, 각 블로그의 성격에 맞게 분기한다.
- 두 블로그 모두 **균형 있게** 성장시키는 것이 목표이다 (한쪽만 우선하지 않음).

### Chance_Blog 상세
- **저장소**: `shine88pc/chanceblog`
- **목적**: 기술·경제·사회·과학·문화·일상을 연결하는 한국어·영어 교양형 매거진
- **기술 스택**: Jekyll + 커스텀 `index.html` (Tailwind CDN)
- **현재 주요 목표**: Google AdSense 승인 및 수익화 + 콘텐츠 품질 유지

### Blogger (macat0722) 상세
- **플랫폼**: Google Blogger
- **기존 성격**: 건강, 음식, 생활, 다이어트, 간 건강, 단백질, 일본 음식 등
- **앞으로의 방향 (C 확정)**:  
  건강·음식·생활 중심을 **유지**하면서 주제를 넓힌다.  
  (예: 수면, 운동, 스트레스, 일상 습관, 간단한 과학 설명, 생활 속 기술 등도 포함 가능)
- **톤**: 쉽게 읽고 바로 적용할 수 있는 실용 정보 위주. 과도한 전문 용어나 긴 분석보다 명확한 설명과 팁 중심.
- **자동화 목표**: Chance_Blog 자동화의 연장선으로, 공통 주제에서 실용 버전을 분기 생성·게시

---

## 2. 콘텐츠 생성 규칙 (중요)

### 절대 금지
- 같은 제목·같은 본문을 양쪽 블로그에 게시
- Chance_Blog 글을 그대로 복사해서 Blogger에 올리기
- Blogger 글을 그대로 복사해서 Chance_Blog에 올리기

### 권장 방식
1. **공통 주제 아이디어**를 먼저 확보한다.
2. Chance_Blog용: 출처 확인 + 맥락 연결 + 분석·한계 제시 중심으로 작성
3. Blogger용: 같은 큰 주제라도  
   - 더 일상적이고 실용적인 각도  
   - 리스트, 팁, 실천 방법, 간단한 설명 위주  
   - 건강·음식·생활과 자연스럽게 연결  
   으로 **완전히 다른 글**을 작성한다.

### 작업 시 반드시 명시할 것
AI가 글을 생성하거나 수정할 때, 작업 대상이 무엇인지 명확히 밝힌다.
- `대상: Chance_Blog`
- `대상: Blogger`
- `대상: 둘 다 (주제만 공유, 내용은 분리)`

---

## 3. Blogger 자동화 구조 (2026-10-20 설계·확정)

Blogger 자동화는 **Chance_Blog 기존 엔진의 연장선**으로 설계한다. 독립적인 별도 시스템이 아니라, 공통 주제에서 분기하는 구조다.

### 3.1 전체 파이프라인

```
[Chance_Blog 기존 엔진 / 공통 주제 발굴]
                │
                ▼
        ① 공통 주제 선정
                │
        ┌───────┴───────┐
        ▼               ▼
  ②-A Chance_Blog용   ②-B Blogger용
  (교양·분석형)        (실용·실행형)
        │               │
        ▼               ▼
   _posts/ 저장      blogger_generator.py
   (기존 방식)       → 생성 + (목표) 게시
```

### 3.2 단계별 역할

| 단계 | 역할 | 비고 |
|------|------|------|
| ① 공통 주제 발굴 | 기존 generator.py 로직 재사용 또는 공통 주제 풀 유지 | 건강·생활 연결 가능한 주제 우선 |
| ②-A Chance_Blog | 근거·맥락·분석 중심 KR/EN 생성 | 기존 유지 |
| ②-B Blogger | 같은 큰 주제 → 실용 버전으로 완전 재작성 | blogger_generator.py |

### 3.3 Blogger용 생성 규칙 (확정)

**상세 프롬프트**: [`.github/editorial/BLOGGER_PROMPT.md`](./.github/editorial/BLOGGER_PROMPT.md) 참고

- **대상 명시**: 반드시 `대상: Blogger`
- **톤**: 친근하고 실용적 (학술·분석 톤 금지)
- **길이**: 1,200~2,000자
- **필수 구조**: 도입 → 팁 3~5개 → 체크리스트 → 마무리
- **금지**: Chance_Blog 글 복사·약간 수정, 의학적 진단·치료 효과 단정, 과도한 클릭베이트

### 3.4 게시 방식 (2026-10-20 확정)

**공식 결정: GitHub Actions + Blogger API**

| 단계 | 방식 | 상태 |
|------|------|------|
| **현재 (1단계)** | `blogger_generator.py`로 생성 → `blogger_history.json`에 기록. 수동 게시 또는 임시 복붙 | 운영 중 |
| **목표 (2단계)** | GitHub Actions에서 생성 후 **Blogger API로 자동 게시** | 다음 구현 대상 |
| 보조 | Blogger Post-by-Email | 서식 약함, 비상용만 |

**선택 이유**
- Chance_Blog와 동일한 실행 환경(GitHub Actions) 유지
- 한 저장소에서 듀얼 블로그 파이프라인 관리 가능
- Sheets 경유 시 시스템 분리·수동 개입 증가 → 장기적으로 비효율
- Blogger API는 OAuth refresh token을 GitHub Secrets에 저장하면 자동 게시 가능

**2단계 구현에 필요한 Secrets**
- `GEMINI_API_KEY` (이미 사용 중)
- `BLOGGER_BLOG_ID`
- `BLOGGER_CLIENT_ID`
- `BLOGGER_CLIENT_SECRET`
- `BLOGGER_REFRESH_TOKEN`

### 3.5 파일/모듈 구조

```
chanceblog/
├── generator.py                 # Chance_Blog 전용
├── blogger_generator.py         # Blogger 분기 생성 (초안 완료)
├── blogger_history.json         # 생성 로그 (런타임)
├── .github/editorial/
│   ├── CHANCE_BLOG_TEMPLATE.md
│   └── BLOGGER_PROMPT.md        # 확정
├── .github/workflows/
│   ├── chanceblog.yml           # 기존
│   └── blogger.yml              # (예정) Blogger 전용 또는 통합
├── AI_COLLAB.md
└── WORKLOG.md
```

### 3.6 스케줄 제안

- Chance_Blog: 기존 유지 (하루 2회 수준)
- Blogger: 하루 1회 (예: KST 11시 또는 20시)
- 같은 날 같은 세부 주제 충돌 방지: `blogger_history.json` + Chance_Blog history 교차 확인

### 3.7 구현 우선순위

1. ~~분기 프롬프트 확정~~ ✅
2. ~~blogger_generator.py 초안~~ ✅
3. ~~게시 방식 확정~~ ✅ (GitHub Actions + Blogger API)
4. Blogger API 인증 준비 + 게시 함수 구현
5. GitHub Actions 워크플로 (`blogger.yml`) 추가
6. 주제 충돌 방지 로직 보강

---

## 4. 주요 파일 구조 (Chance_Blog 저장소)

| 경로 | 설명 |
|------|------|
| `index.html` | 메인 랜딩 페이지 (가장 중요, 광고 코드 포함) |
| `_config.yml` | Jekyll 설정 |
| `_layouts/` | 레이아웃 |
| `_includes/` | head 등 |
| `_posts/` | 게시글 |
| `about.md`, `privacy.md`, `contact.md` | 정책/소개 |
| `generator.py` | Chance_Blog 글 생성 |
| `blogger_generator.py` | Blogger 분기 생성 (초안) |
| `.github/editorial/BLOGGER_PROMPT.md` | Blogger 프롬프트 |
| `AI_COLLAB.md` | 이 파일 |
| `WORKLOG.md` | 인수인계 로그 |
| `README.md` | AI 강제 읽기 안내 |

---

## 5. AI 작업 전 필수 체크리스트

1. [ ] `AI_COLLAB.md` 전체 읽기
2. [ ] `WORKLOG.md` 최신 항목 3~5개 읽기
3. [ ] 작업 대상(Chance_Blog / Blogger / 공통) 확인
4. [ ] AdSense 관련 여부 확인
5. [ ] 최근 다른 AI 변경 여부 확인
6. [ ] 작업 범위 명확화

---

## 6. 작업 규칙 (충돌 방지)

### 6.1 파일 수정 원칙
- 한 번에 하나의 주요 목표에만 집중
- `index.html` 수정 시 변경 범위 명확 기록
- 광고 코드 함부로 삭제/이동 금지

### 6.2 금지 사항
- 다른 AI 작업 확인 없이 덮어쓰기
- AdSense 승인 대기 중 불필요한 대규모 UI 개편
- 출처 없는 사실, 허위 개인 경험
- 두 블로그 동일 콘텐츠 게시

### 6.3 권장 사항
- 작은 단위 커밋, 메시지에 AI 이름·대상 명시
- 작업 후 `WORKLOG.md` 업데이트
- Blogger 작업도 이 로그에 기록

---

## 7. AdSense 관련 현재 상태 (2026-10-20 기준)

- AdSense 스크립트 삽입됨 (`ca-pub-6035749437698387`)
- 검토 요청 상태
- `privacy.md`에 광고 안내 있음

**주의**: 승인 전 광고 배치·정책 위반 소지 콘텐츠 추가 금지.

---

## 8. 편집 원칙 요약

- Chance_Blog: `.github/editorial/CHANCE_BLOG_TEMPLATE.md`
- Blogger: `.github/editorial/BLOGGER_PROMPT.md`
- 사실과 해석 구분, 허위 경험 금지, AI 사용 사실 공개

---

## 9. 작업 후 필수 절차

1. `WORKLOG.md`에 새 항목 추가
2. 커밋 메시지에 요약 작성
3. 다음 AI 주의사항 기록

---

## 10. 우선순위

1. **Chance_Blog AdSense 승인 유지 및 통과** (단기 최우선)
2. **두 블로그 콘텐츠 균형 생산** (중기)
3. **Blogger 자동화** (프롬프트·생성기·게시방식 확정 ✅ → 다음: API 연동)
4. 콘텐츠 품질·SEO 지속 개선

이 문서는 필요에 따라 업데이트합니다. 중요한 규칙 변경 시 `WORKLOG.md`에도 기록하세요.
