# 운영자 답(R-131) — 진짜 채팅, 2026-11-04 약 19:40 (구현자는 이 파일을 먼저 읽고 반영한다)

> 이 파일은 `S` 안 작업 문서이고 저장소·요청 파일에 올리지 않는다. 아래 1절은 운영자가 채팅으로 쓴 글 그대로이고, 2절 이하는 내 해석·확정 사항이다. 구현자의 이전 지시서(`p25p0_brief.md`·`p26p1_brief.md`)와 다른 곳은 **이 파일이 이긴다**.

## 1. 운영자 원문

R-131 검토 결과, 기본안으로 진행해 주세요.

선택값: A=1 B=1 C=1 D=1 E=1 F=1 G=1 H=1

다만 아래 조건을 함께 반영해 주세요.

### 1. Search Trend 지표 분리
E=1은 승인하지만 기존 절대 검색량 필드를 Search Trend 상대지수로 덮어쓰거나 재해석하지 마세요.
다음 데이터를 분리해 주세요.
- search_demand_count: 실제 검색 횟수 데이터가 있을 때만 사용
- trend_ratio: NAVER Search Trend 상대지수
- trend_status: 상승/보통/하락/데이터 부족
- trend_period: 비교 기간
- trend_compared_group: 비교 키워드 그룹
Search Trend 값은 UI에서 `최근 관심도(상대값)`로 표시하고 `월 검색량`이나 `회` 단위를 사용하지 마세요.
기존 search_demand가 어떤 공급자의 어떤 의미인지 먼저 확인하고, 의미가 불명확하면 Migration하지 말고 Legacy 필드로 유지해 주세요.

### 2. 후보 연결 추적
새 엔진 후보를 기존 Candidate로 변환할 때 다음 연결 관계를 보존해 주세요.
- engine_candidate_id
- legacy_candidate_id
- draft_plan_id
- source_topic_id
- seed_id
- channel
새 점수, 추천 이유, Trend 상태와 Seed 출처가 초안 단계에서 유실되지 않게 해 주세요.

### 3. 상태 축 분리
기존 작업 흐름 상태와 새 추천 구간은 별도 필드로 유지해 주세요.
작업 상태 예: NEW, REVIEW, SELECTED, DRAFTING, DRAFT_READY, PUBLISHED
추천 구간 예: RECOMMENDED, GENERAL, HOLD, EXCLUDED
두 개를 하나의 status 필드로 합치지 마세요.

### 4. Seed 및 설정 백업
저장소에는 Schema, Template, 예시와 규칙만 두고 실제 활성 Seed는 사용자 데이터에 저장해 주세요.
아래 파일과 데이터는 백업·복원 범위에 포함해 주세요.
- channel_profiles.json
- seeds.json
- calendar.json
- topic_engine.db
API Key와 Credential은 백업에서 제외해 주세요.

### 5. 계절 키워드 부분 일치 결함
P0b에서 단순 substring 검사를 Token/Phrase 기반으로 변경해 주세요.
최소 회귀 예:
- 그래픽카드 ≠ 금융 카드
- 신용카드 = 금융 카드
- 체크카드 = 금융 카드
- 카드값 = 금융 카드
- 카드뮴 ≠ 금융 카드
기존 잘못된 동작을 Characterization Test로 먼저 기록한 뒤 의도적인 변경 시험으로 교체해 주세요.

### 6. 구현 범위
현재 제안대로 첫 활성 채널은 Naver A/B만 적용해 주세요.
GitHub Pages와 Blogger A/B는: 프로필 / 발행 이력 읽기 / 중복 검사용 정규화 까지만 구현하고 후보 생성 기능은 기본 비활성화해 주세요.

### 7. 단계 진행
P0 → 독립 검증 → 결과 보고 후 P0b 순서로 진행해 주세요.
각 단계 완료 시 다음을 보고해 주세요.
- 변경 파일
- 추가·변경된 시험
- 전체 시험 결과
- 기존 기능 영향
- 다음 단계에서 발생할 동작 변화
- 데이터 Migration 여부
위 조건으로 P0 작업을 시작해 주세요.

## 2. 확정 사항(내 해석 — 구현자가 따른다)

1. **결정 A~H 는 모두 1(기본값) 승인.** 계획 문서·결정 행에서 'R-131 답 대기'를 **'운영자 승인(2026-11-04 채팅)'** 으로 바꾼다.
2. **Search Trend 지표 분리(조건 1)** — 엔진 후보의 필드 이름은 운영자가 정한 그대로: `search_demand_count`(정수 또는 없음. **실제 검색 횟수 출처가 있을 때만**, 값이 있으면 출처 이름 칸(`search_demand_source`)도 필수) · `trend_ratio`(0~100 정수 또는 없음, NAVER Search Trend 상대지수) · `trend_status`(값 4개: `rising`·`flat`·`falling`·`insufficient` — 화면 한국어 상승/보통/하락/데이터 부족) · `trend_period`(비교 기간 한 줄 글) · `trend_compared_group`(비교 키워드 그룹, 글 목록) · (더해서) `trend_queried_on`(조회일 — 오래된 데이터 판정용). **API 장애와 '데이터 부족'의 구분(전략 §15)** 은 `trend_status` 가 아니라 별도 `data_status`(`sufficient`·`partial`·`insufficient`·`unavailable`)로 한다. 상대지수는 어떤 경우에도 `search_demand_count` 로 흘러가지 않는다(시험으로 못박는다). 이름·키·화면 문구 어디에도 `월 검색량`·`검색량 예측`·`volume`·`조회수` 같은 말과 `회` 단위를 Trend 값에 쓰지 않는다 — 화면 표시는 `최근 관심도(상대값)`.
   **기존 `Candidate.search_demand`(월간 검색 수요)·`related_blog_results`·`mobile_share` 는 Legacy 로 그대로 둔다.** 새 필드로 덮어쓰기·재해석·자동 이전을 하지 않는다. **먼저 의미를 조사해 기록한다**(P0 의 일): 어떤 경로로 값이 들어오는가(수동·CSV·명령줄)·공급자 기록 칸이 있는가·문서(ARCHITECTURE §9·DECISIONS·README)와 `connections` 의 `naver_searchad` 설계 흔적이 무엇을 가리키는가·점수 환산(`opportunity` 로그 눈금)·화면 라벨. 결론 후보: '설계상 네이버 검색광고 키워드 도구의 월간 검색 수(PC+모바일)를 사람이 적거나 CSV 로 넣는 값이나 공급자·측정 기간을 적는 칸이 없어 **출처가 불명확**하다' → **Legacy 유지, 새 `search_demand_count` 와 자동 이전 없음**(사용자가 출처를 알고 있는 값만 나중에 사람이 명시적으로 옮길 수 있게 하는 길은 후속 결정). 새 점수(`topics/score.py`)는 Legacy `search_demand` 를 읽지 않는다.
   **E=1 의 해석**: `최근 관심도(상대값)` 라벨은 **새 Trend 지표 칸**의 이름이다. 기존 절대 횟수 칸의 라벨을 상대값 이름으로 **바꿔 달지 않는다**(재해석 금지). 기존 칸(`월 검색량` 라벨)은 Legacy 입력값임을 표시하고 Trend 칸과 섞어 보이지 않게 한다 — 화면 처리는 P4 에서 세부 설계(이 일 P0 는 문구를 바꾸지 않는다).
3. **후보 연결 추적(조건 2)** — 새 엔진 후보를 기존 `Candidate` 로 투영(P3)할 때 보존할 연결: `engine_candidate_id`·`legacy_candidate_id`·`draft_plan_id`·`source_topic_id`·`seed_id`·`channel`, 그리고 새 점수(6항목+최종+구간)·추천 이유·Trend 상태(`trend_*`)·Seed 출처가 **초안 단계에서 유실되지 않게** 하는 출처 스냅샷(`provenance`). 기존 `Candidate` 는 모르는 칸을 거절하므로 연결·스냅샷은 **엔진 쪽 새 저장소의 연결 표**에 두고 초안 계획을 만들 때 서비스 층이 붙인다. `draft_plan_id` 는 지금 초안 계획이 저장되지 않으므로 '계획 입력(후보·옵션·날짜)의 안정된 해시 식별자' 같은 정의를 P3 에서 정한다 — **정의는 계획 문서에 열린 항목으로 적는다.** P1 은 순수 자료형(`CandidateLink`·`Provenance`)과 JSON 왕복·'빠짐 없음' 시험까지.
4. **상태 두 축(조건 3)** — 필드 이름을 `work_status`(작업 흐름)와 `recommendation_band`(추천 구간)로 분리한다. 작업 흐름 값: 후보 단계에 **저장하는 값**은 기존 `Candidate` 와 같은 NEW·REVIEW·SELECTED·HOLD·REJECTED, DRAFTING·DRAFT_READY·COPIED·PUBLISHED 는 기존처럼 **연결된 글(프로젝트)의 상태에서 계산하는 표시값**(`FOLLOW_ON` 대응 — 저장하지 않음). 추천 구간 값: `RECOMMENDED`(80+)·`GENERAL`(65~79)·`HOLD`(50~64)·`EXCLUDED`(0~49) + 점수 없음(`UNRATED`). **하나의 `status` 로 합치지 않는다.** HOLD 가 두 축에 있으니(작업 축 HOLD = 사람이 누른 보류, 구간 축 HOLD = 점수 50~64 의 자동 보류함 90일) 이름·주석·문서에서 구분한다.
5. **저장·백업(조건 4)** — 저장소(공개)에는 스키마·템플릿·예시·규칙만 두고 **실제 활성 Seed·채널 프로필 수정본·캘린더 수정본은 사용자 데이터 폴더**에 둔다. 사용자 데이터 파일 이름은 정확히: `channel_profiles.json`·`seeds.json`·`calendar.json`·`topic_engine.db`. **백업·복원 범위에 이 네 개를 포함**하고(SQLite 는 SQLite 백업 방식, JSON 은 무결성 검사 뒤 복사·복원은 바꾸기 전에 모양 확인), **API 키·Credential 은 백업에서 제외**(키는 윈도 자격 증명 관리자에만 있고 파일에 없음 — 어떤 백업 파일에도 키 모양이 없다는 시험). 새 저장소는 **별도 SQLite 파일 `topic_engine.db`**(자체 `application_id`·`user_version`·마이그레이션·사전 사본·원복·읽기 전용 열기, 기존 `Store` 의 관례를 따름)이고 **기존 보관함 `chanceblog.db`(판 2)는 바꾸지 않는다 → 기존 데이터 마이그레이션 없음**(`topic_engine.db` 는 처음 쓸 때 새로 생김). 폴더 위치는 데이터 폴더 아래 `topic_engine\` 하위를 추천하고 P3 에서 확정. **R-131 §7 의 '보관함 판 2→3' 은 이 지시로 대체된다**(옛 앱으로 되돌려도 `chanceblog.db` 는 그대로 열림 — 장점).
6. **계절 키워드 부분 일치(조건 5)** — 순서: (P0) 현재 잘못된 동작을 **특성 시험으로 먼저 기록**: 지금은 '카드'가 '연말정산 준비' 시기의 이어지는 낱말이라 `그래픽카드`·`신용카드`·`체크카드`·`카드값`·`카드뮴` 다섯 모두 걸린다(그래픽카드·카드뮴이 오탐 = KNOWN_DEFECT, 나머지 셋은 의도한 일치) — 실제 함수 이름·값으로 못박는다. (P0b) 부분 문자열(`word in token`)을 **토큰/구문 기반**으로 바꾸고 위 다섯 개를 의도한 변경 시험으로 교체: 그래픽카드 ≠ 금융 카드·신용카드 = 금융 카드·체크카드 = 금융 카드·카드값 = 금융 카드·카드뮴 ≠ 금융 카드(+ 사운드카드·카드 키(교통카드는?) 등 추가 반례는 구현자가 정해 보고).
7. **구현 범위(조건 6)** — 첫 활성 채널은 Naver A/B 뿐. GitHub Pages·Blogger A/B 는 **프로필·발행 이력 읽기·중복 검사용 정규화** 까지만 구현하고 **후보 생성은 기본 비활성**(`generation_enabled=False`). 채널 프로필에는 두 칸을 둔다: `generation_enabled`(후보 생성 — naver_a·naver_b 만 True)와 `history_enabled`(이력 읽기·정규화 — 5채널 모두 True).
8. **단계 진행·보고(조건 7)** — P0 → **독립 검증** → 결과 보고 → P0b. 각 단계 보고에 **6항목**을 이 순서로: ① 변경 파일 ② 추가·변경된 시험 ③ 전체 시험 결과 ④ 기존 기능 영향 ⑤ 다음 단계에서 발생할 동작 변화 ⑥ 데이터 마이그레이션 여부. 구현자 보고서도 이 6항목을 맨 앞에 둔다.

## 3. 에이전트별 바뀌는 점

**P0 구현자(`p25p0_brief.md`)**
- 특성 시험 G2 에 **다섯 카드 예시의 현재 동작**을 더한다(위 2절 6번). 이미 만든 시험과 겹치면 합친다.
- **기존 `search_demand` 의미 조사 결과**를 `docs/TOPIC_ENGINE_PLAN.md` 한 절과 보고서에 적는다(2절 2번의 질문 목록에 답하고 결론은 'Legacy 유지, 자동 이전 없음'이 맞는지 판단 — 다르게 보이면 근거와 함께 보고). 특성 시험은 'Legacy 는 절대 횟수 눈금으로 환산된다'(G3, 이미 있음)에 더해 '새 필드가 아직 없다/Legacy 필드와 이름이 겹치지 않는다' 수준만.
- 계획 문서·결정 행을 위 확정 사항으로 갱신: Trend 필드 5+2개 이름, 상태 두 축 이름·값, 연결·출처 스냅샷, 저장은 별도 `topic_engine.db`+JSON 3개·백업 4개 포함·키 제외, 기존 보관함 불변(마이그레이션 없음 — '판 3' 표현 삭제), 활성 채널 Naver 만·나머지 3채널은 프로필·이력 읽기·정규화만, P0b 회귀 예, `draft_plan_id` 정의는 열린 항목, A~H '운영자 승인'. 결정 행 번호는 지시서대로(D-36 부터, 연속 시험 확인).
- 보고서 맨 앞 6항목(위 2절 8번).

**P1 구현자(`p26p1_brief.md`)** — 모델 변경 요약
- `TopicCandidate` 의 Trend 칸: `relative_interest` 묶음을 없애고 위 2절 2번의 `trend_ratio`·`trend_status`(4값)·`trend_period`·`trend_compared_group`·`trend_queried_on` 으로, `search_demand_count`+`search_demand_source` 추가(값이 있으면 출처 필수, 점수 계산은 P1 에서 읽지 않음), `data_status`(4값). 필드 이름 검사 시험은 '`search_demand_count` 하나만 예외로 허용하고 `volume`·`검색량`·`조회수` 는 금지'로.
- 상태 두 축: `status`·`grade` 대신 `work_status`·`recommendation_band`(값 RECOMMENDED·GENERAL·HOLD·EXCLUDED·UNRATED, 점수에서 계산). 작업 축 값은 `content.candidates` 상수 재사용.
- 새 순수 자료형 `CandidateLink`(`engine_candidate_id`·`legacy_candidate_id`·`draft_plan_id`·`source_topic_id`·`seed_id`·`channel`)와 `Provenance`(점수 6항목·최종·구간·추천 이유·`trend_*`·`data_status`·Seed 출처·`source_topic_id`·`channel`) — `Provenance.of(candidate)`·엄격 JSON 왕복·'후보의 이 값들이 하나도 빠지지 않고 스냅샷에 담긴다' 시험(빠뜨린 칸 변이를 잡아야 함).
- 채널 프로필: `enabled` → `generation_enabled`(naver_a·naver_b 만 True)+`history_enabled`(5채널 True). 사용자 데이터 파일 이름 상수(`channel_profiles.json`·`seeds.json`·`calendar.json`·`topic_engine.db`)를 작은 모듈(`topics/layout.py`)에 이름만 둔다(저장은 P3).
- P1 의 병합 부탁은 P0b 가 끝난 뒤에야 보낸다(내가 순서를 지킨다) — 구현은 계속 진행.
