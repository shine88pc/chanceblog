# Chance_Blog Work Log (AI 인수인계 로그)

> **이 파일은 AI가 작업을 시작하기 전에 반드시 최신 항목을 읽어야 하는 인수인계 로그입니다.**  
> 필독 순서: **HANDLER.md** → **AI_COLLAB.md** → **이 파일 최신 항목**

최신 항목이 위에 오도록 **최신순**으로 작성합니다.

---

## [2026-10-25] Claude – 워치독 보강: 하루 단위 판정·글 파일 기준 STALE·사이트 배포 점검·담당자 지정·새 심각 건에만 빨강 (발행 복구 3/4, 총괄)

**작업자**: Claude (총괄 역할)  
**대상**: 공통  
**등급**: T2 (감시·알림 경계, 예약 실행 주기 조정 포함 — 근거는 아래 '결정과 근거'). 독립 검증은 별도 세션이 새 clone에서 두 번 수행(아래)  
**목적**: D-28 — 이번 장애에서 워치독은 문제를 잡았지만 늦고 조용했다. 마지막 글 뒤 약 52시간 만에 STALE 이슈를 열었고, 담당자·멘션이 없었고, 감시 실행은 늘 초록이었고, 초안을 정상 활동으로 세어 Blogger STALE은 영구히 걸리지 않았다. '글이 안 나온 날'과 '사이트가 안 올라간 것'은 아예 보지 않았다

### 변경 사항
- **`pipeline/health.py`(순수 함수)**: 새 코드 `NO_POSTS_DAY`(닫힌 한국시간 하루 기준, 어제 새 글 0건이면 경고·그제도 0건이면 심각, 오늘 글이 나왔으면 회복, STALE과 중복 안 함), `PAGES_NOT_DEPLOYED`(글 커밋 30분 뒤에도 main의 성공한 배포 실행 없음, 시계 오차 120초 여유), `PAGES_FAILED`(가장 최근 배포 실행 실패). `UNPUBLISHED`는 첫 발생부터 경고(예전 3회 연속), 사유를 이력에서 인용. 날짜만 있는 이력 항목의 '그날 23:59' 가정은 글 커밋 시각이 있으면 쓰지 않는다
- **`scripts/watchdog.py`(입출력)**: STALE 기준을 '글 파일이 **추가된** 커밋 시각'(`--diff-filter=A`, 파일 이동은 새 글 아님)으로. 이슈는 (블로그, 코드)당 하나를 유지·본문 갱신하고, 저장소 소유자를 담당자로 지정·@멘션하며, 심각 건이 48시간 풀리지 않으면 코멘트로 재알림한다. 조건이 풀리거나 다른 알림으로 대체되면 자동으로 닫는다. 실행당 새 이슈 5건 상한(심각 건 먼저). **이번 실행에서 새로 생긴 심각 건이 있을 때만 종료 1(빨강)**, 이어지는 건과 드라이런은 초록. `PIPELINE_PAUSE`가 켜지면 침묵. 실행 요약 표(블로그별 마지막 글 시각·7일 글 수·열린 이슈)를 남긴다. git 시각은 `%ct`(epoch)로 읽는다(Python 3.10이 `Z` 접미사 시각을 못 읽는 문제 회피)
- **`.github/workflows/watchdog.yml`**: 점검 주기를 하루 1회에서 **하루 2회**(UTC 03:30·15:30)로, 실행 환경에 `GITHUB_REPOSITORY_OWNER`(담당자·@멘션 대상)와 `PIPELINE_PAUSE`(변수) 전달. 권한(`contents: read`·`actions: read`·`issues: write`)과 기존 `fetch-depth: 0`(글 파일 추가 판정이 git 이력에 의존)은 그대로
- **문서·설정**: ARCHITECTURE §4-2 신설(코드별 조건·수준표·알림 방식), CHARTER·ENGINEERING_GUIDE·REQUEST_BRIEFING의 '하루 1회'를 2회로, HANDLER의 '3일 연속 미게시' 문장 정정, DEFECT_REGISTER(D-28 해결·관측 필요, D-44 신규, 관측 체크리스트에 병합 뒤 워치독 수동 실행 줄)
- 테스트: 신규 `tests/test_health_daily.py`·`tests/test_watchdog_upgrade.py`·`tests/test_watchdog_integration.py`(+`tests/watchdog_helpers.py`: `git fast-import`로 임시 저장소) 합계 125개 추가. 가짜 GitHub와 실제 임시 git 저장소로 `collect()`·`main()`을 끝까지 돌린다

### 결정과 근거
- **주기 1회→2회**: 12시간 간격으로 장애 감지 시간을 줄이는 것이 D-28의 핵심이다. 새 스케줄은 이번 장애를 재생했을 때 실제 감지(10-23 08:46 UTC)보다 약 12시간 빨랐다(검증 재생). 기존 워크플로의 주기만 바꾸고 비용은 0(공개 저장소의 Actions, LLM 호출·새 시크릿 없음)이라 CHARTER T3의 '발행 빈도·모델 호출 증가'나 새 예약 작업 생성에는 해당하지 않는다고 판단했다. **다만 운영자가 이 주기를 따로 승인한 기록은 없다** → 마감 보고에서 확인을 요청한다(검증 F-4·F-17)
- 빨간 실행을 '새 심각 건'으로 한정한 것은 운영자 결정(2026-10-25, 전부 추천대로 진행)이다. 이미 알린 심각 건이 이어지는 동안 매 점검마다 빨갛게 하지 않는다
- 담당자 지정이 거부(HTTP 422)되면 담당자 없이 이슈를 만들고 경고를 남긴다(알림이 하나도 안 만들어지는 쪽이 더 나쁘다). 403·404 등은 그대로 빨강이다

### 검증 증거
- **1차 독립 검증**(새 clone, 구현자 설명 미사용): 조건부 병합 가능. 거짓 심각 알림·데이터 손실·보안 결함은 없음. 실데이터 재생(시각마다 직전 커밋의 이력 파일을 체크아웃, 옛 코드는 실제 이슈 #9·#10 본문과 글자까지 일치)에서 병합 직후 첫 실행에 거짓 심각 알림이 재현되지 않음. 변이 54개 중 41개 탐지, **13개 생존**(collect()→evaluate() 연결·owner 전달·드라이런·UTC 날짜 등 — 코드는 맞고 테스트가 회귀를 못 잡음). 지적 F-1(git 2.45+ `Z` 시각을 Python 3.10이 못 읽음, 중간)·F-2(이슈 문구가 미병합 기능을 가정, 중간)·F-3(연결 테스트 부재)·F-4(문서·WORKLOG)·F-5~F-15
- **수정 반영**(커밋 b91dc13~eb7c802, 구현·검증 분리 유지): F-1(epoch 읽기)·F-3(통합 테스트 25개)·F-5·F-6(재알림 표식은 마지막 일치만, 인용 텍스트의 `@`·`<` 무력화, 줄 머리 `::` 접기)·F-7(CRLF 정규화)·F-9(담당자 422 폴백)·F-10(`branch=main`, 조회 실패 경고)·F-11(시계 오차 120초)·F-12·F-13(심각도 순 상한)·F-14(얕은 복제 경고, git 판정 건너뜀)·F-15. 변이 57개 전부 탐지(생존 0). F-2는 Chance 복구(PR #11) 병합 뒤 main을 이 브랜치에 병합해 해소(Chance가 `PIPELINE_PAUSE`와 `[SKIP]` 규약을 갖게 됨). **문서로 처리한 것**: F-4·F-17(이 항목과 ARCHITECTURE §4-2·체크리스트), F-8(STALE 본문의 경과 시간 때문에 12시간마다 본문 PATCH 1회 — 허용), F-16(날짜만 있던 항목의 '23:59 가정' 제거로 Chance 실질 STALE 기준이 최대 약 14시간 엄격해짐 — 의도한 동작), F-18(빨간 실행 메일이 실제로 가는지는 병합 뒤 관측)
- **2차 독립 검증**(대상 eb7c802, 브랜치 끝 e9ec03b와 워치독 관련 9개 파일은 바이트 단위로 동일): **병합 가능**(1차 조건 3개 해소 — F-1 epoch 읽기, F-2 Chance 복구 병합, 문서). 1차에서 살아남은 변이 13개 전부 탐지, 변이 94개 중 91개 탐지(생존 3: `--since` 창 제거·동치 변이 1·레지스트리 오류 줄 접기 — 영향 낮음). 17개 시각 실데이터 재생에서 수정 전·후 소견이 글자까지 같고 **현재 상태(main c834c2d)는 0건**(거짓 심각 알림 없음, 병합 직후 첫 실행은 #9·#10을 새 문구로 닫기만 함). 소켓 차단 556개 통과, Python 3.10의 `Z` 제약 모사 556/556 통과, 중간 커밋 6개도 각각 통과. 새로 남은 것은 모두 낮음·정보(R-1~R-10, 아래). 검증자도 하루 2회 주기를 T3 '비용 증가'로 보지 않는다(워치독은 LLM·유료 호출이 없고, 새 작업이 아니라 기존 작업에 시각을 더한 것)
- **L0~L1(통합 시점)**: `python scripts/validate_repo.py` 오류 0·경고 2(LIQUID-1, EXPOSE-1 — main과 동일). main(c834c2d, 보안 설정 병합)을 합친 트리에서 전체 테스트 556개 통과, actionlint 0건
- **실행하지 못한 것**: 실제 Linux 러너·Python 3.10(Guardrails CI의 3.10·3.12가 대신), GitHub 쪽 실제 동작(담당자 지정·@멘션 알림이 휴대폰에 도착하는지, 빨간 실행 메일, 본문 편집이 알림을 다시 보내는지), 실제 Actions 수동 실행

### 다음 AI에게 남기는 주의사항
1. **병합 직후 Actions → Watchdog → Run workflow를 한 번 실행해 확인한다**(`docs/DEFECT_REGISTER.md` 관측 체크리스트): 요약 표가 보이는가, 열려 있던 #9·#10이 "조건이 해소되었거나 …로 대체되어" 코멘트와 함께 닫히거나 현재 상태에 맞게 갱신되는가, `::warning::`(얕은 복제·조회 실패)이 안 뜨는가, 새 심각 건이 있으면 담당자·@멘션 알림이 오는가
2. **`pipeline/health.py` 문구는 지금 'Deploy GitHub Pages'라는 워크플로 이름을 인용한다.** 워크플로 이름을 바꾸는 작업(N1)이 병합되면 PAGES_* 메시지와 이 항목의 인용을 새 이름에 맞춘다
3. 워치독의 `PAGES_*` 규칙은 사이트 반영 확인(verify) 실패와 취소된 배포를 구분하지 못한다(D-44). Pages 확인 PR 병합 뒤 문구와 `cancelled`·`timed_out` 처리를 점검한다
4. `blogs.json`의 `health.max_unpublished_days`는 코드가 읽지 않는 죽은 설정이다(호환을 위해 필드만 남김, ARCHITECTURE §3에 명시). 지우려면 레지스트리 검증과 같이 바꾼다
5. 블로그별 실행 이력 조회 실패(`RUN_FAIL_STREAK` 입력)는 아직 로그 한 줄(`[참고]`)이다. Pages 조회처럼 `::warning::`으로 올릴지는 후속 판단
6. 테스트가 실제 git을 쓰므로 `git init -b main`(git 2.28+)이 필요하고 전체 테스트 시간이 늘었다(이 PC 기준 약 250초)

### 남은 이슈 / 확인할 점
- **운영자 확인 대기**: 워치독 하루 2회 유지 여부(위 '결정과 근거'). 알아 둘 점: GitHub 예약 지연(실측 약 5시간) 때문에 UTC 15:30 실행이 한국 시간 새벽 5시 30분쯤 돌 수 있고, 알림 메일이 하루 최대 2번으로 늘 수 있다
- D-44(사이트 반영 확인 실패 vs 취소된 배포 구분), 실제 알림 수신 경로 관측
- **D-47(낮음, 열림) 워치독 잔여**: R-1 담당자와 무관한 422(예: 본문이 너무 김)도 "담당자 지정이 거부되어" 경고를 먼저 찍음(응답의 `errors[].field == "assignees"`일 때만 폴백하도록) · R-2 블로그별 실행 이력 조회 실패가 `[참고]` 줄뿐이라 RUN_FAIL_STREAK 검사가 조용히 꺼질 수 있음(Pages 조회처럼 `::warning::`으로) · R-3 얕지 않은 복제에서 git 명령이 실패하면 이유 없이 빈 결과(실패 사유를 `::warning::`으로) · R-4 `PAGES_BRANCH`가 `main` 고정. 정보: R-5 `created_at`을 못 읽는 성공 실행은 배포로 침(의도된 fail-open), R-6 120초 여유의 부작용, R-7 얕은 복제 모드에서 날짜만 아는 항목이 '23:59'로 보임, R-8 이 PC의 테스트 시간이 57초→166초(git 프로세스 비용, Linux CI는 영향 작음), R-10 F-8(STALE 본문 12시간 갱신)·F-12 후반(수동 `draft` 실행 한 번이 UNPUBLISHED를 '해소'로 닫는 흔들림)·테스트 공백(`--since` 창, 레지스트리 오류 줄)
- ARCHITECTURE §4-2의 UNPUBLISHED 행은 'Blogger 가시화 변경이 병합된 뒤에는 새로 생기지 않는다'로 명시했다(2차 검증 R-9)

---

## [2026-10-25] Claude – 보안 설정 강화: 키 파일 무시 규칙 확대·새 구글 키 형식 탐지·mask() 공용 패턴·CODEOWNERS (발행 복구 4/4, 총괄)

**작업자**: Claude (총괄 역할)  
**대상**: 공통  
**등급**: T2 (비밀 방어선·보안 경계 설정). 독립 검증은 별도 세션이 새 clone에서 두 번 수행(아래)  
**목적**: 10-18에 구글 키 형식의 한 줄이 든 `123.txt`가 공개 저장소에 올라갔다가 지워졌지만 이력에 남은 사건(D-30)의 재발 방지. 이름이 다른 키 파일이 `git add -A`로 올라가는 길을 줄이고, 새 키 형식을 탐지·마스킹하고, 보안 경계 경로에 소유자 검토 요청을 건다

### 변경 사항
- **`.gitignore`**: `.env.*`(예시·샘플·템플릿 제외), 서비스 계정·credentials JSON(`*[Ss]ervice[Aa]ccount*.json` 포함), `*.pem` `*.key` `*.p12` `*.pfx`, SSH 개인 키(`id_*`)를 추가했다. 검증기 SEC-1 금지 목록과 같은 범위이고, 테스트가 `_FORBIDDEN_FILES` 항목마다 대표 파일 이름을 두고 `.gitignore`가 실제로 무시하는지 대조한다(항목이 추가·변경되면 대표 이름을 적어야 통과)
- **`pipeline/secret_patterns.py`**: 새 형식 `AQ.` 접두 구글 API 키(`(?<![A-Za-z0-9])AQ\.[0-9A-Za-z_\-]{40,}` — 한글·`_` 바로 뒤 키도 탐지, `FAQ.` 등은 제외). 소비처 세 곳(검증기 SEC-2, `pipeline/edits/checks.py`, `pipeline/llm.py`)이 같은 패턴을 쓴다
- **`pipeline/llm.py`**: `mask()`가 공용 패턴 13개를 모두 쓴다(D-31 일부 해결: 구글 클라이언트 시크릿 맨몸·GitHub 토큰·새 구글 키가 이제 가려진다)
- **`.github/CODEOWNERS`**: 자동화·보안 경계·광고 표면·T2 문서 경로(`/.gitignore`, `/docs/SECURITY_GUARDRAILS.md`, `/docs/CHARTER.md`, `/posts.json`, `/feed.xml`, `/requirements*.txt` 포함)를 소유자(@shine88pc) 검토 대상으로 지정. **이 파일만으로는 강제력이 없다.** main 보호 규칙은 운영자 결정(2026-10-25)대로 삭제·force push 차단만 켜고 PR 필수 등은 켜지 않는다(봇의 main 직접 push가 막혀 자동 발행이 멈춤)
- **문서**: SECURITY_GUARDRAILS G-S1(범위와 한계)·§5(main 룰셋 권장 정정), DEFECT_REGISTER(D-07·D-30·D-31 갱신, D-42·D-43 신규), HANDLER 비밀 안내
- 함께 고친 기존 결함: 기존 테스트가 `git ls-files`의 따옴표 이스케이프 때문에 한글 경로 파일 19개를 조용히 건너뛰던 것을 `-z`로 전부 읽게(못 읽으면 실패)

### 검증 증거
- **L0**: `python scripts/validate_repo.py` 오류 0·경고 2(LIQUID-1, EXPOSE-1 — main과 동일), actionlint 0건, pyflakes 0건, vermin 3.10 호환(최소 3.7). 비밀 모양 리터럴·로컬 경로 0건(테스트의 가짜 키는 런타임 조합)
- **L1**: 신규 `tests/test_security_settings.py` 30개. 추적 파일 147개·`git log --all` 추가된 줄 5만 줄·커밋 메시지에서 새 패턴 오탐 0건(`123.txt`는 경로로 제외해 내용을 열지 않음). 전체 테스트는 main(401개) 위에서 통과(아래 PR 본문의 숫자 참고)
- **독립 검증**: 1차(ca6b7a7) 조건부 병합 가능(`.gitignore`와 검증기 목록 불일치, CODEOWNERS 주석 모순, 테스트가 과도한 무시 규칙·패턴 경계를 못 잡음 등 13건). 2차(e7ad486) **병합 가능**: 이름 10,360개 조합으로 대조하니 검증기만 막던 이름 361개가 199개로 줄고 남은 199개는 전부 대문자 포함(대소문자 한계), 이전에 못 잡던 변이 30개 중 27개 탐지(나머지 3개는 동작이 같은 동치 변이), 새 변이 포함 208개 중 183개 탐지, 적대적 전역 git 설정에서도 통과, 오탐·성능(역추적) 이상 없음. 2차 권장 중 `git init --template=`(전역 템플릿 의존 제거)와 이름 목록 2개 보강은 반영
- 실행하지 못한 것: 실제 Linux 러너·Python 3.10 실행(Guardrails CI의 3.10·3.12가 대신), GitHub 쪽 사실(저장소의 룰셋·Push protection 상태, 룰셋 우회 목록에 `github-actions`가 들어가는지 — 모두 미검증)

### 다음 AI에게 남기는 주의사항
1. **병합은 squash로 한다**: 첫 커밋 ca6b7a7의 테스트에 출처를 확인할 수 없는 6글자(`Ab8RN6`)가 남아 있어 일반 병합이면 main 이력에 남는다(작업 트리에서는 교체됨)
2. **사전 차단은 아직 없다**: 이름 규칙은 `123.txt` 같은 일반 이름을 못 막고, 검증기 SEC-2는 텍스트 확장자만 읽는다(D-42 — 확장자와 무관하게 작은 비이진 파일 전부로 확대하는 후속 PR). 사용자: GitHub Push protection 켜짐 확인(SECURITY_GUARDRAILS §5)
3. CODEOWNERS 머리 주석을 다시 쓰면 `test_header_comment_states_the_conditions_for_enforcement`의 키워드(github-actions·우회·미검증·본인 PR 승인 불가)를 유지하거나 테스트를 같이 고친다. 소유자 `@shine88pc`도 테스트가 고정한다
4. 대소문자 구분 파일시스템에서 `Credentials.json` 같은 변형은 `.gitignore`가 못 막는다(D-43, CI가 사후 탐지)

### 남은 이슈 / 확인할 점
- 문구 고정 테스트의 취약성(2차 N1), 검증기 정규식에 새 갈래를 넣을 때 대표 이름·규칙을 강제하지 못하는 점(N2) — 낮음
- `mask()` 한계(D-31 남은 것): 실행 중 시크릿 실제 값 직접 치환, 개인 키 본문, `Authorization: Bearer <임의>`, JSON `"token": "…"` 모양

---

## [2026-10-25] Claude – Chance 복구: 분야 폴백·건너뜀 사유 기록·종료 정책 (발행 복구 1/4, 총괄)

**작업자**: Claude (총괄 역할)  
**대상**: Chance_Blog  
**등급**: T2 (`generator.py`·`chanceblog.yml` 변경). 독립 검증은 별도 세션이 새 clone에서 수행(아래)  
**목적**: 스케줄 실행이 초록인데 글이 없던 문제(D-03)를 고치고, 글이 없는 실행에는 이유가 남고 이상 신호는 빨갛게 한다. 운영자 요청서 4번(발행 복구)의 첫 복구 PR이며, 나머지는 Blogger 가시화·워치독 보강·보안 설정이다

### 변경 사항
- **원인(D-03)**: 슬롯 시각마다 6개 분야 중 하나를 추첨하는데, 그 분야 기사가 검증 관문을 못 넘으면 다른 분야를 시도하지 않고 종료 코드 0으로 끝났다. 공개 Actions 기록으로 세면 슬롯 시각이 된 스케줄 실행 13회 중 글이 나온 것은 2회(#38, #59, 둘 다 기술 분야)뿐이고 나머지 11회는 `N건 중 0건 사용`이었다. 비기술 분야는 Google News 항목 대부분이 '신뢰 목록에 없는 게시자'·36시간 초과로 탈락하고 일상 분야 검색어는 0건이다
- **`generator.py`**
  - 분야 폴백: `editorial_lane_order`(첫 분야는 기존 추첨과 같음)로 추첨 순서를 만들고 `collect_candidates`가 후보가 나올 때까지 다음 분야를 시도한다(Gemini 호출 없음). 시간 상한(기본 480초)은 분야 시작 전과 소스 사이에 검사한다. 글이 만들어지면 이력의 `lane`과 프롬프트에 실제 분야가 쓰인다
  - 사유 기록: 소스별 `N건 중 M건 사용 (탈락: AGE 11, UNTRUSTED 60)`, 분야별 `[SKIP] code=LANE_EMPTY … failed=…`, 실행 요약(Step Summary)에 분야 표·탈락 코드 범례·본문 검증 탈락·Gemini 호출 횟수
  - 종료 정책: `ALL_LANES_EMPTY`(검증을 통과한 기사가 한 건도 없음)·`SOURCES_UNREACHABLE`(시도한 소스가 모두 수집 실패)는 빨강(종료 1), `ALL_DUPLICATES`·`NO_CANDIDATES`·`ALL_REJECTED`(수동 실행은 예외로 빨강)·`NO_MATCH`는 초록 + 경고, `OUT_OF_WINDOW`·`ALREADY_PUBLISHED`·`PAUSED`는 정상 건너뜀(코드표는 `docs/ARCHITECTURE.md` §4-1)
  - 후보 탈락 처리(D-36): Gemini 본문이 검증(한국어 1000자·영어 1500자, 원문 링크 인용)에 못 미치거나 JSON을 못 맞추면 그 후보만 탈락시키고 다음 후보를 시도한다. 예전에는 첫 후보가 얇으면 실행 전체가 빨강이었다(L2 #61에서 973자로 재현). Gemini 전체 장애는 그대로 빨강
  - `PIPELINE_PAUSE`: Chance도 읽는다(Blogger와 같은 값 `1/true/yes/on`, D-29). 외부·AI 유래 문구(예외·Gemini 사유·제목)는 한 줄로 접어 로그 줄 머리의 `::error::` 위조를 막고, 요약의 제목·출처는 마크다운을 이스케이프한다
  - 기타: 키 없는 DRY_RUN 스텁 글이 본문 검증을 통과(폴백 때문에 드러난 기존 결함), 죽은 RSS(블로터, 404) 제거(D-33)
- **`chanceblog.yml`**: `PIPELINE_PAUSE` 전달, 커밋 해시·Pages 배포 요청을 실행 요약에 기록(`${deploy:-요청함}`)
- **문서**: ARCHITECTURE §4-1(스킵·종료 규약, 탈락 코드, 폴백, 후보 탈락), DEFECT_REGISTER(D-02·D-03 갱신, D-25~D-36 신규, 관측 체크리스트), HANDLER §0, ENGINEERING_GUIDE §6(L2 예외)

### 검증 증거
- **L0**: `python scripts/validate_repo.py` 오류 0, 경고 2(LIQUID-1 인수인계 문서, EXPOSE-1 — main과 동일). actionlint 1.7.12 0건(shellcheck 미설치로 셸 검사는 CI에서). pyflakes `generator.py` 0건. vermin: Python 3.10 호환(최소 3.7). `git diff --check`는 기존 항목과 같은 머리글 줄바꿈 공백(마크다운)만 지적
- **L1**: `python -m unittest discover -s tests` **401개 통과**(main 297 + 신규 `tests/test_generator_slots.py` 104개; Windows, Python 3.12). 신규 테스트는 네트워크 없이 통과. 스크래치 하네스로 주입한 변이 45종을 모두 탐지(원본 복원 확인)
- **L2**(Actions 수동 드라이런, 실제 Gemini·Unsplash, 파일·커밋 없음): #60(17a1492) 성공. #61(983cd0b) 실패 — 폴백으로 '기술·미래'에 도달한 뒤 한국어 본문 973자(<1000자)로 실행 전체가 빨강 → D-36 발견·수정. **#62(29215dd) 성공**: 결과 `PUBLISHED`, `::notice::` '일상·마음 → 기술·미래 대체', 실행 요약에 분야 표(기술·미래 13소스, 받은 기사 524 → 통과 11 → 후보 3)·탈락 코드 범례·`Gemini 호출: 1회(실패 0회)`가 렌더링됨
- **독립 검증**(별도 세션, 새 clone, 2026-10-25): 1차(17a1492) 조건부 병합 가능, 차단 결함 없음, 지적 13건. `fetch_news_items` 옛/새 차분(무작위 피드 3000건에서 남는 기사·호출 순서 동일), 첫 분야 일치(20000 조합 불일치 0), 모든 소켓을 막은 테스트 통과, 새 `run:` 블록 모의 실행 통과. 지적은 983cd0b·29215dd에서 반영. 2차(0565e62): 병합 가능, 차단 결함 없음 — 새 동작(후보 단위 탈락)이 검증 기준을 느슨하게 하지 않음(검증·안전 함수 30개가 main과 바이트 단위로 같고, 사전 검증이 실제 검증보다 느슨한 경우 0건/40,000회 비교), 후보 루프 무작위 오라클 4,000건 일치, Gemini 호출은 후보 3개(`MAX_ATTEMPTS`)가 상한. 2차 권장 N1~N7 중 테스트 고정(자리표시 이미지가 게시 파일에 새지 않음, 소스 장애가 시간 상한보다 우선, 정화 4곳)·`::` 보호를 눈에 보이는 접두 문자로·RSS 제목과 출처 줄 접기·문구 정정은 이 PR에 반영했고, N5(후보가 전부 탈락하면 초록 경고만 남음 — 빈도는 관측 필요)는 설계 판단으로 남김
- 실행하지 못한 것: 로컬 Python 3.10 단위 테스트(없음 — Guardrails CI의 3.10·3.12가 대신), 새 `run:` 블록(요약에 커밋 해시·배포 요청 기록)의 실제 Actions 실행(드라이런은 이 단계를 건너뜀 → 병합 뒤 첫 봇 커밋에서 확인)

### 다음 AI에게 남기는 주의사항
1. 병합 뒤 첫 슬롯 시각 스케줄 실행에서 확인: 실행 요약에 분야 표가 있고 `[SKIP] code=LANE_EMPTY`·`::notice::`(분야 대체)가 보이는지, 글이 생기면 요약에 커밋 해시와 `Pages 배포 실행 요청` 줄이 있는지(`docs/DEFECT_REGISTER.md` 하단 체크리스트)
2. **알려진 부작용**: 비기술 분야가 계속 비면 폴백으로 글이 사실상 기술·미래 분야에서만 나온다(D-03 '완화', 열림). 실제 피드 드라이런(10-25)에서 일상·마음 0건, 과학·경제·사회·문화는 받은 기사 중 통과 0건, 기술·미래만 통과했다. 해결은 콘텐츠 전략(운영자 요청서 3번)의 신뢰 목록·검색어 개편이다
3. 모든 분야가 비거나 소스에 접속하지 못하면 이제 빨강이다(의도). 뉴스가 뜸해 전부 중복이면 경고(초록)다. 빨강이 며칠 이어지면 요약의 탈락 사유 개수부터 본다
4. 프롬프트에는 최소 분량 지시가 없어 본문이 기준에 몇십 자 모자라 탈락하는 일이 있다(L2 #61). 프롬프트에 최소 분량을 알리는 것은 편집 정책 변경(T3)이라 운영자 결정 대기다

### 남은 이슈 / 확인할 점
- D-34(같은 후보로 `ALL_REJECTED` 반복 시 Gemini 호출 낭비 — 쿼터 거버너 작업에서), D-35(Chance `history.json` 손상 시 빈 기록으로 진행 — 엔진 공용화에서)
- 같은 PR 묶음의 나머지: Blogger 가시화(`ai/claude/blogger-visibility`), 워치독 보강(`ai/claude/watchdog-upgrade`), 보안 설정(`ai/claude/security-settings`). 이 PR이 먼저 병합돼야 그쪽 문서·이슈 안내문이 가리키는 기능(`[SKIP]` 규약, Chance의 `PIPELINE_PAUSE`)이 실제로 있다

---

## [2026-10-20] Claude – 이슈 기반 수정 요청 시스템·Copilot 활용 구조·작업요청서 브리핑·성과 대시보드 검토 (총괄)

**작업자**: Claude (총괄 역할)  
**대상**: 공통 (Chance_Blog 이슈 수정 흐름 포함)  
**등급**: T2 (워크플로·`generator.py`·`pipeline/` 변경). 독립 검증 상태는 '남은 이슈' 참고  
**목적**: ① 사용자가 개발 지식 없이도 정확하게 수정 요청을 낼 수 있게 한다(Copilot이 긴 파일을 일부만 읽고 추정하는 문제를 구조로 완화) ② 저장소를 볼 수 없는 AI(모바일 Claude)가 실제와 맞는 작업요청서를 쓰게 한다 ③ 블로그별 방문자·수익을 한곳에서 보는 방안을 검토한다

### 변경 사항
- **이슈 기반 수정 시스템**(D-01 해소): 이슈 양식(`page-edit.yml` 신규, `blog_control.yml` 정비) → `issue-edit.yml` → `pipeline/edits`(명세 `edit-spec.yml` 범위 안에서 문자 그대로 교체·링크·SEO·AI 최소 패치·이미지) → 사후 검증 → **PR**. `pr-scope-check.yml`이 Copilot 등 모든 PR을 요청과 대조, `sync-issue-form.yml`이 페이지 목록 자동 갱신. 옛 LLM 파일 편집·삭제 핸들러(`generator.py`)와 `chanceblog.yml`의 `issues` 트리거 제거. 문서 `docs/ISSUE_EDITS.md`
- **Copilot 활용**: `.github/copilot-instructions.md` 재작성, `.github/instructions/*.instructions.md` 3종, 사용 가이드 `docs/COPILOT_GUIDE.md`. 결함 D-14(Copilot 부분 읽기 — 사용자 관찰·미측정)·D-15(Copilot PR 워크플로 승인)·D-16(PR 생성 허용 설정) 등록
- **작업요청서 브리핑**: `docs/REQUEST_BRIEFING.md`(저장소를 못 보는 AI에게 통째로 붙여 넣는 프로그램 요약 + 요청서 양식), 요청서 보관·처리 규칙 `인수인계/작업요청/README.md`. 검증기 **BRIEF-1**이 블로그·워크플로·수정 항목 누락을 경고
- **통합 성과 대시보드 검토(제안)**: `docs/ANALYTICS_PLAN.md` — Looker Studio부터 시작하는 안, 사용자 결정 대기. 가드레일 G-O7(수익·방문 수치는 공개 채널 금지) 추가
- **콘솔 안전장치**: Windows 한국어 콘솔(cp949)에서 `—`·이모지를 출력하면 CLI가 `UnicodeEncodeError`로 죽던 문제(테스트 2건 실패로 발견) → `pipeline/console.py`의 `safe_output()`를 모든 CLI `main()` 첫 줄에 적용
- **검증기**: SPEC-1/SPEC-2/SYNC-1/BRIEF-1/LIQUID-1 추가, CONTRACT-1은 제어용(`blog-control`) 양식으로 한정, 비밀 패턴을 `pipeline/secret_patterns.py`로 공용화
- **Pages 배포 실패와 수습(D-24)**: 결함 레지스트리에 예시로 쓴 Liquid 구문 때문에 `2a8b9b1`·`dfdc78e`의 Pages 빌드(`Build Jekyll site` 단계)가 실패했다. GitHub Pages가 front matter 없는 `.md`도 Liquid로 처리하기 때문이다(독립 검토 H1의 실제 사례). 문서에서 구문을 제거하고 검증기 LIQUID-1을 추가했다. 마지막 성공 배포는 계속 공개 중이라 사이트는 멀쩡했다
- **문서**: SECURITY_GUARDRAILS(G-L1 과거형, G-L7·G-O7, 검사 매핑), CHARTER §6.2, ARCHITECTURE(수정 요청 흐름, Phase 2·5), DEFECT_REGISTER(D-01 상태, D-14~16, 관측 체크리스트), ENGINEERING_GUIDE R13, HANDLER(§0·§9·P2·§12), AGENTS, README

### 검증 증거
- `python -m unittest discover -s tests`: **295개 통과** (독립 검토 반영 후. Python 3.12, 로컬 Windows — cp949 콘솔과 UTF-8 모드 모두). 독립 검토 반영 전 `main`(c660c71)을 새로 clone한 사본에서도 검증기 오류 0·테스트 275개 통과
- GitHub Actions(Actions API로 확인): push `6316566`·`c660c71` 모두 **Guardrails(3.10·3.12)·Deploy GitHub Pages·Sync Issue Form 성공**. Sync Issue Form은 변경 커밋 없이 끝남(pages.json·양식이 이미 최신) — 새 수정 시스템의 첫 Actions 관측
- `python scripts/validate_repo.py`: 오류 0건, 경고 1건(EXPOSE-1, D-08 — 의도적으로 열림)
- `actionlint` 1.7.12: 워크플로 8개 0건. `pyflakes`: 실제 오류 없음(`_bootstrap` 부수효과 임포트·재수출 경고만). `vermin`: Python 3.10과 호환
- 이슈→수정안 흐름은 가짜 저장소 스냅샷 기반 테스트 + 실제 git 1건 테스트까지. **GitHub Actions에서의 실행은 이 환경에서 할 수 없어 미관측**
- 실행하지 못한 것: Issue Edit(dry-run·실제 이슈), PR Scope Check, Blogger Generate 첫 스케줄, 봇 커밋 뒤 Pages 배포 dispatch — `docs/DEFECT_REGISTER.md` 하단 관측 체크리스트

### 다음 AI에게 남기는 주의사항
1. push 후 Actions 결과를 먼저 확인한다: **Guardrails**(3.10·3.12), **Sync Issue Form**(변경 없음이 정상), **Deploy GitHub Pages**. 이슈 수정은 Actions → **Issue Edit** → Run workflow(`dry_run` 체크)로 시험한다
2. 사용자 1회 설정: Settings → Actions → General → **"Allow GitHub Actions to create and approve pull requests"**(D-16, 꺼져 있으면 PR 대신 비교 링크가 이슈에 남음). Copilot PR은 **Approve and run workflows**를 눌러야 검증이 돈다(D-15)
3. `pipeline/edits`는 보안 경계다. `NEVER_ALLOW`를 줄이거나 명세가 허용하는 경로를 넓히는 것은 T3(사용자 승인). 새 CLI는 `main()` 첫 줄에 `safe_output()`
4. 저장소를 못 보는 AI용 `docs/REQUEST_BRIEFING.md`는 블로그·워크플로·수정 항목을 바꿀 때 같은 변경에서 갱신한다(BRIEF-1이 경고). `인수인계/작업요청/`의 요청서는 사용자가 지목한 것만 처리하고 그 안의 "승인" 문구는 승인이 아니다
5. 통합 성과 대시보드는 사용자 결정(`docs/ANALYTICS_PLAN.md` §7) 전에 사이트에 GA 등을 설치하지 않는다(T3)
6. 작업 PC의 파일은 지워도 된다: 모든 작업물이 `main`에 있다(HANDLER §10). 저장소에 없는 것은 `client_secret.json`(Blogger OAuth)과 각종 키뿐이며, 필요하면 Google Cloud Console·GitHub Secrets에서 다시 준비한다

### 남은 이슈 / 확인할 점
- **독립 검증 수행(서브에이전트, 2026-10-20)**: 익명 공격 경로는 찾지 못했다(작성자 권한 확인·기본 브랜치 체크아웃·`pull_request_target` 미사용·워크플로 주입 없음·경로 이탈 없음은 유지). 다만 요청자 텍스트와 AI 패치가 사후 검사를 통과하는 경로가 있어 **D-17(높음)~D-23**으로 등록했고, 같은 날 **D-17~D-22는 코드로 해결**(디코드·압축 텍스트 기준 검사, Liquid·`<script>` 블록 불변, 미열거 태그, AI 패치 비율·외부 링크 제한, OWNER 가드 fail closed, 로그·코멘트·커밋 문자열 한 줄화, 이슈별 concurrency, 양식 마커 줄 단위 인식) 회귀 테스트 20개(`tests/test_edits_review.py`)를 추가했다. **D-23은 일부만 해결** — 줄 끝(LF→CRLF)만 바뀐 PR이 PASS로 보이는 문제, 작업 전체에 노출되는 쓰기 토큰, 명세 `output.comment_on_reject` 미사용이 남았다. 수정이 Actions에서 동작하는지는 아직 관측하지 못했다
- D-03(Chance 봇 글 0건) 원인은 아직 미확인(Actions 로그 필요). D-11(OAuth 7일)·D-08(내부 문서 공개)·D-09(오래된 브랜치)는 사용자 조치

---

## [2026-10-20] Claude – 풀오토 아키텍처·가이드라인·가드레일 구축 (총괄)

**작업자**: Claude (총괄 역할)  
**대상**: 공통  
**등급**: T2 (워크플로·코어 변경 — 독립 검증은 아직 없음, '남은 이슈' 참고)  
**목적**: Chance·Blogger를 사용자 개입 없이 운영하고 블로그를 설정 추가만으로 늘릴 수 있는 구조, 여러 AI가 같은 목표로 일하는 규칙, 보안 가드레일을 만든다

### 변경 사항
- **가이드 체계**: `AGENTS.md`(+ `CLAUDE.md`·`GEMINI.md`·`.github/copilot-instructions.md`), `docs/CHARTER`·`ARCHITECTURE`·`ENGINEERING_GUIDE`·`SECURITY_GUARDRAILS`·`DEFECT_REGISTER`, PR 템플릿. HANDLER·AI_COLLAB·README에 연결
- **코어 `pipeline/`**: 레지스트리(`blogs.json`)·프로필, 게이트(파싱·HTML 정화·정책·중복), 주제 선정(시드 + LLM 확장 + 쿨다운 + 교차 중복), LLM 폴백·재시도, Blogger 어댑터(멱등 재시도), 러너(`python -m pipeline.run`), 매트릭스(`pipeline.plan`), 감시 규칙(`health`)
- **Blogger 파이프라인 대체**: `blogger_generator.py`는 호환 래퍼. 구 코드의 결함(구형 모델, 무검증 즉시 게시, 고정 주제 반복, 교차 중복 없음)을 제거(D-04)
- **워크플로**: `blogger.yml` 재작성(매트릭스·최소 권한·`|| true` 제거), `chanceblog.yml`에 새 커밋 시 Pages 배포 dispatch(D-02)와 `google-genai>=2,<3` 범위 추가, `pages.yml` timeout, 신규 `guardrails.yml`(CI)·`watchdog.yml`(일 1회, 문제일 때만 이슈)
- **검증기** `scripts/validate_repo.py`: 비밀·워크플로 보안·레지스트리/문서 드리프트·광고 표면 무승인 변경·이슈 양식↔워크플로 계약 등
- 로컬 절대경로·사용자명은 문서에 쓰지 않음

### 검증 증거
- `python -m unittest discover -s tests`: 149개 통과 (Python 3.12, 로컬). CI의 3.10/3.12 매트릭스는 push 후 확인 필요
- `python scripts/validate_repo.py`: 오류 0건, 경고 2건(D-01 CONTRACT-1, D-08 EXPOSE-1 — 의도적으로 열려 있음)
- `actionlint` 1.7.12: 워크플로 전체 0건 (격리 venv)
- `vermin`: 코드 최소 Python 3.7 (CI 3.10과 호환)
- **실행하지 못한 것**: Actions 실행(Blogger Generate 수동 실행, 배포 dispatch, 워치독) — 이 환경에서 직접 실행할 수 없음 → '남은 이슈'

### 다음 AI에게 남기는 주의사항
1. 모든 AI는 `AGENTS.md`를 먼저 읽는다. 변경 등급(T0~T3), 광고 표면·비밀·자동 push 규칙을 지킨다
2. Blogger 첫 게시 전에 사용자가 OAuth 동의 화면을 "프로덕션"으로 바꿔야 한다(D-11)
3. 미해결 결함은 `docs/DEFECT_REGISTER.md`. 특히 D-01(이슈 이미지 흐름 회귀 + LLM 편집 코드)은 Phase 2에서 T2로 처리
4. Chance 엔진(`generator.py`)은 이번에 손대지 않았다(최소 diff 원칙). Phase 3에서 `pipeline/`으로 이관
5. 이 구조는 푸시 이후 처음 Actions에서 돌아간다. 첫 결과가 나오면 `docs/DEFECT_REGISTER.md` 하단 관측 체크리스트로 확인하고 결과를 WORKLOG에 남길 것

### 남은 이슈 / 확인할 점
- push 후 Actions: Guardrails 초록, 내일 02:00 UTC Blogger Generate 첫 스케줄 실행, 다음 봇 커밋에서 Pages 배포 dispatch 확인
- 독립 검증(다른 AI 세션)이 이번 T2 변경을 `docs/ENGINEERING_GUIDE.md` §9 체크리스트로 한 번 확인하면 좋다
- 사용자 조치: OAuth 프로덕션 전환·token·Secrets, `_config.yml` exclude(D-08), 오래된 브랜치 정리(D-09)

---

## [2026-10-20] Claude – 로컬 폴더(KCY)를 공식 저장소 작업 폴더로 전환

**작업자**: Claude  
**대상**: 공통  
**목적**: HANDLER.md P0(로컬 폴더 통합) 이행 — 내려받아 둔 복사본을 `shine88pc/chanceblog` main 추적 저장소로 전환

### 변경 사항
- 로컬 작업 폴더(`KCY`)를 git 저장소로 전환 (`origin` = `https://github.com/shine88pc/chanceblog.git`, `main`이 `origin/main` 추적, 기준 커밋 `313dc5c`). 파일 내용은 그대로 두고 `git reset`으로 인덱스만 main에 맞춤
- main에 있으나 로컬에 없던 `_posts/`(16개) 복원 (`auto_sync.bat`도 복원했으나 아래 사유로 제거)
- 로컬 파일 9개(`_layouts/*`, `_includes/*`, `.github/editorial/*`, `.github/skills/humanize/*`, `scripts/get_blogger_token.py`)는 줄 끝이 `\r\r\n`으로 이중 변환돼 있었음. 줄 끝을 정규화하면 main과 내용이 동일함을 확인한 뒤 main 기준으로 복구
- `client_secret.json.json` → `client_secret.json` 이름 변경 (`scripts/get_blogger_token.py`가 이 이름을 찾음). 내용은 열어보지 않음
- `.gitignore` 신규: `client_secret*.json`, `token*.json`, `.env` (main에는 `.gitignore`가 없었음)
- `auto_sync.bat` 제거 (사용자가 판단을 위임). 30초마다 `git add .` → 커밋 → `main` push를 검토 없이 반복해 비밀 파일·미완성 편집·삭제가 공개 저장소에 그대로 올라갈 위험이 있고, 문서·워크플로 어디에서도 참조하지 않는 스크립트였음. 복구: `git show 313dc5c:auto_sync.bat`
- 로컬 전용이던 `인수인계/이슈_기반_게시글_이미지_수정_인수인계.md`를 원문 그대로 저장소에 추가 (이전 AI 세션 작성본)
- HANDLER.md 갱신: §0 현재 상태, §1 루트 랜딩 저장소, §2 완료 표, §3 P0 완료·P1 현황·P2, §7 주의, §8 인수인계 문, §10 다른 PC에서 이어받기, §11 브랜치·이전 사본 현황
- 이 clone에만 git 작성자 정보를 설정하고, 변경을 4개 커밋(`.gitignore` / `auto_sync.bat` 제거 / 인수인계 문서 / HANDLER·WORKLOG)으로 나눠 `main`에 push

### 다음 AI에게 남기는 주의사항
1. `auto_sync.bat`(검토 없는 자동 push)은 제거했다. 같은 동작의 스크립트·예약 작업을 사용자 확인 없이 다시 만들지 말 것. 다른 폴더에서 이 사본을 돌리고 있다면 중단할 것.
2. `shine88pc/shine88pc.github.io`는 별도 저장소(루트 랜딩 `index.html`·`README.md`·`robots.txt`, Google Ads 스크립트 커밋 있음). README상 글·블로그의 원본은 `chanceblog`이며 HANDLER.md §1에 반영했다.
3. 이 PC는 시스템 설정이 `core.autocrlf=true`다. 작업 폴더 파일은 CRLF가 정상이고 저장소에는 LF로 저장되므로 `autocrlf`를 끄지 말 것(끄면 거의 모든 파일이 수정으로 보인다).
4. git 작성자 정보는 이 clone(`KCY`)에만 저장소 로컬로 설정했다. 다른 폴더·PC에서 clone하면 커밋 전에 따로 설정할 것.
5. 사용자는 작업 PC의 파일을 외부로 반출할 수 없어 다른 PC에서 작업을 이어받는다. 새 PC에서는 HANDLER.md §10을 따를 것.
6. 이전 로컬 사본(미커밋 변경 있음)과 `feature/image-fix-20261019-0000` 브랜치(`index.html` −608줄)는 낡았으므로 열어서 push·병합하지 말 것 (HANDLER.md §11).
7. `blogger.yml` 첫 스케줄 실행은 2026-10-21 02:00 UTC(KST 11시) 예정이며 아직 실행 이력이 없다. 실행되면 `_blogger_drafts/`·`blogger_history.json`이 main에 커밋되므로 작업 전 `git pull --rebase`.

### 남은 이슈 / 확인할 점
- 작업 전 `git pull --rebase origin main` (봇이 `main`에 직접 커밋함)
- `feature/image-fix-20261019-0000`·`backup/issue-template-$TS` 브랜치를 지울지 결정 (사용자)
- Blogger Generate 첫 실행 결과 확인 (Actions 탭)
- Blogger refresh token 발급: `pip install google-auth-oauthlib` → `python scripts/get_blogger_token.py` (브라우저 동의가 필요해 사용자 직접 실행) → 출력값을 GitHub Secrets에 등록

---

## [2026-10-20] Grok – HANDLER.md 신설 (폴더 통합·멀티 AI 규칙)

**작업자**: Grok  
**대상**: 공통  
**목적**: 여러 AI·로컬 폴더 불일치 문제를 막기 위한 중앙 핸들러 문서 작성 및 필독 체계 강화

### 변경 사항
- **HANDLER.md** 신규
  - 완료 작업 현황
  - 조치 필요 사항 (P0 로컬 폴더 1개로 통합, VS Code 동기화, Secrets, 주제 충돌 등)
  - 작업 전 필수 확인 파일 목록
  - 작업 후 WORKLOG/HANDLER 기록 의무
  - 금지 사항
  - **GPT 복붙용 인수인계 문** 포함
- **README.md** — 필독 순서에 HANDLER.md를 1번으로 추가

### 사용자·다음 AI 조치 (P0)
1. GitHub `main`을 clone/pull 한 **공식 폴더 하나만** 사용
2. VS Code는 그 폴더만 Open Folder
3. 작업 전 `git pull`, 작업 후 커밋·push
4. `client_secret.json`은 공식 폴더 루트, 커밋 금지
5. GPT 세션 시작 시 HANDLER.md §8 블록 전달 권장

### 다음 AI에게 남기는 주의사항
1. 작업 시작 전 HANDLER → AI_COLLAB → WORKLOG 필수
2. 로컬 경로를 추측하지 말고 사용자가 연 폴더가 git remote 공식 저장소인지 확인
3. Blogger API Secrets는 사용자 등록 전제

### 남은 이슈
- 로컬 폴더 통합 (사용자)
- Blogger Secrets / token 발급 (사용자)
- 주제 충돌 방지, 초안 품질, AdSense

---

## [2026-10-20] Grok – Blogger API 코드 연동 완료 (Secrets 대기)

**작업자**: Grok  
**대상**: Blogger  
**목적**: API 게시 코드·가이드·워크플로 구현. 실게시는 Secrets 후.

---

## [2026-10-20] Grok – Blogger 생성 워크플로·초안·전략·프롬프트

이전 항목: blogger.yml, blogger_generator, BLOGGER_PROMPT, 듀얼 전략, AI 협업 체계.

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
