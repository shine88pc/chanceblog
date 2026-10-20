# Chance_Blog + Blogger 멀티 AI 핸들러

> **⛔ 모든 AI (Grok / GPT / Claude 등) 작업 시작 전 필수**
>
> 1. 이 파일 `HANDLER.md` 전체 읽기
> 2. `AI_COLLAB.md` 전체 읽기
> 3. `WORKLOG.md` **최신 항목 3~5개** 읽기
> 4. 아래 **작업 전 체크리스트** 확인 후 작업 시작
>
> 사용자가 따로 말하지 않아도 위 순서를 지킨다.

---

## 1. 프로젝트 한눈에

| 항목 | 내용 |
|------|------|
| 저장소 | `shine88pc/chanceblog` (유일한 공식 소스) |
| Chance_Blog | https://shine88pc.github.io/chanceblog/ — 교양·분석형 |
| Blogger | https://macat0722.blogspot.com/ — 건강·생활 실용형 |
| 전략 | C 방향 + **균형 성장** (한쪽만 우선 금지) |
| 콘텐츠 원칙 | **동일 글 양쪽에 올리지 않음**. 같은 주제라도 관점·형식·깊이 다르게 |

### 작업 시 대상 명시 (필수)

- `대상: Chance_Blog`
- `대상: Blogger`
- `대상: 공통`

---

## 2. 지금까지 완료된 작업 (2026-10-20 기준)

| # | 내용 | 상태 |
|---|------|------|
| 1 | 듀얼 블로그 전략 확정 (AI_COLLAB / WORKLOG) | ✅ |
| 2 | Blogger 자동화 구조 설계 | ✅ |
| 3 | Blogger 분기 프롬프트 `BLOGGER_PROMPT.md` | ✅ |
| 4 | `blogger_generator.py` (생성·초안·API 게시 함수) | ✅ 코드 |
| 5 | `.github/workflows/blogger.yml` 스케줄 생성 | ✅ |
| 6 | Blogger API 가이드 `BLOGGER_API_SETUP.md` | ✅ |
| 7 | `scripts/get_blogger_token.py` | ✅ |
| 8 | 초안 폴더 `_blogger_drafts/` 저장 | ✅ |

### Blogger API 실게시

- **코드는 완료**, **Secrets 등록은 사용자 진행 중**
- 로컬에 `client_secret.json`까지 받은 상태 (커밋 금지)
- refresh token 발급은 PC에서 `get_blogger_token.py` 실행 필요
- 결제/Cloud 체험이 부담이면 → 초안 수동 게시 또는 이메일 게시 유지 가능

---

## 3. 지금 조치해야 할 사항 (우선순위)

### P0 — 로컬 폴더 통합 (긴급)

**문제**
- AI·도구마다 다른 로컬 폴더를 열어 작업함
- 예: `클라우드\chanceblog`(오래된 복사본), VS Code의 다른 프로젝트(`hi.py` 등), GitHub main 최신본이 서로 불일치
- `scripts/get_blogger_token.py`를 못 찾는 오류 발생

**조치 (사용자 + AI 공통)**

1. **공식 폴더는 하나만 사용**
   - 권장: Git으로 clone한 `shine88pc/chanceblog` 최신 `main` 한 곳
   - 경로 예: `D:\Dev\chanceblog` 또는 `D:\OneDrive\...\chanceblog` **하나**
2. 예전 복사본·임시 폴더는 이름 변경 후 보관 또는 삭제
   - 예: `chanceblog-old-20261018`
3. **VS Code는 그 폴더만 Open Folder**
   - File → Open Folder → 공식 `chanceblog`만 선택
   - 다른 프로젝트와 창을 섞지 않기
4. **Git 동기화 자동화**
   - 작업 전: `git pull origin main`
   - 작업 후: 커밋 메시지에 AI 이름·대상 명시 후 `git push`
   - VS Code: 왼쪽 Source Control에서 pull/push, 또는 설정에서 autofetch 사용
5. `client_secret.json`은 공식 폴더 **루트에만** 두고 **gitignore / 커밋 금지**

### P1 — Blogger 게시 경로 확정

| 선택 | 조건 |
|------|------|
| A. API 자동 게시 | Secrets 4종 등록 + token 발급 완료 후 |
| B. 초안만 자동 + 수동 게시 | Cloud/카드 없이 현재 유지 |
| C. 이메일 게시 | Blogger 설정「이메일로 게시」 |

Secrets (API 선택 시):

- `BLOGGER_BLOG_ID`
- `BLOGGER_CLIENT_ID`
- `BLOGGER_CLIENT_SECRET`
- `BLOGGER_REFRESH_TOKEN`
- (기존) `GEMINI_API_KEY`

### P2 — 이후 구현

- 주제 충돌 방지 (Chance_Blog history ↔ Blogger history)
- 초안 품질 점검 / 샘플 테스트
- AdSense 승인 모니터링 (Chance_Blog 최우선 유지)

---

## 4. 작업 시작 전 필수 확인 파일

| 순서 | 파일 | 이유 |
|------|------|------|
| 1 | **HANDLER.md** (이 파일) | 현황·조치·폴더 규칙 |
| 2 | **AI_COLLAB.md** | 듀얼 블로그 규칙·금지 사항 |
| 3 | **WORKLOG.md** 최신 3~5개 | 직전 AI가 무엇을 했는지 |
| 4 | (Blogger 작업 시) `.github/editorial/BLOGGER_PROMPT.md` | 톤·구조 |
| 5 | (API 작업 시) `.github/editorial/BLOGGER_API_SETUP.md` | 인증 절차 |

Chance_Blog 글/레이아웃 작업 시 추가:

- `.github/editorial/CHANCE_BLOG_TEMPLATE.md`
- AdSense 관련이면 `index.html`·`privacy.md` 함부로 변경 금지

---

## 5. 작업 중·후 기록 규칙 (핸들러 + WORKLOG)

모든 AI는 의미 있는 작업이 끝나면:

1. **WORKLOG.md** 최상단에 새 항목 추가 (날짜, AI 이름, 대상, 변경, 다음 주의, 남은 이슈)
2. **HANDLER.md** §2 완료 표 / §3 조치 목록을 필요 시 갱신
3. 커밋 메시지 예: `docs: ... (Grok)` / `feat: ... (GPT)`

기록하지 않으면 다음 AI가 다른 폴더·다른 가정으로 작업해 충돌이 난다.

---

## 6. 절대 금지

- 같은 글을 Chance_Blog와 Blogger에 동시 게시
- `client_secret.json`, refresh token, API 키를 저장소에 커밋
- AdSense 승인 전 광고 코드·privacy 무단 대규모 변경
- WORKLOG / HANDLER 미확인 상태에서 덮어쓰기
- “내 로컬 폴더가 최신”이라고 가정 (반드시 `git pull`)

---

## 7. 폴더·VS Code 동기화 표준 절차

```text
[공식]
GitHub main  ←→  로컬 공식 폴더 1개  ←→  VS Code Open Folder
```

매 세션:

```bash
cd (공식 chanceblog 경로)
git pull origin main
# 작업
git add ...
git commit -m "... (AI이름)"
git push origin main
```

VS Code:

- 설정에서 Git: Autofetch 켜기 권장
- 원격과 어긋나면 무조건 pull 먼저
- 충돌 시 HANDLER/WORKLOG 기준으로 수동 병합, 추측으로 덮지 말 것

---

## 8. GPT에게 전달할 인수인계 문 (복붙용)

아래 블록을 GPT 세션 첫 메시지에 붙여 넣으면 된다.

```text
[Chance_Blog + Blogger 인수인계 — GPT용]

저장소: https://github.com/shine88pc/chanceblog
작업 시작 전 반드시 순서대로 읽을 것:
1) HANDLER.md
2) AI_COLLAB.md
3) WORKLOG.md 최신 3~5개

요약:
- 듀얼 블로그: Chance_Blog(교양·분석) + Blogger(실용·건강·생활), 동일 콘텐츠 금지, 균형 성장.
- Blogger 쪽: 프롬프트·blogger_generator.py·workflow·API 코드까지 완료. 실게시는 GitHub Secrets(BLOGGER_*) 등록 후.
- 사용자는 client_secret.json까지 확보. refresh token은 PC에서 scripts/get_blogger_token.py 실행 필요.
- 로컬에 폴더가 여러 개로 갈라져 있음 → 공식 clone 폴더 하나만 쓰고 VS Code도 그 폴더만 연 뒤 git pull/push로 동기화할 것.
- Cloud 결제 부담 시 API 대신 초안(_blogger_drafts) 수동 게시 또는 Blogger 이메일 게시 가능.
- Chance_Blog AdSense 승인 대기 중 → index.html 광고·privacy 함부로 변경 금지.

작업 후: WORKLOG.md 최상단 기록 + 필요 시 HANDLER.md 갱신 + 커밋에 AI 이름·대상 명시.

대상 명시: Chance_Blog / Blogger / 공통 중 하나.
```

---

## 9. 빠른 링크

| 문서 | 경로 |
|------|------|
| 협업 규칙 | `AI_COLLAB.md` |
| 작업 로그 | `WORKLOG.md` |
| Blogger 프롬프트 | `.github/editorial/BLOGGER_PROMPT.md` |
| Blogger API 설정 | `.github/editorial/BLOGGER_API_SETUP.md` |
| Chance 편집 기준 | `.github/editorial/CHANCE_BLOG_TEMPLATE.md` |
| 생성기 | `blogger_generator.py` / `generator.py` |
| 워크플로 | `.github/workflows/blogger.yml` / `chanceblog.yml` |

---

*마지막 갱신: 2026-10-20 Grok — 핸들러 최초 작성, 폴더 통합·VS Code 동기화·GPT 인수인계 포함*
