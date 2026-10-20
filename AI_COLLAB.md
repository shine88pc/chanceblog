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

## 3. Blogger 자동화 구조 (2026-10-20 설계)

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
   _posts/ 저장      Blogger 게시
   (기존 방식)       (API 또는 중간 저장)
```

### 3.2 단계별 역할

| 단계 | 역할 | 비고 |
|------|------|------|
| ① 공통 주제 발굴 | 기존 generator.py 로직 재사용 또는 공통 주제 풀 유지 | 건강·생활 연결 가능한 주제 우선 |
| ②-A Chance_Blog | 근거·맥락·분석 중심 KR/EN 생성 | 기존 유지 |
| ②-B Blogger | 같은 큰 주제 → 실용 버전으로 완전 재작성 | 신규 |

### 3.3 Blogger용 생성 규칙 (확정)

**상세 프롬프트**: [`.github/editorial/BLOGGER_PROMPT.md`](./.github/editorial/BLOGGER_PROMPT.md) 참고

- **대상 명시**: 반드시 `대상: Blogger`
- **톤**: 친근하고 실용적 (학술·분석 톤 금지)
- **길이**: 1,200~2,000자
- **필수 구조**:
  1. 일상 고민으로 시작하는 도입
  2. 실천 가능한 팁 3~5개
  3. 체크리스트 또는 “오늘부터 해볼 것”
  4. 가벼운 마무리
- **금지**: Chance_Blog 글 복사·약간 수정, 의학적 진단·치료 효과 단정, 과도한 클릭베이트

### 3.4 게시 방식 (단계적 적용)

| 단계 | 방식 | 설명 |
|------|------|------|
| 단기 | Google Sheets + Apps Script | 생성 결과를 Sheets에 기록 후 Apps Script로 게시 |
| 중기 | GitHub Actions + Blogger API | chanceblog 워크플로에서 직접 게시 (목표) |
| 대안 | Blogger Post-by-Email | 서식 제어가 약해 보조 수단으로만 사용 |

### 3.5 파일/모듈 구조 (목표)

```
chanceblog/
├── generator.py                 # 기존 (Chance_Blog 전용)
├── blogger_generator.py         # 신규: Blogger 분기 생성 + 게시
├── .github/editorial/
│   ├── CHANCE_BLOG_TEMPLATE.md  # Chance_Blog 편집 기준
│   └── BLOGGER_PROMPT.md        # Blogger 분기 프롬프트 (확정)
├── .github/workflows/
│   ├── chanceblog.yml           # 기존
│   └── blogger.yml              # 신규 또는 기존에 통합
├── AI_COLLAB.md
└── WORKLOG.md
```

### 3.6 스케줄 제안

- Chance_Blog: 기존 유지 (하루 2회 수준)
- Blogger: 하루 1회 (예: KST 11시 또는 20시)
- 같은 날 같은 세부 주제를 양쪽에 쓰지 않도록 기록으로 충돌 방지

### 3.7 구현 우선순위

1. ~~공통 주제 → Blogger용 분기 프롬프트 확정~~ ✅ 완료 (BLOGGER_PROMPT.md)
2. `blogger_generator.py` 초안 (Gemini로 실용 버전 생성)
3. 게시 방식 확정 (단기 Sheets → 중기 Blogger API)
4. GitHub Actions 연동
5. AI_COLLAB / WORKLOG 지속 업데이트

---

## 4. 주요 파일 구조 (Chance_Blog 저장소)

| 경로 | 설명 |
|------|------|
| `index.html` | 메인 랜딩 페이지 (가장 중요, 광고 코드 포함) |
| `_config.yml` | Jekyll 설정 |
| `_layouts/` | 레이아웃 (`post.html`, `info.html`) |
| `_includes/` | head, custom-head 등 |
| `_posts/` | 게시글 (한국어/영어 카테고리별) |
| `about.md`, `privacy.md`, `contact.md` | 정책/소개 페이지 |
| `generator.py` | Chance_Blog 글 생성/동기화 스크립트 |
| `blogger_generator.py` | (예정) Blogger용 분기 생성 스크립트 |
| `.github/editorial/BLOGGER_PROMPT.md` | Blogger 분기 프롬프트 (확정) |
| `AI_COLLAB.md` | 이 파일 (필수 지침) |
| `WORKLOG.md` | 작업 이력 및 인수인계 로그 |
| `README.md` | 저장소 최상단 안내 (AI 강제 읽기 포함) |

---

## 5. AI 작업 전 필수 체크리스트

1. [ ] `AI_COLLAB.md` (이 파일) 전체 읽기
2. [ ] `WORKLOG.md`의 최신 항목 3~5개 읽기
3. [ ] 현재 작업이 Chance_Blog용인지, Blogger용인지, 공통인지 확인
4. [ ] AdSense 관련 작업인지 확인 (승인 대기 중 주의)
5. [ ] 수정하려는 파일이 최근에 다른 AI에 의해 변경되었는지 확인
6. [ ] 작업 범위를 명확히 정의 (한 세션에서 너무 많은 파일을 건드리지 않기)

---

## 6. 작업 규칙 (충돌 방지)

### 6.1 파일 수정 원칙
- **한 번에 하나의 주요 목표**에만 집중한다.
- `index.html`은 매우 큰 파일이므로, 수정 시 **어떤 부분을 왜 바꾸는지** 명확히 기록한다.
- 광고 관련 코드(`adsbygoogle`, AdSense client ID 등)는 함부로 삭제하거나 위치를 바꾸지 않는다.

### 6.2 금지 사항
- 다른 AI가 최근 작업한 내용을 확인하지 않고 덮어쓰기
- AdSense 승인 대기 중에 불필요한 대규모 UI 개편
- 출처 없는 사실 추가, 허위 개인 경험 서술
- 두 블로그에 동일한 콘텐츠 게시

### 6.3 권장 사항
- 작은 단위로 커밋하고, 커밋 메시지에 AI 이름과 작업 목적·대상을 명시
- 작업 후 반드시 `WORKLOG.md`를 업데이트
- Blogger 관련 작업도 이 로그에 기록 (Blogger는 별도 저장소가 없으므로 여기서 추적)

---

## 7. AdSense 관련 현재 상태 (2026-10-20 기준)

- AdSense 광고 스크립트가 `index.html` head에 삽입되어 있음
  - client ID: `ca-pub-6035749437698387`
- 검토 요청 상태
- `privacy.md`에 광고 관련 안내가 작성되어 있음 (아직 광고 미게시 상태 명시)

**주의**: AdSense 승인 전까지는 광고 배치를 과도하게 바꾸거나, 정책 위반 소지가 있는 콘텐츠를 추가하지 말 것.

---

## 8. 편집 원칙 요약 (Chance_Blog)

자세한 내용은 `.github/editorial/CHANCE_BLOG_TEMPLATE.md`를 참고하세요.

- 확인 가능한 출처를 우선
- 사실과 해석을 구분
- 존재하지 않는 개인 경험·인터뷰를 지어내지 않음
- AI 사용 사실을 숨기지 않음 (about 페이지에 공개)

Blogger용 글은 위 원칙을 기본으로 하되, 더 실용적이고 읽기 쉬운 형식을 우선한다.  
Blogger 프롬프트는 `.github/editorial/BLOGGER_PROMPT.md`를 따른다.

---

## 9. 작업 후 필수 절차

1. `WORKLOG.md`에 새 항목 추가 (날짜, AI 이름, 작업 대상(Chance_Blog/Blogger/공통), 내용, 남은 이슈)
2. 커밋 메시지에 작업 요약을 명확히 작성
3. 다음 AI가 알아야 할 주의사항을 로그에 남김

---

## 10. 우선순위

1. **Chance_Blog AdSense 승인 유지 및 통과** (단기 최우선)
2. **두 블로그 콘텐츠의 균형 있는 생산** (중기)
3. **Blogger 자동화 파이프라인 구축** (프롬프트 확정 ✅ → 다음: blogger_generator.py)
4. 콘텐츠 품질·다양성·SEO 지속 개선

이 문서는 필요에 따라 업데이트합니다. 중요한 규칙 변경 시 `WORKLOG.md`에도 기록하세요.
