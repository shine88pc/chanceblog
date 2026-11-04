# P1 보고서 — 주제 엔진 순수 핵심 (새 패키지 `topics/`)

- 작업 폴더 `W\cd_wt_p1`, 가지 `ai/claude/p1-topic-core-1`(기준 `origin/main` = `3b1294b`), **로컬 WIP 커밋 하나: `98ce63d936f27dd896dcc824b6e4a2ff567bd142`**(작성자·커미터 강병수, push·병합 가지·PR 없음, 작업 트리 깨끗).
- 시작 19:37 → 코드·시험·문서·변이 점검·보고서까지 마감(21:17) 안에 끝냄. 코디네이터 보강(`r131_operator_answer.md` 3절 'P1 구현자')은 요청서와 다른 곳에서 **보강 쪽을 따랐다**(아래 '보강 반영').
- 변경 등급 T1: 새 모듈·시험·문서 한 줄씩뿐. 기존 `src/` 파일 수정 0줄, 기존 시험 변경·삭제 0건, 새 의존성·네트워크·비밀·실제 Seed·전략 문서 원문 문장 없음.

## 단계 보고 6항목 (운영자 조건 7 — 이 순서)

1. **변경 파일**: 새 소스 7개 `src/chanceblog_desktop/topics/{__init__,channels,layout,link,model,score,select}.py`(약 1,000줄) · 새 시험 6개 모듈 `tests/test_topics_{channels,score,model,select,link,rules}.py` + 도우미 `tests/topics_support.py`(약 2,300줄) · 문서 2곳 — `docs/ARCHITECTURE.md` §5 표 한 줄 + 의존 방향 한 줄(+3줄, 절 제목 불변), `CHANGELOG.md` 한 줄(+1줄). 줄바꿈은 기존 파일의 CRLF 를 유지했다.
2. **추가·변경된 시험**: 새 시험 **268개**(channels 53·score 49·model 76·select 33·link 32·rules 25). 기존 시험은 바꾸지 않았다.
3. **전체 시험 결과**: 전체 실행은 **하지 않았다**(요청서 지시 — PC 메모리, CI 에서). 실행한 것: 새 6개 모듈 268개 3.12.10·진짜 3.10.11 모두 `OK`, 기존 4개 모듈(문서 수정 뒤 실행) `test_repo_layout` 26·`test_content_candidates` 121·`test_suggest_score` 29·`test_content_model` 34 도 3.12·3.10.11 모두 `OK`.
4. **기존 기능 영향**: 없음. 새 패키지를 쓰는 곳이 `src/` 안에 한 곳도 없고(시험이 확인) 기존 모듈은 읽기만 했다(`content.candidates`·`content.profiles` 의 검증 도구와 `content.status` 의 채널 키를 가져다 쓴다). 문서 두 곳에 줄만 더했다.
5. **다음 단계에서 발생할 동작 변화**: P1 병합 자체는 동작 변화가 없다. P2(후보 생성 규칙)·P3(저장·서비스)에서 처음으로 이 패키지를 쓰는 연결이 생기며, 그때 `test_topics_rules` 의 '아직 쓰는 곳 없음' 시험을 의식적으로 고친다(아래 '다음 단계').
6. **데이터 마이그레이션**: 없음. 저장 구조·보관함(`chanceblog.db` 판 2)·설정 파일 변경 0, 새 파일은 만들지 않는다(사용자 데이터 파일 이름 네 개를 `layout.py` 에 이름 상수로만 둠 — 저장은 P3).

## 한눈에 — 가장 중요한 5가지

1. **다 했다**: 새 순수 패키지 `topics/`(채널 프로필·엔진 후보·6항목 점수·구간·채널별 상위 N 선택·연결/출처 스냅샷·파일 이름) + 시험 268개(3.12·3.10.11 OK) + 변이 점검 전부 잡힘(아래 표), 로컬 WIP 커밋 `98ce63d`(push·PR 없음).
2. **보강 반영**: 관심도(`trend_ratio`+기준 4칸)와 실제 검색 횟수(`search_demand_count`+출처 필수)를 다른 칸으로 분리했고(관심도 서비스를 횟수 출처로 적으면 거절), 상태는 `work_status` 와 `recommendation_band` 두 축, `CandidateLink`·`Provenance`('빠짐 없음' 시험), `generation_enabled`(네이버 A·B 만)·`history_enabled`(5채널), `layout.py` 이름 네 개.
3. **점수 규칙**: 평가 불가 항목은 0점이 아니라 빼고 남은 가중치를 100 으로 다시 나눈다(기존 `combine` 과 같은 결과임을 시험) · 0.5 올림 한 곳 · 구간 80/65/50 은 반올림한 정수에 적용 · `top_view` 는 보류함 이하로 억지로 채우지 않고 모자란 수만 알린다.
4. **내가 결정할 것**: 협찬 15% 범위(코드에 안 넣음)·시기 점수표 초기값·글 종류↔기존 글 유형 대응·반올림 방식·`work_status` 거르기 책임·`demand` 낱말 예외가 둘인 것(아래 표 14가지).
5. **알아 둘 것**: P3 가 처음 이 패키지를 쓰는 순간 의식적으로 고칠 시험 둘이 있고, 새 오류 코드는 만들지 않았으며(`CONTENT_INVALID`·`CANDIDATE_INVALID` 재사용), 저장소 전체 `ruff` 는 기존 지적 때문에 0 이 아니다(새 파일은 0).

## 보강 반영 (`r131_operator_answer.md` 3절 'P1 구현자' — 요청서와 달라진 곳)

| 요청서 | 보강 | 구현 |
|---|---|---|
| `relative_interest` 묶음 | `trend_ratio`(0~100 정수)·`trend_status`(4값 rising·flat·falling·insufficient)·`trend_period`·`trend_compared_group`·`trend_queried_on` | `model.TopicCandidate` 의 칸 다섯 + `check_trend`(상대값에는 기간·비교 그룹·조회일 필수, 상승·보통·하락은 상대값이 있을 때만) |
| (없음) | `search_demand_count` + 출처 + `data_status`(4값) | 횟수에는 출처 필수·출처만 있어도 거절·**Search Trend·데이터랩 등 관심도 서비스를 출처로 적으면 거절**(상대값이 횟수로 흘러가는 길을 막음), 점수 계산은 이 칸을 읽지 않음, 이름 시험은 `demand` 낱말을 이 두 칸에만 허용 |
| `status`·`grade` | `work_status` / `recommendation_band`(RECOMMENDED·GENERAL·HOLD·EXCLUDED·UNRATED) | 작업 상태는 `content.candidates.STATUSES` 를 그대로 쓰고 구간은 점수에서 계산(저장 안 함, JSON 에도 없음), 하나의 `status` 칸이 없음을 시험 |
| (없음) | `CandidateLink`·`Provenance` | `link.py` — 연결 여섯 칸·출처 스냅샷 열세 칸·엄격 JSON 왕복·`Provenance.of`·**후보의 모든 값이 '담는다' 아니면 '담지 않는다(까닭)' 로 남김없이 나뉘는 시험**(새 칸을 빠뜨리면 걸림 — 실제로 만들다 `candidate_type` 분류 누락을 이 시험이 잡았다) |
| `enabled` | `generation_enabled`(네이버 A·B 만)+`history_enabled`(5채널) | `channels.ChannelProfile` |
| (없음) | 사용자 데이터 파일 이름 상수 | `layout.py` — `channel_profiles.json`·`seeds.json`·`calendar.json`·`topic_engine.db`(이름만, 기존 `chanceblog.db` 와 겹치지 않음을 시험) |

## 새 시험 개수와 실제 출력 (`tests` 폴더에서 `python -X utf8 -m unittest <모듈>`)

| 모듈 | 개수 | 3.12.10 | 3.10.11 | 지키는 것 |
|---|---:|---|---|---|
| `test_topics_channels` | 53 | `Ran 53 tests … OK` | `Ran 53 tests … OK` | 채널 이름·별칭·기본값 숫자 전부(손으로 쓴 기댓값)·공통 상수·엄격한 검사·JSON 왕복(모든 칸을 바꿔도 보존) |
| `test_topics_score` | 49 | `Ran 49 tests … OK` | `Ran 49 tests … OK` | 재정규화(없는 항목 1·2·전부)·반올림·구간 경계(49/50·64/65·79/80)·단조성·기존 `combine` 과 같은 결과·시기 점수표 전 칸 |
| `test_topics_model` | 76 | `Ran 76 tests … OK` | `Ran 76 tests … OK` | 닫힌 목록·필수/기본값·결과 약속 표현 거절(모든 글칸)·관심도/횟수 분리·두 상태 축·이름 규칙·JSON 엄격성·전략 25칸 대응 |
| `test_topics_select` | 33 | `Ran 33 tests … OK` | `Ran 33 tests … OK` | 상한(정확히 상한까지)·보충·강제 보충 금지·모자란 수·결정적 순서(모든 입력 순서)·채널 거르기·꺼진 채널·입력 불변 |
| `test_topics_link` | 32 | `Ran 32 tests … OK` | `Ran 32 tests … OK` | 연결·출처 스냅샷('빠짐 없음'·한 칸 바뀌면 스냅샷도 바뀜)·파일 이름 상수 |
| `test_topics_rules` | 25 | `Ran 25 tests … OK` | `Ran 25 tests … OK` | 소스를 훑는 순수성 시험(허용 목록 밖 import·시계·난수·파일·네트워크·`sqlite3`·`subprocess`·`ctypes` 금지, 검사기 자신도 합성 소스로 시험)·문서 표와 코드의 숫자 일치·쓰는 곳 0 |
| **여섯 개 한꺼번에** | **268** | `Ran 268 tests in 0.727s` `OK` | `Ran 268 tests in 1.042s` `OK` | 전부 빠른 순수 시험(`subprocess`·네트워크·실제 시계·난수·파일 쓰기 없음) |


## 만든 것 (모듈별)

| 모듈 | 하는 일 | 주요 공개 이름 |
|---|---|---|
| `channels.py` | 채널 프로필 5개(코드의 채널 키 그대로, Blogger A·B 는 입력 별칭)와 채널과 무관한 공통 상수. 모르는 칸·합 불일치·범위 밖은 `CONTENT_INVALID`(네이버 프로필과 같은 쓰임)로 거절 | `CHANNELS`·`CHANNEL_ALIAS`·`canonical`·`FACTOR_NAMES`·`ChannelProfile`·`default_profiles`·`profiles_to_dict`·`profiles_from_dict`·`SOURCE_MIX`·`PER_SEED`·`GRADE_CUTOFFS`·`HOLD_DAYS`·`FOLLOW_UP_PER_POST`·`MAX_CHANNELS_PER_TOPIC` |
| `score.py` | 여섯 항목 점수(`Factors`)·`score(profile, factors)`→`Score(parts, final, used_weight, missing)`·`ScoreCard`(후보에 저장하는 여섯 항목+최종, 일관성 검사)·`band_of`·`round_half_up`·`timing_score` | `Factors`·`Score`·`ScoreCard`·`score`·`band_of`·`round_half_up`·`timing_score`·`BAND_*`·`TREND_STATUSES`·`DATA_STATUSES`·`CALENDAR_STATES` |
| `model.py` | 엔진 후보 `TopicCandidate`(32칸 — 전략의 25칸에서 상태 한 칸이 `work_status` 로 바뀌고 7칸이 더해졌다. 저장 모양은 `schema` 를 더해 키 33개. 이름으로만 만든다, frozen)·닫힌 목록·`to_post_type`·`display_id`·`check_trend`·`check_search_demand`·엄격한 JSON(`schema` 1) | `TopicCandidate`·`SOURCE_TYPES`·`CANDIDATE_TYPES`·`DUPLICATE_STATUSES`·`SEARCH_INTENTS`·`CONTENT_TYPES`·`CONTENT_TO_POST_TYPE`·`LABELS`·`display_id`·`to_post_type` |
| `link.py` | 연결 `CandidateLink`(엔진 후보·기존 후보·초안 계획·원천 주제·씨앗·채널)과 출처 스냅샷 `Provenance`, 후보 값의 '담는다/담지 않는다(까닭)' 분류표 `NOT_CARRIED` | `CandidateLink`·`Provenance`·`NOT_CARRIED` |
| `select.py` | `top_view(candidates, profile)`→`TopView(items, shortfall, reason)` | `top_view`·`TopView`·`REASON_GENERATION_OFF` |
| `layout.py` | 사용자 데이터 파일 이름 상수 네 개(이름만) | `CHANNEL_PROFILES_FILE`·`SEEDS_FILE`·`CALENDAR_FILE`·`ENGINE_DB_FILE`·`USER_DATA_FILES`·`JSON_FILES`·`SQLITE_FILES` |

설계 메모(독립 검증이 볼 만한 곳):
- **한 줄 규칙·위험한 표기·결과 약속 표현 거절은 기존 후보와 같은 도구를 그대로** 쓴다 — `content.candidates` 의 `_line`·`_keyword`·`_lines`·`_day`·`_ID`·`_invalid`·`forbidden_claim`·`keyword_key`·`parse_stamp`, `content.profiles` 의 `_invalid`·`_number`·`_text`·`_words`·`_no_markup`. 그중 밑줄로 시작하는 것은 비공개 이름이라 이름이 바뀌면 가져오는 순간 실패하고 시험이 바로 알려 준다(요청서의 '검증 헬퍼 재사용'을 따름 — 공개 이름으로 만드는 것은 기존 파일 수정이라 P1 범위 밖).
- 후보 번호는 **만드는 쪽이 정한다**(`TopicCandidate.new` 가 없다) — 난수·시계를 쓰지 않는다는 규칙 때문이다. `display_id` 는 표시용 함수일 뿐 저장 번호가 아니다(앞 글자가 모두 같아 번호 앞부분 선택과 충돌).
- `ScoreCard` 는 '가중 평균은 가장 낮은 항목과 가장 높은 항목 사이'·'평가한 항목이 없으면 최종 점수도 없다' 까지만 검사한다(채널 가중치를 모르므로). 채널 가중치로 다시 계산한 값과 같은지는 `score.score(...).card` 로 만들면 늘 같다.
- `top_view` 는 **같은 후보 번호가 두 번 오면 한 번만** 쓰고, 입력을 바꾸지 않으며(튜플로 복사해 읽음) 후보 객체도 복사하지 않는다(같은 객체를 돌려준다).


## 변이 점검 (스스로 — 새 시험이 못 잡으면 안 되는 변이)

임시 사본(`W\_p1_mut`)에서 소스를 한 곳씩 망가뜨리고 새 시험 여섯 모듈을 돌려 봤다(`W\p26p1_mutate.py`, 작업 트리는 건드리지 않음). **113곳 중 잡힘 113·놓침 0·패턴 불량 0.** 요청서가 예로 든 변이(가중치 +1·합 검사 삭제·구간 경계 80→81/65→66/50→51·반올림 방식·없는 항목 0점 처리·재정규화 분모·묶음 상한 `>=`↔`>`·보충 때 보류 포함·동점 정렬 키 제거·모자란 수 계산·다른 채널 거르기 삭제·꺼진 채널 처리 삭제·별칭표 추가/삭제·모르는 칸 거절 삭제·금지 표현 검사 삭제·`trend_use=none` 에서 관심도 사용·상대 관심도 칸 이름/라벨을 검색량 쪽으로·`import socket` 추가)을 모두 넣었다.

과정에서 나온 것: ① 변이 목록을 짜다가 '채널 프로필 왕복 시험이 두세 칸만 바꿔서 저장 모양에서 한 칸이 기본값으로 돌아와도 안 걸린다' 는 구멍을 찾아, 모든 칸을 기본값과 다르게 바꿔 왕복하는 시험을 더한 뒤 돌렸다. ② 출처 스냅샷의 '남김없이 나눠 담기' 시험이 만들던 중 `candidate_type` 을 어느 쪽에도 분류하지 않은 실수를 실제로 잡았다. ③ 변이 하나(파일 열기 추가)는 처음에 없는 파일을 열어 가져오기 단계에서 터졌기에 가져오기는 성공하는 모양(`open(__file__)`)으로 바꿔 규칙 시험만 잡을 수 있게 했다. ④ 문서 변이 7개(표의 숫자·의존 방향 줄·절 제목·모듈 이름)는 임시 사본의 `docs` 를 망가뜨려 확인했다.

| 파일 | 변이 수 | 잡힘 |
|---|---:|---:|
| `channels.py` | 30 | 30 |
| `score.py` | 21 | 21 |
| `model.py` | 28 | 28 |
| `link.py` | 12 | 12 |
| `select.py` | 13 | 13 |
| `layout.py` | 2 | 2 |
| `docs/ARCHITECTURE.md(임시 사본)` | 7 | 7 |

| # | 대상 | 변이 | 결과 | 처음 잡은 시험 |
|---:|---|---|---|---|
| 1 | `channels.py` | 가중치 하나 +1(네이버 B 채널 적합도 25→26) | 잡힘 | `chanceblog_desktop.errors.render.AppError: CONTENT_INVALID: 원고의 「항목별 가중치」 이 올바르지 않습니다.` |
| 2 | `channels.py` | 가중치 둘을 맞바꿈(GitHub Pages 근거 25→24·수익화 10→11, 합은 그대로) | 잡힘 | `test_the_weights_are_exactly_the_documented_numbers` |
| 3 | `channels.py` | 가중치 합 100 검사 삭제 | 잡힘 | `test_a_profile_with_a_wrong_value_is_rejected_when_read` |
| 4 | `channels.py` | 지속형·실시간 비율 합 검사 삭제 | 잡힘 | `test_the_evergreen_and_realtime_shares_must_add_up_to_one_hundred` |
| 5 | `channels.py` | 별칭표에 이름 추가(blogger_c) | 잡힘 | `test_canonical_rejects_unknown_names_without_fixing_them` |
| 6 | `channels.py` | 별칭표에서 이름 삭제(blogger_b) | 잡힘 | `test_canonical_keeps_code_keys_and_translates_aliases` |
| 7 | `channels.py` | 별칭 방향 뒤집기(A↔B) | 잡힘 | `test_canonical_keeps_code_keys_and_translates_aliases` |
| 8 | `channels.py` | 프로필 from_dict 모르는 칸 거절 삭제 | 잡힘 | `test_an_unknown_or_missing_field_in_a_profile_is_rejected` |
| 9 | `channels.py` | 프로필 from_dict 빠진 칸 거절 삭제 | 잡힘 | `test_an_unknown_or_missing_field_in_a_profile_is_rejected` |
| 10 | `channels.py` | 다섯 채널이 모두 있어야 한다는 검사 삭제 | 잡힘 | `test_every_channel_must_be_present_exactly_once` |
| 11 | `channels.py` | 같은 채널 두 번 허용 | 잡힘 | `test_every_channel_must_be_present_exactly_once` |
| 12 | `channels.py` | 기본값: 네이버 A 후보 생성 끔 | 잡힘 | `test_only_the_two_naver_channels_generate_candidates_and_every_channel_reads_history` |
| 13 | `channels.py` | 기본값: GitHub Pages 이력 읽기 끔 | 잡힘 | `test_only_the_two_naver_channels_generate_candidates_and_every_channel_reads_history` |
| 14 | `channels.py` | 기본값: 중복 기준 75→76 | 잡힘 | `test_top_n_cluster_cap_subheadings_and_duplicate_cutoffs_are_the_same_for_every_channel` |
| 15 | `channels.py` | 기본값: 채널당 후보 수 5→6 | 잡힘 | `test_changing_a_copy_goes_through_the_checks_and_leaves_the_default_alone` |
| 16 | `channels.py` | 공통 상수: 후보 경로 비율 seed 30→31 | 잡힘 | `test_the_candidate_source_mix` |
| 17 | `channels.py` | 공통 상수: 일반 씨앗 보관 2→3 | 잡힘 | `test_the_candidates_made_and_kept_per_seed_type` |
| 18 | `channels.py` | 구간 경계 80→81 | 잡힘 | `test_the_grade_cutoffs_the_hold_days_and_the_reuse_limits` |
| 19 | `channels.py` | 구간 경계 65→66 | 잡힘 | `test_the_grade_cutoffs_the_hold_days_and_the_reuse_limits` |
| 20 | `channels.py` | 구간 경계 50→51 | 잡힘 | `test_the_grade_cutoffs_the_hold_days_and_the_reuse_limits` |
| 21 | `channels.py` | 보류 일수 90→60 | 잡힘 | `test_the_grade_cutoffs_the_hold_days_and_the_reuse_limits` |
| 22 | `channels.py` | 기본값: Blogger 영문 관심도 none→reference | 잡힘 | `test_the_only_english_channel_is_blogger_en_and_it_does_not_use_the_trend` |
| 23 | `channels.py` | 기본값: 표시 이름 바꿈(네이버 A) | 잡힘 | `test_the_display_names_match_the_ones_the_service_layer_shows` |
| 24 | `channels.py` | 기본값: Blogger 영문의 언어 en→ko | 잡힘 | `test_the_only_english_channel_is_blogger_en_and_it_does_not_use_the_trend` |
| 25 | `channels.py` | 기본값: 네이버 B 지속형 50→51(합은 그대로) | 잡힘 | `test_the_evergreen_and_realtime_shares_are_exactly_the_documented_numbers` |
| 26 | `channels.py` | 가중치를 읽기 전용이 아닌 사전으로 | 잡힘 | `test_an_edited_set_survives_the_round_trip` |
| 27 | `channels.py` | 저장 모양에서 중복 기준 칸 빠뜨림(기본값 고정) | 잡힘 | `test_every_field_survives_the_round_trip_when_all_of_them_are_changed` |
| 28 | `channels.py` | 저장 모양에서 채널당 후보 수 칸 빠뜨림(기본값 고정) | 잡힘 | `test_an_edited_set_survives_the_round_trip` |
| 29 | `channels.py` | 언어 검사 삭제(프로필) | 잡힘 | `test_trend_use_and_language_come_from_closed_lists` |
| 30 | `score.py` | 반올림을 파이썬 round(짝수 반올림)로 | 잡힘 | `test_an_exact_half_in_a_real_score_rounds_up_and_just_below_rounds_down` |
| 31 | `score.py` | 반올림을 내림으로 | 잡힘 | `test_an_exact_half_in_a_real_score_rounds_up_and_just_below_rounds_down` |
| 32 | `score.py` | 반올림을 올림으로 | 잡힘 | `test_half_goes_up_and_below_half_goes_down` |
| 33 | `score.py` | 없는 항목을 0점으로 처리(분모를 항상 전체 가중치로) | 잡힘 | `test_the_result_can_be_stored_as_a_score_card` |
| 34 | `score.py` | 재정규화 분모 틀리기(used+1) | 잡힘 | `test_an_exact_half_in_a_real_score_rounds_up_and_just_below_rounds_down` |
| 35 | `score.py` | 항목이 하나도 없을 때 점수 없음 처리 삭제 | 잡힘 | `test_the_results_agree_for_every_pattern_of_missing_factors` |
| 36 | `score.py` | 구간 경계 `>=`→`>` (우선 추천) | 잡힘 | `test_the_cutoffs_come_from_the_shared_constant` |
| 37 | `score.py` | 구간 경계 `>=`→`>` (일반) | 잡힘 | `test_the_cutoffs_come_from_the_shared_constant` |
| 38 | `score.py` | 구간 경계 `>=`→`>` (보류) | 잡힘 | `test_the_cutoffs_come_from_the_shared_constant` |
| 39 | `score.py` | 점수 없음을 제외 구간으로 | 잡힘 | `test_no_score_is_unrated_and_not_excluded` |
| 40 | `score.py` | 점수 묶음의 최종 점수 범위 검사 삭제 | 잡힘 | `test_a_card_with_a_final_score_needs_evaluated_factors_and_the_final_inside_their_range` |
| 41 | `score.py` | 평가한 항목 없는데 최종 점수 있는 것 허용 | 잡힘 | `test_a_card_with_a_final_score_needs_evaluated_factors_and_the_final_inside_their_range` |
| 42 | `score.py` | 시기 점수표 칸 바꿈(도달+상승 90→91) | 잡힘 | `test_every_cell_of_the_table_with_a_known_trend` |
| 43 | `score.py` | 시기 점수표 칸 바꿈(범위 밖+하락 10→0) | 잡힘 | `test_every_cell_of_the_table_with_a_known_trend` |
| 44 | `score.py` | 캘린더만으로 정할 때 도달 60→61 | 잡힘 | `test_a_channel_that_does_not_use_the_trend_never_looks_at_it` |
| 45 | `score.py` | 캘린더도 모르고 관심도도 모를 때 0점 처리 | 잡힘 | `test_a_channel_that_does_not_use_the_trend_never_looks_at_it` |
| 46 | `score.py` | 관심도를 안 쓰는 채널(none)에서 관심도 사용 | 잡힘 | `test_a_channel_that_does_not_use_the_trend_never_looks_at_it` |
| 47 | `score.py` | 관심도 조회 불가(outage) 무시 | 잡힘 | `test_an_outage_ignores_even_a_known_trend_status` |
| 48 | `score.py` | 실시간 표시 조건 완화(상승 조건 삭제) | 잡힘 | `test_a_topic_out_of_the_calendar_whose_interest_is_rising_is_marked_realtime` |
| 49 | `score.py` | 여섯 항목 범위 검사 삭제 | 잡힘 | `test_a_card_rejects_a_bad_final_and_a_bad_factors_object` |
| 50 | `model.py` | 후보 from_dict 모르는 칸 거절 삭제 | 잡힘 | `test_an_unknown_key_is_refused` |
| 51 | `model.py` | 후보 from_dict 빠진 필수 칸 거절 삭제 | 잡힘 | `test_a_missing_required_key_is_refused_but_a_missing_optional_key_takes_its_default` |
| 52 | `model.py` | 후보 schema 검사에서 bool 허용 | 잡힘 | `test_the_schema_must_be_the_integer_one` |
| 53 | `model.py` | 금지 표현 검사 삭제(선정 이유) | 잡힘 | `test_reasons_and_errors_are_lists_of_lines_with_a_limit_and_are_kept_apart` |
| 54 | `model.py` | 금지 표현 검사 삭제(주제) | 잡힘 | `test_a_wrong_value_is_refused_when_read` |
| 55 | `model.py` | 금지 표현 검사 삭제(처리 중 문제) | 잡힘 | `test_reasons_and_errors_are_lists_of_lines_with_a_limit_and_are_kept_apart` |
| 56 | `model.py` | 금지 표현 검사 삭제(관심도 비교 기간) | 잡힘 | `test_the_trend_texts_and_the_count_source_reject_a_promise_too` |
| 57 | `model.py` | 금지 표현 검사 삭제(검색 횟수 출처) | 잡힘 | `test_a_count_without_a_source_and_a_source_without_a_count_are_both_refused` |
| 58 | `model.py` | 상대값에 비교 기준 필수 검사 삭제 | 잡힘 | `test_a_relative_value_without_period_group_or_date_is_refused` |
| 59 | `model.py` | 관심도 값에 조회일 필수 검사 삭제 | 잡힘 | `test_a_relative_value_without_period_group_or_date_is_refused` |
| 60 | `model.py` | 상승·보통·하락에 상대값 필수 검사 삭제 | 잡힘 | `test_a_determinate_trend_status_needs_a_relative_value` |
| 61 | `model.py` | 실제 검색 횟수에 출처 필수 검사 삭제 | 잡힘 | `test_a_wrong_value_is_refused_when_read` |
| 62 | `model.py` | 출처만 있고 횟수 없는 것 허용 | 잡힘 | `test_a_count_without_a_source_and_a_source_without_a_count_are_both_refused` |
| 63 | `model.py` | 관심도 서비스를 횟수 출처로 쓰는 것 허용 | 잡힘 | `test_a_trend_service_cannot_be_the_source_of_a_real_count` |
| 64 | `model.py` | 상대값이 횟수 칸으로 흘러감(to_dict) | 잡힘 | `test_a_relative_value_never_becomes_a_count` |
| 65 | `model.py` | 상대 관심도 저장 키를 search_volume 으로 | 잡힘 | `test_a_minimal_and_a_full_candidate_round_trip_through_json_text` |
| 66 | `model.py` | 상대 관심도 라벨을 월 검색량으로 | 잡힘 | `test_no_label_text_uses_a_search_volume_word` |
| 67 | `model.py` | 작업 상태 값 검사 삭제 | 잡힘 | `test_the_work_status_values_are_the_ones_the_existing_candidate_uses` |
| 68 | `model.py` | 추천 구간을 엉뚱한 값에서 계산 | 잡힘 | `test_the_result_is_an_immutable_tuple_of_the_same_candidate_objects` |
| 69 | `model.py` | 채널 검사 삭제(후보) | 잡힘 | `test_the_strategy_aliases_are_not_stored_and_the_message_says_which_key_to_use` |
| 70 | `model.py` | 채널 별칭을 저장 값으로 허용 | 잡힘 | `test_the_strategy_aliases_are_not_stored_and_the_message_says_which_key_to_use` |
| 71 | `model.py` | 주제 묶음·관점 식별자 검사 삭제 | 잡힘 | `test_the_cluster_and_angle_are_lowercase_hyphen_identifiers` |
| 72 | `model.py` | 표시 번호의 한국 시간 차이 삭제 | 잡힘 | `test_the_display_date_rolls_over_at_korean_midnight` |
| 73 | `model.py` | 글 종류 대응 바꿈(구매 가이드→정보형) | 잡힘 | `test_the_documented_mapping_examples` |
| 74 | `model.py` | 보조 키워드 중복 검사 삭제 | 잡힘 | `test_keywords_must_have_a_letter_or_digit_and_not_repeat` |
| 75 | `model.py` | 검토 기한이 만든 시각보다 앞서는 것 허용 | 잡힘 | `test_the_review_deadline_cannot_be_before_the_creation` |
| 76 | `model.py` | 원천 주제 번호 모양 검사 삭제 | 잡힘 | `test_the_optional_ids_are_none_or_the_same_shape` |
| 77 | `link.py` | 스냅샷이 선정 이유를 빠뜨림 | 잡힘 | `test_changing_any_one_carried_value_of_the_candidate_changes_the_snapshot` |
| 78 | `link.py` | 스냅샷이 씨앗 번호를 빠뜨림 | 잡힘 | `test_changing_any_one_carried_value_of_the_candidate_changes_the_snapshot` |
| 79 | `link.py` | 스냅샷이 원천 주제 번호를 빠뜨림 | 잡힘 | `test_changing_any_one_carried_value_of_the_candidate_changes_the_snapshot` |
| 80 | `link.py` | 스냅샷이 자료 상태를 빠뜨림 | 잡힘 | `test_changing_any_one_carried_value_of_the_candidate_changes_the_snapshot` |
| 81 | `link.py` | 스냅샷이 점수와 구간을 빠뜨림 | 잡힘 | `test_a_band_that_does_not_match_the_final_score_is_refused` |
| 82 | `link.py` | 스냅샷이 채널을 빠뜨림 | 잡힘 | `test_changing_any_one_carried_value_of_the_candidate_changes_the_snapshot` |
| 83 | `link.py` | 스냅샷이 관심도 상태를 빠뜨림 | 잡힘 | `test_a_candidate_without_scores_gives_an_unrated_snapshot` |
| 84 | `link.py` | 스냅샷 구간 일치 검사 삭제 | 잡힘 | `test_a_band_that_does_not_match_the_final_score_is_refused` |
| 85 | `link.py` | 연결이 씨앗 번호를 빠뜨림 | 잡힘 | `test_a_link_made_from_a_candidate_carries_what_the_candidate_has` |
| 86 | `link.py` | 연결·스냅샷의 채널 검사 삭제 | 잡힘 | `test_the_channel_is_a_code_key_and_an_alias_is_refused` |
| 87 | `link.py` | 연결 schema 검사에서 bool 허용 | 잡힘 | `test_the_link_is_read_strictly` |
| 88 | `select.py` | 같은 묶음 상한 비교 `>=`→`>` | 잡힘 | `test_a_cap_of_one_and_a_cap_of_three` |
| 89 | `select.py` | 보충할 때 보류 구간 포함 | 잡힘 | `test_low_candidates_do_not_help_even_when_some_good_ones_exist` |
| 90 | `select.py` | 동점 정렬 키 제거 | 잡힘 | `test_equal_scores_are_ordered_by_creation_time_then_by_id` |
| 91 | `select.py` | 동점 정렬 키에서 후보 번호만 제거 | 잡힘 | `test_equal_scores_are_ordered_by_creation_time_then_by_id` |
| 92 | `select.py` | 모자란 수 계산 틀리기 | 잡힘 | `test_a_pool_without_this_channel_is_all_missing` |
| 93 | `select.py` | 다른 채널 거르기 삭제 | 잡힘 | `test_a_pool_without_this_channel_is_all_missing` |
| 94 | `select.py` | 후보 생성이 꺼진 채널 처리 삭제 | 잡힘 | `test_a_channel_with_generation_off_gives_an_empty_view_and_the_reason` |
| 95 | `select.py` | 정렬 방향 뒤집기 | 잡힘 | `test_candidates_of_other_channels_are_left_out` |
| 96 | `select.py` | 같은 후보 중복 제거 삭제 | 잡힘 | `test_the_same_candidate_given_twice_is_used_once` |
| 97 | `select.py` | 일반 후보 보충 삭제 | 잡힘 | `test_the_cluster_count_carries_over_from_the_recommended_to_the_general_pass` |
| 98 | `select.py` | 묶음 개수를 단계마다 새로 셈 | 잡힘 | `test_the_cluster_count_carries_over_from_the_recommended_to_the_general_pass` |
| 99 | `select.py` | 채널당 후보 수를 5로 고정 | 잡힘 | `test_the_number_of_candidates_follows_the_profile` |
| 100 | `layout.py` | 엔진 보관함 파일 이름을 기존 보관함 이름으로 | 잡힘 | `test_the_four_file_names_are_exactly_these` |
| 101 | `layout.py` | 씨앗 파일 이름 바꿈 | 잡힘 | `test_the_four_file_names_are_exactly_these` |
| 102 | `select.py` | 모듈에 import socket 추가 | 잡힘 | `test_the_real_modules_follow_every_rule` |
| 103 | `channels.py` | 모듈에 import sqlite3 추가 | 잡힘 | `test_the_real_modules_follow_every_rule` |
| 104 | `score.py` | 서비스 층 가져오기 추가 | 잡힘 | `test_the_modules_import_nothing_from_the_service_ui_publish_or_render_layers` |
| 105 | `model.py` | 시계 읽기 추가 | 잡힘 | `test_a_date_is_only_ever_an_argument_never_read_from_the_clock` |
| 106 | `link.py` | 파일 열기 추가(가져오기는 성공하게 — 규칙 시험만 잡을 수 있다) | 잡힘 | `test_the_real_modules_follow_every_rule` |
| 107 | `docs` | 문서 표의 구간 숫자 틀리기(80/65/50→80/65/55) | 잡힘 | `test_the_numbers_in_the_architecture_row_are_the_numbers_in_the_code` |
| 108 | `docs` | 문서 표의 채널당 후보 수 틀리기(5→6) | 잡힘 | `test_the_numbers_in_the_architecture_row_are_the_numbers_in_the_code` |
| 109 | `docs` | 문서 표의 중복 기준 틀리기(40/60/75→40/60/70) | 잡힘 | `test_the_numbers_in_the_architecture_row_are_the_numbers_in_the_code` |
| 110 | `docs` | 문서에서 의존 방향 줄 이름 바꾸기 | 잡힘 | `test_the_architecture_table_has_one_row_that_names_every_module_and_the_dependency_line_follows` |
| 111 | `docs` | 문서 표에서 보관함 파일 이름 빼기 | 잡힘 | `test_the_numbers_in_the_architecture_row_are_the_numbers_in_the_code` |
| 112 | `docs` | 문서의 절 제목 바꾸기 | 잡힘 | `test_the_section_title_the_other_tests_read_is_unchanged` |
| 113 | `docs` | 문서 표에서 select.py 이름 빼기 | 잡힘 | `test_the_architecture_table_has_one_row_that_names_every_module_and_the_dependency_line_follows` |

## 내가 결정할 것 (전략 해석이 갈렸거나 내가 초기값을 정한 곳 — 전부 코드에서 한 곳씩 바꾸면 된다)

| # | 무엇 | 내가 정한 값(기본) | 바꾸려면 |
|---|---|---|---|
| 1 | **협찬 15% 가 어느 채널에 적용되는가**(후보 경로 비율 `sponsor 15`) | 해석이 갈려 **코드에 적용하지 않았다.** 채널과 무관한 공통 상수 `SOURCE_MIX` 에 비율 숫자만 있다(30/20/20/15/15). 네이버 둘에만 적용할지·채널별 비율로 나눌지는 P2(후보 생성)에서 정한다 | P2 시작 전에 운영자 답 |
| 2 | **시기 항목 점수표 초기값**(전략의 방향만 있고 숫자는 없음) | 아래 표 | `score.py` 의 `TIMING_WITH_TREND`·`TIMING_CALENDAR_ONLY` |
| 3 | **글 종류(`content_type` 11종) ↔ 기존 글 유형 5종 대응** | 아래 표(구매 가이드→비교형으로 정함 — 제품·서비스 소개형도 후보였다) | `model.py` 의 `CONTENT_TO_POST_TYPE` |
| 4 | **반올림 규칙** | 최종 점수는 정수, **소수점 첫째 자리에서 0.5 를 올림**(79.5→80, 64.5→65, 49.5→50, 78.5→79 — 파이썬 `round` 의 짝수 반올림이 아니다). **구간 경계는 반올림한 정수에 적용**한다(정확한 평균 79.5 는 우선 추천). 대안: 소수 한 자리 점수에 경계를 적용(기존 `suggest_score.combine` 의 방식) | `score.py` 의 `round_half_up` 한 곳 |
| 5 | **관심도 사용 정도 4단계 중 `primary`·`supporting`·`reference` 의 차이** | 시기 점수표에서는 **셋을 똑같이 취급**하고(`none` 만 관심도를 아예 안 봄) 차이는 채널의 시기 가중치(5~20)로만 드러난다 | 표를 셋으로 나누거나 `reference` 는 '내릴 때만 반영' 같은 규칙을 정하면 |
| 6 | **`search_intent` 8종·`content_type` 11종 닫힌 목록** | 전략 예시 값(`selection_guide`·`buying_guide`)을 넣고 채널 설명에서 내가 정했다 | `model.py` 의 `SEARCH_INTENTS`·`CONTENT_TYPES` |
| 7 | **채널 프로필의 글 목록 기본값**(`topic_clusters`·`expansion_directions`·`monetization_focus`) — 요청서가 숫자만 정해 줘서 내가 전략의 채널 설명에서 짧은 낱말로 뽑았다(문장 복사 없음, 실제 Seed 아님) | 5채널 모두 채웠고 수익화 태그는 네이버 A·B 만(`small_appliance`·`pc_peripheral`·`lodging_travel` / `ai_service`·`pc_parts`·`work_automation`) | `channels.py` 의 `DEFAULT_PROFILES` (나중에 사용자 JSON 에서 고침) |
| 8 | **`demand` 낱말 예외가 둘이다** — 코디네이터 지시는 `search_demand_count` 하나만 예외였는데 짝인 `search_demand_source`(출처 칸)에도 같은 낱말이 있다 | 둘 다 예외로 두고 시험이 '이름에 `demand` 가 있는 칸은 이 둘뿐'임을 못박는다. 대안: 출처 칸 이름을 `search_count_source` 로 바꿔 하나만 예외 | 이름 한 곳(`model.py`)과 시험 상수 |
| 9 | **`work_status` 로 거르는 일** | `top_view` 는 작업 상태(`work_status`)를 **보지 않는다**(두 축을 섞지 않으려고). 제외(REJECTED)·보류(HOLD)한 후보를 빼는 일은 목록을 넘기는 쪽(P3 서비스)이 한다 — 안 하면 제외한 후보가 다시 위에 보일 수 있다 | P3 에서 서비스가 걸러 넘기거나 `top_view` 에 옵션을 더함 |
| 10 | **후보 생성이 꺼진 채널의 `top_view`** | 빈 결과 + 이유 `generation_off`, 모자란 수는 **0**(화면이 '기준 충족 0개' 가 아니라 '꺼져 있음' 을 보이게) | `select.py` |
| 11 | **오류 코드** | 새 코드를 만들지 않았다 — 채널 프로필은 기존 `CONTENT_INVALID`(네이버 프로필과 같은 쓰임), 엔진 후보·점수는 `CANDIDATE_INVALID`. 화면에 보일 문구가 정해지면(P3~P4) `TOPIC_…` 같은 전용 코드와 문서 표 행을 더할지 정한다 | `docs/TROUBLESHOOTING.md` 표 + `sync_errors.py` |
| 12 | **관심도 칸 규칙(내가 정한 일관성 검사)** | 상대값이 있으면 기간·비교 그룹·조회일이 모두 있어야 하고, `rising`/`flat`/`falling` 은 상대값이 있을 때만 쓸 수 있다(`insufficient` 는 값이 있어도·없어도 됨). 실제 검색 횟수는 출처 필수·출처만 있어도 거절·**관심도 서비스(Search Trend·데이터랩 등)를 출처로 적으면 거절** | `model.py` 의 `check_trend`·`check_search_demand` |
| 13 | **5채널 모두 필요** | `profiles_from_dict` 는 다섯 채널이 하나씩 정확히 있어야 읽는다(일부만 있는 파일은 거절) — 일부만 고치는 파일을 허용할지는 P3 | `channels.py` 의 `_ordered` |
| 14 | **같은 `candidate_id` 가 두 번 들어오면** `top_view` 가 한 번만 쓴다 | 입력 오류를 조용히 흡수 | `select.py` |

### 시기 항목 점수표 초기값 (`timing_score(calendar, trend_status, *, trend_use, outage)`)

| 캘린더 \ 관심도 | 상승 | 보통 | 하락 | 데이터 부족·조회 불가·관심도 안 씀(캘린더만) |
|---|---:|---:|---:|---:|
| 시점 도달(`due`) | 90 | 70 | 40 | **60**(0 아님 — `data_status` 는 부족=`insufficient`, 조회 불가=`unavailable`) |
| 범위 밖(`out_of_range`) | 70 + **실시간 후보 표시** | 20 | 10 | 20 |
| 캘린더에 없음(`unknown`) | 70 | 50 | 30 | **평가 불가(None) — 0점이 아니라 계산에서 빠지고 남은 항목이 100 으로 다시 나뉜다** |

- `trend_use=none`(Blogger 영문)은 관심도 상태가 무엇이든 위 마지막 열만 쓴다(자료 상태는 캘린더가 있으면 `sufficient`, 없으면 `insufficient`).
- `outage=True`(장애·한도로 조회 불가)는 알려진 관심도 상태가 있어도 무시하고 마지막 열을 쓰며 자료 상태는 `unavailable` 이다.

### 글 종류 ↔ 기존 글 유형 대응(초기 판단)

| 글 종류(`content_type`) | 기존 글 유형 |
|---|---|
| `explainer`·`how_to_guide`·`checklist`·`news_analysis`·`routine_plan` | 정보형 |
| `troubleshooting`·`dev_log` | 문제 해결형 |
| `buying_guide`·`comparison` | 비교형 |
| `service_intro` | 제품·서비스 소개형 |
| `place_guide` | 장소·업체 정보형 |

## 다음 단계(P2·P3) 입력으로 필요한 것

1. **운영자 결정**: 협찬 15% 의 범위(위 1번)·관심도 사용 정도 3단계를 어떻게 다르게 쓸지(5번)·`work_status` 거르기를 누가 하는지(9번).
2. **P2(후보 생성)가 이 패키지 위에 만들 것**: Seed 모델(유형 키는 `PER_SEED` 의 다섯 이름 `general·priority·seasonal·realtime·sponsorable` 로 가정)·확장어·허용 조합·캘린더에서 `due/out_of_range/unknown` 계산·중복 판정 함수(`dup_cutoffs` 의 세 기준 → `duplicate_status` 네 값, 유사도 % 입력)·작성 가능성 검사·`Factors` 여섯 항목을 만드는 규칙·`data_status`(sufficient/partial/insufficient/unavailable) 집계 규칙.
3. **모델이 일부러 검사하지 않은 것(P2 가 후보를 만들 때 지킬 것)**: 언어 ↔ 채널 일치(Blogger 영문만 `en`)·`topic_cluster` 가 그 채널 프로필의 `topic_clusters` 에 있는지·`source_type` ↔ `candidate_type` 짝·`monetization_tags` 사전·`ScoreCard.final` 이 채널 가중치로 다시 계산한 값과 같은지(프로필이 있어야 확인 가능 — `score.score(...).card` 로 만들면 늘 같다).
4. **P3(저장·서비스)**: 위 `layout.py` 이름 네 개를 쓰는 저장(채널 프로필 JSON ↔ `profiles_to_dict`/`profiles_from_dict`, `topic_engine.db` 새 SQLite — 기존 `chanceblog.db` 불변), 기존 후보로의 투영(이때 `CandidateLink.of` + `Provenance.of` 를 연결 표에 저장), `draft_plan_id` 정의(지금은 번호 모양만 검사), `top_view` 호출 전 `work_status` 거르기, 새 오류 코드 여부(11번). `Provenance` 가 담지 않는 값 중 초안에 필요할 수 있는 것 — `search_intent`·`topic_cluster`·`topic_angle`·`target_reader`·`candidate_type`·`monetization_tags`(`link.NOT_CARRIED` 가 '열린 항목'으로 표시) — 을 정한다.
5. **P3 가 처음 이 패키지를 쓰는 순간 의식적으로 고칠 시험 둘**: `test_topics_rules` 의 `test_nothing_outside_the_package_uses_it_yet…`(지금은 쓰는 곳 0 — '허용된 사용처 목록'으로 바꾼다)와 `test_the_package_has_exactly_the_expected_modules`(P2 가 모듈을 더하면 목록을 고친다). 둘 다 서비스 층 안전 시험처럼 일부러 걸리게 둔 것이다.

## 계획 문서(`docs/TOPIC_ENGINE_PLAN.md`)에 반영할 것 — P0 가 아직 병합 전이라 이 가지에서는 건드리지 않았다

- P1 상태: 완료(WIP 커밋, 병합은 P0b 뒤). 모듈 여섯(`channels·score·model·link·select·layout`)과 시험 여섯 모듈(268개).
- 열린 항목: `draft_plan_id` 의 정의(P3)·`NOT_CARRIED` 의 '열린 항목' 여섯 개·새 오류 코드 여부·협찬 15% 범위·시기 점수표 초기값·글 종류 대응·반올림 규칙(위 표).
- 설계 확정으로 적을 것: 상태 두 축 이름(`work_status` / `recommendation_band` 값 RECOMMENDED·GENERAL·HOLD·EXCLUDED·UNRATED — 두 축에 HOLD 가 있으므로 이름·주석에서 구분)·관심도 칸 다섯(`trend_ratio`·`trend_status` 4값·`trend_period`·`trend_compared_group`·`trend_queried_on`)과 실제 검색 횟수 칸(`search_demand_count` + `search_demand_source`, 점수 계산은 읽지 않음, 기존 `Candidate.search_demand` 는 Legacy 로 그대로)·`CandidateLink`·`Provenance`·채널 프로필 켜기 두 칸(`generation_enabled` 는 네이버 A·B 만, `history_enabled` 는 5채널)·사용자 데이터 파일 이름 네 개.

## 점검 결과

| 점검 | 결과 |
|---|---|
| 새 6개 모듈 3.12.10 / 진짜 3.10.11 | 268개 모두 OK (위 표) |
| 기존 4개 모듈(문서 수정 뒤 실행) | `test_repo_layout` 26 · `test_content_candidates` 121 · `test_suggest_score` 29 · `test_content_model` 34 — 3.12·3.10.11 모두 OK |
| `ruff check --select F,E9,B,UP --target-version py310` | **새·바뀐 파일은 지적 0.** 저장소 전체(`src tests`)로 돌리면 이번 일과 무관한 기존 지적이 다른 파일(`check/similarity.py` 의 B008, `content/profiles.py` 의 F401, 여러 시험 파일)에 있어 0 이 아니다 — 건드리지 않았다 |
| `vermin --target=3.10- --no-tips src/chanceblog_desktop/topics` | Minimum required versions: 3.10 |
| `git diff --check` | 지적 0 (새 파일은 줄 끝 공백·탭·BOM·보이지 않는 글자 0건을 따로 훑음) |
| 커밋을 새로 내보낸 사본(`git archive HEAD`)에서 | 새 6개 모듈 268개 + `test_repo_layout` 26 — 3.12.10·3.10.11 모두 OK(작업 트리의 안 올라간 파일에 기대지 않음) |
| 문서를 읽는 다른 시험 | `test_service_candidates_cli` 60개 3.12 OK(ARCHITECTURE 를 읽는 시험 중 요청서 목록에 없던 하나) |
| 거친 입력 훑기(저장소에 올리지 않음, `W\p26p1_fuzz.py`) | 모든 `from_dict`·생성자에 `None`·거짓/참·빈 값·섞인 목록·`NaN`·큰 수·객체 등 30여 가지를 칸마다 넣어 봤고 `AppError` 외의 예외가 새는 곳 0 |
| 전체 시험 실행 | **하지 않음**(요청서 지시 — 메모리). CI 에서 본다 |

참고(함정): 이 환경에서 도구에 `\u200b` 같은 글자 이스케이프를 쓰면 **실제 보이지 않는 글자로 바뀌어 저장**됐다(시험 소스에 폭 없는 공백·BOM 이 박힐 뻔 — 스캔으로 잡아 `chr(0x200B)`·`chr(0xFEFF)` 로 바꿨다). 보이지 않는 글자를 시험하는 코드는 `chr()` 로 만들 것.

## 만든 도구(저장소 밖, 작업 폴더 `S`)

- 변이 점검 도구 `W\p26p1_mutate.py` — 임시 사본(`W\_p1_mut`)에서 소스(또는 임시 사본의 docs)를 하나씩 망가뜨려 새 시험 여섯 모듈이 잡는지 센다. 결과 `W\p26p1_mutants.json`·`W\p26p1_mutants.log`. 작업 트리는 건드리지 않는다.
- 커밋 메시지 `W\p26p1_commit_msg.txt`.
