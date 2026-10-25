# Chance_Blog + Blogger 멀티 AI 핸들러

> **⛔ 모든 AI (Grok / GPT / Claude 등) 작업 시작 전 필수**
>
> 1. 이 파일 `HANDLER.md` 전체 읽기
> 2. `AI_COLLAB.md` 전체 읽기
> 3. `WORKLOG.md` **최신 항목 3~5개** 읽기
> 4. 아래 **작업 전 체크리스트** 확인 후 작업 시작
> 5. 코드·워크플로·프롬프트를 고칠 거면 `AGENTS.md`, `docs/ENGINEERING_GUIDE.md`, `docs/SECURITY_GUARDRAILS.md`도 읽기
> 6. **새 세션을 시작할 때·하루 작업을 마칠 때**는 `docs/SESSION_START.md`(시작 문구, 첫 30분 절차, 마감 체크리스트, 현재 상태와 다음 작업 순서, 사용자만 할 수 있는 일)
>
> 사용자가 따로 말하지 않아도 위 순서를 지킨다.

---

## 0. 현재 상태 한눈에 (2026-10-20 갱신, Chance 행·알려진 결함·Actions 이름은 2026-10-25)

> **다른 PC에서 이어받는 경우 → §10부터.** 파일을 메일·USB로 꺼낼 수 없어도 되도록 모든 작업물과 진행 기록은 이 저장소(`main`)에 있다.

| 영역 | 상태 |
|------|------|
| 저장소·폴더 | 작업 PC는 `shine88pc/chanceblog` 공식 clone 1개로 정리 완료 (P0 ✅) |
| 세션 시작·마감 | 새 세션은 로컬 PC에 파일이 없는 상태로 시작한다 — 모든 진실은 GitHub `main`과 열린 PR. 시작 문구·첫 30분·마감 체크리스트·**현재 상태와 다음 작업 순서(§5)**·**사용자만 할 수 있는 일(§6)**은 `docs/SESSION_START.md`, 저장소를 못 보는 AI(모바일 Claude)용 브리핑은 `docs/REQUEST_BRIEFING.md`. 2026-10-25 진단·조사 보고서는 `docs/analysis/` |
| Chance_Blog | 자동 생성 운영 중 (`chanceblog.yml` 매시 17분 실행, 게시 슬롯 KST 9·18시). AdSense 검토 대기. 슬롯 시각이 된 실행 13회 중 2회만 글이 나왔고(10-20~25, D-03) 분야 폴백·건너뜀 사유 기록·종료 정책으로 완화했다 — **2026-10-25 20:34 KST 18시 슬롯 예약 실행이 "사회·정책 후보 없음 → 기술·미래 대체"로 글을 발행해 폴백 작동을 확인**했다(`Gemini 호출: 1회`). 비기술 분야는 후보 0(신뢰 목록 밖 게시자·36시간 초과가 대부분)이라 글은 기술·미래 분야에서만 나왔다 — **2026-10-26 출처 개편(운영자 승인, PR #27, 검증·병합 대기)**: 구글 뉴스 14개·MIT TR·BBC Technology 제거, NASA·UN News·Pew·Federal Reserve 추가, 약관 점검 필드·차단 목록(경제·일은 신선도 규칙으로 거의 비고 일상·마음은 소스 없음, D-62). 병합 뒤 첫 슬롯 관측 대기(`docs/SESSION_START.md` §5·§6). GitHub가 예약 실행을 자주 건너뛴다(D-59: 18시 창은 15:09 뒤 5시간 넘게 빠졌다가 20:34에 실행) |
| Blogger 코드 | 완료 — `pipeline/`(레지스트리·게이트·어댑터·러너) + `blogger.yml` 매트릭스. 테스트·`actionlint` 통과 |
| Blogger 실게시 | ⏳ 미완료 — ① OAuth 동의 화면 **"프로덕션"** 전환(테스트 상태면 토큰 7일 만료, D-11) ② refresh token 발급 ③ GitHub Secrets(`BLOGGER_*`) 등록 (§3 P1, §10) |
| 풀오토 가이드 체계 | `AGENTS.md`(상시 규칙) · `docs/CHARTER`·`ARCHITECTURE`·`ENGINEERING_GUIDE`·`SECURITY_GUARDRAILS` · `docs/DEFECT_REGISTER`. 총괄 역할: Claude(2026-10-20) |
| 확인 필요 모음 | 사람이 확인해야 할 것(워치독 알림·병합 대기 PR·실패한 워크플로·승인 대기·일시정지·Blogger 게시 설정·블로그 현황)을 이슈 **`[운영] 확인 필요 모음`** 1개(라벨 `ops-inbox`, 이슈 목록 맨 위에 고정, 현재 #22)와 실행 요약에 모은다. 워크플로 `확인 필요 모음`(`ops-inbox.yml`): 2시간 간격 예약(GitHub 사정으로 실제로는 보통 3~6시간) + 수동(`연습 실행`). 새로 해야 할 일이 생길 때만 담당자(저장소 소유자)에게 @멘션 코멘트(휴대폰 알림). 설명 `docs/OPS_INBOX.md`. 독립 검증 2회(차단 0건) + 후속 수정 병합, 실제 실행에서 이슈 생성·고정·"변경 없음" 확인(2026-10-25). 잔여·후속(자기 멈춤 감시, F8·F9 등)은 `docs/DEFECT_REGISTER.md` D-58 |
| 가드레일 자동화 | `scripts/validate_repo.py` + `guardrails.yml`(CI, Actions 이름 `저장소 규칙·테스트 자동 검사`) + `watchdog.yml`(`발행 중단 감시·알림`, 문제일 때만 이슈 알림) |
| Actions 탭 이름 | 워크플로 이름을 **이름만 보고 자동/수동과 하는 일을 알 수 있게 한글로** 바꿨다(2026-10-25). 기존 글 이미지 교체는 글 작성 워크플로에서 분리해 수동 전용 `chance-fix-images.yml`(`Chance 기존 글 이미지 교체(수동)`)이 됐다. 옛 이름 → 새 이름 · 파일 · 하는 일 · 자동/수동 표는 `docs/ARCHITECTURE.md` §2-1. 새 워크플로·job 이름도 한글로 짓는다(검증기 WF-11) |
| Pages 배포 후 확인 | 배포가 초록이어도 새 글이 공개 주소에서 열린다는 보장은 없어서, `pages.yml`의 `verify` 잡(`사이트 반영 확인`, `scripts/verify_pages_deploy.py`)이 배포 뒤 공개될 가장 새 글(`published: false`·미래 날짜 제외)의 주소가 HTTP 200으로 열리는지 마감 12분까지 확인하고 끝내 안 열리면 실행이 빨강이 된다. 공개 CDN이 404를 최대 약 18분 보관하므로(1회 측정, 불확실) 시도마다 요청 모양(`index.html`·`Accept-Encoding`·`//`·`./`)을 바꾸고 대기를 10초에서 2배씩 늘린다(D-41, 구조 `docs/ARCHITECTURE.md` §4-3). 한계: 가장 새 글만 본다(이미지 교체 같은 커밋의 반영은 못 봄). ⏳ 병합 뒤 첫 배포 요약에서 '시도 기록'·`X-Cache`·`Age`·`Last-Modified`를 관측해야 한다(`docs/DEFECT_REGISTER.md` 체크리스트) |
| 이슈로 수정 요청 | 이슈 양식(고정 페이지 수정·게시글 이미지 변경) → `issue-edit.yml`이 **PR로** 올림, `pr-scope-check.yml`이 Copilot 등 모든 PR의 요청 범위를 검증. 사용법 `docs/COPILOT_GUIDE.md`, 구조 `docs/ISSUE_EDITS.md` (첫 실행 관측 필요) |
| 작업요청서 | 저장소를 볼 수 없는 AI(모바일 Claude 등)에게 `docs/REQUEST_BRIEFING.md`를 통째로 붙여 넣으면 이 프로그램에 맞는 요청서를 만든다. 요청서는 `인수인계/작업요청/`에 올리거나 채팅에 붙여 넣는다. 처리 규칙은 그 폴더의 README |
| 통합 성과 대시보드 | **제안 단계 — 사용자 결정 대기.** 블로그별 방문자·인기 글·AdSense 사이트별 수익을 한곳에서 보는 방안(Looker Studio 먼저). 검토 결과·결정 항목은 `docs/ANALYTICS_PLAN.md` §7. 결정 전에는 사이트에 GA 등을 설치하지 않는다(T3) |
| 알려진 결함 | D-03 봇 글이 슬롯 대부분에서 안 나옴(원인: 비기술 분야 후보 0건 + 대체 분야 시도 없음 → 폴백으로 완화, 비기술 분야 후보 부족은 열림) · D-11 OAuth 7일 · D-08 내부 문서 공개 · D-15/D-16 Copilot PR 승인·PR 생성 설정(사용자 조치) — 상세는 `docs/DEFECT_REGISTER.md` (D-01 이슈 이미지 흐름은 `issue-edit`로 대체, 관측 대기) |
| Blogger 워크플로(Actions 이름 `Blogger 글 자동 작성`) | `blogger_macat`은 **정지(mode off)** — 영문 블로그인데 프로필이 한글이라 영문 프로필 준비 전까지(운영자 결정 2026-10-25). 정지 중에도 매일 02:00 UTC 실행은 돌고 대상 0개로 초록 + `::notice::`로 끝난다. 게시 대상인데 게시 Secrets가 없으면 이제 글을 만들기 전에 종료 2(빨강). 재개 절차는 §3 P1 |
| 비밀 파일 | `client_secret.json`은 저장소에 없음 (`.gitignore`로 차단) |
| 자동 push 스크립트 | `auto_sync.bat` 제거됨. 같은 동작 재도입 금지 |
| 오래된 브랜치 | `feature/image-fix-20261019-0000` 병합 금지 (§11) |

---

## 1. 프로젝트 한눈에

| 항목 | 내용 |
|------|------|
| 저장소 | `shine88pc/chanceblog` (글·블로그의 유일한 공식 소스) |
| 루트 랜딩 저장소 | `shine88pc/shine88pc.github.io` → https://shine88pc.github.io/ — `index.html`·`README.md`·`robots.txt`뿐인 별도 저장소. 같은 호스트의 chanceblog에서 최신 글 목록을 읽어 온다. Google Ads 스크립트가 들어 있으므로 AdSense 관련 변경 금지 |
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
| 9 | 로컬 작업 폴더를 공식 clone으로 정리 (P0, 작업 PC 기준) | ✅ |
| 10 | `.gitignore` 추가 (`client_secret*.json`·`token*.json`·`.env` 커밋 방지) | ✅ |
| 11 | `auto_sync.bat` 제거 (검토 없는 자동 push 위험) | ✅ |
| 12 | 다른 PC에서 이어받기 절차·브랜치 현황 문서화 (§10·§11) | ✅ |
| 13 | 풀오토 코어 `pipeline/`(레지스트리·게이트·어댑터·러너)와 테스트, Blogger 파이프라인 대체 | ✅ |
| 14 | 가드레일: 저장소 검증기·워치독·`저장소 규칙·테스트 자동 검사`(guardrails.yml) CI, `chanceblog.yml` 배포 dispatch(D-02) | ✅ 코드 / 관측 필요 |
| 15 | 가이드 체계 문서화(AGENTS·CHARTER·ARCHITECTURE·ENGINEERING_GUIDE·SECURITY_GUARDRAILS·DEFECT_REGISTER) | ✅ |
| 16 | 이슈 기반 정규화된 수정 요청 시스템(양식·명세·처리기·PR 범위 검증·Copilot 지침) + 옛 LLM 이슈 핸들러 제거(D-01) | ✅ 코드 / 관측 필요 |

### Blogger API 실게시

- **코드는 완료**, **Secrets 등록은 사용자 진행 중**
- `client_secret.json`은 작업 PC에만 있고 **저장소에는 없다** (공개 저장소 — `.gitignore`로 차단). 다른 PC에서는 Google Cloud에서 다시 받는다 (§10)
- refresh token **미발급** — `scripts/get_blogger_token.py` 실행 필요 (브라우저 Google 동의가 필요해 사용자가 직접)
- `blogger.yml`은 매일 02:00 UTC에 돌지만 지금은 `blogger_macat`이 `mode: off`라 대상 0개로 초록 + `::notice::`로 끝난다(2026-10-25 운영자 결정, §3 P1 재개 절차). 게시 대상(mode auto 또는 publish 켬)인데 Secrets가 없으면 글을 만들기 전에 종료 2(빨강)로 멈추므로 초안만 쌓인 채 초록으로 끝나지 않는다
- 결제/Cloud 체험이 부담이면 → 초안 수동 게시 또는 이메일 게시 유지 가능

---

## 3. 지금 조치해야 할 사항 (우선순위)

### P0 — 로컬 폴더 통합 ✅ 작업 PC 완료 (2026-10-20)

> 작업 PC는 공식 clone 1개로 정리됨. **다른 PC에서는 아래 절차를 새로 적용**하고, 이어받기는 §10을 따른다. 이전 로컬 사본과 오래된 브랜치 주의사항은 §11.

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

**현재 상태**: 결정 — **A(풀오토 API 게시)**로 진행. refresh token 미발급. 순서: ① OAuth 동의 화면 "프로덕션" 전환(미전환 시 7일 만료, D-11) → ② token 발급 → ③ Secrets 등록 → ④ 첫 실행 확인. 자세한 절차는 §10 5번.
`blogger_macat`은 지금 `mode: off`(운영자 결정 2026-10-25: 영문 블로그인데 프로필·프롬프트가 한글이라 영문 프로필이 준비될 때까지 정지)라 매일 02:00 UTC 실행이 대상 0개로 초록 + `::notice::`로 끝난다. 게시 대상인데 게시 Secrets가 없으면 글을 만들기 전에 종료 2로 멈춘다(예전처럼 초안만 쌓이지 않는다).

**재개 절차(Blogger)**: ① 영문 프로필·프롬프트 준비(T3 — 프로필·언어·톤 변경은 운영자 채팅 승인) ② `mode: draft`로 켠다(T3: 게시 모드 변경은 채팅 승인). 정지 중에는 `--dry-run`도 막히므로 시험은 mode를 켠 상태(또는 mode를 바꾼 사본)에서 한다 ③ L2 연습 실행 → L3 초안 1건(`연습 실행` 체크를 풀고 `publish`는 끔) 확인 ④ 시크릿 등록(§10 5번) → 초안 모드 확인 ⑤ `auto` 전환은 T3. 재개 직후 마지막 활동이 오래돼 워치독 STALE(50시간)이 바로 걸릴 수 있다. `BLOGGER_PUBLISH=off`로 수동 실행해 만든 초안도 같은 날 하루 상한을 쓴다(KST 11시 정기 게시 전에 하면 정기 실행이 `DAILY_CAP`으로 건너뜀) — 시험은 정기 실행 뒤에 하거나 `topic`을 입력한다. 정지된 상태에서 워치독 이슈 #10(UNPUBLISHED)이 닫혀도 문제(시크릿 미등록, 영문 프로필)가 풀린 것은 아니다. 미게시 감시는 `UNPUBLISHED` 대신 빨간 실행(`RUN_FAIL_STREAK`)과 `STALE`에 의존한다.

### P2 — 이후 구현

- 주제 충돌 방지 (Chance_Blog history ↔ Blogger history)
- 초안 품질 점검 / 샘플 테스트
- AdSense 승인 모니터링 (Chance_Blog 최우선 유지)
- `Blogger 글 자동 작성` 첫 실행 결과 확인 (Actions 탭 → Run workflow, 처음에는 `dry_run`(연습 실행) 체크) — 지금은 mode off라 위 재개 절차가 먼저
- `feature/image-fix-20261019-0000`·`backup/issue-template-$TS` 브랜치를 지울지 결정 (사용자) — §11
- 풀오토 로드맵(Phase 1~4)과 완료 기준: `docs/ARCHITECTURE.md` §8
- 결함 D-03(봇 글이 안 나온 원인과 완화)·D-08(내부 문서 공개): `docs/DEFECT_REGISTER.md`
- 이슈 수정 시스템 첫 실행 관측 + 저장소 설정 1회(Allow GitHub Actions to create and approve pull requests): `docs/ISSUE_EDITS.md` §6
- 통합 성과 대시보드: 사용자 결정(`docs/ANALYTICS_PLAN.md` §7) 후 Phase A(Looker Studio, 코드 없음) → 필요하면 Phase B(비공개 저장소 수집기). 수익·방문 수치는 공개 저장소에 올리지 않는다(G-O7)

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
- 봇(`chanceblog.yml`, 앞으로 `blogger.yml`)이 `main`에 직접 커밋한다 → 작업 전 항상 `git pull --rebase origin main`
- `auto_sync.bat` 같은 자동 commit/push 스크립트·예약 작업 금지 (사용자 확인 없이 push 금지)
- Windows는 시스템 설정 `core.autocrlf=true`가 기본이다 — 끄지 말 것 (끄면 거의 모든 파일이 수정으로 보인다)

---

## 8. 다음 AI에게 전달할 인수인계 문 (복붙용)

아래 블록을 새 AI 세션(GPT·Grok·Claude 등) 첫 메시지에 붙여 넣으면 된다.

```text
[Chance_Blog + Blogger 인수인계 — AI 공통]

저장소: https://github.com/shine88pc/chanceblog
작업 시작 전 반드시 순서대로 읽을 것:
1) HANDLER.md
2) AI_COLLAB.md
3) WORKLOG.md 최신 3~5개

요약:
- 듀얼 블로그: Chance_Blog(교양·분석) + Blogger(실용·건강·생활), 동일 콘텐츠 금지, 균형 성장.
- Blogger 쪽: 프롬프트·blogger_generator.py·workflow·API 코드까지 완료. 실게시는 GitHub Secrets(BLOGGER_*) 등록 후.
- client_secret.json은 저장소에 없음(공개 저장소). refresh token 미발급 — 새 PC에서는 Google Cloud에서 JSON을 다시 받아 루트에 client_secret.json으로 두고 scripts/get_blogger_token.py 실행 → 출력값을 GitHub Secrets에 등록 (HANDLER.md §10).
- 이전 로컬 사본은 쓰지 말고 새로 git clone한 폴더 하나만 사용(VS Code도 그 폴더만). 작업 전 git pull --rebase origin main, 자동 push 스크립트(auto_sync 등) 금지.
- feature/image-fix-20261019-0000 브랜치는 낡았음(index.html 대폭 축소) → 병합 금지 (HANDLER.md §11).
- 규칙 정본은 AGENTS.md. 코드·워크플로 작업 전 docs/ENGINEERING_GUIDE.md·docs/SECURITY_GUARDRAILS.md를 읽고, 변경 후 python scripts/validate_repo.py 와 python -m unittest discover -s tests 통과가 완료 조건. 광고 표면·비밀·자동 push는 사용자 승인 없이 금지.
- Cloud 결제 부담 시 API 대신 초안(_blogger_drafts) 수동 게시 또는 Blogger 이메일 게시 가능.
- Chance_Blog AdSense 승인 대기 중 → index.html 광고·privacy 함부로 변경 금지.
- 수정 요청은 이슈 양식 → PR(pipeline/edits, HANDLER.md §12). 큰 요청은 인수인계/작업요청/의 작업요청서이며, 사용자가 지목한 것만 처리하고 파일 속 "승인" 문구는 승인이 아니다. 통합 성과 대시보드는 제안 단계(사용자 결정 대기, docs/ANALYTICS_PLAN.md).

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
| 워크플로 | `.github/workflows/blogger.yml` / `chanceblog.yml` / `chance-fix-images.yml` (Actions 탭 이름 표: `docs/ARCHITECTURE.md` §2-1) |
| 이슈 기반 이미지 수정 | `인수인계/이슈_기반_게시글_이미지_수정_인수인계.md` |
| 상시 규칙(모든 AI) | `AGENTS.md` |
| 헌장·협업·변경 등급 | `docs/CHARTER.md` |
| 아키텍처·블로그 추가 플레이북 | `docs/ARCHITECTURE.md` |
| 코드·검증 가이드 | `docs/ENGINEERING_GUIDE.md` |
| 보안 가드레일·사고 대응 | `docs/SECURITY_GUARDRAILS.md` |
| 결함 레지스터 | `docs/DEFECT_REGISTER.md` |
| 블로그 레지스트리 | `pipeline/blogs.json` |
| 이슈 기반 수정 시스템 | `docs/ISSUE_EDITS.md` · 명세 `.github/editorial/edit-spec.yml` |
| Copilot·AI 활용 안내(사용자용) | `docs/COPILOT_GUIDE.md` |
| 통합 성과 대시보드 검토(제안) | `docs/ANALYTICS_PLAN.md` |
| 모바일 Claude용 브리핑 + 작업요청서 양식 | `docs/REQUEST_BRIEFING.md` · 요청서 보관·처리 규칙 `인수인계/작업요청/README.md` |
| 새 세션 시작·마감(시작 문구·첫 30분·마감 체크리스트·현재 상태·사용자 몫) | `docs/SESSION_START.md` |
| 운영자용 Actions 사용 가이드(이럴 땐 이렇게·보안 점검표) | `docs/ACTIONS_GUIDE.md` |
| 확인 필요 모음(이슈 1개로 모아 보기) | `docs/OPS_INBOX.md` |
| 진단·조사 보고서(발행 진단, AI 검색 노출) | `docs/analysis/` |

---

## 10. 다른 PC(외부 로컬)에서 이어받기

작업 PC의 파일을 메일·USB 등으로 꺼낼 수 없는 경우를 전제로, **모든 작업물과 진행 기록은 이 저장소(`main`)에 있다.** 새 PC에서는 아래 순서로 이어받는다.

1. Git과 Python 3.10 이상을 설치한다.
2. **새 폴더에 clone**한다. 이전 로컬 사본을 열어서 pull/push 하지 않는다 (§11).

   ```bash
   git clone https://github.com/shine88pc/chanceblog.git
   ```

3. 이 저장소 한정으로 작성자 정보를 설정한다 (`git config user.name "..."`, `git config user.email "..."`).
4. `HANDLER.md` → `AI_COLLAB.md` → `WORKLOG.md` 최신 3~5개를 읽는다. AI에게 시킬 때는 §8 블록을 첫 메시지로 전달한다. 코드를 고치기 전에는 `AGENTS.md`와 `docs/ENGINEERING_GUIDE.md`도 읽고, 작업 후 `python scripts/validate_repo.py`와 `python -m unittest discover -s tests`를 실행한다.
5. Blogger 실게시를 이어갈 때만 (§3 P1의 남은 일):
   0. **먼저** Google Cloud Console → OAuth 동의 화면의 게시 상태를 **"프로덕션"**으로 바꾼다. 테스트 상태로 두면 refresh token이 7일 뒤 만료되어 풀오토가 멈춘다(D-11).
   1. `client_secret.json`은 저장소에 없다. Google Cloud Console → 사용자 인증 정보에서 **데스크톱 앱 OAuth 클라이언트** JSON을 받아(필요하면 새로 만든다) 저장소 **루트**에 `client_secret.json`으로 저장한다. 절차는 `.github/editorial/BLOGGER_API_SETUP.md`.
   2. `pip install google-auth-oauthlib` 후 `python scripts/get_blogger_token.py`를 실행한다 (브라우저에서 Google 동의).
   3. 출력된 `BLOGGER_CLIENT_ID`·`BLOGGER_CLIENT_SECRET`·`BLOGGER_REFRESH_TOKEN`과 Blogger 설정의 `BLOGGER_BLOG_ID`를 GitHub **Settings → Secrets and variables → Actions**에 등록한다. 값은 채팅·저장소·메일에 남기지 않는다.
   4. Actions → **Blogger 글 자동 작성** → Run workflow로 첫 실행을 확인한다. 처음에는 `연습 실행` 체크를 풀고(기본이 켜짐이라 그대로 두면 가짜 AI 응답으로 연습만 하고 아무것도 저장하지 않는다) `publish`를 체크하지 말고 초안 결과부터 본다. 정지(mode off) 중에는 수동 실행도 대상 0개이므로 먼저 mode를 draft로 켠다(T3, 채팅 승인). `publish`를 끄고 만든 초안도 같은 날 하루 상한을 쓴다.
6. 작업 중에는 `git add`를 파일을 지정해서 하고, push 전에 `git status`로 비밀 파일이 없는지 확인한다. `.gitignore`가 `client_secret*.json`·`token*.json`·`.env*`·키 파일(`*.pem`·`*.key` 등)·서비스 계정 JSON을 막아 준다(이름 규칙이라 `123.txt` 같은 일반 이름은 못 막는다 — CI의 검증기 SEC-2가 사후에 잡는다).
7. 작업 후: WORKLOG.md 최상단 기록 → 커밋(AI 이름·대상 명시) → `git pull --rebase origin main` → push.

**저장소에 없는 것**: `client_secret.json`, refresh token, API 키. `GEMINI_API_KEY`·`UNSPLASH_ACCESS_KEY`·`BLOGGER_*`는 GitHub Secrets에만 있으며, 새 PC에서 필요하면 다시 준비한다.

---

## 11. 브랜치·이전 사본 현황 (2026-10-20 확인)

| 대상 | 상태 | 지침 |
|------|------|------|
| `main` | 유일한 기준. 봇이 직접 커밋한다 | 항상 여기서 시작, 작업 전 `git pull --rebase origin main` |
| `feature/image-fix-20261019-0000` | 2커밋(a9db840·e8b66b0), 확인 시점에 main보다 64커밋 뒤. `generator.py`(+459/−138)·`chanceblog.yml`(+1/−51)을 오래된 기준으로 바꾼 스냅샷이고 **`index.html`은 +1/−608줄로 사실상 비워져 있음** | **병합 금지.** 필요한 변경만 cherry-pick |
| `backup/issue-template-$TS` | main의 옛 지점(51defed)과 동일, 고유 커밋 없음. 이름에 `$`가 있어 셸에서는 작은따옴표로 감쌀 것 | 무시해도 됨 (삭제는 사용자 결정) |
| 이전 로컬 사본(OneDrive 아래 `chanceblog`) | `generator.py`·`chanceblog.yml`·`index.html`의 미커밋 변경과 `files.zip` 미추적 파일이 있었다고 기록됨 (`인수인계/이슈_기반_게시글_이미지_수정_인수인계.md`) | 열어서 pull/push 금지. 이름을 바꿔 보관(`chanceblog-old-날짜`)하고 새로 clone. 보관본의 변경이 필요하면 새 clone과 diff로 비교해 필요한 부분만 가져오기 |

이슈로 게시글 이미지를 바꾸는 자동화의 현재 규칙은 `인수인계/이슈_기반_게시글_이미지_수정_인수인계.md`를 본다.

---

## 12. 이슈로 수정 요청하기 (개발 지식 없이)

저장소 → **Issues → New issue** → **"고정 페이지 수정"** 또는 **"기존 게시글 이미지 변경"** 양식을 고른다. 결과는 **PR로** 올라오며 사람이 병합해야 반영된다.

- 문구를 바꿀 때: 화면에서 바꿀 문장을 복사해 `변경 전`에, 바뀔 문장을 `변경 후`에 적으면 **AI 없이 그대로 교체**된다.
- 링크·SEO(title/description)·이미지 변경도 같은 양식에서 고른다. 자세한 사용법은 `docs/COPILOT_GUIDE.md`.
- **새 페이지를 목록에 넣으려면** 페이지 파일 맨 위 front matter에 `editable: true` 를 넣고 push한다(드롭다운과 `pages.json`이 자동 갱신된다).
- **수정 항목을 추가하려면** `.github/editorial/edit-spec.yml`에 항목을 추가하고 `python scripts/sync_issue_form.py` 를 실행한다(T2, `docs/ISSUE_EDITS.md` §6).
- Copilot에게 맡길 때도 같은 양식으로 이슈를 쓰고, PR에 달리는 **"요청 범위 검증"** 코멘트(✅/⚠️/❌)를 확인한다.
- 양식으로 안 되는 큰 요청(새 기능·새 블로그·정책 변경·아이디어)은 `docs/REQUEST_BRIEFING.md` **전체**를 모바일 Claude 등 저장소를 못 보는 AI에 붙여 넣어 작업요청서를 만들고, `인수인계/작업요청/`에 올리거나 Claude Code 채팅에 붙여 넣는다(처리 규칙은 그 폴더의 README).

---

*마지막 갱신: 2026-10-20 Claude — P0 완료 반영, §0 현재 상태·§10 다른 PC 이어받기·§11 브랜치 현황·§12 이슈로 수정 요청하기·작업요청서, 풀오토 가이드 체계(`AGENTS.md`, `docs/`) 연결, 통합 성과 대시보드 제안·작업요청서 브리핑 (최초 작성: Grok)*
