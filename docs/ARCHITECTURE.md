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
  수정 요청: 이슈 양식 ─► pipeline/edits(명세 범위 안에서만) ─► PR ─► 범위 검사(PR 변경 범위 검사) ─► 사람이 병합
```

설계 원칙은 세 가지다. ① **설정과 코드를 분리**한다(블로그 = 레지스트리 항목). ② **게시 전 게이트는 플랫폼과 무관**하게 한곳에 둔다. ③ **플랫폼 차이는 어댑터 안에** 가둔다.

## 2. 현재 상태 (2026-10-20 검증)

| 구성 | Chance_Blog (`chance`) | Blogger (`blogger_macat`) |
|------|------------------------|---------------------------|
| 엔진 | `generator.py` — 레거시 단일 파일. Phase 3에서 `pipeline/`으로 이관 | `python -m pipeline.run --blog blogger_macat` (`blogger_generator.py`는 호환 래퍼) |
| 트리거 | `chanceblog.yml` 매시 17분(KST 9·18시 슬롯을 코드가 판단), 수동 (이슈 요청은 `issue-edit.yml`이, 기존 글 이미지 교체는 수동 전용 `chance-fix-images.yml`이 따로 처리) | `blogger.yml` 매일 02:00 UTC(KST 11시), 수동 |
| 주제 | Google News RSS, 신뢰 도메인 허용 목록, 36시간 이내, 출처 원문 검증 | 프로필 시드 32개 + LLM 확장, 쿨다운 60일, 금지 주제 필터, Chance 이력과 교차 중복 방지 |
| 생성 | Gemini 모델 폴백, KR/EN 쌍, 편집 템플릿 | Gemini 모델 폴백 + 일시 오류 재시도, 형식 엄격 파싱 |
| 게이트 | `validate_post_data`(길이·인라인 출처), 제목 유사도 | `pipeline/gates.py`(파싱·HTML 정화·정책·중복), 탈락 사유를 넣어 최대 3회 재작성 |
| 게시 | git 커밋 → Pages 배포(`pages.yml`). 봇 커밋 뒤 `gh workflow run pages.yml`로 배포 실행 | Blogger API 어댑터(멱등 재시도, 인증 실패 구분) |
| 상태 | `history.json`(문자열·객체 혼합 스키마) | `blogger_history.json`(스키마 v1, §5) |
| 관측 | Actions 로그 | 실행 요약 + 이력 status + 워치독 |
| 수정 요청(이슈) | `issue-edit.yml` + `pipeline/edits`: 이슈 양식 → 문자 그대로 교체·링크·SEO·이미지(AI는 최소 패치·검색어만) → 사후 검증 → PR. 상세 [`ISSUE_EDITS.md`](./ISSUE_EDITS.md) | 해당 없음(Blogger 글은 Blogger 관리 화면) |
| 상태(운영) | 운영 중. 단 슬롯 시각이 된 실행 13회 중 2회만 글이 나왔다(D-03: 분야 폴백·사유 기록으로 완화, 병합 뒤 관측). 이슈 수정은 `pipeline/edits`로 재구축(D-01, Actions 관측 대기) | 코드 완료. refresh token 미발급, 첫 실행 전(D-11) |

공통: 워치독 일 1회(`watchdog.yml`), 저장소 가드레일 CI(`guardrails.yml`), 레지스트리 검증(`python -m pipeline.registry`), PR 범위 검사(`pr-scope-check.yml`, 이슈를 참조하는 모든 PR).

### 2-1. GitHub Actions 탭의 이름 (2026-10-25 기준)

Actions 왼쪽 목록의 이름은 **이름만 보고 자동인지 수동인지, 무엇을 하는지 짐작할 수 있게** 한글로 지었다. 파일 이름(`*.yml`)은 그대로이고(레지스트리·워치독·문서가 파일 이름으로 가리킨다) 화면에 보이는 `name`만 바뀌었다. 실행 목록의 제목(`run-name`)에는 정기/수동·연습 여부(이슈 처리는 이슈 번호)가 붙는다. 새 워크플로·job의 이름도 한글로 짓는다(검증기 **WF-11**, [`ENGINEERING_GUIDE.md`](./ENGINEERING_GUIDE.md) W10).

| 옛 이름 | 새 이름 (Actions 탭) | 파일 | 하는 일 | 자동/수동 |
|---------|----------------------|------|---------|-----------|
| Chance_Blog Full-Auto Engine | `Chance 글 자동 작성·게시` | `chanceblog.yml` | 뉴스 기사를 바탕으로 Chance 글(한국어·영어)을 만들어 검증하고 저장소에 커밋해 게시 | **자동**(매시 17분 UTC에 실행, 게시 시각은 코드가 판단) + 수동 실행(연습이 기본). 실행 제목 `Chance 글 작성·게시 · 정기/수동` |
| (`chanceblog.yml`의 `fix_images` 입력) | `Chance 기존 글 이미지 교체(수동)` | `chance-fix-images.yml` | 기존 글의 깨진·누락·중복 이미지만 교체(새 글은 만들지 않음). 2026-10-25에 글 작성 워크플로에서 분리 | **수동 전용**(연습이 기본) |
| Blogger Generate | `Blogger 글 자동 작성` | `blogger.yml` | 레지스트리의 Blogger 블로그마다 글을 만들고 검증해 초안 저장 또는 게시(블로그 모드에 따름) | **자동**(매일 02:00 UTC = KST 11시) + 수동 실행. 실행 제목 `Blogger 글 작성 · 정기/수동(…)` |
| Deploy GitHub Pages | `사이트 자동 배포` | `pages.yml` | Chance 사이트(GitHub Pages)를 빌드해 게시 | **자동**(main에 push될 때. 봇이 커밋한 뒤에는 `Chance 글 자동 작성·게시`·`Chance 기존 글 이미지 교체(수동)`가 직접 실행을 요청) + 수동 |
| Guardrails | `저장소 규칙·테스트 자동 검사` | `guardrails.yml` | 비밀 유출·워크플로 보안 규칙·문서 불일치·광고 표면 변경 검사, 단위 테스트, `actionlint` | **자동**(main push·모든 PR) + 수동. job 이름 `검사 (Python 3.10/3.12)` |
| Watchdog | `발행 중단 감시·알림` | `watchdog.yml` | 글이 오래 안 올라오거나 실패가 이어지면 `[Watchdog]` 이슈로 알림(문제일 때만, 해소되면 닫음) | **자동**(매일, 시각은 `watchdog.yml`의 cron) + 수동. 실행 제목 `발행 중단 감시 · 정기/수동` |
| Issue Edit | `이슈 수정 요청 처리(수정안 PR 만들기)` | `issue-edit.yml` | 이슈 양식으로 접수된 수정 요청을 검증해 수정안을 PR로 만든다(main에 직접 반영하지 않음) | **자동**(제어 이슈가 열릴 때) + 수동(이슈 번호 입력, 연습이 기본). 실행 제목 `이슈 #번호 수정 요청 처리 · …` |
| PR Scope Check | `PR 변경 범위 검사` | `pr-scope-check.yml` | 이슈를 참조하는 PR(Copilot·사람)이 요청 범위를 지켰는지 검사해 PR에 코멘트 | **자동**(PR이 열리거나 갱신될 때) + 수동(PR 번호 입력) |
| Sync Issue Form | `이슈 양식 페이지 목록 갱신` | `sync-issue-form.yml` | `pages.json`과 이슈 양식의 '대상 페이지'·'수정 항목' 드롭다운을 최신으로 갱신 | **자동**(관련 파일이 main에 push될 때) + 수동 |
| (GitHub 내장) | `pages-build-deployment` | 파일 없음 | GitHub Pages가 스스로 만들어 목록에 보일 수 있는 실행. 이름을 바꿀 수 없다. **누르지 않는다**(배포는 `사이트 자동 배포`) | GitHub 내장 |

기본 제목(커밋 메시지·PR 제목)이 더 알려 주는 `사이트 자동 배포`·`저장소 규칙·테스트 자동 검사`·`PR 변경 범위 검사`·`이슈 양식 페이지 목록 갱신`은 `run-name`을 따로 두지 않았다. 정기·수동·연습은 `Run workflow` 대화상자 입력(`연습 실행` 체크)과 실행 제목으로 구분한다.

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
| `mode` | `off` 중지 · `draft` 초안만 · `auto` 자동 게시. **`auto` 전환은 T3** |
| `workflow`, `entrypoint`, `prompt` | 저장소에 존재하는 파일. `workflow`의 cron이 `schedule.cron`과 같아야 한다(검증기 REG-2) |
| `profile` | `pipeline/profiles/<이름>.json`. `blogger` 플랫폼은 필수 |
| `state.history`, `state.content_dir` | 이력 파일, 산출물 폴더(저장소 상대 경로, `..` 금지) |
| `schedule.cron` | 워크플로 cron과 동일. `slots_kst`는 참고 |
| `limits.max_posts_per_day` | 1~24. 하루 상한(KST 날짜 기준). 수동 `--topic`은 우회 |
| `llm.models`, `llm.max_retries` | 모델 폴백 순서, 일시 오류 재시도 횟수 |
| `secrets` | `{역할: 환경변수(=Secrets) 이름}`. **값은 절대 쓰지 않는다.** 플랫폼별 필수 역할은 `registry.PLATFORMS` |
| `ad_surface`, `protected_paths` | 광고(AdSense) 심사·수익 대상인지, 승인 없이 못 바꾸는 경로(`/`로 끝나면 폴더) |
| `health` | 워치독 기준: `max_gap_hours`, `max_failure_streak`, `max_unpublished_days` |

시크릿 이름은 블로그마다 고유해야 하고(`shared_secrets` 예외), 값 전달은 [§6](#6-시크릿-전달-방식)을 따른다.

## 4. 단계별 계약

| 단계 | 입력 → 출력 | 실패 시 |
|------|-------------|---------|
| **Plan** | 레지스트리 → 매트릭스(`python -m pipeline.plan --platform P [--only KEY]`) | 레지스트리 검증 실패 → 워크플로 중단(종료 코드 1) |
| **Topic** | 프로필 시드·이력·타 블로그 제목 → 주제 1개 | 없으면 `skipped_no_topic` 기록 후 정상 종료. 쿨다운·금지 주제·교차 중복 필터 통과 필수 |
| **Generate** | 프롬프트 + 프로필 추가 규칙 → 원문 | LLM 전부 실패 → `llm_failed` 기록, **종료 코드 1**(Actions 실패 알림) |
| **Gate** | 원문 → 파싱 → HTML 정화 → 정책·중복 검사 | 탈락 사유를 넣어 재작성(최대 `max_attempts`). 끝내 탈락이면 `rejected` 기록, 게시·저장 없음, 정상 종료 |
| **Publish** | 정화된 HTML + 면책 문구 → 어댑터 | 인증·API 오류 → `publish_failed` 기록, **종료 코드 1**. 초안은 남긴다 |
| **Record** | 이력 항목 추가(최근 200개 유지) + 초안 파일 저장(최근 120개) | 이력 파일이 손상돼 있으면 **덮어쓰지 않고** 종료 코드 1 (fail closed) |
| **Deploy** | (`jekyll-git`) 커밋 push 후 `pages.yml` dispatch | dispatch 실패 시 워크플로 실패 |
| **Observe** | 워치독: 이력·마지막 커밋·최근 실행 → `[Watchdog]` 이슈 | 이슈 생성/자동 해소 |

종료 코드: `0` 정상(건너뜀 포함) / `1` 인프라 실패 / `2` 설정 오류.

## 4-1. 건너뜀·종료 규약 (스킵 코드)

"할 일이 없어서", 또는 "조건이 안 맞아서" 끝나는 실행도 **왜** 끝났는지 남긴다. 초록 체크는 "프로그램이 오류 없이 끝났다"는 뜻일 뿐 "글이 올라갔다"는 뜻이 아니기 때문이다(2026-10-25 진단: Chance는 슬롯 시각이 된 스케줄 실행 13회 중 11회가 글 없이 초록으로 끝났고, Blogger는 게시 시크릿이 없어 초안만 만든 채 초록이었다).

한 줄 규격: `[SKIP] code=<코드> key=값 ...` — Actions 로그에서 `[SKIP]`로 찾고, 같은 코드가 실행 요약(Step Summary)에도 쓰인다.

| 수준 | 의미 | 처리 | 종료 | 코드 |
|------|------|------|------|------|
| 정상 건너뜀 | 지금 할 일이 아님 | 초록 + 로그 한 줄 | 0 | `OUT_OF_WINDOW`(첫 게시 시각 전), `ALREADY_PUBLISHED`(그 슬롯 글이 이미 있음), `PAUSED`(`PIPELINE_PAUSE`), 예정: `DAILY_CAP`·`MODE_OFF`·`DRY_RUN` |
| 경고 | 게시하려 했는데 못 했지만 다음 실행에서 다시 시도 | 초록 + `::warning::`(노란 주석) + 요약 | 0 | `ALL_REJECTED`(후보는 있었으나 Gemini 건너뜀·제목 유사·본문 검증 탈락으로 전부 탈락. 수동 실행은 예외로 빨강), `ALL_DUPLICATES`(검증된 기사는 있었지만 모두 이미 쓴 글과 비슷 — 뉴스가 뜸한 때), `NO_CANDIDATES`(시간 상한으로 일부 분야만 시도하고 후보 없음), `NO_MATCH`(수동 주제 요청과 연결되는 검증된 기사 없음) |
| 실패 | 발행하려던 실행이 0건으로 끝난 이상 신호 | **빨강** + `::error::` + 요약 | 1 | `ALL_LANES_EMPTY`(모든 분야에 검증을 통과한 기사가 한 건도 없음), `SOURCES_UNREACHABLE`(시도한 뉴스 소스가 모두 수집 실패 — 네트워크·소스 장애), 예정: `SECRETS_MISSING`·`AUTH_*`·`LLM_FAILED` |

위 코드는 **실행 전체의 결과**다. 분야 하나가 비었을 때는 폴백으로 다음 분야로 넘어가기 전에 `[SKIP] code=LANE_EMPTY lane=… sources=… failed=… fetched=… passed=… reasons=…` 한 줄을 남겨 왜 비었는지(소스 수, 수집 실패 수, 받은 기사 수, 통과 수, 탈락 사유 개수)를 알 수 있게 한다. 폴백으로 정상 발행한 실행에도 이 줄이 찍히므로 로그 검색은 `code=LANE_EMPTY`(분야 단위)와 실행 결과 코드를 구분해서 한다.

**Chance 기사 탈락 사유 코드**(`generator.py` `DROP_LABELS`, 소스별 `소스 X: N건 중 M건 사용 (탈락: …)` 줄과 요약 표에 같은 코드):

| 코드 | 뜻 |
|------|----|
| `NO_TITLE` | 제목 없음 |
| `NOT_TECH` | 기술 키워드가 아님(`tech_filter` 소스만) |
| `AGE` | 36시간 초과 |
| `UNTRUSTED` | 게시자가 그 분야의 신뢰 목록(`TRUSTED_SOURCE_DOMAINS`)에 없음 |
| `UNCHECKED` | 소스당 5건 검사 한도를 넘어 검사하지 않음 |
| `UNRESOLVED` | Google 뉴스 링크에서 게시자 원문 주소를 얻지 못함 |
| `HOST_MISMATCH` | 게시자와 원문 주소의 사이트가 다르거나 원문이 신뢰 목록 밖 |
| `SHORT_SUMMARY` | 요약이 100자 미만(원문 발췌도 실패) |
| `DUPLICATE` | 기존 글과 제목이 비슷(후보 단계) |

요약 표의 '검증 통과'는 소스당 10건 상한·소스 간 같은 제목 병합·`DUPLICATE` 제거를 하기 **전**의 수이고, '후보'는 그 뒤 최대 3건(`MAX_ATTEMPTS`)이다. 소스마다 '받은 기사 = 검증 통과 + 탈락 사유 합'이 성립하며, '검증 통과'가 있는데 '후보'가 0이면 전부 기존 글과 비슷했다는 뜻이다(`ALL_DUPLICATES`). 요약에는 그 실행에서 나온 코드의 뜻을 한 줄로 붙인다.

**Chance 분야 폴백**: 슬롯 시각마다 6개 분야를 확률 가중 추첨 순서(`editorial_lane_order`, 첫 분야는 기존 추첨과 같음)로 늘어놓고, 앞에서부터 후보가 나올 때까지 시도한다. 이 단계는 Gemini를 부르지 않아 비용은 수집 시간뿐이다. `LANE_SEARCH_BUDGET_SECONDS`(기본 480초)가 지나면 새 분야도, 분야 안의 남은 소스도 시도하지 않는다(이미 시작한 소스 하나는 끝까지 기다리므로 수집은 상한 + 약 2분 안에 끝나고, 잡 제한은 20분이다). 시도한 소스가 전부 수집 실패면 시간과 무관하게 `SOURCES_UNREACHABLE`(빨강)이다. 글이 만들어지면 이력의 `lane`과 Gemini 프롬프트에는 실제로 후보가 나온 분야가 쓰인다.

후보 하나가 탈락해도 실행은 계속된다: Gemini가 만든 본문이 검증(한국어 1000자·영어 1500자 이상, 검증된 원문 링크 인용)에 못 미치거나 JSON을 못 맞추면 그 후보만 탈락시키고(이미지를 고르기 전에 검사하므로 Unsplash 호출을 쓰지 않는다) 다음 후보를 시도한다(최대 `MAX_ATTEMPTS`=3건). 예전에는 첫 후보의 본문이 얇으면 실행 전체가 빨강으로 끝났다(D-36). 모든 모델이 실패하는 Gemini 장애는 그대로 빨강이다. 실행 요약에는 후보 탈락(본문 검증·응답 형식) 건수와 사유, Gemini 모델 호출 횟수(`- Gemini 호출: N회(실패 K회)`, 무료 한도를 나눠 쓰기 위한 측정값)를 남긴다.

임시 조치이며 알려진 부작용이 있다: 비기술 분야가 계속 비면(신뢰 목록·검색어 문제, D-03) 글은 사실상 기술·미래 분야에서만 나온다. 이 문제는 콘텐츠 전략 작업(운영자 요청서 3번, 저장소 밖 문서)이 주제 선정을 개편하면서 풀고, 그때 이 폴백을 대체하거나 정리한다.

## 5. 상태·멱등성·동시성

- **이력 스키마 v1**: `v`, `blog`, `date`(KST `YYYY-MM-DD`), `generated_at`(ISO, KST), `status`, `topic`, `topic_source`(`seed`·`llm`·`override`), `title`, `labels`, `url`, `post_id`, `model`, `attempts`, `reasons[]`.
  `status`: `posted` · `draft` · `generated_unpublished`(게시 시크릿 없음) · `rejected` · `publish_failed` · `llm_failed` · `skipped_no_topic`.
- **일일 상한**: `posted`·`draft`·`generated_unpublished` 건수가 `max_posts_per_day`에 도달하면 건너뛴다.
- **쿨다운**: 프로필 `topic_cooldown_days` 안에 같은 주제(유사도 0.8 이상)는 다시 쓰지 않는다.
- **교차 중복**: 다른 블로그의 이력 제목과 유사도 `other_blogs`(0.6) 이상이면 주제·제목 모두 탈락. (Chance 이력은 문자열·객체 혼합이라 `state.entry_titles`가 모두 처리한다.)
- **멱등 게시**: 게시 재시도 전에 같은 제목 글이 방금 올라갔는지 확인한다(응답만 실패한 경우의 중복 방지).
- **원자적 쓰기**: 임시 파일에 쓰고 교체한다. 손상된 이력은 읽지 못하면 실행을 멈춘다.
- **동시성**: 블로그마다 `concurrency: blogger-<key>`, 매트릭스는 `max-parallel: 1`, push는 `pull --rebase` 후 최대 3회 재시도.
- **시간**: 내부는 UTC aware, 날짜 경계는 KST, cron은 UTC.

## 6. 시크릿 전달 방식

레지스트리에는 역할별 **Secrets 이름**만 있다. 워크플로가 `secrets[matrix.secret_<역할>]`로 값을 읽어 `PIPELINE_SECRET_<ROLE>` 환경변수로 넘기면 러너가 그 값을 쓴다(`registry.resolve_secrets`). 로컬 수동 실행은 레지스트리에 적힌 이름(`BLOGGER_BLOG_ID` 등)을 그대로 읽는다. 그래서 **블로그를 추가해도 워크플로를 고치지 않는다.**

## 7. 블로그 추가 플레이북

### A. 같은 플랫폼(Blogger) 블로그 추가 — 워크플로 수정 없음

| # | 누가 | 할 일 |
|---|------|-------|
| 1 | 사용자 | Blogger 블로그 생성, 블로그 ID 확인, Google OAuth 클라이언트 준비(**동의 화면 "프로덕션"** — 테스트 상태는 7일 후 토큰 만료, D-11), refresh token 발급 |
| 2 | 사용자 | GitHub Secrets 등록: 블로그 전용 이름 4종(예: `BLOGGER2_BLOG_ID`, `BLOGGER2_CLIENT_ID`, `BLOGGER2_CLIENT_SECRET`, `BLOGGER2_REFRESH_TOKEN`). LLM 키는 `GEMINI_API_KEY` 공유 |
| 3 | AI (T3 승인 후) | `blogs.json`에 항목 추가: `mode: "draft"`, 고유 `key`, `secrets` 이름, `state`(전용 history·content_dir), 프로필·프롬프트 |
| 4 | AI | `python -m pipeline.registry` · `python scripts/validate_repo.py` · `python -m unittest discover -s tests` |
| 5 | AI/사용자 | Actions → `Blogger 글 자동 작성` → Run workflow(`blog=<key>`, `publish` 미체크)로 초안 확인 |
| 6 | 워치독 | `draft` 상태로 3일 이상 운영하며 `rejected`·실패 이슈가 없는지 본다 (카나리) |
| 7 | 사용자 | `mode: "auto"` 전환 승인(T3) |

### B. 새 플랫폼(WordPress, Tistory, Medium, 다른 Jekyll 저장소 등)

1. **정책 확인(T3)**: 해당 플랫폼 약관이 자동 게시를 허용하는지, 계정·API 방식이 무엇인지 사용자와 확정한다.
2. `registry.PLATFORMS`에 필수 시크릿 역할을 등록한다.
3. `pipeline/publishers/<platform>.py`에 어댑터를 만든다. 계약: `healthcheck()`, `publish(title, html, labels, draft)`, 인증 실패와 API 오류의 `PublishError(code)` 구분, **재시도 전 중복 확인**, 오류 메시지 시크릿 마스킹, `service_factory` 주입으로 가짜 서비스 테스트.
4. `pipeline/run.py`의 플랫폼 분기를 확장한다(현재는 `blogger`만 — Phase 2에서 어댑터 레지스트리로 일반화).
5. 이후 A의 3~7단계.

### C. 또 하나의 Jekyll(git) 블로그

`jekyll-git` 어댑터와 공용 엔진이 필요하다(Phase 3). 그 전에는 `generator.py`를 복사하지 않는다.

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
