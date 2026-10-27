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
  제어: 레지스트리 mode(off/draft/auto) · PIPELINE_PAUSE(킬 스위치) · 일일 상한 · 쿨다운
  수정 요청: 이슈 양식 ─► pipeline/edits(명세 범위 안에서만) ─► PR ─► 범위 검사([공통] PR 변경 범위 검사) ─► 사람이 병합
```

설계 원칙은 세 가지다. ① **설정과 코드를 분리**한다(블로그 = 레지스트리 항목). ② **게시 전 게이트는 플랫폼과 무관**하게 한곳에 둔다. ③ **플랫폼 차이는 어댑터 안에** 가둔다.

## 2. 현재 상태 (2026-10-20 검증)

| 구성 | Chance_Blog (`chance`) | Blogger (`blogger_macat`) |
|------|------------------------|---------------------------|
| 엔진 | `generator.py` — 레거시 단일 파일. Phase 3에서 `pipeline/`으로 이관 | `python -m pipeline.run --blog blogger_macat` (`blogger_generator.py`는 호환 래퍼) |
| 트리거 | `chanceblog.yml` 매시 17분·47분(KST 9·18시 슬롯을 코드가 판단), 수동 (이슈 요청은 `issue-edit.yml`이, 기존 글 이미지 교체는 수동 전용 `chance-fix-images.yml`이 따로 처리) | `blogger.yml` 매일 02:00 UTC(KST 11시), 수동 |
| 주제 | 약관을 읽은 직접 RSS(NASA·Pew·Federal Reserve·EU 집행위원회 계열·캐나다 통계청·영국 정부 GOV.UK 등, UN News는 보류), 신뢰 도메인 허용 목록, 72시간 이내, 출처 원문 검증 | 프로필 시드(영문 34개) + LLM 확장, 쿨다운 60일, 금지 주제 필터(주제 후보·제목·라벨·본문, §7-1), Chance 이력과 교차 중복 방지 |
| 생성 | Gemini 모델 폴백, KR/EN 쌍, 편집 템플릿 | Gemini 모델 폴백 + 일시 오류 재시도, 형식 엄격 파싱 |
| 게이트 | `validate_post_data`(길이·인라인 출처), 제목 유사도 | `pipeline/gates.py`(파싱·HTML 정화·정책·중복), 탈락 사유를 넣어 최대 3회 재작성 |
| 게시 | git 커밋 → Pages 배포(`pages.yml`). 봇 커밋 뒤 `gh workflow run pages.yml`로 배포 실행 | Blogger API 어댑터(멱등 재시도, 인증 실패 구분, 초안함 업로드 `isDraft`, 쓰기 전 인증 점검 — 아래 §4·§4-1) |
| 상태 | `history.json`(문자열·객체 혼합 스키마) | `blogger_history.json`(스키마 v1, §5) |
| 관측 | Actions 로그 | 실행 요약 + 이력 status + 워치독 |
| 수정 요청(이슈) | `issue-edit.yml` + `pipeline/edits`: 이슈 양식 → 문자 그대로 교체·링크·SEO·이미지(AI는 최소 패치·검색어만) → 사후 검증 → PR. 상세 [`ISSUE_EDITS.md`](./ISSUE_EDITS.md) | 해당 없음(Blogger 글은 Blogger 관리 화면) |
| 상태(운영) | 운영 중. 단 슬롯 시각이 된 실행 13회 중 2회만 글이 나왔다(D-03: 분야 폴백·사유 기록으로 완화, 병합 뒤 관측). 이슈 수정은 `pipeline/edits`로 재구축(D-01, Actions 관측 대기) | 코드 완료(초안함 업로드 모드 포함, D-55). 정지(`mode: off`), 게시용 시크릿 미등록, refresh token 미발급(D-11). 실제 구글 호출은 한 번도 한 적이 없어 시크릿 등록 뒤 첫 수동 실행에서 처음 검증된다 |

공통: 워치독 일 2회(`watchdog.yml`), 저장소 가드레일 CI(`guardrails.yml`), 레지스트리 검증(`python -m pipeline.registry`), PR 범위 검사(`pr-scope-check.yml`, 이슈를 참조하는 모든 PR).

### 2-1. GitHub Actions 탭의 이름 (2026-10-27 기준)

Actions 왼쪽 목록의 이름은 **이름만 보고 어느 채널의 것인지, 자동인지 수동인지, 무엇을 하는지 짐작할 수 있게** 지었다. 맨 앞에 `[구분] `을 붙이고 뒤는 한글로 쓴다. 구분은 블로그 채널 라벨(`Chance`·`Blogger`·`Blogger 영문`·`Blogger 한글`·`티스토리`·`네이버`)이거나, 블로그에 속하지 않는 워크플로의 `공통`(배포·검사·감시·점검), 다른 워크플로가 부르는 공용 실행의 `내부`(직접 실행하지 않는다)다. GitHub에는 워크플로를 묶는 폴더나 분류가 없고 목록이 이름순이라, 접두사가 같은 것끼리 붙어 보이게 하는 것이 구분 수단이다. 파일 이름(`*.yml`)은 그대로이고(레지스트리·워치독·문서가 파일 이름으로 가리킨다) 화면에 보이는 `name`·`run-name`만 바뀌었다 — 워크플로를 이름으로 찾는 코드는 없다(워치독·점검 모음은 파일 이름, 이름은 안내 문구와 모음 항목 제목에만 쓴다). `name`은 대괄호로 시작해 YAML에서 큰따옴표가 필요하다(`name: "[Chance] …"`). 실행 목록의 제목(`run-name`)에는 같은 접두사에 이어 정기/수동·연습 여부(이슈 처리는 이슈 번호)가 붙는다. job 이름과 단계 이름에는 접두사를 붙이지 않는다(job 이름은 PR 검사 화면의 이름이다). 블로그 워크플로의 구분은 레지스트리 `channel.label`(§3)과 같은 글자여야 한다(레지스트리 검증이 읽는다, REG-1). 새 워크플로·job의 이름도 한글로 짓고 접두사를 붙인다(검증기 **WF-11**·**WF-12**, [`ENGINEERING_GUIDE.md`](./ENGINEERING_GUIDE.md) W10). 이슈 제목 접두 `[Watchdog]`·`[운영] 확인 필요 모음`과 라벨 `watchdog`·`ops-inbox`는 이름이 아니라 식별자라 그대로다.

| 옛 이름 | 새 이름 (Actions 탭) | 파일 | 하는 일 | 자동/수동 |
|---------|----------------------|------|---------|-----------|
| Chance_Blog Full-Auto Engine | `[Chance] 글 자동 작성·게시` | `chanceblog.yml` | 뉴스 기사를 바탕으로 Chance 글(한국어·영어)을 만들어 검증하고 저장소에 커밋해 게시 | **자동**(매시 17분 UTC에 실행, 게시 시각은 코드가 판단) + 수동 실행(연습이 기본). 실행 제목 `[Chance] 글 작성·게시 · 정기/수동` |
| (`chanceblog.yml`의 `fix_images` 입력) | `[Chance] 기존 글 이미지 교체(수동)` | `chance-fix-images.yml` | 기존 글의 깨진·누락·중복 이미지만 교체(새 글은 만들지 않음). 2026-10-25에 글 작성 워크플로에서 분리 | **수동 전용**(연습이 기본) |
| Blogger Generate | `[Blogger] 글 자동 작성(초안함 업로드)` | `blogger.yml` | 레지스트리의 Blogger 블로그마다 글을 만들고 검증해 저장소 초안 저장·Blogger 초안함 업로드·즉시 게시 중 하나로 보낸다(블로그 모드에 따름. `mode: off`인 블로그는 건너뛰고, 대상이 하나도 없으면 초록 + `::notice::`) | **자동**(매일 02:00 UTC = KST 11시, 모드를 따름) + 수동 실행(입력 `publish`: `off` 저장소 파일만 · `draft` 초안함 업로드(기본) · `publish` 즉시 게시, 입력 `auth_check`(`인증 점검만 실행`, 기본 꺼짐): 글을 만들지 않고 인증만 점검 — §4-1). 실행 제목 `[Blogger] 글 작성 · 정기/수동(…)` |
| Deploy GitHub Pages | `[공통] 사이트 자동 배포` | `pages.yml` | Chance 사이트(GitHub Pages)를 빌드해 게시 | **자동**(main에 push될 때. 봇이 커밋한 뒤에는 `[Chance] 글 자동 작성·게시`·`[Chance] 기존 글 이미지 교체(수동)`가 직접 실행을 요청) + 수동 |
| Guardrails | `[공통] 저장소 규칙·테스트 자동 검사` | `guardrails.yml` | 비밀 유출·워크플로 보안 규칙·문서 불일치·광고 표면 변경 검사, 단위 테스트, `actionlint` | **자동**(main push·모든 PR) + 수동. job 이름 `검사 (Python 3.10/3.12)` |
| Watchdog | `[공통] 발행 중단 감시·알림` | `watchdog.yml` | 글이 오래 안 올라오거나 실패가 이어지거나 글 커밋 뒤 사이트 배포가 안 되면 `[Watchdog]` 이슈로 알림(담당자 지정·@멘션, 문제일 때만, 해소되면 닫음). 규칙은 §4-2 | **자동**(하루 2회, 시각은 `watchdog.yml`의 cron) + 수동. 실행 제목 `[공통] 발행 중단 감시 · 정기/수동` |
| Issue Edit | `[Chance] 이슈 수정 요청 처리(수정안 PR 만들기)` | `issue-edit.yml` | 이슈 양식으로 접수된 수정 요청을 검증해 수정안을 PR로 만든다(main에 직접 반영하지 않음) | **자동**(제어 이슈가 열릴 때) + 수동(이슈 번호 입력, 연습이 기본). 실행 제목 `[Chance] 이슈 #번호 수정 요청 처리 · …` |
| PR Scope Check | `[공통] PR 변경 범위 검사` | `pr-scope-check.yml` | 이슈를 참조하는 PR(Copilot·사람)이 요청 범위를 지켰는지 검사해 PR에 코멘트 | **자동**(PR이 열리거나 갱신될 때) + 수동(PR 번호 입력) |
| Sync Issue Form | `[공통] 이슈 양식 페이지 목록 갱신` | `sync-issue-form.yml` | `pages.json`과 이슈 양식의 '대상 페이지'·'수정 항목' 드롭다운을 최신으로 갱신 | **자동**(관련 파일이 main에 push될 때) + 수동 |
| (신규) | `[공통] 확인 필요 모음` | `ops-inbox.yml` | 해야 할 일·확인할 일(워치독 알림·병합 대기 PR·실패한 워크플로·승인 대기·일시정지·Blogger 게시 설정·채널별 초안 현황)을 이슈 `[운영] 확인 필요 모음` 1개와 실행 요약에 모으고, 새로 해야 할 일이 생기면 코멘트(@멘션)로 알림. 설명: [`OPS_INBOX.md`](./OPS_INBOX.md) | **자동**(2시간 간격 예약, 매 짝수 시 40분 UTC — GitHub가 늦추거나 건너뛰어 실제로는 보통 3~6시간 간격 + 라벨 `초안`이 붙은 이슈·PR이 열리고 닫히고 라벨이 바뀔 때, 사람이 한 조작에 한함) + 수동(`연습 실행` 가능). 실행 제목 `[공통] 확인 필요 모음 갱신 · 정기/수동/이슈 변경(초안만 점검)/PR 변경(초안만 점검)` |
| (GitHub 내장) | `pages-build-deployment` | 파일 없음 | GitHub Pages가 스스로 만들어 목록에 보일 수 있는 실행. 이름을 바꿀 수 없다. **누르지 않는다**(배포는 `[공통] 사이트 자동 배포`) | GitHub 내장 |

기본 제목(커밋 메시지·PR 제목)이 더 알려 주는 `[공통] 사이트 자동 배포`·`[공통] 저장소 규칙·테스트 자동 검사`·`[공통] PR 변경 범위 검사`·`[공통] 이슈 양식 페이지 목록 갱신`은 `run-name`을 따로 두지 않았다. 정기·수동·연습은 `Run workflow` 대화상자 입력(`연습 실행` 체크)과 실행 제목으로 구분한다.

**새 워크플로를 만들면 이 표와 [`REQUEST_BRIEFING.md`](./REQUEST_BRIEFING.md)의 표에 한 줄씩(`파일`과 `이름`을 같은 줄에 백틱으로) 넣어야** `tests/test_workflow_names.py`의 `test_docs_tables_list_every_workflow_with_its_current_name`이 통과한다. 안내 문서·워크플로·이슈 양식·코드에 옛 영문 이름이 새 이름 없이 남아도(옛 이름과 새 이름이 한 줄에 같이 있는 대응표는 제외) `test_operator_docs_do_not_use_the_old_english_names`가 실패한다.

**수동 실행의 기본값과 정지 스위치**(2026-10-25, D-51·D-53·D-54): 무료 Gemini 한도는 프로젝트 단위로 모든 파이프라인이 한 통을 나눠 쓰므로, 점검용 수동 실행이 정기 발행의 몫을 쓰지 않게 기본값을 '연습'으로 맞췄다. `[Chance] 글 자동 작성·게시`와 `[Chance] 기존 글 이미지 교체(수동)`의 `연습 실행`(기본 켜짐)은 **가짜 AI 응답(스텁)**을 쓰고 Gemini 키를 프로세스에 넘기지 않아 호출이 0회이며, 연습에서도 실제 호출로 시험하려면 `real_ai`를 체크한다(기본 꺼짐. 실행 제목에 '실제 AI 호출'이 붙고 요약에 'AI 응답' 줄이 남는다). `[Blogger] 글 자동 작성(초안함 업로드)`의 `dry_run`도 기본이 켜짐으로 바뀌어, 체크를 풀어야 실제 Gemini로 글을 만들어 초안을 저장소에 커밋하고(Blogger에 올릴지는 `publish` 입력에 따른다) 그날 하루 상한을 쓴다. 정기 실행과, 연습을 풀고 실제로 게시하는 수동 실행은 예전처럼 항상 실제 Gemini를 부른다. 기존 글 이미지 교체는 한 번에 최대 20건(`generator.py`의 `FIX_IMAGES_MAX_PER_RUN`)만 처리하고 나머지는 다음 실행으로 넘기며 요약에 그 사실을 남긴다(연습 실행의 요약은 '교체 예정 N건 중 M건 처리 대상'). Chance의 수동 실제 실행은 게시 시각 판단과 하루 상한(`pipeline/blogs.json`의 `max_posts_per_day`)을 따지지 않는다 — 운영자가 일부러 더 게시할 수 있어 막지 않고, 오늘 이미 게시된 글이 상한 이상이면 `::warning::`과 요약 줄만 남긴다. `[Chance] 이슈 수정 요청 처리(수정안 PR 만들기)`도 이제 `PIPELINE_PAUSE`(`1`·`true`·`yes`·`on`)를 읽는다: 켜져 있으면 AI·이미지 검색을 부르지 않고 파일·PR도 만들지 않으며, 형식이 맞는 요청에는 이슈에 '일시정지 중' 코멘트만 남기고 정상 종료한다(코멘트는 변수를 지운 뒤 `연습 실행` 체크를 풀고 다시 실행하라고 안내한다 — 수동 실행은 `연습 실행`이 기본 켜짐이라 그냥 다시 실행하면 연습만 돌아 PR이 안 생긴다). 알아 둘 한계 셋: ① **연습 실행도 Unsplash 이미지 검색은 실제로 한다**(`UNSPLASH_ACCESS_KEY`는 연습에서도 넘어간다). 글 작성 연습은 검색 1회 이하, 이미지 교체 연습은 문제 글마다 1~2회(한 번에 최대 20건이면 20~40회)이며 시간당 한도(코드 주석상 데모 앱 50회)를 정기 글·이슈 이미지 검색과 나눠 쓴다 — 실행 요약의 `Unsplash 남은 호출` 줄로 본다. 연습에서 Unsplash 키도 비우는 안은 운영자 결정 사항이라 동작을 바꾸지 않았다. ② 정기 실행도 하루 상한을 직접 검사하지 않고 슬롯 2개(KST 9시·18시)로만 하루 2편을 지킨다. 수동 글은 `slot=None`이라 슬롯에 잡히지 않아, 09시 슬롯 글이 있는 날 낮에 수동 실제 게시를 하면 18시 정기 실행이 또 만들어 **하루 3편**이 될 수 있다(경고는 수동 실행 시점에 이미 상한 이상일 때만 뜬다). 상한 강제는 T3 결정이다. ③ 정지 중에도 이슈 수정은 `gh label create --force` 4건과 이슈 코멘트 1건을 한다('저장소 쓰기 0'이 아니라 '파일·PR 0'). 이미지 교체의 '나머지는 다음 실행'은 사람이 `Run workflow`를 다시 눌러야 하고, 앞 20건이 영구 실패하면(검색 결과 없음 등) 뒤 글에는 차례가 오지 않는다(**굶김** — 선정 순서는 바꾸지 않았다). 교체가 전부 실패해도 요약이 `교체 0건 / 건너뜀 N건`이고 실행은 초록이다. Blogger 수동 연습의 격리는 Chance처럼 키를 빼는 방식이 아니라 `pipeline/run.py`의 `dry` 분기에 의존한다(키는 연습에도 환경에 있고, 연습이면 LLM·게시자를 만들지 않는다).

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
| `platform` | `jekyll-git` · `blogger` (새 플랫폼은 §7.B) |
| `channel` | **필수.** `{"key": "<영문 식별자>", "label": "<채널 라벨>"}` — 항목에 직접 적는다(`defaults`에서 물려받지 않는다). `label`은 `Chance`·`Blogger`·`Blogger 영문`·`Blogger 한글`·`티스토리`·`네이버` 중 하나(`registry.CHANNEL_LABELS`)이고, **그 블로그 `workflow` 파일의 `name`이 `"[label] …"`로 시작해야 한다**(§2-1. 대괄호로 시작하는 값이라 큰따옴표가 필요하다). `label`·`key`는 블로그끼리 겹칠 수 없다(채널 = 블로그 하나). `공통`·`내부`는 블로그에 속하지 않는 워크플로의 구분이라 여기에 쓰지 않는다. 검증: 레지스트리 검증(REG-1 — `python -m pipeline.registry`·`pipeline.plan`·`pipeline.run`이 같은 규칙을 읽는다). 그래서 **한 워크플로 파일을 채널이 다른 블로그 둘이 나눠 쓸 수 없다** — 채널마다 이름이 다른 워크플로가 필요하다 |
| `mode` | `off` 중지 · `draft` 초안 — Blogger는 게시용 시크릿 4종(`blog_id`·`client_id`·`client_secret`·`refresh_token`)이 **모두** 있으면 글을 Blogger **초안함에 업로드**하고(`draft_uploaded`, 공개되지 않음 — 운영자가 Blogger 화면에서 확인한 뒤 직접 게시), **하나도** 없으면 저장소 파일에만 저장하며(`draft`, 오류 아님), **일부만** 있으면 설정 오류(종료 2) · `auto` 자동 게시. **`auto` 전환은 T3** |
| `workflow`, `entrypoint`, `prompt` | 저장소에 존재하는 파일. `workflow`의 cron 목록에 `schedule.cron`이 들어 있어야 한다(검증기 REG-2, Chance는 17분·47분 두 틱이고 레지스트리에는 17분이 대표값) |
| `profile` | `pipeline/profiles/<이름>.json`. `blogger` 플랫폼은 필수. 글 언어 검사는 `languages`(표시·문서용)가 아니라 프로필의 `language`(`ko`·`en`)가 정한다. 필드와 가드레일은 §7-1 |
| `state.history`, `state.content_dir` | 이력 파일, 산출물 폴더(저장소 상대 경로, `..` 금지) |
| `schedule.cron` | 워크플로 cron 목록 중 하나(대표값). `slots_kst`는 참고 |
| `limits.max_posts_per_day` | 1~24. 하루 상한(KST 날짜 기준). 수동 `--topic`은 우회 |
| `llm.models`, `llm.max_retries` | 모델 폴백 순서, 일시 오류 재시도 횟수 |
| `secrets` | `{역할: 환경변수(=Secrets) 이름}`. **값은 절대 쓰지 않는다.** 플랫폼별 필수 역할은 `registry.PLATFORMS` |
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
- **선언과 사실의 일치(검증기 REG-5)**: `jekyll-git` 블로그는 광고 표면(`protected_paths`)의 파일에 광고 코드(`adsbygoogle`·`googlesyndication`·`ca-pub-숫자`)가 있으면 `ads`가 `on`이어야 하고, `ads`가 `on`이면 광고 코드가 있어야 한다. 광고 코드를 넣거나 빼는 변경과 `ads` 값 변경은 한 묶음이라 둘 다 T3(사용자 승인)다 — 광고 표면 파일 쪽은 검증기 AD-1이 커밋 메시지의 `Ad-Surface-Approved: <사유>`를 요구하고, `ads` 값 쪽은 같은 표시를 붙이는 정책이다(기계가 확인하지 않는다).
- **지금 값**: `chance` = `on`(홈 `index.html`에 광고 스크립트가 있다. 글 페이지에는 없다), `blogger_macat` = `off`. `pending_gate`·`on`으로 올리는 편집은 T3다.
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
| **Record** | 이력 항목 추가(최근 200개 유지) + 초안 파일 저장(최근 120개) | 이력 파일이 손상돼 있으면 **덮어쓰지 않고** 종료 코드 1 (fail closed) |
| **Deploy** | (`jekyll-git`) 커밋 push 후 `pages.yml` dispatch. 배포 뒤 `verify` 잡이 새 글의 공개 주소가 열리는지 확인(§4-3) | dispatch 실패 시 워크플로 실패. 새 글이 마감(12분)까지 공개 주소에서 안 열리면 배포 실행이 빨강이 되어 워치독이 알린다 |
| **Observe** | 워치독: 이력·마지막 커밋·최근 실행 → `[Watchdog]` 이슈 | 이슈 생성/자동 해소 |

종료 코드: `0` 정상(건너뜀 포함) / `1` 인프라 실패 / `2` 설정 오류.

## 4-1. 건너뜀·종료 규약 (스킵 코드)

"할 일이 없어서", 또는 "조건이 안 맞아서" 끝나는 실행도 **왜** 끝났는지 남긴다. 초록 체크는 "프로그램이 오류 없이 끝났다"는 뜻일 뿐 "글이 올라갔다"는 뜻이 아니기 때문이다(2026-10-25 진단: Chance는 슬롯 시각이 된 스케줄 실행 13회 중 11회가 글 없이 초록으로 끝났고, Blogger는 게시 시크릿이 없어 초안만 만든 채 초록이었다).

한 줄 규격: `[SKIP] code=<코드> key=값 ...` — Actions 로그에서 `[SKIP]`로 찾고, 같은 코드가 실행 요약(Step Summary)에도 쓰인다. Blogger 러너(`pipeline/run.py`)의 실행 요약은 어느 경로든 첫 줄이 `### [채널 라벨] 블로그 이름`(레지스트리의 `channel.label`·`name`, 예: `### [Blogger] Blogger (macat0722)`, `summary_head()`)이고 그 아래 줄(`- 결과: **코드** — …`·URL·안내·Gemini 호출)은 이 규약의 코드와 같다(2026-10-27 이전에는 첫 줄이 블로그 key였다).

| 수준 | 의미 | 처리 | 종료 | 코드 |
|------|------|------|------|------|
| 정상 건너뜀 | 지금 할 일이 아님 | 초록 + 로그 한 줄(Blogger의 `PAUSED`·`MODE_OFF`·`DAILY_CAP`·`UPLOAD_SKIPPED`는 `::notice::` 주석도) | 0 | `OUT_OF_WINDOW`(첫 게시 시각 전), `ALREADY_PUBLISHED`(그 슬롯 글이 이미 있음), `PAUSED`(`PIPELINE_PAUSE`), `MODE_OFF`(레지스트리 mode off), `DAILY_CAP`(Blogger 하루 상한 소진), `DRY_RUN`(연습 실행), Blogger: `UPLOAD_SKIPPED`(Blogger 초안함에 올릴 차례인데 게시용 시크릿이 하나도 없어 **저장소 파일에만 저장** — 글은 만들어지고 이력은 `draft`, 요약에 등록할 시크릿 **이름**이 남는다) |
| 경고 | 게시하려 했는데 못 했지만 다음 실행에서 다시 시도 | 초록 + `::warning::`(노란 주석) + 요약 | 0 | `ALL_REJECTED`(후보는 있었으나 Gemini 건너뜀·제목 유사·본문 검증 탈락으로 전부 탈락. 수동 실행은 예외로 빨강), `ALL_DUPLICATES`(검증된 기사는 있었지만 모두 이미 쓴 글과 비슷 — 뉴스가 뜸한 때), `NO_CANDIDATES`(시간 상한으로 일부 분야만 시도하고 후보 없음), `NO_MATCH`(수동 주제 요청과 연결되는 검증된 기사 없음), Blogger: `NO_TOPIC`(시드·확장 후에도 쓸 주제 없음), `GATE_REJECTED`(재작성 끝에도 게이트 탈락) |
| 실패 | 발행하려던 실행이 0건으로 끝난 이상 신호 | **빨강** + `::error::` + 요약 | 1 | `ALL_LANES_EMPTY`(모든 분야에 검증을 통과한 기사가 한 건도 없음), `SOURCES_UNREACHABLE`(시도한 뉴스 소스가 모두 수집 실패 — 네트워크·소스 장애), Blogger: `LLM_FAILED`·`EXPAND_FAILED`(주제 확장 실패)·`PUBLISH_FAILED`(게시·초안함 업로드 실패. 어댑터가 분류하지 못한 예외도 포함, `reason=`으로 분류하고 `target=draft`/`publish`로 구분)·`HISTORY_WRITE_FAILED`(업로드·게시는 끝났는데 이력 파일을 쓰지 못함 — 글 ID·주소는 로그와 요약에 남고, 같은 날 다시 실행하기 전에 Blogger를 확인)·`AUTH_CHECK_FAILED`(인증 점검 실패 중 종료 1인 분류: `auth_expired`·`network`·`bad_response`·`api_error`·`unexpected` — 아래 분류표) |
| 설정 오류 | 사람이 고쳐야 하는 설정 | **빨강** + `::error::` + 요약 | **2** | Blogger `SECRETS_MISSING`(즉시 게시인데 게시용 시크릿이 없거나, 초안함 업로드인데 **일부만** 있음 — 글을 만들기 전에 멈춘다, 초안·이력 없음, 시크릿 **이름**만 표시)·`INVALID_PUBLISH`(`BLOGGER_PUBLISH` 값을 알 수 없음)·`TOPIC_BLOCKED`(수동 `topic`이 프로필의 금지 주제 낱말에 걸림 — Gemini·Blogger를 부르기 전에 멈추고 이력·초안은 남지 않는다. 걸린 낱말은 로그·요약에 남고 `::error::` 주석은 입력 문자열이 없는 고정 문장이다)·`AUTH_CHECK_FAILED`(인증 점검 실패 중 종료 2인 분류: `auth_failed`·`blog_mismatch`)·레지스트리 검증 실패 |

**Blogger 실행(`pipeline/run.py`)의 처리 순서**: `PIPELINE_PAUSE` → `mode: off` → `BLOGGER_PUBLISH` 값 검사(알 수 없으면 종료 2) → 게시용 시크릿 점검(즉시 게시인데 없거나 초안함 업로드인데 일부만 있으면 종료 2) → **수동 `topic` 금지 주제 검사**(프로필의 `banned_topic_patterns`에 걸리면 `TOPIC_BLOCKED`, 종료 2 — 이력 읽기보다 앞이라 상태 파일 문제에 가리지 않는다) → 초안함 업로드인데 게시용 시크릿이 하나도 없으면 `UPLOAD_SKIPPED`로 저장소 파일에만 저장(주제 검사 뒤에 둔다 — 막힌 주제로 아무것도 저장하지 않고 멈추는 실행에 '저장합니다' 안내가 먼저 나오면 모순이다. D-64 ⑦ N-7) → 이력 읽기(손상이면 종료 1) → 하루 상한(`--topic` 지정은 이것을 우회하지만 금지 주제 검사는 우회하지 못한다) → LLM 키(없으면 종료 2) → **인증 점검**(업로드·게시일 때만, 실패하면 종료 1 또는 2) → 주제 → 생성·게이트 → 연습 실행/즉시 게시/초안함 업로드/저장소 초안. 인증 점검을 글 생성 앞에 둔 이유: 인증이 깨진 날 무료 Gemini 호출을 쓰지 않고, 같은 계정의 다른 블로그 ID 를 넣은 사고를 글을 만들기 전에 막는다.

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

**인증 점검 실패의 분류와 종료 코드**(`pipeline/auth_check.py`, [`ENGINEERING_GUIDE.md`](./ENGINEERING_GUIDE.md) R6의 '설정 오류 2 / 인프라 실패 1'): 2는 사람이 설정(블로그 ID·계정 권한·클라이언트 값)을 고쳐야 하고 다시 실행해도 같은 결과인 실패, 1은 시간이 지나 생기는 외부 상태(토큰 만료·폐기)나 일시 오류(네트워크·API 오류)다. 로그에는 `[SKIP] code=AUTH_CHECK_FAILED reason=<분류> exit=<종료 코드>`와 고정 문장의 `::error::`가, 이력에는 `publish_failed`(분류가 `reasons[0]`)가 남고 Gemini·업로드·게시는 하지 않는다. 블로그 주소가 다를 때 응답의 주소·이름은 같은 계정의 다른 블로그 정보가 공개 로그에 남지 않도록 출력하지 않는다.

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
- 소스별 선택 키: `citation`(글 끝 인용 한 줄의 틀 — `{title}`·`{date}`·`{url}`, 소스 약관이 정한 형식, 고지문 앞에 붙임), `exclude_title`·`exclude_link`·`exclude_tags`(제목·기사 주소·피드 분류 태그 정규식, 맞으면 `EXCLUDED`), `topic_regex`(제목·분류 태그에 맞는 말이 없으면 `OFF_TOPIC`), `no_page_fetch`, `notice`(글 끝 고지문 ko·en — `add_discovery_metadata`가 글 언어(front matter `lang`, 없으면 한글 여부)에 맞춰 붙이고 이미 있으면 다시 붙이지 않는다), `prompt_rule`(글 작성 지침에 한 줄), `display_name`(글에 보이는 출처 이름, 생략하면 `name` — 한 게시자의 피드를 분야별로 나눠 읽을 때 `name`이 달라야 해서 둔다). 피드의 `<category>`(Atom은 `term`)는 `parse_feed`가 `categories`로 읽고, 글자가 자식 요소 안에 있는 Atom `type="xhtml"` 제목·요약(통계청)도 자식까지 이어 읽는다.
- 직접 RSS 항목의 `<source>` 태그(UN News는 피드 태그라인이 들어 있다)는 게시자 표시로 쓰지 않는다 — 게시자는 기사 주소의 호스트이고 출처 이름은 소스 이름이다. 구글 뉴스 해석 코드(`google` 키, `_resolve_article_url`)는 쓰는 소스가 없지만 시험이 있어 남겨 두었다.

**Chance 분야 폴백**: 슬롯 시각마다 6개 분야를 확률 가중 추첨 순서(`editorial_lane_order`, 첫 분야는 기존 추첨과 같음)로 늘어놓고, 앞에서부터 후보가 나올 때까지 시도한다. 이 단계는 Gemini를 부르지 않아 비용은 수집 시간뿐이다. `LANE_SEARCH_BUDGET_SECONDS`(기본 480초)가 지나면 새 분야도, 분야 안의 남은 소스도 시도하지 않는다(이미 시작한 소스 하나는 끝까지 기다리므로 수집은 상한 + 약 2분 안에 끝나고, 잡 제한은 20분이다). 시도한 소스가 전부 수집 실패면 시간과 무관하게 `SOURCES_UNREACHABLE`(빨강)이다. 글이 만들어지면 이력의 `lane`과 Gemini 프롬프트에는 실제로 후보가 나온 분야가 쓰인다.

후보 하나가 탈락해도 실행은 계속된다: Gemini가 만든 본문이 검증(한국어 1000자·영어 1500자 이상, 검증된 원문 링크 인용)에 못 미치거나 JSON을 못 맞추면 그 후보만 탈락시키고(이미지를 고르기 전에 검사하므로 Unsplash 호출을 쓰지 않는다) 다음 후보를 시도한다(최대 `MAX_ATTEMPTS`=3건). 예전에는 첫 후보의 본문이 얇으면 실행 전체가 빨강으로 끝났다(D-36). 모든 모델이 실패하는 Gemini 장애는 그대로 빨강이다. 실행 요약에는 후보 탈락(본문 검증·응답 형식) 건수와 사유, Gemini 모델 호출 횟수(`- Gemini 호출: N회(실패 K회)`, 무료 한도를 나눠 쓰기 위한 측정값)를 남긴다.

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
| `FAIL_STREAK` / `REJECT_STREAK` | 심각 / 경고 | 최근 N회 연속 실패 / 5회 연속 게이트 탈락 |
| `UNPUBLISHED` | 경고 | mode auto인데 가장 최근 실행이 게시 없이 저장소 초안만 남김(이력의 사유를 인용). 게시 대상인데 게시 시크릿이 없으면 종료 2로 빨강이라 지금은 새로 생기지 않는다. `mode: draft`의 `draft_uploaded`(Blogger 초안함에 올림)는 게시 없는 초안이 아니라 '글이 나온 날'로 센다 |
| `PAGES_NOT_DEPLOYED` | 심각 | 글 커밋 뒤 30분(+시계 오차 여유 120초)이 지났는데 main 브랜치의 성공한 사이트 배포 실행이 없음 |
| `PAGES_FAILED` | 경고 | 가장 최근 사이트 배포 실행이 실패 |
| `RUN_FAIL_STREAK` | 심각 | 워크플로가 최근 N회 연속 실패 |

알림 방식: (블로그, 코드)마다 이슈 하나를 유지한다. 저장소 소유자를 담당자로 지정하고 본문에 @멘션하며, 열려 있는 동안 본문을 최신 내용으로 갱신하고, 심각 건이 48시간 지나도 풀리지 않으면 코멘트로 다시 알린다. 조건이 풀리거나 다른 알림으로 대체되면 자동으로 닫는다. 한 실행에서 새로 만드는 이슈는 5건까지(심각 건 먼저). 이 실행(워크플로)은 **이번에 새로 생긴 심각 건이 있을 때만 빨강(종료 1)**이 되어 Actions 실패 알림도 가고, 이미 알린 심각 건이 이어지는 동안은 초록이다. `PIPELINE_PAUSE`가 켜져 있으면 알림을 만들지 않는다. 글 파일 추가 판정은 git 이력이 필요해 워크플로가 `fetch-depth: 0`으로 받아야 한다(얕은 복제면 경고를 내고 이력 파일로만 판단한다).

### 4-2-1. 초안 모델과 초안 현황 (2026-10-27, 작업요청서 5 PR-B)

사람이 발행해야 하는 글(티스토리·네이버 초안 패키지, Chance 승인 흐름, Blogger 초안함)의 대기 상태를 한 약속으로 센다. **초안 1건 = GitHub 이슈 1개 또는 PR 1개**, 라벨 `초안`(대기) + `채널:<채널 라벨>`(채널 라벨은 레지스트리 `channel.label`과 같은 글자), 쓰지 않을 초안은 라벨 `폐기` 또는 닫기(닫기 = 발행 완료 또는 폐기). 초안을 만드는 쪽(작업 C·E)이 이 라벨을 붙이고, `[공통] 확인 필요 모음`이 읽어 본문 맨 위의 **초안 현황** 표(채널 | 대기 초안 | 가장 오래된 | 최신 초안)와 항목(열린 초안 이슈·PR이 새로 생기면 action — 코멘트 알림, 3일 넘으면 check)을 만든다. 초안 PR은 한 줄만 남긴다: 열린 PR 규칙이 이미 action으로 올린 PR(병합하면 됩니다·충돌·검사 실패)은 그 줄이 알리고, 그 밖의 상태(저장소 기본 토큰이 연 PR은 검사가 돌지 않아 `검사 결과 없음`이 되기 쉽다)는 열린 PR 줄을 빼고 초안 항목이 알린다. Blogger는 이력의 `draft_uploaded`(최근 14일)를 센 **대략치**다(공개 여부는 Blogger 쪽 사실). 레지스트리에 `publish_flow: pr`(작업 E)이 있는 Chance는 열린 초안 PR 수, 없거나 `direct`면 `자동 공개`다. 규칙(`pipeline/inbox.py`)·읽기와 라벨 만들기(`scripts/ops_inbox.py`)·갱신 트리거(`ops-inbox.yml`의 `issues`·`pull_request`)의 상세와 한계(기본 토큰이 만든 이벤트는 워크플로를 시작시키지 않음)는 [`OPS_INBOX.md`](./OPS_INBOX.md) §3-1·§5.

## 4-3. 배포 후 공개 확인 (`pages.yml`의 `verify` 잡, D-41)

배포 워크플로가 초록이어도 "새 글이 공개 주소에서 열린다"는 보장은 없다(빌드 산출물에서 글이 빠졌거나 공개 CDN이 이전 응답을 들고 있을 수 있다). `deploy` 잡 뒤의 `verify` 잡이 `scripts/verify_pages_deploy.py`로 다음을 확인한다(표준 라이브러리만 사용, 잡 제한 15분).

1. 저장소 `_posts`에서 **공개될 가장 새 글**(같은 시각의 KR/EN 쌍)을 고른다. `published: false`(`False`·`no`·`off`·`null`·빈 값, 따옴표 친 값은 보수적으로 포함. 키를 따옴표로 감싸거나 콜론 앞에 공백을 둔 `"published": false`·`published : false`도 같은 키)와 미래 `date`(Jekyll 기본값 `future: false`)는 사이트에서 빠지므로 제외하고 그다음 새 글을 본다. 전부 제외되면 `건너뜀`(초록, 요약에 이유). `_posts` 폴더 자체가 없으면 설정 오류(종료 2) — 조용히 건너뛰면 검증이 꺼진다.
2. 그 글의 공개 주소를 `_config.yml`의 `permalink`(`:year :month :day :title`만 계산)와 파일명, 글 자신의 front matter(`permalink`·`slug`·`date`)로 **계산**해 HTTP 200으로 열리는지 본다. 계산할 수 없는 패턴이면 공개 `posts.json`의 `absoluteUrl`(같은 출처 https만)을 쓴다. 공개 `posts.json`은 보조 정보(소비자가 읽는 목록에 같은 주소로 실렸는지, 다르면 경고)이며 낡았다는 이유로는 실패시키지 않는다. 다만 계산한 주소가 안 열릴 때 `posts.json`이 알려 준 같은 출처 https 주소가 열리면 그 주소로 확인하고 경고만 남긴다(주소 계산이 Jekyll과 달랐을 때의 안전망).
3. 안 열리면 **마감 720초**까지 다시 확인한다. 대기는 **10초에서 2배씩 늘어난다**(10·20·40·80·160초, 이후 160초 — 기본값이면 시도는 0·10·30·70·150·310·470·630초 부근 8번). 다음 시도가 마감 뒤에 시작하게 되면 그만두고, 마감 뒤에는 새 시도도 새 요청도 시작하지 않는다(첫 시도는 마감과 무관하게 끝까지). **시도마다 요청 모양을 바꾼다**(아래). 요청 하나는 소켓 연산별 15초·전체 30초가 상한이고, 글 주소는 상태만 보므로 본문을 읽지 않는다. 끝내 안 열리면 종료 1(`::error::`)로 배포 실행이 빨강이 된다. 실행 요약에는 시도 기록(시도별 경과 초·요청 모양·상태)과 마지막 응답의 상태·`X-Cache`·`Age`·`Last-Modified`가 남아 '캐시에 남은 404'와 '진짜 미반영'을 가려 볼 수 있다. 진행은 로그에 시도마다 실시간으로 찍힌다.

**공개 CDN과 요청 모양**(2026-10-25 독립 검증 실측, 구현자 재확인): 공개 CDN(Fastly)은 200 응답을 `Cache-Control: max-age=600`으로 보관하고, 없는 주소의 **404도 보관**한다(404 응답에는 `Cache-Control`이 없다). 쿼리 문자열(`?cb=…`)·`Cache-Control: no-cache`·`Pragma` 요청 헤더로는 이 보관을 피하지 못한다. 그래서 첫 요청이 배포 전파 전이라 404를 받으면, 같은 주소를 같은 모양으로 다시 요청하는 재시도는 그 404를 계속 돌려받아 마감에 빨강이 된다(옛 설계 — 검증자의 모델로 재현, 이 PR의 `CdnRotationTest`가 같은 시나리오를 고정한다). 404 보관은 **최대 약 18분**이다(검증자 1회 측정: `Age` 963~1078초까지 HIT, 약 1114초에 MISS. 구현자가 같은 날 한 관측은 한 객체가 `Age` 497초까지 HIT였고 나머지는 136~266초에 새로 바뀌어 차이가 있다 — **보관 시간은 불확실**하다). 이 보관을 피하려고 시도마다 캐시 키가 달라지는 요청 모양을 바꾼다. 첫 시도는 정규 주소이고 이후 순서는 ① 끝에 `index.html` ② `Accept-Encoding: gzip` ③ `Accept-Encoding: deflate` ④ 첫 구간 뒤 `//`(`chanceblog//posts/…`) ⑤ 둘째 구간 뒤 `//`(`posts//2026/…`) ⑥ 끝에 `//` ⑦ 둘째 구간 뒤 `./`(`posts/./2026/…`) ⑧ `index.html`+gzip ⑨ `index.html`+deflate 이다(`SHAPES`). 검증자가 실제 사이트의 기존 글에서 모양마다 HTTP 200과 `X-Cache: MISS`(새 캐시 객체)를 확인했고, 구현자도 기존 글 한 건에 10가지 모양을 한 번씩 요청해 모두 200·MISS(`gzip` 응답은 `Content-Encoding: gzip`)임을, 없는 주소에는 10가지 모두 404·MISS(어떤 모양도 없는 글을 200으로 만들지 않음)임을, 같은 모양을 20여 초 뒤 다시 요청하면 404 `X-Cache: HIT`(`Age` 23~29초)임을 확인했다. `br`·`identity`·임의 토큰·대문자 호스트·`Accept-Language`·`Cookie`·퍼센트 인코딩은 같은 객체로 돌아와 쓰지 않는다. 성공은 상태 200으로만 판정한다. 이 주소에 쓸 수 없는 모양(슬래시로 끝나지 않는 주소의 `index.html` 등)은 건너뛰고 쓸 수 있는 모양만 돌린다. **한계**: 모양을 모두 쓴 뒤(기본값에서는 8번째 시도 다음이라 오지 않고 `--interval 1` 같은 작은 값에서만)에는 처음 모양으로 돌아가 보관 중인 404를 읽을 수 있다. 기본값의 마지막 시도는 약 630초이고 다음은 790초라 마감 720초 뒤라서, 그 뒤 약 90초는 보지 않는다. 첫 시도(정규 주소)가 404였다가 다른 모양으로 200을 확인하고 끝나면 정규 주소를 여는 독자는 CDN 보관이 끝날 때까지 404일 수 있어 요약에 경고로 남긴다. 첫 요청 전에 일부러 기다리는 시간은 두지 않았다(배포 직후 원본이 글을 내놓기까지의 지연을 실측하지 못해 추측으로 넣지 않음). 요약의 '해석'은 마지막 응답의 `Age`를 이 검사의 경과 시간과 견준다: `Age`가 경과 시간(+5초 여유) 이내면 이 검사가 앞서 보낸 요청이 남긴 404를 다시 읽은 것이고(그 요청 때 원본이 404를 줬다는 뜻), 더 크면 검사 시작 전부터 CDN이 들고 있던 응답, `MISS`이거나 `Age`가 없거나 0이면 원본이 직접 준 404(진짜 미반영 가능성)다. **배포 때 CDN이 비워지는지는 관측하지 못했다** — 병합 뒤 첫 배포의 요약에서 '시도 기록'과 `X-Cache`·`Age`·`Last-Modified`(새 글 주소와 배포 전부터 있던 `posts.json`)를 확인한다(`DEFECT_REGISTER.md` 하단 체크리스트).

**한계**: 이 확인은 가장 새 글(공개 가능한 것)의 공개 여부만 본다. 글을 추가하지 않은 커밋(이미지 교체·기존 글 수정·설정 변경)의 반영 실패는 이미 공개 중인 최신 글 때문에 통과한다. Jekyll 빌드 자체가 실패하는 경우(D-24형)는 `build` 잡이 먼저 빨강이 되고 `verify`는 건너뛰어지므로(skipped) 이 잡이 새로 잡는 것이 아니다. 또 워치독이 verify 실패를 빌드 실패 문구로 설명하고 취소된 실행을 다루지 못하는 문제는 워치독 쪽 작업이다(D-44). 글 선정·주소 계산의 알려진 차이: front matter는 블록 매핑의 한 줄 `키: 값`만 읽고(키 따옴표·콜론 앞 공백은 허용), 따옴표 친 `date: "… HH:MM:SS"`는 Jekyll이 사이트 시간대로 읽지만 이 스크립트는 UTC로 읽는다(사이트 시간대가 Asia/Seoul이면 미래 판정이 9시간 어긋난다. 이 저장소의 글에는 없다). 주소의 `:title`은 결합 문자(Mark) 등 일부 유니코드 범주를 Jekyll과 다르게 처리할 수 있다(N-5, 고치지 않음 — 한글·영문 slug에는 영향이 없다).

## 5. 상태·멱등성·동시성

- **이력 스키마 v1**: `v`, `blog`, `date`(KST `YYYY-MM-DD`), `generated_at`(ISO, KST), `status`, `topic`, `topic_source`(`seed`·`llm`·`override`), `title`, `labels`, `url`, `post_id`, `model`, `attempts`, `reasons[]`.
  `status`: `posted`(즉시 게시) · `draft_uploaded`(Blogger 초안함에 업로드 — `post_id`·`url`은 API 응답, 블로그 ID는 기록하지 않는다) · `draft`(저장소 파일에만 저장) · `generated_unpublished`(옛 기록: 게시 시크릿이 없던 때의 초안 — 지금은 게시 대상이 시크릿이 없으면 종료 2로 멈추고 기록하지 않는다) · `rejected` · `publish_failed`(게시·업로드·인증 점검 실패 — 인증 점검 실패는 글을 만들기 전이라 `topic`이 비어 있다) · `llm_failed` · `skipped_no_topic`.
- **일일 상한**: `posted`·`draft`·`draft_uploaded`·`generated_unpublished` 건수가 `max_posts_per_day`에 도달하면 건너뛴다(`rejected`·`llm_failed` 등 글이 안 나온 실행은 세지 않는다). 예외로 `publish_failed`는 **응답에서 글 ID(`post_id`)를 읽은 것만** 센다 — 올리다 실패했어도 초안·글이 이미 Blogger에 만들어졌을 수 있어, 세지 않으면 같은 날 재실행이 초안을 또 만든다. 글 ID가 없는 실패(인증·네트워크 등)는 세지 않는다. 이 이유는 `DAILY_CAP` 주석과 요약에 적히고, 운영자는 Blogger 초안함·글 목록을 확인한다(`topic` 입력은 상한을 건너뛴다). 워치독은 `posted`·`draft_uploaded`를 '글이 나온 날'로 센다.
- **쿨다운**: 프로필 `topic_cooldown_days` 안에 같은 주제(유사도 0.8 이상)는 다시 쓰지 않는다.
- **교차 중복**: 다른 블로그의 이력 제목과 유사도 `other_blogs`(0.6) 이상이면 주제·제목 모두 탈락. (Chance 이력은 문자열·객체 혼합이라 `state.entry_titles`가 모두 처리한다.)
- **멱등 게시**: 게시 재시도 전에 같은 제목 글이 방금 올라갔는지 확인한다(응답만 실패한 경우의 중복 방지).
- **원자적 쓰기**: 임시 파일에 쓰고 교체한다. 손상된 이력은 읽지 못하면 실행을 멈춘다.
- **동시성**: 블로그마다 `concurrency: blogger-<key>`, 매트릭스는 `max-parallel: 1`, push는 `pull --rebase` 후 최대 3회 재시도.
- **시간**: 내부는 UTC aware, 날짜 경계는 KST, cron은 UTC.

## 6. 시크릿 전달 방식

레지스트리에는 역할별 **Secrets 이름**만 있다. 워크플로가 `secrets[matrix.secret_<역할>]`로 값을 읽어 `PIPELINE_SECRET_<ROLE>` 환경변수로 넘기면 러너가 그 값을 쓴다(`registry.resolve_secrets`). 로컬 수동 실행은 레지스트리에 적힌 이름(`BLOGGER_BLOG_ID` 등)을 그대로 읽는다. 그래서 **블로그를 추가해도 워크플로를 고치지 않는다.**

## 7. 블로그 추가 플레이북

### A. 같은 플랫폼(Blogger) 블로그 추가 — 채널 워크플로 필요(`channel` 규칙, §3)

채널(`channel.label`)은 블로그마다 달라야 하고 그 블로그 워크플로의 `name` 접두사와 같아야 하므로, **지금처럼 `blogger.yml` 하나를 여러 Blogger 블로그가 나눠 쓰는 것은 두 번째 블로그부터 레지스트리 검증이 막는다**(`Blogger 영문`·`Blogger 한글`처럼 채널을 나누려면 `blogger.yml`을 재사용 워크플로로 바꾸고 채널마다 얇은 래퍼 워크플로를 두는 작업이 먼저 필요하다 — 한글 Blogger 등록 작업의 몫이다). 아래 표는 그 워크플로가 준비된 뒤의 절차다.

| # | 누가 | 할 일 |
|---|------|-------|
| 1 | 사용자 | Blogger 블로그 생성, 블로그 ID 확인, Google OAuth 클라이언트 준비(**동의 화면 "프로덕션"** — 테스트 상태는 7일 후 토큰 만료, D-11), refresh token 발급 |
| 2 | 사용자 | GitHub Secrets 등록: 블로그 전용 이름 4종(예: `BLOGGER2_BLOG_ID`, `BLOGGER2_CLIENT_ID`, `BLOGGER2_CLIENT_SECRET`, `BLOGGER2_REFRESH_TOKEN`). LLM 키는 `GEMINI_API_KEY` 공유 |
| 3 | AI (T3 승인 후) | `blogs.json`에 항목 추가: **`mode`를 항목에 직접 적는다**(예: `"draft"`. 적지 않으면 검증기 `REG-1` 오류 — `defaults.mode`를 물려받은 새 블로그가 의도하지 않은 모드로, 예를 들어 기본값이 `auto`일 때 시크릿 등록만으로 바로 자동 게시되는 일을 막는다), 고유 `key`, **`channel`**(채널 라벨 — 그 블로그 워크플로 `name`의 `[라벨]` 접두사와 같은 글자, §3), `secrets` 이름, `state`(전용 history·content_dir), 프로필·프롬프트, **`ads`는 적지 않거나 `off`**(신규 채널은 품질 게이트를 통과하기 전까지 광고 없이 시작한다, §3 '광고 선언') |
| 4 | AI | `python -m pipeline.registry` · `python scripts/validate_repo.py` · `python -m unittest discover -s tests` |
| 5 | AI/사용자 | Actions → `[Blogger] 글 자동 작성(초안함 업로드)` → Run workflow(`blog=<key>`, `연습 실행` 체크 해제, `publish=draft`)로 Blogger 초안함에서 글 확인(체크를 풀면 실제 Gemini로 초안을 만들어 저장소에 커밋한다. 시크릿을 등록하기 전이면 `publish=off`로 저장소 초안만) |
| 6 | 워치독 | `draft` 상태로 3일 이상 운영하며 `rejected`·실패 이슈가 없는지 본다 (카나리) |
| 7 | 사용자 | `mode: "auto"` 전환 승인(T3) |

블로그 언어가 기존 프로필과 다르면(예: 영문) 3단계의 프로필·프롬프트·스텁을 §7-1의 체크리스트로 새로 만든다. 글 언어 검사·주제 가드레일 목록·시드·시험이 언어마다 필요하다. 블로그의 `languages`에 프로필의 `language`가 없으면 검증기가 오류로 막는다(D-32 재발 방지).

### B. 새 플랫폼(WordPress, Tistory, Medium, 다른 Jekyll 저장소 등)

1. **정책 확인(T3)**: 해당 플랫폼 약관이 자동 게시를 허용하는지, 계정·API 방식이 무엇인지 사용자와 확정한다.
2. `registry.PLATFORMS`에 필수 시크릿 역할을 등록한다.
3. `pipeline/publishers/<platform>.py`에 어댑터를 만든다. 계약: `healthcheck()`, `publish(title, html, labels, draft)`, 인증 실패와 API 오류의 `PublishError(code)` 구분, **재시도 전 중복 확인**, 오류 메시지 시크릿 마스킹, `service_factory` 주입으로 가짜 서비스 테스트.
4. `pipeline/run.py`의 플랫폼 분기를 확장한다(현재는 `blogger`만 — Phase 2에서 어댑터 레지스트리로 일반화).
5. 이후 A의 3~7단계.

### C. 또 하나의 Jekyll(git) 블로그

`jekyll-git` 어댑터와 공용 엔진이 필요하다(Phase 3). 그 전에는 `generator.py`를 복사하지 않는다.

## 7-1. 프로필(콘텐츠 정책)과 주제 가드레일

블로그마다 프로필 하나(`pipeline/profiles/<이름>.json`)가 "무엇을 어떤 기준으로 게시하는가"를 정한다. 레지스트리의 `profile`이 가리키고, 정규식은 Python `re`로 **대소문자를 무시**해 검사한다. 같은 성격의 블로그는 프로필을 재사용하고, 언어가 다르면 같은 구조의 프로필을 새로 만든다. 지금은 영문 `blogger_practical_en`(macat0722, 모드 off)과 한국어 `blogger_practical_ko`(쓰는 블로그가 없다 — 새 한글 Blogger가 재사용할 예정)가 있다.

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
| `body_clause_split_patterns` | (선택) 문장을 절로 쪼개는 접속어·연결 어미(영어 `, but`·`, so`·`, though`·`, and`+새 절, 쉼표 없이도 `so`·`or`·`because`·`unless you` 등 + 상담 구절, 한국어 `~지만`·`~하되`·`~는데`·`~서`·`그러므로`…). `;` `:` `—` `--`와 띄어 쓴 하이픈은 모든 언어에 공통이라 코드에 있다. 상담 구절이 없는 절은 면제되지 않는다. 패턴마다 따로 컴파일한다(`(?i)`·같은 이름의 묶음도 된다) | 6개 | 7개 |
| `body_safe_veto_patterns` | (선택) 상담·면책 구절이 있어도 **면제하지 않는** 표현 — 용량(`400 mg`·`0.4 g`·`10,000 units`·`2 capsules`·`a 400-mg tablet`·`four hundred milligrams`, 한국어 `밀리그램`·`2알`·`두 캡슐`) | 2개 | 2개 |
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
| 영어 접속어 + 상담 구절(**쉼표는 있어도 없어도 된다**) | 프로필 `body_clause_split_patterns` | `so ask your doctor`·`or ask…`·`because/since/as…`·`unless you ask…`·`otherwise/therefore/thus/hence/plus…`·`which is why you should talk to…`·`meaning you can ask…`·`and make sure to ask…` — 접속어 바로 뒤에(또는 `you should`·`make sure to`·`it is wise to` 같은 도입구 뒤에) 상담 동사 `talk to`·`speak with`·`check with`·`consult`·`ask`와 전문가 낱말이 올 때만 가른다. `see`·`call`·`visit`·`contact`·`seek`은 인과·순서 접속어(`so`·`then`·`because`·`unless`…)와 쓰일 때만 가른다 |
| 한국어 연결 어미 | 프로필 `body_clause_split_patterns` | `~지만`·`~하되`/`~드시되`·`~는데`·`~으나`·`~면서`·`~으며`·`~니까`, `, 그러나/하지만/다만…`, `~고`·`~고,` 뒤에 상담 구절이 이어질 때, 괄호 안의 상담 구절(`(먼저 의사와 …)`) |
| 한국어 접속 부사·`서` 어미 | 프로필 `body_clause_split_patterns` | `, 그러므로/그러니/그러니까`, `~서`(`돼서`·`그래서`·`따라서`·`고 나서`) 뒤에 상담 구절이 이어질 때. 장소의 `에서`(`병원에서 의사와 …`)는 가르지 않는다 |

③ 절마다 `body_safe_patterns`에 맞으면 위험 낱말을 건너뛴다. ④ 다만 `body_safe_veto_patterns`(용량: `400 mg`·`5000 IU`·`400mg`·`밀리그램`에 더해 `0.4 g`·`10,000 units`·`2 capsules`·`a 400-mg tablet`·`four hundred milligrams`, 한국어 `2알`·`두 캡슐`)에도 맞는 절은 **건너뛰지 않는다** — 용량을 적은 글은 상담 구절이 있어도 막는다("Ask your doctor whether 400 mg of magnesium is right for you."). 면제 취소는 면제를 거두는 것뿐이라 그 절에 막는 낱말(`supplements`·`melatonin` 등)이 있을 때 막힌다. 용량 낱말 자체를 막는 목록(`banned_*`의 `mg`·`IU` 패턴)은 넓히지 않았다 — `Take 400 milligrams of magnesium before bed.`는 상담 구절도 막는 낱말도 없어 통과한다(D-64 ⑦ N-3). 프롬프트도 용량을 쓰지 말라고 한다.

계속 통과하는 것: 질환·임신·약을 이름 붙인 정상 상담 안내는 한 절이라 그대로 면제된다(운영자 결정 3번) — "If you are pregnant, talk to your doctor before changing your routine.", "Check with your doctor before trying a new supplement routine.", "임신 중이거나 약을 복용 중이라면 의사와 상담한 뒤 시작하세요." 쉼표로 나열한 병명("asthma, diabetes, and high blood pressure")은 `, and` 뒤가 새 절이 아니라서 가르지 않고, 낱말 안의 하이픈(`well-known`)·범위(`2-3`)도 가르지 않는다. 효능 단정(`banned_patterns`)은 절 단위 면제와 무관하게 늘 막는다.

**알려진 과잉 차단(트레이드오프)**: 병명·임신을 이름 붙인 절과 상담 구절이 접속어·문장부호로 나뉜 정상 안내도 이제 막는다 — "Pregnancy can change your needs, so talk to your doctor.", "If you have a health condition—such as diabetes or high blood pressure—talk to your doctor …", "Who should check with a doctor first: pregnant women, people with diabetes …", "Some people take supplements; if you do, talk to your doctor first.", "임신 중에는 몸 상태가 달라질 수 있으니 의사와 상담하세요." 이 문장들은 독립 검증이 막으라고 한 "Vitamin D supplements may lower your blood pressure, so ask your doctor."와 모양이 같아(위험 낱말이 든 절 + 접속어·문장부호 + 상담 절) 구조로는 가를 수 없다. 모델이 쓸 법한 상담 안내 40문장(영어 30·한국어 10)으로 재 보면 막히는 문장이 옛 main 2개에서 7개로 늘었다. 같은 뜻을 한 절로 쓰면 통과하고(`, such as …,`·`Because pregnancy can change your needs, talk to your doctor.`·`~ 수 있어 의사와 상담하세요`), 영어 프롬프트가 질환·임신을 쓰지 말라고 하므로 실제 빈도는 낮을 것이다. 막히면 걸린 낱말이 재시도 사유로 돌아가 모델이 그 문장을 뺀다. 풀려면 `gates._CLAUSE_PUNCTUATION`(`—`·`:`·`;`)과 프로필 `body_clause_split_patterns`(`, so`·`으니`)에서 경계를 빼면 되지만, 그러면 검증자의 문장도 통과하므로 운영자·총괄의 결정이다. 시험 `STRICT_TRADE_OFF_*`가 지금의 결정을 고정한다. 쉼표 없는 접속어와 도입구까지 닫은 2차 보강(D-64 ⑦ N-1)도 같은 값을 치른다 — 검증자의 정상 안내 표본(영어 42·한국어 15)에서는 새로 막히는 문장이 0개지만, 내가 쓴 정상 안내 68문장(영어 47·한국어 21)에서는 14문장이 새로 막힌다("Medication can interact with food, which is why you should talk to your doctor."·"Do not start any new supplement unless you check with your doctor first."·"People with asthma can then ask their doctor about stretching."·"Pregnant women should rest and then check with their doctor …"·"Pregnant women should rest, otherwise check with their doctor."·"임신 중이라서 의사와 상담이 필요해요."·"혈압이 걱정돼서 병원을 방문하세요." 등 — 측정에 쓴 표본은 저장소 밖이고, 대표 문장만 `STRICT_TRADE_OFF_*`로 고정한다).

**한계**: 쉼표만으로 이은 상담 구절은 여전히 면제된다 — 쉼표 이음("Magnesium supplements help you sleep, talk to your doctor first.")·`, please`·`, just`·`, also`·`, of course,`·`, if you want,`·`, remember to`·`, be sure to`·`, make sure to`·한국어 `~는 점, 의사와 …`, 그리고 꼬리 구절("…, after checking with your doctor"). 쉼표 뒤 명령형을 경계로 삼으면 정상 안내 "If you are pregnant, talk to your doctor"가 깨져서 일부러 그렇게 두었다(시험 `ConnectorGridTest`가 이 목록을 고정한다). 상담 구절이 앞에 오고 위험한 권유가 쉼표 없는 `and try …`·`, and many people find …`로 뒤따르는 문장도 이번에는 가르지 않았다. `, then` 조건문("If you are pregnant, then check with your doctor first.")과 "stop and consult"처럼 정상 안내가 막히는 과잉 차단은 고치지 않았다 — 첫 실제 영어 초안의 `BODY_TOPIC` 빈도를 보고 정한다(D-64 ⑦ N-2). 한 문단 안에서 줄을 바꿔 쓴 문장은 줄바꿈이 문장 경계라 두 낱말 용어가 줄 끝에서 갈리면(`blood⏎pressure`) 놓친다. 한 문장에 다른 언어의 낱말이 섞이면(영문 글의 `당뇨`) 그 프로필의 목록으로는 걸리지 않는다 — 언어 게이트는 영문 글에서 라틴 문자가 90% 미만일 때(한국어 글은 한글이 50% 미만일 때)만 막으므로 낱말 한두 개는 지나간다.

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

권장대로 한국어 프로필(`blogger_practical_ko`)에도 같은 가드레일을 적용했다. 근거: ① 위험(YMYL)·광고 계정·파이프라인이 같아 언어에 따라 안전선이 달라질 이유가 없다. ② 지금 한국어 프로필을 쓰는 블로그가 없어(macat0722는 영문으로 전환, 새 한글 Blogger는 계획) 운영 중인 흐름이 바뀌지 않는다. ③ 적용 전후로 확인했다 — 기존 시험이 `make_root`(임시 저장소가 영문 항목을 한국어 프로필·프롬프트로 바꿔 쓰게 함) 외에는 수정 없이 통과하고, 한국어 시드 32개·스텁 글·실제로 생성돼 이력에 남은 제목 5개·본문 5편이 새 제목·본문 검사를 통과한다. ④ 이 확인에서 **오탐 1건**을 찾아 고쳤다: 실제 생성 글의 "딱 3분만 투자해서"가 `자해`(자기 해침)와 겹쳐 본문 검사에 걸렸다. 한국어 낱말은 어절 중간 일치가 흔해서, 주제 목록의 `자해`를 `(?<![가-힣])자해`(앞에 한글이 없을 때만)로, `주사`를 `주사(?!위)`(주사위 제외)로 고쳤다. 이 목록이 제목·라벨에도 걸리게 됐기 때문에(제목 "3분 투자해서 …"는 흔하다) 필요한 수정이고, 걸리지 않게 된 것은 `비자해`처럼 실제로 쓰지 않는 합성어뿐이다. ⑤ 목록을 28개에서 56개로 늘린 보강(D-64 ⑥ b·f)도 같은 방식으로 확인했다 — 실제로 생성된 글 5편의 제목·라벨·주제와 본문 문장 40개, 한국어 일상 문장 20개, 독립 검증이 쓴 한국어 32문장에서 오탐이 0건이다(`간 건강`은 `시간 건강`과, `단식`은 `간단식`과 겹치지 않게 앞에 한글이 없을 때만 막는다).

### 영어 시드(34개)

한국어 시드 32개 중 30개의 영어판(2개는 뺐다: 야식 충동·간식 기준 — 체중 관리·영양 주장으로 흐르기 쉽다. '잠이 안 올 때'는 문제 틀을 빼고 '자기 전 진정 루틴'으로, '운동·소화·비 오는 날 기분·피곤할 때 에너지'는 의학적 해석을 부르는 낱말을 풀어 다시 썼다)과 새 시드 4개(책상 정리·채소 더하기·주간 플래너·습관 쌓기). 생활 습관·수면 위생·책상 자세·산책·정리·식사 계획·스트레칭처럼 **의학적 주장이 필요 없는** 주제만이다. 영어는 같은 뜻이 더 길어서 35~55자(주제 길이 한도는 8~60자)다. 모든 시드는 레지스트리 검증과 시험에서 금지 주제 목록을 통과해야 하고, 시드마다 영어 스텁 글이 게이트 전체를 통과하는지, Chance 영·한 제목·한국어 이력과의 제목 유사도가 교차 중복 한도(0.6) 아래인지(측정한 최댓값 0.50)도 시험이 본다.

### 새 언어·새 블로그 프로필 체크리스트

1. 가장 가까운 프로필 JSON을 복사해 `name`·`language`·비율 필드·길이·목록·시드·`disclosure_html`·`prompt_extra`·`topic_expand_prompt`와, 본문 가드레일을 쓰면 `body_clause_split_patterns`(그 언어의 접속어·연결 어미)·`body_safe_veto_patterns`(용량 표기)를 그 언어로 만든다. 목록은 이 절의 대응표를 기준으로 낱말·굴절형을 정하고, 정규식에는 단어 경계를 둔다.
2. 새 `language` 값이면 `pipeline/gates.py`의 `SUPPORTED_LANGUAGES`와 `check_post`의 글 언어 검사에 그 언어를 더한다(현재 `ko`·`en`).
3. 프롬프트 파일(`.github/editorial/…`)을 만든다: `text` 코드 블록 안에 `{topic}`(영어는 줄 맨 앞 `Topic: {topic}`)과 출력 형식. 머리표는 `제목:/라벨:/내용:` 또는 `Title:/Labels:/Content:`(`gates._MARKER_SETS` — 새 머리표는 여기에 더한다).
4. `pipeline/stubs.py`가 그 언어의 글을 내도록 한다. 안 그러면 연습 실행(`--dry-run`·`연습 실행`)이 한국어 가짜 글로 언어 검사에서 탈락한다.
5. 시험: `tests/test_guardrails.py`의 막힘·통과 표본(부분 문자열 오탐 포함)을 새 언어로, 시드·스텁 통과, 임시 저장소(`make_root`)에서 가짜 LLM으로 한 편(통과·탈락·재작성).
6. `python -m pipeline.registry` → `python scripts/validate_repo.py` → `python -m unittest discover -s tests`. 레지스트리에는 `mode`를 직접(`off`로) 적는다.

**알려진 한계**: `pipeline/run.py`의 `build_prompt`가 `[추가 규칙]`·`[이전 시도에서 고쳐야 할 점]` 머리글을 한국어로 붙이고 탈락 사유도 한국어라, 영문 블로그의 프롬프트는 영어 본문에 한국어 머리글이 섞인다(모델은 이해하지만 영어로 통일하려면 `run.py`를 고쳐야 한다 — 범위 밖으로 남겼다, D-64 ③). 영어 글의 제목·라벨 중복 검사(`DUP_SAME`·`DUP_OTHER`)는 Chance 영어 제목과 한국어 이력에 그대로 쓰며(문자열 비교라 언어가 달라도 동작하고 영·한 사이는 거의 겹치지 않는다), 영어 제목은 같은 틀("5 Simple Ways to …")이 반복돼 같은 블로그 안 유사도(0.72)에 걸릴 수 있다.

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
| 수정 요청은 구조화된 이슈 양식 + 문자 그대로 교체 + PR | 비개발자의 자유 문장 요청을 AI가 해석하면 요청 밖을 고치거나 일부만 읽고 추정할 수 있다(D-14). 양식으로 대상·수정 항목을 고정하고, 가능한 곳은 AI 없이 교체하며, 결과는 기계 검사 후 사람이 병합 | 한 요청은 한 파일만. AI 패치(`layout`, 변경 전이 없는 `text_change`)는 범위만 증명하고 내용의 정확성은 사람이 본다 |
