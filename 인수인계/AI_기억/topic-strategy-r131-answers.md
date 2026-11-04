---
name: topic-strategy-r131-answers
description: 5채널 주제 선정 전략 — 운영자 R-131 답(A~H=1)과 7조건, 단계 P0~P5, 설계 요약, 코드 조사에서 얻은 사실(2026-11-04)
metadata:
  type: project
---

운영자가 2026-11-04 19:05 채팅으로 '5개 채널 주제 선정 전략 v1.0.0' 문서를 첨부하고(**원문은 저장소 금지** — 이전 PC 에만 있었으니 운영자가 다시 첨부해야 읽을 수 있다), 현재 `chanceblog-desktop` 구조를 먼저 분석한 뒤 구조 제안·단계별 순서를 보고하라고 했다. 보고·결정 요청이 R-131(19:24)이고, 운영자 답이 19:40 에 왔다. 이 문서는 그 답과 설계를 **내 말로** 적은 것이다(원문 복사 아님). 요약본은 [topic-selection-strategy-v100.md](./topic-selection-strategy-v100.md).

## 운영자가 처음 준 원칙 (분석 요청 때)
1. 기존 정상 기능·화면을 시험으로 먼저 보호 2. 현재 PySide6 구조·데이터 흐름 재사용 3. 주제 엔진을 화면·초안 생성과 분리 4. NAVER Search Trend 는 선택적 제공자로 격리 5. API·AI 가 없어도 규칙 기반 후보 생성이 돌아야 함 6. 기존 GitHub Pages·Blogger 운영은 직접 바꾸지 않음 7. Naver A/B 부터 구현하되 5채널로 확장 가능 8. 구현 전에 먼저 보고(관련 코드·재사용·새 데이터 모델·바꿀 화면·단계 순서·기존 기능 영향·마이그레이션 여부·시험 계획·결정 사항).

## R-131 에 대한 운영자 답 (2026-11-04 19:40)
- **선택값: A=1 B=1 C=1 D=1 E=1 F=1 G=1 H=1 — 모두 기본안.** 기본안의 뼈대: 새 순수 패키지 `topics/` 를 기존 코드 옆에 얹고 기존 `Candidate`·`suggest*` 는 그대로 둔다.
- **조건 7개**
  1. **Search Trend 지표 분리**: 필드를 `search_demand_count`(진짜 절대 검색 건수가 있을 때만)·`trend_ratio`·`trend_status`(상승/보통/하락/데이터 부족)·`trend_period`·`trend_compared_group` 으로 나눈다. 화면 문구는 `최근 관심도(상대값)`, Trend 에 `월 검색량`·`회` 를 쓰지 않는다. E=1 은 승인하되 **기존 절대 검색량 필드를 덮어쓰거나 재해석하지 않는다** — 기존 `search_demand` 가 어느 제공자의 무슨 값인지 먼저 조사하고 불명확하면 이관하지 않고 Legacy 로 둔다.
  2. 새 엔진 후보를 기존 Candidate 로 바꿀 때 `engine_candidate_id`·`legacy_candidate_id`·`draft_plan_id`·`source_topic_id`·`seed_id`·`channel` 을 보존하고, 새 점수·이유·Trend 상태·Seed 출처가 초안 단계에서 사라지지 않게 한다.
  3. **상태 두 축**: 작업 상태(NEW, REVIEW, SELECTED, DRAFTING, DRAFT_READY, PUBLISHED)와 추천 구간(RECOMMENDED, GENERAL, HOLD, EXCLUDED)을 한 `status` 로 합치지 않는다.
  4. 저장소에는 스키마·틀·예시·규칙만, **실제 활성 Seed 는 사용자 데이터**. 백업·복구에 `channel_profiles.json`·`seeds.json`·`calendar.json`·`topic_engine.db` 를 포함하고 **API 키·자격 증명은 제외**.
  5. **P0b**: 계절 키워드의 단순 부분 문자열 검사를 토큰/구문 기반으로 바꾼다 — 그래픽카드 ≠ 금융 카드, 신용카드·체크카드·카드값 = 금융 카드, 카드뮴 ≠. 잘못된 현재 동작을 먼저 **특성 시험(Characterization Test)** 으로 기록한 뒤 의도한 변경 시험으로 교체한다.
  6. 첫 활성 채널은 **Naver A/B** 뿐. GitHub Pages·Blogger A/B 는 프로필·발행 이력 읽기·중복 정규화까지만, 후보 생성은 기본 꺼짐.
  7. **순서: P0 → 독립 검증 → 결과 보고 → P0b.** 단계마다 보고 6항목 — 변경 파일 / 추가·변경 시험 / 전체 시험 결과 / 기존 기능 영향 / 다음 단계에서 달라질 동작 / 데이터 마이그레이션 여부.

## 단계 계획 (R-131 에서 정한 순서)
P0 기존 동작 보호 시험·계획 문서(`docs/TOPIC_ENGINE_PLAN.md`) → P0b 계절 일치 고침 → P1 순수 엔진 핵심(`topics/`: channels·model·score·select·link·layout) → P2 Seed·확장·캘린더·중복·이력 읽기 → P3 저장(`topic_engine.db`)·서비스·명령줄 → P4 화면(문구 `최근 관심도(상대값)`) → P5 실제 Search Trend 호출(T3, 운영자 승인·NAVER API HUB 결정 R-122 뒤).
- 새 결정 번호: N1 이 D-35, P0 이 D-36~D-39, P0b 는 D-40 이후.
- 다른 안전 틀(N1): NAVER API HUB 검색어 트렌드 호출의 한도·장부·Fail-Closed 장치(호출 코드 없음) — 상세는 [naver-api-hub-handoff-v100.md](./naver-api-hub-handoff-v100.md).

## 설계 요약 (구현자들에게 준 틀)
- 새 순수 패키지 `chanceblog_desktop/topics/` — 채널 프로필(`channels`), 엔진 후보 모델(`model`, `TopicCandidate` 약 32필드), 점수(`score`: 6요소, 알 수 없는 요소는 빼고 가중치를 다시 나눔, 구간 경계 80/65/50), 선택(`select`: 상위 노출 5개 상한·같은 묶음 2개 상한·부족하면 GENERAL 에서만 채움), 연결·출처 추적(`link`), 파일 이름(`layout`).
- 저장은 별도 `topic_engine.db` + JSON 3개(기존 `chanceblog.db` 판 2 불변 = 마이그레이션 없음).
- Trend 는 `TrendProvider` 인터페이스(Null·Fake 먼저, 실제 호출은 T3). `service/*` 는 네트워크 import 를 AST 시험으로 금지하므로 실제 HTTP 제공자는 `service/` 밖에 두고 fetcher 를 주입한다.
- 앱 안 예약은 D-09 가 금지 — 수동 `주제 분석 시작` 이 먼저.

## 코드 조사로 알게 된 사실 (2026-11-04, 데스크톱 main 3b1294b)
- 채널 키 5개가 이미 코드에 있다: `github_pages`·`blogger_en`·`blogger_ko`·`naver_a`·`naver_b` (전략 문서의 Blogger A=한글·B=영문은 별칭으로 연결).
- 기존 `Candidate` 는 저장 키 24개·상태 5개·지표 9개, DB 는 판 2 `chanceblog.db`(엄격한 `from_dict`). 제안 엔진은 규칙 기반·결정적이고, 계절 판정이 `word in token` 부분 문자열이라 '그래픽카드'가 '카드'에 걸리는 결함이 있다(P0 가 특성 시험으로 기록, P0b 가 고침).
- `settings.json` 은 최상위 키가 엄격하다. 화면은 Home 만 구현돼 있고 메뉴 6개 중 `topics` 는 자리표시자. CI 는 Qt 시험을 돌리지 않는다(91개 건너뜀).
- P1 구현자가 `content.candidates`·`content.profiles` 의 밑줄(비공개) 도우미를 가져다 쓴다 — 결합 위험으로 독립 검증이 평가한다.

## 지금 상태
최신 진행·다음 행동은 `인수인계/작업내용.md` §0 (이 사본은 2026-11-04 21시 기준). 지시서·보고서는 `인수인계/도구/work/` 의 `p2*_brief.md`·`p2*_report.md`·`an_*.md`·`r131_*.md`.
