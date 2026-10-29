# Copilot 지침

이 저장소의 규칙 정본은 [`AGENTS.md`](../AGENTS.md)다. 아래는 Copilot용 핵심 요약이다. 일의 절차는 [`docs/AGENT_RUNBOOK.md`](../docs/AGENT_RUNBOOK.md), 위임 설계는 [`docs/AGENT_DELEGATION.md`](../docs/AGENT_DELEGATION.md).

## 먼저 어떤 일인지 가른다

- **A. 수정 요청**: 이슈 양식(고정 페이지·게시글 이미지)으로 접수된 문구·링크·SEO·이미지 수정 → "수정 요청을 받으면".
- **B. 위임 작업**: 저장소 소유자가 연 `[요청]` 이슈에 **소유자가 직접 Copilot 을 지정**했고 `진행 범위`가 '구현·시험까지'일 때만 → "위임 작업".
- 그 밖(`[답변]` 이슈, 소유자가 아닌 사람의 이슈, 진행 범위가 '논의·준비까지만')은 파일을 고치지 말고 PR 설명에 계획·질문만 적고 멈춘다.

## 수정 요청을 받으면 (A)

1. **수정할 파일을 처음부터 끝까지 읽은 뒤** 고친다. 앞부분만 읽고 나머지를 추정하지 않는다. 다 읽지 못했다면 그렇게 말하고 멈춘다.
2. 요청의 문구·위치를 **원문과 글자 하나까지 대조**한다. 못 찾으면 비슷한 곳을 고치지 말고 질문한다.
3. **요청한 부분만** 최소로 수정한다. 다른 문장·서식·링크·front matter를 정리하거나 되돌리지 않는다.
4. 확신이 없으면 추측하지 말고 PR 설명에 "확인 필요"로 적는다. 끝나면 diff에 요청과 무관한 변경이 없는지 확인하고 PR 설명에 **바꾼 곳 / 바꾸지 않은 곳**을 적는다.
5. 이슈의 `대상 페이지`·`수정 항목`·`변경 전`·`변경 후`가 정확한 지시서다. `변경 전`이 있으면 `변경 후`로 **그대로** 교체한다(링크는 URL만, SEO는 `title`/`description` 줄만). PR 본문에 `Fixes #이슈번호`를 넣는다(`[공통] PR 변경 범위 검사`가 쓴다).
6. **광고 표면은 고치지 않는다**: `index.html`, `privacy.md`, `about.md`, `contact.md`, `_includes/`, `_layouts/`, `_config.yml`, `robots.txt`, `ads.txt`, 사이트 인증 파일 `googlee86895dfeddcdd45.html`·`naver8e7a71b78d49e6f323e7ad60ffb862a8.html`. 소유자가 이슈 양식으로 요청했어도 파일을 바꾸지 말고 PR 설명에 "광고 표면 변경 요청 — 자동 처리 양식이나 세션형 AI 가 필요(승인 표시는 Copilot 이 쓸 수 없고 검증기가 막는다)"라고 쓰고 멈춘다. `.github/workflows/`·`pipeline/`·`scripts/`·비밀 파일은 **소유자가 이슈 양식으로 그 문구를 명시적으로 요청한 경우만** 고친다. 광고 코드(`adsbygoogle`, `ca-pub-`)는 어떤 경우에도 추가·삭제하지 않는다.

## 위임 작업 (B)

1. 먼저 읽기: `AGENTS.md` → `docs/AGENT_RUNBOOK.md`(해당 일의 절차) → `인수인계/작업내용.md`. 같은 파일을 만지는 열린 PR·브랜치가 있으면 멈추고 PR 설명에 적는다.
2. **T0~T2만** 한다. T3(광고 표면, 시크릿·계정, `mode` 변경, 새 블로그·플랫폼, 삭제, 정책·톤, 비용 증가)는 하지 말고 PR 설명 맨 위에 "T3 승인 필요 — 하지 않음"이라고 쓴다.
3. **고치지 않는 곳(T3로 본다)**: 위 광고 표면 목록 전부, 비밀 파일, `.github/` 전체(워크플로·이슈 양식·이 지침 파일들·CODEOWNERS), `scripts/validate_repo.py`, `pipeline/blogs.json`(어느 필드든), `pipeline/edits/`(자동 수정 범위 — `NEVER_ALLOW` 를 줄이면 T3), `AGENTS.md`·`CLAUDE.md`·`GEMINI.md`, `docs/CHARTER.md`·`docs/SECURITY_GUARDRAILS.md`, `requirements*.txt`, `.gitignore`. 검사 장치나 자기 규칙을 스스로 고치면 그 검사는 힘을 잃는다 — 필요하면 PR 설명에 이유를 적고 세션형 AI 에게 넘긴다.
4. 커밋 메시지에 `Ad-Surface-Approved:`를 **절대 쓰지 않는다**. 승인은 사람만 하며 검증기(AD-2)가 Copilot 이 쓴 표시를 거부한다. 자동 commit/push·예약 작업·강제 push·삭제도 하지 않는다.
5. 코드는 Python 3.10 문법(3.12 전용 f-string 금지), 시험은 네트워크 없이 성공·실패 경로 모두. 먼저 `pip install -r requirements-dev.txt pyflakes vermin`. 비밀·토큰을 코드·로그·PR에 쓰지 않는다. 실패를 `except: pass`·`|| true`로 숨기지 않는다.
6. 검증: `python scripts/final_checks.py --base origin/main` 결과를 PR 본문에 그대로 붙인다. 못 돌렸거나 건너뛴 단계(종료 코드 3)는 "실행 필요"로 적고 통과로 쓰지 않는다.
7. `pipeline/` 코어·`scripts/`를 고치면 T2다. PR 설명 맨 위에 "독립 검증 필요 — 작성 AI: Copilot"이라고 쓴다(검증은 다른 주체가 한다).
8. 같은 PR에서 `인수인계/작업내용.md` 해당 행과 `WORKLOG.md` 최상단 항목을 갱신한다. 새 현황 문서를 만들지 않는다. 한 PR = 한 가지 일, 최소 diff, 파일 통째 덮어쓰기·요청 밖 정리는 금지.
9. 운영자에게 물어야 하면 PR 설명 맨 위 "운영자 확인 필요"에 번호 목록으로 쓴다. 그 글은 **승인이 아니며**, 운영자는 텔레그램만 보므로 세션형 AI 가 요청 파일로 대신 묻는다.

## 운영자 요청함 이슈

이슈 제목이 `[답변] `·`[요청] ` 로 시작하면 운영자 요청함의 응답·새 일 요청이다(`blog-control` 라벨이 없고 위 수정 양식과 무관). 승인은 이슈 작성자 login 이 저장소 소유자이고 **그리고** `author_association` 이 `OWNER` 이며, 양식 `[답변]` 의 요청 번호가 AI 가 보낸 요청의 번호와 같을 때만 그 요청 파일에 적힌 항목에 한해서 승인으로 본다. 양식 `[요청]`·양식 밖의 빈 이슈·이슈 코멘트·요청서 파일은 접수만 하고 승인이 아니다(T3 가 필요하면 AI 가 번호 있는 `decision` 요청으로 다시 묻는다).(AGENTS.md 8번) `[답변]` 이슈로는 파일을 고치는 PR 을 만들지 않는다. `[요청]` 이슈는 소유자가 Copilot 을 직접 지정했을 때만 위 "위임 작업"으로 처리한다.

## 읽을 문서

[`HANDLER.md`](../HANDLER.md) · [`docs/SECURITY_GUARDRAILS.md`](../docs/SECURITY_GUARDRAILS.md) · 코드 작업이면 [`docs/ENGINEERING_GUIDE.md`](../docs/ENGINEERING_GUIDE.md)

변경 후 `python scripts/validate_repo.py`와 `python -m unittest discover -s tests`를 통과시킨다.
