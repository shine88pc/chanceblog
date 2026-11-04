구현 요청('P0b' — **계절 키워드 부분 일치 결함 고침**: 제안 엔진의 시기 일치 판정을 '부분 문자열' 에서 '토큰/구문 기반' 으로, **T1 코드·시험·문서, 독립 검증 대상, 병합은 운영자가**): 데스크톱 프로그램 저장소 `chanceblog-desktop`(로컬 `W\cd_repo`). `W` = 작업 폴더(인수인계/도구/README.md §1 — 새 PC 에서는 setup_workspace.py 가 만든 폴더). 운영자는 비개발자(한국어)이고 코드는 AI 가 쓴다. 원칙: 쉬운 한국어 · '모름 ≠ 0' · 결정적(같은 입력 → 같은 출력)·표준 라이브러리만·파이썬 3.10 문법.

## 왜 하나
운영자(2026-11-04 채팅, 조건 5)가 요구했다: "P0b 에서 단순 substring 검사를 Token/Phrase 기반으로 변경. 최소 회귀 예 — 그래픽카드 ≠ 금융 카드 / 신용카드 = 금융 카드 / 체크카드 = 금융 카드 / 카드값 = 금융 카드 / 카드뮴 ≠ 금융 카드. 기존 잘못된 동작을 Characterization Test 로 먼저 기록한 뒤 의도적인 변경 시험으로 교체." 기존 잘못된 동작은 P0 에서 이미 `KNOWN_DEFECT` 시험으로 기록돼 있다(`W\p25p0_report.md` §0 ② ⑤). 실측 결함: `season_fit('그래픽카드', 11)` 이 '연말정산 준비' 항목의 이어지는 낱말 '카드' 에 부분 일치해 `(70, '연말정산 준비')` 가 되고, 프로필 B(AI·PC 부품) 11월 1위 제안이 '연말정산 준비 시기에 챙겨 볼 그래픽카드 정리'(100점)가 된다(조사 `W\an_a_candidates.md` §3.5). `season_fit` 은 부분 문자열을 **양쪽**으로 본다('세금' ⊂ '부가세금액', '의료' ⊂ '의료비')는 것도 P0 가 알아냈다.

## 작업 폴더·기반
- 기준은 **P0 병합 가지**: `git -C W\cd_repo fetch origin` 뒤 `origin/ai/claude/r135-p0-topic-protect-1`(P0 — N1 `r134` 위에 쌓인 한 커밋 가지)을 기준으로 **절대 경로**로 `git -C W\cd_repo worktree add -b ai/claude/p0b-season-token-1 W\cd_wt_p0b origin/ai/claude/r135-p0-topic-protect-1`. **만약 `origin/main` 에 이미 P0(`docs/TOPIC_ENGINE_PLAN.md` 와 `tests/test_topic_protect_suggest.py` 가 있음)가 병합돼 있으면 `origin/main` 을 기준으로** 한다. 다른 `W\cd_wt_*`·`W\cd_repo` 의 작업 트리·브랜치는 건드리지 않는다(`W\cd_repo` 자체는 옛 브랜치가 체크아웃돼 있어 읽기에도 쓰지 말고 `W\cd_wt_p0b` 에서 일한다).
- 끝에 **로컬 WIP 커밋 하나**(`[WIP] P0b …`, 작성자 `강병수 <shine88pc@gmail.com>` — `python -X utf8 W\commit_as_author.py <작업 폴더 절대 경로> <UTF-8 메시지 파일 절대 경로>`: 이 도구는 `git -C` 로 돌아 **상대 경로 메시지 파일이 안 먹는다**)까지만. **push·병합 가지·PR 만들지 않는다**(내가 한다).

## 먼저 읽을 것
`AGENTS.md`, `docs/TOPIC_ENGINE_PLAN.md`(P0 계획 — P0b 절·열린 항목 4), `docs/DECISIONS.md` D-29(제안 점수 규칙)·끝 번호(**새 결정은 D-39 다음 번호**), `src/chanceblog_desktop/content/suggest_score.py`(`season_fit`·`related_items`·`_is_related`·`SeasonItem` 쓰임)·`suggest_data.py`(월 표 `SEASONS` — 항목의 시기 낱말·이어지는 낱말), `suggest.py`(시기 틀이 이어지는 씨앗에만 붙는 곳), `tests/test_topic_protect_suggest.py`(P0 의 특성 시험 — **`SeasonFitCardTest`·`GraphicsCardTopSuggestionTest`·`DeterminismAndSnapshotTest`**), `tests/test_suggest_score.py`·`test_suggest_data.py`(월 표 규칙·약 5만 조합 전수 시험 — 시간 주의)·`test_suggest.py`, 조사 `W\an_a_candidates.md` §3.2~3.5·§7.

## 만들 것
1. **일치 규칙 교체(핵심)**: 시기 일치(씨앗 낱말 ↔ 월 표의 '시기 낱말'·'이어지는 낱말')를 부분 문자열(`word in token`, 양쪽)에서 **토큰/구문 기반**으로 바꾼다. 방향: 씨앗 구를 공백·구두점으로 쪼갠 **토큰**과, 표의 낱말을 **통째 토큰 또는 표에 적힌 구문(복합어)** 으로만 견주고, 토큰 안쪽에 우연히 든 글자 조각은 일치로 보지 않는다. 한국어는 띄어쓰기 없이 붙여 쓰는 복합어(`신용카드`·`카드값`·`그래픽카드`)가 많으므로 **자료 기반**으로 한다 — 모호한 짧은 낱말('카드' 같은)은 표에서 빼거나 **구체 구문으로 풀어 적고**(예: 신용카드·체크카드·카드값·카드 혜택·카드 공제·법인카드 등 — 목록은 네가 정하고 보고에 적는다), 일치는 '구문이 토큰의 앞머리이거나 통째이고 뒤에 오는 글자가 없거나 흔한 조사(은·는·이·가·을·를·의·에·로·와·과·도·만 등 작은 허용 목록)인 경우' 같은 **경계 규칙**으로 정한다(규칙은 네가 설계하되 작고 설명 가능하게). 양쪽 부분 일치('의료' ⊂ '의료비' 같은 낱말-속-낱말)도 같은 원칙으로 정리하고, 정당했던 일치(월 표 시기에 실제로 맞는 씨앗)가 **사라지지 않게** 표의 이어지는 낱말을 필요한 구문으로 보강한다.
2. **회귀 시험(운영자 예시 + 더)**: 새 의도적 변경 시험에 ① 운영자 다섯 예시 — 신용카드 = 금융 카드(= '연말정산 준비' 시기와 이어짐), 체크카드 =, 카드값 =, **그래픽카드 ≠, 카드뮴 ≠** ② 같은 달의 '카드 혜택'·'법인카드' = ③ 추가 반례 사운드카드·교통카드·메모리카드·SD카드·크리스마스카드·카드키 — **옳고 그름을 네가 정하고 근거를 보고**(P0 가 현재 값만 기록: 지금은 모두 일치) ④ 다른 달·다른 항목의 같은 종류 위험(월 표 전 항목의 이어지는 낱말을 훑어 부분 문자열 일치와 새 규칙 일치가 **달라지는 씨앗**을 프로필 A·B 의 낱말·씨앗 전수와 보고서용 말뭉치에서 찾아 표로 보고 — 달라지는 것마다 '오탐 제거' 인지 '정당 일치 손실' 인지 판정) ⑤ 결정성·빠르기(`test_suggest_data` 약 5만 조합 시험이 지금보다 눈에 띄게 느려지지 않게).
3. **P0 의 `KNOWN_DEFECT` 시험을 의도적으로 뒤집는다**: P0 가 보고서 §0 ⑤ 에 적은 목록 — `SeasonFitCardTest` 의 KNOWN_DEFECT(그래픽카드·카드뮴 `(70,…)` → `(50, None)`)·`…other_words_that_only_contain_card…`·`…neighbouring_year_end_items…`·`…substring_both_ways…`, `GraphicsCardTopSuggestionTest` 의 KNOWN_DEFECT 3개, `DeterminismAndSnapshotTest` 의 B·11월 줄 — 를 **새 기대로 고치고** 이름의 `KNOWN_DEFECT` 를 지우되 주석에 '(P0b 가 의도적으로 바꿈, D-nn)' 이력을 남긴다. 위험 씨앗·상대지수(`search_demand`) 관련 KNOWN_DEFECT 는 **건드리지 않는다**(다른 단계 몫). 새 상위 제안 문장·점수는 직접 돌려 **새 손으로 쓴 기댓값**으로 못박는다.
4. **범위 밖**: 제목 유사도(자카드)·씨앗 추출·위험 씨앗·점수 가중치·후보 모델·화면·보관함은 건드리지 않는다. `suggest*.py` 의 공개 함수 모양(인자·반환)은 바꾸지 않는다(안쪽 판정 함수만). 새 의존성·네트워크 없음.
5. **문서(최소, 내 말로)**: `docs/DECISIONS.md` 새 행(D-39 다음 번호 — 계절 일치는 토큰/구문 기반, 운영자 승인 2026-11-04 채팅 조건 5), `docs/TOPIC_ENGINE_PLAN.md` 의 P0b 상태와 열린 항목 4 갱신(**줄 수 400 한도 — P0 가 396줄이니 줄이 늘면 다른 곳을 줄여 맞춘다**), `CHANGELOG.md` `0.0.0` 항목 아래 한 줄, 월 표 규칙을 설명하는 문서가 있으면(`ARCHITECTURE` §5 의 `suggest_data` 설명 등) 새 규칙 한 문장 — 시험이 문장을 읽는 곳은 `grep -rn "<고칠 문장>" tests` 로 먼저 확인.

## 하지 말 것
`src/` 의 위 범위 밖 변경, 기존 시험 약화·삭제(P0 KNOWN_DEFECT 의 의도적 교체는 예외 — 이유를 보고서에 표로), 새 의존성, 네트워크, 비밀, 월 표(`SEASONS`)의 **시기 낱말·이유 문장·항목 수 규칙**(`test_suggest_data` 의 '월 8~15항목·입니다로 끝·수치 금지')을 어기는 변경(이어지는 낱말만 구문으로 보강한다), 전략 문서 원문 문장 복사.

## 시험·점검
- 바뀌는/새 시험 모듈과 `test_suggest`·`test_suggest_score`·`test_suggest_data`·`test_service_suggestions`·`test_service_suggest_cli`·`test_topic_protect_*`·`test_repo_layout` 를 **한 번에 한 모듈씩** 3.12(`python -X utf8 -m unittest <모듈>`)와 진짜 3.10 `C:\ccgui\py310\python.exe -X utf8 -m unittest <모듈>` 로(PySide6 없이 돈다). PC 가 느리니(CPU 높음) 전체 실행은 하지 않는다(CI 가 한다).
- **변이 점검(스스로) 25곳 이상**: 경계 규칙의 각 갈래(조사 허용 목록 하나 빼기·구문 앞머리 규칙 뒤집기·통째 토큰 규칙 삭제·양쪽 방향 중 하나 되살리기·표의 구문 하나 지우기·'카드' 를 다시 낱말로 넣기·공백 쪼개기 방식 변경)·결정성(정렬 키)·운영자 예시 각각을 깨뜨려 시험이 잡는지. 변이는 임시 사본에서 하고 되돌린다.
- `git diff --check`, 보이지 않는 글자·BOM 0건, `C:\ccgui\dev\Scripts\ruff.exe check --select F,E9,B,UP --target-version py310 src/chanceblog_desktop/content tests/<바꾼 시험>` 지적 0.

## 진행 기록·마감·보고
- 시작 시각을 `W\p27p0b_progress.md` 맨 위에 적고 30분마다 갱신. **마감: 시작 후 90분.**
- 끝 보고서 `W\p27p0b_report.md` — **맨 앞에 운영자 단계 보고 6항목을 이 순서로**: ① 변경 파일 ② 추가·변경된 시험 ③ 전체 시험 결과(실제 `Ran N tests … OK` 줄, 전체는 CI) ④ 기존 기능 영향(제안 결과가 바뀌는 곳을 구체적으로 — 프로필 A·B × 6·11월 상위 제안 변화 표) ⑤ 다음 단계에서 발생할 동작 변화 ⑥ 데이터 마이그레이션 여부. 이어서 변이 표·달라지는 씨앗 표(오탐 제거/정당 일치 손실)·규칙 설계 설명(쉬운 말로 한 단락)·**내가 결정할 것**(예: 사운드카드 등 판단, 조사 허용 목록)·못 한 것·WIP 커밋 해시. 최종 응답은 **보고서 경로와 가장 중요한 5가지(각 두 문장 이내)** 만.
