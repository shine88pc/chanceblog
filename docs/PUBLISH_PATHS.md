# 공개 경로 전수조사와 제한 재개 잠금

> 2026-11-09 운영자 결정(일정·제한 재개): 발행 정지(`PIPELINE_PAUSE`)를 풀기 전에 **Chance 는 승인 흐름(`publish_flow: pr`), Blogger 는 초안 전용, 자동·직접 게시는 꺼짐, 하루 최대 1편, 사람 승인 없는 공개 경로 0개**가 성립해야 하고,
> 이것을 코드와 시험으로 보장하지 못하면 정지를 유지한다. 이 문서는 ① 모든 공개 경로를 조사한 표 ② 레지스트리의 **제한 재개 잠금**(`resume_lock`)이 각 경로를 어떻게 막는지 ③ 켤 때 바꿀 값 ④ 남은 위험을 적는다.
> 코드 `pipeline/publish_lock.py` · 시험 `tests/test_publish_lock.py`·`tests/test_publish_paths.py` · 변경 등급 T2(워크플로 둘은 T3 성격이라 이유를 모두 적었다).

## 쉬운 설명 — 제한 재개 잠금이란

**잠금**은 레지스트리(`pipeline/blogs.json`) 맨 위의 스위치 한 줄(`"resume_lock": true`)입니다. 이 줄이 **없거나 `false`** 이면 아무것도 달라지지 않습니다(지금 상태 — 이전과 똑같이 동작).
이 줄을 **켜면** 사람이 글을 읽고 승인(PR 병합 또는 Blogger 화면에서 직접 게시)하지 않은 글이 공개 화면에 나갈 수 있는 길이 코드로 막힙니다. 규칙을 어기는 값이 하나라도 있으면 **글을 만들지 않고 빨간 실행으로 멈춥니다**(조용히 넘어가지 않습니다):

| 켜면 | 그래서 |
|------|--------|
| Chance 는 초안 PR 로만 올라간다(`publish_flow: pr`) | 병합(= 공개)은 사람이 한다. 닫으면 폐기 |
| Blogger 두 곳은 초안함·파일로만 간다(`auto` 금지, 수동 `publish`(즉시 게시) 입력도 거절) | 공개는 Blogger 화면에서 운영자가 직접 |
| 기존 글 이미지 교체(`[Chance] 기존 글 이미지 교체(수동)`)의 실제 교체는 멈춘다(연습 실행은 저장하지 않으므로 그대로 된다) | 이미지 변경은 이슈 수정 요청(수정안 PR)으로 |
| 하루에 만드는 글은 최대 1편(정기 실행·수동 실행 모두) | 지금은 정기 실행이 슬롯 2개로 하루 2편이고 수동 실행은 상한을 따지지 않는다 |
| 승인을 기다리는 초안이 3개에 닿으면 새 초안을 만들지 않는다 | 검토가 밀리면 더 쌓지 않는다 |
| 레지스트리의 잠금 줄을 잘못 적으면(`resume_lok` 같은 오타, 대소문자·하이픈·뒤 공백, `defaults` 나 블로그 항목 안) | 줄이 없는 것과 달리 '켠 줄 알았는데 꺼져 있는' 일이 없도록 **그것도 오류로 멈춥니다** |

켜는 값 목록은 §6, 켜는 변경은 **별도 T3 병합**입니다(이 일은 레지스트리 값을 바꾸지 않았습니다).

## 1. 한눈에 보기 — 판정 요약

| 번호 | 경로 | 잠금 꺼짐(지금) | 잠금 켬 | 막는 시험(`tests/test_publish_lock.py`) |
|------|------|-----------------|---------|------------------------------------------|
| **P1** | Chance 직접 게시 — `chanceblog.yml` (`publish_flow: direct`) | **열려 있음**(승인 없이 main 에 글을 커밋·배포). 지금은 `PIPELINE_PAUSE` 로만 멈춰 있다 | 막힘: `pr` 이 아니면 '발행 흐름 확인' 단계가 실패해 뒤 단계(직접 커밋)가 하나도 돌지 않는다 | `DirectPushNeverRunsUnderTheLockTest`·`ChanceFlowLockTest`·`GeneratorMainTest` |
| **P2** | 기존 글 이미지 교체 — `chance-fix-images.yml` (수동) | **열려 있음**(공개 글을 승인 없이 고쳐 main 에 커밋) | 막힘: 실제 교체는 첫 단계에서 종료 1(연습 실행은 저장하지 않아 이 단계를 건너뛴다) + 생성기 가드가 이중으로 거절 | `DirectPushNeverRunsUnderTheLockTest`·`GuardFixImagesTest` |
| **P3** | Blogger 자동 게시 — `blogger-en.yml`·`blogger-ko.yml` → `blogger.yml` (`mode: auto`) | 닫혀 있음(두 블로그 모두 `draft`, 운영자 승인 2026-10-28). `auto` 로 바꾸면 열린다 | 막힘: `auto` 는 레지스트리 검증이 거절, 러너도 거절 | `BloggerLockTest`·`GuardRegistryRuleTest` |
| **P4** | Blogger 수동 즉시 게시 — 같은 워크플로의 수동 입력 `publish: publish` | **열려 있음**(레지스트리가 `draft` 여도 그 실행은 즉시 공개) | 막힘: 러너가 어떤 표기(`publish`·`on`·`1`·`true`·`yes`·`--publish on`)로도 거절(종료 2) | `BloggerLockTest` |
| **P5** | 워크플로 밖 — 사람·AI 가 자격 증명으로 main 에 직접 push | 열려 있음(규칙은 정책뿐: AI 는 가지를 쓴다 — `AGENTS.md`) | **막지 못함**(남은 위험, §7) | — |
| **P6** | 사이트 배포 — `pages.yml` | 경로가 아니라 **수단**: main 에 들어간 모든 것이 공개된다 | 같음. main 이 '사람이 병합한 글'과 '공개 사이트가 읽지 않는 기록'만 받게 하는 것이 P1·P2·P5 의 일이다 | `RecordFilesAreNotPublicTest`(`tests/test_publish_paths.py`) |

경로마다의 사실(어떤 파일이 무엇을 언제 어떤 권한으로 바꾸는지, 사람 승인이 있는지):

| 번호 | 경로 이름 | 파일 | 무엇을 바꾸는가 | 트리거 | 쓰기 권한 | 사람 승인(잠금 없을 때) |
|------|-----------|------|-----------------|--------|-----------|--------------------------|
| P1 | Chance 직접 게시 | `chanceblog.yml`(+ `generator.py`) | 글 두 편(`_posts`)·이력을 main 에 커밋하고 배포를 요청 → 몇 분 안에 공개 | 정기(매시 17·47분 UTC) + 수동(연습이 기본) | contents·actions·pull-requests 쓰기 | **없음** |
| P2 | 기존 글 이미지 교체 | `chance-fix-images.yml` | 기존 공개 글의 이미지·출처 줄을 고쳐 main 에 커밋하고 배포를 요청 | 수동 전용(연습이 기본) | contents·actions 쓰기 | **없음** |
| P3 | Blogger 자동 게시 | `blogger-en.yml`·`blogger-ko.yml` → `blogger.yml` | `mode: auto` 이면 만든 글을 Blogger API 로 즉시 공개 게시(기록·초안 파일은 main 에 커밋) | 정기(영문 02:00·한글 03:30 UTC) + 수동 | contents 쓰기 + Blogger 게시 시크릿 | **없음**(auto 일 때) |
| P4 | Blogger 수동 즉시 게시 | 같은 워크플로의 수동 입력 `publish: publish` | 레지스트리 `mode` 와 무관하게 그 실행의 글을 즉시 공개 | 수동(입력으로 고를 때만, 기본은 `draft`) | 같음 | **없음**(운영자가 누르지만 글을 읽고 승인하는 단계가 없다) |
| P5 | 워크플로 밖 main 직접 push | (파일 없음 — 사람·AI 의 자격 증명) | main 에 올라가는 글·파일 | 사람·AI 가 하는 때 | 저장소 쓰기 자격 증명 | 정책뿐(AI 는 가지를 쓴다) |
| P6 | 사이트 배포 | `pages.yml` | main 을 빌드해 Pages 에 올린다 — 새 글을 만들지 않고 main 의 공개 파일을 공개한다 | main push + 수동 | pages·id-token 쓰기 | 수단이다(승인은 main 에 들어가는 길에서 일어난다) |

**결론: 잠금 켬 + §6 의 값에서 워크플로·코드로 열 수 있는 승인 없는 공개 경로는 P1–P4 모두 닫힌다(코드와 시험이 증명). 남는 것은 워크플로 밖의 P5(정책)와 §7 의 한계다.**
이 판정의 근거는 `tests/test_publish_paths.py` 가 워크플로 파일 전체의 쓰기 신호를 읽어 이 문서의 표와 같은지 확인하는 것이다 — 새 쓰기 길이 생기면 시험이 빨강이 된다.

## 2. 정의와 판정 기준

- **공개 경로**: 새 글·글 수정이 **사람 승인 없이 공개 화면**(GitHub Pages 사이트, Blogger 공개 글)에 나타나는 길. **사람 승인** = 사람이 글을 읽고 하는 동작 — Chance 는 초안 PR 의 병합, Blogger 는 초안함의 글을 Blogger 화면에서 직접 게시.
- **기록 파일·초안 폴더 커밋은 공개가 아니다 — 단, Jekyll 이 공개하는 경로로 들어가면 공개다.** 판정 규칙: 공개 사이트 파일이 되는 것은 ① `_posts/` 아래 글 ② 점(.)·밑줄(_)로 시작하는 구간이 없고 `_config.yml` 의 `exclude` 에 없는 파일. 밑줄 폴더(`_blogger_drafts`·`_blogger_ko_drafts`·`_naver_drafts`)와 점 폴더(`.github`)는 Jekyll 이 처리하지 않고, 이력 파일(`history.json`·`blogger_history.json`·`blogger_ko_history.json`·`naver_history.json`)과 `pages.json` 은 `exclude` 에 있다.
  시험(`RecordFilesAreNotPublicTest`)이 레지스트리의 모든 `state` 경로와 워크플로가 커밋하는 파일이 공개 경로가 아님을 같은 규칙으로 확인한다(대조군: `_posts/` 아래와 `about.md` 는 공개로 판정된다).
- 저장소는 공개라서 초안 브랜치·초안 PR·초안 이슈는 **GitHub 화면에서는** 누구나 읽을 수 있다. 블로그 사이트(공개 화면)는 아니다 — 이것은 승인된 설계다(`SECURITY_GUARDRAILS.md` G-L9 ⑧).

## 3. 워크플로 전수표 — 쓰기 신호와 판정

`tests/test_publish_paths.py` 의 `ALLOWED` 표와 같은 내용이다(파일마다 쓰기 권한·쓰기 명령·파이썬 진입점·외부 액션이 정확히 같아야 시험이 통과한다). 공개 경로는 **굵게**.

| 파일 | 경로 번호 | 무엇을 바꾸는가 | 트리거 | 쓰기 권한·명령 | 사람 승인 | 공개 여부 |
|------|-----------|-----------------|--------|-----------------|-----------|-----------|
| `chanceblog.yml` | **P1** | 글(`_posts`)·이력을 `git add -A` → commit → push 로 main 에 올리고 배포 요청. `pr` 흐름이면 초안 브랜치(`ai/draft/…`)와 PR 을 올리고 **이력 한 파일만** main 에 커밋 | 정기(매시 17·47분 UTC) + 수동 | contents·actions·pull-requests 쓰기, `git push`·`gh workflow run` | direct: 없음 / pr: PR 병합 | direct 면 **공개**, pr 이면 병합 때 공개 |
| `chance-fix-images.yml` | **P2** | 기존 글의 이미지·출처 줄을 고쳐 main 에 직접 커밋하고 배포 요청 | 수동 전용 | contents·actions 쓰기, `git push`·`gh workflow run` | 없음 | **공개**(기존 공개 글 수정) |
| `blogger-en.yml`, `blogger-ko.yml` | **P3·P4** | 래퍼: 자기 cron·수동 입력으로 공용 `blogger.yml` 을 부른다 | 정기(매일) + 수동 | contents 쓰기(공용 워크플로가 커밋하려면 필요) | — | — |
| `blogger.yml` | **P3·P4** | 글 생성 → `pipeline/run.py` 가 mode 에 따라 Blogger 초안함 업로드 / **즉시 게시** / 저장소 파일만. 이력·초안 파일은 main 에 커밋 | 래퍼가 부를 때만 | contents 쓰기, `git push` | auto·`publish`: 없음 / draft: Blogger 화면에서 직접 게시 | 즉시 게시만 **공개**. 초안·이력·`_blogger_*_drafts` 는 공개 아님 |
| `naver.yml`, `tistory.yml` | — | 초안 패키지를 GitHub 이슈로 만들고(라벨 `초안`) 이력·`_naver_drafts` 를 main 에 커밋. 티스토리는 정기 실행 없음, 네이버는 `mode: off` | 정기(네이버)·수동 | contents·issues 쓰기, `git push` | 운영자가 복사해 직접 발행 | 아니오(이슈는 저장소 화면, 기록은 공개 아님) |
| `issue-edit.yml` | — | 이슈 수정 요청 → 수정 가지 + **PR**(병합은 사람) | 이슈 등록 + 수동 | contents·issues·pull-requests·actions 쓰기, `gh pr create`·`git push`(가지) | PR 병합 | 병합 때 공개 |
| `auto-pr.yml` | — | AI 가 올린 병합 부탁 가지의 PR 만 만든다(**병합·승인 호출 없음**) | `ai/claude/M###-*` 가지 push | pull-requests 쓰기, `gh api` | PR 병합 | 아니오 |
| `sync-issue-form.yml` | — | `pages.json`·`.github/ISSUE_TEMPLATE/page-edit.yml` 두 파일을 main 에 자동 커밋(글에서 뽑은 목록) | main 에 관련 파일 push + 수동 | contents 쓰기, `git push` | — | 아니오(두 파일 모두 공개 경로 아님) |
| `pages.yml` | **P6** | main 을 빌드해 GitHub Pages 에 배포 | main push + 수동 | pages·id-token 쓰기 | — | 수단: main 의 공개 파일이 공개된다 |
| `pr-scope-check.yml` | — | PR 에 범위 검사 코멘트 | PR | pull-requests 쓰기, `gh pr comment` | — | 아니오 |
| `ops-inbox.yml`, `watchdog.yml`, `operator-reply.yml`, `telegram-inbox.yml` | — | 이슈·코멘트·라벨만 쓴다(파일·브랜치 없음) | 정기·이슈·수동 | issues 쓰기 | — | 아니오 |
| `guardrails.yml`, `ai-request.yml`, `telegram-test.yml` | — | 읽기 전용(검사·알림) | push·수동 | 없음 | — | 아니오 |
| `chance-shadow.yml` | — | **그림자 실행**: 후보 글을 읽기 전용으로 만들어 평가만 한다(§5 — 그림자 실행 코드(GATE 묶음)가 먼저 병합된 뒤에만 안전하다) | 수동 전용 | **없음**(`contents: read`) | — | 아니오 |

`contents: write` 를 가진 워크플로는 정확히 아홉 개(`blogger-en.yml`·`blogger-ko.yml`·`blogger.yml`·`chance-fix-images.yml`·`chanceblog.yml`·`issue-edit.yml`·`naver.yml`·`sync-issue-form.yml`·`tistory.yml`)이고, 글 전체를 커밋하는 `git add -A` 는 P1·P2 의 두 파일에만 있으며,
`gh pr merge` 는 어디에도 없다(사람의 병합이 곧 승인이다). 세 가지 모두 시험이 고정한다.

### 파이썬 쪽 쓰기 길(워크플로 글자에 안 보이는 것)
- `pipeline/draft_flow.py` `deliver`: 초안 두 파일을 초안 브랜치로 push 하고 `history.json` 한 파일만 main 에 커밋한다(`history.json` 은 공개 경로가 아니다 — 시험 확인). PR 은 `pull-requests: write` 로 연다.
- `pipeline/run.py`: Blogger API 로 초안 업로드 또는 공개 게시. 공개 게시(`draft=False`)는 mode `auto` 이거나 수동 `publish` 입력일 때뿐이다(P3·P4).
- `blogger_generator.py`: `pipeline.run.main` 을 부르는 호환용 얇은 래퍼다(워크플로가 부르지 않는다). 잠금은 러너 안에 있으므로 어떻게 시작하든 같은 규칙이 적용된다.
- 모든 새 파이썬 진입점은 `ALLOWED` 표에 올라 있어야 한다(새 명령이 더해지면 시험이 빨강).

## 4. 잠금 설계 — 켜면 코드가 강제하는 것

### 4-1. 레지스트리 규칙 (검증기: `python -m pipeline.registry`·`pipeline.plan`·`pipeline.run`·`validate_repo` REG-1)

**L0–L7 은 잠금이 켜져 있을 때만** 적용된다(꺼져 있으면 값 모양 검사 한 가지뿐 — L5 의 둘째 줄). 모르는 값은 켜진 것으로 읽는다(fail closed). **K1·K2 는 잠금과 무관하게 항상** 적용된다 — 잠금 키가 아예 없는 지금의 레지스트리는 그대로 통과한다.

| 규칙 | 내용 | 막는 길 |
|------|------|---------|
| **L0** | `resume_lock` 의 **값**은 `true` 또는 `false` — 그 밖의 값(문자열 `"true"`·숫자·null)은 켜진 것으로 읽고 이 오류를 낸다. **L0 은 값 오타만 막는다**(키 이름 오타·위치 오류는 아래 K1·K2 가 막는다) | 값 오타로 잠금이 꺼지는 것 |
| **L1** | `chance.publish_flow` 는 `pr` — 적지 않으면 `direct` 로 읽히므로 `pr` 을 직접 적어야 한다 | P1 |
| **L2** | Chance 밖의 모든 블로그의 `mode` 는 `off`·`draft`·`package` 중 하나(`auto` 금지, 기본값 상속도 실제 값으로 판정) | P3 |
| **L3** | `chance.mode` 가 `auto` 이면 `publish_flow: pr` 가 함께 적혀 있어야 한다(자동 생성은 PR 로만) | P1 |
| **L4** | `chance.limits.max_posts_per_day` 는 1 | 하루 상한 |
| **L5** | `chance.limits.max_open_drafts`(열린 초안 PR 상한)가 있고 1 이상 3 이하 정수. 잠금이 꺼져 있어도 값이 적혀 있으면 1 이상 정수여야 한다(잘못 적은 값이 조용히 '규칙 없음'이 되지 않게) | 초안 적체 |
| **L6** | `chance.languages` 가 있으면 `ko` 를 포함하고 `ko`·`en` 만 겹침 없이(`["ko"]` 또는 `["ko", "en"]`) — 국문 우선 방향 | 번역 복제 |
| **L7** | Chance 밖의 모든 블로그의 `limits.max_posts_per_day` 도 1 (이 일이 더한 확장 규칙 — 운영자 조건 '하루 최대 1편'을 모든 블로그로 넓힘. 지금 값은 이미 1) | 하루 상한 |
| **K1** | 레지스트리 **최상위에는 알려진 키만** 둔다: `_doc`·`schema_version`·`shared_secrets`·`defaults`·`blogs`·`resume_lock`(`pipeline/publish_lock.py` 의 `KNOWN_TOP_LEVEL_KEYS` — 새 키는 이 목록과 시험(`KeyTypoTest`)을 함께 고쳐 의도적으로 더한다). 모르는 키는 오류이고, 줄인 이름(소문자로 바꾸고 `_`·`-`·공백을 뺀 것)에 `resume`·`lock` 이 들어 있으면 'resume_lock 오타로 보입니다' 라고 알려 준다(`resume_lok`·`Resume_Lock`·`resume-lock`·`resume_lock `(뒤 공백) 등) | 키 이름 오타로 잠금이 꺼진 채 통과하는 것 |
| **K2** | `resume_lock`(과 그 오타 — 줄인 이름에 `resume` 이 든 키)은 **최상위에만** 둔다 — `defaults`·블로그 항목 안에 있으면 오류('최상위에 두어야 한다') | 잘못된 위치로 잠금이 꺼진 채 통과하는 것 |

K1·K2 는 잠금 키가 없는 지금의 레지스트리에서 아무 오류도 내지 않는다(최상위 키가 모두 알려진 것이다). **실행 시에도 멈춘다**: 오타로 보이는 최상위 키(K1)와 잘못된 위치(K2)를 '잠금 키 문제'라 부르고, 가드·`chance_flow`·Blogger 러너·`check`·`check-direct` 가 이것을 만나면 글을 만들지 않고 멈춘다 — 오타가 '꺼짐'으로 읽혀 P2·P4·하루 1편 상한이 열리는 것을 막는다(독립 검증 지적 1). 잠금과 관계없는 모르는 키는 검증기만 거절하고 실행 시에는 새 실패 방식을 만들지 않는다.

### 4-2. 실행 시 가드 — 레지스트리 검증을 안 거친 길까지

| 길 | 어디서 | 잠금이 켜져 있으면 |
|----|--------|--------------------|
| 생성기(정기·수동) | `generator.py` `main()` 정지 검사 직후 한 줄 `publish_lock.guard_start(...)` | 규칙 위반이면 글을 만들지 않고 `::error::` + 종료 1. 하루 상한(1편)에 닿았으면 건너뜀(종료 0, 수동 실행이면 `::notice::`). 열린 초안 브랜치가 상한에 닿았거나 확인하지 못하면 건너뜀. 이력 파일이 깨졌으면 세지 못해 멈춤 |
| 기존 글 이미지 교체 | 같은 가드 + 워크플로 첫 단계 | 실제 실행은 종료 1(연습 실행은 쓰는 것이 없어 가드는 통과하지만 워크플로 첫 단계가 어떤 실행이든 멈춘다) |
| Chance 발행 흐름 읽기 | `drafts.chance_flow()` — '발행 흐름 확인' 단계·`draft_flow deliver`·생성기가 쓰는 한 곳 | 규칙 위반이면 `direct` 로도 `pr` 로도 답하지 않고 멈춘다 → 그 단계가 실패하면 뒤 단계(직접 커밋·배포 요청·초안 올리기)는 하나도 돌지 않는다 |
| Blogger 러너 | `pipeline/run.py` — 레지스트리를 읽자마자 규칙 검사, 전달 방식이 정해진 직후 즉시 게시 검사 | 규칙 위반이면 어떤 글도 만들지 않고 `::error::` + 종료 2. `publish`(수동 입력·`--publish on`) 은 어떤 표기로도 거절. 초안함 업로드(`draft`)·파일 저장(`off`)은 그대로 된다 |
| Blogger 대상 계산 | `pipeline.plan`(워크플로 plan 잡) | 레지스트리 검증이 먼저라 규칙 위반이면 글 생성 잡이 시작되지 않는다 |
| 직접 커밋 워크플로 | `python -m pipeline.publish_lock check-direct`(`chance-fix-images.yml` 첫 단계) | 켜져 있거나 레지스트리를 읽지 못하면 종료 1 |

- **꺼짐 = 이전과 같다**: 잠금이 꺼져 있고 `max_open_drafts` 값도 없으면 가드는 레지스트리를 읽는 것 말고 아무것도 하지 않는다(이력·원격·출력 없음 — 시험 `GuardOffTest`가 부르면 실패하는 대역으로 확인). `main()` 수준의 같음은 `GeneratorMainTest` 의 `…guard_changes_nothing…` 시험이 지킨다(같은 하루를 가드를 거쳐 돌린 실행과 가드를 건너뛴 실행의 반환값·출력·요약·모델에 보낸 글·이력이 같다). `chance_flow`·러너는 기존 시험(`test_drafts`·`test_run`·`test_blogger_split` 등)이 그대로 통과한다. `generator.main` 을 돌리는 기존 시험은 흐름만 보도록 가드를 `guard_off()`(tests/lock_helpers.py)로 건너뛴다 — 켜는 변경이 레지스트리 값을 바꿔도 그 시험들이 임시 폴더에서 열린 초안을 세려다 멈추지 않게 하려는 것이고, 이유는 §9 에 있다.
- **읽기 전용 실행은 상한을 세지 않는다**: 연습 실행(`DRY_RUN`)과 그림자 실행(`SHADOW_RUN`)은 글을 올리지 않으므로 하루 상한·열린 초안 상한을 세지 않는다. 다만 규칙 위반(과 잠금 키 문제)은 가드에 닿은 실행이면 연습이든 그림자든 멈춘다(우회 없음).
- **합친 뒤의 순서(A)**: `generator.py` `main()` 에서 **정지 검사 → 그림자 분기(GATE 묶음, `SHADOW_RUN`) → 잠금 가드** 순서로 확정했다(코드 주석에도 적었다). 그림자 분기는 읽기 전용으로 처리하고 끝나므로 그림자 실행은 가드에 닿지 않는다 — 그래서 '그림자도 규칙 위반이면 멈춘다'는 순서 B(가드가 먼저)에서만 참이고 A 에서는 아니다(그림자는 쓰는 길이 없어 위험하지 않다). 가드 안의 `SHADOW_RUN` 예외(상한을 세지 않음)는 평소에는 닿지 않는 **방어선**이다: 그림자 분기를 지나쳐 가드에 온 경우를 위한 것이다. GATE 병합 전의 이 가지에는 그림자 분기가 없어 생성기가 `SHADOW_RUN` 을 모르므로 이 예외가 오히려 상한을 건너뛰는 틈이 된다 — 그래서 `chance-shadow.yml` 은 첫 단계에서 그림자 실행 코드(`pipeline/shadow_run.py`)가 없으면 실패한다(§5·§7).
- **`SHADOW_RUN` 값 집합(이 문서가 한 곳)**: 켜짐 `1`·`true`·`yes`·`on`·`enabled`, 꺼짐 비움·`0`·`false`·`no`·`off`·`disabled`(대소문자·앞뒤 공백은 무시). 그 밖의 값은 **잠금이 켜져 있을 때** 가드가 실행을 거절한다(종료 2, 로그 `[SKIP] code=LOCK_BLOCKED reason=SHADOW_RUN_VALUE`, `::error::` 는 고정 문장). 잠금이 꺼져 있으면 가드는 값을 보지 않는다(출력이 이전과 같다). GATE 의 `generator.py` 판정과 같은 집합이어야 하고, 병합 뒤에는 `ShadowValueTest` 가 둘을 견준다(GATE 코드가 없는 이 가지에서는 그 견줌만 건너뛴다).
- **상태 줄(검증 지적 1②)**: 잠금이 **켜져 있으면** 가드가 로그에 `[잠금] 제한 재개 잠금: 켜짐` 한 줄을 남긴다. **꺼져 있으면(키가 없든 `false` 든) 아무것도 남기지 않는다** — 꺼진 상태의 출력이 이전과 바이트까지 같아야 하므로 '항상' 이 아니라 '켜져 있을 때만'을 골랐다. 기준선(origin/main)과 시나리오 56개를 견주니 '키가 있을 때만'(꺼짐 줄 포함)은 `resume_lock: false` 인 시나리오 둘이 한 줄 달라졌고 '켜져 있을 때만'은 꺼진 모든 시나리오가 같았다. 꺼짐은 `check` 로 본다. 키 이름 오타·위치 오류는 K1·K2 로 멈추므로 '조용히 꺼진 채'가 되지 않는다. `check`·`check-direct`(워크플로 단계의 명령)는 늘 상태를 로그에, `GITHUB_STEP_SUMMARY` 가 있으면 실행 요약에도 남긴다.
- **열린 초안 수 세기의 한계**: 생성기 프로세스에는 저장소 쓰기 토큰을 주지 않는다(`test_the_generator_step_does_not_get_the_github_token`). GitHub API 로 '열린 PR 수'를 세려면 토큰이 필요하므로 git 으로 원격의 초안 브랜치(`ai/draft/…`)를 읽고, 글이 이미 main 에 있는(병합된) 초안은 빼서 센다. **닫은 초안도 브랜치가 정리되기까지(7일) 열린 것으로 센다** — 실제 열린 PR 수보다 크거나 같아 상한을 넘기는 쪽으로는 틀리지 않는다(승인을 연달아 닫으면 최대 7일 새 초안이 쉬는 것이 비용이다).
- **하루 상한의 단위**: 이력(`history.json`)의 `date`(한국 날짜)가 오늘인 항목 수다. 승인 대기·닫힘·병합 모두 이력에 남으므로 닫은 뒤에도 같은 날 다시 만들지 않는다.
- **실제 git 으로 확인한 이야기**: `tests/test_publish_lock_git.py`(`RealGitLockStoryTest`)가 임시 bare origin 과 실제 생성기로 하루하루를 따라간다 — 잠금이 켜진 승인 흐름에서 main 에는 이력 한 파일만 올라가고 글은 초안 브랜치에만 있다, 같은 날 두 번째 슬롯은 원격을 그대로 두고 건너뛴다, 열린 초안 수는 **실제 `git ls-remote`** 로 세며 병합한 초안은 빼고 이력에 없는 브랜치는 센다, 규칙을 어긴 레지스트리는 아무것도 올리지 않는다.

### 4-3. 워크플로 변경(최소)

| 파일 | 변경 | 이유 |
|------|------|------|
| `chance-fix-images.yml` | 첫 단계 `제한 재개 잠금 확인 (켜져 있으면 직접 커밋 금지)` 한 개(`python -m pipeline.publish_lock check-direct`) — **연습 실행(`dry_run` 체크, 기본값)은 건너뛴다**(단계 조건 `if` 가 입력 `dry_run` 의 부정 `!inputs.dry_run` — 이중 중괄호 식 문법은 이 문서가 Liquid 로 읽히는 것을 피하려고 적지 않는다) | 이 워크플로는 사람 승인 없이 공개 글을 고쳐 main 에 커밋하므로 잠금 아래에서는 실제 교체를 실행하지 않는다. 연습 실행은 저장·커밋을 하지 않고(커밋 단계도 연습이면 건너뛴다) 생성기 가드도 연습은 통과시키므로 막을 이유가 없다 — 연습까지 막히면 켠 뒤 교체 대상을 눈으로 확인하는 길도 사라진다(독립 검증 지적 6). 규칙 위반이면 생성기 가드가 연습도 멈춘다. 쓰기 권한은 줄이지 않았다 — 권한을 줄이려면 job 을 둘로 쪼개야 해서 시험이 고정한 구조를 크게 바꾼다. 생성기 가드가 같은 일을 한 번 더 막는다 |
| `chance-shadow.yml` | 새 워크플로(읽기 전용, §5). 체크아웃 바로 뒤 첫 단계가 `pipeline/shadow_run.py` 가 있는지 확인하고 없으면 실패한다 | 정지를 유지한 채 그림자 모드 3회·초안 10개 이상 평가를 얻는다. 그림자 실행 코드(GATE 묶음)가 먼저 병합돼야 안전하다(§5·§7) |
| `chanceblog.yml` | **변경 없음** | 이 파일의 단계 목록은 시험이 정확히 고정한다. 직접 커밋 단계는 '발행 흐름 확인' 단계의 결과에 기대고(`flow != 'pr'`), 그 단계가 `drafts.chance_flow()` 로 실패하면 뒤 단계가 돌지 않는다는 것을 시험이 단계 조건으로 계산해 보인다(`DirectPushNeverRunsUnderTheLockTest`). 어떤 단계도 `always()`·`failure()`·`cancelled()` 를 쓰지 않는다는 것도 시험이 고정한다 |

## 5. 그림자 실행 워크플로(`chance-shadow.yml`)가 어떤 쓰기도 못 하는 이유

목적: 발행 정지를 유지한 채 최소 품질 Gate 가 붙은 생성기가 만드는 초안을 읽기 전용으로 평가한다. 생성기의 `SHADOW_RUN=1`·`SHADOW_OUT`·`SHADOW_COUNT` 인터페이스를 부르고(출력 형식은 `docs/QUALITY_GATE.md`), 두 번째 단계에서 **별도 프로세스**로 측정 도구를 돌려 실행 요약(숫자만)과 아티팩트(보관 14일)로 낸다.

1. 트리거는 `workflow_dispatch` 하나 — 정기 실행·push·PR·이슈 이벤트가 없다.
2. 권한은 `contents: read` 뿐 — push 도 PR·이슈·배포 요청(`actions: write`)도 할 수 없다. 체크아웃은 `persist-credentials: false` 라 토큰이 git 설정에 남지 않는다. job 이 권한을 올리지도 않는다.
3. 단계에 `git`·`gh`·`curl` 이 없고 `GITHUB_TOKEN` 을 어느 단계에도 넘기지 않는다. 비밀(Gemini·Unsplash 키)은 생성기 단계의 `env` 로만 간다.
4. 정지 변수 `PIPELINE_PAUSE` 는 값을 그대로 넘길 뿐 바꾸지 않는다(정지가 켜져 있어도 건너뛰는 것은 생성기의 그림자 모드 코드다).
5. 생성기는 측정 도구를 부르지 않는다. 측정 단계는 도구(`pipeline/quality_shadow.py`)가 저장소에 있을 때만 돌고 없으면 건너뛴다. 실행 요약에는 숫자와 고정 문장만 쓴다.
6. 이 모든 것을 `ShadowWorkflowCannotWriteTest` 가 파일에서 직접 확인한다. 이 워크플로를 어떤 다른 워크플로도 부르지 않는다.
7. **병합 순서 의존(정직하게)**: 위 1–6 은 워크플로가 하는 약속이고, '읽기 전용으로 돈다·정지 중에도 돈다'는 말은 **그림자 실행 코드(GATE 묶음 — `pipeline/shadow_run.py` 와 `generator.py` 의 `SHADOW_RUN` 분기)가 먼저 병합된 뒤에만** 참이다. 그 코드가 없는 저장소의 생성기는 `SHADOW_RUN` 을 모르기 때문에 일반 실행으로 돌아 글을 만들고 Gemini 무료 한도를 쓴다. 그래서 체크아웃 바로 뒤 첫 단계가 `pipeline/shadow_run.py` 가 없으면 '이 저장소에는 그림자 실행 코드가 없어 중단합니다' 로 실패한다(없는 채로 도는 것을 구조로 막는다. 시험: `ShadowWorkflowCannotWriteTest` 의 단계·파일 존재 검사). 병합 순서는 GATE → LOCK → SHADOW → R2 → SRC → FACT 로 확정했다. 출력 형식 문서 `docs/QUALITY_GATE.md` 도 GATE 병합 전에는 저장소에 없다.

## 6. 켜는 방법 — 레지스트리에서 바꿀 값 (별도 T3 병합)

잠금을 켜려면 **한 번의 변경**으로 다음을 함께 고친다(하나라도 빠지면 검증이 빨강이라 병합 전에 걸린다):

| 위치 | 지금 | 켤 때 | 규칙 |
|------|------|-------|------|
| 최상위 `resume_lock` | 없음 | `true` | L0 |
| `chance.publish_flow` | `direct` | `pr` | L1·L3 |
| `chance.limits.max_posts_per_day` | `2` | `1` | L4 |
| `chance.limits.max_open_drafts` | 없음 | `3` | L5 |
| `chance.mode` | `auto` | 그대로(`pr` 은 `auto` 일 때만 허용) | L3 |
| `blogger_macat.mode`·`blogger_kcyoon.mode` | `draft` | 그대로 | L2 |
| `naver_life_tips.mode` | `off` | 그대로(`package` 도 허용) | L2 |
| `chance.languages` | `["ko", "en"]` | 그대로(국문만 시작하려면 `["ko"]`) | L6 |
| Blogger·네이버 `limits.max_posts_per_day` | `1` | 그대로 | L7 |
| `PIPELINE_PAUSE`(저장소 변수) | 켜짐 | **이 일은 건드리지 않는다** — 잠금·최소 품질 Gate·그림자 검증이 끝난 뒤 운영자가 해제 | — |

같은 변경에서 함께 고쳐야 하는 시험의 고정값(켜는 변경이 일부러 깨뜨리는 표지판): 이 문서 §9 의 목록.
**잠금을 끄는 것**(`resume_lock` 을 지우거나 `false`)과 규칙을 줄이는 것도 T3 다 — 승인 없는 공개 경로를 다시 여는 변경이다(`SECURITY_GUARDRAILS.md` §3).

## 7. 한계와 남은 위험

1. **P5(워크플로 밖 main 직접 push)는 막지 못한다.** main 룰셋은 삭제·강제 푸시만 막고 PR 필수 규칙은 켜지 않았다(운영자 결정 2026-10-25 — 봇이 main 에 직접 push 해야 한다). 잠금이 켜지면 봇이 main 에 직접 올리는 것은 기록 파일(공개 아님)뿐이므로 PR 필수 규칙(봇 우회 허용 필요 — 미검증)을 켜는 것이 다음 단계 후보이고, 켜는 것은 운영자 설정이다.
2. 닫은 초안도 최대 7일 열린 것으로 센다(§4-2) — 새 초안이 쉬는 쪽의 오차다. 열린 PR 을 API 로 정확히 세려면 토큰이 필요한 별도 단계가 필요하고 시험이 막아 둔 '생성기에 토큰 금지' 원칙과 부딪힌다(운영자 결정 대기).
3. 이력 파일(`history.json`)이 깨지면 생성기의 `read_history` 는(잠금과 무관하게) 빈 기록으로 계속하는 기존 약점이 있다. 잠금 가드는 이 경우 하루 상한을 셀 수 없어 **멈춘다**(fail closed). 잠금이 꺼져 있을 때의 기존 동작은 바꾸지 않았다.
4. 하루 상한은 이력에 기록된 글 수로 센다. 같은 날 두 번째 슬롯·수동 실행을 막지만, 이력 커밋(`deliver` 가 main 에 올린다)이 실패해 롤백된 초안은 기록이 없어 세지 않는다(그 초안도 브랜치째 지워진다).
5. 레지스트리를 아예 읽지 못하면 글을 만드는 길은 `chance_flow()` 가 멈추지만 가드 자체는 새 실패 방식을 만들지 않는다(기존 동작 유지). 레지스트리를 읽지 않던 이미지 교체 길만 읽지 못하면 멈춘다.
6. `chance.mode: off` 는 Chance 생성기가 읽지 않는다(Chance 의 정지는 `PIPELINE_PAUSE` 뿐이다 — 기존 사실). 그래서 L1·L4–L6 은 Chance 의 `mode` 와 무관하게 적용한다.
7. 그림자 실행의 아티팩트는 공개 저장소의 공개 산출물이다(초안 PR 과 같은 취급). 비밀·수익 수치는 싣지 않는다.
8. 시험을 지우거나 약하게 만드는 변경은 시험이 지키지 못한다 — 사람 검토(독립 검증·`CODEOWNERS`)가 막는다.
9. `pages.yml` 의 수동 배포는 사람이 누르는 것이고 글을 만들지 않는다. 가지 배포를 환경 규칙이 막는지는 이 일에서 확인하지 못했다(미검증).
10. 잠금이 켜져 있으면 `chance.mode` 는 `auto` 로 고정된다(`publish_flow: pr` 은 `auto` 일 때만 허용되는 기존 규칙). Chance 만 따로 멈추려면 `mode: off` 가 아니라 전체 정지(`PIPELINE_PAUSE`)나 잠금을 끄는 T3 변경을 쓴다.
11. 그림자 실행 워크플로의 정지 우회(`SHADOW_RUN` 이 켜짐일 때만 정지 검사를 건너뜀)와 쓰기 차단은 생성기 쪽 코드(GATE 묶음)가 맡는다 — 이 문서와 시험은 워크플로가 읽기 전용이라는 것과 그 인터페이스(`SHADOW_RUN`·`SHADOW_OUT`·`SHADOW_COUNT`)만 증명한다. **'그림자 실행은 정지 중에도 돌고 읽기 전용이다'는 GATE 가 먼저 병합된 뒤에만 참이다**(§5-7). 합친 뒤의 `main()` 순서는 정지 검사 → 그림자 분기 → 잠금 가드(A)이므로 그림자 실행은 잠금 가드에 닿지 않는다 — '그림자도 규칙 위반이면 멈춘다'는 순서 B 에서만 참이다(§4-2). 병합한 뒤 실제 실행으로 확인한다(미관측).
12. **원격 초안 목록을 못 읽으면 조용히 건너뛴다**: `git ls-remote` 가 실패하면 가드는 종료 0(초록)으로 건너뛴다(`OPEN_DRAFTS_UNKNOWN`, `::warning::` 한 줄). 그 상태가 계속되면 글이 조용히 나오지 않고, 드러나는 곳은 워치독의 '마지막 글 36시간 격차' 알림뿐이다(빨강이 아니다). 일시 장애에 다음 정기 실행이 다시 시도하게 하려고 일부러 초록으로 두었다.
13. **닫은 초안은 7일간 열린 것으로 센다**(§4-2): 초안 PR 을 닫아도 브랜치가 정리되는 7일까지(`RETENTION_DAYS`) 상한에 들어가므로, 3개를 닫아도 새 초안이 며칠 쉴 수 있다.
14. **하루 '1편'은 한국어·영어 한 쌍이다**: 한 번의 생성이 글 파일 둘(`KR`·`EN`)을 만들고 이력에는 항목 하나가 남는다. 하루 상한 1 은 이 '한 번의 생성'을 센다(글 파일 수가 아니다).
15. **L6 은 GATE 의 `languages` 검증과 판정이 다르다(독립 검증의 비교표, 2026-11-09)**: L6 은 키가 없거나 `null` 이면 규칙을 적용하지 않고(그 경우는 기존 검증기와 GATE 의 검증이 따로 거절한다), 값이 목록이면 `ko` 를 포함하고 `ko`·`en` 만 겹침 없이 담았는지만 본다(순서 무관 — 허용 언어는 정확히 `{ko, en}` 이고 시험이 못박는다). GATE 묶음의 검증은 잠금과 무관하게 항상 켜져 있고, 비교한 시점의 GATE 는 순서(`["en", "ko"]`)·키 없음·`null` 도 거절해 L6 보다 엄격했다. GATE 가 순서를 가리지 않는 쪽(L6 과 같은 집합)으로 맞추는 중이라 병합 때 차이가 키 없음·`null` 로 줄 수 있다 — 병합 때 이 문장을 다시 확인한다. 어느 쪽이든 GATE 병합 뒤에는 두 검증을 모두 통과해야 레지스트리가 통과하므로 더 엄격한 쪽이 이긴다(서로 모순되지 않는다).
16. **실행 시 멈춤은 오타로 '보이는' 키만 본다**: 가드·`chance_flow`·Blogger 러너·`check` 가 멈추는 잠금 키 문제는 영문 철자에 `resume`·`lock` 이 든 최상위 키(K1)와 잘못된 위치(K2)뿐이다. 모양이 전혀 다른 모르는 최상위 키는 병합 전 검사(검증기 REG-1)가 거절하지만 실행 시에는 막지 않는다 — 그 키는 잠금과 무관하게 무시되고, 잠금 키 오타는 위 모양에 걸린다.

## 8. 설계 결정

| 번호 | 결정 | 이유 |
|------|------|------|
| L-1 | 잠금은 레지스트리 최상위 키 하나이고 기본 꺼짐 | 켜는 것이 T3 이고 꺼짐은 이전과 같아야 한다(`ENGINEERING_GUIDE` §9-11). 값이 키 하나라 켜고 끄는 변경이 작다 |
| L-2 | 모르는 값은 켜진 것으로 읽는다 | 철자 실수가 승인 없는 공개 경로를 여는 것을 막는다(fail closed) |
| L-3 | 규칙 검사는 순수 함수(`lock_errors`)에 두고 검증기·`chance_flow`·러너·가드가 같은 함수를 부른다 | 네 곳이 같은 규칙을 읽는다 — 한 곳을 빼도 시험이 잡는다(변이 점검) |
| L-4 | 하루 상한은 이력의 오늘 날짜 항목 수로 세고, 정기·수동 모두에 잠금 아래에서만 강제한다 | 지금은 상한이 정기 실행의 슬롯 수와 수동 실행의 경고뿐이다(D-54). 꺼짐의 동작은 바꾸지 않는다 |
| L-5 | 열린 초안 상한은 git 의 원격 초안 브랜치 중 병합되지 않은 것으로 센다 | 생성기에 쓰기 토큰을 주지 않는 원칙(시험이 고정) 안에서 가능한 가장 보수적인 근사 |
| L-6 | `chanceblog.yml` 은 고치지 않고 `chance_flow` 의 실패로 뒤 단계를 막는다 | 단계 목록을 시험이 고정하고, 실패한 단계 뒤는 돌지 않는다는 규칙을 단계 조건 계산으로 증명할 수 있다 |
| L-7 | `chance-fix-images.yml` 은 잠금 아래에서 중단한다(PR 로 올리지 않는다) | PR 로 올리는 길은 이미 이슈 수정 요청이 있다. 새 PR 코드·권한을 더하지 않는 것이 최소 변경이다 |
| L-8 | 그림자 워크플로는 읽기 전용 권한 + 별도 측정 프로세스 | 쓰기 길이 구조적으로 없어야 정지 중에도 안전하게 돌릴 수 있다 |
| L-9 | 새 쓰기 길 탐지는 권한·명령·파이썬 진입점·외부 액션의 전체 신호를 정확히 비교한다 | 글자에 안 보이는 파이썬 쓰기 길도 새 진입점으로 드러난다 |
| L-10 | Blogger 수동 `publish` 를 잠금 아래에서 거절한다 | 레지스트리 mode 와 무관하게 즉시 공개되는 유일한 Blogger 길이다 |
| L-11 | 레지스트리 최상위는 알려진 키만 허용하고(K1) 잠금 키의 위치를 본다(K2) — 잠금과 무관하게 항상, 오타로 보이는 키·잘못된 위치는 실행 시에도 멈춘다 | 키가 없으면 꺼짐이라서 이름 오타·위치 오류가 조용히 잠금을 끈다(독립 검증 지적 1). 잠금 키가 없는 지금의 레지스트리는 영향이 없다 |
| L-12 | 가드의 상태 줄은 잠금이 켜져 있을 때만 남긴다. `check`·`check-direct` 는 늘 남긴다 | 꺼진 상태(키 없음·`false`)의 출력이 이전과 바이트까지 같아야 한다 — 비교로 확인했다 |
| L-13 | 합친 뒤 `main()` 순서는 정지 검사 → 그림자 분기 → 잠금 가드(A) | 그림자 분기는 읽기 전용으로 끝나므로 가드가 필요 없다. 가드의 그림자 예외는 방어선이다 |
| L-14 | `SHADOW_RUN` 값 집합을 GATE 와 같게(켜짐 5 · 꺼짐 6), 모르는 값은 잠금이 켜져 있을 때 가드가 거절 | 가드와 GATE 가 같은 값을 다르게 읽어 상한이 건너뛰어지는 틈을 없앤다 |
| L-15 | 이미지 교체 워크플로의 첫 단계는 연습 실행(저장 안 함)에서 건너뛴다 | 연습은 쓰는 길이 없고 생성기 가드가 통과시킨다. 켠 뒤에도 교체 대상을 확인할 수 있다 |

## 9. 켜는 변경이 일부러 깨뜨리는 시험 고정값

켜는 변경(§6)은 별도 T3 병합이고, 그 변경은 **같은 변경에서** 진짜 레지스트리 값을 못박은 '표지판' 시험을 의도적으로 고친다(레지스트리만 슬쩍 바뀌면 이 시험들이 빨강이 되게 하려는 것이다).
이 목록은 켜는 값을 레지스트리 파일에 글자 그대로 넣은 복사본에 전체 시험(98개 모듈)을 돌려 얻은 것이고, 아래 고침을 더한 복사본은 전체가 초록이다.

| 고치는 곳 | 못박은 것 | 켤 때 | 이 고침으로 통과하는 시험 |
|-----------|-----------|-------|----------------------------|
| `pipeline/blogs.json` | `resume_lock` 없음 · Chance `publish_flow` `direct` · 하루 상한 `2` · `max_open_drafts` 없음 | §6 의 값 넷 | — |
| `tests/draft_helpers.py` `REAL_PUBLISH_FLOW` | `"direct"` | `"pr"` | `test_drafts`(`ChanceFlowTest.test_the_real_registry_has_the_pinned_flow`·`ChanceFlowTest.test_the_cli_flow_command_prints_the_value_or_fails`·`PublishFlowRegistryTest.test_the_real_registry_writes_direct_for_chance_and_is_valid`)·`test_generator_drafts`(`FlowLookupTest.test_the_engine_enters_the_draft_flow_exactly_when_the_real_registry_says_pr`)·`test_batch2_integration`(`RegistryCombinationTest.test_the_real_registry_is_unchanged_by_the_merge`)·`test_ops_inbox_drafts`(`RunWithDraftsTest.test_the_real_registry_gives_chance_blogger_and_package_rows_with_nothing_pending`) |
| `tests/test_registry.py` `RealRegistryTest.test_defaults_are_merged` | Chance 하루 상한 `2` | `1` | 그 시험 한 개 |
| `tests/test_publish_lock.py` `LockStateTest.test_the_real_registry_has_the_lock_off_today` | `resume_lock` 키가 없고 레지스트리가 `today_registry()` 와 같다 | `resume_lock` 이 `True` 이고 `lock_ready()` 와 같다(시험 이름도 바꾼다) | 그 시험 한 개 |

**이 일이 미리 보강해 둔 것**(켜는 변경이 건드리지 않아도 된다):
- `generator.main` 을 임시 폴더에서 돌리는 기존 시험(`test_generator_drafts` 의 `run_tick`·`test_generator_slots` `MainPolicyTest`·`test_manual_run_defaults` 둘·`test_gemini_call_log` 하나)은 잠금 가드를 `guard_off()`(`tests/lock_helpers.py`)로 건너뛰고 흐름만 본다. 가드가 임시 폴더(저장소가 아님)에서 열린 초안 수를 `git ls-remote` 로 세려다 멈추기 때문이다. `draft_flow_on` 을 시험 쪽에서 고정해 온 것과 같은 방식이다. 가드를 거치는 같음은 `GeneratorMainTest` 가 따로 지킨다. 새 시험이 `generator.main` 을 돌리면 같은 방식을 쓰고, 잠금 자체를 보는 시험만 `run_tick(..., guarded=True)` 로 돌린다.
- 실제 레지스트리를 복사해 Blogger 를 `auto` 로 두는 임시 저장소·사본(`test_run.make_root`·`test_plan_and_watchdog.registry_all_auto`·`test_drafts.real_registry`)은 `resume_lock` 키를 뺀다 — 그 시험들은 잠금이 꺼진 설정의 흐름을 보고, 잠금 규칙은 `test_publish_lock` 이 본다.
- 수동 실행의 하루 상한 경고 시험(`test_manual_run_defaults.ManualOverCapTest`)은 상한 2 를 읽는 '잠금 꺼짐' 레지스트리 사본으로 고정한다.
- 이 일의 시험은 '꺼짐' 기준에 진짜 레지스트리 대신 `today_registry()`(진짜 값을 오늘의 값으로 맞춘 사본)를 쓴다. 진짜 값에 묶인 것은 위 표의 `test_publish_lock` 한 시험뿐이다.

**표지판 시험은 고치되 지우지 않는다**: `LockStateTest.test_the_real_registry_has_the_lock_off_today` 는 켠 뒤 `resume_lock is True` 이고 `reg == lock_ready()` 인지 확인하는 시험으로 **바뀐다**(위 `flip.patch` 가 그렇게 고친다). 이 시험을 지우면 레지스트리의 잠금 줄을 지우는 변경(키가 없으면 꺼짐)을 아무도 못 잡는다 — K1·K2 는 오타와 잘못된 위치를 잡지만 줄을 통째로 지운 것은 이 시험만 잡는다.
**켠 뒤에 달라지는 동작**: 18시 슬롯의 정기 실행은 하루 상한(1편)에 닿아 만들지 않고 정상 건너뜀(`[SKIP] code=LOCK_DAILY_CAP`, 초록)으로 끝난다. 수동 실행도 같은 날 두 번째부터는 같다. 승인을 기다리는 초안이 3개에 닿으면 새 초안을 만들지 않는다.
**켠 뒤 틀리는 문구**(워크플로 파일은 이 가지에서 바꾸지 않았다 — 켜는 변경(T3)에서 같이 고친다): `chanceblog.yml` 수동 입력 `dry_run` 의 설명 '(수동 게시는 게시 시각·하루 상한을 따지지 않습니다)' 는 잠금 아래에서 틀린다(수동 게시도 하루 1편을 따진다). 같은 취지의 문서: `docs/ACTIONS_GUIDE.md` 3-1 과 3-13 의 '수동 게시는 … 하루 상한(2편)도 따지지 않습니다'·'막지는 않고 노란 경고와 요약 줄로 알립니다'.
**같은 변경에서 고칠 문서**(시험이 일치를 확인하지는 않는다): 이 문서의 맨 위 설명과 §1 표의 `지금(꺼짐)` 열·§6 의 `지금` 열, `docs/ARCHITECTURE.md` §4-9 의 스위치 문단('이 일은 레지스트리 값을 바꾸지 않았다' 문장), `docs/ACTIONS_GUIDE.md` 3-22 의 `지금(꺼짐)` 열과 '켜졌는지 보는 법'.
