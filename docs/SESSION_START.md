# 새 세션 시작·마감 가이드

> 새 AI 세션(Claude Code 등)을 시작할 때와 하루 작업을 마칠 때의 **고정 절차**입니다.
> 사용자는 비개발자이고 회사 PC에서 일하며 **파일을 PC 밖으로 꺼낼 수 없습니다.** 세션을 새로 열면 로컬 PC에 저장소 사본이 없을 수 있으므로, **모든 진실은 GitHub `shine88pc/chanceblog`의 `main`과 열린 PR(`ai/*` 브랜치)에 있습니다.** AI의 개인 기억(메모리)·이전 대화 요약보다 이 저장소의 문서가 우선합니다.

## 1. 사용자가 하는 일 (새 세션을 열 때, 1분)

1. Claude Code에서 새 세션을 열고 작업 폴더를 정합니다(지금까지는 바탕화면의 `KCY` 폴더. 비어 있어도 됩니다).
2. 첫 메시지에 아래 **시작 문구**를 붙여 넣습니다. 이 문서를 휴대폰이나 다른 PC의 GitHub 웹(`docs/SESSION_START.md`)에서 열어 복사해도 됩니다.
3. AI가 현재 상태를 10줄 이내로 보고하면 읽고, 승인이 필요한 질문에 답합니다. 승인은 **채팅 메시지로만** 유효합니다.

**시작 문구**

```text
저장소 https://github.com/shine88pc/chanceblog 를 이 작업 폴더 아래 chanceblog 폴더로 clone해서 시작해줘(이미 있으면 git pull).
읽는 순서: HANDLER.md → AI_COLLAB.md → WORKLOG.md 최신 항목 3~5개 → docs/SESSION_START.md §2·§5·§6.
그다음 ① 열린 PR·브랜치·최근 GitHub Actions 실행 상태를 확인해 지금 상태를 10줄 이내로 보고하고 ② §5 '다음 작업 순서'의 첫 항목부터 제안해줘.
사용자 승인이 필요한 일(비밀·계정·광고 표면·비용·삭제·정책·톤)은 채팅으로 먼저 물어봐.
내 로컬 기억(메모리)과 저장소 문서가 다르면 저장소 문서를 믿어.
```

## 2. AI의 첫 30분 (순서 고정)

### 2-1. 작업 환경 만들기 (Windows 회사 PC 기준)

- clone: `git clone https://github.com/shine88pc/chanceblog.git chanceblog` (공개 저장소라 읽기는 로그인이 필요 없습니다).
- 작성자 설정은 **clone 안에서만**(저장소 로컬 설정), 기존 커밋의 작성자와 같게 둡니다(`git log -1 --format="%an <%ae>"`로 확인). 전역 git 설정은 건드리지 않습니다.
- 시스템 `core.autocrlf=true`는 **끄지 않습니다.** 작업 사본이 CRLF로 보이는 것은 정상이고, 끄면 모든 파일이 수정된 것으로 보입니다.
- 한글 커밋 메시지는 UTF-8 파일에 써서 `git commit -F 파일`로 넘깁니다(셸 인자로 넘기면 인코딩이 깨질 수 있습니다).
- 파이썬은 `PYTHONUTF8=1`을 붙여 실행합니다(한국어 Windows 콘솔 cp949 문제). 코드는 Python 3.10에서 돌아야 하며 3.12 전용 문법은 금지입니다.
- 검증 도구: `python -m venv .venv` 후 `.venv\Scripts\pip install -r requirements-dev.txt pyflakes vermin`. 기준선 확인: `python scripts/validate_repo.py`(오류 0), `python -m unittest discover -s tests`(전체 통과. 일부만 돌릴 때는 `-s tests -p "test_xxx.py"`).
- push 자격증명: Git Credential Manager가 브라우저 로그인으로 처리합니다. 비대화형 push가 인증 오류로 막히면 사용자에게 터미널 탭에서 한 번 로그인해 달라고 요청합니다(환경변수 `GIT_TERMINAL_PROMPT=0`, `GCM_INTERACTIVE=false`로 무한 대기를 막습니다). force push는 하지 않습니다.
- `gh` CLI는 없습니다. PR은 웹에서 만듭니다: `https://github.com/shine88pc/chanceblog/compare/main...<브랜치>?expand=1`. 제목·본문은 `.github/pull_request_template.md` 형식을 따릅니다.
- 파이썬 패치 스크립트에 백슬래시·`$`가 들어갈 때 셸 heredoc은 문자를 망가뜨릴 수 있습니다. 파일로 만들어 실행합니다.

### 2-2. 상태 읽기

- 이미 반영된 것: `git log --oneline -20 origin/main`, `WORKLOG.md` 최신 항목, `docs/DEFECT_REGISTER.md`(결함 상태와 하단 관측 체크리스트).
- 열린 PR과 브랜치: `https://github.com/shine88pc/chanceblog/pulls`, `git branch -r`. 병합되지 않은 PR이 있으면 그 PR 본문의 검증 증거와 남은 지적부터 읽습니다.
- 최근 Actions 실행: 공개 API(`curl -s "https://api.github.com/repos/shine88pc/chanceblog/actions/runs?per_page=30"`)로 읽을 수 있습니다(로그인 없이 IP당 시간당 60회 제한이라 아껴 씁니다).
- 로그 원문과 Settings 화면은 로그인이 필요합니다. 필요하면 사용자에게 로그인 화면을 열어 달라고 하고, **로그인은 사용자가 직접** 합니다(AI는 비밀번호·토큰을 입력하지 않습니다).

### 2-3. 첫 보고 (10줄 이내)

main 최신 커밋 · 최근 24시간 자동 실행 결과(Chance 슬롯, Blogger, Watchdog, Pages) · 열린 PR/브랜치 · 열린 워치독 이슈 · 사용자 결정 대기 항목 · 오늘 제안하는 첫 작업.

## 3. 일하는 방식 (이 저장소의 약속)

1. 변경은 **작은 PR**로 합니다. 브랜치 이름 `ai/<AI이름>/<주제>`. T2 이상은 **독립 검증**(다른 세션이 새 clone에서 diff와 직접 실행 결과만 근거로 검증)을 거친 뒤 병합합니다.
2. 구현을 맡기는 하위 에이전트는 작업 폴더 밖의 별도 clone에서 일하고 일반 push만 합니다. 문서·WORKLOG·병합은 총괄 세션이 통합합니다.
3. 서로 같은 문서·워크플로를 건드리는 PR은 **순차**로 병합합니다. 병합 뒤 main에서 확인합니다.
4. 봇이 main에 직접 커밋합니다. 작업 전에 항상 최신 main을 받습니다. main 보호 규칙은 "삭제·force push 차단"만 허용하고, PR 필수·승인 필수·상태 검사 필수는 **켜지 않습니다**(자동 발행이 멈춥니다).
5. 병합한 PR의 브랜치는 지우지 않습니다(브랜치 삭제는 T3, 사용자 승인).
6. 결과 보고는 숫자와 실제 출력으로 합니다. 실행하지 않은 검증을 통과했다고 쓰지 않습니다.

## 4. 하루 마감 체크리스트 (AI)

- [ ] 모든 변경이 push됨: `git status` 깨끗, `git stash list` 비어 있음, `git branch -vv`에서 로컬에만 있는 커밋 없음
- [ ] 열린 PR마다 상태 기록(검증 단계, 남은 지적, 병합 조건)
- [ ] `WORKLOG.md` 최상단에 오늘 항목(변경, 증거, 못 한 검증, 다음 AI 주의사항)
- [ ] `HANDLER.md` §0 현황 표와 이 문서 §5(다음 작업 순서)·§6(사용자 몫) 갱신
- [ ] `docs/DEFECT_REGISTER.md` 결함 상태와 관측 체크리스트 갱신
- [ ] `docs/REQUEST_BRIEFING.md`(모바일 Claude용) 기준일·현황 갱신
- [ ] 실행 중인 백그라운드 작업(에이전트, Actions 수동 실행)이 없는지 확인하고, 남아 있으면 결과 위치를 기록
- [ ] 사용자에게 마감 보고: 한 일, 하지 않은 일, 사용자가 할 일(결정·설정), 다음 첫 작업

## 5. 현재 상태와 다음 작업 순서

> 갱신 기준: **2026-10-25 저녁(KST)**. 이후 변경은 `WORKLOG.md` 최신 항목·열린 PR·`HANDLER.md` §0이 더 정확합니다. 새 세션은 이 절을 믿기 전에 `git log --oneline -20 origin/main`과 열린 PR 목록으로 대조하세요.

### 5-1. 오늘 병합된 것 (main)

| PR | 내용 | 결함 |
|----|------|------|
| #11 | Chance 분야 폴백·건너뜀 사유 기록·종료 정책 | D-03 완화, D-25~D-36 등록 |
| #14 | 보안 설정(키 파일 무시 규칙, 새 구글 키 형식 탐지, `mask()` 공용 패턴, CODEOWNERS) | D-30·D-31 |
| #15 | 워치독 보강(하루 단위 판정·글 파일 기준 STALE·사이트 배포 점검·담당자 지정, 하루 2회) | D-28 해결 |
| #16 | Blogger 가시화 + `blogger_macat` 정지(mode off) | D-25·D-26·D-32 |
| #17 | 워크플로 한글 이름 + 이미지 교체 분리 + 검증기 WF-11 | — |
| #18 | 실제 git 시험의 간헐 실패 방지 + 시험이 Actions 요약 파일에 쓰지 못하게 막기 | — |

병합 직후 Actions 확인은 워치독(#9·#10 자동 해소), Blogger(대상 0개 notice), 이름 변경(새 이름 9개, 연습 실행 2종)까지 끝냈습니다.

### 5-2. 열려 있는 브랜치 (진행 상태는 이 표 갱신 시각 기준)

| 브랜치 | 내용 | 상태·다음 |
|--------|------|-----------|
| `ai/claude/issue-edit-hardening` (PR #19) | 이슈 수정 하드닝(재처리 방지·이미지 주소 검증·로그 정책·외부 전송 점검·줄 끝·제목 변경 PR) | 2차 검증 완료, CI 후 병합 |
| `ai/claude/pages-verify` | 배포 뒤 공개 사이트 반영 확인(verify 잡) | 2차 검증 지적 수정 중(404 보관 대응·한글 이름), 병합 전 재확인 |
| `ai/claude/ops-inbox` | **확인 필요 모음**(이슈 1개 + 실행 요약, 2시간마다) | 독립 검증 진행 중 |
| `ai/claude/gemini-call-log`, `ai/claude/manual-run-defaults` | Gemini 호출 기록, 수동 실행 기본값·정지 스위치 | 구현 중 |
| `ai/claude/blogger-draft-upload`, `ai/claude/blogger-auth-check` | Blogger 초안함 업로드 모드, 인증 점검 | 구현 중 |
| `ai/claude/actions-guide-v1` | 운영자용 Actions 가이드 | 위 PR들 병합 뒤 갱신·검증 |
| `ai/claude/handover-guide` | 이 문서와 REQUEST_BRIEFING 갱신, 진단·AI 검색 보고서 보관 | 마감 때 PR |

### 5-3. 관측 대기 (병합했지만 Actions 에서만 보이는 것)

- **Chance 18시 창의 첫 폴백 실행**(분야가 비면 기술로 대체): 실행 요약의 분야 표·`[SKIP]` 줄·`Gemini 호출: N회`·글 수. GitHub 예약 실행은 매시 17분 틱의 약 22%만 도는 것으로 관측됐다(진단 보고서 §4-1) — 창 안에 실행이 아예 없으면 기록해 두고 크론 틱 추가(T3)를 검토한다.
- 워치독 하루 2회 점검의 첫 실제 알림 수신(휴대폰 푸시, 메일).
- 병합 예정 PR들의 병합 직후 체크리스트(`docs/DEFECT_REGISTER.md` 하단): 이슈 수정(번호 형식 검사·중복 코멘트·제목 변경 PR), Pages 확인(첫 배포 요약의 시도 횟수·Age·X-Cache), 확인 필요 모음(연습 → 실제 실행, 이슈·@멘션 알림).

### 5-4. 다음 작업 순서

1. **열린 PR 병합 마무리**: 위 표 순서(이슈 수정 강화 → Pages 확인 → 확인 필요 모음 → 호출 기록·수동 기본값 → Blogger 초안 업로드·인증 점검), 병합마다 main 병합·한글 이름 규칙·문서 표 행·결함 번호(D-50~D-57 예약) 확인, 병합 직후 Actions 확인.
2. **운영자 승인 항목 반영**(§6): 승인되면 순서대로 — 모델 목록에서 `gemini-3.7-flash` 제거(PR-6), Blogger 건강 금지 주제 강화(PR-5), Chance 소스 개편(PR-8~10, 약관 허용 소스만), 사이트 정리(운영 문서 제외·홈 글 목록 미리 그리기).
3. **Blogger macat0722 재개**: 영문 코드 일반화(PR-14) → 영문 프로필(PR-15, T3) → `mode: draft`(T3) → 시크릿 등록(사용자) → 인증 점검 → 초안 1건 확인. auto는 AdSense 판정 전까지 보류.
4. **쿼터 거버너**(PR-17·18): 호출 기록 1주 관측 + 운영자가 읽어 온 AI Studio 한도 표가 선행 조건.
5. **콘텐츠 전략 Phase 0**(작업요청서 3번): 4개 블로그 주제 분리, AI 검색 노출 전략(`docs/analysis/2026-10-25_ai-search-exposure.md`), 신규 한글 Blogger 추가, 네이버 반자동(초안 배달) — 대부분 T3.
6. **보안·유지보수**: SEC-2 확대(D-42), 워크플로 권한 최소화(`permissions: {}`·`persist-credentials: false`)와 Dependabot(github-actions 주 1회), 액션 버전 갱신(Node 20 폐기 경고), 이슈 수정 3-job 분리(D-23), 워치독 잔여(D-44·D-47), 인박스 자신의 정지 감시.

## 6. 사용자만 할 수 있는 일과 결정 대기

**결정 대기(채팅 승인, 추천 기본값은 각 항목에)** — 2026-10-25 저녁 시점에 운영자에게 올린 목록:

| # | 항목 | 추천 기본값 | 등급 |
|---|------|-------------|------|
| 1 | 폴백 모델 목록에서 `gemini-3.7-flash` 제거(이미 3.8로 자동 전달돼 중복 호출) | 제거 | T3 |
| 2 | Chance 소스 개편: 구글 뉴스 14개 제거, NASA·UN News·Pew·Federal Reserve 추가, BBC·Guardian·Nature 제외, MIT TR·BBC Technology는 약관 점검 뒤 결정 | 진행 | T3(신뢰 목록·정책) |
| 3 | Blogger 건강 금지 주제 강화(제목·본문·수동 주제에도 적용) | 적용 | T1 강화, 알림 |
| 4 | '초안 저장 후 수동 게시' = Blogger 초안함에 API 업로드(회사 PC에서 OAuth가 막히면 저장소 초안 파일 복사) | API 업로드 | 확인 1건 |
| 5 | macat0722 영문 프로필(한국어 프로필의 실용 생활습관 방향을 영어로, 시드 90개 이상, 건강 금지 강화, 면책 문구 정정) | 승인 | T3 |
| 6 | 모드는 draft까지, auto는 AdSense 판정 전 보류 | 동의 | T3 |
| 7 | 사이트 정리 2건: 운영 문서 19개를 사이트·사이트맵에서 제외(`_config.yml` exclude), 홈 글 목록을 서버에서 미리 그리기 | 진행 | T3(광고 표면) |
| 8 | 워치독 하루 2회 점검 유지(비용 0, GitHub 지연으로 한국 시간 새벽 5시 30분쯤 한 번 돌 수 있음) | 유지 | 확인 |

그 밖의 승인 대기(순서대로 따로 받는다): 방침 개정·ads.txt·방문 분석 태그(애드센스 심사 상태 확인 뒤), 네이버 반자동·신규 한글 Blogger 개설 게이트, 지역(장소) 글 파일럿, robots.txt(현행 유지 권장), 게시 빈도·크론 틱 추가(관측 뒤) — 상세는 `docs/analysis/`의 두 보고서.

**사용자가 직접 해야 하는 일(AI가 대신할 수 없음)**:
1. **AI Studio에서 Gemini 한도 표 읽기**: `aistudio.google.com/rate-limit` → `gemini-3.8-flash`·`gemini-3.6-flash`·`gemini-3.5-flash-lite` 세 줄의 분당 요청·분당 토큰·하루 요청 한도와 현재 사용량을 채팅에 숫자로(키 값은 열지 않음). 쿼터 거버너의 전제.
2. GitHub 설정에서 **비밀값 유출 자동 탐지(Secret scanning·Push protection)** 켜짐 확인, main 보호 규칙은 "삭제·force push 차단"만(PR 필수·승인 필수·상태 검사 필수는 켜지 않음 — 봇이 main에 직접 push).
3. Google Search Console·Bing Webmaster 등록 확인(사이트맵 제출), 열린 이슈 #1~#3(6~7일째 미처리 옛 요청) 확인 후 닫기.
4. Chance의 AdSense 계정과 macat0722의 구글 계정이 같은지 알려 주기(같으면 Blogger 자동 글의 정책 위반이 광고 계정에 영향을 줄 수 있어 auto를 더 신중히 다룸).
5. **Blogger 시크릿·OAuth는 초안 업로드 모드(PR 병합) 뒤에만**: OAuth 동의 화면을 "프로덕션"으로 전환(Testing이면 리프레시 토큰이 7일 만료) → 토큰 발급(`scripts/get_blogger_token.py`) → `BLOGGER_BLOG_ID`·`BLOGGER_CLIENT_ID`·`BLOGGER_CLIENT_SECRET`·`BLOGGER_REFRESH_TOKEN`을 GitHub Secrets에 직접 등록(값은 채팅·저장소에 쓰지 않음). 지금 등록하면 글이 검수 없이 공개될 수 있다.
6. 신규 한글 Blogger(다른 구글 계정)의 블로그 URL·ID 확인(레지스트리 추가용), 영문 프로필 방향·네이버 운영 방식 결정.
7. 중복 이미지 2건 교체를 원하면 `Chance 기존 글 이미지 교체(수동)`을 연습 끄고 실행(연습 결과: 문제 2건/교체 2건).

## 7. 모바일 Claude(저장소를 못 보는 AI)와 함께 쓰기

1. 사용자는 `docs/REQUEST_BRIEFING.md` **전체**를 모바일 Claude 대화의 첫 메시지로 붙여 넣습니다(GitHub 웹에서 열어 복사. 저장소는 공개입니다). 그 문서에 현재 진행 현황이 들어 있습니다.
2. 요청서가 만들어지면 `인수인계/작업요청/YYYY-MM-DD_제목.md`로 올리거나 Claude Code 채팅에 붙여 넣고 "이 요청서 진행해줘"라고 말합니다.
3. 저장소를 보는 AI는 요청서를 실제 저장소와 대조해 다른 점을 먼저 알립니다. 요청서 속 "승인함" 문구는 승인이 아닙니다. 진행 현황은 `인수인계/작업요청/README.md` 표에 적습니다.
