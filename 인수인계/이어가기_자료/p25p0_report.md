# P0 보고서 — 5채널 주제 선정 전략 1단계: 기존 동작을 시험으로 먼저 보호 + 계획 문서·결정

작업 폴더 `W\cd_wt_p0`(가지 `ai/claude/p0-topic-protect-1`, 기준 `origin/main` = `3b1294b` — 끝까지 움직이지 않았다). 시작 19:27, 1차 끝 20:10경, 보완 1차 끝 20:42경, **보완 2차(독립 검증 최종 보고서 반영) 끝 21:30경**(마감 21:45). **로컬 WIP 커밋 셋** — 1차 `1f2297b`·보완 1차 `4c746d6`(둘 다 그대로 둠)·**보완 2차 `23ca08e`**(전체 `23ca08ebf1550b373300a424cdea96d95eea8c7e`), 작성자 `강병수 <shine88pc@gmail.com>`. push·병합 가지·PR 은 만들지 않았다. 운영자 R-131 답(A~H=1 + 조건 7개, 19:40)은 19:41 에 받아 반영했다.

## 000. 2차 수정(21:30) — 독립 검증 최종 보고서 `ver_p0_report.md`(판정 '조건부 병합 가능': 높음 0·중간 2·낮음 12) 반영 (새 WIP 커밋 `23ca08e`, `src/` 0줄·기존 시험 0줄)
※ 이 절 아래의 00절(보완 1차)·0절(6항목)·1~10절은 그 시점의 값이다 — **2차 이후 최신 값은 이 절을 따른다**: 시험 **76개**(ui 31·suggest 26·candidates 19), 변이 점검 **67곳**, 결정 **D-36~D-41**, 계획 문서 396줄. 새 커밋 `23ca08e` 의 부모는 `4c746d6` 이고 `git diff --stat origin/main HEAD -- src` 는 비어 있다(기준 대비 6파일 +1,435·삭제 0).

### 반영한 것
| 지적 | 한 일 | 확인 |
|---|---|---|
| **M1 (중간·필수)** 계획 7절 ③·⑥ 의 `connections.py` 인용이 N1 병합 뒤에는 틀려짐 | ③ 의 공급자 문장을 **'`3b1294b` 기준'**(`:138` `naver_openapi`·`:142` `naver_searchad`)과 **'N1 병합 뒤'**(`r134-naver-hub-safety-2` 머리 `3b0194f`: `naver_openapi` 는 이름이 '옛 항목 — 네이버 오픈 API(검색·데이터랩)' 가 되어 읽기만 하고 새 항목은 더하지 못함 `:198`, 새 `naver_apihub` `:176` 이 데이터랩 '검색어 트렌드' 로 **관심도 변화**를 조회하는 용도(안전 장치만 있고 호출 코드 없음), `naver_searchad` `:181` 그대로)로 나눠 적었다. ⑥ 에는 '(`3b1294b` 기준)' 과 'N1 뒤에는 이 근거가 약해진다 — 남는 것은 이미 든 값이 무엇이었는지 알 수 없다는 쪽뿐, 결론(Legacy 유지·자동 이전 없음)은 어느 쪽이든 같다' 를 더했다. 7절 머리에는 '인용한 줄은 `3b1294b` 의 줄이다' 를 적었다 | N1 머리(`3b0194f`)에서 계획의 `파일:줄` 인용을 전수 대조: **밀리는 것은 `connections.py`(138→198·142→181, 새 용도 176)뿐**이고 `cli.py:502·627`·`format.py:236` 은 같은 줄이다. 새 시험 76개는 N1 머리 위에서도 OK(아래) |
| **M2 (중간)** Qt 소스 글자 훑기 시험이 주석으로 남긴 옛 줄(V85)에 속고 동작이 같은 정리(V86·V87)에 깨짐 | `test_the_qt_shell_source_picks_home_or_the_placeholder_and_shows_the_drawer_on_home_only` 를 정규식에서 **`ast` 기반**으로 바꿨다 — `shell.py` 의 `render`·`_sync_overlays` 에서 `home_screen`·`placeholder_screen`·`drawer_view` 호출이 '`…page == "home"` 조건의 참/거짓 가지' 안에 있는지, `screens.py` 에서 `vm["section"]["all"]` 글의 단추 눌림이 `shell.go("topics")` 로 이어지는지 본다. 조건을 지역 변수에 담은 것도 같은 조건으로 읽는다 | 변이 M53~M60 (아래 표): 깨뜨리는 4곳(홈↔자리표시 맞바꿈·서랍을 설정 화면 말고 모두·'전체 보기'→기록·**옛 줄을 주석으로 남기고 서랍을 모두 보임(V85)**) **모두 잡힘**, 동작이 같은 4곳(조건을 변수로 뺌(V86)·줄 바꿈(V87)·주석만 덧붙임·단추 변수 이름 바꿈) **모두 통과** |
| 낮음 1 — 아무 시험도 못 잡던 변이 3곳 | **V11** 추세 낱말 표(보합→`flat`)·`TREND_ICON`·화면 글(상승·보통·하락·데이터 없음) `test_the_three_trend_words_become_up_flat_and_down_and_no_trend_stays_empty` / **V30** 새로 불러오면 칩이 '전체' 로 돌아가고 첫 행이 선택됨 `test_loading_new_data_puts_the_chip_back_to_all_and_selects_the_first_live_row` / **V34** `SeasonGenericWordTest` — '준비'·'마무리'·'행사' 만 든 글은 시기 이름의 일부여도('종합소득세 준비'·'여름 마무리'·'쇼핑 행사') 시기와 이어지지 않고, 흔한 말을 뺀 나머지 낱말은 이어지며(70) 이름 전체는 일치(100) | 변이 M61(V11)·M62(V30)·M63~M65(V34 의 '준비'·'마무리'·'행사' 각각) **모두 잡힘** |
| 낮음 2 — 새 시험이 놓치고 기존 시험이 잡는 변이 7곳 | 계획 9.1 에 **'새 시험은 기존 시험과 합쳐서 보호한다'** 한 문장(제안 점수 구간 경계·태그 씨앗 강도·경쟁·관심도 보합·위험 판정의 금지 문구·프로필 없는 네이버 B 안내는 기존 시험 몫) | 문장만 — 겹치는 시험은 더하지 않음(원칙) |
| 낮음 3 — 결정 B·H 행 없음 | **D-40**(채널 이름 대응) · **D-41**(실시간 이슈) 두 행을 표 끝에 더했다. 계획 5.2 제목·10절 B·H 행의 '이어지는 곳' 에 연결 | `test_repo_layout` OK(부르는 번호 ⊆ 정의된 번호) |
| 낮음 4 — 결정 A '제안 상태 시작 목록' 위치 | 계획 10절 A 행과 D-39 ④ 에 **'전략 문서에서 뽑은 시작 목록도 실제 Seed 라서 사용자 데이터(`seeds.json`)에만 두고 저장소에는 시험용 가짜 예시만'** | 둘이 같은 말 |
| 낮음 5 — P4 행 '화면 문구 3곳' | 구체화: 의식적으로 바뀌는 기존 시험 = 서랍 항목 목록 시험·'주제 후보' 가 자리표시가 아니게 되는 곳(메뉴 시험의 자리표시 단추 단언·`test_ui_qt` 자리표시 시험). R-131 의 '3곳' 은 재라벨을 전제로 센 것이라 지금은 세지 않음(11절 열린 항목 3), 구체 목록은 P4 구현자가 보고 | — |
| 낮음 6 — 새 문구 없음 시험의 오경보 | `T` 훑기를 **'상대값' 낱말만** 보게 좁히고 주석에 '새 Trend 문구는 새 키로 더한다' 를 적었다. 서랍 시험의 `최근 관심도` 검사도 `상대값` 으로 좁혔다 | 변이 M66(새 키로 `최근 관심도(상대값)` 를 더함 — 의도대로 깨짐)·**M67(기존 `d_trend` 를 '최근 관심도 변화' 로 바꿈 — 깨지지 않음, 오경보 없음)** |
| 낮음 7 — Legacy KNOWN_DEFECT 3개는 뒤집는 단계가 없음 | 시험 3개에 '뒤집는 단계가 없다 — Legacy 는 그대로 두고 새 Trend 칸이 대신한다(D-37 ③)' 주석, 계획 9.2 `KNOWN_DEFECT` 행에 같은 문장 | — |
| 낮음 8 — 실제 시계 | 화면 시험의 `AppState` 에 `today=TODAY`(2026-11-03)를 넘긴다(전엔 `date.today()` 를 읽었다). `make_ctx` 의 `Clock` 은 고정 가짜 시계 | **`date.today()`·`datetime.now()` 를 부르면 터지게 바꿔 놓고 76개를 돌려 통과** — 시험이 실제 시계를 읽지 않는다 |
| 낮음 9 — P1 지시와 계획 3.2 충돌 | 계획 3.2 의 의존 방향·3.1 `model.py` 행·D-36 ① 을 **'`errors`·`check.claims`·`content` 의 순수 부품(작업 상태 상수 같은 것)만 가져오고 `content.store`·`service`·`ui` 는 가져오지 않는다'** 로 정확하게 고쳤다(`content.candidates` 는 `errors`·`content.status`·`content.model`·`content.profiles` 만 가져옴을 확인) | P1 지시('작업 축 값은 `content.candidates` 상수 재사용')와 일치 |
| 낮음 11 — 비공개 이름 의존 | `sg._RISKY`·`ServiceHomeProvider()._names` 를 읽는 곳에 '비공개 이름 — 바뀌면 이 시험을 고친다' 주석 | — |

### 반영하지 않은 것과 이유
| 지적 | 이유 |
|---|---|
| 낮음 10 — 시험 예시 프로필 A·B 를 중립 낱말로 | B 의 '그래픽카드' 는 운영자 요청의 오탐 예시 자체이고, A·B 의 첫 셋 제안이 손으로 옮긴 값(스냅샷)이라 바꾸려면 값을 다시 구해 못박아야 한다. 낱말은 일반 낱말이고 계획·결정 행에는 전략 문서의 채널 분야를 옮기지 않았다 — 코디네이터가 원하면 P1 이후에 중립 예시로 바꾼다 |
| 낮음 12 — 계획 문서의 `README` 링크 | 이번 라운드는 'src·기존 시험·기존 문서 줄은 바꾸지 않는다' 이고 README 는 요청 범위 밖이다(시험도 요구하지 않음). 병합 때 링크할지는 코디네이터 판단 |
| 낮음 2 의 '새 시험 더하기' | 기존 시험이 이미 잡는 것(7곳)이라 겹치는 시험을 더하지 않았다(문장으로만 반영) |
| 기존 줄을 바꿔야 하는 지적 | 없었다 — 이번 지적은 모두 새 시험·새 문서 줄·내 앞 커밋의 줄 안에서 처리했다(`src/`·기존 시험 파일은 0줄) |

### 시험 결과 (3.12.10 / 3.10.11, 한 번에 한 모듈씩 — 전체 실행은 하지 않음)
```text
                                3.12.10                          3.10.11
test_topic_protect_ui           Ran 31 tests in 0.784s  OK      Ran 31 tests in 0.804s  OK
test_topic_protect_suggest      Ran 26 tests in 3.575s  OK      Ran 26 tests in 3.620s  OK
test_topic_protect_candidates   Ran 19 tests in 0.091s  OK      Ran 19 tests in 0.098s  OK      (합 76)
test_repo_layout                Ran 26 tests in 1.759s  OK      Ran 26 tests in 1.562s  OK
test_content_model              Ran 34 tests in 0.019s  OK      Ran 34 tests in 0.017s  OK
test_ui_core                    Ran 94 tests in 3.163s  OK      Ran 94 tests in 3.400s  OK
test_service_candidates_cli     Ran 60 tests in 10.983s OK      Ran 60 tests in 11.537s OK
N1 병합 가지 머리 3b0194f 위에서 새 3모듈:
test_topic_protect_ui           Ran 31 tests in 0.732s  OK      Ran 31 tests in 0.732s  OK
test_topic_protect_suggest      Ran 26 tests in 3.394s  OK      Ran 26 tests in 3.595s  OK
test_topic_protect_candidates   Ran 19 tests in 0.086s  OK      Ran 19 tests in 0.069s  OK
```
`ruff check --select F,E9,B,UP --target-version py310` 새 시험 3개 **0건** · `git diff --check` 0건 · 새·바뀐 6파일의 BOM·보이지 않는 글자·줄 끝 공백·탭 **0건** · 계획 문서 **396줄**(한도 400) · 모든 시험(76/76) 위 표준 주석 있음 · 계획·시험에 `D-35` 글자 0건 · 임시 N1 작업 폴더·변이 사본은 작업 폴더 밖이고 끝에 지웠다(변이 사본은 작업 폴더와 바이트까지 같음 확인).

### 변이 점검 (임시 사본에서 한 곳씩 깨뜨리고 되돌림)
전체 **67곳**(1차 M01~M42·보완 1차 M43~M52·2차 M53~M67)을 **2차의 최종 시험으로 처음부터 다시** 돌렸다: **62곳 잡힘**(동작을 깨뜨리는 것은 전부), **5곳은 통과가 맞다**(M57~M60 = 동작이 같은 정리, M67 = 오경보 방지) — 기대와 다른 결과 0. 새로 더한 M53~M67 은 아래 표(앞 52곳 표는 2절).

| 번호 | 변이 | 기대 | 결과 |
|---|---|---|---|
| M53 | (Qt 소스) 홈 화면과 자리표시 화면을 맞바꿈 · `ui/qt/shell.py` | 잡혀야 함 | 잡힘 — the_qt_shell_source_picks_home_or_the_placeholder_and_shows_… |
| M54 | (Qt 소스) 서랍이 설정 화면 말고는 모두 보임 · `ui/qt/shell.py` | 잡혀야 함 | 잡힘 — the_qt_shell_source_picks_home_or_the_placeholder_and_shows_… |
| M55 | (Qt 소스) '전체 보기' 가 기록 화면으로 · `ui/qt/screens.py` | 잡혀야 함 | 잡힘 — the_qt_shell_source_picks_home_or_the_placeholder_and_shows_… |
| M56 | (Qt 소스) 서랍을 모든 화면에 보이되 옛 줄을 주석으로 남김 — 옛 글자 훑기 시험은 속았다(V85) · `ui/qt/shell.py` | 잡혀야 함 | 잡힘 — the_qt_shell_source_picks_home_or_the_placeholder_and_shows_… |
| M57 | (Qt 소스) 동작은 같고 조건을 변수 하나로 뺀 정리 — 통과해야 한다(V86) · `ui/qt/shell.py` | 통과해야 함(동작이 같음) | 통과(맞음) |
| M58 | (Qt 소스) 동작은 같고 줄만 바꾼 정리 — 통과해야 한다(V87) · `ui/qt/shell.py` | 통과해야 함(동작이 같음) | 통과(맞음) |
| M59 | (Qt 소스) 동작은 같고 주석만 덧붙임 — 통과해야 한다 · `ui/qt/shell.py` | 통과해야 함(동작이 같음) | 통과(맞음) |
| M60 | (Qt 소스) 동작은 같고 단추 변수 이름만 바꾼 정리 — 통과해야 한다 · `ui/qt/screens.py` | 통과해야 함(동작이 같음) | 통과(맞음) |
| M61 | 추세 표에서 보합을 up 으로(V11 — 아무 시험도 못 잡던 것) · `ui/adapters.py` | 잡혀야 함 | 잡힘 — the_three_trend_words_become_up_flat_and_down_and_no_trend_s… |
| M62 | 새로 불러와도 칩 거르기를 '전체' 로 되돌리지 않음(V30 — 아무 시험도 못 잡던 것) · `ui/core/app_state.py` | 잡혀야 함 | 잡힘 — loading_new_data_puts_the_chip_back_to_all_and_selects_the_f… |
| M63 | 흔한 말 목록에서 '준비' 빼기(V34 — 아무 시험도 못 잡던 것) · `content/suggest_score.py` | 잡혀야 함 | 잡힘 — a_text_with_only_a_generic_word_does_not_connect_to_a_season… |
| M64 | 흔한 말 목록에서 '마무리' 빼기 · `content/suggest_score.py` | 잡혀야 함 | 잡힘 — a_text_with_only_a_generic_word_does_not_connect_to_a_season… |
| M65 | 흔한 말 목록에서 '행사' 빼기 · `content/suggest_score.py` | 잡혀야 함 | 잡힘 — a_text_with_only_a_generic_word_does_not_connect_to_a_season… |
| M66 | 새 Trend 문구를 새 키로 더함(P4 가 할 일) — '아직 없음' 시험이 의식적으로 깨져야 한다 · `ui/core/text.py` | 깨져야 함(의도) | 잡힘 — the_screen_text_has_no_relative_interest_label_yet_so_p4_add… |
| M67 | 기존 추세 서랍 이름을 '최근 관심도 변화' 로 바꿈 — 좁힌 시험은 깨지지 않아야 한다(오경보 방지) · `ui/core/text.py` | 통과해야 함(오경보 방지) | 통과(맞음) |

### 내가 결정할 것(2차 이후)
- 낮음 10(중립 예시 프로필)·낮음 12(README 링크)를 할지.
- N1 → P0 순서로 병합하면 `DECISIONS.md`·`CHANGELOG.md` 끝 충돌만 풀면 된다(N1 은 D-35 한 행뿐 — `git diff` 로 확인, P0 의 D-36~D-41 과 겹치지 않음).

## 00. 보완 1차(20:42) — 독립 검증 `ver_p0_report_partial.md` 지적 3건 (새 WIP 커밋 `4c746d6`, `src/` 0줄·기존 시험 변경 0)
| # | 지적 | 한 일 |
|---|---|---|
| ① | 계획 문서 7절 ⑥ 이 '운영자의 결론·근거(검색광고 한 곳·PC+모바일 합계)'라고 썼지만 그 근거는 운영자가 한 말이 아니라 코디네이터의 가설이었다 | **계획 문서 4.2·5.1·7절 ⑥·10절 E 행, 결정 D-36~D-39, CHANGELOG** 에서 '운영자가 한 말(채팅의 조건 1~7)'과 '이 계획의 해석'·'이 조사의 결론'을 나눠 다시 썼다. 4.2 표에 **'누가 정했나' 열**(운영자 조건 1 / 이 계획)을 더해 운영자가 정한 칸 이름(`search_demand_count`·`trend_ratio`·`trend_status`·`trend_period`·`trend_compared_group`)과 이 계획이 더한 것(`search_demand_source`·`trend_queried_on`·`data_status`·영문 상태 값·0~100 범위)을 갈랐다. 7절 ⑥ 은 '운영자 말이 아니라 **이 조사의 결론**(코드·문서 근거)이고 **운영자 지시(조건 1: 의미가 불명확하면 Migration 하지 말고 Legacy 필드로 유지)** 를 이 값에 적용한 것'으로 고쳤다. 결정 4행의 상태 칸도 '확정(운영자 승인…)' → '운영자 승인의 범위에서 이 계획이 구체화한 결정 — 운영자가 직접 정한 것은 본문에 따로 표시, 나머지는 해석'. 이 보고서의 같은 표현(1절 4번·4절 ⑥·7절 5번)도 고쳤다 |
| ② | 기존 절대 횟수 칸의 화면 이름·단위(`T["demand"]="월 검색량"`·서랍 `월간 검색량`·`회`)가 어느 시험에도 못박혀 있지 않아 '재라벨'이 소리 없이 통과할 수 있다 | `tests/test_topic_protect_ui.py` 에 `LegacyDemandLabelTest` 4개(순수, Qt 없음): 이름·단위·툴팁·`fmt_demand`/`fmt_docs` 값 / 네 문구에 상대·관심도·지수·트렌드·Trend·ratio 가 없다(재라벨 금지) / 지금 화면 문구 어디에도 `상대값`·`최근 관심도` 가 없다(P4 가 새 문구로 더할 때 의식적으로 고침) / 행·서랍 뷰모델의 값(`8,600회`·`4,120건`)과 서랍 첫 항목 `월간 검색량`. 명령줄 쪽은 `test_topic_protect_candidates.LegacyCountOnTheCommandLineTest` 1개(`METRIC_UNITS`·`metric_text`·`LABELS`). **변이 점검**(아래 2절 M43~M49·M52): 행 라벨 재라벨(M43)·서랍 라벨 재라벨(M44)·'회' 지우기(M45)·툴팁 바꾸기(M46)·쉼표 지우기(M47)·명령줄 '회' 지우기(M48)·`LABELS` 재라벨(M49)·서랍 첫 항목 바꾸기(M52) 모두 잡힘. 기존 시험만으로는 **M43(행 라벨 재라벨)을 놓친다**(같은 변이를 `test_ui_core`+`test_ui_adapters` 만 돌려 확인 — 기준선과 같은 결과였고, 서랍 라벨(M44)·'회' 지우기(M45)는 기존 시험이 이미 잡았다) |
| ③ | P0b 영향 설명이 '제안 결과'만 말한다 — `season_fit` 은 보관함 후보의 우선도 계산(`suggest.assess` ← `service/suggestions.py:296` ← `candidates list --priority`(`cli.py:465`)·`candidates show`(`cli.py:474`))에도 쓰인다 | 계획 문서 **8.1 P0b 행·8.2 ⑤ 예·8.3** 에 한 줄씩 더했다(같은 오탐으로 '그래픽카드' 후보가 11월에 시기 요인 70점과 '연말정산 준비' 이유를 받아 우선도 **89.1**, 고치면 평범한 낱말과 같은 81.8). 현재 값을 `StoredCandidatePriorityTest` 3개로 못박았다(KNOWN_DEFECT 1·의도한 일치와 평범한 낱말 1·외부 계절성 달이 낱말을 이기는 것 1). 계획 문서는 **396줄 그대로**(400줄 한도) — 새 줄을 더하지 않고 있던 줄 안에서 고쳤다 |

**점검(보완 뒤)**: 새 시험 3모듈 **73개**(ui 29·suggest 25·candidates 19) 3.12.10·3.10.11 OK(아래 ③ 줄) · `test_repo_layout` 26 OK 둘 다 · 변이 점검 **52곳**(1차 42 + 10) 모두 잡힘 · ruff 새 시험 3개 0건 · `git diff --check`·BOM·보이지 않는 글자·줄 끝 공백·탭 0건 · 공개 가지 N1(`b2096ce`) 머리에서도 73개 3.12·3.10 OK(임시 폴더는 지움). 새 WIP 커밋은 `1f2297b` 위에 얹었고(`4c746d6`, 부모 `1f2297b`) `git diff --stat origin/main HEAD -- src` 는 비어 있다.

## 0. 운영자 단계 보고 6항목 (조건 7 — 이 순서)

### ① 변경 파일
`git diff --stat origin/main HEAD` = 6개 파일, +1,435줄, 삭제 0줄(커밋 셋 합산 — 보완 2차만 보면 +139·−37, 모두 내 앞 커밋의 줄).

| 파일 | 상태 | 줄 | 내용 |
|---|---|---:|---|
| `tests/test_topic_protect_ui.py` | 새 | 449 | 특성 시험 31개 — G1 어댑터·뷰모델, G4 화면 쪽, G5 `주제 후보` 자리, **Legacy 절대 횟수 칸의 화면 이름·단위(보완)** |
| `tests/test_topic_protect_suggest.py` | 새 | 338 | 특성 시험 26개 — G2 제안 엔진(다섯 카드 예시 포함), G4 제안 서비스 쪽, **보관함 후보 우선도의 같은 계절 오탐(보완)** |
| `tests/test_topic_protect_candidates.py` | 새 | 245 | 특성 시험 19개 — G3 후보 모양·CSV·설정 엄격성, G4 채널 열거, **명령줄의 Legacy 횟수 이름·단위(보완)** |
| `docs/TOPIC_ENGINE_PLAN.md` | 새 | 396 | 계획 문서(400줄 이내) — 7절이 기존 `search_demand` 의미 조사 |
| `docs/DECISIONS.md` | +6행 | 41~46행 | D-36~D-41(표 끝, 보완에서 운영자 말과 이 계획의 해석을 나눠 다시 씀). 기존 D-01~D-34 는 한 글자도 안 바뀜(CRLF 유지) |
| `CHANGELOG.md` | +1줄 | 39행 | 맨 끝 한 줄 |

**바꾸지 않은 곳**: `src/` 전부(0줄 — 오타·주석 포함), 기존 시험 전부(고치거나 약화한 것 0), `README.md`·`docs/ARCHITECTURE.md`·`ci.yml`·`vendor/`.

### ② 추가·변경된 시험
- **추가 76개**(모듈별: ui 31 · suggest 26 · candidates 19 — 1차 65개 + 보완 1차 8개 + 2차 3개). **변경한 기존 시험 0개.** 모든 시험 위에 한국어 주석 한 줄('특성 시험(P0): 현재 동작을 못박는다. 바꾸려면 새 결정(D-nn)을 쓰고 이 시험을 의식적으로 고친다.')이 있고 76/76 을 스크립트로 확인했다. PySide6·네트워크·`subprocess`·실제 시계 없음.
- **`KNOWN_DEFECT` 11개**(이름·주석에 표시 — 뒤 단계가 의도적으로 뒤집는다):
  1. `test_topic_protect_suggest.SeasonFitCardTest.test_KNOWN_DEFECT_graphics_card_and_cadmium_match_the_year_end_tax_season_only_because_they_contain_card` — **다섯 카드 예시** 중 오탐 둘(그래픽카드·카드뮴)
  2. `…GraphicsCardTopSuggestionTest.test_KNOWN_DEFECT_profile_b_in_november_ranks_a_year_end_tax_title_for_graphics_cards_first` — 프로필 B 11월 1위 '연말정산 준비 시기에 챙겨 볼 그래픽카드 정리' **100.0 높음**(직접 돌려 확인한 값)
  3. `…test_KNOWN_DEFECT_the_same_title_wins_when_the_graphics_card_seed_comes_from_the_category` — 씨앗이 카테고리에서 오면 같은 제목 94.7
  4. `…test_KNOWN_DEFECT_the_year_end_title_appears_only_in_the_months_whose_table_holds_card` — 11·12·1·2월에만 나타남, 6월엔 없음
  5. `…RiskySeedTest.test_KNOWN_DEFECT_health_and_brand_seeds_pass_into_suggestions_with_no_caution_mark` — '영양제'·'불면증 해결'·'삼성 갤럭시' 씨앗이 표시 없이 통과('체험단 모집' 은 버려짐)
  6. `…RelativeIndexScoreEffectTest.test_KNOWN_DEFECT_a_relative_index_of_87_is_scored_as_87_searches_and_lowers_the_priority` — 우선도 81.8 → 72.6
  7. `test_topic_protect_candidates.RelativeIndexLooksLikeACountTest.test_KNOWN_DEFECT_the_number_87_passes_as_a_monthly_search_demand_of_87_with_no_way_to_tell_an_index_from_a_count`
  8. `…test_KNOWN_DEFECT_the_same_87_scores_far_below_87_because_it_is_read_as_a_count` — 기회도 38.89
  9. `…CsvAndTrendColumnTest.test_KNOWN_DEFECT_a_column_named_search_volume_is_taken_as_the_monthly_search_demand` — CSV `검색량` 열 87 → 월간 검색 수요 87
  10. `test_topic_protect_ui.ToTopicTest.test_KNOWN_DEFECT_a_rejected_candidate_is_filtered_by_load_home_not_by_the_mapping` — 제외 후보가 표에 없어 'new' 로 바뀜(홈에서 안 보이는 것은 `load_home` 이 먼저 거르기 때문)
  11. `test_topic_protect_suggest.StoredCandidatePriorityTest.test_KNOWN_DEFECT_a_stored_candidates_priority_also_reads_graphics_card_and_cadmium_as_the_year_end_season` — **(보완)** 보관함 후보의 우선도도 같은 오탐: 그래픽카드·카드뮴 후보 89.1(평범한 낱말 81.8), 프로필 B 가 있으면 92.9
- **운영자 조건 5(다섯 카드 예시) — 현재 동작을 먼저 못박았다**(`season_fit(낱말, 11)` 을 실제로 돌려 확인): 그래픽카드·신용카드·체크카드·카드값·카드뮴 **다섯 모두 `(70, '연말정산 준비')`**.
  - 그래픽카드·카드뮴 = 오탐(`KNOWN_DEFECT`, P0b 가 `(50, None)` 으로 뒤집는다).
  - 신용카드·체크카드·카드값(과 '카드 혜택'·'카드') = 의도한 일치 → `test_the_card_words_the_operator_means_to_match_do_match_the_year_end_tax_season`(일반 시험, P0b 뒤에도 그대로여야 함).
  - 추가 반례 사운드카드·교통카드·메모리카드도 지금은 같은 값 — **옳고 그름은 정하지 않고 현재 값만** 기록(`test_other_words_that_only_contain_card_also_match_today_and_p0b_decides_each`, 판단은 P0b 구현자).
  - 다른 달: 1·2·12월은 `'연말정산'` 항목에 걸리고 6월은 걸리지 않는다(`test_the_same_five_words_match_the_neighbouring_year_end_items…`).
- **Legacy `search_demand` 조건 1**: '새 필드가 아직 없다/이름이 겹치지 않는다' 수준만 — `test_the_candidate_has_none_of_the_new_engine_names_and_no_field_says_where_a_number_came_from`(새 엔진 이름 24개가 `Candidate` 칸에 하나도 없고, 저장 키는 지금 24개 그대로다), 모르는 칸 거절 시험이 같은 24개 이름을 `from_dict`·`edited` 양쪽으로 거절하는지 본다.
- **보호 범위(요청서 G1~G5)**: G1 우선도 라벨 69/70·39/40 을 `to_topic` 까지 · 상태 5종 · 블로그 키 10가지 조합 · `load_home` 후보 0·1·5·6·50 × A만/B만/둘 다 15가지 · 홈 행 5·칩 5·필터·정렬(우선도→최신 날짜, 동률은 먼저 만든 후보가 위)·보류 제외 / G2 결정성 A·B × 6·11월 4경우(첫 셋 손으로 옮긴 값) · 다섯 카드 · 위험 씨앗 / G3 `search_demand=87` · 로그 눈금 기준점 9개(0·1·10·87·100·1,000·10,000·10만·100만) · 모르는 칸 거절 · CSV `검색량`·`트렌드` · 설정 엄격성 / G4 `BLOG_KEYS`·`BLOG_NAMES`·`HOME_CHIPS`·`profile_for`·`OTHER_BLOG_GUIDANCE`·`NaverProfile`·`PLATFORMS`·`PLATFORM_FAMILY`·채널 이름 대응 / G5 `NAV` 의 `topics`·카드 `go`·자리표시·서랍.

### ③ 전체 시험 결과
**전체(`discover`)는 지시에 따라 돌리지 않았다**(PC 메모리 2GB 안팎 — 코디네이터가 CI 네 칸으로 본다). 대신 요청서의 모듈을 **한 번에 하나씩** 3.12.10 과 진짜 3.10.11 로 돌렸다(PySide6 없음 — Qt 시험은 건너뜀). 실제 줄:

```text
새 시험 (보완 2차 뒤 최종 실행)                         3.12.10                    3.10.11
test_topic_protect_ui          Ran 31 tests in 0.784s  OK        Ran 31 tests in 0.804s  OK
test_topic_protect_suggest     Ran 26 tests in 3.575s  OK        Ran 26 tests in 3.620s  OK
test_topic_protect_candidates  Ran 19 tests in 0.091s  OK        Ran 19 tests in 0.098s  OK
test_repo_layout               Ran 26 tests in 1.759s  OK        Ran 26 tests in 1.562s  OK

요청서의 기존 시험 모듈(1차 때 실행한 값 — 보완은 소스·기존 시험을 안 바꿨으므로 그대로)
test_ui_adapters               Ran 25 tests in 3.120s  OK        Ran 25 tests in 3.187s  OK
test_ui_core                   Ran 94 tests in 3.481s  OK        Ran 94 tests in 3.584s  OK
test_suggest                   Ran 113 tests in 15.556s OK       Ran 113 tests in 17.013s OK
test_suggest_score             Ran 29 tests in 0.015s  OK        Ran 29 tests in 0.020s  OK
test_suggest_data              Ran 12 tests in 6.175s  OK        Ran 12 tests in 6.227s  OK
test_content_candidates        Ran 121 tests in 0.379s OK        Ran 121 tests in 0.408s OK
test_candidate_csv             Ran 67 tests in 0.532s  OK        Ran 67 tests in 0.598s  OK
test_service_write_json        Ran 19 tests in 0.439s  OK        Ran 19 tests in 0.509s  OK

문서를 읽는 다른 기존 모듈(문서 갱신 뒤 확인)
test_service_candidates_cli    Ran 60 tests in 10.383s OK        Ran 60 tests in 12.836s OK
test_errors_catalog            Ran 37 tests in 2.132s  OK        Ran 37 tests in 1.988s  OK
test_content_model             Ran 34 tests in 0.015s  OK        Ran 34 tests in 0.019s  OK
test_content_draft_options     Ran 79 tests in 2.195s  OK        Ran 79 tests in 2.252s  OK
test_service_draft_token       Ran 13 tests in 3.411s  OK        Ran 13 tests in 3.603s  OK
(test_ui_core 를 문서 갱신 뒤 다시: 94 tests OK 2.989s / 3.198s)
```
- **CI 네 칸(Windows·Ubuntu × 3.10·3.12)은 확인하지 못했다** — push 를 하지 않았으므로. Ubuntu 는 이 PC 에서 돌리지 못했다(시험은 경로·줄바꿈에 기대지 않고 임시 폴더만 쓴다).
- **병합 순서 확인**: 공개 가지 `origin/ai/claude/r134-naver-hub-safety-1`(N1, 머리 `b2096ce`) 머리를 임시 detached 작업 폴더로 받아 내 새 시험 3개를 복사해 돌렸다 → 1차(65개)는 3.12 에서 25·22·18 OK·3.10 에서 65 OK, **보완 뒤 73개도 3.12·3.10 모두 `Ran 73 tests … OK`**. 임시 폴더는 지웠다. N1 과 내 가지를 `git merge-tree` 로 합쳐 보면 **`CHANGELOG.md`·`docs/DECISIONS.md` 두 파일만 충돌**(둘 다 맨 끝에 줄을 더해서)이고 나머지는 자동으로 합쳐진다 — 둘 다 남기고 D-35 를 D-36 앞에 두면 된다.

### ④ 기존 기능 영향
**없다.** 근거: ① `src/` 변경 0줄(`git diff --stat origin/main..HEAD` 의 파일 6개가 모두 `tests/`·`docs/`·`CHANGELOG.md`) ② 기존 시험 파일 변경 0 ③ 위 기존 모듈 14개(요청서 9개 + 문서를 읽는 5개)가 3.12·3.10 모두 그대로 통과 ④ 새 시험은 현재 동작을 못박았을 뿐 기능을 더하지 않았다. 새 시험 76개가 일부러 깨뜨린 소스를 **67곳 중 동작을 깨뜨리는 62곳 모두** 잡았다(나머지 5곳은 동작이 같은 정리·오경보 방지라 통과가 맞다 — 위 000절).

### ⑤ 다음 단계에서 발생할 동작 변화
| 단계 | 동작 변화 | 이때 의식적으로 고쳐야 하는 이 시험들 |
|---|---|---|
| **P0b**(계절 부분 일치 수정) | 제안 결과가 **의도대로** 바뀐다 — 프로필 B 의 11·12·1·2월 제안에서 '…시기에 챙겨 볼 그래픽카드 정리'가 사라지고 11월 1위가 바뀐다(`generated` 74·`filtered`·순위 변화). **보관함 후보의 우선도 계산(`candidates list --priority`·`candidates show`)도 같은 `season_fit` 이라 '그래픽카드'·'카드뮴' 후보의 시기 요인이 70 → 50 이 되어 점수(89.1 → 81.8)와 추천 이유의 시기 문장이 바뀐다.** 신용카드·체크카드·카드값은 그대로 걸려야 한다 | `SeasonFitCardTest` 의 KNOWN_DEFECT 1개(그래픽카드·카드뮴을 `(50, None)` 으로)·`…other_words_that_only_contain_card…`(사운드카드 등 — 판단에 따라)·`…neighbouring_year_end_items…`(그래픽카드·카드뮴 행)·`…substring_both_ways…`('부가세금액'·'의료'·'직장' 은 토큰/구문 방식에 따라 달라질 수 있음) · `GraphicsCardTopSuggestionTest` 의 KNOWN_DEFECT 3개 · `StoredCandidatePriorityTest` 의 KNOWN_DEFECT 1개 · `DeterminismAndSnapshotTest.test_the_first_three_suggestions_and_the_counts_for_the_four_cases` 의 B·11월 줄 |
| P1 | 없음(새 순수 모듈) | `test_the_candidate_has_none_of_the_new_engine_names…` 는 엔진 모델이 `Candidate` 와 따로 있는 한 그대로 통과해야 한다 |
| P2 | 건강·브랜드 표시가 생기면 위험 씨앗 결과가 바뀐다(새 모듈이 더하고 `suggest*` 는 그대로면 변화 없음) | `RiskySeedTest` KNOWN_DEFECT 1개·`…no_caution_or_disclosure_field`(JSON 칸 고정)·`…risky_word_list…` |
| P3 | 처음 쓸 때 `topic_engine.db` 가 새로 생김(기존 보관함·설정 그대로) | 변화 없음 — 오히려 `SettingsStrictnessTest`·보관함 판 고정 시험이 계속 통과해야 한다 |
| P4 | `주제 후보` 화면이 생기고 `월 검색량` 라벨 처리가 바뀐다(Legacy 칸 표시, 새 Trend 칸은 `최근 관심도(상대값)`) | `TopicsPlaceholderTest` 전부·`test_the_qt_shell_source_picks_home…`(Qt 소스 두 줄) · `LegacyDemandLabelTest.test_the_screen_text_has_no_relative_interest_label_yet…`(빈 목록 — 새 문구를 더할 때 고침. 나머지 세 시험은 Legacy 문구를 지켜야 하므로 그대로) · 기존 `test_ui_core` 서랍 항목 목록 |
| P5·P6 | 실제 Trend 호출·나머지 3채널 후보 생성 켜기 | `ChannelTwoAssumptionTest`·`OtherChannelsInTheSuggestionServiceTest`(P6 에서 세 채널을 켤 때) |

### ⑥ 데이터 마이그레이션 여부
**없다.** 이 단계는 데이터 파일·스키마를 건드리지 않았다. 계획상으로도 새 데이터는 별도 `topic_engine.db` + JSON 셋에 두고 **기존 `chanceblog.db`(판 2)·`settings.json`·후보 JSON 은 바꾸지 않아 마이그레이션이 없다**(`topic_engine.db` 는 처음 쓸 때 새로 생김). R-131 §7 의 '보관함 판 2→3' 은 이 지시로 대체됐고 문서에서 '판 3' 표현을 모두 지웠다. 보관함 판 고정 시험(`test_content_migration.DdlFreezeTest.test_the_documented_numbers_are_these_literal_ones` — `SCHEMA_VERSION` 2·`MIGRATIONS` 키 `{1}`)은 건드리지 않았다.

---

## 1. 가장 중요한 5가지
1. **기존 동작을 먼저 못박았다.** 새 특성 시험 76개(3모듈)가 3.12·3.10 에서 통과하고 `src/` 와 기존 시험은 한 글자도 안 바뀌었다 — WIP 커밋 `1f2297b`(1차)·`4c746d6`(보완 1차)·`23ca08e`(보완 2차), 로컬·push 안 함.
2. **알려진 결함 11개를 '현재 그대로' 못박았다.** 다섯 카드 예시는 모두 `(70, '연말정산 준비')`(그래픽카드·카드뮴이 오탐), 프로필 B 11월 1위는 '연말정산 준비 시기에 챙겨 볼 그래픽카드 정리' 100점, 상대지수 87 은 '월간 검색 수요 87'로 저장되어 기회도 38.89점이 된다.
3. **변이 점검 67곳**: 동작을 깨뜨리는 62곳을 모두 잡고, 동작이 같은 정리 4곳과 오경보 방지 1곳은 통과한다(2곳은 처음에 살아남아 시험을 보강한 뒤). 'season_fit 부분 일치 → 정확 일치' 변이는 하위 시험까지 24건이 잡는다.
4. **`search_demand` 조사 결론(이 조사의 결론 — 운영자 말이 아니다): 'Legacy 유지·자동 이전 없음'이 맞다** — 운영자 지시(조건 1: 의미가 불명확하면 Legacy 유지)를 이 값에 적용한 것이다. 값의 뜻은 '월간 검색 수(회)'로 일관되지만 공급자·기간 칸도 수집 코드도 없다. 요청서의 결론 후보(코디네이터 가설)와 달랐던 두 가지: 공급자는 검색광고 한 곳이 아니고 오픈 API(데이터랩)도 같은 칸을 채우는 용도로 적혀 있음 · 'PC+모바일 합'은 코드·문서에 없음.
5. **계획 문서·D-36~D-39 를 운영자 승인으로 확정했다**(별도 `topic_engine.db`, 마이그레이션 없음). 번호 연속을 요구하는 시험이 없어 D-35 를 비운 채 D-36 부터 만들었고, N1 가지와는 `DECISIONS.md`·`CHANGELOG.md` 끝에서만 충돌한다.

## 2. 변이 점검 표 (임시 사본 `W\p25p0_mut`, 작업 폴더는 건드리지 않음 — 끝나고 사본의 소스가 작업 폴더와 바이트까지 같은지 확인, 52곳)
52곳을 일부러 깨뜨리고 새 시험 3개 모듈(73개)을 돌렸다(M01~M42 는 65개로, M43~M52 는 73개로). **놓침 0**. 처음에 놓친 둘(M09·M17)은 시험을 보강(칩 시험에 `flat` 추세 후보 추가 / 부분 일치 시험에 '의료'·'직장' 추가)한 뒤 잡혔다. 같은 변이를 한 시험이 여러 번 잡으면 '잡은 시험 수'가 크다(하위 시험 포함).

| 번호 | 영역 | 변이(소스를 이렇게 바꿈) | 결과 | 먼저 잡은 시험 | 잡은 건수 |
|---|---|---|---|---|---:|
| M01 | G1 | 우선도 라벨 경계 70→71 · `ui/adapters.py` | 잡힘 | `the_priority_label_boundaries_reach_the_topic_through_to_topic` | 1 |
| M02 | G1 | 우선도 라벨 경계 40→41 · `ui/adapters.py` | 잡힘 | `the_priority_label_boundaries_reach_the_topic_through_to_topic` | 1 |
| M03 | G1 | 상태 표: 검토(REVIEW) → selected · `ui/adapters.py` | 잡힘 | `the_five_candidate_states_become_new_new_selected_hold_and_new` | 1 |
| M04 | G1·G4 | BLOG_KEYS 에 키 추가 · `ui/adapters.py` | 잡힘 | `only_naver_profiles_can_rename_a_blog_and_other_keys_in_the_settings_are_igno…` | 6 |
| M05 | G1 | 정렬 키 뒤집기(최신 날짜) · `ui/core/app_state.py` | 잡힘 | `rows_stop_at_five_but_the_chips_and_the_card_count_every_live_topic` | 1 |
| M06 | G1 | 모르는 우선도 라벨을 맨 앞으로 · `ui/core/app_state.py` | 잡힘 | `equal_priority_and_date_keep_the_input_order_and_an_unknown_priority_comes_la…` | 1 |
| M07 | G1 | 홈 행 수 5→6 · `ui/core/app_state.py` | 잡힘 | `the_home_chips_are_five_in_this_order_and_only_a_and_b_name_a_blog` | 9 |
| M08 | G4 | HOME_CHIPS 의 a·b 순서 바꾸기 · `ui/core/app_state.py` | 잡힘 | `the_home_chips_are_five_in_this_order_and_only_a_and_b_name_a_blog` | 10 |
| M09 | G1 | '급상승' 칩 기준 넓히기 · `ui/core/app_state.py` | 잡힘 | `chip_counts_follow_the_blog_trend_and_status_of_each_live_topic_and_never_cou…` | 1 |
| M10 | G1 | 제외한 후보를 거르지 않기 · `ui/adapters.py` | 잡힘 | `KNOWN_DEFECT_a_rejected_candidate_is_filtered_by_load_home_not_by_the_mapping` | 1 |
| M11 | G1 | 블로그 후보 수에 보류도 세기 · `ui/adapters.py` | 잡힘 | `held_candidates_are_saved_ideas_and_do_not_count_toward_a_blogs_candidates` | 1 |
| M12 | G5 | 메뉴 키 topics 이름 바꾸기 · `ui/core/app_state.py` | 잡힘 | `every_screen_but_home_shows_the_same_placeholder_text_with_its_own_name` | 5 |
| M13 | G5 | 저장된 아이디어 카드의 이동 대상 지우기 · `ui/core/app_state.py` | 잡힘 | `the_home_cards_for_recommended_topics_and_saved_ideas_go_to_topics_and_the_ot…` | 1 |
| M14 | G5 | 화면을 옮겨도 서랍을 닫지 않기 · `ui/core/app_state.py` | 잡힘 | `leaving_home_closes_the_drawer_and_a_drawer_opened_on_another_page_is_only_a_…` | 1 |
| M15 | G5 | 서랍을 홈 밖에서도 보이기(Qt 소스) · `ui/qt/shell.py` | 잡힘 | `the_qt_shell_source_picks_home_or_the_placeholder_and_shows_the_drawer_on_hom…` | 1 |
| M16 | G2 | season_fit 부분 일치를 정확 일치로(= KNOWN_DEFECT 시험이 잡아야 한다) · `content/suggest_score.py` | 잡힘 | `KNOWN_DEFECT_the_same_title_wins_when_the_graphics_card_seed_comes_from_the_c…` | 24 |
| M17 | G2 | season_fit 의 '글 낱말 ⊂ 이어지는 낱말' 한쪽만 남기기 · `content/suggest_score.py` | 잡힘 | `the_matching_is_substring_both_ways_so_a_short_word_inside_a_long_related_wor…` | 1 |
| M18 | G2 | 위험 씨앗 목록에서 '체험단' 빼기 · `content/suggest.py` | 잡힘 | `KNOWN_DEFECT_health_and_brand_seeds_pass_into_suggestions_with_no_caution_mark` | 3 |
| M19 | G2 | 위험 씨앗 목록에 '영양제' 더하기 · `content/suggest.py` | 잡힘 | `KNOWN_DEFECT_health_and_brand_seeds_pass_into_suggestions_with_no_caution_mark` | 3 |
| M20 | G2 | 같은 점수일 때 정렬 열쇠를 조합 순서에서 키워드로 · `content/suggest.py` | 잡힘 | `the_first_three_suggestions_and_the_counts_for_the_four_cases` | 5 |
| M21 | G2 | 시기와 이어지는 주제 점수 70→65 · `content/suggest_score.py` | 잡힘 | `the_first_three_suggestions_and_the_counts_for_the_four_cases` | 1 |
| M22 | G2 | (자료) 11월 시기 표에서 연말정산 준비의 이어지는 낱말 '카드' 지우기 · `content/suggest_data.py` | 잡힘 | `KNOWN_DEFECT_the_same_title_wins_when_the_graphics_card_seed_comes_from_the_c…` | 15 |
| M23 | G2 | 시기 가중치 20→25 · `content/suggest_score.py` | 잡힘 | `the_first_three_suggestions_and_the_counts_for_the_four_cases` | 4 |
| M24 | G4 | 다른 블로그 안내문 바꾸기 · `service/suggestions.py` | 잡힘 | `a_suggestion_for_a_non_naver_blog_is_an_empty_list_with_the_other_blog_guidan…` | 1 |
| M25 | G4 | 다른 블로그 안내문을 아예 안 붙이기 · `service/suggestions.py` | 잡힘 | `a_suggestion_for_a_non_naver_blog_is_an_empty_list_with_the_other_blog_guidan…` | 3 |
| M26 | G3 | edited 가 모르는 칸을 받게 하기 · `content/candidates.py` | 잡힘 | `the_strategy_style_and_engine_names_are_refused_as_unknown_fields_when_read_a…` | 25 |
| M27 | G3 | from_dict 가 모르는 칸을 받게 하기 · `content/candidates.py` | 잡힘 | `the_strategy_style_and_engine_names_are_refused_as_unknown_fields_when_read_a…` | 24 |
| M28 | G3 | 수요 로그 눈금의 꽉 찬 값 10만→100만 · `content/suggest_score.py` | 잡힘 | `KNOWN_DEFECT_a_relative_index_of_87_is_scored_as_87_searches_and_lowers_the_p…` | 2 |
| M29 | G3 | 트렌드 열이 숫자도 받게 하기(모르는 글은 보합) · `content/candidate_csv.py` | 잡힘 | `a_trend_column_takes_only_the_three_words_so_a_number_in_it_is_refused_with_t…` | 4 |
| M30 | G3 | CSV 열 별칭에서 '검색량' 빼기 · `content/candidate_csv.py` | 잡힘 | `KNOWN_DEFECT_a_column_named_search_volume_is_taken_as_the_monthly_search_dema…` | 1 |
| M31 | G3 | 설정 파일이 모르는 최상위 칸을 받게 하기 · `service/context.py` | 잡힘 | `an_unknown_top_level_field_makes_the_settings_unreadable_and_the_file_is_left…` | 4 |
| M32 | G4 | 네이버 프로필 키에 github_pages 추가 · `content/profiles.py` | 잡힘 | `a_suggestion_for_a_non_naver_blog_is_an_empty_list_with_the_other_blog_guidan…` | 4 |
| M33 | G4 | PLATFORMS 순서 바꾸기(blogger_ko 가 en 보다 앞) · `content/status.py` | 잡힘 | `platforms_run_pages_then_blogger_english_then_blogger_korean_then_naver_a_and…` | 1 |
| M34 | G4 | 채널 이름 대응 뒤바꾸기(영문↔한글) · `service/format.py` | 잡힘 | `the_strategys_blogger_a_korean_and_b_english_are_blogger_ko_and_blogger_en_in…` | 1 |
| M35 | G4 | BLOG_NAMES 에 항목 추가 · `ui/core/app_state.py` | 잡힘 | `a_blog_key_outside_a_and_b_gets_no_badge_in_the_view_model` | 2 |
| M36 | G1 | 아이콘 돌려 쓰기 주기 6→3 · `ui/adapters.py` | 잡힘 | `icons_cycle_by_position_keywords_are_cut_and_the_date_falls_back_to_the_creat…` | 1 |
| M37 | G3 | 검색 수요 상한 10억→100 · `content/candidates.py` | 잡힘 | `the_label_is_the_candidates_own_priority_and_never_a_computed_score` | 3 |
| M38 | G2 | 제안 JSON 에 건강 표시 칸 하나 더하기 · `content/suggest.py` | 잡힘 | `the_report_and_suggestion_json_have_exactly_these_fields_and_no_caution_or_di…` | 1 |
| M39 | G4 | 네이버 주소 허용 목록에 다른 블로그 주소 더하기 · `content/model.py` | 잡힘 | `a_naver_profile_accepts_only_naver_a_or_b_and_a_naver_blog_address` | 1 |
| M40 | G5 | 자리표시 화면의 단추 글 바꾸기 · `ui/core/text.py` | 잡힘 | `every_screen_but_home_shows_the_same_placeholder_text_with_its_own_name` | 5 |
| M41 | G1 | 조회일이 없을 때의 날짜 자르기 10→7 · `ui/adapters.py` | 잡힘 | `icons_cycle_by_position_keywords_are_cut_and_the_date_falls_back_to_the_creat…` | 1 |
| M42 | G1 | 후보의 블로그 배지 순서를 B→A 로 · `ui/adapters.py` | 잡힘 | `to_topic_keeps_only_the_two_naver_blogs_in_a_then_b_order` | 2 |
| M43 | L1 | 행의 Legacy 지표 이름 '월 검색량' 을 '최근 관심도(상대값)' 로 재라벨(운영자가 금지한 일) · `ui/core/text.py` | 잡힘 | `none_of_the_legacy_count_labels_borrows_the_relative_interest_wording` | 4 |
| M44 | L1 | 서랍의 Legacy 항목 이름을 '최근 관심도(상대값)' 로 재라벨 · `ui/core/text.py` | 잡힘 | `none_of_the_legacy_count_labels_borrows_the_relative_interest_wording` | 5 |
| M45 | L1 | Legacy 횟수의 '회' 단위 지우기 · `ui/core/text.py` | 잡힘 | `the_legacy_absolute_count_is_called_monthly_search_volume_and_counted_in_time…` | 2 |
| M46 | L1 | Legacy 툴팁을 상대값 설명으로 바꾸기 · `ui/core/text.py` | 잡힘 | `none_of_the_legacy_count_labels_borrows_the_relative_interest_wording` | 3 |
| M47 | L1 | Legacy 횟수의 천 단위 쉼표 지우기 · `ui/core/text.py` | 잡힘 | `the_legacy_absolute_count_is_called_monthly_search_volume_and_counted_in_time…` | 2 |
| M48 | L1 | 명령줄 출력의 Legacy 횟수 '회' 단위 지우기 · `service/format.py` | 잡힘 | `the_command_line_prints_the_legacy_count_as_monthly_search_demand_in_times_an…` | 1 |
| M49 | L1 | Legacy 칸의 이름(LABELS)을 '최근 관심도(상대값)' 로 재라벨 · `content/candidates.py` | 잡힘 | `the_command_line_prints_the_legacy_count_as_monthly_search_demand_in_times_an…` | 2 |
| M50 | L2 | 보관함 후보 평가가 시기 낱말을 아예 안 읽기 · `content/suggest.py` | 잡힘 | `KNOWN_DEFECT_a_stored_candidates_priority_also_reads_graphics_card_and_cadmiu…` | 6 |
| M51 | L2 | 보관함 후보의 외부 계절성이 이번 달이 아닐 때 점수 30→50 · `content/suggest.py` | 잡힘 | `external_months_on_the_candidate_decide_the_season_factor_without_reading_the…` | 1 |
| M52 | L1 | 서랍 첫 항목을 월간 검색량에서 PC·모바일 비중으로 바꾸기 · `ui/core/app_state.py` | 잡힘 | `the_row_and_the_drawer_show_the_legacy_count_with_the_times_unit_and_the_mont…` | 1 |

합계: **52곳 중 52곳 잡힘, 놓침 0.** 영역별(표의 '영역' 칸 그대로; L1 = Legacy 절대 횟수 칸의 이름·단위, L2 = 보관함 후보 우선도의 계절 요인) — G1 12곳, G1·G4 1곳, G2 9곳, G3 7곳, G4 8곳, G5 5곳, L1 8곳, L2 2곳. 앞 42곳(M01~M42)은 1차, M43~M52 는 보완 1차에서 더했다.

참고: `service/suggestions.profile_for` 의 `if blog not in NAVER_KEYS: return None` 을 지우는 변이는 시도하지 않았다 — 설정이 네이버 키 밖의 프로필을 거절하므로 결과가 같은 **동등 변이**다(안전 확인: `SettingsStrictnessTest`).

## 3. '이미 있어서 더하지 않은 시험' (겹치지 않게 더함 — 거기에 없는 경계·조합만 새로 씀)
| 요청서 항목 | 기존 시험 이름 |
|---|---|
| 우선도 라벨 낱개(None·0·39.9·40·69.9·70·100) | `test_ui_adapters.AdapterTest.test_priority_labels` (새 시험은 `to_topic` 까지 이은 경계 69/70·39/40) |
| 메뉴 여섯·이름·순서 | `test_ui_core.ServicesAndStateTest.test_the_menu_has_exactly_six_entries_in_the_operator_order` |
| 홈 카드 넷·행 다섯·칩 다섯의 이름 | `…test_home_view_has_four_cards_five_rows_and_five_chips` |
| 칩 필터·선택 유지 | `…test_chips_filter_rows_and_keep_a_valid_selection` |
| 보류 제외·저장된 아이디어 | `…test_held_topics_are_not_recommended_but_counted_as_saved_ideas` · `test_ui_adapters.AdapterTest.test_rejected_candidates_are_left_out_and_held_ones_count_as_saved_ideas` |
| 예시 데이터 정렬(우선도→최신) | `…test_the_home_list_is_ordered_by_priority_then_newest_with_hand_written_expectations` (새 시험은 동률·모르는 라벨·5행 자르기·칩 거르기 순서) |
| 서랍 항목 8개 | `…test_the_drawer_shows_details_and_no_internal_ids` |
| A·B 밖 블로그의 배지 없음(부분) | `test_ui_adapters.AdapterTest.test_the_blog_names_come_from_the_naver_profiles_and_counts_from_the_candidates` |
| 월 표 12개월×8~15항목·이름 있는 시기 낱말 | `test_suggest_data.SeasonTableTest.test_every_month_is_there_with_eight_to_fifteen_items` · `…test_the_usual_yearly_topics_the_brief_names_are_in_the_table` |
| 제안 결정성(프로필 하나·해시 시드 독립) | `test_suggest.DeterminismTest` 3개 (새 시험은 프로필 A·B × 6·11월) |
| 위험 낱말 32개 전수 | `test_suggest.SeedFilterTest.test_every_word_of_the_experience_and_guarantee_list_is_pinned_by_a_test` |
| 점수 상수·구간·수요 양 끝 | `test_suggest_score.ConstantsTest` · `…OpportunityTest.test_one_part_alone_is_that_part` (새 시험은 중간 기준점 0·1·10·87·100·1,000·10,000·100만) |
| 다른 블로그 안내문(부분) | `test_service_suggestions.InputsTest.test_a_blog_without_a_saved_profile_gets_the_profile_guidance_and_a_non_naver_blog_gets_its_own_note` |
| **후보 한 행이 깨지면 `list_candidates` 가 `CANDIDATE_CORRUPT`** (요청서: 있으면 생략) | `test_content_candidates_store.MessagesTest.test_a_corrupt_candidate_blocks_the_list_but_can_be_deleted_alone_and_the_others_stay` · `test_content_candidates_batch.CandidateIdsTest.test_a_corrupt_candidate_that_blocks_the_list_still_has_its_number_listed` |
| **CSV 모르는 열 무시 + 알림** (있으면 생략) | `test_candidate_csv.HeaderTest.test_unknown_columns_are_ignored_and_listed` · 별칭 전수 `…test_every_accepted_name_works_in_korean_and_english_whatever_the_spacing_case_or_underscores` |
| `from_dict` 가 모르는 칸 거절(일반) | `test_content_candidates.JsonShapeTest.test_unknown_or_malformed_stored_data_is_refused_not_repaired` (새 시험은 전략·엔진 이름 24개를 `from_dict`·`edited` 양쪽으로) |
| `PLATFORMS` 순서 | `test_content_candidates.ValidationTest.test_blogs_are_one_or_more_distinct_known_platforms_and_keep_the_order_given`(값 비교) · `test_content_candidates_store.ProjectsStillWorkTest.test_every_platform_name_the_candidates_use_is_a_platform_of_the_content_model` (새 시험은 `PLATFORM_FAMILY` 값·순서와 채널 이름 대응) |
| `NaverProfile` 키·주소(일반) | `test_naver_profiles.ValidationTest.test_the_blog_key_is_one_of_the_two` · `…test_the_blog_address_must_be_a_plain_https_naver_blog_address` (새 시험은 다른 세 채널 키·블로그스팟·티스토리 주소) |
| **설정 파일 모르는 최상위 칸 → `SETTINGS_INVALID`** (있으면 생략) | **찾지 못해 새로 더했다**: `test_topic_protect_candidates.SettingsStrictnessTest`(`SETTINGS_INVALID` 가 나오는 기존 시험은 깨진 파일·값 오류 쪽뿐이었다) |
| **기존 절대 횟수 칸의 행 라벨 `T["demand"]`(보완)** | **기존 시험 중 없다** — 서랍 라벨 목록(`test_the_drawer_shows_details_and_no_internal_ids`)과 '회' 단위 쪽은 이미 잡지만 행 라벨 재라벨(M43)은 `test_ui_core`+`test_ui_adapters` 가 놓친다(기준선과 같은 결과). 그래서 새로 더했다: `test_topic_protect_ui.LegacyDemandLabelTest` |
| 보관함 `SCHEMA_VERSION`·`MIGRATIONS` 키·DDL 해시 | `test_content_migration.DdlFreezeTest.test_the_documented_numbers_are_these_literal_ones`(`SCHEMA_VERSION` 2·`MIGRATIONS` `{1}`)·`test_content_candidates_store.py:885` — **건드리지 않았다** |

## 4. 기존 `search_demand` 의미 조사 (운영자 조건 1 — 계획 문서 7절과 같은 내용, 인용은 내가 코드에서 다시 확인)
읽기 전용 조사. **사실**은 코드·문서에서 직접 읽은 것, **추정**은 표시했다.

| # | 질문 | 답 (`파일:줄`) |
|---|---|---|
| ① | 값이 어디로 들어오나 | **사람이 적는 길뿐**이다 — 명령줄 `candidates add --search-demand N`(`service/cli.py:627`, 단위 표시 `metavar="회"`·모으는 곳 `:502`), CSV 열 별칭 '월간 검색 수요'·'검색량'·'monthly searches' 등(`content/candidate_csv.py:47`, 읽기 `:370`), 코드의 `Candidate.new(search_demand=…)`(`content/candidates.py:444`). **모으는 코드는 없다**(`docs/ARCHITECTURE.md:85`·`README.md:61`·D-29 ②). 제안은 값을 만들지 않고 보관함의 같은 키워드 후보 값을 읽기만 한다(`content/suggest.py:210-220`, 제안을 후보로 넣을 때도 지표를 안 넣는다 `service/suggestions.py:256`) |
| ② | 공급자·측정 기간·조회 방법을 적는 칸이 있나 | **없다.** `Candidate` 23칸(+`schema`)에서 출처에 가까운 것은 조회일 `data_date`(지표가 하나라도 있으면 필수 `content/candidates.py:423-426`)와 자유 글 `reason` 뿐. CSV 에 '출처'·'기간' 열을 넣어도 별칭표에 없어 모르는 열로 무시되고 알림만 남는다(`candidate_csv.py:41-58`·`service/candidates.py:512`). 새 시험이 칸 목록을 못박는다 |
| ③ | 문서·설계 흔적은 무엇을 가리키나 | 값의 뜻은 **'월간 검색 수요(회)'** 로 일관된다 — `content/candidates.py:70`(라벨)·`:370`(주석 '월간 검색 수요(회)'), `docs/ARCHITECTURE.md:128`·`:140`, `README.md:65`, `docs/UI_DESIGN_SPEC.md:62`·`:100`, `docs/UI_STATES.md:18`. **공급자는 한 곳으로 정해져 있지 않다**: `service/connections.py:142` `naver_searchad`(검색광고 API)는 '키워드 도구의 월간 검색 수 같은 지표를 조회'(준비 중·한도 미확인)이고, 같은 파일 `:138` `naver_openapi`(검색·데이터랩)는 '검색 수요·블로그 검색 결과 수 같은 지표를 조회해 후보의 지표 칸을 채우는 데' 쓴다고 적혀 있다. 둘 다 호출 코드가 없다(`docs/ARCHITECTURE.md:74-75`). D-23·D-24·`PLATFORM_POLICY.md` 는 이 칸의 뜻을 말하지 않는다 |
| ④ | 점수에는 어떻게 쓰이나 | **절대 횟수의 로그 눈금** — 10만 회에서 100점(`content/suggest_score.py:48`·`:111-112`), 키워드 기회도의 50% 몫(`:47`·`:119-120`), 기회도는 우선도의 15%(`:22`). 제안(`content/suggest.py:417`)과 보관함 후보 평가(`:668`) 모두 쓴다. 상대지수 87 을 넣으면 87회로 읽어 38.89점이 된다(새 시험이 못박음) |
| ⑤ | 화면에는 어떻게 보이나 | `ui/adapters.py:60` → `Topic.demand`(`ui/core/services.py:31`) → 행 `월 검색량`(`ui/core/text.py:28`)·서랍 `월간 검색량`(`:39`)에 '회'를 붙여(`:74-75`) 보인다. 툴팁은 '한 달 동안 이 키워드가 검색된 횟수를 어림잡은 값'(`:29`). 명령줄 출력도 `{:,}회`(`service/format.py:236`) |

**⑥ 결론 — Legacy 로 유지하고 새 `search_demand_count` 로 자동 이전하지 않는다. 이것은 운영자 말이 아니라 이 조사의 결론(코드·문서 근거)이고, 운영자 지시(조건 1: 의미가 불명확하면 Migration 하지 말고 Legacy 필드로 유지한다)를 이 값에 적용한 것이다.** 요청서에 적힌 결론 후보('설계상 네이버 검색광고 키워드 도구의 월간 검색 수(PC+모바일)를 사람이 적거나 CSV 로 넣는 값')는 코디네이터의 가설이었고 운영자가 한 말이 아니다. 근거: 코드·문서가 말하는 **뜻**은 '월간 검색 수(회)'로 일관되지만(사실), 보관함에 든 숫자가 **어느 공급자의 어느 기간 값인지** 적는 칸이 없고 수집 코드도 없어 알 수 없다(사실) — 자동 이전하면 알 수 없는 값에 출처를 붙여 주는 셈이라 안 된다. **가설과 달랐던 사실 두 가지**:
- **공급자가 검색광고 한 곳이 아니다** — `connections.py:138` 은 오픈 API(검색·데이터랩)도 같은 지표 칸을 채우는 용도로 적고 있다. 데이터랩 값이 상대지수라면(**추정** — 코드·문서에 그 설명은 없다) 바로 '상대값을 횟수 칸에 넣는' 혼동이 이미 생길 수 있다.
- **'PC+모바일 합계'라는 말은 코드·문서 어디에도 없다**(`PC+모바일`·`모바일 합`·`합계` 로 찾아 0건) — 설명은 '월간 검색 수요(회)' 뿐이고 PC·모바일을 합친 값인지는 적혀 있지 않다. 서랍의 'PC·모바일 검색 비중'(`text.py:39`)은 `mobile_share` 의 라벨일 뿐이다.
- 보태서: 상대지수·`relative` 같은 말도 코드·문서에 없다(0건) — 기존 칸에 상대값이 들어올 길을 막는 장치도, 구분하는 장치도 없다는 현재 모습이 `KNOWN_DEFECT` 시험으로 못박혀 있다. 사용자가 출처를 아는 값만 나중에 사람이 명시적으로 새 칸으로 옮기는 길은 **후속 결정**(계획 문서 열린 항목 5).

## 5. 계획 문서 요약 5줄 (`docs/TOPIC_ENGINE_PLAN.md`, 396줄·표 28개)
1. 맨 위에 '이 문서는 계획이고 P0 는 `src/` 를 한 줄도 바꾸지 않았다'를 쓰고 `topics/` 패키지·`topic_engine.db`·명령줄 `topics`·`주제 후보` 화면은 모두 '아직 없음(P1~)'으로 표시했다. 원칙 8개·현재 구조(파일 이름 중심)·코드와 전략이 어긋나는 곳 8개(`KNOWN_DEFECT` 3종 포함)·제안 구조(조각 14개·의존 방향·`test_service_safety` 맞추기·`TrendProvider` 없음/가짜/실제).
2. **저장**: 별도 SQLite `topic_engine.db` + 사용자 데이터 JSON 셋(`channel_profiles.json`·`seeds.json`·`calendar.json`), 백업·복원에 네 파일 포함·API 키 제외, 기존 `chanceblog.db`(판 2) 불변이라 **마이그레이션 없음** — '판 3' 표현은 전부 지움. 실제 Seed·프로필 수정본·캘린더 수정본은 사용자 데이터에만.
3. **Trend 분리·상태 두 축·연결**: `search_demand_count`(+`search_demand_source`)·`trend_ratio`·`trend_status`(4값)·`trend_period`·`trend_compared_group`·`trend_queried_on`·`data_status`(4값) / `work_status`(저장 5값 + 계산하는 표시 4값)와 `recommendation_band`(UNRATED 포함, HOLD 가 두 축에 있는 구분 명시) / `CandidateLink`·`Provenance` / 채널 프로필 `generation_enabled`(네이버 둘만 True)·`history_enabled`(5채널).
4. 값은 전략 문서와 대조해 옮겼다(6항목 가중치 5열×6행·지속형:실시간 비율·구간 80/65/50·중복 40/60/75·상위 5·묶음 2·채널 간 2 — 내가 전략 §6·§7·§13·§14·§17 과 숫자 대조해 일치 확인, 설명은 새로 씀).
5. 단계 P0~P6(등급·동작 변화)·단계 보고 6항목 표·P0b 회귀 예 다섯 표·시험 계획(3모듈 범위·`KNOWN_DEFECT` 규칙·변이 점검)·결정 A~H '운영자 승인(2026-11-04 채팅)' 표와 조건 7개 표·열린 항목 6개(`draft_plan_id` 정의 등)·7절 `search_demand` 조사·알려 둔 한계.

## 6. DECISIONS 처리 — 번호 연속 시험 확인 결과
- **확인함**: `tests/test_repo_layout.py` 92~99행 `test_every_decision_number_used_in_docs_is_defined_in_the_decision_log` 는 ① 정의된 `D-nn` 이 19개 이상인지 ② `.md` 파일이 부르는 모든 `D-nn` 이 표에 정의돼 있는지만 본다. **번호 연속(D-35 가 비면 실패)을 요구하지 않는다.** 다른 시험(`test_ui_core` 는 D-32 행, `test_service_candidates_cli` 는 D-23·D-24 행)도 연속을 보지 않는다.
- 그래서 **D-36~D-39 네 행을 만들었다**(표 끝, 날짜 2026-11-04, 상태 '확정(운영자 승인 2026-11-04 채팅 — A~H 기본값 + 조건 7개)'): D-36 주제 엔진은 새 모듈로 나란히(상태 두 축·점수 나란히·후보 연결과 출처 스냅샷·활성 채널 네이버만) / D-37 Trend 지표는 Legacy 와 분리한 전용 칸·`최근 관심도(상대값)` 는 새 칸의 이름 / D-38 첫 버전 수동 실행(D-09 와의 관계) / D-39 저장 위치(별도 `topic_engine.db` + JSON 3개·백업 4개·키 제외·마이그레이션 없음)·실제 Seed 는 공개 저장소에 올리지 않음.
- **함정 하나**: 어느 `.md` 에도 `D-35` 라는 글자를 쓰면 안 된다(정의되지 않은 번호를 부르면 시험이 실패한다). 계획 문서는 '35번 결정 번호'로 돌려 썼다. N1 가지가 병합돼 D-35 가 생기면 그때는 써도 된다.
- 병합 충돌: N1(`r134`)도 같은 표 끝·CHANGELOG 끝에 한 행/한 줄을 더해 **둘 다 끝에서 충돌**한다(`git merge-tree` 로 확인). 둘 다 남기고 D-35 를 D-36 앞에 두면 된다.

## 7. 내가 결정할 것 (코디네이터)
1. **Qt 소스 훑기 시험 1개 유지 여부**: `test_the_qt_shell_source_picks_home_or_the_placeholder_and_shows_the_drawer_on_home_only` 는 PySide6 를 불러오지 않고 `ui/qt/shell.py`·`screens.py` 의 소스 글만 읽는다(순수 뷰모델에는 '어느 화면을 그릴지·`전체 보기` 가 어디로 가는지'가 없어서). 요청서의 'Qt 시험은 더하지 않는다'와 충돌할 수 있고 코드 모양(`state.page == "home"` 두 곳)에 묶여 P4 에서 반드시 고쳐야 한다 — 빼려면 그 메서드 하나만 지우면 된다(나머지 G5 시험은 순수 뷰모델).
2. **`KNOWN_DEFECT` 표지의 범위**: 요청서·운영자 답에 있는 것(계절 부분 일치·`search_demand=87`·위험 씨앗)에 더해 **'제외한 후보가 표에서 `new` 로 바뀜'(10번)은 내 판단**으로 표시했다(홈에서 안 보이는 건 `load_home` 의 거르기 덕이라서). 빼려면 이름·주석만 고치면 된다.
3. **사운드카드·교통카드·메모리카드**: 운영자 예시 밖이라 옳고 그름을 정하지 않고 현재 값만 못박았다 — P0b 구현자가 정한다(계획 문서 열린 항목 4).
4. **병합 순서**: N1 과 이 가지 중 누가 먼저 병합돼도 `DECISIONS.md`·`CHANGELOG.md` 끝 충돌 해결이 필요하다(위 6절). 이 가지를 먼저 병합하면 D-35 가 잠시 비어 있다(시험은 통과).
5. **운영자에게 알릴 조사 결과**: 4절 ⑥ 의 사실 두 가지(공급자가 오픈 API(데이터랩)도 있음·'PC+모바일 합'은 코드·문서에 없음)는 요청서의 결론 후보(코디네이터 가설)와 달랐다 — 운영자가 한 말이 아니므로 '운영자 결론'이라고 쓰지 않았다. 운영자 보고에 넣을지.
6. 계획 문서가 396줄(한도 400)이라 이후 단계에서 줄을 더하려면 먼저 줄여야 한다. `README.md` 에서 새 문서를 링크하지 않았다(시험이 요구하지 않음) — 링크할지.
7. **기존 `ruff` 지적 79건**(`B023` 30·`UP012` 16·`F401` 8 … — 다른 시험 파일, 이 일에서 안 건드림). 새 파일 3개는 0건. 지금 CI 는 `ruff` 를 안 돌리므로 영향이 없다 — 정리할지.

## 8. 조사하며 알게 된 것 (요청 밖, 사실만)
- `Topic.date` 는 조회일이 없으면 `created_at` 의 **UTC 날짜 앞 10자**다(한국 시간 11월 3일 아침에 만든 후보가 11월 2일로 보임) — 서랍의 '데이터 조회일'이 사실은 만든 날이 된다. `test_icons_cycle_by_position_keywords_are_cut_and_the_date_falls_back_to_the_creation_day` 가 현재 모습을 못박았다(P4 에서 볼 일).
- **제안 엔진은 이미 5채널 키를 모두 받는다**(`suggest(blog=…)`) — 네이버 둘만 쓰게 막는 곳은 서비스 층(`profile_for`·`OTHER_BLOG_GUIDANCE`)뿐이다(`test_the_engine_itself_already_accepts_all_five_channel_keys_and_only_the_service_layer_blocks_them`).
- `season_fit` 은 부분 문자열을 **양쪽**으로 본다 — 이어지는 낱말이 글의 낱말 안에 있어도('세금' ⊂ '부가세금액') 글의 낱말이 이어지는 낱말 안에 있어도('의료' ⊂ '의료비', '직장' ⊂ '직장인') 이어진다. P0b 가 두 방향을 다 바꿔야 한다.
- 후보 한 건이 다섯 채널을 모두 가질 수 있다(`Candidate.blogs` 1~5개) — 전략은 후보 1건 = 채널 1개다.
- 홈은 네이버가 아닌 채널의 후보를 '전체' 칩에만 보여 주고 블로그 배지·후보 수에서는 뺀다 — 새 시험이 못박았다(`test_candidates_for_channels_other_than_naver_show_under_all_only_and_in_no_blog_count`).

## 9. 못 한 것·한계
- 전체 시험 실행(지시)·CI 네 칸(push 안 함)·Ubuntu 실행·Qt 시험(PySide6 없음, 추가 금지)은 하지 않았다. 독립 검증은 코디네이터 몫이라 하지 않았다.
- 전략 문서 대조는 값 표(가중치·비율·구간·중복 구간·상위 수·묶음 상한·채널 간 최대)만 했고 문장은 옮기지 않았다. 전략 문서 원문 문장·실제 Seed 목록은 저장소의 새·바뀐 파일 어디에도 없다 — 전략 문서의 모든 줄을 18글자 단위로 훑어 내 새 파일 4개와 DECISIONS·CHANGELOG 추가분에 같은 글이 있는지 본 결과 **0건**(심어 둔 문장은 잡히는지 확인한 대조 시험 포함).
- 블로그 쪽 `posts.json`·`blogger*_history.json` 형식은 이 PC 에 블로그 사본이 없어 확인하지 못했다(계획 문서 12절에 적음).
- 변이 점검은 새 시험 3개 모듈만 돌렸다(기존 시험이 같은 변이를 잡는지는 일부만 앎 — 예: 라벨 경계는 `test_priority_labels` 도 잡고, 행 라벨 재라벨(M43)은 기존 시험이 놓치는 것을 확인했다).
- `service/suggestions.profile_for` 가드 변이는 동등 변이라 시도하지 않았다(2절 참고).

## 10. 점검
- `git diff --check`(새 파일은 `git add -N` 뒤) 0건 · 새·바뀐 파일 6개에 BOM·보이지 않는 글자(Cf/Cc·NBSP·폭 없는 글자)·줄 끝 공백·탭 **0건**, 새 파일은 LF·끝에 줄바꿈 하나 · `ruff check --select F,E9,B,UP --target-version py310` 새 시험 3개 **0건**(`tests` 전체는 기존 79건 — 7절 7번).
- 비밀·키 모양·개인 이메일·절대 경로·전략 문서 원문 문장·실제 Seed 목록을 저장소에 쓰지 않았다(`test_repo_layout` 의 키 모양·개인 이메일·GitHub Models 훑기 통과).
- 진행 기록 `W\p25p0_progress.md`(시작 시각 맨 위, 갱신 19:53·20:00 …). 변이 점검 도구 `W\p25p0_mutate.py`·결과 `W\p25p0_mut_results.json`.
