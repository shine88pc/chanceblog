# 에이전트 공통 규칙 (데스크톱 `chanceblog-desktop` 작업 — 모든 구현·검증·설계 에이전트가 먼저 읽는다)

> 2026-11-23 저장소 사본 안내 — 이 문서는 11-11 데스크톱 주제 엔진(P2b) 갈래의 구현자에게 줬던 공통 규칙이다(그때의 기준 커밋·`W\p29_*.py` 같은 도구 이름은 옛 상태). 갈래 지시서가 공통으로 읽는 최신 규칙은 `audit6/improve/LANE_RULES.md` 이다.

운영자는 비개발자(한국어)이고 코드는 AI 가 쓴다. 쉬운 한국어로 쓰고, 칭찬·장황한 요약 없이 사실만 쓴다. `W` = 작업 폴더(옛 PC 에서는 `C:` 드라이브의 `work` 아래 `ai` 폴더였고, 새 PC 의 W 는 도구 README 의 `setup_workspace.py` 가 만든 폴더다).

## 환경
- Windows 11, 시스템 `python` = 3.12, 진짜 3.10 = `C:\ccgui\py310\python.exe`, 개발 도구 `C:\ccgui\dev\Scripts\`(ruff·vermin·coverage·hypothesis). 로컬 저장소 `W\cd_repo`(데스크톱 clone), 기준 커밋: P2a 검증본 `1c307c8a1264535b9dfc14fcbca058057e9cf719`, P2b 구현 WIP `c1f5e3f167494bf609f27f6405a62cf31b89cdd7`(작업 폴더 `W\cd_wt_p2b`, **읽기만**), main = `ec76b74`(P2a 병합 커밋, 트리 = `1c307c8` 트리 + `docs/P4_REVIEW_ITEMS.md` 한 파일).
- 시험 실행: `python -X utf8 -m unittest <모듈>` 을 **모듈 하나씩**, `PYTHONPATH=<작업폴더>\src;<작업폴더>\tests;<작업폴더>`. 도우미 `python -X utf8 W\p29_run.py <파이썬> <작업폴더> [-v] 모듈 …` 이 모듈을 하나씩 돌려 결과 줄만 보여 준다(`-v` 는 실패 본문). 주제 엔진 시험 모듈 = `tests\test_topics_*.py` 15개(+새 것), 함께 돌릴 것: `test_repo_layout`·`test_season_match`·`test_topic_protect_candidates`·`test_content_candidates`·`test_suggest_score`·`test_errors_catalog`. 전체 시험은 돌리지 않는다(CI 가 함).
- 점검 도구(있는 것 재사용): `W\p29p2b_purity.py <작업폴더>`(순수성 런타임 점검), `W\p29p2b_mutate.py`·`p29p2b_rerun.py`(P2b 변이 도구 — 본떠 새 것을 만들어도 됨), 이전 검증자 도구 `W\ver_p2b_x\tools_backup\*.py`(위생·AST 순수성·가져오기 목록·공격·차분 예).
- 이 PC 는 느리고 여유 메모리가 1.5GB 안팎이다: 무거운 일은 **한 번에 하나**, 시작 전 여유 메모리 ≥0.6GB 확인(`Get-CimInstance Win32_OperatingSystem`), 프로세스는 **자기가 시작한 PID 만** 끝낸다(이름 `python` 일괄 종료 금지), 창을 띄우지 않음, 전경 `sleep` 금지(기다림은 짧은 확인 반복), 7분 넘게 걸리는 시험은 끊고 보고에 적는다. **이 PC 는 매일 23:00 에 강제 재부팅**되어 에이전트도 끊긴다 — 22:50 이후에는 무거운 일을 새로 시작하지 말고 중간 결과를 먼저 저장한다.

## 도구 함정(실제로 겪음)
- **파일은 Write/Edit 도구로 쓴다.** Bash heredoc 은 역슬래시를 망가뜨린다(스크립트 안에서 역슬래시는 `chr(92)`). 쓴 뒤 읽어서 확인한다.
- `core.autocrlf=true` 이다 — 끄지 말 것. 기존 파일은 줄바꿈 스타일을 유지한다. 새 파일은 LF 로 써도 git 이 정규화한다.
- 커밋은 `python -X utf8 W\commit_as_author.py <작업 폴더 절대 경로> <UTF-8 메시지 파일 절대 경로>`(작성자는 도구의 고정 작성자 상수 — 이름·메일은 `commit_as_author.py` 에 있고 문서에는 쓰지 않는다) — 메시지 파일은 **절대 경로**, 끝에 `Co-Authored-By: Claude Sonnet 5.5` 줄(보낸이 전용 주소는 `audit6/improve/LANE_RULES.md` 와 같은 것). **push·PR·병합 가지는 만들지 않는다**(코디네이터가 한다). GitHub·네트워크·텔레그램 호출 금지, 비밀·내 PC 경로를 산출물에 쓰지 않는다.
- 검증기 SEC-2 가 문서·시험 문자열에서 텔레그램 토큰 모양(숫자 6–12자리·콜론·영숫자 30–50자)을 막는다 — 그런 모양을 쓰지 않는다.
- `scripts/sync_errors.py` 는 `docs/TROUBLESHOOTING.md` 표에서 `errors/catalog.py` 를 만든다(`--check` 로 확인). 새 오류 코드를 만들지 않는다(기존 `CONTENT_INVALID`·`CANDIDATE_INVALID` 사용).
- Git Bash 에서 `git show <ref>:<경로>` 는 경로 변환으로 깨진다 — `MSYS_NO_PATHCONV=1` 을 앞에 붙인다.

## 지켜야 할 약속(프로젝트 공통)
- 주제 엔진 `src/chanceblog_desktop/topics/` 는 **순수 계산**이다: 표준 라이브러리만, 파이썬 3.10 문법, 파일·네트워크·시계·난수·AI·프로세스 없음, 같은 입력은 늘 같은 결과(해시 시드·입력 순서와 무관), 입력 객체는 바꾸지 않는다. 날짜·시각은 인자로 받는다. 아직 `topics/` 밖 어디서도 부르지 않는다(`test_nothing_outside_the_package_uses_it_yet…` 시험이 지킨다).
- **'모름 ≠ 0'**: 알 수 없는 값은 None/모름이고 0점이 아니다. 후보를 숫자만으로 지우거나 제외하지 않는다(표시·중지 상태만 — 지울지는 운영자가 정한다).
- **전략 문서 원문은 이 PC 에 없다.** 원문이 있어야 정할 수 있는 모든 표·낱말 목록·문구는 **'초기값 — 전략 원문 확인 전'** 으로 코드·문서·시험에 표시하고, 한 곳에 모으고, 시험이 값 목록을 못박아 고칠 때 의식적으로 같이 고치게 한다. 전략 요약은 `<사용자폴더>\Desktop\KCY\Chance\인수인계\AI_기억\topic-strategy-r131-answers.md`·`topic-selection-strategy-v100.md`, 계획 문서는 저장소 `docs/TOPIC_ENGINE_PLAN.md`(**400줄 한도** — 지금 정확히 400줄).
- 운영자 R-149 기본값(변경 금지): A 전략 원문 없이 진행 · B 협찬 15% 는 `generation_enabled`(네이버 A·B)에만 · C '시기 도달+관심도 하락'은 보류로 강제하지 않고 점수만 낮춤 · D 관심도 사용 4단계 그대로(Trend 상대 지수와 `search_demand_count` 를 섞지 않음) · E 채널 사이 같은 주제는 일곱 항목 중 4개 이상 달라야 함. 점수 가중치·구간(80/65/50)·중복 40/60/75·씨앗 180일·30/20 도 바꾸지 않는다.
- **화면(UI)·서비스·저장소·명령줄·월 표(`suggest_data.py`)·`suggest_score.py`·`check/claims.py` 는 바꾸지 않는다**(운영자 지시: UI 는 P4 전까지 수정 금지). 새 의존성 금지.
- 운영자가 채팅으로 준 요구서·요청서 **원문은 저장소에 올리지 않는다**: 산문을 복사해 넣지 말고(표의 낱말·시험 예문은 허용), 파일을 저장소에 두지 않는다. 실제 씨앗·실제 블로그 글 제목을 저장소에 복사하지 않는다(시험 자료는 '예시' 가짜).
- 결정 번호는 `docs/DECISIONS.md` 에 이어서(P2b 가 D-46–D-49 를 썼다 → 새 것은 D-50 부터, 끝 번호를 직접 확인), 변경 이력은 `CHANGELOG.md`, 구조는 `docs/ARCHITECTURE.md` §5 `topics/` 행.
- 산출물에서 운영자 화면에 보일 수 있는 문장(안내문·이유·진단·오류 설명)에는 **파이썬 목록 꼴(`['a', 'b']`)·`Enum` 표기·내부 코드(`health_check`·`BRAND_ONLY` 같은 식별자)** 를 쓰지 않는다.
