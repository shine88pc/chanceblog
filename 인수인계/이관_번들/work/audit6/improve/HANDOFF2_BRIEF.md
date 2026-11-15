# HANDOFF2 — 저장소 도구 사본을 최신으로 맞추기 (블로그, T2, 구현자 지시서)

먼저 `C:/work/ai/audit6/improve/LANE_RULES.md` 를 끝까지 읽고 그대로 따른다(범위 한계·작업 위치·편집 함정·시험과 메모리·문서와 번호·보고서 형식).

## 왜 하는가
운영자 이슈 #198(새 세션이 '저장소를 확인하고 이어서 진행해줘' 한 문장으로 이어받을 안내)의 후속이다. 모의 시험(`C:/work/ai/audit6/improve/handoff1/fresh_eyes_report_1.md`, 막힘 4번 '도구 사본'·9번·'저장소 밖 자료' 표)에서 **저장소의 `인수인계/도구/` 안 도구 사본이 옛 버전**이라 새 PC·새 세션이 첫 보고·병합 부탁·병합완료 확인·CI 확인·감시를 못 하는 것이 드러났다: `make_request.py`·`make_info_request.py`·`next_notice_no.py`·`notice_tools.py` 는 저장소 사본과 이 PC 의 현행 사본이 크게 다르고(diff 336·20·690·502 줄) `make_merged_notice.py`·`check_notify.py`·`verify_live_counts.py`·`watch_issues.py`·`watch_heads2.sh`·`resume_check.py`·`merge_guard.py`·`cron_status_prompt_v3.txt` 는 저장소에 없다.

## 작업 위치
- 블로그 저장소 클론 `C:/work/ai/wt_r30`(요청 가지 작업 폴더 — **절대 checkout·커밋하지 않는다**). 새 작업 폴더: `git -C C:/work/ai/wt_r30 fetch origin` 뒤 `git -C C:/work/ai/wt_r30 worktree add -b ai/claude/NO-MERGE-handoff2-wip C:/work/ai/improve_wt_handoff2 origin/main` (origin/main 이 HANDOFF1 병합 등으로 4b22239 보다 앞서 있을 수 있다 — 시작 때 확인). 쓰기는 이 작업 폴더와 보고서 폴더 `C:/work/ai/audit6/improve/handoff2/` 에만. 체크포인트 `[WIP][handoff2 N] …`(`commit_as_author.py`, 메시지 파일 절대 경로, 끝에 `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`). **푸시·PR·병합 가지·force 금지.**
- 진행 기록 `C:/work/ai/audit6/improve/handoff2/progress.md` 맨 위에 '재개 순서'(PC 는 밤 23:00 재부팅), 한 줄씩 시각(`date`)과 함께.

## 현행 도구(원본 — 읽기 전용으로 가져온다)
`C:/work/ai/` 바로 아래: `make_request.py`·`make_info_request.py`·`make_merged_notice.py`·`next_notice_no.py`·`notice_tools.py`·`commit_as_author.py`·`mk_merge_branch.py`(저장소에 있음, 비교)
`C:/work/ai/scratch/`: `wait_ci.py`·`check_notify.py`·`verify_live_counts.py`·`watch_issues.py`·`watch_heads2.sh`·`resume_check.py`·`merge_guard.py`·`mk_lane_merge.py`·`mk_lane_merge_desktop.py` (그 밖에 저장소 사본이 이미 있는 `watch_light.py` 등은 비교만)
`C:/work/ai/audit6/n2/tools/memfree.py`(메모리 대기 도우미)·`C:/work/ai/cron_status_prompt_v3.txt`(현행 진행 현황 크론 프롬프트 — 2시간 주기판)
저장소 쪽 위치: `인수인계/도구/`(README.md·setup_workspace.py·`work/`·`work/scratch/`·`정기_현황_알림_프롬프트.txt`·`정기_현황_알림_본보기.md`).

## 할 일
1. **조사(먼저)**: 저장소 사본과 현행 사본의 차이를 파일별로 표로 만든다(어느 쪽이 새것인지는 `git log -1` 과 파일 안 기능 — 예: `merged` 종류·`M###` 강제·물결표 검사 유무로 판정). 저장소 안에서 이 사본들을 읽는 곳을 모두 찾는다: `grep -rn "도구/work" tests pipeline scripts` — 시험(`test_notice_tools`·`test_merged_notice_requests`·`test_wait_ci_gate`·`test_egress` 등)과 `pipeline/operator_loop.py`·`pipeline/egress.py`·`scripts/validate_repo.py` 가 이 사본의 어떤 낱말·동작을 못박았는지(예: 허용 목록·경로). **현행 사본으로 바꾸면 깨질 시험이 있는지 먼저 실제로 돌려 확인**한다.
2. **이관**: 현행 도구를 `인수인계/도구/work/`(바로 아래 도구)와 `인수인계/도구/work/scratch/`(검사·감시 읽기 도구)에 맞는 위치로 복사해 최신으로 맞춘다. 이 PC 전용 값을 일반화한다: `C:/work/ai`·사용자 경로 같은 고정 경로는 **스크립트 위치 기준(`Path(__file__).resolve().parent` 또는 작업 폴더 `W` 인자·환경 변수)** 으로 바꾸고, 사용자 이름·실제 키·토큰·블로그 ID·광고 번호는 없어야 한다(작성자 고정 `강병수 <shine88pc@gmail.com>` 은 이미 저장소 사본 `commit_as_author.py` 에 있는 기존 값이라 그대로). `memfree.py` 는 `scratch/` 쪽에 둔다(위치를 가리키는 경로를 도구 안에서 맞춘다). `cron_status_prompt_v3.txt` 는 `인수인계/도구/` 에 `정기_현황_알림_프롬프트_v3.txt` 같은 이름으로 두고 옛 230분판 두 파일 맨 위에 '이 문서는 옛 판 — 현행은 …_v3.txt' 한 줄만 더한다(삭제 금지).
3. **요청 가지 이름 정정**: `인수인계/도구/setup_workspace.py` L23 근처와 `인수인계/도구/README.md` L15 근처의 `desktop-bootstrap-merge` 를 현행 요청 가지 `ai/claude/NO-MERGE-operator-requests` 로 고친다(원격에 이 가지가 있고 `desktop-bootstrap-merge` 는 옛 가지다 — `git ls-remote` 로 확인). `setup_workspace.py` 가 새 도구 목록(위 이관분 포함)을 모두 복사하도록 고친다.
4. **README 정리**: `인수인계/도구/README.md` 의 표·절을 현행 도구에 맞게 고친다(새 도구 사용법 한 줄씩: `make_merged_notice.py`·`check_notify.py`·`verify_live_counts.py`·`watch_issues.py`·`watch_heads2.sh`·`resume_check.py`·`merge_guard.py`(**검사 전용 — 병합·푸시 기능 없음**, '직접 병합' 정책은 운영자 결정 전이므로 이 도구를 쓰라는 문장은 쓰지 않는다)·`memfree.py`). 푸시 권한이 없는 환경에서 쓸 수 있는 읽기 도구(`resume_check.py`·`verify_live_counts.py`)를 구분해 적는다. `watch_issues.py` 설명에는 **비인증 GitHub REST 는 '변경 없음(304)' 응답도 시간당 60회 한도에 센다(2026-11-15 실측)** 와 5분 주기·한도 소진 시 쉬기를 적는다.
5. **시험**: 이관한 도구에 대해 **새 시험을 더한다**(기존 시험을 약화하지 않는다): 예) `merge_guard` 의 등급 판정 함수(문서만·문서와 시험·코드·운영자 전용 경로)와 비밀 모양 감지, `watch_issues.relevant`·`line` 의 순수 함수, `resume_check` 가 비밀·고정 경로를 출력하지 않음, 이관한 파일에 이 PC 사용자 경로·고정 `C:/work/ai` 가 없음(정적), 도구 사본과 `pipeline` 의 표준 번호 정규식이 같음(기존 시험이 이미 있으면 그대로). 새 시험은 네트워크를 쓰지 않는다(가짜 응답). 이관 대상 파이썬 파일이 3.10 문법으로 돌아가는지(`python3.10 -m py_compile` 또는 시험 모듈 import) 확인한다.
6. **변경 금지**: `.github/`·광고 표면·`pipeline/` 의 제품 코드(시험이 읽는 도구 사본이 아닌 것)·레지스트리 값·`README.md`(루트, 공개 파일)·`인수인계/작업내용.md`·`WORKLOG.md`(총괄이 병합 직전에 한 줄만 더한다 — 구현자는 건드리지 않는다). 새 파일은 위 `인수인계/도구/` 아래와 `tests/` 에만.

## 시험·검사
- 블로그 시스템 파이썬 3.12(`<사용자폴더>/AppData/Local/Programs/Python/Python312/python.exe -X utf8`)와 CI 의 3.10 모양(LANE_RULES §3 — 이 PC 의 3.10 은 `C:/ccgui/v310/Scripts/python.exe`)에서 영향 모듈을 각각 돌린다: `test_notice_tools`·`test_merged_notice_requests`·`test_wait_ci_gate`·`test_egress`·`test_notice_requests`·`test_operator_loop*`·`test_validate_repo`·새 시험 + `scripts/validate_repo.py` 오류 0. 마지막에 블로그 전체 시험을 3.12 로 한 번(약 20분, 시작 전 `memfree.py 0.6`, 한 번에 하나).
- 새 시험은 고치기 전(옛 사본) 코드에서 빨강을 보이고(해당하는 경우) 변이(도구를 일부러 틀리게)로 시험이 빨개지는지 본다.

## 끝나면
최종 응답(보고서 파일 저장이 거절되면 전문을 응답에): ① 조사 표(파일별 저장소 사본 vs 현행 — 어느 쪽이 새것, 차이 요약) ② 바꾼 파일·줄(파일별 +/−, 새 파일 목록) ③ 일반화한 고정 경로 목록 ④ 시험 결과(개수 전→후·3.12/3.10·전체) ⑤ 바뀐 기존 시험 목록(강화만) ⑥ 이관하지 않은 것과 이유 ⑦ 남은 위험(새 PC 에서 `setup_workspace.py` 를 실제로 돌려 보지 못한 부분 등).
