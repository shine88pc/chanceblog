# Chance_Blog Work Log (AI 인수인계 로그)

> **이 파일은 AI가 작업을 시작하기 전에 반드시 최신 항목을 읽어야 하는 인수인계 로그입니다.**  
> 필독 순서: **HANDLER.md** → **AI_COLLAB.md** → **이 파일 최신 항목**

최신 항목이 위에 오도록 **최신순**으로 작성합니다.

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
