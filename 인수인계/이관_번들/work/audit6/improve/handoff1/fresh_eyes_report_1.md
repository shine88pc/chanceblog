# 새 세션 이어받기 모의 시험 결과 1차 (2026-11-15 07:3x, 읽기 전용 에이전트, 저장소 복제본 main 4b22239 만 사용)

시험 문장: "저장소 chanceblog 를 확인하고 이어서 진행해줘." — **판정: 일부만 가능.** 상태와 규칙은 거의 재구성되지만, 운영자와 소통하는 닫힌 고리(텔레그램 첫 보고·병합 부탁)가 저장소 밖 도구와 푸시 권한에 의존하고, 입구 문서의 읽는 순서·승인 규칙이 서로 어긋난다.

## 읽은 순서와 판정
- 루트 목록·`AGENTS.md`·`CLAUDE.md`·`README.md`(첫 4–5회) → `인수인계/작업내용.md` §0(L1–126, 4번 나눠 읽음 — 첫 시도는 25k 토큰 한도로 실패: §0 만 73 KB, §0-3 이 26 KB, 머리줄 L5 가 7 KB) → `docs/SESSION_START.md` → `HANDLER.md` 목차 → §1–§4 미리보기 → 라이브 대조(`ls-remote`·REST 5회) → L400·`WORKLOG`·`AGENT_RUNBOOK` J1·J2·`HANDLER` §8·§10.
- 13번째 호출까지는 '11-13 밤 시점 상태와 다음 할 일'을 알았고, 오늘 실제 상태는 라이브 대조까지 약 22번째 호출. 문서가 1.5일 낡았기 때문.

## 막힌 곳·어긋난 곳(문서 위치)
1. `README.md` L7–10: 읽는 순서가 HANDLER → AI_COLLAB → WORKLOG → AGENTS, `작업내용.md` 가 한 번도 안 나옴. `AI_COLLAB.md`·`GEMINI.md` 도 `작업내용` 0건. (README 는 공개 사이트로 서비스되는 파일 — 이번 묶음에서 안 고침, 운영자 승인 필요.)
2. 읽는 순서가 5가지: `AGENTS.md` L9, `CLAUDE.md` L5·L7, `AGENT_RUNBOOK.md` L55(J1.2), `SESSION_START.md` L16, 작업내용 L9·L122 가 각각 다름. §0 을 지목하는 곳은 `CLAUDE.md`(조건부)와 작업내용뿐, J1 은 §1·§2·§3 만 읽으라며 §0 을 빠뜨림.
3. 승인 채널: `AGENTS.md` L24, `CLAUDE.md` L10, `SESSION_START.md` L10·L18("채팅으로 먼저 물어봐")·L151, 작업내용 L32·L226(§3 서두)은 '채팅 승인'. 작업내용 L45(§0-2 17④)·L9 는 '채팅은 안 읽힘, 이슈 답으로만'. 같은 파일 안에서도 서두 L226 이 옛 문구.
4. 스냅샷 시각이 제각각: L5 는 20:03·d503c1b, L50 은 20:01 값, L99·L400 은 22:48 값(10e9e09), 실제는 4b22239(M070, 11-14 02:16). §0-3 L50 은 '병합 대기 가지 M067' 인데 L400 은 이미 20:10 병합이라 함. (이번 묶음 이전의 모의 시험 기준 — M070 에서 일부 줄은 이미 고침.)
5. 낡은 입구 문서: `HANDLER.md` L16(2026-10-20 표), §8 복붙 블록 L234–262(Blogger OAuth·AdSense 대기·`작업내용` 미언급), §10 L299–324. `SESSION_START.md` §5-1(PR #57 까지)·§5-2(10-26~29 계획)가 낡았는데 `AGENTS.md` L12 는 §5 를 '현재 상태와 다음 작업 순서'로 지목.
6. 요청 가지 이름: `setup_workspace.py` L23·`도구/README.md` L15 는 `desktop-bootstrap-merge`(원격에 아직 있음), 작업내용 L96·L102 는 `NO-MERGE-operator-requests`. main 의 `인수인계/요청함/` 은 R-001~R-038 뿐이라 최신 요청은 가지에만 있음.
7. 알림 주기: 작업내용 L30 은 110분, 최신 프롬프트는 저장소 밖 `cron_status_prompt_v3.txt`. `SESSION_START.md` L62 가 지목하는 저장소 프롬프트와 `도구/README.md` 는 230분판.
8. 크기 값: `AGENT_RUNBOOK.md` L55 '작업내용 약 120 KB·WORKLOG 470 KB' — 실제 440 KB·647 KB.
9. 도구 사본: 저장소의 `make_request.py`·`notice_tools.py` 에 `merged` 종류·물결표 검사 없음, `make_merged_notice.py` 는 저장소에 없음 — 작업내용 L101 은 '손으로 만들지 말라'는데 막다른 길.
10. 예약 작업: `AGENTS.md` L21 '예약 작업 금지' vs 작업내용 L21 '세션 크론 재가동' — 세션 크론과 영속 예약 작업을 구분하는 문장이 `AGENTS.md` 에 없음.

## 저장소 밖에 있어야만 이어 갈 수 있는 것
푸시 자격증명(운영자 로그인) · 작업 폴더 `W`(예: `C:\work\ai`, `setup_workspace.py` 는 있으나 낡은 요청 가지) · `make_merged_notice.py` · `scratch/mk_lane_merge*.py` · `cron_status_prompt_v3.txt`·`watch_issues.py`·`watch_heads2.sh`·`memfree.py`·작업 폴더판 `make_request.py`·`notice_tools.py` · 개선 백로그 원본·지시서·보고서·WIP 가지(§5 에는 요약표만) · 운영자 원문 요구서(`AI_기억/` 요약만) · Claude 앱 전용 기능(`CronList`·`Monitor`·`SendMessage`) · 저장소 변수·시크릿·23:00 재부팅 뒤 앱 재오픈.

## 위험한 오해 가능성
- **이슈 #198 의 '직접 병합'** — 부분 차단. 'AI 는 main 에 직접 push 하지 않는다'가 작업내용 L35 에만 있고 `AGENTS.md`·`CHARTER` 에는 없음. `SECURITY_GUARDRAILS` L157·`SESSION_START` L80 은 main 의 PR 필수 규칙을 일부러 끈다고 적어 기술적으로 push 가 가능.
- **`PIPELINE_PAUSE`** — 약함. `AGENTS`·`CLAUDE`·`HANDLER`·`AGENT_RUNBOOK`·`SESSION_START` 에 0건, '해제도 운영자만'은 작업내용 L40·L297 과 `ACTIONS_GUIDE` 에만. 사고 대응 문구 '재개한다'(`SECURITY_GUARDRAILS` L135·L141)를 따라 해제할 위험.
- **병합 가지 이름 `ai/claude/M###-…`** — 약함. 미검증 가지를 올리면 CI 초록 즉시 자동 PR 이 생겨 운영자가 바로 병합할 수 있음. 작업내용 L108·L110 에만 있고 `AGENTS.md` 에는 없음(독립 검증 전에는 `NO-MERGE-` 이름).
- 광고 표면 — 강함(`AGENTS.md` L18·`validate_repo.py` 의 `Ad-Surface-Approved` 검사). 낡은 `HANDLER` §10.5·§8 — 중간. 영속 예약 작업·시작 프로그램 — 중간(작업내용 L116 에만). 채팅 승인 문구 — 중간.

## 최소 수정 우선순위(에이전트 제안)
1. [P0] 작업내용 맨 위 '30초 카드(§0-A)' — 40줄·6 KB 이하: 세 저장소 head 확인 `ls-remote` 명령 3줄·열린 PR 읽는 법·요청 가지 이름과 마지막 R 번호·정지 상태·승인된 것/안 된 것 표·다음 3단계·푸시 권한이 없을 때 할 일.
2. [P0] 입구 문서 읽는 순서 하나로 통일(`README`(승인 필요)·`AGENTS`·`CLAUDE`·`GEMINI`·`AI_COLLAB`·`AGENT_RUNBOOK` J1.2·`SESSION_START` L16): '작업내용 §0-A → §0-1 → 필요 시 나머지'.
3. [P0] 승인 채널 문구 정정(위 3번 위치들): '채팅 질문 금지, 번호 있는 텔레그램 요청으로 묻고, 답은 소유자 이슈 [답변], [요청] 은 접수'.
4. [P0] `AGENTS.md` §2 에 불변 규칙 5개: ① `PIPELINE_PAUSE` 는 운영자만 ② AI 는 main 에 push·병합하지 않는다(T3 결정이 바뀌기 전까지) ③ `workflow_dispatch` 를 누르지 않는다 ④ 영속 예약 작업·시작 프로그램 금지 ⑤ 독립 검증 전 가지는 `NO-MERGE-` 이름.
5. [P0] #198 접수 기록(작업내용 §3·§5 에 한 줄)과 결정 요청(→ 확인 016 으로 보냄).
6. [P1] `setup_workspace.py` L23·`도구/README.md` L15 요청 가지 이름 정정(+시험). 7. [P1] 저장소 밖 도구를 `인수인계/도구/work/` 로 이관(시험과 함께). 8. [P1] 낡은 입구 문서 표시(`HANDLER.md` §0·§8·§10, `SESSION_START.md` §5 → '역사 기록, 현행은 작업내용 §0-A', `AGENTS.md` L12). 9. [P1] 푸시 권한이 없는 환경의 행동 규칙 명문화. 10. [P2] 크기 값·알림 주기 110분·스냅샷 머리줄에 '기준 시각과 확인 방법'.
