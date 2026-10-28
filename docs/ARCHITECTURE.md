# 풀오토 아키텍처

> 목표: 블로그 N개를 사용자 개입 없이 운영하고, 블로그를 **설정 추가만으로** 늘린다.
> 상위 규칙: [`CHARTER.md`](./CHARTER.md) · 보안: [`SECURITY_GUARDRAILS.md`](./SECURITY_GUARDRAILS.md) · 코드·검증: [`ENGINEERING_GUIDE.md`](./ENGINEERING_GUIDE.md) · 알려진 결함: [`DEFECT_REGISTER.md`](./DEFECT_REGISTER.md)

## 1. 목표 구조

```
        pipeline/blogs.json (레지스트리)  +  pipeline/profiles/*.json (콘텐츠 정책)
                               │
      GitHub Actions ─ plan(매트릭스 계산·레지스트리 검증) ─► 블로그별 job (블로그마다 concurrency 그룹)
                               │
  주제 선정 ─► 생성(LLM) ─► 게이트 ─► 게시(어댑터) ─► 기록(history) ─► (jekyll-git만) 배포 트리거
  topics.py    llm.py      gates.py    publishers/*     state.py
                               │
  관측: 워치독(문제일 때만 이슈) · 실행 요약($GITHUB_STEP_SUMMARY) · Actions 실패 메일
  제어: 레지스트리 mode(off/draft/package/auto) · PIPELINE_PAUSE(킬 스위치) · 일일 상한 · 쿨다운 · publish_flow(Chance만, direct/pr)
  수정 요청: 이슈 양식 ─► pipeline/edits(명세 범위 안에서만) ─► PR ─► 범위 검사([공통] PR 변경 범위 검사) ─► 사람이 병합
  승인 흐름(선택, Chance): 글 한 쌍 ─► 초안 브랜치 ─► 승인 PR ─► 사람이 병합 = 공개 (기본 꺼짐, §4-4)
  초안 패키지(티스토리·네이버): 게이트 통과 글 ─► GitHub 이슈 1개(라벨 초안, 공개 없음) ─► 운영자가 복사해 직접 발행 ─► 이슈 닫기
```

설계 원칙은 세 가지다. ① **설정과 코드를 분리**한다(블로그 = 레지스트리 항목). ② **게시 전 게이트는 플랫폼과 무관**하게 한곳에 둔다. ③ **플랫폼 차이는 어댑터 안에** 가둔다.

## 2. 현재 상태 (2026-10-20 검증)

| 구성 | Chance_Blog (`chance`) | Blogger 영문 (`blogger_macat`) |
|------|------------------------|---------------------------|
| 엔진 | `generator.py` — 레거시 단일 파일. Phase 3에서 `pipeline/`으로 이관 | `python -m pipeline.run --blog blogger_macat` (`blogger_generator.py`는 호환 래퍼) |
| 트리거 | `chanceblog.yml` 매시 17분·47분(KST 9·18시 슬롯을 코드가 판단), 수동 (이슈 요청은 `issue-edit.yml`이, 기존 글 이미지 교체는 수동 전용 `chance-fix-images.yml`이 따로 처리) | `blogger-en.yml`(공용 `blogger.yml`을 부름) 매일 02:00 UTC(KST 11시), 수동 |
| 주제 | 약관을 읽은 직접 RSS(NASA·Pew·Federal Reserve·EU 집행위원회 계열·캐나다 통계청·영국 정부 GOV.UK 등, UN News는 보류), 신뢰 도메인 허용 목록, 72시간 이내, 출처 원문 검증 | 프로필 시드(영문 34개) + LLM 확장, 쿨다운 60일, 금지 주제 필터(주제 후보·제목·라벨·본문, §7-1), Chance 이력과 교차 중복 방지 |
| 생성 | Gemini 모델 폴백, KR/EN 쌍, 편집 템플릿 | Gemini 모델 폴백 + 일시 오류 재시도, 형식 엄격 파싱 |
| 게이트 | `validate_post_data`(길이·인라인 출처·머리말 검사·복구), 최종 머리말 검사(`front_matter_problems`), 제목 유사도 | `pipeline/gates.py`(파싱·HTML 정화·정책·중복), 탈락 사유를 넣어 최대 3회 재작성 |
| 게시 | git 커밋 → Pages 배포(`pages.yml`). 봇 커밋 뒤 `gh workflow run pages.yml`로 배포 실행. 레지스트리 `publish_flow: pr`(기본은 `direct`, 지금 꺼짐)이면 커밋 대신 초안 브랜치와 승인 PR 로 올리고 병합이 공개(§4-4) | Blogger API 어댑터(멱등 재시도, 인증 실패 구분, 초안함 업로드 `isDraft`, 쓰기 전 인증 점검 — 아래 §4·§4-1) |
| 상태 | `history.json`(문자열·객체 혼합 스키마. 승인 흐름의 항목에는 `flow`·`branch`·`paths` 필드가 더 있다 — §4-4) | `blogger_history.json`(스키마 v1, §5) |
| 관측 | Actions 로그 | 실행 요약 + 이력 status + 워치독 |
| 수정 요청(이슈) | `issue-edit.yml` + `pipeline/edits`: 이슈 양식 → 문자 그대로 교체·링크·SEO·이미지(AI는 최소 패치·검색어만) → 사후 검증 → PR. 상세 [`ISSUE_EDITS.md`](./ISSUE_EDITS.md) | 해당 없음(Blogger 글은 Blogger 관리 화면) |
| 상태(운영) | 운영 중. 단 슬롯 시각이 된 실행 13회 중 2회만 글이 나왔다(D-03: 분야 폴백·사유 기록으로 완화, 병합 뒤 관측). 이슈 수정은 `pipeline/edits`로 재구축(D-01, Actions 관측 대기) | 코드 완료(초안함 업로드 모드 포함, D-55). 정지(`mode: off`), 게시용 시크릿 미등록, refresh token 미발급(D-11). 실제 구글 호출은 한 번도 한 적이 없어 시크릿 등록 뒤 첫 수동 실행에서 처음 검증된다 |

공통: 워치독 일 2회(`watchdog.yml`), 저장소 가드레일 CI(`guardrails.yml`), 레지스트리 검증(`python -m pipeline.registry`), PR 범위 검사(`pr-scope-check.yml`, 이슈를 참조하는 모든 PR).

한글 Blogger(`blogger_kcyoon`, kcyoon.blogspot.com, 2026-10-27 등록 — 작업 D, 운영자 승인 D5·D6, T3): 일상 속 AI·디지털 도구 활용법(약 70%)과 집·살림 정리(약 30%)를 다루는 한국어 블로그다. 영문과 **같은 러너·같은 Blogger 어댑터**를 쓰고 레지스트리 값만 다르다 — 프로필 `blogger_ai_tools_ko`(§7-1), 프롬프트 `.github/editorial/BLOGGER_PROMPT_KO_AI.md`, 이력 `blogger_ko_history.json`, 초안 `_blogger_ko_drafts/`, 시크릿 `BLOGGER_KO_*` 4종(영문과 **다른 구글 계정·Cloud 프로젝트·OAuth 클라이언트**, LLM 키 `GEMINI_API_KEY`만 공유), 워크플로 `blogger-ko.yml`(매일 03:30 UTC = KST 12:30). **`mode: off`·`ads: off`·`ad_surface: false`로 등록**돼 켜기 전에는 글도 구글·Gemini 호출도 없다(정기 실행은 '대상 0개'로 초록). 켜는 것은 별도 운영자 승인(T3)이다([`ACTIONS_GUIDE.md`](./ACTIONS_GUIDE.md) 3-12). 실제 GitHub 실행으로는 한 번도 돌려 보지 않았다(문법 검사 `actionlint`와 시험으로만 확인).

**Blogger 워크플로 구조**(작업 D): `blogger.yml`은 **재사용 워크플로**(`on: workflow_call`, 이름 `[내부] Blogger 글 작성 공용(직접 실행하지 마세요)`)이고, 채널마다 얇은 래퍼 — `blogger-en.yml`(`[Blogger 영문]`)·`blogger-ko.yml`(`[Blogger 한글]`) — 가 자기 cron·수동 입력(`topic`·`dry_run`·`publish`·`auth_check`)·동시 실행 줄(`blogger-en`·`blogger-ko`)·시크릿 이름을 갖고 `with:`·`secrets:`로 값을 명시해 부른다. 정기·수동 판단(`github.event_name`·`github.event.inputs`)은 래퍼가 하고 공용 워크플로는 부르는 쪽 이벤트를 읽지 않는다. 재사용 워크플로를 부른 실행은 부른 쪽(래퍼) 파일 아래에 기록되므로 워치독·확인 필요 모음은 레지스트리 `workflow`(= 래퍼)로 '마지막 실행'을 찾는다. 래퍼가 레지스트리와 맞는지(`with.blog`·넘기는 시크릿 이름·호출 잡 권한이 정확히 `contents: write`·동시 실행 줄)는 검증기 **REG-6**이, 시크릿 전달 자리는 **WF-13**이 본다.

초안 패키지 채널(티스토리·네이버, 2026-10-27 운영자 승인 D4·D7, T3): 공식 자동 게시 수단이 없어(티스토리 오픈 API 2024-02 종료, 네이버 글쓰기 API 2020 종료) 글을 공개하지 않고 **GitHub 이슈 1개(= 초안 1건)**로 보여 주며 운영자가 복사해 직접 발행한다(§7-B). 코드(`mode: package`·`pipeline/publishers/issue_package.py`)·워크플로(`tistory.yml`·`naver.yml`)·검증·시험은 끝났다. **레지스트리에는 두 채널의 항목이 아직 없다**(블로그 주소·주제는 사용자 입력 대기) — 그래서 정기 실행은 '대상 0개'로 초록이다. 첫 실제 초안 이슈가 복사 가능한 모양인지는 Actions·GitHub 화면에서만 확인할 수 있어 관측 대기다.

### 2-1. GitHub Actions 탭의 이름 (2026-10-27 기준)

Actions 왼쪽 목록의 이름은 **이름만 보고 어느 채널의 것인지, 자동인지 수동인지, 무엇을 하는지 짐작할 수 있게** 지었다. 맨 앞에 `[구분] `을 붙이고 뒤는 한글로 쓴다. 구분은 블로그 채널 라벨(`Chance`·`Blogger 영문`·`Blogger 한글`·`티스토리`·`네이버`)이거나, 블로그에 속하지 않는 워크플로의 `공통`(배포·검사·감시·점검), 다른 워크플로가 부르는 공용 실행의 `내부`(직접 실행하지 않는다)다. GitHub에는 워크플로를 묶는 폴더나 분류가 없고 목록이 이름순이라, 접두사가 같은 것끼리 붙어 보이게 하는 것이 구분 수단이다. 파일 이름(`*.yml`)은 그대로이고(레지스트리·워치독·문서가 파일 이름으로 가리킨다) 화면에 보이는 `name`·`run-name`만 바뀌었다 — 워크플로를 이름으로 찾는 코드는 없다(워치독·점검 모음은 파일 이름, 이름은 안내 문구와 모음 항목 제목에만 쓴다). `name`은 대괄호로 시작해 YAML에서 큰따옴표가 필요하다(`name: "[Chance] …"`). 실행 목록의 제목(`run-name`)에는 같은 접두사에 이어 정기/수동·연습 여부(이슈 처리는 이슈 번호)가 붙는다. job 이름과 단계 이름에는 접두사를 붙이지 않는다(job 이름은 PR 검사 화면의 이름이다). 블로그 워크플로의 구분은 레지스트리 `channel.label`(§3)과 같은 글자여야 한다(레지스트리 검증이 읽는다, REG-1). 새 워크플로·job의 이름도 한글로 짓고 접두사를 붙인다(검증기 **WF-11**·**WF-12**, [`ENGINEERING_GUIDE.md`](./ENGINEERING_GUIDE.md) W10). 이슈 제목 접두 `[Watchdog]`·`[운영] 확인 필요 모음`과 라벨 `watchdog`·`ops-inbox`는 이름이 아니라 식별자라 그대로다.

| 옛 이름 | 새 이름 (Actions 탭) | 파일 | 하는 일 | 자동/수동 |
|---------|----------------------|------|---------|-----------|
| Chance_Blog Full-Auto Engine | `[Chance] 글 자동 작성·게시` | `chanceblog.yml` | 뉴스 기사를 바탕으로 Chance 글(한국어·영어)을 만들어 검증하고 저장소에 커밋해 게시(레지스트리 `publish_flow: pr`이면 커밋 대신 초안 PR 로 올려 사람이 병합해야 공개 — 기본 꺼짐, §4-4) | **자동**(매시 17분·47분 UTC에 실행, 게시 시각은 코드가 판단) + 수동 실행(연습이 기본). 실행 제목 `[Chance] 글 작성·게시 · 정기/수동`. 새 글을 push 한 실행의 마지막 단계 `텔레그램 알림(새 글)`이 휴대폰으로 알린다(§4-5) |
| (`chanceblog.yml`의 `fix_images` 입력) | `[Chance] 기존 글 이미지 교체(수동)` | `chance-fix-images.yml` | 기존 글의 깨진·누락·중복 이미지만 교체(새 글은 만들지 않음). 2026-10-25에 글 작성 워크플로에서 분리 | **수동 전용**(연습이 기본) |
| Blogger Generate | `[Blogger 영문] 글 자동 작성` | `blogger-en.yml` | 영문 Blogger(`blogger_macat`)의 글을 만들고 검증해 저장소 초안 저장·Blogger 초안함 업로드·즉시 게시 중 하나로 보낸다(블로그 모드에 따름. `mode: off`면 건너뛰고 초록 + `::notice::`). 실제 작업은 공용 `blogger.yml`을 불러서 한다(아래 `[내부]` 행). 이름에 '(초안함 업로드)'가 없는 것은 `mode: auto`면 즉시 게시라 이름이 어긋나서다(독립 검증 N7) | **자동**(매일 02:00 UTC = KST 11시, 모드를 따름) + 수동 실행(입력 `publish`: `off` 저장소 파일만 · `draft` 초안함 업로드(기본) · `publish` 즉시 게시, 입력 `auth_check`(`인증 점검만 실행`, 기본 꺼짐): 글을 만들지 않고 인증만 점검 — §4-1). 실행 제목 `[Blogger 영문] 글 작성 · 정기/수동(…)`. 초안함 업로드·즉시 게시가 성공하면 러너가 휴대폰으로 알린다(§4-5) |
| (신규) | `[Blogger 한글] 글 자동 작성` | `blogger-ko.yml` | 위와 같음 — 한글 Blogger(`blogger_kcyoon`, 일상 속 AI·디지털 도구 활용법 + 집·살림)용. 시크릿은 `BLOGGER_KO_*`, 이력은 `blogger_ko_history.json`·`_blogger_ko_drafts/`. 지금 `mode: off`라 '대상 0개'로 초록(인증 점검만은 정지 중에도 한다) | **자동**(매일 03:30 UTC = KST 12:30, 모드를 따름) + 수동 실행(입력은 영문과 같다). 실행 제목 `[Blogger 한글] 글 작성 · 정기/수동(…)` |
| (신규) | `[내부] Blogger 글 작성 공용(직접 실행하지 마세요)` | `blogger.yml` | 위 두 워크플로가 부르는 **재사용 워크플로**(`on: workflow_call`만 있어 Run workflow 버튼도 정기 실행도 없다). 대상 계산(`pipeline.plan`)과 글 생성·이력 커밋을 한다. 입력(`blog`·`topic`·`dry_run`·`publish`·`auth_check`)과 시크릿 7개(선택)를 부르는 쪽이 명시해 넘긴다 — `secrets: inherit` 금지(WF-13) | 직접 실행하지 않는다(부르는 쪽 실행 안에서만 돈다) |
| Deploy GitHub Pages | `[공통] 사이트 자동 배포` | `pages.yml` | Chance 사이트(GitHub Pages)를 빌드해 게시 | **자동**(main에 push될 때. 봇이 커밋한 뒤에는 `[Chance] 글 자동 작성·게시`·`[Chance] 기존 글 이미지 교체(수동)`가 직접 실행을 요청) + 수동 |
| Guardrails | `[공통] 저장소 규칙·테스트 자동 검사` | `guardrails.yml` | 비밀 유출·워크플로 보안 규칙·문서 불일치·광고 표면 변경 검사, 단위 테스트, `actionlint` | **자동**(main push·모든 PR) + 수동. job 이름 `검사 (Python 3.10/3.12)` |
| Watchdog | `[공통] 발행 중단 감시·알림` | `watchdog.yml` | 글이 오래 안 올라오거나 실패가 이어지거나 글 커밋 뒤 사이트 배포가 안 되면 `[Watchdog]` 이슈로 알림(담당자 지정·@멘션, 문제일 때만, 해소되면 닫음. 승인 흐름에서 승인 대기 초안 PR 이 있으면 '글이 안 나옴'을 `DRAFT_WAITING` 경고로 낮춘다). 규칙은 §4-2 | **자동**(하루 2회, 시각은 `watchdog.yml`의 cron) + 수동. 실행 제목 `[공통] 발행 중단 감시 · 정기/수동` |
| Issue Edit | `[Chance] 이슈 수정 요청 처리(수정안 PR 만들기)` | `issue-edit.yml` | 이슈 양식으로 접수된 수정 요청을 검증해 수정안을 PR로 만든다(main에 직접 반영하지 않음) | **자동**(제어 이슈가 열릴 때) + 수동(이슈 번호 입력, 연습이 기본). 실행 제목 `[Chance] 이슈 #번호 수정 요청 처리 · …` |
| PR Scope Check | `[공통] PR 변경 범위 검사` | `pr-scope-check.yml` | 이슈를 참조하는 PR(Copilot·사람)이 요청 범위를 지켰는지 검사해 PR에 코멘트 | **자동**(PR이 열리거나 갱신될 때) + 수동(PR 번호 입력) |
| Sync Issue Form | `[공통] 이슈 양식 페이지 목록 갱신` | `sync-issue-form.yml` | `pages.json`과 이슈 양식의 '대상 페이지'·'수정 항목' 드롭다운을 최신으로 갱신 | **자동**(관련 파일이 main에 push될 때) + 수동 |
| (신규) | `[공통] 확인 필요 모음` | `ops-inbox.yml` | 해야 할 일·확인할 일(워치독 알림·병합 대기 PR·실패한 워크플로·승인 대기·일시정지·Blogger 게시 설정·채널별 초안 현황)을 이슈 `[운영] 확인 필요 모음` 1개와 실행 요약에 모으고, 새로 해야 할 일이 생기면 코멘트(@멘션)로 알림. 설명: [`OPS_INBOX.md`](./OPS_INBOX.md) | **자동**(2시간 간격 예약, 매 짝수 시 40분 UTC — GitHub가 늦추거나 건너뛰어 실제로는 보통 3~6시간 간격 + 라벨 `초안`이 붙은 이슈·PR이 열리고 닫히고 라벨이 바뀔 때, 사람이 한 조작에 한함) + 수동(`연습 실행` 가능). 실행 제목 `[공통] 확인 필요 모음 갱신 · 정기/수동/이슈 변경(초안만 점검)/PR 변경(초안만 점검)`. 코멘트를 쓰는 새 해야 할 일은 같은 요약으로 휴대폰에도 알린다(§4-5) |
| (신규) | `[티스토리] 초안 패키지 만들기` | `tistory.yml` | 레지스트리의 `platform: tistory` 블로그마다 글을 만들고 검증해 **GitHub 이슈 1개(초안 패키지)**로 보여 준다. 공개하지 않는다 — 운영자가 이슈의 복사 상자(제목·HTML·태그)로 티스토리에 직접 발행하고 이슈를 닫는다. 같은 채널에 열린 `초안` 이슈가 3건 이상이면 새로 만들지 않고, 대상이 없으면(블로그가 레지스트리에 없거나 `mode: off`) 초록 + `::notice::`로 끝난다. 시크릿은 Gemini 키뿐(계정 정보 없음). 설명 §7-B·[`ACTIONS_GUIDE.md`](./ACTIONS_GUIDE.md) 6-12 | **자동**(매일 05:20 UTC = KST 14:20) + 수동 실행(`연습 실행` 기본 켜짐: GitHub 호출 0회, 이슈 본문 미리보기만 실행 요약에). 실행 제목 `[티스토리] 초안 패키지 · 정기/수동(…)` |
| (신규) | `[네이버] 초안 패키지 만들기` | `naver.yml` | 위와 같음 — 네이버 블로그용. 이슈의 '서식 있는 글'을 선택·복사해 스마트에디터에 붙여넣는다(안 되면 평문 상자). 글감은 Chance 글의 각색이 아니라 이 블로그 자체 주제다(원고 변형 복제 금지, D7). 설명 §7-B·[`ACTIONS_GUIDE.md`](./ACTIONS_GUIDE.md) 6-13 | **자동**(매일 06:20 UTC = KST 15:20) + 수동 실행(`연습 실행` 기본 켜짐). 실행 제목 `[네이버] 초안 패키지 · 정기/수동(…)` |
| (신규) | `[공통] 텔레그램 알림 시험` | `telegram-test.yml` | 시크릿 `TELEGRAM_BOT_TOKEN`·`TELEGRAM_CHAT_ID`가 등록돼 있는지 이름별 '등록됨/없음'만 요약에 쓰고, 둘 다 있으면 휴대폰에 '알림 연결 확인' 한 통을 보낸다. 실패하면 이유(토큰 틀림·채팅 ID 틀림·봇에 /start 안 함·네트워크)를 요약에 분류해 쓴다(저장소는 읽기만). 설명: `.github/editorial/TELEGRAM_SETUP.md` | **수동 전용** |
| (신규) | `[공통] AI 요청 텔레그램 알림` | `ai-request.yml` | AI 가 `ai/claude/**` 브랜치로 push 한 커밋이 **새로 더한** 요청 파일(`인수인계/요청함/R-001_….md`)의 제목·요약을 휴대폰 텔레그램으로 보낸다(한 push 에 3통까지, 버튼 `요청 열기`·`PR 열기`·`답하기`·`사용법`). 새 파일은 파이썬이 git 으로 가린다(§4-6). 저장소는 읽기만 하고 시크릿은 마지막 단계의 env 로만 쓴다 | **자동**(`ai/claude/**` 브랜치 push 마다 — 경로 필터를 쓰지 않아 새 요청 파일이 없는 push 에서도 짧게 돌고 곧바로 끝난다) |
| (신규) | `[공통] 운영자 응답 접수` | `operator-reply.yml` | 운영자가 이슈 양식(`AI 요청에 답하기(결정·확인)` `[답변]`·`AI 에게 새 일 맡기기(작업 요청)` `[요청]`)으로 연 이슈를 **소유자만** 접수 확인한다: 라벨 `운영자응답`·`운영자요청` 붙이기·접수 코멘트 한 번·텔레그램 `✅ 답변 접수`(§4-6). 이슈 글은 명령·로그에 넣지 않는다 | **자동**(이슈가 열릴 때만, 실행 제목 `[공통] 운영자 응답 접수 · 이슈 #번호`) |
| (GitHub 내장) | `pages-build-deployment` | 파일 없음 | GitHub Pages가 스스로 만들어 목록에 보일 수 있는 실행. 이름을 바꿀 수 없다. **누르지 않는다**(배포는 `[공통] 사이트 자동 배포`) | GitHub 내장 |

기본 제목(커밋 메시지·PR 제목)이 더 알려 주는 `[공통] 사이트 자동 배포`·`[공통] 저장소 규칙·테스트 자동 검사`·`[공통] PR 변경 범위 검사`·`[공통] 이슈 양식 페이지 목록 갱신`은 `run-name`을 따로 두지 않았다. 정기·수동·연습은 `Run workflow` 대화상자 입력(`연습 실행` 체크)과 실행 제목으로 구분한다.

**새 워크플로를 만들면 이 표와 [`REQUEST_BRIEFING.md`](./REQUEST_BRIEFING.md)의 표에 한 줄씩(`파일`과 `이름`을 같은 줄에 백틱으로) 넣어야** `tests/test_workflow_names.py`의 `test_docs_tables_list_every_workflow_with_its_current_name`이 통과한다. 안내 문서·워크플로·이슈 양식·코드에 옛 영문 이름이 새 이름 없이 남아도(옛 이름과 새 이름이 한 줄에 같이 있는 대응표는 제외) `test_operator_docs_do_not_use_the_old_english_names`가 실패한다.

**블로그 워크플로의 `name` 줄 모양에 레지스트리가 기댄다**: 레지스트리 검증(REG-1)은 YAML 을 해석하지 않고 `blogs.json`의 `workflow` 파일에서 들여쓰기 없는 첫 `name:` 줄을 읽어, 따옴표로 감싼 값이 `"[채널 라벨] 이름"`(대괄호 뒤 공백 하나와 이름)인지 본다. 이 줄을 따옴표 없이 쓰거나 접두사·공백을 잘못 고치면 레지스트리 검증이 실패하고, 그 검증을 먼저 하는 plan 잡(`pipeline.plan`, 종료 1 — `[Blogger 영문]`·`[Blogger 한글]`·`[티스토리]`·`[네이버]` 워크플로의 대상 계산 단계)·러너(`pipeline.run`, 설정 오류 종료 2)·워치독(`scripts/watchdog.py`, 종료 1)이 레지스트리 오류로 멈춘다. 블로그 워크플로의 `name`을 고칠 때는 `blogs.json`의 `channel.label`과 함께 바꾸고 `python -m pipeline.registry`로 확인한다(검증기 WF-12 는 접두사 모양만 본다).

**수동 실행의 기본값과 정지 스위치**(2026-10-25, D-51·D-53·D-54): 무료 Gemini 한도는 프로젝트 단위로 모든 파이프라인이 한 통을 나눠 쓰므로, 점검용 수동 실행이 정기 발행의 몫을 쓰지 않게 기본값을 '연습'으로 맞췄다. `[Chance] 글 자동 작성·게시`와 `[Chance] 기존 글 이미지 교체(수동)`의 `연습 실행`(기본 켜짐)은 **가짜 AI 응답(스텁)**을 쓰고 Gemini 키를 프로세스에 넘기지 않아 호출이 0회이며, 연습에서도 실제 호출로 시험하려면 `real_ai`를 체크한다(기본 꺼짐. 실행 제목에 '실제 AI 호출'이 붙고 요약에 'AI 응답' 줄이 남는다). `[Blogger 영문] 글 자동 작성`·`[Blogger 한글] 글 자동 작성`의 `dry_run`도 기본이 켜짐(래퍼의 입력 기본값, 공용 워크플로는 부르는 쪽이 넘긴 값만 쓴다)으로 바뀌어, 체크를 풀어야 실제 Gemini로 글을 만들어 초안을 저장소에 커밋하고(Blogger에 올릴지는 `publish` 입력에 따른다) 그날 하루 상한을 쓴다. 정기 실행과, 연습을 풀고 실제로 게시하는 수동 실행은 예전처럼 항상 실제 Gemini를 부른다. 기존 글 이미지 교체는 한 번에 최대 20건(`generator.py`의 `FIX_IMAGES_MAX_PER_RUN`)만 처리하고 나머지는 다음 실행으로 넘기며 요약에 그 사실을 남긴다(연습 실행의 요약은 '교체 예정 N건 중 M건 처리 대상'). Chance의 수동 실제 실행은 게시 시각 판단과 하루 상한(`pipeline/blogs.json`의 `max_posts_per_day`)을 따지지 않는다 — 운영자가 일부러 더 게시할 수 있어 막지 않고, 오늘 이미 게시된 글이 상한 이상이면 `::warning::`과 요약 줄만 남긴다. `[Chance] 이슈 수정 요청 처리(수정안 PR 만들기)`도 이제 `PIPELINE_PAUSE`(`1`·`true`·`yes`·`on`)를 읽는다: 켜져 있으면 AI·이미지 검색을 부르지 않고 파일·PR도 만들지 않으며, 형식이 맞는 요청에는 이슈에 '일시정지 중' 코멘트만 남기고 정상 종료한다(코멘트는 변수를 지운 뒤 `연습 실행` 체크를 풀고 다시 실행하라고 안내한다 — 수동 실행은 `연습 실행`이 기본 켜짐이라 그냥 다시 실행하면 연습만 돌아 PR이 안 생긴다). 알아 둘 한계 셋: ① **연습 실행도 Unsplash 이미지 검색은 실제로 한다**(`UNSPLASH_ACCESS_KEY`는 연습에서도 넘어간다). 글 작성 연습은 검색 1회 이하, 이미지 교체 연습은 문제 글마다 1~2회(한 번에 최대 20건이면 20~40회)이며 시간당 한도(코드 주석상 데모 앱 50회)를 정기 글·이슈 이미지 검색과 나눠 쓴다 — 실행 요약의 `Unsplash 남은 호출` 줄로 본다. 연습에서 Unsplash 키도 비우는 안은 운영자 결정 사항이라 동작을 바꾸지 않았다. ② 정기 실행도 하루 상한을 직접 검사하지 않고 슬롯 2개(KST 9시·18시)로만 하루 2편을 지킨다. 수동 글은 `slot=None`이라 슬롯에 잡히지 않아, 09시 슬롯 글이 있는 날 낮에 수동 실제 게시를 하면 18시 정기 실행이 또 만들어 **하루 3편**이 될 수 있다(경고는 수동 실행 시점에 이미 상한 이상일 때만 뜬다). 상한 강제는 T3 결정이다. ③ 정지 중에도 이슈 수정은 `gh label create --force` 4건과 이슈 코멘트 1건을 한다('저장소 쓰기 0'이 아니라 '파일·PR 0'). 이미지 교체의 '나머지는 다음 실행'은 사람이 `Run workflow`를 다시 눌러야 하고, 앞 20건이 영구 실패하면(검색 결과 없음 등) 뒤 글에는 차례가 오지 않는다(**굶김** — 선정 순서는 바꾸지 않았다). 교체가 전부 실패해도 요약이 `교체 0건 / 건너뜀 N건`이고 실행은 초록이다. Blogger 수동 연습의 격리는 Chance처럼 키를 빼는 방식이 아니라 `pipeline/run.py`의 `dry` 분기에 의존한다(키는 연습에도 환경에 있고, 연습이면 LLM·게시자를 만들지 않는다).

**사이트에 내보내지 않는 것**(2026-10-26 운영자 승인, D-08·SIT-03): `_config.yml`에 `exclude`(AGENTS·AI_COLLAB·CLAUDE·GEMINI·HANDLER·WORKLOG, `docs/`·`인수인계/`)를 더해 운영 문서를 사이트·사이트맵·글 내비·정적 파일로 내보내지 않고(코드·상태 파일 11항목 `generator.py`·`blogger_generator.py`·`pipeline/`·`scripts/`·`tests/`·`history.json`·`blogger_history.json`·`pages.json`·`requirements-*.txt` 3개도 같은 날 운영자 승인 "2. 추천대로"를 받아 뺐다. `README.md`는 문서라 승인 범위 밖이어서 그대로 열려 있다), `index.html`의 글 목록 영역을 Jekyll 반복문(`site.posts` 최근 24편)으로 미리 그려 JS 없이도 글 링크가 보이게 했다(JS는 미리 그린 카드를 새 목록이 준비될 때까지 두었다가 같은 글로 한 번 바꾼다). 광고 스크립트 줄·모달·방문 카운터는 그대로이고 `<head>`에는 JS 없는 방문자용 `<noscript><style>` 한 줄만 더했다. 새 맨 위 파일·폴더는 `tests/test_site_cleanup.py`의 `PUBLIC_ROOT`(내보냄)·`STATIC_EXPOSED`(일부러 그대로 열어 두는 파일 — 지금은 `README.md`)·`_config.yml`의 `exclude`(뺌) 중 한 곳에 넣어야 시험이 통과한다. 저장소에는 그대로 있다.

### 외부 소비자 계약

| 파일 | 소비자 | 규칙 |
|------|--------|------|
| `posts.json` (`/chanceblog/posts.json`) | 루트 랜딩 저장소 `shine88pc.github.io`의 `index.html`이 `fetch`로 읽는다 | 스키마·경로 변경은 T2, 사전에 루트 저장소와 함께 확인 |
| `feed.xml`, `sitemap`, 사이트 인증 파일 | 검색엔진·구독자 | 광고 표면과 같은 취급(T3) |

## 3. 레지스트리 스키마 (`pipeline/blogs.json`, v1)

최상위: `schema_version`(1), `shared_secrets`(여러 블로그가 함께 쓰는 시크릿 이름), `defaults`(모든 블로그가 상속), `blogs[]`.

| 필드 | 설명 / 제약 |
|------|-------------|
| `key` | 고유 식별자 `^[a-z][a-z0-9_]{1,30}$` |
| `name`, `role`, `url`, `languages` | 표시·문서용. `url`은 `https://` |
| `platform` | `jekyll-git` · `blogger` · `tistory` · `naver`(둘은 초안 패키지 전용 — §7-B-2). 게시 어댑터가 있는 새 플랫폼은 §7.B |
| `channel` | **필수.** `{"key": "<영문 식별자>", "label": "<채널 라벨>"}` — 항목에 직접 적는다(`defaults`에서 물려받지 않는다). `label`은 `Chance`·`Blogger 영문`·`Blogger 한글`·`티스토리`·`네이버` 중 하나(`registry.CHANNEL_LABELS`, 채널을 나누기 전의 라벨 `Blogger`는 없앴다)이고, **그 블로그 `workflow` 파일의 `name`이 `"[label] …"`로 시작해야 한다**(§2-1. 대괄호로 시작하는 값이라 큰따옴표가 필요하다). `label`·`key`는 블로그끼리 겹칠 수 없다(채널 = 블로그 하나). `공통`·`내부`는 블로그에 속하지 않는 워크플로의 구분이라 여기에 쓰지 않는다. 검증: 레지스트리 검증(REG-1 — `python -m pipeline.registry`·`pipeline.plan`·`pipeline.run`이 같은 규칙을 읽는다). 그래서 **한 워크플로 파일을 채널이 다른 블로그 둘이 나눠 쓸 수 없다** — 채널마다 이름이 다른 워크플로가 필요하다(Blogger 는 채널별 래퍼 `blogger-en.yml`·`blogger-ko.yml`이 공용 `blogger.yml`을 부르고, 래퍼가 레지스트리와 맞는지는 REG-6, §7-A). `tistory`·`naver` platform 블로그의 라벨은 각각 `티스토리`·`네이버`여야 한다(초안 이슈의 라벨 `채널:<라벨>`이 이 값으로 만들어진다) |
| `mode` | `off` 중지 · `package` 초안 패키지(`tistory`·`naver` 전용이고 이 두 platform 은 `off`·`package` 만 쓴다) — 글을 만들어 GitHub 이슈 1개(라벨 `초안`)로 보여 줄 뿐 공개하지 않는다(`package_issued`, §4-1·§7-B-2) · `draft` 초안 — Blogger는 게시용 시크릿 4종(`blog_id`·`client_id`·`client_secret`·`refresh_token`)이 **모두** 있으면 글을 Blogger **초안함에 업로드**하고(`draft_uploaded`, 공개되지 않음 — 운영자가 Blogger 화면에서 확인한 뒤 직접 게시), **하나도** 없으면 저장소 파일에만 저장하며(`draft`, 오류 아님), **일부만** 있으면 설정 오류(종료 2) · `auto` 자동 게시. **`auto` 전환은 T3** |
| `publish_flow` | (선택, `jekyll-git`만, 지금은 Chance) 글을 만든 뒤 공개되는 방식. `direct` 만들자마자 main 에 커밋해 게시(기본 — 필드가 없어도 같다, 지금 동작) · `pr` 초안 브랜치와 승인 PR 로 올리고 **사람이 병합해야 공개**(`mode`는 `auto`여야 한다. §4-4). 값이 틀리거나 읽지 못하면 직접 게시로 떨어지지 않고 멈춘다. **`pr`로 바꾸는 것은 T3**(게시 방식) |
| `workflow`, `entrypoint`, `prompt` | 저장소에 존재하는 파일. `workflow`의 cron 목록에 `schedule.cron`이 들어 있어야 한다(검증기 REG-2, Chance는 17분·47분 두 틱이고 레지스트리에는 17분이 대표값). 초안 패키지 블로그의 `entrypoint`는 `pipeline/run.py`다(별도 생성기 파일이 없다) |
| `profile` | `pipeline/profiles/<이름>.json`. `blogger`·`tistory`·`naver` 플랫폼은 필수. 글 언어 검사는 `languages`(표시·문서용)가 아니라 프로필의 `language`(`ko`·`en`)가 정한다. 필드와 가드레일은 §7-1 |
| `state.history`, `state.content_dir` | 이력 파일, 산출물 폴더(저장소 상대 경로, `..` 금지) |
| `schedule.cron` | 워크플로 cron 목록 중 하나(대표값). `slots_kst`는 참고 |
| `limits.max_posts_per_day` | 1~24. 하루 상한(KST 날짜 기준). 수동 `--topic`은 우회 |
| `llm.models`, `llm.max_retries` | 모델 폴백 순서, 일시 오류 재시도 횟수 |
| `secrets` | `{역할: 환경변수(=Secrets) 이름}`. **값은 절대 쓰지 않는다.** 플랫폼별 필수 역할은 `registry.PLATFORMS`. `tistory`·`naver`는 `llm_api_key` **뿐**이다 — 다른 역할이나 이름에 `PASSWORD`·`PASSWD`·`PWD`·`COOKIE`·`SESSION`·`LOGIN`·`CREDENTIAL`이 든 시크릿은 레지스트리 검증(REG-1)이 막는다(구조적 보장은 시크릿 역할이 `llm_api_key` 뿐이라는 것이다 — 이름 검사는 실수를 막는 보조이고 포함 검사라 `PASS_WORD`·`TISTORY_PW` 같은 우회 철자는 통과한다. [`SECURITY_GUARDRAILS.md`](./SECURITY_GUARDRAILS.md) G-S7) |
| `ad_surface`, `protected_paths` | 광고(AdSense) 심사·수익 대상인지, 승인 없이 못 바꾸는 경로(`/`로 끝나면 폴더). `ad_surface: true`는 사이트 코드가 이 저장소에 있는 `jekyll-git` 블로그에만 쓴다 |
| `ads` | 광고 선언 `off`·`pending_gate`·`on`(적지 않으면 `defaults.ads` = `off`). 아래 '광고 선언' 절 |
| `health` | 워치독 기준: `max_gap_hours`, `max_failure_streak`. `max_unpublished_days`는 지금 **쓰이지 않는다**(UNPUBLISHED는 첫 발생부터 경고하도록 바뀌었다 — 호환을 위해 필드만 남김) |

시크릿 이름은 블로그마다 고유해야 하고(`shared_secrets` 예외), 값 전달은 [§6](#6-시크릿-전달-방식)을 따른다.

### 광고 선언(`ads`)과 신규 채널의 광고 원칙

**원칙(운영자 승인 2026-10-27, D6): 신규 채널(한글 Blogger·티스토리·네이버)은 품질 게이트를 통과하기 전까지 광고를 켜지 않는다 — 플랫폼 화면에서도.** 광고 정책의 반복·중대한 위반은 사이트가 아니라 계정 단위 조치(정지·폐쇄)로 이어질 수 있어, 한 채널의 문제가 같은 계정의 다른 사이트로 번지지 않게 채널을 광고 없이 시작하게 하는 구조적 장치다. 광고 정책은 사람의 검토나 큐레이션 없는 자동 생성 콘텐츠에 광고를 두지 말라고 안내한다(2026-10-27 채널 관리 계획 보고 §1·§7). 레지스트리의 `ads`는 광고를 실제로 켜고 끄는 스위치가 아니라 **의도 선언 + 실수 방지**다 — 광고는 각 플랫폼 화면(Blogger 레이아웃 등)에서 운영자가 켠다.

| 값 | 뜻 | 쓸 수 있는 곳 |
|----|----|---------------|
| `off` | 광고가 없다. 새 채널의 시작값(`defaults.ads`) | 모든 플랫폼 |
| `pending_gate` | 품질 게이트를 통과하면 켜려는 곳. 아직 광고 코드는 없다 | 모든 플랫폼 |
| `on` | 광고 코드가 사이트에 들어 있다(AdSense 승인 대기 중이어도 `on`) | `jekyll-git`만(광고 코드를 이 저장소가 관리한다) |

- **규칙(레지스트리 검증, REG-1)**: ① `ads`는 위 세 값 중 하나, 생략하면 `defaults.ads` ② `platform`이 `jekyll-git`이 아니면 `on` 금지 ③ `ad_surface: true`도 `jekyll-git`에만 ④ `defaults.ads`는 `off`로 고정(`ads`를 적지 않은 새 블로그가 광고를 켠 채 시작하지 않게 한다).
- **선언과 사실의 일치(검증기 REG-5)**: `jekyll-git` 블로그는 광고 표면(`protected_paths`)의 파일에 광고 코드(`adsbygoogle`·`googlesyndication`·`ca-pub-숫자`)가 있으면 `ads`가 `on`이어야 하고, `ads`가 `on`이면 광고 코드가 있어야 한다. 광고 코드를 넣거나 빼는 변경과 `ads` 값 변경은 한 묶음이라 둘 다 T3(사용자 승인)다 — 광고 표면 파일 쪽은 검증기 AD-1이 커밋 메시지의 `Ad-Surface-Approved: <사유>`를 요구하고, `ads` 값 쪽은 같은 표시를 붙이는 정책이다(기계가 확인하지 않는다). **REG-5 의 한계**: 광고 표면 파일을 검증기의 텍스트 읽기(`read_text`)로 읽으므로 확장자가 `TEXT_EXT`(`.md`·`.py`·`.yml`·`.yaml`·`.json`·`.html`·`.htm`·`.js`·`.css`·`.txt`·`.xml` 등) 밖이거나 2MB(`MAX_TEXT_BYTES`)를 넘는 파일은 읽지 못해 그 안의 광고 코드를 보지 못한다 — 광고 표면(`protected_paths`)에 그런 파일을 두지 않는다.
- **지금 값**: `chance` = `on`(홈 `index.html`에 광고 스크립트가 있다. 글 페이지에는 없다), `blogger_macat` = `off`, `blogger_kcyoon` = `off`(`ad_surface: false`). `pending_gate`·`on`으로 올리는 편집은 T3다.
- **품질 게이트 기준(제안, 2026-10-27 채널 관리 계획 보고 §6 — 운영자 승인 전)**: ① 사람이 읽고 승인한 글 10편 이상 ② 표본 5편의 사실 확인 오류 0 ③ 가드레일 탈락·오탐 기록 검토 ④ 해당 플랫폼의 광고 정책 확인. 통과 판단과 `pending_gate` → `on` 전환은 운영자가 한다.

## 4. 단계별 계약

| 단계 | 입력 → 출력 | 실패 시 |
|------|-------------|---------|
| **Plan** | 레지스트리 → 매트릭스(`python -m pipeline.plan --platform P [--only KEY] [--include-off]` — `--include-off`는 '인증 점검만 실행' 수동 실행 전용으로 정지한 블로그도 대상에 넣는다) | 레지스트리 검증 실패, `--only`에 레지스트리에 없는 key나 `--platform`과 다른 플랫폼의 key를 준 경우 → 워크플로 중단(종료 코드 1, 유효 key 안내). 대상(수동 실행이면 지정한 블로그, 아니면 그 플랫폼 전체)이 모두 `mode: off`이거나 없으면 대상 0개로 초록 + `::notice::`·요약을 남기고 `generate` 잡은 건너뜀 |
| **Auth check** | (Blogger 초안함 업로드·즉시 게시일 때만, 글을 만들기 **전에** 1회) 토큰 갱신 → `blogs.get` → 돌려준 블로그 주소가 레지스트리 `url`과 같은지. **쓰기 없음**(`pipeline/auth_check.py`) | 하나라도 실패하면 Gemini 호출·업로드·게시 없이 종료 1 또는 2(분류별 기준은 §4-1 '인증 점검 실패의 분류'), 이력에 `publish_failed`. 연습 실행은 Blogger에 접속하지 않는다 |
| **Topic** | 프로필 시드·이력·타 블로그 제목 → 주제 1개 | 시드가 바닥나면 LLM으로 주제를 확장한다(확장 실패는 `llm_failed`, **종료 코드 1**). 그래도 없으면 `skipped_no_topic` 기록 후 정상 종료(경고 주석). 쿨다운·금지 주제·교차 중복 필터 통과 필수 |
| **Generate** | 프롬프트 + 프로필 추가 규칙 → 원문 | LLM 전부 실패 → `llm_failed` 기록, **종료 코드 1**(Actions 실패 알림) |
| **Gate** | 원문 → 파싱 → HTML 정화 → 정책·중복 검사 | 탈락 사유를 넣어 재작성(최대 `max_attempts`). 끝내 탈락이면 `rejected` 기록, 게시·저장 없음, 정상 종료 |
| **Publish** | 정화된 HTML + 면책 문구 → 어댑터. `mode: auto`면 `draft=False`로 즉시 게시(`posted`), `mode: draft`+게시용 시크릿이면 `draft=True`(`isDraft`)로 Blogger 초안함에 업로드(`draft_uploaded`). 응답에 글 ID·주소(`url`)가 비어 있거나 요청과 다른 상태(초안인데 공개 등)면 실패로 본다 | 인증·API 오류 → `publish_failed` 기록, **종료 코드 1**. 어댑터가 분류하지 못한 예외(`PublishError` 밖)도 같다. 초안은 남긴다 |
| **Package** | (`mode: package`만) 정화된 HTML + 면책 문구 + 게이트 결과 → 소독(멘션·이슈 참조·펜스·HTML, G-L9) → GitHub 이슈 1개(`package_issued`, 공개 없음). 글을 만들기 **전에** 같은 채널에 열린 `초안` 이슈 수를 읽어 3건 이상이면 건너뛴다(적체 방지). 같은 초안(본문 첫 줄의 숨은 표지 `draft-id`)의 이슈가 이미 있으면 새로 만들지 않는다(멱등). 연습 실행은 본문만 만들어 실행 요약에 보이고 GitHub를 부르지 않는다 | 점검·생성 실패 → `publish_failed` + `PACKAGE_FAILED`(분류별 종료 코드: 권한·길이 초과 **2**, 그 밖 **1**, §4-1 분류표). 만든 글은 저장소 초안 파일로 남는다. 열린 초안 3건 이상은 실패가 아니라 `PACKAGE_BACKLOG`(종료 0) |
| **Record** | 이력 항목 추가(최근 200개 유지) + 초안 파일 저장(최근 120개) | 이력 파일이 손상돼 있으면 **덮어쓰지 않고** 종료 코드 1 (fail closed) |
| **Deploy** | (`jekyll-git`) 커밋 push 후 `pages.yml` dispatch(승인 흐름 `pr`은 dispatch 를 하지 않는다: PR 병합이 push 이벤트를 만들어 배포를 실행시킨다 — §4-4). 배포 뒤 `verify` 잡이 새 글의 공개 주소가 열리는지 확인(§4-3) | dispatch 실패 시 워크플로 실패. 새 글이 마감(12분)까지 공개 주소에서 안 열리면 배포 실행이 빨강이 되어 워치독이 알린다 |
| **Observe** | 워치독: 이력·마지막 커밋·최근 실행 → `[Watchdog]` 이슈 | 이슈 생성/자동 해소 |

종료 코드: `0` 정상(건너뜀 포함) / `1` 인프라 실패 / `2` 설정 오류.

## 4-1. 건너뜀·종료 규약 (스킵 코드)

"할 일이 없어서", 또는 "조건이 안 맞아서" 끝나는 실행도 **왜** 끝났는지 남긴다. 초록 체크는 "프로그램이 오류 없이 끝났다"는 뜻일 뿐 "글이 올라갔다"는 뜻이 아니기 때문이다(2026-10-25 진단: Chance는 슬롯 시각이 된 스케줄 실행 13회 중 11회가 글 없이 초록으로 끝났고, Blogger는 게시 시크릿이 없어 초안만 만든 채 초록이었다).

한 줄 규격: `[SKIP] code=<코드> key=값 ...` — Actions 로그에서 `[SKIP]`로 찾고, 같은 코드가 실행 요약(Step Summary)에도 쓰인다. Blogger 러너(`pipeline/run.py`)의 실행 요약은 어느 경로든(초안 패키지 경로 포함: `### [티스토리] 블로그 이름`) 첫 줄이 `### [채널 라벨] 블로그 이름`(레지스트리의 `channel.label`·`name`, 예: `### [Blogger 영문] Blogger (macat0722)`·`### [Blogger 한글] Blogger (kcyoon)`, `summary_head()`)이고 그 아래 줄(`- 결과: **코드** — …`·URL·안내·Gemini 호출)은 이 규약의 코드와 같다(2026-10-27 이전에는 첫 줄이 블로그 key였다).

| 수준 | 의미 | 처리 | 종료 | 코드 |
|------|------|------|------|------|
| 정상 건너뜀 | 지금 할 일이 아님 | 초록 + 로그 한 줄(Blogger의 `PAUSED`·`MODE_OFF`·`DAILY_CAP`·`UPLOAD_SKIPPED`는 `::notice::` 주석도) | 0 | `OUT_OF_WINDOW`(첫 게시 시각 전), `ALREADY_PUBLISHED`(그 슬롯 글이 이미 있음), `DRAFT_PENDING`(승인 흐름: 그 슬롯의 초안이 승인(PR 병합)을 기다리는 중이거나 닫혀 폐기됨 — 같은 슬롯을 다시 만들지 않음, §4-4), `PAUSED`(`PIPELINE_PAUSE`), `MODE_OFF`(레지스트리 mode off), `DAILY_CAP`(Blogger 하루 상한 소진), `DRY_RUN`(연습 실행), Blogger: `UPLOAD_SKIPPED`(Blogger 초안함에 올릴 차례인데 게시용 시크릿이 하나도 없어 **저장소 파일에만 저장** — 글은 만들어지고 이력은 `draft`, 요약에 등록할 시크릿 **이름**이 남는다), 초안 패키지: `PACKAGE_BACKLOG`(같은 채널에 열린 `초안` 이슈가 3건 이상이라 **새 초안을 만들지 않음** — Gemini·이슈·이력 없음, `::notice::`와 요약. 이슈를 발행해 닫으면 다음 실행부터 풀린다) |
| 경고 | 게시하려 했는데 못 했지만 다음 실행에서 다시 시도 | 초록 + `::warning::`(노란 주석) + 요약 | 0 | `ALL_REJECTED`(후보는 있었으나 Gemini 건너뜀·제목 유사·본문 검증 탈락으로 전부 탈락. 수동 실행은 예외로 빨강), `ALL_DUPLICATES`(검증된 기사는 있었지만 모두 이미 쓴 글과 비슷 — 뉴스가 뜸한 때), `NO_CANDIDATES`(시간 상한으로 일부 분야만 시도하고 후보 없음), `NO_MATCH`(수동 주제 요청과 연결되는 검증된 기사 없음), `DRAFT_CHECK_FAILED`(승인 흐름: 슬롯 시각인데 초안 브랜치를 확인하지 못해(`git ls-remote` 실패) 이번 실행만 건너뜀 — 다음 실행이 다시 확인, §4-4), Blogger: `NO_TOPIC`(시드·확장 후에도 쓸 주제 없음), `GATE_REJECTED`(재작성 끝에도 게이트 탈락) |
| 실패 | 발행하려던 실행이 0건으로 끝난 이상 신호 | **빨강** + `::error::` + 요약 | 1 | `ALL_LANES_EMPTY`(모든 분야에 검증을 통과한 기사가 한 건도 없음), `SOURCES_UNREACHABLE`(시도한 뉴스 소스가 모두 수집 실패 — 네트워크·소스 장애), `DRAFT_BRANCH_ONLY`(승인 흐름: 초안 브랜치와 이력은 올라갔는데 승인 PR 을 열지 못함 — 저장소 설정 'Allow GitHub Actions to create and approve pull requests'가 꺼져 있는 경우 등. 글은 잃지 않았고 다음 실행의 정리가 PR 을 다시 연다. `초안 올리기` 단계의 실행 요약과 고정 문장 `::error::`에 남는다, §4-4), Blogger: `LLM_FAILED`·`EXPAND_FAILED`(주제 확장 실패)·`PUBLISH_FAILED`(게시·초안함 업로드 실패. 어댑터가 분류하지 못한 예외도 포함, `reason=`으로 분류하고 `target=draft`/`publish`로 구분)·`HISTORY_WRITE_FAILED`(업로드·게시는 끝났는데 이력 파일을 쓰지 못함 — 글 ID·주소는 로그와 요약에 남고, 같은 날 다시 실행하기 전에 Blogger를 확인)·`AUTH_CHECK_FAILED`(인증 점검 실패 중 종료 1인 분류: `auth_expired`·`network`·`bad_response`·`api_error`·`unexpected` — 아래 분류표), 초안 패키지: `PACKAGE_FAILED`(GitHub 이슈를 읽거나 만들지 못함 중 종료 1인 분류: `network`·`bad_response`·`api_error`·`unexpected`, `stage=precheck`(글을 만들기 전 점검)·`issue`(이슈 만들기) — 아래 분류표) |
| 설정 오류 | 사람이 고쳐야 하는 설정 | **빨강** + `::error::` + 요약 | **2** | Blogger `SECRETS_MISSING`(즉시 게시인데 게시용 시크릿이 없거나, 초안함 업로드인데 **일부만** 있음 — 글을 만들기 전에 멈춘다, 초안·이력 없음, 시크릿 **이름**만 표시)·`INVALID_PUBLISH`(`BLOGGER_PUBLISH` 값을 알 수 없음)·`TOPIC_BLOCKED`(수동 `topic`이 프로필의 금지 주제 낱말에 걸림 — Gemini·Blogger를 부르기 전에 멈추고 이력·초안은 남지 않는다. 걸린 낱말은 로그·요약에 남고 `::error::` 주석은 입력 문자열이 없는 고정 문장이다)·`AUTH_CHECK_FAILED`(인증 점검 실패 중 종료 2인 분류: `auth_failed`·`blog_mismatch`)·레지스트리 검증 실패, 초안 패키지: `SECRETS_MISSING`(`GITHUB_TOKEN`·`GITHUB_REPOSITORY` 없음 — Gemini를 부르기 전에 멈춘다)·`INVALID_PUBLISH`(이 채널에서 `BLOGGER_PUBLISH`·`--publish`를 씀)·`AUTH_CHECK_UNSUPPORTED`(`--auth-check` — 점검할 계정 인증이 없다. 조용히 이슈를 만들지 않으려고 거절한다)·`PACKAGE_FAILED`(분류 `auth_failed`·`too_long`, `stage=build`는 연습 실행에서 본문이 한도를 넘음) |

승인 흐름(`publish_flow: pr`)에서 글을 만든 실행의 결과는 `PUBLISHED` 대신 `DRAFT_CREATED`(초록, 요약 '초안을 만들었습니다')이고, 올리기 단계의 요약은 `DRAFT_OPENED`(PR 을 열었음, 종료 0) 또는 `NO_DRAFT`(이번 실행에서 만든 초안이 없음, 종료 0)이다. 위 표의 `DRAFT_*` 코드와 함께 §4-4에 정리했다.

**Blogger 실행(`pipeline/run.py`)의 처리 순서**: `PIPELINE_PAUSE` → `mode: off` → `BLOGGER_PUBLISH` 값 검사(알 수 없으면 종료 2) → 게시용 시크릿 점검(즉시 게시인데 없거나 초안함 업로드인데 일부만 있으면 종료 2) → **수동 `topic` 금지 주제 검사**(프로필의 `banned_topic_patterns`에 걸리면 `TOPIC_BLOCKED`, 종료 2 — 이력 읽기보다 앞이라 상태 파일 문제에 가리지 않는다) → 초안함 업로드인데 게시용 시크릿이 하나도 없으면 `UPLOAD_SKIPPED`로 저장소 파일에만 저장(주제 검사 뒤에 둔다 — 막힌 주제로 아무것도 저장하지 않고 멈추는 실행에 '저장합니다' 안내가 먼저 나오면 모순이다. D-64 ⑦ N-7) → 이력 읽기(손상이면 종료 1) → 하루 상한(`--topic` 지정은 이것을 우회하지만 금지 주제 검사는 우회하지 못한다) → LLM 키(없으면 종료 2) → **인증 점검**(업로드·게시일 때만, 실패하면 종료 1 또는 2) → 주제 → 생성·게이트 → 연습 실행/즉시 게시/초안함 업로드/저장소 초안. 인증 점검을 글 생성 앞에 둔 이유: 인증이 깨진 날 무료 Gemini 호출을 쓰지 않고, 같은 계정의 다른 블로그 ID 를 넣은 사고를 글을 만들기 전에 막는다.

**초안 패키지 실행(`mode: package`, 티스토리·네이버)의 처리 순서**: `PIPELINE_PAUSE` → `mode: off` → `--auth-check` 거절(`AUTH_CHECK_UNSUPPORTED`) → `BLOGGER_PUBLISH` 값 검사(알 수 없거나 `auto`가 아니면 종료 2 — 이 채널에는 즉시 게시·초안함·파일만 저장이 없다) → **수동 `topic` 금지 주제 검사** → 이력 읽기(손상이면 종료 1) → 하루 상한(`package_issued`도 센다, `--topic` 지정은 우회) → LLM 키(없으면 종료 2) → **초안 패키지 사전 점검**(연습 실행이 아닐 때만: `GITHUB_TOKEN`·`GITHUB_REPOSITORY`가 없으면 종료 2, 같은 채널에 열린 `초안` 이슈를 읽어 3건 이상이면 `PACKAGE_BACKLOG`로 종료 0 — `--topic`도 이것은 우회하지 못한다, 읽기에 실패하면 `PACKAGE_FAILED stage=precheck`) → 주제 → 생성·게이트 → 이슈 만들기(연습 실행은 본문만 만들어 실행 요약에 보이고 GitHub를 부르지 않는다. 호출 0회). Blogger의 시크릿 점검·인증 점검은 하지 않는다(필요한 것은 Gemini 키와 워크플로가 넘기는 `GITHUB_TOKEN`뿐). 사전 점검을 글 생성 앞에 둔 이유는 Blogger의 인증 점검과 같다: 권한이 깨진 날 무료 Gemini 호출을 쓰지 않는다.

| 초안 패키지 실패 분류(`reason=`) | 뜻 | 종료 | 사람이 할 일 |
|----------------------------------|----|------|--------------|
| `auth_failed` | 401·403·404·410 — 이슈를 읽거나 쓸 권한이 없다·저장소를 못 찾는다·저장소의 Issues 기능이 꺼져 있다 | 2 | 워크플로 `permissions`에 `issues: write`가 있는지, Settings > Actions > General의 Workflow permissions, 저장소 Issues 기능을 확인 |
| `too_long` | 초안이 이슈 본문 한도(65,536자, 안전 한도 60,000자)에 안 들어간다 — **잘라서 올리지 않는다**(끊긴 글이 발행되지 않게). GitHub를 부르기 전의 입력 문제(`stage=build`, 연습 실행과 같다) | 2 | 프로필 `length.max_chars`를 줄인다 |
| `invalid_draft` | AI가 만든 제목이나 본문이 정화한 뒤 비었다(스크립트·태그뿐인 출력 — 게이트는 이런 제목을 거르지 않는다)거나 입력 모양이 어긋난다. GitHub를 부르기 전의 입력 문제(`stage=build`)라 이슈는 만들어지지 않았다 | 2 | 로그를 확인한다. 다음 실행이 새 글을 만든다. 되풀이되면 프로필의 제목·본문 규칙을 점검 |
| `network` | 연결 실패·시간 초과(읽기는 2번 더 시도한 뒤에도). **이슈 만들기(`stage=issue`)에서는 만들어졌는지 모른다** | 1 | 이슈 목록(라벨 `초안`)을 먼저 확인한 뒤 필요하면 다시 실행. 같은 요청을 자동으로 다시 보내지 않는다 |
| `bad_response` | 응답에 이슈 번호·주소가 없다, JSON이 아니다. **이슈 만들기에서는 만들어졌을 수 있다** | 1 | 이슈 목록에서 초안이 만들어졌는지 확인한 뒤 다시 실행 |
| `api_error` | 429·5xx(읽기는 재시도 뒤에도), 호출 한도, 그 밖의 HTTP 오류. 이슈 만들기에서 **4xx(429 포함)는 거절된 것이라 만들어지지 않았고**, 5xx는 만들어졌는지 모른다 | 1 | 로그를 확인하고 다시 실행(5xx면 먼저 이슈 목록 확인) |
| `unexpected` | 어댑터 밖의 예외 | 1 | 로그를 확인 |

**이슈 만들기 요청은 한 번만 보낸다(자동 재시도하지 않는다) — 만들어졌는지 모호하면 멈춘다**: 서버가 이미 이슈를 만들었는데 응답만 잃은 경우(시간 초과·연결 끊김·502 등) 같은 요청을 다시 보내면 같은 글의 이슈가 둘이 되기 때문이다. 그래서 모호한 실패(응답을 못 받음·5xx·이상한 응답)는 3초 기다렸다가 같은 초안 번호(숨은 표지)를 **한 번만** 찾는다 — 있으면 그 이슈를 결과로 쓰고(성공, `[참고]` 줄), 없거나 찾는 읽기도 실패하면 다시 만들지 않고 `PACKAGE_FAILED`(종료 1)로 멈추며 안내에 '초안 이슈가 만들어졌을 수 있으니 재실행 전에 라벨 `초안` 이슈 목록을 확인하세요'가 붙는다. HTTP 4xx로 거절된 실패(권한·검증·호출 한도)는 만들어지지 않았음이 확실해 그 안내 없이 바로 실패로 끝나고 다음 실행이 다시 한다. 이슈를 만들다 실패하면 이력은 `publish_failed`(이슈 번호 없음 — 하루 상한에 세지 않는다)이고 만든 글은 저장소 초안 파일에 남는다. 표지의 해시는 제목·본문에서 만들어지므로 이 멱등은 **같은 글을 다시 올리려는 시도**만 막는다 — 같은 날 다른 글이 만들어지면(이력이 사라진 뒤의 재실행 등) 이슈가 또 생긴다.

글을 어디까지 보내는지(전달 방식)는 `BLOGGER_PUBLISH`(수동 실행 입력 `publish`)와 레지스트리 `mode`로 정해진다. 정기 실행은 입력이 비어 `mode`를 따른다:

| `BLOGGER_PUBLISH` | `mode: draft` | `mode: auto` |
|-------------------|---------------|--------------|
| 비어 있음 · `auto` (정기 실행) | Blogger 초안함에 업로드 | 즉시 게시 |
| `draft` (수동 입력 기본값) | Blogger 초안함에 업로드 | Blogger 초안함에 업로드 |
| `publish` (`on`·`1`·`true`·`yes`) | 즉시 게시 | 즉시 게시 |
| `off` (`0`·`false`·`no`) | 저장소 파일에만 저장 | 저장소 파일에만 저장 |
| 그 밖의 값 | 설정 오류(종료 2) | 설정 오류(종료 2) |

초안함에 올리는 글은 공개되지 않는다. 운영자가 Blogger 화면에서 확인한 뒤 직접 게시한다. 저장소의 `_blogger_drafts/` 사본은 어느 전달 방식에서도 그대로 남는다. 연습 실행(`dry_run`)은 어느 쪽이든 Blogger에 접속하지 않는다.

게시 대상 실행이 이유·기록 없이 초록으로 끝나는 경로는 없다(조건 12,960가지 열거로 확인한 독립 검증, 2026-10-25. 초안함 업로드 모드를 넣은 뒤에는 `tests/test_draft_upload.py`가 모드×입력×시크릿×하루 상한 격자와 인증 점검→글 생성→게시 단계 경로를 기준 모델과 비교하며 같은 불변식을 확인한다). 하루 상한은 게시되지 않은 초안과 초안함에 올린 초안도 센다(`posted`·`draft`·`draft_uploaded`·`generated_unpublished`. 실패·탈락한 실행은 세지 않는다. `BLOGGER_PUBLISH=off` 수동 실행은 같은 날 정기 게시를 `DAILY_CAP`으로 건너뛰게 한다 — 상한의 의미 유지는 T3). 같은 글이 두 번 올라가는 것은 이력(하루 상한과 제목 중복 게이트 DUP_SAME)으로 막는다. 그래서 업로드·게시가 끝나면 **이력을 먼저 쓰고** 저장소 초안 파일(감사용 사본)을 나중에 쓴다: 사본 저장이 실패해도 이력은 남고(`::warning::`, 올라간 글이 없는 저장소 파일 전용 실행이면 빨강), 이력 쓰기가 실패하면 예외로 죽지 않고 글 ID·주소를 로그와 요약에 남긴 채 빨강(종료 1, `HISTORY_WRITE_FAILED`)으로 끝나며 같은 날 다시 실행하기 전에 Blogger를 확인하라고 알린다(이 경우에는 이력이 없어 상한이 막아 주지 못한다). 운영자가 Blogger에서 초안을 지웠는지는 알 수 없다. `mode: draft`여도 수동 실행에서 `publish` 입력을 `publish`로 고르면 즉시 게시한다(기존 동작이며, 막을지는 T3 결정). 로그·요약에 쓰는 외부·AI 유래 문자열(제목·사유·예외 문구)은 `pipeline/console.py`의 `one_line()`(한 줄로 접고 `::`·`##[`를 위치와 상관없이 무력화)·`md_cell()`(요약 표용 마크다운 이스케이프)을 거치고, `::warning::`·`::error::` 주석에는 고정 문장만 쓴다. 오류 문구에서는 비밀 모양 패턴과 이 실행이 가진 실제 시크릿 값(블로그 ID·클라이언트 ID·시크릿·refresh token)을 글자 그대로 가린다(`pipeline/publishers/base.py` `redact()`).

**인증 점검 실패의 분류와 종료 코드**(`pipeline/auth_check.py`, [`ENGINEERING_GUIDE.md`](./ENGINEERING_GUIDE.md) R6의 '설정 오류 2 / 인프라 실패 1'): 2는 사람이 설정(블로그 ID·계정 권한·클라이언트 값)을 고쳐야 하고 다시 실행해도 같은 결과인 실패, 1은 시간이 지나 생기는 외부 상태(토큰 만료·폐기)나 일시 오류(네트워크·API 오류)다. 로그에는 `[SKIP] code=AUTH_CHECK_FAILED reason=<분류> exit=<종료 코드>`와 고정 문장의 `::error::`가, 이력에는 `publish_failed`(분류가 `reasons[0]`)가 남고 Gemini·업로드·게시는 하지 않는다. 블로그 주소가 다를 때 응답의 주소·이름은 같은 계정의 다른 블로그 정보가 공개 로그에 남지 않도록 출력하지 않는다. **고정 문장·원인 줄·실행 요약 속 시크릿 이름은 그 블로그 항목(`blog["secrets"]`)의 이름이다** — 영문은 `BLOGGER_*`, 한글은 `BLOGGER_KO_*`(`auth_check.sentence_for(code, secrets)`가 문장의 자리표시자를 채우고, 어댑터는 `secret_names`로 블로그 ID 형식 안내를 채운다. 이름을 받지 못하면 영문 이름). 한글 실행의 실패를 보고 영문 시크릿을 고치러 가는 일이 없게 한 것이다(독립 검증 N3). 아래 표의 시크릿 이름은 영문 Blogger 기준이고 한글은 `BLOGGER_KO_*` 로 읽는다.

| 분류(`reason=`) | 뜻 | 종료 | 사람이 할 일 |
|-----------------|----|------|--------------|
| `auth_expired` | 토큰 갱신이 `invalid_grant`·만료·폐기로 거부됨 | 1 | OAuth 동의 화면이 'In production'인지 확인하고 토큰을 새로 받아 `BLOGGER_REFRESH_TOKEN` 시크릿을 갱신 |
| `auth_failed` | 토큰 갱신의 그 밖의 거부(클라이언트 ID·시크릿 불일치 등) 또는 `blogs.get`의 400(블로그 ID 형식 오류로 보임)·401·403·404(권한 없음·블로그 없음) | 2 | `BLOGGER_BLOG_ID`·`BLOGGER_CLIENT_ID`·`BLOGGER_CLIENT_SECRET` 시크릿, Blogger API 사용 설정, 로그인한 계정의 블로그 권한을 확인 |
| `blog_mismatch` | 인증은 통과했지만 돌려준 블로그 주소가 레지스트리 `url`과 다름(스킴·`www.`·끝 슬래시·국가별 blogspot 도메인 차이는 무시) | 2 | `BLOGGER_BLOG_ID`가 이 블로그의 ID인지 확인(커스텀 도메인이면 레지스트리 `url`을 고친다) |
| `network` | 연결 실패·시간 초과(재시도 2회 뒤에도) | 1 | 잠시 뒤 다시 실행 |
| `bad_response` | 응답에 필요한 값이 없음(`blogs.get`에 `url` 없음 등) | 1 | 로그를 확인하고 다시 실행 |
| `api_error` | 그 밖의 HTTP 오류(429·5xx는 재시도 2회 뒤에도), 403이지만 사유가 호출 한도(쿼터·속도 제한: `rateLimitExceeded` 등)인 것, 알 수 없는 분류 | 1 | 로그를 확인하고 다시 실행 |
| `unexpected` | 어댑터 밖의 예외(라이브러리 미설치 등) | 1 | 로그를 확인 |

게시 단계의 실패(`PUBLISH_FAILED`)는 같은 분류 이름을 쓰지만 종료 코드는 항상 1이다(글을 올리다 실패한 것은 인프라 실패로 본다).

**단독 인증 점검**(`python -m pipeline.run --blog KEY --auth-check`, 워크플로 수동 입력 `인증 점검만 실행`, 환경변수 `BLOGGER_AUTH_CHECK=1`): 글을 만들지 않고 위의 인증 점검만 한다.

- 쓰기 0(이력·초안·저장소 커밋이 없다), Gemini 호출 0회(Gemini 키도 필요 없다). `BLOGGER_PUBLISH`·`--topic`·하루 상한은 읽지 않는다
- 정지(`mode: off`) 중에도, 연습 실행(`dry_run`)이 켜져 있어도 실제로 점검한다(쓰기가 없고, 시크릿을 등록한 직후 mode 를 켜기 **전에** 확인해야 하기 때문이다). `PIPELINE_PAUSE`는 따른다(`PAUSED`, 종료 0). 워크플로에서는 `plan`이 `--include-off`로 정지한 블로그도 대상에 넣는다
- 종료 코드는 위 분류표와 같다: 0 통과(`::notice::`와 요약 `AUTH_CHECK_OK` — 확인한 시크릿 **이름**만 보이고 값은 없다) · 1 인프라(`auth_expired`·`network`·`bad_response`·`api_error`·`unexpected`) · 2 설정(`SECRETS_MISSING` — 게시용 시크릿이 하나도 없으면 요약에 '시크릿 없음', 일부만 없으면 '시크릿 일부 없음'; `auth_failed`; `blog_mismatch`)
- 시크릿을 등록한 직후와 토큰을 새로 받은 직후에 1회 실행한다. **주 1회 정기 점검은 새 예약(cron) 작업이라 T3**이므로 이번 변경에 넣지 않았다. 후속 작업에서 기존 워치독 실행에 붙이는 방안을 먼저 검토한다(새 예약을 만들지 않는 쪽)

위 코드는 **실행 전체의 결과**다. 분야 하나가 비었을 때는 폴백으로 다음 분야로 넘어가기 전에 `[SKIP] code=LANE_EMPTY lane=… sources=… failed=… fetched=… passed=… reasons=…` 한 줄을 남겨 왜 비었는지(소스 수, 수집 실패 수, 받은 기사 수, 통과 수, 탈락 사유 개수)를 알 수 있게 한다. 폴백으로 정상 발행한 실행에도 이 줄이 찍히므로 로그 검색은 `code=LANE_EMPTY`(분야 단위)와 실행 결과 코드를 구분해서 한다.

**Chance 기사 탈락 사유 코드**(`generator.py` `DROP_LABELS`, 소스별 `소스 X: N건 중 M건 사용 (탈락: …)` 줄과 요약 표에 같은 코드):

| 코드 | 뜻 |
|------|----|
| `NO_TITLE` | 제목 없음 |
| `NOT_TECH` | 기술 키워드가 아님(`tech_filter` 소스만) |
| `EXCLUDED` | 소스별 제외 규칙(`exclude_title`)에 걸림 — 약관이 빼라고 한 것, 글감이 못 되는 공지·퀴즈 등 |
| `OFF_TOPIC` | 제목·분류 태그에 이 분야 주제어(`topic_regex`)가 없음 |
| `AGE` | 72시간 초과(2026-10-26에 36시간에서 늘림 — 주말 공급 공백, D-62) |
| `UNTRUSTED` | 게시자가 그 분야의 신뢰 목록(`TRUSTED_SOURCE_DOMAINS`)에 없음 |
| `UNCHECKED` | 소스당 5건 검사 한도를 넘어 검사하지 않음 |
| `UNRESOLVED` | 기사 원문 주소를 얻지 못했거나 주소 모양이 안전하지 않음(공백·꺾쇠·따옴표·역슬래시·괄호·대괄호가 들었거나 http(s)가 아님). 구글 뉴스 링크 해석(`google` 키 소스)은 지금 쓰는 소스가 없다 |
| `HOST_MISMATCH` | 게시자와 원문 주소의 사이트가 다르거나 원문이 신뢰 목록 밖 |
| `SHORT_SUMMARY` | 요약이 100자 미만(원문 발췌도 실패) |
| `DUPLICATE` | 기존 글과 제목이 비슷(후보 단계) |

요약 표의 '검증 통과'는 소스당 10건 상한·소스 간 같은 제목 병합·`DUPLICATE` 제거를 하기 **전**의 수이고, '후보'는 그 뒤 최대 3건(`MAX_ATTEMPTS`)이다. 소스마다 '받은 기사 = 검증 통과 + 탈락 사유 합'이 성립하며, '검증 통과'가 있는데 '후보'가 0이면 전부 기존 글과 비슷했다는 뜻이다(`ALL_DUPLICATES`). 요약에는 그 실행에서 나온 코드의 뜻을 한 줄로 붙인다.

**Chance 소스와 약관 점검**(`generator.py`의 `NEWS_SOURCES`·`TRUSTED_SOURCE_DOMAINS`·`TERMS_BLOCKED_DOMAINS`, 2026-10-26 출처 개편): 소스는 분야마다 **약관을 읽고 이 용도(출처를 밝히고 요약해 새 글을 쓰는 것)가 허용된다고 판단한 직접 RSS**만 둔다. 2026-10-26에 미국 외 해외 소스(EU 집행위원회 계열·캐나다 통계청·영국 정부 GOV.UK)를 더하고 전자신문을 뺐다(조사 근거: [`docs/analysis/2026-10-26_overseas-sources.md`](./analysis/2026-10-26_overseas-sources.md)). 구글 뉴스 검색 소스 14개는 링크가 게시자 원문 주소로 풀리지 않아 통과율이 0.4%였기에 뺐다(약관 해석은 법률 판단이 아니다).

| 분야 | 소스(약관 점검 allowed) | 소스별 규칙 |
|------|------------------------|-------------|
| 과학·환경 | NASA | APOD·취재진 초대·행사 안내(`exclude_title`)와 사진 설명·Glenn 센터 음향 연구실 소개 쪽(`exclude_link`) 제외(센터 소식 기사는 살린다). NASA의 AI 이용 안내(정보를 NASA에 직접 귀속하지 말 것)에 따라 작성 지침 한 줄(`prompt_rule`)과 글 끝 고지문(`notice`, 정확성 면책 포함) |
| 과학·환경 | European Commission · Environment, European Commission · JRC | CC BY 4.0(집행위원회 법적 고지: 출처 표시·변경 표시가 조건). **Eurostat 소식(자체 고지가 따로 있음)·Horizon 매거진(기자 이름·바닥글 의무)·Press Corner 보도자료(재사용 조건을 확인하지 못함)는 주소로 뺀다**(`exclude_link`: `/eurostat/`·`/horizon-magazine/`·`/commission/presscorner/`), 연설·성명·선언 제목 제외, 모집·신청 안내는 Environment 만 제외. JRC는 국방·안보 분류 글 제외(`exclude_tags`). 글 끝에 인용 줄(`citation`: 제목·기관·날짜·원문 주소·© European Union·라이선스 링크)과 고지문(AI 작성·바뀐 부분 있음·집행위원회가 검토·보증하지 않음) |
| 과학·환경 | GOV.UK · Environment & Energy | 영국 정부(DESNZ·Defra) 뉴스 Atom. **OGL v3.0**: 출처 표시("Contains public sector information licensed under the Open Government Licence v3.0.")와 보증 암시 금지가 조건. 보도 기사(`/government/news/`)만 쓰고 연설·정책 문서·사례 소개는 `exclude_link`로, 인사·신청 안내·성명·선거·전쟁 소재·민감 주제는 `exclude_title`로 뺀다. 기사 페이지를 읽지 않는다(`no_page_fetch` — 메타 설명이 피드 요약과 같음). 글 끝에 인용 줄(제목·GOV.UK·날짜·원문 주소·OGL 문구와 링크)과 고지문(AI 작성·바뀐 부분·정부가 검토·보증하지 않음·공식 입장이 아님), 작성 지침(정부의 계획·주장과 확인된 사실 구분, 정당·선거·장관 평가 금지, 의학 조언 금지) |
| 사회·정책 | UN News — **보류(`pending`)** | 유엔에 알리는 일과 robots.txt 확인(D-63)이 끝날 때까지 읽지 않는다(로그에 `소스 UN News: 보류 — …` 한 줄). 풀면 'World News in Brief' 제외, 글 끝 고지문 |
| 사회·정책 | European Commission(소식), Statistics Canada · society | 집행위원회 소식: 국채 입찰 공지·모집 안내·위원 방문 예고·연설·성명·선거·정치광고·`democracy` 분류 글 제외(Pew와 같은 중립 원칙). 통계청: 교육·인구·범죄·원주민·이민·장애·주거 등 주제어(`topic_regex`)만, 기술 공지·부문 물가지수·자살·약물 과다복용·성폭력·살인·가정·친밀한 관계·성별 기반 폭력·아동 학대 제외. 통계청 약관 문구 `Adapted from Statistics Canada, …`(`citation`)와 고지문, 수치를 그대로 쓰라는 작성 지침(`prompt_rule`) |
| 문화·미디어 | Pew Research Center | 제목·분류 태그에 미디어·온라인 주제어가 있는 것만(`topic_regex`), 선거·정당·퀴즈·보고서 부속 쪽(`exclude_title`)과 뉴스레터 모음(`exclude_link`)·방법론·선거 분류 글(`exclude_tags`) 제외, 기사 페이지를 읽지 않음(`no_page_fetch`, Pew 약관의 스크래핑 금지), 약관 §2 인용 줄(`citation`)과 번역 면책 문장이 든 고지문 |
| 경제·일 | Federal Reserve(보도자료) | 제재·인가 승인·이의 없음 통보 건 제외, 글 끝 고지문. 그 건들을 빼면 주 1~2건이라 연준만으로는 대부분 비어 있어 아래 소스를 더했다(D-62) |
| 경제·일 | European Commission · Energy, Statistics Canada · economy | Energy: 평일 거의 매일 나오는 에너지·경제 소식(연설문·성명·위원 방문 예고·모집·의견 수렴 공지·Eurostat 소식·보도자료(Press Corner) 제외; 피드에 섞이는 EIB·ACER 기사는 신뢰 목록에 없어 떨어짐). 통계청: 소비자물가·고용·소매·무역·GDP 같은 대표 발표만(`topic_regex`), 부문 물가지수·공급 처리표·원자료 모음 제외 |
| 일상·마음 | Statistics Canada · daily life | 건강 보고서·출생·출산·삶의 질 같은 주제어만(`topic_regex`), 자살·약물 과다복용·마약성 진통제·폭력·학대 주제 제외. 의학 조언 없는 통계 해설만 쓴다(원문 수치를 그대로) |
| 기술·미래 | EU Digital Strategy(AI Act·디지털서비스법 소식) | 약 주 2건이라 기술·미래 글은 드물어졌다(여러 분야를 고르게 쓰려는 운영자 확인 2026-10-26). 사이트가 요약 앞에 붙이는 "Anonymous (not verified) 날짜" 잡음은 작성 지침으로 쓰지 않게 한다. **전자신문(콘텐츠 이용에 정식 계약·사용료 필요)·AI타임스("AI학습 및 활용 금지") 는 운영자 결정(2026-10-26)으로, Ars Technica·IEEE Spectrum은 robots.txt가 AI 크롤러(ClaudeBot 등)를 막기 때문에 접근하지 않는다**(`TERMS_BLOCKED_DOMAINS`). 글감이 한 건도 안 되던 TechCrunch·The Verge와 간접 경로 Hacker News도 뺐다 |
| 기술·미래 | GOV.UK · Science & Technology | 같은 약관·규칙의 영국 정부(DSIT·AI Security Institute) 뉴스 Atom. 한 달에 서너 건이라 보충용 |

- 소스마다 `terms`(`status` — `allowed` 허용으로 읽음 / `pending` 허용이지만 채우지 못한 조건(`blocker`)이 있어 읽지 않음 / `unverified` 못 읽었거나 불명확한 기존 소스, 확인한 날짜, 근거 쪽 주소)를 적는다. `unverified`(약관 불명확 유예)는 지금 쓰는 소스가 없고(마지막이던 전자신문을 2026-10-26에 뺐다) 시험(`SourceListTest`)이 늘리지 못하게 막는다. 금지로 읽힌 매체는 소스에 두지 않고 `TERMS_BLOCKED_DOMAINS`에 올린다.
- **BBC·Guardian·Nature·MIT Technology Review·AI타임스**는 약관이 이 용도(광고가 붙는 사이트에서 RSS 제목·요약을 AI에 주어 새 글을 쓰는 것)를 금지하거나 허가가 필요하다고 읽혀 `TERMS_BLOCKED_DOMAINS`에 올렸다. 소스에도 신뢰 목록에도 없고, 실수로 신뢰 목록에 다시 들어와도 `_trusted_domain`이 거부한다(시험으로 고정). 허가를 받으면 이 목록에서 빼고 `terms`를 allowed로 적는다.
- **Ars Technica·IEEE Spectrum**은 robots.txt가 AI 관련 크롤러를 이름으로 막아(ClaudeBot·anthropic-ai·CCBot 등. 검증 A 재집계: `Disallow: /` 대상이 Ars 34개 중 AI 관련 약 30개, IEEE 33개 중 약 21개이고 IEEE는 사용자 요청형 일부를 명시 허용) 운영자 결정(2026-10-26 "AI 크롤러를 막는 사이트는 접근하지 않는 원칙")으로 같은 목록에 올렸다. 같은 날 남은 소스의 robots.txt도 읽었다: NASA는 제한이 없고, Pew는 `Content-Signal: ai-train=yes, ai-input=yes`로 이용을 명시 허용하고, 연준은 robots.txt가 없고, 전자신문은 제한이 없다(GPTBot 차단 줄은 주석 처리). UN News는 일반 봇에 이 피드 경로(`*/news/`)를 허용하지 않아 이미 보류다.
- **전자신문**은 콘텐츠 이용 안내(info.etnews.com 콘텐츠 구매 페이지)가 영리·비영리 정보서비스에 사전 협의·정식 계약을 요구하고 수집해 자체 DB를 만들면 저작권 침해이며 무단 사용에는 사용료의 30배 배상을 안내한다. 운영자 결정(2026-10-26 "계약·사용료는 '무료 자동화 기반' 취지에 맞지 않음")으로 소스·신뢰 목록에서 빼고 `TERMS_BLOCKED_DOMAINS`에 올렸다(뉴스 기사를 AI가 각색하는 방식은 어느 매체나 같은 종류의 위험이라, 출처는 약관이 재가공을 허용한 공식·공공·개방 라이선스 자료 중심으로 옮긴다). 그 출처로 이미 공개된 글 1쌍은 운영자 승인(2026-10-26 채팅)을 받아 `published: false`로 비공개 전환했다(PR #36, 삭제 없음).
- 수집 루프는 피드 주소의 호스트가 `TERMS_BLOCKED_DOMAINS`에 있는 소스를 읽지 않고(로그에 `약관상 접근하지 않는 도메인` 한 줄), 기사 주소에 공백·꺾쇠·따옴표·역슬래시·괄호·대괄호가 있으면 `UNRESOLVED`로 버린다(글의 출처 목록·인용 줄에 그대로 들어가 마크다운·HTML이 되지 않게).
- **공통 작성 지침(글 근거 보강, D-77)**: 출처가 있는 모든 글감의 프롬프트에는 소스와 상관없이 `generator.py`의 `GROUNDING_RULES` 세 줄이 붙는다(`build_post_prompt`가 '출처를 추정해 만들지 마세요' 줄 바로 뒤, 소스별 `prompt_rule` 앞에 넣는다): ① 통화·단위를 환산하거나 숫자를 반올림·추정하지 않고 요약의 수치·단위·기준 시점을 그대로 쓴다(한국어 글에서 유로를 원화로 바꾸는 것도 금지) ② 요약에 없는 평가 기준·심사 절차·일정·시행 시기·금액·예산 대비 배수·참여 국가 수·법적 효력을 쓰지 않는다(배경은 '일반적으로 …'로 일반론임을 드러내고 구체적인 수치·고유명사는 지어내지 않는다) ③ 출처에 없는 내용을 출처 기관이 말하거나 밝힌 것처럼 쓰지 않는다. 소스별 `prompt_rule`에는 그 소스 고유 조건(약관의 보증 암시 금지·링크 글자·구분 문장 등)만 남기고 같은 말을 두 곳에 적지 않는다 — 집행위원회·GOV.UK 규칙의 '요약에 없는 시행 시기·금액·법적 효력' 문장과 통계청 규칙의 '반올림·환산·추정 금지, 원인·전망 귀속 금지' 문장은 공통 지침으로 옮겼다. 수집 방식(RSS 요약, 100자 미만이면 기사 페이지의 메타 설명, 본문 전문 수집 금지)은 바꾸지 않았다 — 원문 발췌를 읽을지는 운영자 결정이다(기본값 변경 없음). 지침은 모델이 어길 수 있어 병합 뒤 새 글을 눈으로 확인한다(`docs/DEFECT_REGISTER.md` D-77·관측 체크리스트). 시험: `tests/test_prompt_grounding.py`.
- 소스별 선택 키: `citation`(글 끝 인용 한 줄의 틀 — `{title}`·`{date}`·`{url}`, 소스 약관이 정한 형식, 고지문 앞에 붙임), `exclude_title`·`exclude_link`·`exclude_tags`(제목·기사 주소·피드 분류 태그 정규식, 맞으면 `EXCLUDED`), `topic_regex`(제목·분류 태그에 맞는 말이 없으면 `OFF_TOPIC`), `no_page_fetch`, `notice`(글 끝 고지문 ko·en — `add_discovery_metadata`가 글 언어(front matter `lang`, 없으면 한글 여부)에 맞춰 붙이고 이미 있으면 다시 붙이지 않는다), `prompt_rule`(글 작성 지침에 한 줄), `display_name`(글에 보이는 출처 이름, 생략하면 `name` — 한 게시자의 피드를 분야별로 나눠 읽을 때 `name`이 달라야 해서 둔다). 피드의 `<category>`(Atom은 `term`)는 `parse_feed`가 `categories`로 읽고, 글자가 자식 요소 안에 있는 Atom `type="xhtml"` 제목·요약(통계청)도 자식까지 이어 읽는다.
- 직접 RSS 항목의 `<source>` 태그(UN News는 피드 태그라인이 들어 있다)는 게시자 표시로 쓰지 않는다 — 게시자는 기사 주소의 호스트이고 출처 이름은 소스 이름이다. 구글 뉴스 해석 코드(`google` 키, `_resolve_article_url`)는 쓰는 소스가 없지만 시험이 있어 남겨 두었다.

**Chance 분야 폴백**: 슬롯 시각마다 6개 분야를 확률 가중 추첨 순서(`editorial_lane_order`, 첫 분야는 기존 추첨과 같음)로 늘어놓고, 앞에서부터 후보가 나올 때까지 시도한다. 이 단계는 Gemini를 부르지 않아 비용은 수집 시간뿐이다. `LANE_SEARCH_BUDGET_SECONDS`(기본 480초)가 지나면 새 분야도, 분야 안의 남은 소스도 시도하지 않는다(이미 시작한 소스 하나는 끝까지 기다리므로 수집은 상한 + 약 2분 안에 끝나고, 잡 제한은 20분이다). 시도한 소스가 전부 수집 실패면 시간과 무관하게 `SOURCES_UNREACHABLE`(빨강)이다. 글이 만들어지면 이력의 `lane`과 Gemini 프롬프트에는 실제로 후보가 나온 분야가 쓰인다.

**글 머리말(front matter)은 모델이 쓴 줄을 믿지 않는다(D-80)**: `validate_post_data`가 응답에서 머리말과 본문을 견고하게 가른 뒤(BOM·앞 공백·CRLF·`------`·여는 울타리 두 번·머리말 두 번·본문 앞의 `---` 줄을 걷어낸다) 모델이 쓴 머리말이 엄격 검사(첫 줄과 닫는 줄이 정확히 `---`, 한 줄 한 키, 키 중복 없음, 값이 안전한 모양, `title`은 한 줄 JSON 문자열, `layout` 줄이 있으면 정확히 post, YAML이 읽지 못하는 글자와 줄바꿈으로 읽는 U+0085·U+2028·U+2029가 없음)를 통과할 때만 그 줄을 보존하고, 아니면 구조화된 값(제목·분야·태그)으로 머리말을 처음부터 다시 쓴다(로그에 사유 한 줄). 우리가 쓰는 JSON 한 줄(제목·분야·태그와 엔진이 더하는 설명·출처 줄)에서는 U+0085·U+2028·U+2029를 `\uXXXX`로 이스케이프해 글자를 그대로 보존한다. 설명·출처 줄까지 더한 최종 글은 `front_matter_problems`(PyYAML 없이 정규식·JSON)로 한 번 더 검사해 문제가 있으면 그 후보를 거절한다. 한 줄 목록(`tags: [a, b]`)을 보는 정규식은 평문 항목이 공백으로 끝나지 못하고 `?`를 품지 못하며 큰따옴표 항목은 JSON이 아는 이스케이프만 쓴다(되돌아가기가 항목 수의 지수로 늘지 않게, 그리고 PyYAML·libyaml이 읽지 못하는 목록을 받아들이지 않게 — N1·N2). 저장소의 실제 글 전체는 `tests/test_posts_front_matter.py`가 같은 규칙으로 지킨다. **바이트 동일의 범위**: 머리말이 없는 응답과, 모델 머리말이 위 엄격 검사를 통과하는 LF 응답의 출력은 옛 함수와 바이트 단위로 같다. 그 밖은 일부러 다르다 — 따옴표 없는 `title`·post가 아닌 `layout`·평문 목록 항목의 `?`·날 U+0085/2028/2029는 머리말을 구조화된 값(`json.dumps` 한 줄 제목 등)으로 다시 쓰고(모델이 쓴 `date`·`published` 같은 다른 줄도 함께 버려진다), CRLF 응답은 머리말 줄 끝의 CR이 사라진다. **한계**: 머리말을 `yaml` 코드 블록으로 감싼 응답은 머리말 없는 응답으로 보아 코드 블록이 본문 앞에 남는다 — 그 안의 `layout:` 같은 줄이 본문 앞 세 줄(빈 줄 제외)에 있으면 최종 검사가 그 후보를 거절하고 그보다 뒤에 있으면 보지 못한다. `published`·`permalink` 같은 다른 Jekyll 키는 모양이 안전하면 그대로 믿는다(키 허용 목록은 두지 않았다).

후보 하나가 탈락해도 실행은 계속된다: Gemini가 만든 본문이 검증(한국어 1000자·영어 1500자 이상, 검증된 원문 링크 인용)이나 머리말 최종 검사에 못 미치거나 JSON을 못 맞추면 그 후보만 탈락시키고(이미지를 고르기 전에 검사하므로 Unsplash 호출을 쓰지 않는다) 다음 후보를 시도한다(최대 `MAX_ATTEMPTS`=3건). 예전에는 첫 후보의 본문이 얇으면 실행 전체가 빨강으로 끝났다(D-36). 모든 모델이 실패하는 Gemini 장애는 그대로 빨강이다. 실행 요약에는 후보 탈락(본문 검증·응답 형식) 건수와 사유, Gemini 모델 호출 횟수(`- Gemini 호출: N회(실패 K회)`, 무료 한도를 나눠 쓰기 위한 측정값)를 남긴다.

**Gemini 호출 기록**(`pipeline/llm.py`의 `CallLog`, 무료 한도 측정용): 무료 한도는 키가 아니라 프로젝트 단위라 Chance·Blogger·이슈 수정·수동 실행이 한 통을 나눠 쓰고, 실제 소비는 AI Studio 사용량 화면에서만 보인다. 그래서 세 실행기(Blogger `pipeline/run.py`·이슈 수정 `pipeline/edits/runner.py`·Chance `generator.py`)가 같은 기록 장치로 **요청 한 번마다** 로그 한 줄을 남긴다: `[GEMINI] label=<블로그 키·chance·issue-edit> purpose=<generate·topic-expansion·patch·image-queries·post> model=<요청 모델> result=<ok·429·5xx·empty·other> sec=<소요 초> served=<응답의 modelVersion> tokens=in:·out:·total: detail=<실패 사유>`. 실패 사유(`detail`)는 예외의 코드·상태와 구글 오류 본문의 한도 구분 필드(`quotaId`·`retryDelay`·`quotaMetric`)를 앞에 두고, 비밀을 먼저 가린 뒤(비밀 패턴, 구글 오류 본문의 프로젝트 번호 `project_number:…`·`projects/…`, 이 실행의 Gemini 키를 글자 그대로) 한 줄로 접어 600자까지 남긴다(예전에는 200~300자에서 잘려 일 한도와 분 한도를 가르는 필드와 재시도 대기 시간이 사라졌다). 실제 429는 한도 위반이 3개까지 나오므로(분당 토큰 → 분당 요청 → 일 요청 순으로 보고됨) 필드 순서는 일 한도 id(`…PerDay…`) → 재시도 대기(`retryDelay`) → 나머지 id → 지표이고 키마다 5개까지 보인다 — 그래서 Blogger의 600자 줄과 이슈 수정의 300자 줄 모두에 일 한도 id와 재시도 대기가 남는다. 이슈 수정 러너는 로그 정책(`ISSUE_EDITS.md` §4-1)에 맞춰 이 줄에도 `issue=#N author=…` 머리를 달고 300자로 자르며(코드·상태·`quotaId`·`retryDelay`는 그 안에 들어온다), AI를 부르지 않은 처리는 로그 줄을 늘리지 않고 실행 요약에만 `Gemini 호출: 0회`를 남긴다. 실행 요약에는 `Gemini 호출: N회(실패 K회)`(Chance·Blogger·이슈 수정이 같은 형식, 호출이 없던 실행도 `0회`로 적는다 — 줄이 없으면 '호출 안 함'과 '이 기능이 없는 옛 요약'을 구분할 수 없다)와, 값이 있는 것만 골라 실패 종류별 횟수·요청 모델→응답 모델·토큰 합계·용도별 횟수(용도가 둘 이상일 때)를 접어 쓴다. 모든 모델이 실패해 예외로 끝난 실행(Blogger `LLM_FAILED`·`EXPAND_FAILED`, Chance 예외 요약)에서도 호출 수가 요약에서 사라지지 않는다. Chance 요약에는 마지막으로 관측한 Unsplash 응답 헤더 `X-Ratelimit-Remaining`(시간당 남은 호출)도 한 줄 넣는다(헤더가 없으면 줄을 만들지 않는다). 기록은 **측정 전용**이다: 호출·재시도·폴백·반환값·예외는 그대로이고(기록하다 오류가 나도 — 응답·오류 객체의 깨진 속성, 막힌 로그 출력 — 호출 결과는 그대로이고 기록만 줄어든다. Ctrl+C·종료 신호는 그대로 지나간다), 기록은 메모리와 로그·요약에만 남으며 장부 파일·커밋은 만들지 않는다(하루 단위 장부와 예비 한도는 쿼터 거버너 후속 작업). 429를 일 한도와 분 한도로 가르는 규칙과 재시도 변경은 실제 429 본문을 로그로 모은 뒤의 별도 작업이다(공식 문서의 오류 코드 표는 다른 API용이라 그대로 가정하지 않는다). 기록한 수가 서버가 세는 요청 수와 같다는 보장은 없으므로 AI Studio 사용량 화면과 대조해 확인한다.

**Gemini 한도 확인 요령(비개발자용, 다섯 줄)**
1. 어디를 보나: Actions 실행 화면의 요약 맨 위 `Gemini 호출: N회(실패 K회)`, 그리고 단계 로그에서 `[GEMINI]`를 검색하면 요청 한 번마다 한 줄이 나온다(`result=429`면 한도 초과).
2. `quotaId=…PerDay…`가 보이면 **하루 한도**, `…PerMinute…`면 분당 한도다. `retryDelay=…s`는 구글이 알려 준 재시도 대기 시간이다.
3. `served=`는 구글이 실제로 답한 모델이다. 요청한 `model=`과 다르면 폐기된 모델 이름이 다른 모델로 연결된 것이다.
4. 실제 사용량은 AI Studio 사용량 화면(429 본문에도 안내되는 https://ai.dev/usage?tab=rate-limit)에서만 정확히 보인다. 이 저장소의 숫자는 참고용이라 병합 일주일 뒤 하루 단위로 대조한다 — AI Studio 숫자가 우리 숫자의 배수로 나오면 SDK 자체 재시도가 요청을 더 보내고 있다는 신호다(공식 문서들이 SDK 재시도에 대해 서로 다르게 말해 아직 확정하지 못했다).
5. 하루 한도는 한국 날짜가 아니라 미국 태평양 시간 자정(한국 시각 오후 4~5시, 서머타임에 따라)에 풀린다. 그래서 한국 날짜가 바뀌어도 한도가 그대로일 수 있고, 이 저장소의 날짜(한국 시각)로 센 숫자와 AI Studio의 하루 숫자는 칸이 어긋난다.

임시 조치이며 알려진 부작용이 있다: 비기술 분야가 계속 비면 글은 사실상 기술·미래 분야에서만 나온다. 2026-10-26 출처 개편이 구글 뉴스 소스를 약관상 쓸 수 있는 직접 RSS로 바꿔 과학·문화에 후보를 만들 수 있게 했다 — 사회·정책은 UN News가 보류 중이지만 집행위원회 소식·캐나다 통계청이 후보를 낸다(아래 '**Chance 소스와 약관 점검**'). 2026-10-26 해외 소스 추가(#35)로 경제·일·사회·정책·일상·마음에도 읽는 소스가 생겼지만(D-62), 주말·월요일 아침에는 공공기관 발표가 적어 분야가 비는 일이 남아 폴백은 그대로 둔다. 콘텐츠 전략 작업(운영자 요청서 3번, 저장소 밖 문서)이 주제 선정을 개편하면서 이 폴백을 대체하거나 정리한다.

## 4-2. 워치독 규칙과 알림 방식

워치독(`watchdog.yml`)은 하루 2회(UTC 03:30·15:30 = 한국시간 12:30·00:30, GitHub 예약 실행은 몇 시간 늦게 돌 수 있다) 이력·마지막 글 커밋·최근 실행 결과를 보고 **사람이 개입해야 하는 상황만** GitHub 이슈로 알린다. 규칙은 `pipeline/health.py`(순수 함수), 입출력은 `scripts/watchdog.py`. 기준값은 `pipeline/blogs.json`의 블로그별 `health`(Chance는 `max_gap_hours` 36).

| 코드 | 수준 | 조건 |
|------|------|------|
| `STALE` | 심각 | 마지막 활동(글 파일이 **추가된** 커밋 시각 또는 이력) 이후 `max_gap_hours` 초과 |
| `NO_ACTIVITY` | 경고 | 발행·초안 기록이 전혀 없음 |
| `NO_POSTS_DAY` | 경고 / 심각 | mode auto: 닫힌 한국시간 하루 기준 어제 새 글 0건이면 경고, 그제도 0건이면 심각(오늘 새 글이 나왔으면 회복. `STALE`이 울리면 중복 알림 안 함) |
| `DRAFT_WAITING` | 경고 | 승인 흐름(`publish_flow: pr`) 블로그에서 열린 초안 PR(이 저장소의 `ai/draft/…` 브랜치)이 있는 동안 위 `STALE`·`NO_POSTS_DAY`를 이것으로 **바꾼다**: 새 글이 안 나온 것은 멈춤이 아니라 승인 대기이기 때문이다(대기 N건·가장 오래된 N일 전, 병합하면 공개·닫으면 폐기, 오래 두면 글감이 낡는다는 안내). 초안 PR 이 없거나 목록을 읽지 못하면 바꾸지 않아 `STALE`이 그대로 울린다(§4-4) |
| `FAIL_STREAK` / `REJECT_STREAK` | 심각 / 경고 | 최근 N회 연속 실패 / 5회 연속 게이트 탈락 |
| `UNPUBLISHED` | 경고 | mode auto인데 가장 최근 실행이 게시 없이 저장소 초안만 남김(이력의 사유를 인용). 게시 대상인데 게시 시크릿이 없으면 종료 2로 빨강이라 지금은 새로 생기지 않는다. `mode: draft`의 `draft_uploaded`(Blogger 초안함에 올림)는 게시 없는 초안이 아니라 '글이 나온 날'로 센다 |
| `PAGES_NOT_DEPLOYED` | 심각 | 글 커밋 뒤 30분(+시계 오차 여유 120초)이 지났는데 main 브랜치의 성공한 사이트 배포 실행이 없음 |
| `PAGES_FAILED` | 경고 | 가장 최근 사이트 배포 실행이 실패 |
| `RUN_FAIL_STREAK` | 심각 | 워크플로가 최근 N회 연속 실패 |

`DRAFT_WAITING`을 가리려면 열린 PR 목록을 읽어야 해서 `watchdog.yml`에 `pull-requests: read` 권한을 더했다(읽기 전용). 승인 흐름이 아닌 블로그(지금 모두)에서는 PR 목록을 읽지 않는다.

알림 방식: (블로그, 코드)마다 이슈 하나를 유지한다. 저장소 소유자를 담당자로 지정하고 본문에 @멘션하며, 열려 있는 동안 본문을 최신 내용으로 갱신하고, 심각 건이 48시간 지나도 풀리지 않으면 코멘트로 다시 알린다. 조건이 풀리거나 다른 알림으로 대체되면 자동으로 닫는다. 한 실행에서 새로 만드는 이슈는 5건까지(심각 건 먼저). 이 실행(워크플로)은 **이번에 새로 생긴 심각 건이 있을 때만 빨강(종료 1)**이 되어 Actions 실패 알림도 가고, 이미 알린 심각 건이 이어지는 동안은 초록이다. `PIPELINE_PAUSE`가 켜져 있으면 알림을 만들지 않는다. 글 파일 추가 판정은 git 이력이 필요해 워크플로가 `fetch-depth: 0`으로 받아야 한다(얕은 복제면 경고를 내고 이력 파일로만 판단한다).

### 4-2-1. 초안 모델과 초안 현황 (2026-10-27, 작업요청서 5 PR-B)

사람이 발행해야 하는 글(티스토리·네이버 초안 패키지, Chance 승인 흐름, Blogger 초안함)의 대기 상태를 한 약속으로 센다. **초안 1건 = GitHub 이슈 1개 또는 PR 1개**, 라벨 `초안`(대기) + `채널:<채널 라벨>`(채널 라벨은 레지스트리 `channel.label`과 같은 글자), 쓰지 않을 초안은 라벨 `폐기` 또는 닫기(닫기 = 발행 완료 또는 폐기). 초안을 만드는 쪽(작업 C·E)이 이 라벨을 붙이고, `[공통] 확인 필요 모음`이 읽어 본문 맨 위의 **초안 현황** 표(채널 | 대기 초안 | 가장 오래된 | 최신 초안)와 항목(열린 초안 이슈·PR이 새로 생기면 action — 코멘트 알림, 3일 넘으면 check)을 만든다. 초안 PR은 한 줄만 남긴다: 열린 PR 규칙이 이미 action으로 올린 PR(병합하면 됩니다·충돌·검사 실패)은 그 줄이 알리고, 그 밖의 상태(저장소 기본 토큰이 연 PR은 검사가 돌지 않아 `검사 결과 없음`이 되기 쉽다)는 열린 PR 줄을 빼고 초안 항목이 알린다. Blogger는 이력의 `draft_uploaded`(최근 14일)를 센 **대략치**다(공개 여부는 Blogger 쪽 사실). 레지스트리에 `publish_flow: pr`(작업 E)이 있는 Chance는 열린 초안 PR 수, 없거나 `direct`면 `자동 공개`다. 규칙(`pipeline/inbox.py`)·읽기와 라벨 만들기(`scripts/ops_inbox.py`)·갱신 트리거(`ops-inbox.yml`의 `issues`·`pull_request`)의 상세와 한계(기본 토큰이 만든 이벤트는 워크플로를 시작시키지 않음)는 [`OPS_INBOX.md`](./OPS_INBOX.md) §3-1·§5.

**켜기 전에 연결할 것**(묶음 2 통합에서 일부러 연결하지 않았다 — 승인 흐름·초안 패키지가 모두 꺼져 있어 지금은 필요 없다): Chance 승인 흐름(E)과 티스토리·네이버 초안 패키지(C)가 초안을 만든 **직후** ① `ops-inbox.yml`을 `workflow_dispatch`로 불러 현황판을 바로 갱신하고(기본 토큰이 만든 이슈·PR 은 이벤트 트리거를 일으키지 못한다) ② `notify_draft_waiting()`(§4-5)으로 휴대폰에 `📝 발행 대기`를 보낸다(승인 흐름에서는 새 글 알림 단계가 돌지 않는다 — 글을 main 에 커밋하지 않아서다).

## 4-3. 배포 후 공개 확인 (`pages.yml`의 `verify` 잡, D-41)

배포 워크플로가 초록이어도 "새 글이 공개 주소에서 열린다"는 보장은 없다(빌드 산출물에서 글이 빠졌거나 공개 CDN이 이전 응답을 들고 있을 수 있다). `deploy` 잡 뒤의 `verify` 잡이 `scripts/verify_pages_deploy.py`로 다음을 확인한다(표준 라이브러리만 사용, 잡 제한 15분).

1. 저장소 `_posts`에서 **공개될 가장 새 글**(같은 시각의 KR/EN 쌍)을 고른다. `published: false`(`False`·`no`·`off`·`null`·빈 값, 따옴표 친 값은 보수적으로 포함. 키를 따옴표로 감싸거나 콜론 앞에 공백을 둔 `"published": false`·`published : false`도 같은 키)와 미래 `date`(Jekyll 기본값 `future: false`)는 사이트에서 빠지므로 제외하고 그다음 새 글을 본다. 전부 제외되면 `건너뜀`(초록, 요약에 이유). `_posts` 폴더 자체가 없으면 설정 오류(종료 2) — 조용히 건너뛰면 검증이 꺼진다.
2. 그 글의 공개 주소를 `_config.yml`의 `permalink`(`:year :month :day :title`만 계산)와 파일명, 글 자신의 front matter(`permalink`·`slug`·`date`)로 **계산**해 HTTP 200으로 열리는지 본다. 계산할 수 없는 패턴이면 공개 `posts.json`의 `absoluteUrl`(같은 출처 https만)을 쓴다. 공개 `posts.json`은 보조 정보(소비자가 읽는 목록에 같은 주소로 실렸는지, 다르면 경고)이며 낡았다는 이유로는 실패시키지 않는다. 다만 계산한 주소가 안 열릴 때 `posts.json`이 알려 준 같은 출처 https 주소가 열리면 그 주소로 확인하고 경고만 남긴다(주소 계산이 Jekyll과 달랐을 때의 안전망).
3. 안 열리면 **마감 720초**까지 다시 확인한다. 대기는 **10초에서 2배씩 늘어난다**(10·20·40·80·160초, 이후 160초 — 기본값이면 시도는 0·10·30·70·150·310·470·630초 부근 8번). 다음 시도가 마감 뒤에 시작하게 되면 그만두고, 마감 뒤에는 새 시도도 새 요청도 시작하지 않는다(첫 시도는 마감과 무관하게 끝까지). **시도마다 요청 모양을 바꾼다**(아래). 요청 하나는 소켓 연산별 15초·전체 30초가 상한이고, 글 주소는 상태만 보므로 본문을 읽지 않는다. 끝내 안 열리면 종료 1(`::error::`)로 배포 실행이 빨강이 된다. 실행 요약에는 시도 기록(시도별 경과 초·요청 모양·상태)과 마지막 응답의 상태·`X-Cache`·`Age`·`Last-Modified`가 남아 '캐시에 남은 404'와 '진짜 미반영'을 가려 볼 수 있다. 진행은 로그에 시도마다 실시간으로 찍힌다.

**공개 CDN과 요청 모양**(2026-10-25 독립 검증 실측, 구현자 재확인): 공개 CDN(Fastly)은 200 응답을 `Cache-Control: max-age=600`으로 보관하고, 없는 주소의 **404도 보관**한다(404 응답에는 `Cache-Control`이 없다). 쿼리 문자열(`?cb=…`)·`Cache-Control: no-cache`·`Pragma` 요청 헤더로는 이 보관을 피하지 못한다. 그래서 첫 요청이 배포 전파 전이라 404를 받으면, 같은 주소를 같은 모양으로 다시 요청하는 재시도는 그 404를 계속 돌려받아 마감에 빨강이 된다(옛 설계 — 검증자의 모델로 재현, 이 PR의 `CdnRotationTest`가 같은 시나리오를 고정한다). 404 보관은 **최대 약 18분**이다(검증자 1회 측정: `Age` 963~1078초까지 HIT, 약 1114초에 MISS. 구현자가 같은 날 한 관측은 한 객체가 `Age` 497초까지 HIT였고 나머지는 136~266초에 새로 바뀌어 차이가 있다 — **보관 시간은 불확실**하다). 이 보관을 피하려고 시도마다 캐시 키가 달라지는 요청 모양을 바꾼다. 첫 시도는 정규 주소이고 이후 순서는 ① 끝에 `index.html` ② `Accept-Encoding: gzip` ③ `Accept-Encoding: deflate` ④ 첫 구간 뒤 `//`(`chanceblog//posts/…`) ⑤ 둘째 구간 뒤 `//`(`posts//2026/…`) ⑥ 끝에 `//` ⑦ 둘째 구간 뒤 `./`(`posts/./2026/…`) ⑧ `index.html`+gzip ⑨ `index.html`+deflate 이다(`SHAPES`). 검증자가 실제 사이트의 기존 글에서 모양마다 HTTP 200과 `X-Cache: MISS`(새 캐시 객체)를 확인했고, 구현자도 기존 글 한 건에 10가지 모양을 한 번씩 요청해 모두 200·MISS(`gzip` 응답은 `Content-Encoding: gzip`)임을, 없는 주소에는 10가지 모두 404·MISS(어떤 모양도 없는 글을 200으로 만들지 않음)임을, 같은 모양을 20여 초 뒤 다시 요청하면 404 `X-Cache: HIT`(`Age` 23~29초)임을 확인했다. `br`·`identity`·임의 토큰·대문자 호스트·`Accept-Language`·`Cookie`·퍼센트 인코딩은 같은 객체로 돌아와 쓰지 않는다. 성공은 상태 200으로만 판정한다. 이 주소에 쓸 수 없는 모양(슬래시로 끝나지 않는 주소의 `index.html` 등)은 건너뛰고 쓸 수 있는 모양만 돌린다. **한계**: 모양을 모두 쓴 뒤(기본값에서는 8번째 시도 다음이라 오지 않고 `--interval 1` 같은 작은 값에서만)에는 처음 모양으로 돌아가 보관 중인 404를 읽을 수 있다. 기본값의 마지막 시도는 약 630초이고 다음은 790초라 마감 720초 뒤라서, 그 뒤 약 90초는 보지 않는다. 첫 시도(정규 주소)가 404였다가 다른 모양으로 200을 확인하고 끝나면 정규 주소를 여는 독자는 CDN 보관이 끝날 때까지 404일 수 있어 요약에 경고로 남긴다. 첫 요청 전에 일부러 기다리는 시간은 두지 않았다(배포 직후 원본이 글을 내놓기까지의 지연을 실측하지 못해 추측으로 넣지 않음). 요약의 '해석'은 마지막 응답의 `Age`를 이 검사의 경과 시간과 견준다: `Age`가 경과 시간(+5초 여유) 이내면 이 검사가 앞서 보낸 요청이 남긴 404를 다시 읽은 것이고(그 요청 때 원본이 404를 줬다는 뜻), 더 크면 검사 시작 전부터 CDN이 들고 있던 응답, `MISS`이거나 `Age`가 없거나 0이면 원본이 직접 준 404(진짜 미반영 가능성)다. **배포 때 CDN이 비워지는지는 관측하지 못했다** — 병합 뒤 첫 배포의 요약에서 '시도 기록'과 `X-Cache`·`Age`·`Last-Modified`(새 글 주소와 배포 전부터 있던 `posts.json`)를 확인한다(`DEFECT_REGISTER.md` 하단 체크리스트).

**한계**: 이 확인은 가장 새 글(공개 가능한 것)의 공개 여부만 본다. 글을 추가하지 않은 커밋(이미지 교체·기존 글 수정·설정 변경)의 반영 실패는 이미 공개 중인 최신 글 때문에 통과한다. Jekyll 빌드 자체가 실패하는 경우(D-24형)는 `build` 잡이 먼저 빨강이 되고 `verify`는 건너뛰어지므로(skipped) 이 잡이 새로 잡는 것이 아니다. 또 워치독이 verify 실패를 빌드 실패 문구로 설명하고 취소된 실행을 다루지 못하는 문제는 워치독 쪽 작업이다(D-44). 글 선정·주소 계산의 알려진 차이: front matter는 블록 매핑의 한 줄 `키: 값`만 읽고(키 따옴표·콜론 앞 공백은 허용), 따옴표 친 `date: "… HH:MM:SS"`는 Jekyll이 사이트 시간대로 읽지만 이 스크립트는 UTC로 읽는다(사이트 시간대가 Asia/Seoul이면 미래 판정이 9시간 어긋난다. 이 저장소의 글에는 없다). 주소의 `:title`은 결합 문자(Mark) 등 일부 유니코드 범주를 Jekyll과 다르게 처리할 수 있다(N-5, 고치지 않음 — 한글·영문 slug에는 영향이 없다).

## 4-4. Chance 승인 흐름 — 초안 → 사람 승인 → 공개 (선택, 기본 꺼짐)

레지스트리 `chance.publish_flow`가 `pr`이면 Chance 엔진은 글 한 쌍을 지금과 똑같이 만들되(소스 선정·게이트·Gemini 폴백·슬롯 규칙 그대로) **main 에 바로 올리지 않고** 초안 브랜치(`ai/draft/…`)와 승인 PR 로 올린다. 운영자가 휴대폰 GitHub 앱에서 **PR 을 병합하면 그것이 공개**(사람의 push 가 `pages.yml`을 자동으로 실행시킨다)이고 **닫으면 폐기**다. 이유: 구글 게시자 정책은 수동 검토·큐레이션 없이 자동 생성된 콘텐츠에 광고를 두지 말라고 안내한다. 운영자가 2026-10-27 채팅으로 이 방향(채널 관리 계획의 D1 (a))을 승인했다.

**상태**: 코드와 시험은 있고 **기본값은 꺼짐(`direct`)이다.** `direct`는 이 기능을 넣기 전과 동작이 같다(레지스트리를 읽을 수 있는 한 — 읽지 못하면 아래 '스위치와 검증'처럼 멈춘다. 같은 가짜 입력으로 main 의 `generator.py`와 새 코드를 여러 시나리오에서 돌려 표준 출력·종료 코드·생성 파일·이력·실행 요약이 바이트 단위로 같음을 확인했다). `publish_flow`를 `pr`로 바꾸는 변경은 별도의 **T3**(게시 방식)이고 저장소 설정 하나가 먼저 필요하다([`ACTIONS_GUIDE.md`](./ACTIONS_GUIDE.md) 3-17). **실제 GitHub 에서는 한 번도 돌려 보지 않았다.** 시험은 임시 git 저장소(bare origin)와 가짜 GitHub 클라이언트로 한 것이라, PR 만들기·라벨·병합 뒤 배포는 켠 뒤 처음 관측해야 한다(3-17의 확인 목록, [`DEFECT_REGISTER.md`](./DEFECT_REGISTER.md) 하단 관측 체크리스트).

| | `direct`(기본, 지금 동작) | `pr`(승인 흐름) |
|---|---|---|
| 글 만들기 | 소스 선정·게이트·Gemini 폴백·슬롯 규칙 | **같음** |
| 글이 가는 곳 | main 에 바로 커밋 | 초안 브랜치 `ai/draft/…`(글 파일 둘뿐)와 승인 PR. main 에는 이력 항목만 따로 커밋 |
| 공개 | 커밋 뒤 `gh workflow run pages.yml`(봇의 push 는 push 이벤트를 만들지 못한다) | 운영자가 PR 을 병합 = 사람의 push → `pages.yml` 자동 실행. 이 워크플로는 배포를 요청하지 않는다 |
| 폐기 | 해당 없음 | PR 을 닫는다. 같은 슬롯은 같은 날 다시 만들지 않고 브랜치는 7일 뒤 자동으로 지운다 |
| 실행 요약의 결과 | `PUBLISHED` | 만들기 `DRAFT_CREATED` → 올리기 단계 `DRAFT_OPENED`(실패 `DRAFT_BRANCH_ONLY`) |
| 연습 실행(`dry_run`) | 파일·커밋·게시 없음 | 같음(브랜치·PR 도 없음. 원격 브랜치 확인도 하지 않는다) |

**스위치와 검증**: 레지스트리 `chance` 항목의 `publish_flow`(`direct`|`pr`, 없으면 `direct`)다. 검증기(`python -m pipeline.registry`, REG-1)는 값이 둘 중 하나인지, `platform`이 `jekyll-git`인지(Blogger 의 사람 확인 단계는 `mode: draft`의 초안함이다), `pr`이면 `mode`가 `auto`인지(자동으로 만들고 사람이 승인) 본다. 값은 두 곳에서 같은 함수(`pipeline/drafts.py`의 `chance_flow`)로 읽는다: 워크플로의 `발행 흐름 확인 (레지스트리 publish_flow)` 단계(`python -m pipeline.draft_flow flow`, 표준 라이브러리만 써서 의존성 설치 전에 돈다 — 출력은 `steps.flow.outputs.flow`)와 `generator.py`. **읽지 못하거나 값이 틀리면 직접 게시로 떨어지지 않고 멈춘다**(단계가 빨강으로 끝나 글을 만들기 전에 종료). 승인 흐름을 켜 둔 채 레지스트리 오류 때문에 승인 없는 게시가 나가는 일을 막으려는 것이다. 같은 이유로 **직접 게시(`direct`)에서도 깨진 레지스트리면 글을 만들기 전에 멈춘다**(레지스트리는 CI 가 PR 마다 검증하므로 정상 운영에서는 달라지는 것이 없다). **켜는 변경(T3)은 두 줄이다**: `pipeline/blogs.json`의 `publish_flow`와, 그 값을 지금 값으로 못 박아 둔 표지판 시험의 기준 `tests/draft_helpers.py`의 `REAL_PUBLISH_FLOW` — 표지판 시험(`tests/test_drafts.py`·`tests/test_generator_drafts.py`의 실제 레지스트리 시험 4개, `tests/test_batch2_integration.py`의 `test_the_real_registry_is_unchanged_by_the_merge`, `tests/test_ops_inbox_drafts.py`의 `test_the_real_registry_gives_chance_and_blogger_rows_with_nothing_pending`)이 모두 이 한 상수를 읽는다. 레지스트리만 바뀌면 이 시험들이 빨강이 되고, 둘을 함께 바꾸면 전체 시험이 통과한다(`pr`로 바꾼 사본의 전체 시험으로 확인).

**실행 순서(`pr`)**: ① `발행 흐름 확인`이 `pr`을 읽고 실행 요약에 한 블록을 남긴다. ② `generator.py`가 평소처럼 `_posts/`에 글 둘을 쓰고 `history.json`에 항목을 더한다. 항목에 `flow: "pr"`·`branch`·`paths`(글 파일 둘의 저장소 상대 경로)가 더해지고 결과는 `DRAFT_CREATED`다. ③ `변경 사항 커밋`·`Pages 배포 실행` 단계는 건너뛴다(`steps.flow.outputs.flow != 'pr'`). ④ `초안 올리기와 승인 PR 열기 (승인 흐름일 때만)` 단계(`python -m pipeline.draft_flow deliver`)가 다음을 한다.

1. 글 둘만 담은 커밋을 새 초안 브랜치에 만들고, 기준 브랜치(main)로 돌아와 **이력 파일만 담은 커밋**을 만든다(커밋 작성자는 `github-actions[bot]`).
2. 초안 브랜치를 push 하고, 이어서 이력 커밋을 main 에 push 한다(거절되면 `pull --rebase` 뒤 최대 3번). 이력 push 가 끝내 실패하면 **방금 올린 초안 브랜치를 지우고(롤백)** 빨강(종료 1)으로 끝난다 — 이력 없는 초안이 남아 같은 슬롯을 또 만들지 않게, 다음 정기 실행이 그 슬롯을 처음부터 다시 만든다.
3. PR 을 연다(5xx·네트워크 오류는 2초·5초 간격으로 재시도, 이미 같은 브랜치의 PR 이 있으면 그 번호를 쓴다). 라벨 `초안`·`채널:Chance`를 붙인다(없으면 만든다. 실패해도 경고만).
4. 남은 초안을 정리한다(아래 '정리').

직접 게시 단계와 이 단계는 서로 배타적이다(`if` 조건이 반대). 이 단계는 연습 실행이면 실행되지 않고, 프로그램 안에서도 `DRY_RUN`·`PIPELINE_PAUSE`가 켜져 있거나 `GITHUB_TOKEN`·`GITHUB_REPOSITORY`가 없으면(로컬 실행) 아무것도 쓰지 않는다.

**이력 항목만 main 에 따로 커밋하는 이유**(설계 결정과 대안): 이력 파일을 글과 같은 PR 에 두면 슬롯 중복 방지가 초안 브랜치의 존재에만 의존하고, 열린 PR 이 둘이 되면 `history.json`의 같은 줄을 둘 다 고쳐 하나를 병합한 뒤 다른 쪽이 충돌한다(휴대폰에서 풀 수 없다. 임시 저장소 시험으로 재현했다). 별도 원장 파일(`drafts.json`)을 두면 `history.json`과 이중 장부가 되고 소비자(워치독·현황판)가 읽을 파일이 하나 더 늘어난다. 그래서 이력 항목(필드 셋 추가)을 생성 시점에 main 에 커밋하고 PR 에는 글 파일 둘만 둔다: 슬롯·제목(0.6/0.7)·이미지·분야 중복 검사가 지금처럼 main 의 이력만 읽고, 초안이 몇 개 열려 있어도 PR 끼리 충돌하지 않는다. **대가**: 닫아서 폐기한 초안의 이력 항목도 남아 그 슬롯·주제·이미지는 다시 쓰지 않는다(의도한 동작이지만 '이력에 있는 글 = 공개된 글'이 더는 아니다). 이력으로 글 수를 세는 곳(예: 확인 필요 모음의 '최근 24시간 글 수' 현황)은 초안도 센다 — 공개 여부는 글 파일이 main 에 있는지로 판단한다.

**슬롯 상태와 결과 코드**(`generator.py`의 `slot_state`가 이력으로 판정한 것을 `pipeline/drafts.py`의 `refine_slot_state`가 다듬는다):

| 그 슬롯의 상태 | 판정 | `[SKIP] code=` (종료) |
|---|---|---|
| 이력 항목 없음, 초안 브랜치도 원격에 없음 | 만든다 | (없음) |
| 이력 항목이 `flow: "pr"`이고 `paths`의 글이 main 에 있음(병합됨) | 이미 공개됨 | `ALREADY_PUBLISHED` (0) |
| 이력 항목이 `flow: "pr"`이고 글이 main 에 없음(승인 대기이거나 닫혀 폐기됨) | 같은 슬롯을 다시 만들지 않음 | `DRAFT_PENDING` (0, 정상 건너뜀) |
| 이력 항목은 없는데 그 슬롯의 초안 브랜치(`ai/draft/<날짜>-s<슬롯>`)가 원격에 있음(이력 쓰기가 실패한 드문 경우) | 같은 슬롯을 다시 만들지 않음 | `DRAFT_PENDING` (0) |
| 원격 브랜치를 확인하지 못함(`git ls-remote` 실패) | 이번 실행만 건너뜀, 다음 실행이 다시 본다 | `DRAFT_CHECK_FAILED` (0, `::warning::` 고정 문장) |

수동 실행에는 슬롯이 없다(`slot=None`): 브랜치 이름은 `ai/draft/<날짜>-m<HHMMSS>`(KST 생성 시각)이고 슬롯 판정은 하지 않는다(수동 실행은 원래 하루 상한·슬롯 규칙과 무관하다). 슬롯 둘(9시·18시)은 서로 다른 브랜치·이력 항목이라 간섭하지 않는다.

**승인 PR 의 모양**(운영자가 읽고, 현황판·워치독이 알아보는 값):

| 항목 | 값 |
|---|---|
| 작성자 | `github-actions[bot]`(`GITHUB_TOKEN`) |
| head → base | `ai/draft/<YYYY-MM-DD>-s<슬롯>`(정기) 또는 `ai/draft/<YYYY-MM-DD>-m<HHMMSS>`(수동) → `main` |
| 제목 | `[초안][Chance] <한국어 제목> / <영어 제목>` — 제목마다 80자, 전체 200자 이하, 소독됨 |
| 라벨 | `초안`(색 `d4c5f9`)·`채널:Chance`(색 `1d76db`). 없으면 만든다 |
| 바뀐 파일 | `_posts/…` 두 개(한국어·영어)뿐. `history.json`은 PR 에 없다 |
| 본문 | 승인 안내(운영자 @멘션) · 요약(분야·출처·원문 링크·발행 슬롯) · 제목 · 첫 문단 발췌 · 자동 점검 결과(분량·원문 인용·출처 목록·고지문·제목 유사도) · 승인 체크리스트 · 안내. 9,000자 이하 |
| 체크리스트 | 정확히 `- [ ] 원문과 수치·사실을 대조했다` / `- [ ] 제목·요약에 문제가 없다` / `- [ ] 병합 = 공개(사람 검토 단계)` 세 줄 |
| 검사(CI) | **돌지 않는다**: `GITHUB_TOKEN`으로 연 PR 은 `pull_request` 워크플로를 시작시키지 않는다(GitHub 규칙, 켠 뒤 관측). 글 파일만 바뀌어 병합에 필요하지 않다. 라벨 `초안`이 붙은 PR 은 확인 필요 모음이 '초안 대기'(지금 해야 할 일) 한 줄로 보여 준다([`OPS_INBOX.md`](./OPS_INBOX.md) §3 의 `초안(PR)` 행) |

이력 항목(`history.json`)은 Chance 의 기존 필드(`date`·`topic`·`kr_title`·`en_title`·`kr_image`·`en_image`·`slot`·`lane`·`source`·`source_url`)에 `flow`(`"pr"`)·`branch`·`paths`가 더해진 것이다. 별도 원장 파일은 없다.

**PR 본문 소독**: PR 제목·본문에는 AI 가 쓴 글과 외부 피드 문구가 섞인다. 모두 `pipeline/drafts.py`의 `neutralize()`를 거친다 — 보이지 않는 글자·방향 제어 문자 제거, HTML 주석과 `script`·`style` 류 블록 제거, 비밀 모양 가리기(`mask`), 한 줄로 접기(`::`·`##[` 포함), `<`·`>`·`[`·`]`은 전각으로, 백틱은 작은따옴표로, `~`는 전각으로, 문자 참조(`&#64;` 등)는 `&amp;`로 감싸고, `@`·`#`·`://`·`www.` 뒤에는 폭 없는 공백을 넣어(멘션·이슈 참조·자동 링크 무력화) 길이를 제한한다. 운영자 멘션과 원문 링크(안전한 단순 https 주소만)는 이 모듈이 직접 붙인다. 토큰은 환경변수로만 받고 로그·오류·요약에 쓰지 않으며, `::error::`·`::warning::` 줄에는 외부 문자열이 없는 고정 문장만 쓴다. REST 호출은 표준 라이브러리(`urllib`)만 쓴다.

**실패 안전**(만든 글을 잃지 않는다):

| 상황 | 결과 | 종료 | 사람이 할 일 |
|---|---|---|---|
| PR 열기가 거부됨(403 — 저장소 설정 'Allow GitHub Actions to create and approve pull requests'가 꺼져 있는 경우 등)·API 오류·재시도 뒤에도 5xx | 초안 브랜치와 이력은 그대로. 요약 `DRAFT_BRANCH_ONLY` + 안내(설정을 켜거나 GitHub 화면에서 직접 PR 열기). 슬롯은 처리된 것으로 취급해 다시 만들지 않는다. 다음 정기 실행의 정리가 최대 3일 동안 PR 열기를 다시 시도한다(경고만) | **1(빨강)**, Actions 실패 알림이 간다 | 설정을 켜면 다음 실행(30분 안)이 PR 을 다시 연다. 급하면 브랜치 화면의 'Compare & pull request' |
| 초안 브랜치 push 실패 | 이력이 아직 없으므로 슬롯은 처리되지 않았고 다음 정기 실행이 처음부터 다시 만든다 | 1 | 로그 확인 |
| 이력 push 가 3번 모두 거절됨 | 방금 올린 브랜치를 지운다(롤백) | 1 | 다음 실행을 기다린다 |
| 라벨 실패·정리 실패·정리 중 예상 밖 오류 | PR 은 열렸고 발행에는 영향 없음. 로그와 요약에 사유, `::warning::` 고정 문장 | 0 | 다음 실행이 다시 시도 |

**정리**(`deliver` 단계 끝, 열린 PR 목록은 저장소 안의 `ai/draft/` 브랜치에서 연 것만): PR 이 없는 초안 브랜치는 만든 지 3일 안이면 PR 을 다시 연다(글은 원격 브랜치에서 읽는다). 병합됐거나 닫힌 브랜치, 그리고 PR 이 없는 오래된 브랜치는 이름의 날짜로 7일이 지나면 지운다. **열린 PR 이 있는 브랜치는 오래돼도 지우지 않는다.** `ai/draft/` 아래라도 이름 형식(`<날짜>-s<슬롯>`·`<날짜>-m<HHMMSS>`)이 아니면 건드리지 않는다. PR 목록은 저장소의 최근 PR 300건까지만 읽으므로, 끝까지 읽지 못했으면 '목록에 PR 이 안 보이는' 브랜치는 PR 이 없다는 증거가 아니라서 지우지 않는다(닫힌 PR 이 보이는 브랜치는 지운다). 정리 실패는 경고일 뿐 발행을 실패시키지 않는다. 정리는 이 단계에서만 돌므로 `direct`로 되돌린 뒤 남은 `ai/draft/…` 브랜치는 직접 지운다.

**워치독**: 승인 흐름에서는 새 글이 안 나온 것이 멈춤이 아니라 승인 대기일 수 있다. `pipeline/health.py`는 `publish_flow: pr` 블로그에 열린 초안 PR 이 있으면 `STALE`·`NO_POSTS_DAY`를 `DRAFT_WAITING`(경고, 대기 N건·가장 오래된 N일)으로 바꾼다(§4-2). 열린 초안이 없거나 목록을 읽지 못했으면 예전처럼 `STALE`이 울린다 — 초안을 닫기만 하고 새 글이 안 나오는 것은 정말 멈춘 것이다. 이 규칙이 맞게 돌도록 워치독의 두 판정을 바꿨다(직접 게시에서는 결과가 같다): ① 글이 올라온 시각은 초안을 만든 시각이 아니라 **병합 시각**이다 — 글 파일을 더한 커밋을 `git log --first-parent`로 찾는다(기본 이력 단순화는 병합 대신 초안 브랜치의 커밋을 보여 줘 늦게 병합하면 `STALE`이 헛울리고 `PAGES_NOT_DEPLOYED`의 기준 시각이 어긋난다). ② 병합하지 않은 초안의 이력 항목(`flow: "pr"`)은 글 커밋 날짜를 알 때 '글이 나온 날'로 세지 않는다(`NO_POSTS_DAY`가 가려지지 않게. 얕은 복제라 날짜를 모르면 예전처럼 이력으로 판단).

**사이트 반영 확인**: PR 병합은 main 에 push 이벤트를 만들어 `pages.yml`이 자동으로 돌고 `verify` 잡(§4-3)이 가장 새 글 쌍의 공개 주소를 확인한다. 글에는 front matter `date`가 없어 Jekyll 은 파일 이름의 날짜(만든 날) 자정을 글 날짜로 쓰는데, 이는 병합 시점에 과거이거나 같은 날이라 `future: false`에 걸리지 않는다. 대신 늦게 병합한 글은 공개된 시각이 아니라 만든 날짜 자리에 놓인다(사이트 목록·피드의 순서와 날짜 표시가 병합일이 아니라 만든 날을 따른다). 알려진 한계: `verify`는 가장 새 글 쌍만 보므로 **오래된 초안을 더 새 글보다 늦게 병합하면 그 글은 따로 확인되지 않는다**(새 글이 이미 열려 있으면 통과). 병합 방식(Merge commit·Squash·Rebase)은 글 파일이 main 에 생기기만 하면 되므로 무엇이든 슬롯 판정에 영향이 없고, 워치독은 어느 방식이든 main 줄기에서 글 파일을 더한 커밋의 시각을 글이 올라온 시각으로 본다(위 '워치독' ①).

**알려진 한계와 미관측**: ① PR 만들기·라벨 붙이기·병합 뒤 배포가 실제 GitHub 에서 의도대로 도는지는 켠 뒤 처음 관측한다. ② 저장소 설정 'Allow GitHub Actions to create and approve pull requests'는 [`ACTIONS_GUIDE.md`](./ACTIONS_GUIDE.md) 5-1에 켜짐(이슈 수정이 PR 을 만든 것이 근거)으로 기록돼 있으나 이 변경을 만든 쪽에서 화면을 확인하지 못했다. ③ 초안을 만든 실행이 도중에 죽으면 두 가지가 남을 수 있다. 이력 push 뒤 PR 열기 전이면 PR 없는 브랜치가 남고 정리가 3일 동안 PR 을 다시 열어 본다. 초안 브랜치 push 뒤 이력 push 전이면 이력 항목이 없는 브랜치가 남는다: 그 슬롯은 `DRAFT_PENDING`(원격 브랜치 확인)이라 다시 만들지 않지만 PR 은 열리지 않고 브랜치는 7일 뒤 지워진다 — 로그의 '이력 항목이 없어 다시 열지 못합니다' 줄이 단서이고, 급하면 브랜치에서 직접 PR 을 연다. ④ 이력 항목은 초안을 만들 때 main 에 들어가고 글은 병합 때 들어오므로, 병합 전에는 이력에 있는 글이 사이트에 없다. 이력을 읽는 곳(중복 검사·확인 필요 모음의 현황)은 이를 구분하지 못한다(위 '대가'). ⑤ 봇 PR 에는 검사가 돌지 않아 병합 전에 사람이 글을 읽는 것이 유일한 검증이다(그래서 이 흐름이 있다). ⑥ main 에 '상태 검사 필수'나 'PR 필수' 보호 규칙을 켜면 봇이 연 초안 PR 은 검사가 없어 병합이 막히고 봇의 이력 push 도 거부된다([`ACTIONS_GUIDE.md`](./ACTIONS_GUIDE.md) 5장 경고와 같다). ⑦ 라벨을 붙이는 호출이 `pull-requests: write`만으로 되는지(`issues: write`가 필요한지)는 켠 뒤 관측한다 — 안 되면 라벨 없이 PR 만 열리고 경고 한 줄이 남으며, 제목 접두 `[초안][Chance]`와 브랜치 이름은 그대로라 알아볼 수 있다.

## 4-5. 텔레그램 알림 계층 (`pipeline/notify.py`, 2026-10-27)

새 글 발행·초안 발행 대기·확인 필요를 **휴대폰 텔레그램**으로 알리는 보조 계층이다(운영자 요청). 표준 라이브러리만 쓰고(`urllib`, Python 3.10 호환 — Chance 워크플로는 `google-genai` 외에 설치하는 것이 없다), 시크릿 `TELEGRAM_BOT_TOKEN`·`TELEGRAM_CHAT_ID`가 **둘 다** 있을 때만 켜진다. 하나라도 없으면 아무것도 보내지 않고, 호출하는 쪽의 출력도 예전과 바이트 단위로 같다(알림 단계 명령만 `텔레그램 알림: 건너뜀(시크릿 없음)` 한 줄을 남긴다). 운영자용 설정: `.github/editorial/TELEGRAM_SETUP.md`.

| 이벤트 | 함수(`Notifier`의 메서드이자 같은 이름의 모듈 함수) | 호출 자리 | 내용 |
|--------|------|------|------|
| 새 글 발행 | `notify_chance_published(posts, run_info)` | `chanceblog.yml`의 마지막 단계 `텔레그램 알림(새 글)` → `python -m pipeline.notify chance-published --commit HEAD` | 방금 push 한 커밋이 **새로 더한** `_posts/**.md`(부모가 있는 커밋만, `published: false` 제외)를 (날짜·시각)으로 짝지어 한·영 한 쌍을 한 통으로: 제목 둘·분야·출처·예상 공개 주소 둘(`scripts/verify_pages_deploy.py`의 주소 계산을 그대로 씀)·배포 안내("배포가 끝나기까지 약 3분 — 일찍 열면 404 가 최대 약 18분 보관될 수 있으니 3분 뒤에 열어 보세요", D-41)·실행 기록 링크, 버튼 `한글 글`·`English` |
| 발행 대기 | `notify_draft_waiting(channel_label, title, where, url=None)` | `notify_blogger_result`가 `draft_uploaded`에서 부른다. **티스토리·네이버 초안 패키지와 Chance 승인 대기가 초안을 만든 직후 같은 함수를 부른다(호출은 아직 연결하지 않았다 — 켜기 전에 연결할 것, §4-2-1)** | `📝 발행 대기 — 채널: 제목 → 어디서 무엇을 하면 되는지` + 허용된 주소면 `열기` 버튼 |
| Blogger 결과 | `notify_blogger_result(result_code, title, url, blog_label, extra_prefixes)` | `pipeline/run.py`가 게시·초안 업로드에 성공했을 때(`posted`·`draft_uploaded`), 이력·초안 파일·실행 요약을 모두 쓴 **맨 마지막에**(알림이 느리거나 그 사이 실행이 끊겨도 올라간 글의 기록이 먼저 남는다) | `draft_uploaded` → 발행 대기 문구(Blogger 대시보드 → 초안에서 확인·게시), `posted` → `✅ 게시됨`(글 주소가 레지스트리의 블로그 주소 아래일 때만 `글 보기` 버튼). 실패·저장소 파일만 저장·연습 실행은 보내지 않는다(실패는 확인 필요 모음·Actions 실패 알림이 맡는다) |
| 확인 필요 | `notify_ops_alert(item_lines, inbox_url, count)` | `scripts/ops_inbox.py`가 코멘트(@멘션)를 쓰려고 할 때(연습 제외) — 같은 `new_items`, `inbox.alert_lines()`가 코멘트와 같은 제목 줄을 만든다 | **평문** 한 통(`📌 확인 필요 모음 — 새로 해야 할 일 N건` + 항목 제목 줄 최대 10줄), 버튼 `확인 필요 모음 열기` |
| 연결 확인 | `notify_test()` | `python -m pipeline.notify test`(`[공통] 텔레그램 알림 시험`) | `✅ 알림 연결 확인` |

**실패 격리**: ① 모든 공개 함수는 예외를 던지지 않고 `Result(ok, sent, status, reason, detail)`를 돌려준다(분류 코드: `sent`·`disabled`·`not_applicable`·`invalid_token`·`invalid_chat_id`·`unauthorized`(401)·`chat_not_found`(400)·`forbidden`(403)·`not_found`(404)·`rate_limited`(429)·`server_error`(5xx)·`network`·`timeout`·`bad_request`·`parse_error`·`button_error`·`bad_response`·`limit`·`internal_error`). 호출하는 쪽도 한 번 더 감싼다 — Blogger 러너는 알림이 실패하거나 예외를 던져도 게시 결과·이력·요약·종료 코드를 바꾸지 않고(로그에 `[참고]` 한 줄과 고정 문장 `::warning::`만), 점검 모음은 코멘트·표식·종료 코드를 바꾸지 않는다(코멘트가 실패해 다음 점검이 같은 항목을 다시 알릴 때는 휴대폰 알림도 한 번 더 간다 — "놓치는 것보다 한 번 더 알리는 쪽이 낫다"는 기존 원칙, `docs/OPS_INBOX.md` §4). ② Chance 알림 단계는 `if: steps.commit.outputs.pushed == 'true'`(연습 실행은 push 가 없어 안 돈다)·`continue-on-error: true`·`timeout-minutes: 2`이고, 명령은 전송이 실패해도 종료 코드 0으로 끝나며 `::warning::`으로 드러낸다 — 확인 필요 모음이 "실행은 성공했지만 경고가 있습니다"로 모은다. `continue-on-error`는 이 단계 모양(run 이 `python -m pipeline.notify …` 한 줄 + `timeout-minutes`)에만 검증기 WF-6 이 경고하지 않는다. ③ 알림 시험(`test`)만 실패 때 종료 1(빨강)이다.

**전송 규칙**: JSON `POST https://api.telegram.org/bot<토큰>/sendMessage`, 제한 시간 15초, 링크 미리보기 끔. 본문 3,800자(UTF-16 코드 단위로 센다 — 이모지는 2, 텔레그램 한도는 4,096) 안으로 줄이고(잘리면 `…`), HTML 알림이 너무 길면 서식을 버리고 평문으로 보낸다. 한 실행(프로세스)에서 5통까지, 통 사이 1.1초(같은 채팅에는 초당 1통이 안전). 429 는 `retry_after`(최대 10초)만큼 기다려 한 번, 네트워크 오류·5xx 는 2초 뒤 한 번, HTML 해석 오류(400)는 서식 없이 한 번, 버튼 거부(400)는 버튼 없이 한 번 다시 보낸다(한 통에 요청은 최대 5번). 400·401·403·404 는 다시 시도하지 않는다. 텔레그램 전송에는 멱등성 키가 없어 타임아웃 뒤 재시도로 같은 알림이 드물게 두 번 갈 수 있다(알림은 최소 한 번 가는 쪽을 택했다).

**토큰 취급**(G-C12): 시크릿은 단계 `env`로만 넘기고(검증기 WF-13), 코드는 환경변수에서만 읽는다. 토큰이 요청 주소의 경로에 들어가므로 **예외 문구를 어디에도 쓰지 않고** 클래스 이름·HTTP 상태·텔레그램이 준 짧은 설명만 남기며, 돌려주는 모든 글에서 토큰·채팅 ID(와 URL 인코딩 형태·토큰 절반)를 지운 뒤 비밀 모양 패턴(`Telegram 봇 토큰`)으로 한 번 더 가린다. 외부·AI 유래 글(제목·출처 이름·항목 제목)은 비밀 모양 가리기 → 보이지 않는 문자·제어 문자 제거 → 한 줄로 접기 → 길이 제한 → HTML 이스케이프 순으로 소독하고(수백만 자짜리 입력에 정규식을 통째로 돌리지 않게 보이는 길이의 10배(최소 2,000자)까지만 읽는다), 주소는 허용 목록(`https://shine88pc.github.io/…`·`https://github.com/shine88pc/chanceblog/…`·`https://www.blogger.com/…`, 그리고 코드가 직접 주는 레지스트리의 블로그 주소)만 링크·버튼으로 건다(허용 밖 주소와, 제목·출처 같은 외부 글 속의 `https://…`·`tg://…` 는 `://`를 전각 콜론으로 바꿔 글자로만 둔다 — 텔레그램이 글자 그대로를 링크로 바꾸지 못하게).

**한계와 후속**(독립 검증 1차 반영): ① 새 글 알림은 사이트 배포를 요청한 직후에 오고 주소·버튼이 같이 간다. 배포가 퍼지기 전에 열면 공개 CDN 이 그 404 를 최대 약 18분 보관해(D-41) 독자에게도 한동안 404 가 보일 수 있어, 알림 문구와 안내서에 "3분 뒤에 열어 보세요"를 적었다. **후속 후보(코드는 아직 하지 않음)**: 알림을 `pages.yml`의 `verify` 잡(사이트 반영 확인) 성공 뒤로 옮기거나, 반영이 확인된 뒤에만 주소를 다는 것. ② 알림 단계의 조건은 `if: steps.commit.outputs.pushed == 'true'`뿐이라 암묵적으로 `success()`도 따른다 — 바로 앞 `Pages 배포 실행` 단계가 실패하면 알림도 건너뛴다(그때는 Actions 실패 알림 메일이 대신한다). ③ **WF-13 은 시크릿 이름이 글자로 나오는 곳만 본다**: `toJSON(secrets)`·`secrets[format(…)]`·`secrets: inherit` 처럼 이름 없이 넘기는 길과 외부 `uses:` 단계의 env 는 못 잡는다(기존 규칙도 못 잡던 것). **작업 D 처리(2026-10-27, `blogger.yml`의 재사용 워크플로화)**: 부르는 쪽(`blogger-en.yml`·`blogger-ko.yml`)의 `jobs.<잡>.secrets` 의 `TELEGRAM_BOT_TOKEN`·`TELEGRAM_CHAT_ID` 항목에 **같은 이름의** 시크릿 표현식(`secrets.그 이름` 하나, 달러 기호와 이중 중괄호로 감싼 모양)을 넣어 넘기고, WF-13 은 그 자리 — 이 저장소 안의 재사용 워크플로(`uses: ./.github/workflows/…`)를 부르는 잡의 `secrets` 항목, 같은 이름·같은 시크릿 표현식 하나뿐 — 를 허용한다(`secrets: inherit`·다른 값을 그 이름으로 넘기는 것·다른 저장소의 워크플로로 넘기는 것은 오류). 불린 쪽 `on.workflow_call.secrets` 의 텔레그램 정의는 대문자 이름·`required`·`description` 만 두고 `required: true`가 아니어야 한다(필수로 두면 시크릿을 등록하지 않은 저장소에서 호출이 통째로 실패한다 — 알림은 보조). 러너 단계 `env` 두 줄은 공용 워크플로에 그대로 남아 그 값을 받는다. 시험 `TelegramReusableWorkflowTest`가 허용·거절 경계를 고정한다. ④ 저장소 시크릿은 모든 브랜치의 워크플로가 읽을 수 있어 `[공통] 텔레그램 알림 시험`은 `main` 에서만 실행한다(후속 후보: 두 값을 main 만 허용하는 Environment 시크릿으로 두고 단계에 `environment:` 를 다는 것 — 운영자의 등록 절차가 바뀐다).

**관측이 필요한 것**(실제 텔레그램을 호출하지 못했다): 시크릿 등록 뒤 `[공통] 텔레그램 알림 시험` 실행, 다음 새 글 1쌍의 알림(주소·버튼이 열리는지), 휴대폰 앱의 버튼(`url`) 동작. 텔레그램 공식 문서는 이 PC 에서 읽을 수 없어 한도·형식은 라이브러리 문서·공식 채널·소스로 확인한 값이다(근거: 2026-10-27 조사 보고).

## 4-6. 운영자 요청함 — AI 의 텔레그램 요청과 이슈 응답 (`pipeline/operator_loop.py`, 2026-10-28)

공용 PC 에서 운영자가 가끔만 들어오고 AI 는 GitHub 화면(PR 만들기·병합·Actions 실행·설정·시크릿·댓글)을 쓸 수 없어, 막히거나 결정이 필요할 때 **AI → 운영자**로 부탁하고 **운영자 → AI**로 답을 받는 길이다(운영자 지시 2026-10-28, 새 승인 채널 — [`SECURITY_GUARDRAILS.md`](./SECURITY_GUARDRAILS.md) G-S9). 표준 라이브러리만 쓰고 Python 3.10 에서 돈다. 운영자용 안내: [`인수인계/운영자_요청함_사용법.md`](../인수인계/운영자_요청함_사용법.md), AI 용: [`인수인계/요청함/README.md`](../인수인계/요청함/README.md).

```
AI(push 만 가능) ──요청 파일──▶ 인수인계/요청함/R-001_….md  (ai/claude/** 브랜치)
        │                                  │ push
        │                       [공통] AI 요청 텔레그램 알림 (ai-request.yml)
        │                                  ▼  python -m pipeline.operator_loop requests
        │                          운영자 휴대폰 텔레그램: 🔔 AI 요청 R-001 · 병합 부탁 [요청 열기][PR 열기][답하기][사용법]
        │                                  │ 운영자가 New issue 메뉴에서 양식으로 답(소유자 계정)
        ▼                                  ▼
공개 REST 로 이슈를 읽음 ◀── 이슈 [답변] ─── [공통] 운영자 응답 접수 (operator-reply.yml, issues: opened)
(운영자응답·운영자요청 라벨)        python -m pipeline.operator_loop ack → 라벨 + 접수 코멘트 한 번 + 텔레그램 ✅ 답변 접수
```

| 구성 | 파일 | 하는 일 |
|------|------|---------|
| 코어 | `pipeline/operator_loop.py` | 요청 파일 파서·새 파일 고르기·알림 보내기(`requests`), 응답 이슈 파서·접수 코멘트·GitHub REST(urllib)·접수(`ack`), 명령 줄(인자를 받지 않음) |
| 메시지 | `pipeline/notify.py` | `format_ai_request`·`notify_ai_request`(HTML, 소독·허용 주소 버튼)·`format_reply_received`·`format_task_received` — 기존 알림의 소독·허용 주소·토큰 비노출·통 수 상한·실패 격리를 그대로 쓴다(새 HTTP 코드 없음) |
| 알림 워크플로 | `.github/workflows/ai-request.yml` | `push` + `branches: ['ai/claude/**']` 뿐(경로 필터 없음), 권한 contents 읽기, 시크릿은 마지막 단계 env |
| 접수 워크플로 | `.github/workflows/operator-reply.yml` | `issues: [opened]` 뿐, 권한 issues 쓰기+contents 읽기, job `if` 로 소유자만(이중 방어) |
| 이슈 양식 | `.github/ISSUE_TEMPLATE/ai-reply.yml`·`ai-task.yml`·`config.yml` | 제목 머리 `[답변] `·`[요청] `, 라벨 `운영자응답`·`운영자요청`(`blog-control` 아님), 항목 id·제목·선택지는 코드의 상수와 같다(검증기 FORM-1) |

**요청 파일**: `인수인계/요청함/R-<세 자리>_<영문 소문자·숫자·하이픈>.md`. 앞머리는 파일 맨 앞 `---`…`---` 사이의 `키: 값` 한 줄들(YAML 해석기를 쓰지 않는다 — 블록·목록·앵커를 읽지 않는다): `id`(파일 이름의 번호와 같음)·`kind`(merge·run·confirm·decision·info)·`title`(80자)·`summary`(300자, 텔레그램 본문)·`urgency`(보통·급함)·`pr`(선택)·`created`(선택). 줄은 `\n` 으로만 나누고(U+2028 같은 문자로 줄을 위조하지 못하게) 닫는 `---` 는 첫 40줄 안에 있어야 하며 한 줄은 2,000자까지만 읽는다. 런타임은 모르는 키를 무시하고 긴 제목·요약은 보낼 때 줄여 알림을 잃지 않으며, 검증기(REQ-1)는 모르는 키·긴 값·id 불일치·중복 번호를 오류로 알려 올리기 전에 잡는다. 본문은 읽지 않는다(텔레그램에는 싣지 않고 버튼으로 연다).

**새 요청 파일 고르기**(`new_request_names`): 푸시마다 도는 워크플로가 같은 요청을 다시 알리지 않도록, 다음 둘을 **모두** 만족하는 `인수인계/요청함/` 바로 아래의 이름 규칙에 맞는 파일만 새 파일로 본다.
① **트리 차이** `git diff --diff-filter=A <기준> <AFTER>` 에서 '더해진' 것(수정만·이름만 바뀐 것은 빠진다). 기준은 `BEFORE_SHA` 이고, 새 브랜치 첫 push 처럼 전부 0 이면 `merge-base(origin/<기본 브랜치>, AFTER)` 다(`git rev-parse --is-shallow-repository` 가 `false` 가 아니면 기준을 믿을 수 없어 중단).
② **커밋 차이** `git log --diff-filter=A AFTER ^BEFORE --not --exclude=origin/<이 브랜치> --remotes=origin` 에서 더해진 것 — AFTER 에서 도달하지만 BEFORE 와 **이 브랜치 말고 다른 모든 원격 브랜치**(기본 브랜치 포함)에서는 도달하지 못하는 커밋이 더한 것. 그래서 main 을 이 브랜치에 합쳐도(main 이 가져온 요청 파일은 그 브랜치들에 있음), 이미 알린 다른 브랜치를 합치거나 거기서 새 브랜치를 만들어도 그 파일을 다시 알리지 않는다. 같은 내용의 리베이스·강제 push 는 ①이 거른다(BEFORE 트리에 이미 있음).
git 호출이 하나라도 실패하면(얕은 복제·사라진 BEFORE 커밋 등) **보내지 않고** `::warning::` 만 남긴다(중복·도배를 막는 쪽을 택했다). 브랜치 이름은 `ai/claude/` 뒤에 영문·숫자·`.`·`_`·`-` 조각(`/` 로 이어도 됨)만 받는다 — 한글·`+`·`@`·`#` 등이 든 이름이면 git 에 넘기지 않고 같은 경고로 끝난다. 트리 차이에는 있지만 커밋 차이로 걸러진 파일은 로그에 `다른 브랜치에도 있어 알리지 않은 요청 파일: R-001` 한 줄로 남긴다(`request_name_selection`, 독립 검증 N-1). 파일은 작업 트리가 아니라 push 한 커밋의 git 객체에서 읽는다(심볼릭 링크로 밖의 파일을 읽지 않게). 시험은 진짜 git 으로 위 흐름(이어 push·새 브랜치·main 합치기·리베이스·통합 브랜치)을 모두 돌린다.
**워크플로를 경로 필터 없이 브랜치만으로 거는 이유**: 공식 문서상 새 브랜치 첫 push 의 경로 필터 평가는 '가장 깊은 push 커밋의 조상의 부모'와의 두 점 비교로 확인할 수 있다. 그래도 모든 push 에서 도는 짧은 실행(새 파일이 없으면 한 줄 남기고 종료 0, 전송 0)을 감수하고 필터를 쓰지 않는 쪽이 더 안전하고 단순해 유지한다. 같은 그룹에서 **대기 중인 실행은 새 실행이 오면 취소되고**(GitHub 규칙) 취소된 push 의 요청 파일은 다음 실행이 알리지 못하므로, 동시 실행 그룹은 `ai-request-<커밋>` 로 push 마다 다르게 두었다(병렬로 돌아도 각 실행이 자기 push 범위만 보므로 중복이 없다).

**알림 메시지**: `🔔 AI 요청 R-001 · 병합 부탁`(급하면 ` 🚨 급함`) / 제목(80자) / 요약(300자) / `관련 PR: #번호`(있을 때) / 확인·결정 종류에는 `답하는 법: 아래 [답하기] → 양식에서 R-001 선택` / 한 push 에 담지 못한 요청이 있으면 마지막 통에 `… 외 N건`. 제목·요약은 `safe_text`(비밀 모양 가리기·보이지 않는 문자·제어 문자 제거·한 줄로 접기·`://` 풀어 쓰기·HTML 이스케이프)에 더해 `@` 를 전각으로 바꿔 멘션 링크가 되지 않게 한다. 한 push 에 3통(`MAX_REQUEST_MESSAGES`), 한 실행(프로세스)에서 5통 상한(`notify.MAX_MESSAGES`)과 통 사이 1.1초는 그대로다. 버튼은 최대 4개(`요청 열기`=이 브랜치의 그 파일, `PR 열기`=`…/pull/<번호>`, `답하기`=`…/issues/new/choose`, `사용법`=기본 브랜치의 사용법 문서)이고 경로는 퍼센트 인코딩하며 `notify.allowed_url` 허용 목록을 통과한 주소만 버튼이 된다.

**응답 이슈 접수**: 이벤트는 `GITHUB_EVENT_PATH` 파일에서 파이썬이 읽는다(이슈 글이 `run:`·명령 줄·환경변수·`$GITHUB_OUTPUT`·워크플로 명령 어디에도 들어가지 않는다). 순서: ① **신뢰 판정** — `issue.user.login` 이 저장소 소유자(`GITHUB_REPOSITORY_OWNER`)와 같고(ASCII 영문 대소문자만 무시, 계정 이름 모양이 아니면 비교하기 전에 거절 — `ſhine88pc`·켈빈 기호 같은 글자로 흉내 내지 못한다) `author_association` 이 정확히 `OWNER` 여야 한다. 아니면 코멘트·라벨·텔레그램 없이 로그 한 줄로 끝난다 ② 제목이 `[답변]`·`[요청]` 이 아니면 접수하지 않는다 ③ 본문의 양식 항목 제목(`### 요청 번호`·`### 답변`·`### 선택`·`### 메모`, 새 일은 `### 해 주었으면 하는 일`·`### 끝났다고 볼 기준`·`### 긴급도`·`### 진행 범위`)으로 값을 읽고 **검증된 값만** 담는다: 요청 번호 `R-` 와 숫자 세 자리, 답은 양식의 선택지 전체 문구와 글자 그대로 같을 것(짧은 말로 바꿔 담음), 선택은 영문·숫자·한글 1~3자(아니면 '표시하지 않음'), 메모는 **글자 수만**. 본문의 항목 제목이 두 번 나오면(메모 칸에 `### 요청 번호` 같은 줄을 심은 시도) 양식 모양 문제로 거절한다 ④ 라벨(`운영자응답`·`운영자요청`, 없으면 만들고 붙임) ⑤ 접수 코멘트 **한 번**: 맨 앞 표지 `<!-- ack:v1 -->` 가 있고 **작성자가 `github-actions[bot]` 인** 코멘트가 이미 있으면 달지 않는다(낯선 사람이 표지를 흉내 내 접수를 막지 못하게, 코멘트는 첫 100개만 본다). 만들어졌는지 모호한 실패(응답 유실·5xx·429·연결 오류)는 같은 요청을 그대로 되풀이하지 않고 표지를 다시 찾아 있으면 달린 것으로 본다 ⑥ 텔레그램은 **이번에 코멘트를 새로 단 때만**(재실행에서 두 번 가지 않게). 요청 번호가 이 저장소 기본 브랜치의 요청함에 없으면 코멘트에 중립 사실 진술 한 줄('요청 번호 R-007 은 AI 가 자기가 보낸 요청과 대조해 처리합니다(…정상일 수 있습니다)')을 더하고 접수는 한다(요청 파일은 병합 전 작업 브랜치에 있는 것이 보통이라 기본 브랜치에서 안 보이는 것이 정상일 수 있고, 그래서 '번호를 다시 확인하세요' 같은 말은 쓰지 않는다 — 독립 검증 N-2). `[요청]`(새 일)은 **접수만** 한다: T3 승인이 아니므로 코멘트·텔레그램에 '진행 범위'(논의·준비까지만 / 구현까지, T3 제외)만 적고 승인으로 읽힐 말은 쓰지 않는다(독립 검증 B-1). 양식 모양이 틀리면 고정 문구만으로 된 설명 코멘트를 한 번 달고 텔레그램은 보내지 않는다. 실패는 모두 `::warning::` 이고 종료 코드는 0(사용법 오류만 2)이다.
GitHub REST 는 `urllib` 만 쓴다: 토큰은 `Authorization` 헤더에만, 오류 문구는 HTTP 상태·클래스 이름·GitHub 가 준 짧은 설명(비밀 모양을 가리고 한 줄로 접은 것)뿐, 응답은 2MB·요청은 20초까지, 일시 오류(429·5xx·연결 오류)는 한 번 다시 시도한다.

**통제와 한계**

| 위협 | 통제 | 한계·미확인 |
|------|------|-------------|
| 낯선 사람이 공개 저장소에 이슈를 열어 승인을 위조 | 소유자 login + `OWNER` 둘 다(이벤트 값), 소유자가 아니면 아무 일도 하지 않음, 본문의 `author_association` 같은 글은 보지 않음 | 저장소 소유자가 조직이면 접수하지 않는다(개인 계정 저장소 전제) |
| AI 가 자기 자격증명으로 소유자 명의의 이슈를 만들어 스스로 승인 | G-S9 규칙(AI 는 자기 자격증명·push 용 토큰으로 이슈·코멘트를 쓰지 않는다), 위조 이슈도 접수 워크플로가 휴대폰에 `✅ 답변 접수` 를 보내므로 운영자가 알아챌 수 있음(사용법 5장) | **기술적으로는 막지 못한다**(이 PC 의 AI 세션은 push 용 자격증명을 갖고 있다) — 규칙과 탐지에 기댄다 |
| `[요청]` 양식을 T3 승인으로 오해 | `[요청]` 은 승인이 아니다(G-S9, 양식 안내·접수 코멘트·텔레그램이 '진행 범위'만 적고 FORM-1 이 안내 문장을 고정). T3 는 번호 있는 `decision` 요청 + `[답변]` | — |
| 필수 드롭다운이 첫 선택지를 미리 보여 줘 요청 번호만 쓰고 올려도 `승인` 이 됨 | `답변` 의 첫 선택지를 `보류` 로 두고 `default: 0` 으로 미리 선택(FORM-1 이 고정), 양식 안내·사용법에 '반드시 직접 고르세요' | 필수 드롭다운의 초기 표시를 공식 문서가 적지 않는다(미확인) — 그래서 어느 쪽이어도 안전한 값을 첫째로 뒀다 |
| 이슈·요청 파일의 글로 명령·알림 위조 | 글은 `run:`·명령 줄에 들어가지 않고(검증기 WF-14 가 `run` 에 GitHub 표현식을 금지), 코멘트·텔레그램에는 검증된 값만 | 메모 글자 수만 싣는다 — AI 는 이슈 본문을 직접 읽으므로 그 글은 **데이터**로만 쓴다(AGENTS.md) |
| 푸시 알림 워크플로로 시크릿 유출 | 시크릿은 단계 env 로만(WF-13·WF-14), 권한 contents 읽기, `pull_request_target`·`issue_comment`·`workflow_run` 금지, 토큰은 로그·요약·예외에 없음 | 저장소 시크릿은 모든 브랜치의 워크플로가 읽을 수 있다(쓰기 권한이 있으면 누구나 같은 길로 읽을 수 있음 — 기존 한계, G-C12) |
| 중복·도배 | 두 차이의 교집합·git 실패 시 전송 중단·한 push 3통·통 사이 간격 | 경로 필터를 쓰지 않아 푸시마다 짧은 실행이 생긴다. 같은 이름의 요청 파일을 서로 다른 두 브랜치가 따로(다른 커밋으로) 더하면 각각 알린다. **요청 파일을 가진 커밋이 든 두 브랜치를 한꺼번에 push 하면 둘 다 '다른 브랜치에도 있다'고 보고 아무도 알리지 못한다**(독립 검증 N-1 — 로그에 `다른 브랜치에도 있어 알리지 않은 요청 파일` 줄이 남고, 먼저 올려 알림 실행이 끝난 뒤 다음 것을 올리면 정상) |
| 접수 누락 | 코멘트 실패는 경고만(이슈는 그대로, AI 가 읽음), 응답 유실 시 표지 재확인 | AI 가 꺼져 있으면 다음 세션에서 처리한다. 이슈를 고치면 접수 확인은 다시 오지 않는다 |
| 이슈 수정 시스템과의 충돌 | 두 양식에 `blog-control` 라벨이 없고 제목이 `[페이지 수정]`·`[이미지 변경]` 이 아니라 `issue-edit.yml` 의 `if` 가 거짓(시험이 계산) | — |

**관측이 필요한 것**(실제 GitHub·텔레그램에서 한 번도 돌려 보지 않았다): 병합 뒤 ① 이슈 양식 둘이 New issue 목록에 보이는지(기본 브랜치에서만 읽힌다) ② `ai/claude/**` 에 요청 파일을 하나 push 했을 때 텔레그램 도착·버튼 주소(한글 경로 인코딩) ③ 새 브랜치 첫 push 에서 `before` 가 0 인 경우의 동작 ④ 양식으로 연 이슈에 접수 코멘트·라벨·텔레그램 ⑤ `GITHUB_TOKEN` 이 만든 라벨·코멘트가 다른 워크플로(확인 필요 모음 등)를 일으키지 않는지 ⑥ 이슈 본문이 양식 항목 제목 그대로(`### 요청 번호`)로 만들어지는지(파서가 이 모양에 기댄다) ⑦ 접수 코멘트의 작성자 login 이 `github-actions[bot]` 인지(아니면 멱등 검사가 같은 이슈의 재실행에서만 깨진다) ⑧ 소유자가 연 이슈의 `author_association` 이 `OWNER` 로 오는지(아니면 `접수하지 않음` 한 줄이 로그에 남는다) ⑨ `ai/claude/**` 브랜치를 지운 뒤 Actions 목록(삭제 push 에 알림 워크플로가 도는지·어떻게 보이는지 — 문서가 모호하다) ⑩ 필수 드롭다운 `답변` 이 `보류` 를 미리 선택해 보여 주는지.

## 5. 상태·멱등성·동시성

- **이력 스키마 v1**: `v`, `blog`, `date`(KST `YYYY-MM-DD`), `generated_at`(ISO, KST), `status`, `topic`, `topic_source`(`seed`·`llm`·`override`), `title`, `labels`, `url`, `post_id`, `model`, `attempts`, `reasons[]`.
  `status`: `posted`(즉시 게시) · `draft_uploaded`(Blogger 초안함에 업로드 — `post_id`·`url`은 API 응답, 블로그 ID는 기록하지 않는다) · `package_issued`(티스토리·네이버 초안 패키지 이슈를 만듦 — `post_id`는 이슈 번호, `url`은 이슈 주소, 공개되지 않음) · `draft`(저장소 파일에만 저장) · `generated_unpublished`(옛 기록: 게시 시크릿이 없던 때의 초안 — 지금은 게시 대상이 시크릿이 없으면 종료 2로 멈추고 기록하지 않는다) · `rejected` · `publish_failed`(게시·업로드·인증 점검 실패 — 인증 점검 실패는 글을 만들기 전이라 `topic`이 비어 있다) · `llm_failed` · `skipped_no_topic`.
- **일일 상한**: `posted`·`draft`·`draft_uploaded`·`generated_unpublished`·`package_issued` 건수가 `max_posts_per_day`에 도달하면 건너뛴다(`rejected`·`llm_failed` 등 글이 안 나온 실행은 세지 않는다). 예외로 `publish_failed`는 **응답에서 글 ID(`post_id`)를 읽은 것만** 센다 — 올리다 실패했어도 초안·글이 이미 Blogger에 만들어졌을 수 있어, 세지 않으면 같은 날 재실행이 초안을 또 만든다. 글 ID가 없는 실패(인증·네트워크 등)는 세지 않는다. 이 이유는 `DAILY_CAP` 주석과 요약에 적히고, 운영자는 Blogger 초안함·글 목록을 확인한다(`topic` 입력은 상한을 건너뛴다). 워치독은 `posted`·`draft_uploaded`를 '글이 나온 날'로 센다.
- **쿨다운**: 프로필 `topic_cooldown_days` 안에 같은 주제(유사도 0.8 이상)는 다시 쓰지 않는다.
- **교차 중복**: 다른 블로그의 이력 제목과 유사도 `other_blogs`(0.6) 이상이면 주제·제목 모두 탈락. (Chance 이력은 문자열·객체 혼합이라 `state.entry_titles`가 모두 처리한다.) **글자 유사도라 같은 언어 안에서만 걸린다** — 영문 글을 번역한 한글 제목은 유사도가 대체로 0.2 이하(독립 검증 측정 0.12~0.18)라 통과하므로 영·한 번역·복제는 코드가 못 잡고 운영자가 눈으로 확인한다(§7-1 '한글 AI·도구 프로필').
- **멱등 게시**: 게시 재시도 전에 같은 제목 글이 방금 올라갔는지 확인한다(응답만 실패한 경우의 중복 방지). 초안 패키지는 이슈 본문 첫 줄의 숨은 표지(`<!-- draft-id: <블로그키>-<날짜>-<해시> -->`)로 같은 초안의 이슈(열림·닫힘 모두)를 찾아 중복을 막는다(같은 글을 다시 올리려는 재시도만 막는다 — 표지의 해시가 제목·본문에서 만들어지므로 이력 파일이 사라진 날 다른 글이 만들어지면 이슈가 또 생긴다. 하루 상한은 이력 파일이 지킨다).
- **원자적 쓰기**: 임시 파일에 쓰고 교체한다. 손상된 이력은 읽지 못하면 실행을 멈춘다.
- **동시성**: 블로그마다 `concurrency: blogger-<key>`(공용 워크플로 안의 `generate` 잡, 초안 패키지는 `tistory-<key>`·`naver-<key>`), 매트릭스는 `max-parallel: 1`, push는 `pull --rebase` 후 최대 3회 재시도. Blogger 래퍼는 그 위에 **워크플로 단위 줄**(`blogger-en`·`blogger-ko`, `cancel-in-progress: false`)을 따로 둔다 — 안쪽 줄 `blogger-<블로그 key>`와 이름이 같으면 부르는 쪽과 불린 잡이 서로를 기다려 멈추므로 같은 이름을(GitHub 처럼 대소문자만 달라도 같은 이름이다) 쓰면 REG-6이 오류로 막는다.
- **시간**: 내부는 UTC aware, 날짜 경계는 KST, cron은 UTC.

## 6. 시크릿 전달 방식

레지스트리에는 역할별 **Secrets 이름**만 있다. Blogger 는 채널별 래퍼 워크플로(`blogger-en.yml`·`blogger-ko.yml`)가 `secrets:` 에 **그 블로그의 시크릿 이름을 하나씩 짚어**(`PIPELINE_SECRET_BLOG_ID` 항목에 `secrets.BLOGGER_BLOG_ID` 표현식을 넣는 식으로) 역할 이름 `PIPELINE_SECRET_<ROLE>` 으로 공용 워크플로(`blogger.yml`)에 넘기고, 공용 워크플로가 러너 단계의 환경변수로 그대로 넘기면 러너가 그 값을 쓴다(`registry.resolve_secrets`). `secrets: inherit` 는 쓰지 않는다(모든 시크릿이 이름 없이 넘어가 WF-13 이 오류로 막는다). 영문 래퍼는 `BLOGGER_*` 4종, 한글 래퍼는 `BLOGGER_KO_*` 4종만 넘기고 `GEMINI_API_KEY`만 공유한다 — 두 블로그가 계정·OAuth 클라이언트를 나누는 이 구조가 레지스트리 시크릿 이름과 래퍼 매핑이 어긋나면 깨지므로 검증기 REG-6이 둘을 대조한다. 로컬 수동 실행은 레지스트리에 적힌 이름(`BLOGGER_BLOG_ID`·`BLOGGER_KO_BLOG_ID` 등)을 그대로 읽는다. 새 Blogger 블로그는 새 채널이라 새 래퍼가 필요하다(§7-A) — 시크릿 이름은 래퍼와 레지스트리 두 곳에 같게 적는다.

텔레그램 알림용 시크릿 `TELEGRAM_BOT_TOKEN`·`TELEGRAM_CHAT_ID`는 블로그 시크릿이 아니라 저장소 공통 값이라 레지스트리를 거치지 않는다. 워크플로가 알림을 부르는 단계(`chanceblog.yml`의 알림 단계·`blogger.yml`의 러너 단계(부르는 래퍼가 `secrets:`로 같은 이름으로 넘긴 값)·`ops-inbox.yml`·`telegram-test.yml`)의 `env`에 같은 이름으로 넘기고 (그 밖의 자리에 쓰면 검증기 WF-13 이 오류), `pipeline/notify.py`가 환경변수에서만 읽는다(§4-5). 시크릿이 없으면 알림은 꺼져 있고 다른 동작은 바뀌지 않는다.

**시크릿 값의 보이지 않는 문자**(2026-10-28, 결함 D-79, 이슈 #58): 채팅 앱·문서에서 복사해 붙여넣은 값에는 폭 없는 공백(U+200B)·단어 결합자(U+2060)·BOM(U+FEFF) 같은 글자가 섞이기 쉽고, `str.strip()` 은 이를 못 지워 인증이 이유를 알려 주지 않고 어긋났다. 그래서 값은 `pipeline/console.py` 의 `clean_secret`(보이지 않는 문자 목록·제어 문자·서식 문자를 어디에 있든 지우고 앞뒤 공백을 자름)을 거쳐 쓴다 — `registry.resolve_secrets`(Blogger·초안 패키지 러너의 Gemini 키·블로그 시크릿 전부)와 텔레그램 `Notifier`(토큰·채팅 ID)가 같은 함수를 쓴다. 지운 시크릿이 있으면 러너가 **이름만**(`registry.cleaned_secret_names`, 레지스트리에 적힌 GitHub 시크릿 이름) `::notice::` 한 줄과 인증 점검(`AUTH_CHECK_OK`·`AUTH_CHECK_FAILED`) 실행 요약에 남기고 '원본에서 바로 복사해 다시 등록하라'고 권한다(값·길이는 어디에도 쓰지 않는다). 보이지 않는 문자가 없는 값은 예전과 똑같이 앞뒤 공백만 자른 값이라 출력이 바뀌지 않는다. **범위 밖(열린 문제)**: Chance 엔진(`generator.py`)과 이슈 수정(`pipeline/edits`)은 `GEMINI_API_KEY`·`UNSPLASH_ACCESS_KEY` 를 환경변수에서 직접 읽어 이 함수를 쓰지 않는다.

## 7. 블로그 추가 플레이북

### A. 같은 플랫폼(Blogger) 블로그 추가 — 채널 워크플로 필요(`channel` 규칙, §3)

채널(`channel.label`)은 블로그마다 달라야 하고 그 블로그 워크플로의 `name` 접두사와 같아야 하므로, **Blogger 블로그를 하나 더하면 채널 래퍼 워크플로도 하나 더한다.** `blogger.yml`은 2026-10-27에 재사용 워크플로(`on: workflow_call`, `[내부] Blogger 글 작성 공용(직접 실행하지 마세요)`)가 됐고, 채널마다 얇은 래퍼(`blogger-en.yml` = `[Blogger 영문]`, `blogger-ko.yml` = `[Blogger 한글]`)가 자기 cron·수동 입력·동시 실행 줄·시크릿 이름을 갖고 `blog: <레지스트리 key>`를 `with:`로 넘겨 공용 워크플로를 부른다. 새 블로그는 가장 가까운 래퍼를 복사해 이름의 라벨·run-name·cron·`with.blog`·동시 실행 줄 이름·`secrets:` 의 시크릿 이름을 바꾸고 `registry.CHANNEL_LABELS`에 라벨을 더한다. 래퍼가 레지스트리와 맞는지는 검증기 **REG-6**(§3)이 PR 단계에서 확인한다 — `with.blog`·다섯 입력의 명시·넘기는 시크릿 이름, 호출 잡의 `permissions` 가 **정확히 `contents: write` 하나**(`id-token`·`issues` 같은 추가 권한은 오류), 동시 실행 줄 이름이 래퍼끼리·공용 워크플로 안의 줄과 다름(GitHub 처럼 **대소문자 무시**). 정기 실행에는 `github.event.inputs` 가 없어 문자열 입력 `topic` 이 null 이 되므로 래퍼는 `with.topic` 에 표현식 `github.event.inputs.topic || ''` 를 넣어 빈 문자열을 직접 넘긴다(문자열 입력에 null 을 넘길 때의 동작이 GitHub 문서에 없다). 한글 Blogger(`blogger_kcyoon`)가 이 절차의 첫 사례다.

| # | 누가 | 할 일 |
|---|------|-------|
| 1 | 사용자 | Blogger 블로그 생성, 블로그 ID 확인, Google OAuth 클라이언트 준비(**동의 화면 "프로덕션"** — 테스트 상태는 7일 후 토큰 만료, D-11), refresh token 발급 |
| 2 | 사용자 | GitHub Secrets 등록: 블로그 전용 이름 4종(예: 한글 Blogger 는 `BLOGGER_KO_BLOG_ID`, `BLOGGER_KO_CLIENT_ID`, `BLOGGER_KO_CLIENT_SECRET`, `BLOGGER_KO_REFRESH_TOKEN`). **구글 계정·Cloud 프로젝트·OAuth 클라이언트도 다른 블로그와 따로** 만든다. LLM 키는 `GEMINI_API_KEY` 공유 |
| 3 | AI (T3 승인 후) | `blogs.json`에 항목 추가: **`mode`를 항목에 직접 적는다**(예: `"draft"`. 적지 않으면 검증기 `REG-1` 오류 — `defaults.mode`를 물려받은 새 블로그가 의도하지 않은 모드로, 예를 들어 기본값이 `auto`일 때 시크릿 등록만으로 바로 자동 게시되는 일을 막는다), 고유 `key`, **`channel`**(채널 라벨 — 그 블로그 워크플로 `name`의 `[라벨]` 접두사와 같은 글자, §3), `secrets` 이름, `state`(전용 history·content_dir), 프로필·프롬프트, **`ads`는 적지 않거나 `off`**(신규 채널은 품질 게이트를 통과하기 전까지 광고 없이 시작한다, §3 '광고 선언') |
| 3-1 | AI (T3 승인 후) | **채널 래퍼 워크플로**를 더한다(위 설명). 새 채널 라벨은 `registry.CHANNEL_LABELS`에도 넣고, `schedule.cron`은 래퍼의 cron 과 같게 적는다(REG-2). 시험이 래퍼를 이름으로 알고 있으므로(`tests/blogger_workflow_helpers.py`의 `WRAPPERS`·`WRAPPER_LABELS`) 새 래퍼를 더하면 거기에도 한 줄을 더해야 이벤트·입력 조합 대조와 시크릿 분리 시험이 새 래퍼까지 본다 — REG-6 은 래퍼의 구조(블로그 key·시크릿 이름·권한·동시 실행 줄)만 보고 `with` 식의 의미는 보지 않는다 |
| 4 | AI | `python -m pipeline.registry` · `python scripts/validate_repo.py` · `python -m unittest discover -s tests` · `actionlint` |
| 5 | AI/사용자 | Actions → 그 블로그의 래퍼(예: `[Blogger 한글] 글 자동 작성`) → Run workflow(`인증 점검만 실행`으로 먼저 인증을 확인한 뒤, `연습 실행` 체크 해제, `publish=draft`)로 Blogger 초안함에서 글 확인(체크를 풀면 실제 Gemini로 초안을 만들어 저장소에 커밋한다. 시크릿을 등록하기 전이면 `publish=off`로 저장소 초안만) |
| 6 | 워치독 | `draft` 상태로 3일 이상 운영하며 `rejected`·실패 이슈가 없는지 본다 (카나리) |
| 7 | 사용자 | `mode: "auto"` 전환 승인(T3) |

블로그 언어가 기존 프로필과 다르면(예: 영문) 3단계의 프로필·프롬프트·스텁을 §7-1의 체크리스트로 새로 만든다. 글 언어 검사·주제 가드레일 목록·시드·시험이 언어마다 필요하다. 블로그의 `languages`에 프로필의 `language`가 없으면 검증기가 오류로 막는다(D-32 재발 방지).

### B. 새 플랫폼(WordPress, Medium, 다른 Jekyll 저장소 등) — 게시 어댑터가 있는 채널

1. **정책 확인(T3)**: 해당 플랫폼 약관이 자동 게시를 허용하는지, 계정·API 방식이 무엇인지 사용자와 확정한다. **공식 자동 게시 수단이 없으면 어댑터를 만들지 않고 §7-B-2의 초안 패키지로 간다**(티스토리·네이버가 그렇다).
2. `registry.PLATFORMS`에 필수 시크릿 역할을 등록한다.
3. `pipeline/publishers/<platform>.py`에 어댑터를 만든다. 계약: `healthcheck()`, `publish(title, html, labels, draft)`, 인증 실패와 API 오류의 `PublishError(code)` 구분, **재시도 전 중복 확인**, 오류 메시지 시크릿 마스킹, `service_factory` 주입으로 가짜 서비스 테스트.
4. `pipeline/run.py`의 플랫폼 분기를 확장한다(지금은 `blogger`(게시 어댑터)와 `tistory`·`naver`(초안 패키지, `default_publisher_factory`)가 있다 — Phase 2에서 어댑터 레지스트리로 일반화).
5. 이후 A의 3~7단계.

### B-2. 공식 자동 게시 수단이 없는 채널 — 초안 패키지(티스토리·네이버, 2026-10-27 운영자 승인 D4·D7, T3)

**왜 어댑터가 아니라 패키지인가**(2026-10-27 확인, 근거: [`docs/analysis/2026-10-27_channel-management-plan.md`](./analysis/2026-10-27_channel-management-plan.md) §5-1·§11):

| | 티스토리 | 네이버 블로그 |
|---|---|---|
| 자동 게시 수단 | 없음. 오픈 API는 2024-02 종료(공지 2664). 약관·운영정책에 자동화·AI 생성물 조항은 없고 동일 내용 반복·스팸성 게시물 금지 같은 일반 조항만 있다 | 공식 글쓰기 API 2020 종료. 허락 없는 자동 게재는 약관상 금지(`docs/REQUEST_BRIEFING.md`) |
| 에디터 | PC 웹 에디터 3모드(기본·마크다운·HTML), 모드를 바꾸면 서식이 달라질 수 있다는 공식 경고. **모바일 앱 에디터에는 HTML 블록이 없다** → HTML 붙여넣기는 PC 웹 필요 | 스마트에디터. HTML 직접 입력 모드는 없다고 알고 있으나 **미확인**, 서식 있는 글을 붙여넣을 때의 서식 보존도 **미확인** |
| 이미지 | 업로드 개당 20MB. **외부 URL `<img>`는 본문에는 보이나 목록 썸네일에는 안 나온다**(공식 FAQ 39670) → 대표 이미지 1장은 직접 업로드 | 미확인 |
| 정책 신호 | 공지 2705(2026-10-12): 크리에이터 선정에서 아쉬운 사례로 'AI가 쓴 글을 거의 그대로 발행해 경험·생각이 드러나지 않는 글'(적용 2027-01-02, 발행 자체에는 영향 없다고 밝힘) | — |
| 설계 | **초안 패키지 + 운영자 복사 발행**. 로그인·세션 자동화는 만들지 않는다 | 같음. 글감은 Chance 글의 한국어 각색이 아니라 **자체 주제**(원고 변형 복제 금지, D7) |

**무엇을 만들었나**

- 레지스트리: `mode: package`, `platform: tistory`·`naver`(필수 시크릿은 `llm_api_key` 뿐), 금지 시크릿 검증(§3). **실제 `pipeline/blogs.json`에는 두 채널의 항목이 없다** — 블로그 주소·주제(사용자 입력)를 받기 전이라 대상 0개로 초록이다.
- 러너: `pipeline/run.py`의 `delivery == "package"` 경로(기존 Blogger 경로는 바꾸지 않았다 — `tests/`와 바이트 비교로 증명, WORKLOG). 프로필·게이트·주제 선정·하루 상한·이력 규약은 그대로 재사용하고 이력 상태 `package_issued`를 더했다.
- 어댑터: `pipeline/publishers/issue_package.py` — `build_issue()`(순수 함수: 제목·본문·라벨·초안 번호)와 `IssuePackagePublisher`(GitHub REST, urllib, 의존성 추가 없음).
- 워크플로 2개: `tistory.yml`(`[티스토리] 초안 패키지 만들기`)·`naver.yml`(`[네이버] 초안 패키지 만들기`). 권한은 `contents: write`(이력)·`issues: write`뿐이고 시크릿은 Gemini 키뿐이다.

**이슈 한 개의 모양**(제목 `[초안][<채널>] <글 제목 60자>`, 라벨 `초안`·`채널:<라벨>`, 본문 맨 위 숨은 표지 `draft-id`): ① 복사용 제목(코드 상자) ② 본문 — 티스토리: HTML 모드에 붙여넣을 순수 HTML(코드 상자, `h2~h4`·`p`·`ul`·`ol`·`strong`·`em`·`br`·`blockquote`만 — 스타일·스크립트·iframe 없음) / 네이버: 이슈 화면에서 선택·복사할 서식 있는 글(렌더링되는 마크다운)과 평문 상자 ③ 해시태그(쉼표 구분, `#` 없음, 코드 상자) ④ 이미지 표(번호·용도·주소·출처·라이선스·**AI 생성 이미지 여부**, Unsplash는 작가·Unsplash 링크 표기 문구) ⑤ 근거 출처 ⑥ 게이트 점검 결과(**사실 확인은 하지 않았다**고 적는다) ⑦ 발행 체크리스트(8항목: 제목 붙여넣기 · HTML 모드 본문 · 대표 이미지 업로드 · 카테고리·홈주제 · 태그 · **직접 경험·판단 문단을 더했다** · 광고·협찬 표기 · 발행 후 주소 기록하고 이슈 닫기). 닫으면 '발행 완료', 쓰지 않을 초안은 라벨 `폐기`를 붙이거나 닫는다. 현재 자동으로 채워지는 이미지·출처는 없고(생성 파이프라인에 그 단계가 없다) 어댑터가 받을 자리와 표만 있다.

**AI 출력은 신뢰하지 않는다**(G-L9): 이슈 본문·제목이 되기 전에 `@멘션`·`#123`·`GH-123`·HTML 주석 시작(`<!--`) 뒤에 영(0)폭 공백을 넣어 알림·자동 링크·숨은 표지 위조가 되지 않게 하고(코드 상자 안도 같다. 주소·이메일 안의 것은 그대로), 복사 상자는 본문 안의 가장 긴 백틱 줄보다 한 칸 더 긴 펜스로 감싸 빠져나오지 못하게 하며, HTML 은 `gates.sanitize_html`을 한 번 더 거친 뒤 제어 문자(NUL·ESC)와 글자 방향 서식 문자(U+202E 등)를 지우고(영폭 공백은 남긴다) 네이버 마크다운은 `< > & [ ] | $ \` 같은 문법 문자를 모두 이스케이프한다. 제목 접두사·라벨은 고정값, 길이는 이슈 한도 안(넘으면 잘라 올리지 않고 `too_long`으로 실패). 이슈를 셸로 넘기지 않고 파이썬에서 API로만 쓴다.

**공개 저장소라는 점**: 이 저장소는 공개라 초안 이슈도 공개 페이지(검색 색인 가능)다 — 운영자가 블로그에 올리기 전에 같은 글이 먼저 공개되는 셈이다(승인된 D4, 공개 저장소에서 볼 수 있는 `_blogger_drafts/` 저장소 사본과 같은 수준의 노출). 이슈 본문의 주소(URL)는 소독하지 않는다(주소 안의 `@`·`#`은 링크의 일부 — AI 가 GitHub 이슈 주소를 쓰면 GitHub 이 그 이슈에 역링크를 만들 수 있다, 미확인).

**멱등·적체**: 같은 초안 번호의 이슈가 이미 있으면(열림·닫힘 모두) 새로 만들지 않는다. 이슈 만들기 요청은 한 번만 보내며 만들어졌는지 모호하면 다시 만들지 않고 멈춘다(§4-1). 같은 채널에 열린 `초안` 이슈가 3건 이상이면 새로 만들지 않는다(`PACKAGE_BACKLOG`; 라벨 `폐기`가 붙은 것은 세지 않는다 — 폐기 = 라벨 `폐기` 또는 닫기, `[운영] 확인 필요 모음`의 초안 현황판과 같은 규칙). 라벨은 없으면 만든다(색·설명 고정).

**하지 않는 것**: 티스토리·네이버 로그인·글쓰기·세션·쿠키 자동화, 계정 정보의 저장·처리, 블로그·계정 자동 개설, 채널 간 상호 링크, 원고 변형 복제. 신규 채널은 품질 게이트를 통과하기 전까지 광고 없이 시작한다(G-C10).

**블로그 주소·주제를 받으면 해야 할 일 체크리스트**(지금은 사용자 입력 대기라 만들지 않았다)

| # | 누가 | 할 일 |
|---|------|-------|
| 1 | 사용자 | 블로그 개설과 **주소·주제·카테고리 이름** 결정(네이버는 자체 주제 — Chance 글 각색 아님). 새 시크릿은 없다(Gemini 키 `GEMINI_API_KEY` 공유) |
| 2 | AI (T3 승인 후) | 프로필 `pipeline/profiles/<이름>.json`(한국어 Blogger 프로필 구조를 따라: 길이·제목·라벨 한도, 금지 패턴·주제 가드레일, `allow_links`, 시드 주제, `topic_expand_prompt`, AI 사용 고지 `disclosure_html`, 지어낸 경험·제품 광고 어조 금지 `prompt_extra`)과 프롬프트 파일(```text 블록과 `{topic}`) |
| 3 | AI | `blogs.json` 항목 추가: `key`, `name`, `channel`(`티스토리` 또는 `네이버`), `platform`, `url`(https), **`mode`**(T3 승인 뒤 `"package"` — 공개되지 않는 모드라 이 값으로 시작해도 사이트·블로그에는 아무 일도 없다. 승인 전에 항목만 넣어 두려면 `"off"`, 그동안 대상 0개), `workflow`(`.github/workflows/tistory.yml`·`naver.yml`), `entrypoint: pipeline/run.py`, `prompt`, `profile`, `state`(전용 history·content_dir), `schedule.cron`(워크플로와 같게: 티스토리 `20 5 * * *`, 네이버 `20 6 * * *`), `limits.max_posts_per_day`, `secrets: {"llm_api_key": "GEMINI_API_KEY"}`, `ads: "off"` |
| 3-1 | AI | 첫 실제 package 블로그를 넣는 PR에서 **걸림돌 시험을 함께 고친다**: `tests/test_package_registry.py`의 `test_the_real_registry_has_no_package_blog_yet`는 실제 레지스트리에 package 블로그가 없다고 못 박은 시험이다. 실제 레지스트리의 키 목록을 `["chance", "blogger_macat"]`로 고정한 기존 시험(`grep '"chance", "blogger_macat"' tests/*.py` — `tests/test_registry.py`·`tests/test_plan_and_watchdog.py`·`tests/test_auth_check_only.py`·`tests/test_ops_inbox_script.py`)도 새 키를 반영하고, 실제 레지스트리 키 목록·`mode`를 고정한 `tests/test_batch2_integration.py`의 `test_the_real_registry_is_unchanged_by_the_merge`와 실제 확인 필요 모음 표가 Chance·Blogger 두 줄이라고 못 박은 `tests/test_ops_inbox_drafts.py`의 `test_the_real_registry_gives_chance_and_blogger_rows_with_nothing_pending`(블로그가 늘면 표에 줄이 더해진다)도 고친다(블로그를 하나 더 하는 PR이면 늘 걸린다) |
| 3-2 | AI (**T3 승인**) | 새 블로그의 이력 파일(`state.history`, 루트의 `*.json`)을 `_config.yml`의 `exclude`에 더한다. Jekyll은 밑줄로 시작하지 않는 루트 파일을 사이트에 그대로 내므로(기존 `history.json`·`blogger_history.json`이 `exclude`에 있는 이유와 같다) 안 넣으면 이력이 공개 주소가 된다. `_config.yml`은 광고 표면이라 T3 승인이 필요하고, 봇 커밋은 시험을 돌리지 않으므로(`tests/test_site_cleanup.py`가 새 루트 파일을 잡는 것은 다음 PR부터) 항목을 넣는 PR에서 미리 더한다. 저장소 초안 사본 폴더(`content_dir`)는 밑줄로 시작하는 이름(`_tistory_drafts` 등)으로 정해 사이트에 내보내지 않게 한다 |
| 4 | AI | `python -m pipeline.registry` · `python scripts/validate_repo.py` · 전체 시험. 프로필 시험(시드 전부 가드레일 통과, 정상·위험 문장 표본) |
| 5 | 사용자 | 병합 직후, 첫 정기 실행(티스토리 14:20·네이버 15:20 KST) 전에: Actions → `[티스토리] 초안 패키지 만들기`(또는 `[네이버] …`) → Run workflow(`연습 실행` 체크 유지) → 실행 요약의 이슈 본문 미리보기 확인(`mode: off`인 동안은 정지라 연습도 대상 0개). 정기 실행이 먼저 돌아도 첫 초안 이슈가 만들어질 뿐 공개되는 것은 없다 |
| 6 | 사용자 | **비공개 시험 글 1건**으로 확인: 태그 입력 방식·HTML 붙여넣기 뒤 서식·대표 이미지 업로드(회사 PC에서 파일 업로드가 되는지)·예약 발행 화면 |
| 7 | 사용자 | 첫 실제 초안 이슈(정기 실행 또는 `연습 실행`을 푼 수동 실행)를 열어 복사 상자·표·체크리스트가 보이고 위 시험 글에 붙여넣을 수 있는지 확인. 항목을 `off`로 넣어 두었다면 먼저 `mode`를 `package`로 바꾸는 T3 승인과 한 줄 수정이 필요하다 |
| 8 | 워치독 | 3일 이상 운영하며 실패·방치 이슈가 없는지 본다 |

### C. 또 하나의 Jekyll(git) 블로그

`jekyll-git` 어댑터와 공용 엔진이 필요하다(Phase 3). 그 전에는 `generator.py`를 복사하지 않는다.

## 7-1. 프로필(콘텐츠 정책)과 주제 가드레일

블로그마다 프로필 하나(`pipeline/profiles/<이름>.json`)가 "무엇을 어떤 기준으로 게시하는가"를 정한다. 레지스트리의 `profile`이 가리키고, 정규식은 Python `re`로 **대소문자를 무시**해 검사한다. 같은 성격의 블로그는 프로필을 재사용하고, 언어가 다르면 같은 구조의 프로필을 새로 만든다. 지금은 영문 `blogger_practical_en`(macat0722, 모드 off), 한국어 `blogger_practical_ko`(쓰는 블로그가 없다), 한글 AI·도구 프로필 `blogger_ai_tools_ko`(kcyoon, 모드 off — 아래 별도 절)가 있다.

### 프로필 필드

| 필드 | 뜻 | 한국어 | 영어 |
|------|----|--------|------|
| `language` | 글 언어 검사(`LANG`)의 종류. `ko`·`en`만 허용하고 그 밖의 값은 레지스트리가 오류로 막는다(모르는 언어는 검사가 조용히 꺼지므로) | `ko` | `en` |
| `min_hangul_ratio` / `min_latin_ratio` | `ko`: 본문 글자 중 한글 비율 하한(기본 0.5). `en`: 글자(숫자·기호 제외) 중 라틴 문자(é·ñ 포함) 비율 하한(기본 0.9). 영어는 **제목에 라틴 문자가 아닌 글자가 하나라도 있으면** 탈락한다 | 0.5 | 0.9 |
| `length` · `title` · `labels` | 본문 글자 수, 제목 글자 수, 라벨 개수·글자 수 | 900~3200 · 8~60 · 1~5개 20자 | 2400~7500 · 15~70 · 1~5개 30자 |
| `structure` · `similarity` · `topic_cooldown_days` · `max_attempts` · `allow_links` | 소제목 3개 이상·목록 필수, 같은 블로그 0.72·다른 블로그 0.6 제목 유사도, 쿨다운 60일, 재작성 3회, 링크 제거 | 같음 | 같음 |
| `prompt_extra` | 프롬프트 뒤에 붙는 추가 규칙(문자열 배열). 쓰지 말 것에 다이어트·간 건강도 들어 있다 | 한국어 4줄 | 영어 5줄 |
| `topic_expand_prompt` | 시드를 다 쓴 뒤 LLM에 새 주제를 청하는 지시문(`{n}`·`{min}`·`{max}`·`{avoid}` 자리표시자, `{n}`·`{avoid}` 필수). **없으면 코드(`pipeline/topics.py`)의 한국어 지시문** — 새 언어를 코드 수정 없이 붙이기 위한 필드 | 없음 | 있음 |
| `banned_patterns` | 효능·안전 **단정**(완치·기적·부작용 없음·100% 효과·병원 갈 필요 없음·약을 끊어라 등). 제목+본문 전체에 예외 없이 건다 → `BANNED` | 10개 | 13개 |
| `title_banned_patterns` | 클릭 미끼 제목(충격·비밀·의사들이·`!!` 등) → `TITLE_BANNED` | 11개 | 12개 |
| `leak_patterns` | AI 자기 언급·코드 펜스·템플릿 잔재·머리표 잔여물 → `LEAK` | 12개 | 16개 |
| `banned_topic_patterns` | **주제 가드레일의 위험 어휘**: 주제 후보·생성된 제목·생성된 라벨에 예외 없이 건다 → (주제는 버림) · `TITLE_TOPIC` · `LABELS`. 수동 `topic`도 같은 목록을 거친다(`TOPIC_BLOCKED`) | 56개 | 67개 |
| `body_banned_patterns` · `body_safe_patterns` | (선택) 생성된 본문의 위험 표현과, 있어도 건너뛸 전문가 상담·면책 **절** → `BODY_TOPIC`. 없으면 본문 위험 낱말 검사를 하지 않는다 | 56개 · 4개 | 57개 · 4개 |
| `body_clause_split_patterns` | (선택) 문장을 절로 쪼개는 접속어·연결 어미(영어 `, but`·`, so`·`, though`·`, and`+새 절, 연결어 앞뒤의 쉼표가 있든 없든 `so`·`or`·`because`·`unless you`·`however` 등 + (도입구가 끼어도) 상담 구절, 한국어 `~지만`·`~하되`·`~는데`·`~서`·`그러므로`·`그렇기 때문에`…). `;` `:` `—` `--`와 띄어 쓴 하이픈은 모든 언어에 공통이라 코드에 있다. 상담 구절이 없는 절은 면제되지 않는다. 패턴마다 따로 컴파일한다(`(?i)`·같은 이름의 묶음도 된다) | 6개 | 7개 |
| `body_safe_veto_patterns` | (선택) 상담·면책 구절이 있어도 **면제하지 않는** 표현 — 용량(`400 mg`·`400mgs`·`100 ug`·`0.4 g`·`10,000 units`·`2 capsules`·`2 softgels`·`3 gummies`·`a 400-mg tablet`·`four hundred milligrams`, 한국어 `밀리그램`·`2알`·`반 알`·`두 캡슐`). 단위 `g`는 대소문자를 구분해 `5G`(통신)는 용량이 아니다 | 2개 | 2개 |
| `disclosure_html` | AI 사용·면책 문구. 게이트를 통과한 **뒤** 게시 직전에 붙인다(`append_disclosure`) | 한국어 | 영어(AI 도움·일반 참고용·진단/치료 대체 아님·전문가 상담) |
| `seed_topics` | 시드 주제(8~60자). 모두 `banned_topic_patterns`를 통과해야 한다(레지스트리 검증) | 32개 | 34개 |

레지스트리 검증(`registry.validate_profile`, 검증기 REG-1)은 위 필수 항목과 함께 ① 모든 정규식이 컴파일되는지, ② **빈 문자열에 맞는 정규식**(끝에 `|`가 남은 것 같은 실수 — 금지 목록이면 모든 글이 탈락하고 `body_safe_patterns`면 모든 문장을 건너뛰어 가드레일이 조용히 꺼진다)이 없는지, ③ 시드가 금지 주제 목록을 통과하는지, ④ `language`가 지원 언어인지, ⑤ 비율 필드·`prompt_extra`·`topic_expand_prompt`의 형식을 본다. 레지스트리 항목은 추가로 ⑥ 블로그의 `languages`에 프로필의 `language`가 들어 있어야 한다(영문 블로그에 한국어 프로필을 쓰는 어긋남 — D-32 — 이 다시 생기지 않게).

응답 머리표는 한국어 프롬프트가 `제목:/라벨:/내용:`, 영어 프롬프트가 `Title:/Labels:/Content:`다. 파서(`gates.parse_labeled_post`)는 한국어 머리표를 먼저 보고(한국어 응답의 결과·오류 문구는 그대로), 온전하지 않을 때만 영어 머리표를 본다. 두 가지를 섞어 빈 항목을 채우지는 않는다.

### 가드레일: 같은 위험 영역을 세 곳에서 막는다

위험 영역은 질병·치료·약·보충제·진단·임신·영유아·체중 감량(G-C4). 수동 작성 경로가 없어 모든 글이 자동 생성이므로, 모델이 안전한 주제를 받고도 위험한 내용으로 흐를 수 있다. 그래서 주제에만 걸던 규칙을 생성물에도 건다(운영자 승인 2026-10-26).

| 지점 | 검사 대상 | 쓰는 목록 | 예외 | 코드 |
|------|-----------|-----------|------|------|
| (a) 주제 후보 | 시드·LLM 확장 주제, **수동 `topic`** | `banned_topic_patterns` | 없음 | 후보에서 버림(`pipeline/topics.py`) · 수동 `topic`은 `TOPIC_BLOCKED`로 종료 2(`pipeline/run.py`) |
| (b) 제목 | 생성된 제목 | `banned_topic_patterns` | 없음 | `TITLE_TOPIC` |
| (b) 라벨 | 생성된 라벨 각각 | `banned_topic_patterns` | 없음 | `LABELS` |
| (c) 본문 | 정화된 본문 텍스트(면책을 붙이기 **전**) | `body_banned_patterns` | **절 단위**: `body_safe_patterns`에 맞는 절은 건너뛰되 `body_safe_veto_patterns`(용량)에도 맞으면 건너뛰지 않음 | `BODY_TOPIC` |
| (d) 단정 표현 | 제목+본문 전체 | `banned_patterns` | 없음 | `BANNED` |

`TITLE_TOPIC`·`BODY_TOPIC` 사유에는 걸린 낱말이 들어가(`'Melatonin'`, `'당뇨'`) 다음 시도의 프롬프트로 돌아가 모델이 그 문장을 뺀다. 낱말은 모델 출력에서 온 것이라 한 줄·40자로 접어서만 넣는다. 수동 `topic`(override)에도 러너가 (a)를 적용한다: 걸리면 Gemini·Blogger를 부르기 전에 종료 2(`TOPIC_BLOCKED`, 이력·초안 없음, 걸린 낱말은 로그·요약에)로 멈춘다 — 운영자가 직접 넣은 값이라 조용한 초록이 아니라 빨강으로 알린다(`INVALID_PUBLISH`와 같은 분류). 주제가 통과한 뒤 모델이 흐르는 경우는 (b)·(c)가 두 번째 방어선이다(시험이 고정).

비교하기 전에 글을 고른다(`gates._normalized`, 화면에 나가는 글은 바뀌지 않는다): ① NFKC(전각 영문·풀어 쓴 한글 자모), ② 보이지 않는 서식 문자(너비 0 공백·소프트 하이픈 등) 제거, ③ 굽은 따옴표(U+2019 등)와 특수 하이픈을 곧게. 모델이 영어 글에 굽은 따옴표를 자주 써서 ③이 없으면 `isn't a substitute for medical advice` 같은 안전한 면책이 탈락하고 `you won't need medication` 같은 단정이 통과한다. 키릴·그리스 문자로 바꿔치기한 낱말은 다루지 않는다 — 이 가드레일은 모델이 흐르는 것을 막는 것이지 일부러 피해 가는 입력을 막는 것이 아니다. 정규식은 모두 길이가 한정돼(`{0,3}` 같은 상한) 7,000자짜리 반복 입력에서도 가장 느린 경우가 약 0.1초다(시험이 2초 안에 끝나는지 본다).

**제목·라벨은 엄격하게, 본문은 '단정·조언 문맥'에 가깝게** 건다. 이유는 셋이다.

1. **본문에는 안전한 문장에도 위험 낱말이 들어간다.** "진단이나 치료를 대신하지 않습니다", "does not replace professional medical advice", "의사와 상담하세요", "if you are pregnant, check with your doctor" 같은 문장이다. 검사는 `append_disclosure`가 면책을 붙이기 전이라 프로필의 면책 문구 자체는 걸리지 않지만, 모델이 비슷한 문장을 본문에 쓸 수 있고 그것을 탈락시키면 안 된다. 그래서 전문가 상담 안내와 '의학 조언이 아님' 구절은 **절** 단위로 건너뛴다(`body_safe_patterns`, 아래 '절 단위 면제'). 효능 단정(`banned_patterns`)은 이 예외를 받지 않는다 — "의사와 상담하세요, 하지만 부작용은 전혀 없어요"는 걸린다.
2. **영어에는 일상어와 겹치는 낱말이 많다.** `treat yourself`·`a small treat`·`a dose of fresh air`·`time heals`·`home remedy` 같은 표현이다. 그래서 영어 본문 목록은 주제 목록에서 bare `treat`·`heal`·`remedy`·`immune`·`pharmacy`와 사람을 가리키는 `therapist`(의사·약사처럼 상담 안내에 흔히 나오고 그 자체가 위험 낱말은 아니다)를 빼고, `treat`는 증상·질병·통증 같은 **의료 대상**이 뒤따를 때만 막으며, `dose`는 `a dose of fresh air/sunshine/nature` 같은 관용구를 통과시킨다. 제목·라벨·주제는 짧고 우리가 정하는 자리라 `Treat Yourself` 같은 제목도 막는다.
3. **오탐의 비용이 크다.** 재시도 3회가 모두 탈락하면 그날 발행을 잃는다(`GATE_REJECTED`). 건강 느낌이 나지만 위험하지 않은 일상 문장 52개(수면·자세·카페인·수분·번아웃·두통 같은 낱말 포함)와 안전한 표본 문장 28개는 영어 본문 검사에서 탈락 0건이어야 한다고 시험이 고정한다(`tests/test_guardrails.py`).

한국어는 본문 목록과 주제 목록이 **같은 어휘**다(시험이 같음을 고정). 한국어 목록은 `치료`·`진단`·`처방`처럼 의료 어휘만 담고 있어 본문에서도 일상 문장과 겹치지 않기 때문이다(실제로 생성된 본문 5편은 탈락하지 않는다). 처음에는 28개뿐이라 영어가 막는 질환·약·감량 낱말이 한국어에는 하나도 없었고(D-64 ⑥ b), 한국어 프로필을 쓰는 블로그가 생기기 전에 56개로 늘렸다. 영어만 본문 목록이 주제 목록의 부분집합이다(`immunity`는 본문에도, 형용사 `immune`은 본문에서 뺀다).

본문 예외(`body_safe_patterns`)는 둘이다. ① 상담 안내: 상담·문의·확인 동사와 의사·약사·전문가·의료진·병원 같은 전문가 낱말이 같은 절에 있는 것(영어는 `consult`·`talk to`·`check with`·`ask`·`see` … `doctor`·`pharmacist`·`healthcare professional` …). ② 면책: "진단·치료·의학적 조언을 대신하지 않는다 / is not a substitute for … medical advice, diagnosis or treatment / is for informational purposes only".

### 절 단위 면제 (D-64 ⑥ a)

예외는 **문장**이 아니라 **절** 단위다. 문장 전체를 면제하면 "Magnesium supplements may help you sleep, but talk to your doctor first."처럼 위험한 권유 뒤에 상담 구절을 붙인 문장이 통째로 통과한다(독립 검증 2026-10-26). 그래서 ① 본문을 `.`·`!`·`?`·줄바꿈(`<li>` 같은 목록 항목은 마침표 없이 끝나므로 줄바꿈이 문장 경계다)으로 문장으로 나눈 뒤, ② 각 문장을 **절 경계**에서 더 쪼갠다.

| 경계 | 어디에 있나 | 예 |
|------|-------------|----|
| `;` `:` `—` `--`, 양쪽에 공백이 있는 하이픈(엔 대시는 비교 전에 하이픈으로 바뀐다) | 코드(`gates._CLAUSE_PUNCTUATION`, 모든 언어 공통) | `…help you sleep; check with your doctor` |
| 영어 접속어 | 프로필 `body_clause_split_patterns` | `, but`·` but `·`, though`·` although `·`, so`·`, yet`·`, while`·`, then`·`, however,`·`, and ask…`(`and` 뒤에 상담·권유 동사나 대명사가 올 때)·` and ask…`·괄호 안에서 시작하는 상담 구절 `(ask your doctor)` |
| 영어 접속어 + 상담 구절(**연결어 앞의 쉼표도 바로 뒤의 쉼표도 있어도 없어도 된다**) | 프로필 `body_clause_split_patterns` | `so ask your doctor`·`so, ask…`·`or ask…`·`because/since/as…`·`unless you ask…`·`otherwise/therefore/thus/hence/plus…`·`however/accordingly/consequently/for this reason/nevertheless/nonetheless/that said…`·`which is why you should talk to…`·`meaning you can ask…`·`and make sure to ask…` — 접속어 바로 뒤에(또는 도입구 뒤에) 상담 동사 `talk to`·`speak with`·`check with`·`consult`·`ask`·`refer to`(`asking`·`talking to` 같은 동명사도)와 전문가 낱말이 올 때만 가른다. 도입구는 `you should`·`you might want to`·`you'd better`·`you really should`·`make sure to`·`remember to`·`it is wise to`·`it would be wise to`·`it makes sense to`·`I would suggest`·`we recommend`·`please do`·`kindly`·`don't forget to`·`do not hesitate to`·`feel free to`·`take a moment to`와 3인칭 주어 `people should`·`they should`·`everyone should`…이고 두 겹까지(`you should make sure to`) 이어진다. 상담 부사 `please`·`also`·`always`·`just`·`first`·`definitely`·`probably`·`really`·`certainly`·`simply`는 몇 개든 끼고 뒤에 쉼표가 붙어도 된다. `see`·`call`·`visit`·`contact`·`seek`(동명사 포함)은 인과·순서 접속어(`so`·`then`·`because`·`unless`…)와 쓰일 때만 가른다. 상담 동사와 전문가 낱말 사이는 최대 4단어다 |
| 한국어 연결 어미 | 프로필 `body_clause_split_patterns` | `~지만`·`~하되`/`~드시되`·`~는데`·`~으나`·`~면서`·`~으며`·`~니까`, `, 그러나/하지만/다만…`(바로 뒤의 쉼표도), `~고`·`~고,` 뒤에 상담 구절이 이어질 때, 괄호 안의 상담 구절(`(먼저 의사와 …)`). 상담 구절의 첫머리는 `의사`·`약사`·`전문가`·`전문의`·`의료진`·`병원`·`상담`·`문의`·`주치의`·`한의원`·`영양사`이고 앞에 `가까운`·`담당`·`전문`·`주변`·`동네`·`의료`·`건강`·`치과`·`한`(가까운 병원·담당 의사·의료 전문가·한의사)이나 부사 `꼭`·`반드시`·`먼저`·`항상`·`우선`·`일단`·`미리`·`한번`이 셋까지 붙어도 된다 — 안전 패턴(`body_safe_patterns`)이 인식하는 상담 낱말 가운데 흔한 것을 같이 넣었지만 두 목록이 완전히 같지는 않다(어긋나면 `그래서 주치의와 상담하세요`처럼 안전 패턴만 알아서 면제가 남는다. 남은 어긋남: 안전 패턴 [1]은 `진료·진찰·방문·도움·조언`+10자 안의 `의사·약사·전문가·전문의·의료진·병원` 같은 '행위 먼저' 표현도 면제로 인식하지만 경계 앞내다보기는 `상담·문의`만 받고, 상담 낱말 앞 수식어가 닫힌 목록이라 `내과`·`산부인과`·`정신건강의학과`·`믿을 만한`·`해당 분야`·`가족 주치의` 같은 말이 붙으면 면제만 남는다(독립 검증 V-1 — 한글 Blogger 를 켜기 전에 목록을 한 번 더 점검)) |
| 한국어 접속 부사·`서` 어미 | 프로필 `body_clause_split_patterns` | `, 그러므로/그러니/그러니까/그렇기 때문에/이 때문에/그런 이유로`(바로 뒤의 쉼표도), `~서`(`돼서`·`그래서`·`따라서`·`고 나서`·바로 뒤의 쉼표도) 뒤에 상담 구절이 이어질 때. 장소·출처의 `에서`(`병원에서 의사와 …`)·`에게서`·`한테서`와, 후치사·부사처럼 쓰인 `~서`(`에 대해서`·`에 관해서`·`을 위해서`·`을 통해서`·`로 인해서`·`에 비해서`·`에 의해서`·`과 관련해서`·`로서`·`에 따라서`·`에 앞서`·`여기서`·`어디서`)는 가르지 않는다 — 접속 어미가 아니라서 `보충제에 대해서 의사와 상담하세요.` 같은 정상 안내를 막지 않는다(`준비해서`·`소통해서`·`동의해서`는 접속 어미라 그대로 가른다) |

③ 절마다 `body_safe_patterns`에 맞으면 위험 낱말을 건너뛴다. ④ 다만 `body_safe_veto_patterns`(용량: `400 mg`·`5000 IU`·`400mg`·`밀리그램`에 더해 `0.4 g`·`10,000 units`·`2 capsules`·`a 400-mg tablet`·`four hundred milligrams`·`400mgs`·`100 ug`·`2 softgels`·`3 gummies`, 한국어 `2알`·`반 알`·`두 캡슐`)에도 맞는 절은 **건너뛰지 않는다** — 용량을 적은 글은 상담 구절이 있어도 막는다("Ask your doctor whether 400 mg of magnesium is right for you."). 면제 취소는 면제를 거두는 것뿐이라 그 절에 막는 낱말(`supplements`·`melatonin` 등)이 있을 때 막힌다. 용량 낱말 자체를 막는 목록(`banned_*`의 `mg`·`IU` 패턴)은 넓히지 않았다 — `Take 400 milligrams of magnesium before bed.`는 상담 구절도 막는 낱말도 없어 통과한다(D-64 ⑦ N-3). 프롬프트도 용량을 쓰지 말라고 한다. 단위 `g`는 영어·한국어 모두 대소문자를 구분한다(`5 g`은 용량, `a 5G phone`·`5G 요금제`는 아니다). `6 glasses of water`·`B12 tablets`·`a phone tablet stand`·`two gramophone records`·`2정거장`·`5gb`도 읽지 않는다 — 시험 `test_everyday_counting_words_are_not_doses`가 문장마다 금지 낱말과 상담 구절을 같이 넣어 면제 취소가 잘못 읽으면 막히게 고정한다(D-64 ⑧ N2-5). 일상어로도 쓰이는 단위(`ml`·`teaspoon`·`tablespoon`·`tabs`(브라우저 탭)·`a gram`(`a gram of curiosity`)·`스푼`·`2개`)는 읽지 않는다 — 읽으면 `Ask your doctor about melatonin and 250 ml of water.` 같은 문장이 오탐이 된다. 숫자+단위로 읽히는 일상 표현(`2 tablets of rest`·`10 grams of sugar`·`3 units of study`·`한 정도`)은 상담 구절·금지 낱말과 한 절에 있을 때만 막히므로 드물다.

계속 통과하는 것: 질환·임신·약을 이름 붙인 정상 상담 안내는 한 절이라 그대로 면제된다(운영자 결정 3번) — "If you are pregnant, talk to your doctor before changing your routine.", "Check with your doctor before trying a new supplement routine.", "임신 중이거나 약을 복용 중이라면 의사와 상담한 뒤 시작하세요." 쉼표로 나열한 병명("asthma, diabetes, and high blood pressure")은 `, and` 뒤가 새 절이 아니라서 가르지 않고, 낱말 안의 하이픈(`well-known`)·범위(`2-3`)도 가르지 않는다. 효능 단정(`banned_patterns`)은 절 단위 면제와 무관하게 늘 막는다.

**알려진 과잉 차단(트레이드오프)**: 병명·임신을 이름 붙인 절과 상담 구절이 접속어·문장부호로 나뉜 정상 안내도 이제 막는다 — "Pregnancy can change your needs, so talk to your doctor.", "If you have a health condition—such as diabetes or high blood pressure—talk to your doctor …", "Who should check with a doctor first: pregnant women, people with diabetes …", "Some people take supplements; if you do, talk to your doctor first.", "임신 중에는 몸 상태가 달라질 수 있으니 의사와 상담하세요." 이 문장들은 독립 검증이 막으라고 한 "Vitamin D supplements may lower your blood pressure, so ask your doctor."와 모양이 같아(위험 낱말이 든 절 + 접속어·문장부호 + 상담 절) 구조로는 가를 수 없다. 모델이 쓸 법한 상담 안내 40문장(영어 30·한국어 10)으로 재 보면 막히는 문장이 옛 main 2개에서 7개로 늘었다. 같은 뜻을 한 절로 쓰면 통과하고(`, such as …,`·`Because pregnancy can change your needs, talk to your doctor.`·`~ 수 있어 의사와 상담하세요`), 영어 프롬프트가 질환·임신을 쓰지 말라고 하므로 실제 빈도는 낮을 것이다. 막히면 걸린 낱말이 재시도 사유로 돌아가 모델이 그 문장을 뺀다. 풀려면 `gates._CLAUSE_PUNCTUATION`(`—`·`:`·`;`)과 프로필 `body_clause_split_patterns`(`, so`·`으니`)에서 경계를 빼면 되지만, 그러면 검증자의 문장도 통과하므로 운영자·총괄의 결정이다. 시험 `STRICT_TRADE_OFF_*`가 지금의 결정을 고정한다. 쉼표 없는 접속어와 도입구까지 닫은 2차 보강(D-64 ⑦ N-1)도 같은 값을 치른다 — 검증자의 정상 안내 표본(영어 42·한국어 15)에서는 새로 막히는 문장이 0개지만, 내가 쓴 정상 안내 68문장(영어 47·한국어 21)에서는 14문장이 새로 막힌다("Medication can interact with food, which is why you should talk to your doctor."·"Do not start any new supplement unless you check with your doctor first."·"People with asthma can then ask their doctor about stretching."·"Pregnant women should rest and then check with their doctor …"·"Pregnant women should rest, otherwise check with their doctor."·"임신 중이라서 의사와 상담이 필요해요."·"혈압이 걱정돼서 병원을 방문하세요." 등 — 측정에 쓴 표본은 저장소 밖이고, 대표 문장만 `STRICT_TRADE_OFF_*`로 고정한다). 3차 보강(D-64 ⑧)은 연결어 앞뒤의 쉼표·도입구·3인칭 주어·동명사·새 연결어와 한국어 상담 낱말·`그러므로` 계열 접속 부사까지 더 닫았지만 같은 표본들에서 **새 오탐이 0개**다 — 검증자 caveat 75문장 중 막히는 문장은 2차 보강 뒤와 같은 38개(main은 8개), 검증자 정상 안내 영어 42·한국어 15는 그대로 8·1, 내 정상 안내 68문장도 그대로 12·5(main은 3·0), 8만 문장 생성 말뭉치의 일상 문장(`benign`)은 영어·한국어 모두 새로 막힌 것이 없다. 이번에 새로 쓴 자연스러운 정상 안내(영어 26·한국어 20 — 저장소 밖)에서는 영어 4문장(`Diabetes affects people differently, therefore, you should ask your doctor.`·`Some medications cause drowsiness, so, please check with your pharmacist before driving.`·`Heart conditions vary a lot, accordingly check with your doctor before you begin.`·`People with diabetes differ, hence they should talk to their doctor.`)과 한국어 6문장(`임신 중이라서 주치의와 상담이 필요해요.`·`임신 중에는 몸 상태가 달라질 수 있어요, 그렇기 때문에 의사와 상담하세요.` 등)이 같은 모양이라 새로 막히고, 한국어 8문장(`보충제에 대해서 의사와 상담하세요.`·`혈압에 따라서 …`·`보충제를 시작하기에 앞서 …` 같은 후치사 `~서`)은 풀렸다. **영어 `or`·`unless`·`, then` 계열은 풀지 않고 결정을 고정했다(2차 델타 검증 N2-2)**: 정상 안내 caveat 75문장 중 막히는 문장이 main 8개에서 2차 보강 뒤 38개로 늘었고 `or`가 가장 크다(검증자 계산으로 `or`를 빼면 새 오탐이 30개에서 17개). `Stay home if you have symptoms, or talk to a healthcare professional.`·`If you have diabetes, keep the routine gentle or check with your doctor.`·`Avoid this exercise if you have asthma unless you check with your doctor.`·`If you are pregnant, then check with your doctor first.` 같은 문장이 막히고 시험 `STRICT_TRADE_OFF_EN`이 그 값을 고정한다. 풀지 말지는 첫 실제 영어 초안의 `BODY_TOPIC` 빈도를 보고 정한다(`WORKLOG.md`에 같은 줄).

**한계**: 쉼표만으로 이은 상담 구절은 여전히 면제된다 — 쉼표 이음("Magnesium supplements help you sleep, talk to your doctor first.")·`, please`·`, just`·`, also`·`, of course,`·`, if you want,`·`, remember to`·`, be sure to`·`, make sure to`·한국어 `~는 점, 의사와 …`, 그리고 꼬리 구절("…, after checking with your doctor"). 쉼표 뒤 명령형을 경계로 삼으면 정상 안내 "If you are pregnant, talk to your doctor"가 깨져서 일부러 그렇게 두었다(시험 `ConnectorGridTest`가 이 목록을 고정한다). 상담 구절이 앞에 오고 위험한 권유가 쉼표 없는 `and try …`·`, and many people find …`로 뒤따르는 문장도 이번에는 가르지 않았다. `, then` 조건문("If you are pregnant, then check with your doctor first.")과 "stop and consult"처럼 정상 안내가 막히는 과잉 차단은 고치지 않았다 — 위 '알려진 과잉 차단'에서 `or`·`unless`와 함께 결정을 고정했다(D-64 ⑦ N-2, ⑧ N2-2). 3차 보강 뒤에도 영어에서 열려 있는 것: 연결어 뒤에 부사절이 끼면 통과한다(`so if in doubt, ask…`·`so to be safe, ask…`·`so of course, ask…` — 조건절 뒤 쉼표 + 상담 구절과 구별할 수 없다). 상담 구절을 앞세우지 않는 연결어(`so that you can ask…`·`in case you want to ask…`·`still`·`either way`·`regardless`)와 쉼표 뒤 부사구(`, to be safe, ask…`·`, to be sure, ask…`·`, for safety ask…` — 조건절 뒤 쉼표 + 상담 구절과 같은 모양)도 그대로다. 수식어가 붙은 3인칭 주어(`so anyone taking medication should ask…`·`so those with health concerns should…`)는 병렬 주어 "Pregnant women and anyone taking medication should talk to their doctor."를 막아 버려서 넣지 않았다. 상담 동사와 전문가 낱말 사이는 4단어까지만 본다(`ask your very kind local family doctor`는 통과). 도입구는 목록이라 목록에 없는 말(`you are advised to`·`it is best that you`·`I'd say`)은 열려 있다. 약한 동사(`see`·`call`·`visit`·`contact`·`seek`)는 `or`·`while`·`as`와 쓰이면 가르지 않는다('take a break or see a specialist'를 막지 않으려고). 한국어는 `~므로`·`~기 때문에`·`~다 보니`·`~거나`·`~든지`·`또는`·`아니면`·`또한`·`게다가`·`그러면`·`물론`으로 이은 상담 구절이 열려 있다 — `~므로`를 닫으면 검증자의 정상 안내 "임신 중에는 몸 상태가 달라지므로 의사와 상담하세요."가 새로 막히고, `거나`·`또는`을 닫으면 "증상이 계속되면 쉬거나 병원을 방문하세요." 같은 흔한 정상 안내가 막힌다(영어 `or`와 같은 값이라 첫 한국어 초안을 보고 정한다). 용량은 일상어와 겹치는 단위(`ml`·`teaspoon`·`tablespoon`·`tabs`·`a gram`·`스푼`·`2개`)를 읽지 않는다. 한 문단 안에서 줄을 바꿔 쓴 문장은 줄바꿈이 문장 경계라 두 낱말 용어가 줄 끝에서 갈리면(`blood⏎pressure`) 놓친다. 한 문장에 다른 언어의 낱말이 섞이면(영문 글의 `당뇨`) 그 프로필의 목록으로는 걸리지 않는다 — 언어 게이트는 영문 글에서 라틴 문자가 90% 미만일 때(한국어 글은 한글이 50% 미만일 때)만 막으므로 낱말 한두 개는 지나간다.

### 한국어 ↔ 영어 대응표 (`banned_topic_patterns`)

영어는 단어 경계(`\b`)와 굴절형(treat·treats·treated·treating·treatment)을 명시해 `secure`·`manicure`(cure), `cancel`·`Cancun`(cancer), `dosa`(dose), `insulation`(insulin), `pillow`(pill), `retreat`(treat), `meditation`(medication), `surge`(surgery), `patience`(patients)가 걸리지 않는다.

| 위험 영역 | 한국어 낱말 | 영어 패턴(굴절형 포함) |
|-----------|-------------|-------------------------|
| 치료·완치 | 치료, 완치, 요법 | `treat`·`treats`·`treated`·`treating`·`treatment(s)`, `cure`(s/d)·`curing`·`curable`, `heal`(s/ed/ing/er), `remedy`·`remedies`, `therapy`·`therapies`·`therapist`·`therapeutic` |
| 진단·처방 | 진단, 처방 | `diagnose`(s/d)·`diagnosing`·`diagnosis`·`diagnostic`, `prescribe`(s/d)·`prescribing`·`prescription(s)` |
| 의료·시술 | 의료, 수술, 시술, 주사, 한약, 임상, 접종, 스테로이드, 침술·카이로프랙틱 | `medical(ly)`, `medicine`·`medicinal`, `medication(s)`·`medicate`, `meds`, `clinical(ly)`, `surgery`·`surgical`·`surgeon`, `injection(s)`·`injectable`, `vaccine`·`vaccination`, `steroid(s)`, `acupuncture`, `chiropractic`(한약은 medicine·remedy·supplement가 포괄) |
| 질병 일반 | 질환, 질병, 증상, 환자, 감염 | `disease(s)`, `illness(es)`, `disorder(s)`, `syndrome(s)`, `symptom(s)`, `patients`, `infection(s)`, `inflammation`·`inflammatory`, `chronic pain/fatigue/illness/disease/condition`(하이픈 포함) |
| 암 | 암(독립된 낱말), 종양, 항암, 백혈병, 림프종 | `cancer`(s/ous), `tumor`·`tumour`, `chemo(therapy)`, `oncology`, `leukemia`·`melanoma`·`lymphoma` |
| 당뇨·혈압·심장 | 당뇨, 혈압(고혈압·저혈압 포함), 혈당, 콜레스테롤, 심장병·심근경색·뇌졸중·협심증·부정맥·동맥경화·심혈관 | `diabetes`·`diabetic`·`prediabetes`, `insulin`, `hypertension`·`hypotension`, `blood pressure/sugar/glucose`(`blood-pressure`·`bloodpressure` 포함), `cholesterol`·`triglycerides`, `heart disease/attack/failure/condition`, `cardiac`·`cardiovascular`, `stroke` |
| 정신 건강 | 우울증, 공황, 자살, 자해, 치매, 자폐·조현병·알츠하이머·파킨슨·양극성·강박증·불안장애·섭식장애·거식증·폭식증 | `depression`·`depressive`·`depressed`·`antidepressant`, `anxiety disorder/attack`, `panic attack/disorder`, `bipolar`·`schizophrenia`·`psychosis`·`PTSD`·`OCD`·`ADHD`·`autism`·`dementia`·`alzheimer`·`parkinson`, `mental illness/disorder/health condition…`, `eating disorder`·`anorexia`·`bulimia`, `suicide`·`suicidal`, `self-harm`·`self harm`·`self-injury`, `overdose` |
| 그 밖의 질환명 | 불면, 편두통, 천식, 관절염, 갑상선, 빈혈, 비만, 골다공증, 지방간, 간염, 뇌전증, 갱년기·폐경 | `insomnia`, `sleep apnea`, `arthritis`, `asthma`, `COPD`, `epilepsy`·`seizure`, `migraine`, `fibromyalgia`, `thyroid`, `anemia`, `obese`·`obesity`, `osteoporosis`, `hepatitis`, `cirrhosis`, `fatty liver`, `kidney disease/stones/failure`, `covid`·`coronavirus`, `HIV`, `menopause`(`perimenopause`·`postmenopausal`) |
| 약물·복용 | 약물, 복용, 항생제·진통제·수면제·해열제·항우울제·소염제·알약, 용량(`400mg`·`밀리그램`) | `drug(s)`, `pill(s)`, `pharmacy`·`pharmacist`, `antibiotic`·`painkiller`·`pain reliever`·`ibuprofen`·`acetaminophen`·`paracetamol`·`aspirin`·`NSAID`·`opioid`·`sedative`·`antihistamine`·`benzodiazepine`, `over-the-counter`·`OTC`, `dose`·`doses`·`dosed`·`dosing`·`dosage`, `5 mg`·`200mcg`·`IU` 같은 용량, `sleep(ing) aid/tablet/capsule` |
| 보충제·영양제 | 보충제, 영양제, 건강기능식품, 멜라토닌, 종합·멀티 비타민·비타민제 | `supplement`(s/ed/ing)·`supplementation`, `multivitamin`, `vitamin pills/tablets/capsules/gummies`, `melatonin`·`ashwagandha`·`CBD`·`cannabis`·`marijuana`·`THC`·`creatine` |
| 임신·영유아 | 임신, 태아, 영유아, 신생아, 임산부, 산모, 출산 | `pregnant`·`pregnancy`, `prenatal`·`postnatal`·`postpartum`·`antenatal`, `expectant`·`expecting mothers`, `miscarriage`·`fertility`, `breastfeeding`·`lactation`·`nursing mothers`, `fetus`·`fetal`·`foetus`, `infant(s)`·`newborn(s)`·`babies`·`toddler(s)`·`neonatal`·`pediatric` |
| 체중 감량·다이어트·디톡스 | 체중 감량, 다이어트, 체지방·지방 연소·지방 분해, 슬리밍, 디톡스, 단식, 키토·저탄고지 | `weight loss`·`weight-loss`, `lose weight/fat`·`lose 10 pounds`, `fat burn(ing/er)`·`burn belly fat`, `slimming`·`slim down`, `crash diet`·`fad diet`·`keto`·`fasting`·`starve`·`calorie deficit`, `detox`(es/ification)·`cleanse`, `dieting`·`diet plan/program/pills/menu/…`(단독 `diet`·`balanced diet`는 일상어라 막지 않는다), `shed pounds`·`drop a few kilos`, `body/belly/visceral fat` |
| 간 건강 | 간 건강·간 기능·간 수치·간 질환·간 해독(`간`은 한 글자라 앞에 한글이 없을 때만) | `liver health/function/support/damage/care/cleanse/detox/enzymes/disease`, `healthy liver`, `support your liver` |
| 면역 | 면역(면역력 포함) | `immune`·`immunity` — 본문 목록에는 형용사 `immune`(`immune to criticism`)을 빼고 `immunity`만 둔다 |

영어 본문 목록은 이 표에서 `heal`·`remedy`·`immune`(형용사)·`pharmacy`·`therapist`를 빼고, `treat`는 의료 대상이 뒤따를 때만 막는다. 두 언어 모두 일상 표현과 겹치는 `pain`·`vitamin`(단독)·`allergy`·`kids`(한국어 `통증`·`비타민`·`알레르기`·`아이`)는 넣지 않았다 — 어디까지 막을지는 열린 운영자 결정이다(D-64 ④. 더 엄격하게 하려면 이 표에 한 줄씩 추가하고 `tests/test_guardrails.py`의 표본을 같이 바꾼다).

**한국어에서 일부러 뺀 영어 대응 낱말**(일상어와 겹쳐 정상 글이 탈락한다): `백신`(컴퓨터 백신 — `접종`만 넣었다), `해독`(암호 해독), `코로나`(시기를 가리키는 일상어), `수유`(수유동·수유역), `감량`(쓰레기 감량), `용량`(배터리 용량), `뜸`(밥 뜸 들이다), `간질`(간질간질), `약`(약 10분), `살 빼`(동사 활용과 겹침), `불안`·`우울감`·`두통`·`변비`·`탈모`·`관절`(영어도 `anxiety`(단독)·`headache`·`constipation`·`hair loss`·`joints`는 막지 않는다). 영어에만 있는 것: `cleanse`·`starve`·`calorie deficit`·`ashwagandha`·`CBD`·`cannabis`·`marijuana`·`THC`·`creatine`·`pharmacy`·`fertility`·`miscarriage`.

### 한국어 프로필에 적용한 근거

권장대로 한국어 프로필(`blogger_practical_ko`)에도 같은 가드레일을 적용했다. 근거: ① 위험(YMYL)·광고 계정·파이프라인이 같아 언어에 따라 안전선이 달라질 이유가 없다. ② 지금 이 프로필(`blogger_practical_ko`)을 쓰는 블로그가 없어(macat0722는 영문으로 전환했고, 한글 Blogger kcyoon 은 별도 프로필 `blogger_ai_tools_ko` 를 쓴다 — 아래) 운영 중인 흐름이 바뀌지 않는다. ③ 적용 전후로 확인했다 — 기존 시험이 `make_root`(임시 저장소가 영문 항목을 한국어 프로필·프롬프트로 바꿔 쓰게 함) 외에는 수정 없이 통과하고, 한국어 시드 32개·스텁 글·실제로 생성돼 이력에 남은 제목 5개·본문 5편이 새 제목·본문 검사를 통과한다. ④ 이 확인에서 **오탐 1건**을 찾아 고쳤다: 실제 생성 글의 "딱 3분만 투자해서"가 `자해`(자기 해침)와 겹쳐 본문 검사에 걸렸다. 한국어 낱말은 어절 중간 일치가 흔해서, 주제 목록의 `자해`를 `(?<![가-힣])자해`(앞에 한글이 없을 때만)로, `주사`를 `주사(?!위)`(주사위 제외)로 고쳤다. 이 목록이 제목·라벨에도 걸리게 됐기 때문에(제목 "3분 투자해서 …"는 흔하다) 필요한 수정이고, 걸리지 않게 된 것은 `비자해`처럼 실제로 쓰지 않는 합성어뿐이다. ⑤ 목록을 28개에서 56개로 늘린 보강(D-64 ⑥ b·f)도 같은 방식으로 확인했다 — 실제로 생성된 글 5편의 제목·라벨·주제와 본문 문장 40개, 한국어 일상 문장 20개, 독립 검증이 쓴 한국어 32문장에서 오탐이 0건이다(`간 건강`은 `시간 건강`과, `단식`은 `간단식`과 겹치지 않게 앞에 한글이 없을 때만 막는다).

### 한글 AI·도구 프로필(`blogger_ai_tools_ko`, 작업 D — 한글 Blogger kcyoon, 모드 off)

일상 속 AI·디지털 도구 활용법(약 70%)과 집·살림 정리 습관(약 30%)을 다루는 한국어 Blogger용이다. `blogger_practical_ko`와 **같은 필드 구조**(금지 패턴·절 단위 상담 구절 면제·누출 검사·길이·구조·유사도·쿨다운)를 쓰고, 이 블로그에 맞게 다음이 다르다.

| 항목 | `blogger_practical_ko` | `blogger_ai_tools_ko` | 이유 |
|------|------------------------|------------------------|------|
| 주제 범위 | 생활 습관 | AI·디지털 도구 약 70% + 집·살림 약 30%(`_seed_mix`는 문서용) | 운영자 결정(D5) |
| 시드 | 32개 | **36개**(AI·디지털 26 + 집·살림 10, 35~55자) | 모두 금지 주제 목록을 통과해야 한다(레지스트리 검증) |
| `topic_expand_prompt` | 없음(코드의 기본 지시문) | 있음 — 시드를 다 쓴 뒤 70:30으로 새 주제를 청한다 | 주제 비율을 지키려고 |
| `banned_patterns`(제목+본문, 예외 없음) | 10개 | **30개** | 지어낸 개인 경험("직접 써 봤더니")·지어낸 수치·벤치마크("30% 빨라집니다")·지어낸 인용·후기·연구·인터뷰, 단정·보장("100% 안전", "해킹 걱정이 전혀 없어요"), 요금제·한도 주장("월 9,900원", "하루 50회"), 광고·제휴 어조("강력 추천", "할인 코드", "협찬"), 링크·주소·이메일 |
| `banned_topic_patterns` · `body_banned_patterns` | 56개 | **63개** | 건강 주장에 **의료·법률·세금·대출·투자·보험 어휘**(소송·변호사·합의금·연말정산·대출·주식·코인·보험료 …)를 더했다. AI·디지털 글에서 흔한 낱말(`비밀번호`·`감염`(악성코드)·`예방`·`약`(약 10분)·`todo`·`전세계`·`고소한`·`주식회사`·`담보`)이 정상 글을 막지 않도록 어절 경계·부정 전방 탐색으로 좁혔다(`비밀(?!번호)`·`전세(?!계)`·`고소(?!한)`·`(?<![가-힣])암(?![가-힣])`·`약` 앞 글자 제한·`감염`은 의료 맥락만) |
| `leak_patterns` | 12개 | 16개 | AI 자기 언급("저는 AI 언어 모델이라서")·"죄송합니다 …"·"다음은 요청하신 …"·`[링크 삽입]`·`TODO:` 같은 응답 잔재. 이 블로그가 AI 도구를 다뤄 `AI 어시스턴트`·`언어 모델`이라는 **낱말 자체는 막지 않는다** |
| `allow_links` | `false` | `false` | 링크·주소·이메일은 지우거나 막는다(요금·한도·화면 이름이 바뀌어도 낡은 링크가 남지 않게) |
| `disclosure_html` | 생활 정보 | "AI의 도움을 받아 작성·편집한 일반 정보입니다. 도구의 기능·화면·요금은 자주 바뀌므로 … 공식 화면에서 확인하세요. 건강·법률·세금·금융·투자에 대한 전문적인 조언이 아니며 …" | 게시 직전에 항상 붙는다 |
| `min_hangul_ratio` | 0.5 | 0.6 | 영어로 쓴 글을 더 확실히 거르는 쪽으로 올렸다(영문 약어가 일부 섞인 한국어 글은 통과) |
| `prompt_extra` | 4줄 | 8줄 | 지어낸 경험·수치·인용 금지, 기능·요금·한도 단정 금지, 공식 화면 확인 안내 |

**프롬프트**(`.github/editorial/BLOGGER_PROMPT_KO_AI.md`)는 `[대상: Blogger 한글]` 머리와 12개 규칙의 `text` 블록(독자가 오늘 따라 할 수 있는 순서 중심, 직접 써 본 척 금지, 바뀔 수 있는 사실(요금·한도·화면 이름)을 단정하지 않기, 광고·제휴 어조 금지, 의료·법률·세금·투자 조언 금지, AI 답은 직접 확인하라는 안내, 링크·주소·이메일 금지, `제목:/라벨:/내용:` 출력)과 §6 '켜기 전에 운영자가 읽을 것'을 담는다. 켜기 전에 운영자가 시드 36개·금지 범위·AI 고지 문구·말투를 읽고 승인한다(T3).

**시험**: `tests/test_profile_ko_ai.py`(53개)가 구조·시드(35~55자, 36개 모두 게이트 통과)·게이트·상담 구절 면제 구조·**프롬프트 파일**(규칙 12개가 각각 말해야 하는 것·글 길이·제목 길이·소제목·라벨 수가 게이트 범위 안인지·출력 머리표를 러너의 파서가 읽는지, 독립 검증 N7)·**규칙 표**(규칙 71개 각각에 '걸려야 하는 표본'과 '걸리면 안 되는 표본')를 고정한다. 정상 한국어 문장 51개·정상 제목 16개는 0건 걸리고, 위반 본문 53개·위반 제목 16개는 모두 막힌다. 한계는 다른 프로필과 같다 — 걸리지 않는 우회 표현은 열려 있고(모델이 만든 글은 운영자가 초안함에서 읽고 게시한다), 의료·법률·금융 낱말이 아닌 **사실 오류**(틀린 설정 방법)는 게이트가 알 수 없다.

**영문 글의 번역·복제는 코드가 못 잡는다**(독립 검증 N2): 다른 블로그와의 제목 교차 중복(`DUP_OTHER`, 유사도 0.6 이상 탈락)은 글자 유사도라 **같은 언어 안에서만** 걸린다 — 한글 글은 한글 이력·Chance 한글 글과 겹치는 제목만 막고, 영문 글을 번역한 한글 제목은 유사도가 대체로 0.2 이하(독립 검증 측정 0.12~0.18)라 통과한다. 시드는 영문 시드의 번역이 아님을 시험이 고정하지만(`tests/test_profile_ko_ai.py`), 모델이 영문 글을 옮겨 쓰는지는 켜기 전과 첫 초안들에서 운영자가 눈으로 확인한다(`BLOGGER_PROMPT_KO_AI.md` §6의 7번, `ACTIONS_GUIDE.md` 3-12 한글 켜기 6번).

### 영어 시드(34개)

한국어 시드 32개 중 30개의 영어판(2개는 뺐다: 야식 충동·간식 기준 — 체중 관리·영양 주장으로 흐르기 쉽다. '잠이 안 올 때'는 문제 틀을 빼고 '자기 전 진정 루틴'으로, '운동·소화·비 오는 날 기분·피곤할 때 에너지'는 의학적 해석을 부르는 낱말을 풀어 다시 썼다)과 새 시드 4개(책상 정리·채소 더하기·주간 플래너·습관 쌓기). 생활 습관·수면 위생·책상 자세·산책·정리·식사 계획·스트레칭처럼 **의학적 주장이 필요 없는** 주제만이다. 영어는 같은 뜻이 더 길어서 35~55자(주제 길이 한도는 8~60자)다. 모든 시드는 레지스트리 검증과 시험에서 금지 주제 목록을 통과해야 하고, 시드마다 영어 스텁 글이 게이트 전체를 통과하는지, Chance 영·한 제목·한국어 이력과의 제목 유사도가 교차 중복 한도(0.6) 아래인지(측정한 최댓값 0.50)도 시험이 본다.

### 새 언어·새 블로그 프로필 체크리스트

1. 가장 가까운 프로필 JSON을 복사해 `name`·`language`·비율 필드·길이·목록·시드·`disclosure_html`·`prompt_extra`·`topic_expand_prompt`와, 본문 가드레일을 쓰면 `body_clause_split_patterns`(그 언어의 접속어·연결 어미)·`body_safe_veto_patterns`(용량 표기)를 그 언어로 만든다. 목록은 이 절의 대응표를 기준으로 낱말·굴절형을 정하고, 정규식에는 단어 경계를 둔다.
2. 새 `language` 값이면 `pipeline/gates.py`의 `SUPPORTED_LANGUAGES`와 `check_post`의 글 언어 검사에 그 언어를 더한다(현재 `ko`·`en`).
3. 프롬프트 파일(`.github/editorial/…`)을 만든다: `text` 코드 블록 안에 `{topic}`(영어는 줄 맨 앞 `Topic: {topic}`)과 출력 형식. 머리표는 `제목:/라벨:/내용:` 또는 `Title:/Labels:/Content:`(`gates._MARKER_SETS` — 새 머리표는 여기에 더한다).
4. `pipeline/stubs.py`가 그 언어의 글을 내도록 한다. 안 그러면 연습 실행(`--dry-run`·`연습 실행`)이 한국어 가짜 글로 언어 검사에서 탈락한다.
5. 시험: `tests/test_guardrails.py`의 막힘·통과 표본(부분 문자열 오탐 포함)을 새 언어로, 시드·스텁 통과, 임시 저장소(`make_root`)에서 가짜 LLM으로 한 편(통과·탈락·재작성).
6. `python -m pipeline.registry` → `python scripts/validate_repo.py` → `python -m unittest discover -s tests`. 레지스트리에는 `mode`를 직접(`off`로) 적는다.

**알려진 한계**: `pipeline/run.py`의 `build_prompt`가 `[추가 규칙]`·`[이전 시도에서 고쳐야 할 점]` 머리글을 한국어로 붙이고 탈락 사유도 한국어라, 영문 블로그의 프롬프트는 영어 본문에 한국어 머리글이 섞인다(모델은 이해하지만 영어로 통일하려면 `run.py`를 고쳐야 한다 — 범위 밖으로 남겼다, D-64 ③). 영어 글의 제목·라벨 중복 검사(`DUP_SAME`·`DUP_OTHER`)는 Chance 영어 제목과 한국어 이력에 그대로 쓰며(문자열 비교라 같은 언어 안의 중복만 막는다 — 영·한 번역 제목은 유사도가 대체로 0.2 이하라 못 잡는다), 영어 제목은 같은 틀("5 Simple Ways to …")이 반복돼 같은 블로그 안 유사도(0.72)에 걸릴 수 있다.

## 8. 로드맵과 완료 기준

| Phase | 내용 | 완료 기준 |
|-------|------|-----------|
| **0 (완료)** | 가드레일(검증기·CI·워치독), 레지스트리, Blogger 파이프라인, 문서 체계 | `validate_repo` 오류 0, 테스트 통과, `actionlint` 0건 |
| **1** | Blogger 가동: OAuth 프로덕션 전환 → token·Secrets → 초안 확인 → 자동 게시 | 연속 3회 정상 실행(`posted`), 워치독 이슈 0건 |
| **2** | Chance 안정화: D-01 이슈 수정 흐름 재구축(`pipeline/edits` — **코드 완료, Actions 관측 대기**), D-03 스킵 사유 가시화(분야 폴백·실행 요약, §4-1), 모델 목록 단일화(D-12) | 이슈 → 워크플로 E2E 시나리오 통과(Actions 첫 관측), 스킵 사유가 로그와 실행 요약에 남음(이력 파일에는 남기지 않는다) |
| **3** | 엔진 공용화: `generator.py`의 공통부(LLM·이미지·중복·검증)를 `pipeline/`으로 이관, `jekyll-git` 어댑터, `chanceblog.yml`도 매트릭스 | 골든 테스트(기존 산출물과 동등) + 2주 무사고 |
| **4** | 블로그 N개 온보딩, 공통 주제 풀(주제 하나를 블로그별로 다르게 변형), 일일 요약(비용·탈락률) | 플레이북 A로 신규 블로그 1개를 코드 수정 없이 온보딩 |
| **5 (제안)** | 통합 성과 대시보드: Looker Studio(코드 없음) → 필요하면 비공개 저장소의 수집기와 주간 비공개 리포트. 방문자·인기 글·AdSense 사이트별 수익. 대상은 공식 API가 있는 플랫폼(구글 계열) | [`ANALYTICS_PLAN.md`](./ANALYTICS_PLAN.md) §7의 사용자 결정 대기. 수치는 공개 채널에 올리지 않는다(G-O7) |

## 9. 설계 결정 요약

| 결정 | 이유 | 한계·대안 |
|------|------|-----------|
| JSON 레지스트리 | 표준 라이브러리만으로 읽고, AI·사람이 모두 고치기 쉽다 | 주석 불가 → `_doc` 필드와 이 문서로 보완 |
| Actions 매트릭스 | 블로그를 늘려도 워크플로 수정이 없다 | 병렬 push 경합 → `max-parallel: 1` + 재시도 |
| 이력을 저장소에 저장 | 단순·감사 가능·외부 DB 불필요 | 동시 실행 경합, 크기 증가 → 개수 상한, 블로그별 파일. 규모가 커지면 외부 저장소 검토 |
| 게이트 fail closed | 자동 게시의 최대 위험은 "나쁜 글이 나가는 것" | 탈락률이 높으면 프롬프트·프로필 조정(워치독 REJECT_STREAK) |
| 이슈로 알림 | 사용자가 따로 대시보드를 볼 필요 없이 메일로 온다 | 알림이 많아지면 요약형으로 전환 |
| `workflow_dispatch`로 배포 | `GITHUB_TOKEN` push는 push 이벤트를 만들지 않으므로(예외: dispatch) | PAT·GitHub App 방식은 시크릿이 늘어 채택하지 않음 |
| Chance 승인 흐름은 초안 PR + 이력 항목만 main 에 따로 커밋(§4-4) | 사람이 병합해야 공개(수동 검토 없는 자동 생성 콘텐츠에 광고를 두지 말라는 게시자 정책 안내). 병합이 push 이벤트라 배포가 저절로 실행되고, 슬롯·제목·이미지 중복 검사는 main 의 이력만 읽는 지금 구조 그대로이며, 열린 초안이 여럿이어도 `history.json` 충돌이 없다 | 닫아서 폐기한 초안의 이력도 남아 그 슬롯·주제는 다시 안 쓴다. 이력의 글이 공개된 글이 아닐 수 있다. 봇 PR 에는 검사가 안 돈다. 대안: 이력을 PR 안에 두기(충돌), 별도 원장 파일(이중 장부), 사람이 PR 대신 이슈로 승인(휴대폰 병합 한 번보다 번거로움) |
| 티스토리·네이버는 어댑터 없이 **초안 패키지(GitHub 이슈) + 운영자 복사 발행** | 공식 자동 게시 수단이 없고(티스토리 API 종료, 네이버 약관) 로그인·세션 자동화는 계정 위험과 약관 위험이 크다. 사람이 읽고 경험·판단을 더한 뒤 올리는 단계가 광고 정책의 '수동 검토·큐레이션'과 방향이 같다 | 운영자가 한 편마다 복사해야 한다(7단계 안팎). 이슈가 쌓이면 새 초안을 멈춘다(3건). 모바일 티스토리 앱에는 HTML 모드가 없어 PC 웹이 필요 |
| 수정 요청은 구조화된 이슈 양식 + 문자 그대로 교체 + PR | 비개발자의 자유 문장 요청을 AI가 해석하면 요청 밖을 고치거나 일부만 읽고 추정할 수 있다(D-14). 양식으로 대상·수정 항목을 고정하고, 가능한 곳은 AI 없이 교체하며, 결과는 기계 검사 후 사람이 병합 | 한 요청은 한 파일만. AI 패치(`layout`, 변경 전이 없는 `text_change`)는 범위만 증명하고 내용의 정확성은 사람이 본다 |
