# 개선 묶음(lane) 구현·검증 공통 규칙 — 자체 개선 진행용 (2026-11-13 14:2x 작성)

운영자가 2026-11-13 마지막 채팅으로 '프로그램의 성능 향상을 위한 개선은 AI 가 스스로 진행하고 진행 상황만 알려 달라'고 했다. 그 허락의 범위와 한계는 기억 `operator-comms-messages-issues-only-2026-11-13` 와 이 문서가 정한다. 구현자·수정자·검증자 모두 이 문서를 먼저 읽는다.

## 0. 범위와 한계 (넘으면 즉시 멈추고 보고서에 적는다)
- 허락된 것: T0(문서 표기)·T1(시험·문서만)·T2(제품 코드, 동작 영향이 작고 시험으로 지킬 수 있음). 병합은 **운영자만** 한다(병합 부탁 → 운영자 병합 → AI 가 직접 확인). 병합 가지는 **독립 검증이 끝난 뒤에만**, 총괄이 한 커밋으로 만든다. **구현자는 WIP 커밋까지만 — push·PR·병합 가지·force 금지.**
- 금지(T3 — 운영자 승인이 따로 필요): `.github/` 아래 모든 파일, 광고 표면·`ads.txt`·AdSense, 공개 글(`_posts`)·고정 페이지, 레지스트리·설정 값 변경(예: `pipeline/blogs.json`·`source_registry.json` 의 값), 발행 정지 변수 `PIPELINE_PAUSE`, 제공처 켜기, 비밀·키·토큰, 예약 작업, 새 외부 접속·외부 쓰기, 의존성·잠금 파일, `vendor/`(앱의 블로그 사본), 데스크톱 앱의 외부 쓰기 스위치. 필요해 보이면 **제안만** 보고서에 적는다.
- 시험을 약화하거나 지우지 않는다(바꾼 기존 시험은 전부 나열하고 강화만). 안전 장치를 완화하지 않는다.
- 비밀·광고 번호·실제 블로그 이름·개인 정보는 어떤 파일·출력·커밋 메시지에도 쓰지 않는다. 시험의 가짜 비밀은 `CANARY_` 로 시작하는 조립 문자열.
- 문서·주석·요청 글에 ASCII 물결표(~)와 http 링크를 쓰지 않는다(숫자 범위는 en dash).

## 1. 작업 위치 (실제 경로)
- **블로그** `shine88pc/chanceblog`: 로컬 클론 `C:/work/ai/wt_r30` — **요청 가지 작업 폴더라 절대 `git checkout`·커밋하지 않는다.** 새 작업 폴더: `git -C C:/work/ai/wt_r30 fetch origin` 뒤 `git -C C:/work/ai/wt_r30 worktree add -b ai/claude/NO-MERGE-<슬러그>-wip C:/work/ai/<작업폴더> origin/main`.
- **데스크톱 앱** `shine88pc/chanceblog-desktop`: 로컬 클론 `C:/work/ai/cd_repo`(main) — 같은 방식 `git -C C:/work/ai/cd_repo worktree add -b … C:/work/ai/<작업폴더> origin/main`.
- 쓰기는 **그 작업 폴더와 보고서 폴더(`C:/work/ai/audit6/improve/<슬러그>/`)** 에만. 다른 작업 폴더(`wt_*`·`cd_wt_*`)는 읽지도 쓰지도 않는다.
- 체크포인트 커밋: `python -X utf8 C:/work/ai/commit_as_author.py <작업폴더> <메시지 파일의 절대 경로>` — 제목 `[WIP][<슬러그> N] …`, 끝에 `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`. 메시지는 UTF-8 파일(한글을 셸 인자로 넘기지 않는다). 메시지 파일 경로는 **반드시 절대 경로**(상대 경로면 저장소 기준으로 읽혀 실패한다).
- Git Bash 에서 `git show origin/main:경로` 꼴은 `export MSYS_NO_PATHCONV=1` 을 먼저(경로 변환 방지).

## 2. 편집 함정 (이 PC 에서 실제로 겪은 것)
- 작업 사본 파일은 CRLF 와 LF 가 섞여 있고 `core.autocrlf=true` 라 커밋은 LF 로 정규화된다 — 줄 끝 경고는 무시. **정확히 한 곳씩 바꾸는 파이썬 도우미**(바이트 치환, 옛 글이 정확히 한 번 나오지 않으면 실패)를 쓰거나 Edit 도구를 쓰되, 바꾼 뒤 `git diff --stat` 으로 의도한 줄만 바뀌었는지 본다(전체 파일이 바뀌면 줄 끝이 뒤집힌 것 — 되돌린다).
- Write/Edit 도구는 소스 안의 백슬래시-u 네 자리(유니코드 이스케이프)와 백슬래시-b 를 진짜 글자로 바꿔 넣는다 — 소스에는 가시 글자나 `chr()` 를 쓴다. Bash 도구는 `\\` 를 `\` 로 한 번 풀어 넘기고, 한글·따옴표가 섞인 heredoc 이 실패하는 일이 있다 — 긴 스크립트·메시지는 Write 도구로 파일을 만든다.
- 파이썬은 **3.10 문법**(CI 는 3.10·3.12 둘 다, 이 PC 의 시스템 파이썬은 3.12 뿐 — 3.12 에서만 통과하는 동작에 기대지 않는다). 표준 라이브러리만(기존 의존성 외 새 패키지 금지).
- 리눅스 CI 교훈: 윈도에서 만든 해시·경로 구분자·CRLF 가 값에 들어가는 골든 비교 금지(경로는 `as_posix`, 파일 비교는 줄 끝 통일 뒤), `os.name`·`msvcrt`·`ctypes.windll` 의존 시험은 건너뛰기 표시, **다른 묶음의 결정 번호·전체 최댓값을 못박는 단언을 새로 만들지 않는다**.

## 3. 시험·메모리 (이 PC 는 여유 메모리 0.3–1GB)
- 시험·빌드는 **한 번에 한 프로세스**, 시작 전 `python -X utf8 C:/work/ai/audit6/n2/tools/memfree.py 0.6`(모자라면 기다렸다 다시). 프로세스는 **자기가 띄운 것만 PID 로** 정리(이름·패턴으로 끝내기 금지). 네트워크 접속 금지(시험은 외부 접속 0).
- **블로그**: 시스템 파이썬 `<사용자폴더>/AppData/Local/Programs/Python/Python312/python.exe -X utf8`. 검사 `scripts/validate_repo.py`(오류 0 이어야 함), 시험 `python -X utf8 -m unittest discover -s tests`(개별 모듈 지정은 `_bootstrap` 임포트 오류가 난다 — 모듈 하나만 돌리려면 `-s tests -p test_이름.py`). 문서·시험만 바꿔도 CI 는 전체 시험을 돌린다(기존 시험이 문서 표를 훑는다) — 푸시 전 전체를 **한 번**. 작업 기록 문서를 건드릴 때는 먼저 `grep -rn 작업내용 tests`(시험이 낱말을 못박는다).
- **데스크톱 앱**: 3.12 Qt 없음(CI 모양) `C:/ccgui/dev/Scripts/python.exe`, 3.12 Qt 있음 `C:/ccgui/v/Scripts/python.exe`(offscreen: 환경 변수 `QT_QPA_PLATFORM=offscreen`, 실제 창을 띄우지 않는다), 3.10 `C:/ccgui/v310/Scripts/python.exe`. 전체 시험은 `scripts/ci_shard.py <조각> 3`(조각 0–2; 오래 걸리면 새·바뀐 모듈과 보안·문서를 읽는 시험으로 줄이고 줄인 것을 보고서에), 같은 모양을 흉내 내는 도우미 `C:/work/ai/run_shard_like.py`. 느린 모듈(`test_pages_publish`·`test_vendor_core`·`test_service_repolock`·`test_service_recovery`·`test_service_unpushed`·Qt 모듈)은 전체 실행에서 제외하고 필요할 때만 따로.
- **알려진 흔들림(고치는 것은 이 묶음 밖 — 보고서에 날짜·모듈·메시지만 적고 무시하지 않는다)**: `test_service_lock`(TwoRealProcessesTest)은 윈도 venv 파이썬에서만 항상 한 건 실패(`Popen.pid` ≠ 자식의 `os.getpid()`), `test_service_quota_legacy_locale` 은 윈도 파일 쓰기 경쟁으로 가끔 실패, `test_service_write_json` OrderTest·`test_topicdb_backup`·`test_service_own_posts`(임시 폴더 PermissionError)가 가끔 흔들린다. 전체 실행에서 실패 한두 건이 나오면 이 목록인지 먼저 본다.
- 새 동작마다 **시험 + 변이 시험**: 새 시험은 고치기 전 코드에서 **빨갛게 나오는 것**을 보인다(되돌려 실행해 확인), 변이는 사본에서 코드를 일부러 틀리게 해 시험이 빨개지는지 본다(항목마다 3개 이상·묶음 전체 8개 이상, 원복 뒤 sha256 로 사본 동일 확인).

## 4. 문서·번호
- 문서는 **새 절·새 줄을 끝에 덧붙이고 기존 줄을 재배치·재정렬하지 않는다**(병합 충돌 줄이기).
- 결정 번호: 앱 `docs/DECISIONS.md` 의 현재 최댓값은 D-470(작업 시작 때 다시 확인, 다음 번호부터), 블로그 결함 번호 `docs/DEFECT_REGISTER.md` 의 현재 최댓값은 D-331(역시 다시 확인). 새 결정은 멈추거나 묻지 말고 `C:/work/ai/operator_delegation_rules.md` 우선순위(최신 운영자 결정 > 확정 문서 > 기존 기록 > 정상 동작 > 데이터 보존 > 보안 > 최소 변경 > 안전한 기본값)로 스스로 정해 근거와 함께 적는다.
- 앱의 `CHANGELOG.md`·`docs/` 안내가 바뀌면 그곳에 한 줄. 운영자가 읽는 문장은 쉬운 한국어.

## 5. 진행 기록·보고서
- 진행은 보고서 폴더의 `progress.md` 에 한 줄씩(시각은 `date` 로 읽은 값, **PC 가 밤 23:00 에 재부팅되므로 재개 순서를 맨 위에**). 재부팅·중단 뒤에도 같은 지시로 이어서 한다(작업 폴더·WIP 커밋이 남아 있다).
- 끝나면 보고서 `report.md`: ① 바꾼 파일·줄 ② 항목 → 고침 → 시험 → 변이 표 ③ 시험 개수 전→후(3.12/3.10, 앱은 CI 조각 모양 실행) ④ 바뀐 기존 시험 목록(강화만) ⑤ 흔들림 관찰 ⑥ 남은 위험·한계 ⑦ 운영자에게 물을 항목(있으면). 저장이 거절되면 최종 응답에 전문. 최종 응답은 짧게(새 머리 해시·시험 개수·남은 일).

## 6. 독립 검증자 공통
- 구현자와 다른 눈으로 본다. 작업 폴더·보고서를 **읽기 전용**으로 연다(고치지 않는다 — 고칠 곳은 지적만). 시험 실행은 **'시험' 렌즈 검증자 한 명만**(나머지는 읽기와 아주 작은 파이썬 확인만), 그 한 명도 한 번에 한 프로세스.
- 지적은 심각도(필수·권장·정보)와 위치(파일:줄)·이유·고치는 방법으로. 의심스러우면 필수 쪽으로 판단한다. '문제 없음'이면 무엇을 어떻게 확인했는지 적는다(읽은 파일·돌린 명령).
