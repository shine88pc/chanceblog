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

## 1. 프로젝트 개요

- **사이트**: https://shine88pc.github.io/chanceblog/
- **저장소**: `shine88pc/chanceblog`
- **목적**: 기술·경제·사회·과학·문화·일상을 연결하는 한국어·영어 교양형 매거진
- **기술 스택**: Jekyll (minima 테마) + 커스텀 `index.html` (Tailwind CDN 기반 SPA-like 구조)
- **현재 주요 목표**: Google AdSense 승인 및 수익화

### 주요 파일 구조

| 경로 | 설명 |
|------|------|
| `index.html` | 메인 랜딩 페이지 (가장 중요, 광고 코드 포함) |
| `_config.yml` | Jekyll 설정 |
| `_layouts/` | 레이아웃 (`post.html`, `info.html`) |
| `_includes/` | head, custom-head 등 |
| `_posts/` | 게시글 (한국어/영어 카테고리별) |
| `about.md`, `privacy.md`, `contact.md` | 정책/소개 페이지 |
| `generator.py` | 글 생성/동기화 관련 스크립트 |
| `AI_COLLAB.md` | 이 파일 (필수 지침) |
| `WORKLOG.md` | 작업 이력 및 인수인계 로그 |
| `README.md` | 저장소 최상단 안내 (AI 강제 읽기 포함) |

---

## 2. AI 작업 전 필수 체크리스트

작업을 시작하기 전에 아래를 **반드시** 확인하세요.

1. [ ] `AI_COLLAB.md` (이 파일) 전체 읽기
2. [ ] `WORKLOG.md`의 최신 항목 3~5개 읽기
3. [ ] 현재 진행 중인 작업이 있는지 확인 (특히 AdSense 관련)
4. [ ] 수정하려는 파일이 최근에 다른 AI에 의해 변경되었는지 확인
5. [ ] 작업 범위를 명확히 정의 (한 세션에서 너무 많은 파일을 건드리지 않기)

---

## 3. 작업 규칙 (충돌 방지)

### 3.1 파일 수정 원칙
- **한 번에 하나의 주요 목표**에만 집중한다.
- `index.html`은 매우 큰 파일이므로, 수정 시 **어떤 부분을 왜 바꾸는지** 명확히 기록한다.
- 광고 관련 코드(`adsbygoogle`, AdSense client ID 등)는 함부로 삭제하거나 위치를 바꾸지 않는다.
- CSS/스타일 변경 시 기존 Tailwind 클래스와 커스텀 스타일의 의도를 존중한다.

### 3.2 금지 사항
- 다른 AI가 최근 작업한 내용을 확인하지 않고 덮어쓰기
- AdSense 승인 대기 중에 불필요한 대규모 UI 개편
- 출처 없는 사실 추가, 허위 개인 경험 서술 (편집 원칙 위반)
- `privacy.md`, `about.md`의 AdSense 관련 문구를 승인 전에 성급히 변경

### 3.3 권장 사항
- 작은 단위로 커밋하고, 커밋 메시지에 AI 이름과 작업 목적을 명시
- 작업 후 반드시 `WORKLOG.md`를 업데이트
- 의도가 불분명한 기존 코드는 삭제하지 말고 주석으로 남기거나 로그에 질문 남기기

---

## 4. AdSense 관련 현재 상태 (2026-10-20 기준)

- AdSense 광고 스크립트가 `index.html` head에 삽입되어 있음
  - client ID: `ca-pub-6035749437698387`
- 검토 요청 상태
- `privacy.md`에 광고 관련 안내가 작성되어 있음 (아직 광고 미게시 상태 명시)
- HTML/CSS를 AdSense 정책에 맞게 일부 수정한 상태

**주의**: AdSense 승인 전까지는 광고 배치를 과도하게 바꾸거나, 정책 위반 소지가 있는 콘텐츠를 추가하지 말 것.

---

## 5. 편집 원칙 요약

자세한 내용은 `.github/editorial/CHANCE_BLOG_TEMPLATE.md`를 참고하세요.

핵심만 요약:
- 확인 가능한 출처를 우선
- 사실과 해석을 구분
- 존재하지 않는 개인 경험·인터뷰를 지어내지 않음
- AI 사용 사실을 숨기지 않음 (about 페이지에 공개)

---

## 6. 작업 후 필수 절차

작업을 마치면 **반드시** 아래를 수행하세요.

1. `WORKLOG.md`에 새 항목 추가 (날짜, AI 이름, 작업 내용, 변경 파일, 남은 이슈)
2. 커밋 메시지에 작업 요약을 명확히 작성
3. 다음 AI가 알아야 할 주의사항을 로그에 남김

---

## 7. 연락 및 우선순위

- 운영자: shine88pc
- 현재 최우선 목표: **AdSense 승인 유지 및 통과**
- 그 다음: 콘텐츠 품질 유지, SEO, 사용자 경험 개선

이 문서는 필요에 따라 업데이트합니다. 중요한 규칙 변경 시 `WORKLOG.md`에도 기록하세요.
