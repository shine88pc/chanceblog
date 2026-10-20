# 결함 레지스터

> 코드·설정·문서에서 **직접 확인한** 결함만 적는다(확인일: 2026-10-20). 추측은 "미확인"으로 표시한다.
> 상태: **해결**(이번 변경으로 고침) · **완화**(위험을 줄였지만 근본 해결 전) · **사용자 조치**(AI가 할 수 없음) · **열림**(계획됨)
> 새 결함을 발견하면 ID를 붙여 여기에 추가하고, 고쳤다면 상태·근거를 갱신한다. 검증기 검사 ID(`scripts/validate_repo.py`)와 연결한다.

| ID | 심각도 | 결함 | 근거(확인 방법) | 상태 | 해결 계획 |
|----|--------|------|-----------------|------|-----------|
| **D-01** | 높음 | **이슈 기반 이미지 변경이 main에서 동작하지 않고, 위험한 LLM 편집 코드가 남아 있다.** 이슈 양식(제목 `[이미지 변경] `, 필드 `target_post`·`user_prompt`)·워크플로 조건(`startsWith(… '[Control]')`)·`generator.py`(옛 `작업 종류` 파서)가 서로 맞지 않는다. 옛 핸들러는 LLM이 파일을 골라 편집·삭제한다(`plan_actions`·`edit_file_with_patches`·`delete_post`) | `1d7ccc6`(10-19 11:20 KST)이 이미지 전용 처리(`resolve_issue_post`·`replace_post_image`)를 도입했으나, 직계 자식 `32a2469`("Update print statement from 'Hello' to 'Goodbye'", 10-19 18:14 KST)가 `generator.py`를 통째로 교체(+442/−241). 현재 main에는 `resolve_issue_post` 0건, `plan_actions` 2건(**수정 전 main 기준**). 검증기 **CONTRACT-1** | **해결**(코드) — **관측 필요** (옛 LLM 편집·삭제 핸들러와 `chanceblog.yml`의 `issues` 트리거를 제거하고 `pipeline/edits` + `issue-edit.yml`로 대체. 단 Actions에서 실제 이슈를 처리한 적은 없음) | 구현: [`ISSUE_EDITS.md`](./ISSUE_EDITS.md)(이슈 양식 → 문자 그대로 교체·AI 최소 패치 → 사후 검증 → PR). 검증기 **CONTRACT-1**(양식↔워크플로)·**SPEC-1/2**, 테스트 109개. 관측: 하단 체크리스트의 Issue Edit dry-run과 실제 이슈 1건 → 확인되면 "해결"로 바꾸고 D-06을 닫는다. T2 |
| **D-02** | 높음 | **봇이 커밋해도 Pages 배포가 실행되지 않을 수 있다.** `GITHUB_TOKEN`으로 push한 커밋은 `push` 이벤트를 만들지 않는다(예외: `workflow_dispatch`) | `pages.yml`은 `on: push`만 트리거(10-20 01:20 KST 추가). 봇 마지막 커밋 `05adcff`(10-19 10:57Z)에는 연결된 실행 0건(API `head_sha` 조회). 그 이후 봇 커밋이 없어 **실제 발생은 미관측** | **해결**(코드) — **관측 필요** | `chanceblog.yml`이 새 커밋을 push한 뒤 `gh workflow run pages.yml`을 실행(`actions: write`). 다음 봇 커밋 때 `Deploy GitHub Pages`가 `workflow_dispatch`로 실행되는지 Actions 탭에서 확인(L4). 검증기 **WF-10** |
| **D-03** | 중간 | **Chance 스케줄 실행은 성공하는데 봇 글이 하루 넘게 0건이다.** 원인 미확인 | `chanceblog.yml` 스케줄 실행 #28~#32(10-19 16:32Z ~ 10-20 11:41Z)가 모두 `success`, 봇(`github-actions[bot]`) 마지막 `_posts` 커밋은 10-19 10:57Z. 10-20 글 2건은 `shine88pc` 계정 커밋(수동). `generator.py`는 검증된 출처가 없으면 "쓸 만한 새 기사가 없습니다"로 건너뛴다 | **열림** (원인 로그 확인 필요) | Actions 로그에서 건너뜀 사유 확인(사용자/운영자). Phase 2: 건너뜀 사유 코드를 실행 요약·이력에 남김. 감시: 워치독 **STALE**(`chance` 허용 36시간) |
| **D-04** | 높음 | **구 `blogger_generator.py`**: 모델 목록이 구버전(`gemini-2.0/1.5-flash`), 검증 없는 즉시 공개 게시, 고정 10개 주제 무한 반복, Chance와 교차 중복 검사 없음, 파싱 실패 시 `제목 없음`으로 게시, `DRY_RUN`에서도 이력·초안 저장 | 코드 읽기(2026-10-20). 첫 스케줄 실행(2026-10-21 02:00 UTC) 전 | **해결** | `pipeline/`(게이트·주제·어댑터·러너)로 대체, 122+개 테스트 |
| **D-05** | 중간 | `blogger.yml`이 `git add … \|\| true`·`git pull --rebase … \|\| true`로 실패를 숨기고 의존성을 고정하지 않았다 | 워크플로 읽기, 검증기 **WF-6**·**DEP-1** | **해결** | 재작성(명시적 재시도 루프, 범위 고정, 매트릭스, 최소 권한) |
| **D-06** | 중간 | **문서와 코드의 드리프트**: 인수인계 문서는 "이슈 이미지 전용 완료, main에 push"라 기록했지만 현재 main에는 그 코드가 없다 | D-01 근거와 동일 | **완화** | 검증기 계약 검사(CONTRACT-1, REG-2·3·4), 규칙 "완료 기록 = main에 있고 검증 통과"(`AGENTS.md` §2-7). D-01의 Actions 관측이 끝나면 닫는다 |
| **D-07** | 높음 | **낡은 사본·통째 덮어쓰기로 main 회귀**, 사람 계정으로 여러 AI가 main에 직접 push | `32a2469`(D-01), `auto_sync.bat`(제거함), 이전 로컬 사본에 미커밋 변경(`인수인계/…md`) | **완화** | `AGENTS.md`·AI별 지침 파일, 검증기 **AD-1**(광고 표면), CI `guardrails.yml`. 권장(사용자): main 룰셋으로 T2 이상 PR 필수, `github-actions` 우회 허용(`SECURITY_GUARDRAILS.md` §5) |
| **D-08** | 낮음 | Jekyll이 `HANDLER.md`·`WORKLOG.md`·`AI_COLLAB.md`·스크립트를 사이트에 정적 파일로 공개한다 | `_config.yml`에 `exclude` 없음, 검증기 **EXPOSE-1** | **사용자 조치**(광고 표면 T3) | `_config.yml`에 `exclude` 추가를 사용자 승인 후 적용. AdSense 심사에 미치는 영향 검토 |
| **D-09** | 낮음 | 오래된 원격 브랜치 `feature/image-fix-20261019-0000`(main보다 64커밋 뒤, `index.html` +1/−608), `backup/issue-template-$TS`(이름에 `$`) | `git for-each-ref`, `git diff --numstat` | **사용자 조치**(삭제는 T3) | **병합 금지**. 필요한 변경만 cherry-pick. 삭제 여부는 사용자가 결정 |
| **D-10** | 중간 | 의존성이 고정되지 않아 메이저 업그레이드 때 갑자기 깨질 수 있다 | 워크플로 `pip install` 무범위, 검증기 **DEP-1** | **완화** | `google-genai>=2,<3` 등 범위 고정(3.10·3.12에서 같은 버전으로 풀림 확인: genai 2.31.0, google-auth 2.62.0, api-client 2.201.0). 첫 성공 실행 뒤 정확한 버전으로 좁힘 |
| **D-11** | 높음(풀오토 차단) | **OAuth 동의 화면이 "테스트" 상태면 refresh token이 7일 후 만료**되어 Blogger 게시가 멈춘다 | Google 문서([Manage App Audience](https://support.google.com/cloud/answer/15549945?hl=en), [Data Portability OAuth](https://developers.google.com/data-portability/user-guide/configure-oauth)). 현재 동의 화면 상태는 **미확인** | **사용자 조치** | 동의 화면을 "프로덕션"으로 전환한 뒤 토큰 발급(`HANDLER.md` §10). 만료되면 `auth_expired` → 워치독 이슈 |
| **D-12** | 중간 | 모델 이름이 `generator.py`와 `blogs.json`에 이중으로 있다 | 검증기 **REG-4**(현재는 일치) | **열림** | Phase 3에서 공용 LLM 모듈로 단일화 |
| **D-13** | 낮음 | `history.json`이 문자열 항목과 객체 항목이 섞인 스키마다 | `history.json` 읽기 | **열림** | `state.entry_titles`가 둘 다 처리한다. Phase 3에서 스키마 v1로 이관 |
| **D-14** | 중간 | **Copilot이 긴 파일의 앞부분만 읽고 나머지를 추정해 고치는 것처럼 보인다.** 비개발자가 "핵심 지점만 고쳐라"고 정밀하게 요청하기 어렵다 | 사용자 보고(2026-10-20, 청크가 약 500자 수준으로 체감). **측정·재현하지 않았고 공식 수치가 아니다** — Copilot 내부 동작은 확인하지 못했다 | **완화** | 요청을 자유 문장이 아닌 이슈 양식 항목으로 받음 + 문자 그대로 교체(AI 없이) + `pr-scope-check`가 PR의 실제 변경을 요청과 대조 + Copilot 지침 파일(`.github/copilot-instructions.md`, `.github/instructions/*.instructions.md`) + [`COPILOT_GUIDE.md`](./COPILOT_GUIDE.md). Copilot 쪽 동작은 우리가 통제할 수 없으므로 근본 해결은 아님 |
| **D-15** | 중간 | **Copilot이 만든 PR은 사람이 "Approve and run workflows"를 누르기 전에는 워크플로(Guardrails·PR Scope Check)가 돌지 않는다.** 검사가 돌지 않은 채 병합할 위험 | GitHub 변경 이력([2026-03-13](https://github.blog/changelog/2026-03-13-optionally-skip-approval-for-copilot-coding-agent-actions-workflows/))이 기본값을 "승인 필요"로 설명. 이 환경에서는 **미관측** | **사용자 조치** | 병합 전에 PR 하단 검사 결과가 보이는지 확인(`COPILOT_GUIDE.md`에 안내). 결과가 없으면 병합하지 않는다 |
| **D-16** | 중간 | **Settings → Actions → General의 "Allow GitHub Actions to create and approve pull requests"가 꺼져 있으면 `issue-edit.yml`이 PR을 만들지 못한다** | 현재 저장소 설정은 **미확인**(이 환경에서 읽을 수 없음) | **사용자 조치** (완화: PR 대신 비교 링크를 이슈에 남기는 폴백) | 설정을 켜거나, 폴백의 링크에서 사용자가 PR을 만든다(`ISSUE_EDITS.md` §6) |

## 운영 중 확인할 것 (관측 체크리스트)

| 시점 | 확인 | 정상 |
|------|------|------|
| 푸시 직후 | Actions → **Guardrails** | 3.10·3.12 모두 초록(경고는 허용) |
| 2026-10-21 02:00 UTC | Actions → **Blogger Generate** 첫 스케줄 실행 | 초록. `_blogger_drafts/`·`blogger_history.json` 커밋. 시크릿이 없으면 `generated_unpublished` |
| 2026-10-21 03:30 UTC | Actions → **Watchdog** | 이슈 없음 또는 `[Watchdog]` 이슈의 내용이 현재 상태와 일치 |
| 다음 봇 글 커밋 | Actions → **Deploy GitHub Pages** | `workflow_dispatch`로 실행됨(D-02 검증) |
| 푸시 직후 | Actions → **Sync Issue Form** (수동 실행 또는 `pages.json`·`_posts`·명세 변경 시) | 초록. 변경이 없으면 커밋 없음, 있으면 `pages.json`·양식 두 파일만 커밋(사이트 화면에는 영향이 없어 배포 dispatch는 하지 않는다) |
| 푸시 직후 | Actions → **Issue Edit** → Run workflow(`issue_number`, `dry_run` 체크) | 초록. 로그에 대상 파일·수정 방식·사후 검증 결과가 나오고 파일·PR·코멘트는 생기지 않음(D-01) |
| 이슈 양식 첫 사용 | 이슈 양식(고정 페이지 수정)으로 작은 문구 교체 1건 | 브랜치 `issue-edit/<번호>-…`와 PR(`Fixes #번호`) 생성, 이슈에 코멘트. "PR 생성 허용" 설정이 꺼져 있으면 비교 링크가 옴(D-16) |
| 이슈 요청 PR 생성 직후 | PR 하단 **PR Scope Check** 코멘트 | PASS/WARN/FAIL 중 하나가 달림. 안 보이면 Copilot PR은 "Approve and run workflows"(D-15) |
