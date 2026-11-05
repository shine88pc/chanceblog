# AI 도구 모음 (인수인계/도구)

> **누구를 위한 것인가**: 이 저장소와 데스크톱 저장소에서 일하는 AI 세션(새 PC·새 세션 포함)이 **운영자 요청 보내기·병합 부탁·검사 읽기·감시** 같은 반복 작업을 같은 방식으로 하게 하는 작은 스크립트들입니다. 모두 **표준 라이브러리만** 쓰고, 비밀·키·개인 PC 경로가 없습니다(공개 저장소). 운영자가 직접 쓰는 것이 아니라 AI 가 쓰는 도구입니다. 설명 정본은 이 파일이고, 일하는 규칙은 [`docs/AGENT_RUNBOOK.md`](../../docs/AGENT_RUNBOOK.md)(J1~J12)·[`docs/SESSION_START.md`](../../docs/SESSION_START.md)·[`인수인계/요청함/README.md`](../요청함/README.md) 입니다.

## 1. 작업 폴더 만들기 (새 PC 에서 한 번)

```text
python -X utf8 인수인계/도구/setup_workspace.py <작업 폴더 W>
```

`W` 는 짧은 경로의 빈 폴더(예: `C:\work\ai`)입니다. 이 명령이 하는 일: 도구 복사 → 저장소 두 개 clone → 요청 가지 작업 폴더 만들기. **스크립트들은 아래 이름의 폴더를 그대로 가정합니다.**

| 폴더(`W` 아래) | 내용 |
|---|---|
| `wt_r30` | 블로그 저장소 `chanceblog` clone, **가지 `ai/claude/desktop-bootstrap-merge`**(요청 파일을 쌓는 가지 — `인수인계/요청함/R-nnn_*.md`). `git worktree add` 로 임시 작업 폴더를 만들 때의 기준 저장소이기도 함 |
| `cd_repo` | 데스크톱 저장소 `chanceblog-desktop` clone(기본 가지 main — 병합 가지·작업 폴더를 만들 때의 기준 저장소) |
| `scratch` | 검사·감시를 **읽기만** 하는 도구(아래 3절) |
| `W` 바로 아래 | 요청 파일·병합 가지·커밋 도구(아래 2절), **지시서·보고서·병합 부탁 초안**(아래 7절), 작업 중 생기는 초안·메시지 파일 |

**속보 자료**: 요청 가지(`wt_r30`)에 `인수인계/이어가기_최신.md`(진행 요약)와 `인수인계/이어가기_자료/`(갱신된 보고서·검증 결과)가 있으면 `setup_workspace.py` 가 자료 파일을 `W` 로 **덮어 복사**합니다 — 이 폴더(`work/`)의 같은 이름 파일보다 요청 가지의 것이 최신입니다(병합 없이 갱신됨). 새 세션은 `이어가기_최신.md` 를 `작업내용.md` §0 다음으로 읽습니다.

작성자(커밋·병합 가지)는 모든 도구가 `강병수 <shine88pc@gmail.com>` 로 고정해 만듭니다(운영자 계정 — AI 가 만든 커밋도 이 작성자이고 본문 끝에 `Co-Authored-By` 줄로 AI 를 밝힙니다). **push 자격증명은 운영자가 새 PC 에서 Git 이 묻는 창에 직접 로그인**합니다(AI 는 비밀번호·토큰을 입력하지 않고, force push 는 하지 않습니다).

## 2. 요청·병합 부탁 도구 (`W` 바로 아래)

| 도구 | 쓰는 법 | 하는 일 |
|---|---|---|
| `make_info_request.py` | `python -X utf8 make_info_request.py <R-번호> <슬러그> <초안 파일>` | 안내(`kind: info`)·결정(`kind: decision`) 요청 파일을 `wt_r30/인수인계/요청함/R-nnn_슬러그.md` 로 만든다. **링크(`http`)·`<…>` 패턴·길이(제목 80·요약 300자) 위반이면 만들지 않는다** |
| `make_request.py` | `python -X utf8 make_request.py <R-번호> <슬러그> <초안> <시험 문구> <검증 문구> [이전 문장] [소유자/저장소:브랜치]` | 병합 부탁(`kind: merge`)까지 만드는 본체. **`kind: merge` 는 마지막 인자(`소유자/저장소:브랜치`)가 필수이고 그 브랜치 머리 커밋의 자동 검사가 모두 끝나 초록이어야 파일이 만들어진다**(운영자 지시 2026-11-03: 병합 부탁은 검사가 이미 끝난 뒤에만). 초안의 `@TESTS@`·`@VERIFY@`·`@PREVIOUS@` 를 채운다 |
| `mk_merge_branch.py` | `python -X utf8 mk_merge_branch.py <저장소 경로> <트리 원본 커밋> <부모 ref> <커밋 메시지 파일> <새 가지 이름>` | **한 커밋 병합 가지**를 만든다 — 트리는 원본 커밋의 것, 부모는 지정한 ref 하나(작업 폴더를 건드리지 않는 `git commit-tree`). 같은 이름이 있으면 실패(되감기 금지, 새 이름 `-2`) |
| `commit_as_author.py` | `python -X utf8 commit_as_author.py <작업 폴더 절대 경로> <메시지 파일 절대 경로> [--only 경로 …]` | 작성자를 고정해 UTF-8 메시지 파일로 커밋한다(한글 환경 변수·셸 인코딩 문제를 피함). **`git -C` 로 돌아 상대 경로 메시지 파일은 안 먹는다** |
| `pipsafe.py` | `python -X utf8 pipsafe.py <대상 파이썬 exe> <패키지==버전> …` | 공식 PyPI 휠만, 나온 지 14일 미만·yanked 이면 멈추는 안전 설치(개발 도구용) |

요청 번호는 **J3**: 블로그 저장소 모든 원격 브랜치의 `인수인계/요청함/` 번호 최댓값 + 1(데스크톱 병합 가지 이름의 번호 `rNNN` 은 블로그 refs 에 안 보이니 사용 중인 번호를 `작업내용.md` §2 에서 확인해 비워 둔다).

## 3. 검사·감시 읽기 도구 (`W/scratch`)

| 도구 | 쓰는 법 | 하는 일 |
|---|---|---|
| `runs_by_sha.py` | `python -X utf8 runs_by_sha.py <소유자/저장소> <sha7> […]` | 한 번의 읽기로 여러 커밋의 실행 상태를 보인다 |
| `wait_ci_multi.py` | `python -X utf8 -u wait_ci_multi.py <소유자/저장소> <최대 분> <간격 초> <커밋 SHA 전체> […]` | 여러 브랜치 머리의 검사가 끝나길 기다린다(공개 REST 한 건씩, 시간당 60회 한도를 아낀다) |
| `wait_ci.py` | (`make_request.py` 가 불러 쓴다) | 병합 브랜치의 검사가 초록인지 공개 웹 목록으로 확인 |
| `ci_web.py` | `python -X utf8 ci_web.py <소유자/저장소> [개수] [페이지 경로]` | **REST 한도(시간당 60회)를 다 썼을 때** 쓰는 읽기 도구 — 공개 Actions 웹 페이지에 실린 JSON 만 읽어 최근 실행 N 개(번호·상태·브랜치·걸린 시간·제목)를 한 줄씩 보인다(로그인·API 없음) |
| `run_steps_times.py`·`run_annotations.py` | `python -X utf8 run_steps_times.py <소유자/저장소> <run id> [주석 1/0]` | 한 실행의 job·단계 결과와 **단계별 소요 시간**·주석을 읽는다(실패 원인은 주석에 있다) |
| `watch_light.py`·`watch_desktop.py` | `cd W/scratch && WATCH_SINCE=$(date +%s) python -X utf8 -u watch_light.py` | 블로그/데스크톱 저장소를 **API 한도 없이**(git ls-remote + 공개 웹) 지켜보며 새 PR·병합(main 이동)·새 실패 실행·소유자 이슈·`텔레그램수신` 이슈를 한 줄씩 알린다. **한 번 켜면 29분 뒤 끝나므로 끝났다는 알림이 오면 다시 켠다**(Claude 의 Monitor 도구로 돌린다) |

REST 호출은 로그인 없이 IP 당 시간당 60회입니다 — 한 번 쓰면 그 시각부터 1시간 창이 열리고(`https://api.github.com/rate_limit` 은 한도를 안 쓴다) 남은 수가 12 아래면 도구가 간격을 늘립니다.

## 4. 늘 하는 흐름 (그대로 따라 하면 되는 순서)

**A. 운영자에게 안내·결정 요청 보내기**: 초안(표 중심 쉬운 한국어, 링크 금지, 앞머리 `id`·`kind`·`title`·`summary`·`urgency`·`created`) → `make_info_request.py` → `wt_r30` 에서 `python scripts/validate_repo.py --root .`(오류 0) → 메시지 파일(제목 끝 `(요청 파일, 병합 대상 아님) [대상: 공통]`, `Co-Authored-By` 줄) → `commit_as_author.py … --only <요청 파일>` → `git push origin ai/claude/desktop-bootstrap-merge`(**GitHub 가 가끔 'Internal Server Error'·'failure' 로 거절한다 — 15~20초 뒤 다시**) → 알림 워크플로 `ai-request.yml` 성공 확인(`GET /repos/<저장소>/actions/workflows/ai-request.yml/runs?branch=ai/claude/desktop-bootstrap-merge`).

**B. 병합 부탁 보내기(변경을 main 에 넣을 때)**: 구현·시험 → **독립 검증**(구현자와 다른 AI, T2 이상 필수) → `mk_merge_branch.py` 로 한 커밋 가지(제목 `[R-nnn] 짧은 이름 [대상: …]`, 가지 이름 `ai/claude/rnnn-짧은이름-1`, 부모 `origin/main`) → push → 검사(블로그 약 2.5분, 데스크톱 4칸 약 20분)가 **초록**이 되면 `make_request.py … 소유자/저장소:가지` 로 요청 파일 → A 의 나머지 단계. **한 번에 한 요청만**, 요청에 쓸 가지 말고 다른 가지를 미리 올려 노란 배너를 늘리지 않는다. 요청 안내문 틀은 `docs/AGENT_RUNBOOK.md` J3·J4 와 `인수인계/PR_병합_방법.md` 를 따른다.

**C. 병합 확인**: 운영자가 병합하면 감시가 알린다 — `git diff <가지> origin/main` 이 비었는지(블로그는 봇 파일만 달라도 됨), main 검사·배포 초록을 AI 가 직접 확인한다(운영자에게 보고를 요구하지 않는다).

**D. 텔레그램으로 받은 글 읽기**: 운영자가 봇에게 보낸 글은 `[공통] 텔레그램 수신 가져오기`(`telegram-inbox.yml`)가 공개 이슈(라벨 `텔레그램수신`)로 옮긴다. **정기 실행(cron)은 GitHub 사정으로 몇 시간째 안 돌 수 있다** — AI 가 `ai/claude/**` 브랜치를 올릴 때마다 한 번 더 읽는다. 점검할 때마다 읽으려면 main 에서 새 가지를 만들어 올린다: `git push origin origin/main:refs/heads/ai/claude/inbox-poll-<n>`(내용 변경 없음, 검사 한 번이 돎, 쓴 뒤 `git push origin --delete` 로 지워도 새 실행이 생기지 않는다). 접수일 뿐 승인이 아니다(승인은 번호 있는 요청에 대한 소유자 `[답변]` 이슈 또는 채팅뿐).

## 5. 정기 현황 알림 크론 (운영자 상시 지시)

[`정기_현황_알림_프롬프트.txt`](./정기_현황_알림_프롬프트.txt) 의 전문을 Claude 세션의 `CronCreate`(표현식 `7 * * * *` — 매시 7분, 24시간, 반복) 프롬프트로 그대로 넣는다. 세션이 바뀌면(PC 이전·재시작) **다시 만들어야 한다**(세션 안 크론은 앱이 꺼지면 사라진다). 규칙 요약: 진행 중인 일이 있으면 마지막 현황 알림에서 **50분 이상** 지났을 때만 새 `[R-nnn] 진행 현황 알림 — 월-일 시:분 기준`(info)을 보낸다, 시간대 제한은 없다(밤·새벽에도 보낸다 — 운영자 지시 2026-11-05), 앱 푸시·채팅 질문 없음.

## 6. 함정 (이 환경에서 실제로 겪은 것)

- Bash heredoc 은 역슬래시·`\u` 를 망가뜨린다 → 파이썬은 **파일로 만들어 실행**한다. 도구가 `\u200b` 같은 이스케이프를 실제 보이지 않는 글자로 바꿔 저장하는 경우가 있어 스크립트에서는 `chr()` 을 쓴다. PowerShell 은 빈 문자열 인자를 버린다 → 빈 인자가 필요한 `make_request.py` 는 `make_info_request.py`(래퍼)나 Bash 로 부른다.
- Git Bash 가 `git show origin/main:경로` 의 인자를 경로로 오해한다 → `MSYS_NO_PATHCONV=1` 을 앞에 붙인다.
- 전경 `sleep` 은 막힌다 → `python -c "import time; time.sleep(N)"` 이나 Monitor/백그라운드 작업을 쓴다. 이 PC 는 느리고 에이전트가 함께 돌면 메모리가 모자라니 무거운 시험은 한 번에 하나.
- 한글 커밋 메시지는 UTF-8 파일 + `git commit -F`(위 `commit_as_author.py`). 시스템 `core.autocrlf=true` 는 끄지 않는다(작업 사본은 CRLF, 커밋은 LF).
- 시험이 `인수인계/작업내용.md` 의 낱말을 못박는 곳이 있다 — 고치기 전에 `grep -rn 작업내용 tests`.
- 블로그 시험은 `PYTHONPATH="tests;."`(Windows 구분자) 로 `python -X utf8 -m unittest <모듈>`, 데스크톱은 `PYTHONPATH="src;tests;."`. 진짜 3.10 시험이 필요하면 python.org 의 3.10.11 을 사용자 수준으로 설치한다(개발 도구 목록은 `docs/SESSION_START.md` §2-4).
- 블로그 main 은 봇이 자주 커밋한다 → 가지를 만들기 직전에 `git fetch` 하고, main 이 앞서가면 새 main 위에서 다시 만든다.
- 이 PC 의 파일 편집 도구는 보이지 않는 글자(`\u200b` 등)나 `\` 가 든 파이썬을 가끔 망가뜨린다 → 파일을 쓴 뒤 실행하기 전에 한 번 읽어 확인하고, 정규식 치환의 대체 문자열 끝 역슬래시는 `lambda m: …` 로 준다.

## 7. 지시서·보고서·병합 부탁 초안 (`work/` → `W` 로 복사됨)

`setup_workspace.py` 가 `work/*.md` 를 `W` 바로 아래로 복사합니다. 지시서 안의 `W\파일` 은 이 복사본을 가리킵니다. **현황의 정본은 `인수인계/작업내용.md` §0 이고 이 문서들은 거기서 부르는 자료입니다**(진행 중인 일의 가지·커밋은 §0-3).

| 파일 | 무엇 |
|---|---|
| `p27p0b_brief.md` | **P0b**(계절 일치 고침) 구현 에이전트에게 그대로 줄 지시서 — P0 독립 검증·보고 뒤에 시작 |
| `verify_p1_brief.md` | **P1**(`topics/` 순수 엔진 핵심) 독립 검증 지시서 — 새 검증 에이전트에게 줌 |
| `verify_nv_brief_final.md`·`verify_p0_brief_final.md` | N1·P0 독립 검증 지시서(이전 PC 에서 이미 돌렸다 — 결과가 없으면 수정분 중심으로 다시) |
| `p24nv_brief.md`·`p25p0_brief.md`·`p26p1_brief.md` | 구현 지시서 본보기(N1·P0·P1) — P2 이후 지시서를 쓸 때 모양을 따른다(코드 위치·원칙·시험·변이 점검·마감·보고 6항목) |
| `p25p0_report.md`·`p26p1_report.md`·`p24nv_progress.md` | 구현 보고서(맨 앞이 **운영자 단계 보고 6항목**)·N1 진행 기록 — 병합 부탁 요청의 보고에 인용 |
| `an_a_candidates.md`·`an_b_channels.md`·`an_c_ui_tests_docs.md` | 데스크톱 코드 조사(후보·제안·보관함·프로필 / 채널·초안·서비스·연결·이관 / 화면·시험·CI·문서) — main `3b1294b` 기준 |
| `r131_draft.md`·`r131_operator_answer.md` | 5채널 전략 분석·결정 요청(R-131)의 초안, 운영자 답(조건 7개)과 내 해석·구현자별 변경 |
| `r134_draft.md`·`r134_fill.py`·`r135_draft.md`·`r135_fill.py` | N1(R-134)·P0(R-135) **병합 부탁 요청 초안과 채우개** — 검증 문구를 `r134_verify.txt`·`r135_verify.txt` 로 써 두고 `python -X utf8 r134_fill.py R-134 시작HH:MM 끝HH:MM "NN분 NN초" 가지이름 "21파일"` 로 요청 파일을 만든다(검사 초록 관문 포함, 자리표시가 남으면 실패) |

개발 도구 위치(`C:\ccgui\...`)는 `docs/SESSION_START.md` §2-4 표를 따라 만들면 지시서가 그대로 맞습니다.
