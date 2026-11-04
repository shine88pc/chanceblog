# 독립 검증 최종 보고서 — P0 '기존 동작 보호 특성 시험 + 계획 문서·결정 후보' (T0~T1)

**판정: 조건부 병합 가능** — 높음 0 · 중간 2 · 낮음 12. 대상은 가지 `ai/claude/p0-topic-protect-1` 머리 **`4c746d6`**(WIP 2, 부모 `1f2297b` = WIP 1, 기준 `3b1294b`). 병합 전에 고칠 것은 '계획 7절 ③·⑥ 의 `connections.py` 인용을 N1 기준으로 맞추는 것' 하나다(N1 이 먼저 병합되는 순서일 때).

근거 3줄:
1. **범위·위생이 깨끗하고 새 시험 73개가 어디서나 통과한다** — 변경은 시험·문서 6파일(+1,333/−0)뿐이고 `src/`·`scripts/`·`vendor/`·`.github/`·`VERSION`·의존성 0줄, 기존 시험·기존 문서 줄 삭제 0, 숨은 글자·BOM 0. 새 시험은 기준선 `3b1294b` 소스·N1 머리(`b2096ce`)·3.12·진짜 3.10.11·PySide6 설치 3.12 모두 `OK`, 병합 충돌은 `CHANGELOG.md`·`docs/DECISIONS.md` 두 곳뿐.
2. **시험이 '현재 동작'을 잘 못박는다** — 내가 새로 설계한 변이 98곳(구현자 1차 42곳과 겹치지 않음 — 보완 10곳 중 라벨 7곳은 내 V31·N01~N06 과 비슷하고 결과도 같음) 중 일부러 깨뜨린 90곳을 새 시험이 80곳 잡고, 놓친 10곳 중 7곳은 기존 시험이 대신 잡으며 **모두 놓치는 것은 3곳**뿐이다. '결함 고치기' 5곳(그래픽카드·카드뮴만 제외 F01, 자료 쪽 수정 F02, 제외 후보 상태 F03, 부분 일치→정확 일치 F04, 새 Trend 라벨 더하기 N07)은 KNOWN_DEFECT·'아직 없음' 시험이 의도대로 깨지고, 올바른 고침(F01·F02)에서는 신용카드·체크카드·카드값 일치 시험이 그대로 통과하며 과격한 정확 일치(F04)에서는 그 시험도 깨져 '틀린 고침' 임을 알려 준다. 기존 시험 4모듈(`test_suggest`·`test_suggest_score`·`test_suggest_data`·`test_service_suggestions`)은 F01·F02·F04 어느 것에도 안 깨진다 — 의도한 카드 낱말 일치를 지키는 것은 새 시험뿐이다.
3. **1차 중간 보고의 지적 3건(중간 2·낮음 1)이 델타 `4c746d6` 로 해소됐다** — ① '운영자의 결론·근거' 귀속 오류 → 출처 표기 분리(`운영자` 낱말 전수 확인, 오귀속 0) ② 화면 라벨 `월 검색량` 공백 → `LegacyDemandLabelTest` 가 이제 잡음(V31·N01~N06) ③ P0b 영향 설명 → 보관함 후보 우선도(89.1 → 81.8)가 코드와 값까지 맞음. 남은 중간 지적은 아래 2건.

작업 시각: 시작 20:10:34 → 중간 저장 20:26·20:39·20:54(`W\ver_p0_report_partial.md`) → 델타 확인 20:46~21:05 → 최종 저장 시각은 맨 끝 줄(마감 21:25:34).

## 1. 지적

### 높음
없음. (기준선에서 실패하는 새 시험·`src/` 변경·기존 시험 약화·숨은 글자·비밀·원문 문장 단위 복사(15자 조각 1개는 낮음 10)·숫자 어긋남 모두 없음.)

### 중간 (남은 것 2건)
**M1. 계획 7절 ③·⑥ 의 `connections.py` 인용은 `3b1294b` 기준이라 N1 이 먼저 병합되면 틀려진다.**
- 재현: `git show b2096ce:src/chanceblog_desktop/service/connections.py | grep -n 'Purpose("naver'` — N1 은 `naver_openapi` 를 '옛 항목 — … 호출하지 않습니다' 로 바꾸고, 새 용도 `naver_apihub`('네이버 데이터랩 검색어 트렌드로 키워드의 **관심도 변화**를 조회해 후보의 지표를 보정')를 더한다. 계획 7절 ③·⑥ 은 '`connections.py:138` 의 오픈 API(검색·데이터랩)도 후보의 지표 칸을 채우는 용도 → 공급자가 한 곳이 아니다' 라고 쓴다. 병합 순서는 N1 → P0(코디네이터 ④)이고 델타(`4c746d6`)는 ③(271행)을 그대로 두었고 ⑥(275행)은 귀속만 고쳐 '공급자가 한 곳이 아니다' 문장은 남아 있다. `service/format.py:236` 등 줄 번호도 N1(97줄 변경) 뒤에는 밀린다.
- 고칠 방향: N1 위에 병합 가지를 쌓을 때 7절 ③·⑥ 의 `connections` 문장에 '(`3b1294b` 기준)'을 적고 'N1 뒤: 오픈 API 는 옛 항목이고, 데이터랩 검색어 트렌드는 `naver_apihub` 가 "관심도 변화" 를 조회하는 용도로 적혀 있어(호출 코드는 아직 없음) "공급자가 한 곳이 아니다·상대값을 횟수 칸에 넣는 혼동" 이라는 근거는 N1 뒤에는 약해진다' 한 줄을 더한다. 결론(Legacy 유지·자동 이전 없음)은 그대로다.

**M2. Qt 소스 글자 훑기 시험 1개(`TopicsPlaceholderTest.test_the_qt_shell_source_picks_home_or_the_placeholder_and_shows_the_drawer_on_home_only`)는 동시에 헐렁하고 깨지기 쉽다 — 유지에는 동의.**
- 헐렁함(V85): 서랍을 모든 화면에 보이게 바꾸면서 옛 줄을 주석으로 남기면(`view = state.drawer_view()  # was: view = state.drawer_view() if state.page == "home" else None`) 통과한다 — 규칙이 아니라 글자 모양을 못박는다.
- 깨지기 쉬움(V86·V87): 동작이 같은 정리 둘 — 조건을 변수 하나로 뺌(`is_home = state.page == "home"` 뒤 `… if is_home else …`), 한 줄을 괄호로 줄 바꿈 — 에 깨진다.
- 판단: PySide6 없이 CI 에서 도는 유일한 '서랍은 홈에서만' 안전망이고 P4 가 의식적으로 고칠 자리라 **유지**(코디네이터 판단 ①에 동의). 병합 전 필수는 아니다. 고칠 방향(선택): 정규식 대신 `ast` 로 `shell.py` 를 읽어 `state.page == "home"` 을 조건으로 가진 `IfExp` 의 몸통이 `home_screen`·`drawer_view` 호출인지 보면 공백·줄 바꿈·주석에 흔들리지 않는다.

### 낮음
1. **시험 공백 — 새·기존 시험 모두 놓치는 변이 3곳**: `to_topic` 추세 표의 보합→flat(V11: `보합` 을 `up` 으로 바꿔도 통과), `apply_home` 의 칩 되돌림(V30), `GENERIC_WORD_STEMS` 의 '준비'(V34). 고칠 방향: 각각 한 줄 단언(`보합→flat·하락→down`, '새로 불러오면 칩이 전체로', '준비' 만 든 글은 시기와 안 이어짐).
2. **새 시험이 놓치고 기존 시험이 잡는 변이 7곳**: 제안 쪽 `HIGH_FROM`·`MID_FROM`(V37·V38)·태그 씨앗 강도(V42)·경쟁 점수 반전(V45)·관심도 보합 점수(V46)·위험 판정의 금지 문구 검사(V50)·프로필 없는 네이버 B 안내(V81). D-37 ④ 가 말하는 `opportunity()` 눈금(10만 회 = 100점)은 새 시험이 못박고, 기회도의 경쟁·관심도 보합 부분과 위험 판정의 일부는 기존 시험 몫이다 — 새 시험만으로 '다 못박았다' 고 읽히지 않게 계획 9.1 에 '기존 시험과 합쳐' 한 마디를 더해도 좋다.
3. **결정 B(채널 이름 대응)·H(실시간 이슈)는 `DECISIONS.md` 에 행이 없다**(D-36=D·D-37=E·D-38=G·D-39=A·C·F). 계획 5.2·10절에만 있다. 코드가 기대는 이름 약속이라 한 줄씩 결정 행이 있는 편이 안전.
4. **결정 A 행 '제안 상태 시작 목록' 의 위치가 없다**: 계획 10절 A 행은 '시험용 예시와 제안 상태의 네이버 A·B 시작 목록만 두고' 라고 쓰는데 D-39 ④ 는 '저장소에는 시험용 예시만'. 전략 문서에서 뽑은 목록이면 공개 저장소에 두면 안 되므로 '사용자 데이터에만' 으로 못박기.
5. **계획 8.1 의 P4 행 '기존 시험 중 서랍 항목 목록과 화면 문구 3곳이 의식적으로 바뀐다' — 3곳이 무엇인지 안 적혀 있다.** 재라벨이 아님은 새 시험으로 못박혔으므로 3곳(예: 자리표시 화면 글·빠른 작업 안내·서랍 항목 수)을 적거나 '라벨 처리는 열린 항목 3' 으로 돌리기.
6. **새 `LegacyDemandLabelTest.test_the_screen_text_has_no_relative_interest_label_yet…` 는 `text.T` 전체를 훑어 `상대값`·`최근 관심도` 가 하나도 없어야 한다** — P4 가 새 문구를 더하면 깨지게 한 것은 의도지만, 기존 추세 서랍 라벨(`최근 트렌드`)이 나중에 `최근 관심도 변화`(후보 라벨 이름)로 바뀌어도 오경보가 난다. 주석에 '새 Trend 문구는 키 이름으로 구분'을 적어 두면 좋다.
7. **KNOWN_DEFECT 중 '상대지수 87·CSV 검색량' 3개(candidates 모듈)는 뒤집는 단계가 계획에 없다** — Legacy 는 그대로 두기로 했으므로(D-37 ③) 이 시험은 영구히 '결함' 이름으로 남는다. 주석에 '새 Trend 칸이 대신하고 이 시험은 그대로' 를 적거나 이름을 `LEGACY_` 로.
8. **계획 9.2 '실제 시계 없이'**: `LoadHomeScenarioTest`·`OtherChannelsInTheSuggestionServiceTest` 는 `make_ctx` 의 실제 `Clock()` 을 쓴다(단언은 날짜와 무관해 안전; 해시 시드 0·1·4242 로 3번 돌려 같은 결과).
9. **P1 지시와 계획이 어긋난다**: `r131_operator_answer.md` 3절의 P1 지시('작업 축 값은 `content.candidates` 상수 재사용')는 계획 3.2·D-36 ①('`topics` 는 … `service`·`ui`(계획 3.2 는 `content` 도) 를 가져오지 않는다')와 부딪힌다 — P1 전에 정리.
10. **계획 머리말 '설명은 새로 썼다' 는 거의 맞다**: 전략 문서와 12자 이상 같은 곳 39곳은 식별자·표 틀이 대부분이고 문장 조각은 `숫자만으로 자동 삭제하지 않는다`(15자)와 표 칸 둘뿐 — 규칙·값 수준이라 선을 넘지 않음. 시험 예시 프로필 A·B 의 낱말(소형가전·숙박·여행·PC 주변기기 / AI·PC 부품·업무 자동화)이 전략 문서의 네이버 A·B 채널 분야와 겹치는 것도 일반 낱말이라 문제는 아니나 중립 예시(가전·여행 …)가 더 안전.
11. **시험이 비공개 이름에 기댄다**: `sg._RISKY.pattern`·`ServiceHomeProvider()._names` — 리팩터링에 약함(깨지면 알려 주는 것이 목적이라 허용 범위).
12. **계획 문서에 `README` 링크가 없다**(시험은 요구 안 함 — 구현자 7절 6번 질문): 문서가 늘어나는 단계에서 목록을 정리할 때 링크.

### 델타로 해소된 지적 (R1·R2 는 중간, R3 은 낮음 — 코디네이터 요청 ①②③)
- R1(귀속 오류): 계획 4.2 에 '누가 정했나' 열이 생겨 운영자가 정한 칸 이름은 다섯(`search_demand_count`·`trend_ratio`·`trend_status`·`trend_period`·`trend_compared_group`)뿐, `search_demand_source`·`trend_queried_on`·`data_status`·영문 상태 값·0~100 범위·`work_status`·`recommendation_band`·`UNRATED`·`COPIED`·`generation_enabled`·`history_enabled`·`CandidateLink`·`Provenance` 는 '이 계획의 해석/이름'. 7절 ⑥ 은 '이것은 운영자 말이 아니라 이 조사의 결론이고 운영자 지시(조건 1)를 적용한 것'. `운영자` 낱말 계획 24·결정 12·CHANGELOG 2곳을 하나씩 운영자 원문(R-131 답 1절)과 대조해 오귀속 0.
- R2(라벨 공백): `LegacyDemandLabelTest` 4개 + `LegacyCountOnTheCommandLineTest` 1개. V31(행 라벨→`최근 관심도(상대값)`)이 이제 4건에서 잡힘, 서랍 라벨(N01)·툴팁(N02)·명령줄 단위(N03)·후보 라벨(N04)·행 라벨 `블로그 문서 수`(N05)·숫자 쉼표(N06) 변이도 모두 잡힘.
- R3(P0b 영향): 계획 8.1·8.2·8.3 과 `StoredCandidatePriorityTest` 3개가 코드와 맞음(`candidates list --priority`·`show` → `service/suggestions.assess_rows` → `sg.assess` → `season_fit`).

## 2. 병합 전에 반드시 고칠 것
1. **M1** — 계획 7절 ③·⑥ 의 `connections` 인용에 기준 커밋 '(`3b1294b` 기준)'과 N1 뒤의 모습 한 줄을 더한다(N1 → P0 순서의 병합 가지에서). 이것만 필수다.
2. (권장, 필수 아님) 낮음 1·2 의 한 줄 시험·문장 좁히기, 낮음 3·4 의 결정 행·위치 문장, M2 의 `ast` 방식.


## 3. 변이 표 — 내가 새로 설계한 98곳 (구현자 변이와 따로)

방법: 임시 사본(`W\ver_p0_x\mutN` — 작업 폴더 `cd_wt_p0` 는 건드리지 않음)에서 소스를 한 곳씩 바꾸고 새 3모듈을 돌린 뒤 되돌림(한 번에 하나, 3.12). **종류**: 번호 V·N = 동작을 일부러 깨뜨림(새 시험이 잡아야 함), F = 현실적인 '결함 고치기'(KNOWN_DEFECT 시험이 의도대로 깨져야 함), V85 = 동작은 바뀌었는데 글자 모양은 그대로(속는지), V86·V87 = 동작은 그대로인 정리(깨지는지). '1f2297b' 열은 1차 커밋에서, '4c746d6' 열은 보완 커밋에서 돌린 결과다(보완 커밋은 시험만 더하므로 1차에서 잡힌 것은 계속 잡힌다 — 그래도 전부 다시 돌렸다). '기존 시험' 열은 새 시험이 놓친 변이를 기존 시험 모듈(`test_ui_core`·`test_ui_adapters`·`test_suggest`·`test_suggest_score`·`test_suggest_data`·`test_service_suggestions`)이 잡는지(이 PC, PySide6 없는 3.12 — Qt 시험은 안 돌림)다.

**집계(4c746d6)**: 동작을 깨뜨린 90곳 중 새 시험이 잡은 것 80곳, 놓친 것 10곳(V11, V30, V34, V37, V38, V42, V45, V46, V50, V81) — 그 중 기존 시험이 대신 잡는 것 7곳(V37, V38, V42, V45, V46, V50, V81), **기존 시험도 놓치는 것 3곳**(V11, V30, V34). 1f2297b 에서는 놓친 것이 13곳이었고 보완으로 V31·V32·V36 이 잡히게 됐다.

| 번호 | 영역 | 변이(소스를 이렇게 바꿈) | 1f2297b | 4c746d6 | 잡은 새 시험 수(4c746d6)·먼저 잡은 시험 | 기존 시험(새 시험이 놓친 것만) |

|---|---|---|---|---|---|---|

| V01 | 작성 우선도 경계 | 높음 경계를 70 이상 → 70 초과로(정확히 70 이 보통이 됨) | 잡힘 | 잡힘 | 1 · the_priority_label_boundaries_reach_the_topic_through_to_t | - |

| V02 | 작성 우선도 경계 | 보통 경계를 40 이상 → 40 초과로 | 잡힘 | 잡힘 | 1 · the_priority_label_boundaries_reach_the_topic_through_to_t | - |

| V03 | 작성 우선도 라벨 | 우선도가 없는 후보를 '낮음' 으로 지어냄 | 잡힘 | 잡힘 | 2 · the_label_is_the_candidates_own_priority_and_never_a_compu | - |

| V04 | to_topic 상태 대응 | 보류(HOLD) 를 새 후보(new) 로 | 잡힘 | 잡힘 | 2 · held_candidates_are_saved_ideas_and_do_not_count_toward_a_ | - |

| V05 | to_topic 상태 대응 | 표에 없는 상태(제외) 의 기본값을 new → hold 로 | 잡힘 | 잡힘 | 2 · KNOWN_DEFECT_a_rejected_candidate_is_filtered_by_load_home | - |

| V06 | 블로그 키 표 | BLOG_KEYS 의 A·B 글자를 맞바꿈 | 잡힘 | 잡힘 | 18 · only_naver_profiles_can_rename_a_blog_and_other_keys_in_th | - |

| V07 | to_topic 설명 | 설명: 추천 이유 우선 → 핵심 키워드 우선 | 잡힘 | 잡힘 | 1 · icons_cycle_by_position_keywords_are_cut_and_the_date_fall | - |

| V08 | to_topic 키워드 자르기 | 보조 키워드를 둘 → 셋까지 | 잡힘 | 잡힘 | 1 · icons_cycle_by_position_keywords_are_cut_and_the_date_fall | - |

| V09 | to_topic 날짜 | 날짜: 조회일 우선 → 만든 날 우선 | 잡힘 | 잡힘 | 1 · icons_cycle_by_position_keywords_are_cut_and_the_date_fall | - |

| V10 | to_topic 아이콘 | 아이콘을 돌려 쓰지 않고 항상 첫째 | 잡힘 | 잡힘 | 1 · icons_cycle_by_position_keywords_are_cut_and_the_date_fall | - |

| V11 | to_topic 추세 | 보합을 '상승(up)' 으로 | **놓침** | **놓침** | 0 · - | **기존 시험도 놓침** |

| V12 | 블로그 이름 읽기 | 표시 이름이 글인지 확인을 지움(숫자면 예외) | 잡힘 | 잡힘 | 1 · only_naver_profiles_can_rename_a_blog_and_other_keys_in_th | - |

| V13 | 블로그 이름 읽기 | 네이버가 아닌 프로필 키도 블로그 A 이름이 되게 | 잡힘 | 잡힘 | 1 · only_naver_profiles_can_rename_a_blog_and_other_keys_in_th | - |

| V14 | 보류 제외 | 보류한 후보도 홈 대상에 넣음 | 잡힘 | 잡힘 | 2 · chip_counts_follow_the_blog_trend_and_status_of_each_live_ | - |

| V15 | 보류 제외·선택 제외 | 홈에는 새 후보만(선택한 것도 빠짐) | 잡힘 | 잡힘 | 1 · chip_counts_follow_the_blog_trend_and_status_of_each_live_ | - |

| V16 | 정렬 키 | 우선도 순위에서 보통과 낮음을 맞바꿈 | 잡힘 | 잡힘 | 1 · equal_priority_and_date_keep_the_input_order_and_an_unknow | - |

| V17 | 정렬 키 | 정렬 순서를 맞바꿔 날짜가 우선도보다 앞서게 | 잡힘 | 잡힘 | 1 · equal_priority_and_date_keep_the_input_order_and_an_unknow | - |

| V18 | 홈 행 수 | 화면 행 자르기를 HOME_ROWS 대신 4 로(상수는 그대로 5) | 잡힘 | 잡힘 | 12 · equal_priority_and_date_keep_the_input_order_and_an_unknow | - |

| V19 | 칩 | '신규' 칩에 선택한 후보도 넣음 | 잡힘 | 잡힘 | 1 · chip_counts_follow_the_blog_trend_and_status_of_each_live_ | - |

| V20 | 칩 | 블로그 A·B 칩의 거르기 조건을 맞바꿈 | 잡힘 | 잡힘 | 11 · a_chip_with_no_rows_leaves_nothing_selected_and_the_all_ch | - |

| V21 | 홈 카드 | 추천 주제 카드가 보류까지 셈 | 잡힘 | 잡힘 | 2 · chip_counts_follow_the_blog_trend_and_status_of_each_live_ | - |

| V22 | 홈 카드 이동 | 작성 완료 카드가 주제 후보로 이동하게 | 잡힘 | 잡힘 | 1 · the_home_cards_for_recommended_topics_and_saved_ideas_go_t | - |

| V23 | 메뉴 이동 | 지금 화면으로도 이동(True) | 잡힘 | 잡힘 | 1 · every_screen_but_home_shows_the_same_placeholder_text_with | - |

| V24 | 빠른 작업 이동 | 저장한 아이디어 빠른 작업이 블로그 화면으로 | 잡힘 | 잡힘 | 1 · the_quick_actions_that_move_go_to_topics_history_and_blogs | - |

| V25 | 메뉴 순서 | 주제 후보와 초안 메뉴 순서를 맞바꿈 | 잡힘 | 잡힘 | 2 · the_home_cards_for_recommended_topics_and_saved_ideas_go_t | - |

| V26 | 메뉴 상한 | 메뉴 상한 6 → 7 | 잡힘 | 잡힘 | 1 · the_menu_keys_and_icons_put_topics_second_and_the_label_sa | - |

| V27 | 칩 | '신규' 칩을 지움(칩 4개) | 잡힘 | 잡힘 | 18 · the_home_chips_are_five_in_this_order_and_only_a_and_b_nam | - |

| V28 | 채널 둘 가정 | 뷰모델이 A·B 밖 키를 거르지 않음(예외) | 잡힘 | 잡힘 | 1 · a_blog_key_outside_a_and_b_gets_no_badge_in_the_view_model | - |

| V29 | 선택 유지 | 처음 선택을 첫 행 → 마지막 후보로 | 잡힘 | 잡힘 | 3 · home_data_and_the_home_view_for_zero_one_five_six_and_fift | - |

| V30 | 칩 되돌림 | 새로 불러와도 칩 거르기를 '전체' 로 되돌리지 않음 | **놓침** | **놓침** | 0 · - | **기존 시험도 놓침** |

| V31 | 화면 문구 | 행의 `월 검색량` 라벨을 상대값 이름으로 다시 붙임(운영자가 금지한 재라벨) | **놓침** | 잡힘 | 4 · none_of_the_legacy_count_labels_borrows_the_relative_inter | - |

| V32 | 화면 문구 | 검색량 단위 '회' 를 '점' 으로 | **놓침** | 잡힘 | 2 · the_legacy_absolute_count_is_called_monthly_search_volume_ | - |

| V33 | season_fit | 부분 일치의 '낱말 ⊂ 글 낱말' 방향을 지움(반대 방향만 남김) | 잡힘 | 잡힘 | 30 · KNOWN_DEFECT_the_same_title_wins_when_the_graphics_card_se | - |

| V34 | 계절 표 항목 | 흔한 말 목록에서 '준비' 를 뺌 | **놓침** | **놓침** | 0 · - | **기존 시험도 놓침** |

| V35 | season_fit | 시기와 무관한 상시 주제 점수 50 → 55 | 잡힘 | 잡힘 | 3 · the_first_three_suggestions_and_the_counts_for_the_four_ca | - |

| V36 | season_fit | 이번 달이 아닌 계절 자료 점수 30 → 25 | **놓침** | 잡힘 | 1 · external_months_on_the_candidate_decide_the_season_factor_ | - |

| V37 | 작성 우선도 경계 | 제안 쪽 '높음' 경계 70 → 71 | **놓침** | **놓침** | 0 · - | 기존 시험이 잡음: the_levels_change_exactly_at_the_boundaries 외 1 |

| V38 | 작성 우선도 경계 | 제안 쪽 '보통' 경계 40 → 41 | **놓침** | **놓침** | 0 · - | 기존 시험이 잡음: the_levels_change_exactly_at_the_boundaries 외 1 |

| V39 | 가중치 | 균형 15→20·기회도 15→10(합 100 유지) | 잡힘 | 잡힘 | 12 · the_first_three_suggestions_and_the_counts_for_the_four_ca | - |

| V40 | 적합도 | 글 유형 일치 가산점 10 → 5 | 잡힘 | 잡힘 | 7 · the_first_three_suggestions_and_the_counts_for_the_four_ca | - |

| V41 | 적합도 | 카테고리 씨앗 강도 75 → 70 | 잡힘 | 잡힘 | 1 · KNOWN_DEFECT_the_same_title_wins_when_the_graphics_card_se | - |

| V42 | 적합도 | 태그 씨앗 강도 60 → 55 | **놓침** | **놓침** | 0 · - | 기존 시험이 잡음: the_fit_follows_where_the_seed_came_from_and_the_post_type 외 2 |

| V43 | search_demand 환산 눈금 | 로그 눈금에서 +1 보정을 뺌(1회가 0점) | 잡힘 | 잡힘 | 2 · opportunity_turns_the_demand_into_a_log_scale_where_a_hund | - |

| V44 | search_demand 환산 눈금 | 수요를 로그 눈금이 아니라 그대로 0~100 점수로 읽음(상대지수처럼) | 잡힘 | 잡힘 | 3 · KNOWN_DEFECT_the_same_87_scores_far_below_87_because_it_is | - |

| V45 | 기회도 경쟁 | 관련 블로그 결과 수가 많을수록 점수가 높게(뒤집음) | **놓침** | **놓침** | 0 · - | 기존 시험이 잡음: more_blog_results_lowers_the_priority 외 3 |

| V46 | 기회도 추세 | 보합 점수 50 → 60 | **놓침** | **놓침** | 0 · - | 기존 시험이 잡음: the_published_weights_levels_and_thresholds 외 2 |

| V47 | 점수 반올림 | 우선도 반올림 소수 한 자리 → 두 자리 | 잡힘 | 잡힘 | 12 · the_first_three_suggestions_and_the_counts_for_the_four_ca | - |

| V48 | 적합도 상한 | 적합도 상한 100 → 99 | 잡힘 | 잡힘 | 6 · the_first_three_suggestions_and_the_counts_for_the_four_ca | - |

| V49 | 위험 씨앗 목록 | 위험 낱말 목록에서 '후기' 를 뺌 | 잡힘 | 잡힘 | 1 · the_risky_word_list_has_no_word_for_health_brand_or_sponso | - |

| V50 | 위험 씨앗 판정 | 위험 판정에서 금지 문구·경험 지어내기 검사를 뺌 | **놓침** | **놓침** | 0 · - | 기존 시험이 잡음: asking_for_one_suggestion_never_lets_a_violation_through_e 외 1 |

| V51 | 제안 정렬 키 | 제안 정렬을 점수 오름차순으로 | 잡힘 | 잡힘 | 12 · KNOWN_DEFECT_the_same_title_wins_when_the_graphics_card_se | - |

| V52 | 제안 채널 인자 | 제안이 blog 인자를 무시하고 프로필 키만 씀 | 잡힘 | 잡힘 | 9 · a_suggestion_for_a_non_naver_blog_is_an_empty_list_with_th | - |

| V53 | 계절 표 항목 | 11월 표에서 '쇼핑 행사' 항목을 지움 | 잡힘 | 잡힘 | 1 · the_first_three_suggestions_and_the_counts_for_the_four_ca | - |

| V54 | 계절 표 항목 | 12월 '연말정산' 항목에서 이어지는 낱말 '카드' 를 지움 | 잡힘 | 잡힘 | 6 · KNOWN_DEFECT_the_year_end_title_appears_only_in_the_months | - |

| V55 | search_demand 상한 | 검색 수요 상한을 10억 → 10억 1 | 잡힘 | 잡힘 | 1 · the_search_demand_accepts_only_whole_numbers_from_zero_to_ | - |

| V56 | 숫자 칸 모양 | 숫자 칸이 True 를 1 로 받음 | 잡힘 | 잡힘 | 1 · the_search_demand_accepts_only_whole_numbers_from_zero_to_ | - |

| V57 | 조회일 필수 | 지표가 있어도 조회일을 요구하지 않음 | 잡힘 | 잡힘 | 1 · the_search_demand_accepts_only_whole_numbers_from_zero_to_ | - |

| V58 | edited 가 모르는 칸 | edited 로 상태를 바꿀 수 있게 | 잡힘 | 잡힘 | 1 · the_strategy_style_and_engine_names_are_refused_as_unknown | - |

| V59 | 관심도 낱말 | 관심도 변화에 '데이터 부족' 값을 더함 | 잡힘 | 잡힘 | 5 · a_trend_column_takes_only_the_three_words_so_a_number_in_i | - |

| V60 | LABELS | 후보 칸 라벨을 `월 검색량` 으로 | 잡힘 | 잡힘 | 2 · the_command_line_prints_the_legacy_count_as_monthly_search | - |

| V61 | Candidate 칸 추가 | Candidate 에 새 엔진 이름 칸(trend_ratio)을 더함 | 잡힘 | 잡힘 | 1 · the_candidate_has_none_of_the_new_engine_names_and_no_fiel | - |

| V62 | 블로그 목록 검사 | 후보의 채널 목록이 겹침을 허용 | 잡힘 | 잡힘 | 1 · a_candidate_carries_one_to_five_channels_so_one_candidate_ | - |

| V63 | 블로그 목록 검사 | 후보의 채널 목록이 비어도 허용 | 잡힘 | 잡힘 | 1 · a_candidate_carries_one_to_five_channels_so_one_candidate_ | - |

| V64 | CSV 모르는 열 | 모르는 열을 알림 목록에 올리지 않음 | 잡힘 | 잡힘 | 1 · columns_that_name_a_relative_index_are_not_known_so_they_a | - |

| V65 | CSV 모르는 열 | '트렌드 지수' 열이 추세 칸으로 읽힘 | 잡힘 | 잡힘 | 1 · columns_that_name_a_relative_index_are_not_known_so_they_a | - |

| V66 | CSV 모르는 열 | 'Relative Index' 열이 월간 검색 수요 칸으로 읽힘 | 잡힘 | 잡힘 | 1 · columns_that_name_a_relative_index_are_not_known_so_they_a | - |

| V67 | CSV 숫자 | 숫자 칸이 천 단위 쉼표를 못 읽음 | 잡힘 | 잡힘 | 1 · KNOWN_DEFECT_a_column_named_search_volume_is_taken_as_the_ | - |

| V68 | CSV 추세 안내문 | 추세 열 오류 안내의 구분자 변경 | 잡힘 | 잡힘 | 4 · a_trend_column_takes_only_the_three_words_so_a_number_in_i | - |

| V69 | CSV 열 별칭 | '검색량' 이 관련 블로그 검색 결과 수 칸으로 읽힘 | 잡힘 | 잡힘 | 1 · KNOWN_DEFECT_a_column_named_search_volume_is_taken_as_the_ | - |

| V70 | 설정 엄격성 | 설정 파일이 네이버 밖 채널의 프로필 키를 받음 | 잡힘 | 잡힘 | 3 · the_settings_hold_only_naver_profiles_so_a_profile_for_ano | - |

| V71 | 설정 엄격성 | 설정 파일이 다른 schema 숫자를 받음 | 잡힘 | 잡힘 | 1 · the_settings_hold_only_naver_profiles_so_a_profile_for_ano | - |

| V72 | PLATFORMS 순서 | 네이버 B 가 A 보다 앞 | 잡힘 | 잡힘 | 2 · platforms_run_pages_then_blogger_english_then_blogger_kore | - |

| V73 | PLATFORMS 가족 | Blogger 한글의 가족을 pages 로 | 잡힘 | 잡힘 | 1 · platforms_run_pages_then_blogger_english_then_blogger_kore | - |

| V74 | PLATFORMS 순서 | github_pages 가 blogger_en 뒤로 | 잡힘 | 잡힘 | 1 · platforms_run_pages_then_blogger_english_then_blogger_kore | - |

| V75 | NaverProfile 키 제한 | 네이버 프로필 키 순서를 B, A 로 | 잡힘 | 잡힘 | 3 · a_naver_profile_accepts_only_naver_a_or_b_and_a_naver_blog | - |

| V76 | NaverProfile 키 제한 | 네이버 프로필이 어떤 키든 받음 | 잡힘 | 잡힘 | 3 · a_naver_profile_accepts_only_naver_a_or_b_and_a_naver_blog | - |

| V77 | NaverProfile 주소 제한 | 네이버 프로필이 네이버 밖 주소도 받음 | 잡힘 | 잡힘 | 4 · a_naver_profile_accepts_only_naver_a_or_b_and_a_naver_blog | - |

| V78 | profile_for 비네이버 | profile_for 가 네이버 밖 채널에 네이버 A 프로필을 줌(동등 변이가 아닌 형태) | 잡힘 | 잡힘 | 4 · a_suggestion_for_a_non_naver_blog_is_an_empty_list_with_th | - |

| V79 | 서비스 기본 채널 | 블로그를 안 주고 프로필이 없으면 네이버 B 로 제안 | 잡힘 | 잡힘 | 1 · without_a_blog_the_service_suggests_for_each_saved_naver_p | - |

| V80 | 프로필 있는 블로그 순서 | 프로필 있는 블로그를 B, A 순으로 | 잡힘 | 잡힘 | 2 · only_the_two_naver_blogs_have_profiles_and_the_other_three | - |

| V81 | 다른 블로그 안내 | 프로필 없는 네이버 B 도 '다른 블로그' 안내를 받음 | **놓침** | **놓침** | 0 · - | 기존 시험이 잡음: the_error_for_a_blog_that_cannot_suggest_says_why 외 1 |

| V82 | Qt 소스(홈 선택) | 홈 화면 그릴 쪽을 주제 후보 화면으로 | 잡힘 | 잡힘 | 1 · the_qt_shell_source_picks_home_or_the_placeholder_and_show | - |

| V83 | Qt 소스(서랍) | 서랍을 설정 화면 말고는 모두 보임 | 잡힘 | 잡힘 | 1 · the_qt_shell_source_picks_home_or_the_placeholder_and_show | - |

| V84 | Qt 소스(전체 보기) | '전체 보기' 가 기록 화면으로 | 잡힘 | 잡힘 | 1 · the_qt_shell_source_picks_home_or_the_placeholder_and_show | - |

| V85 | Qt 소스(서랍) | 서랍을 모든 화면에서 보이게 하되 옛 줄을 주석으로 남김(글자 훑기 시험이 속는지) | **통과(놓침)** | **통과(놓침)** | 0 · - | - |

| V86 | Qt 소스(홈 선택) | 동작은 같고 변수 하나만 만든 정리(글자 훑기 시험이 깨지는지) | **깨짐(동작은 그대로)** | **깨짐(동작은 그대로)** | 1 · the_qt_shell_source_picks_home_or_the_placeholder_and_show | - |

| V87 | Qt 소스(서랍) | 동작은 같고 줄만 바꾼 정리(글자 훑기 시험이 깨지는지) | **깨짐(동작은 그대로)** | **깨짐(동작은 그대로)** | 1 · the_qt_shell_source_picks_home_or_the_placeholder_and_show | - |

| F01 | KNOWN_DEFECT 고치기 | 그래픽카드·카드뮴만 이어짐에서 제외(현실적인 P0b 식 수정) — KNOWN_DEFECT 시험이 깨져야 하고 신용카드·체크카드·카드값은 그대로여야 함 | 깨짐(의도) | 깨짐(의도) | 14 · KNOWN_DEFECT_the_same_title_wins_when_the_graphics_card_se | 기존 시험은 안 깨짐 |

| F02 | KNOWN_DEFECT 고치기 | 11월 표의 '카드' 를 구체적 카드 낱말 셋으로 바꿈(자료 쪽 수정) — KNOWN_DEFECT 시험이 깨져야 함 | 깨짐(의도) | 깨짐(의도) | 12 · KNOWN_DEFECT_the_same_title_wins_when_the_graphics_card_se | 기존 시험은 안 깨짐 |

| F03 | KNOWN_DEFECT 고치기 | 제외 후보 상태를 표에 넣음 — KNOWN_DEFECT(10번) 시험이 깨져야 함 | 깨짐(의도) | 깨짐(의도) | 2 · KNOWN_DEFECT_a_rejected_candidate_is_filtered_by_load_home | - |

| F04 | KNOWN_DEFECT 고치기(과격) | 부분 일치를 정확 일치로(과격한 고침 — 신용카드·체크카드·카드값 일치까지 사라져야 하므로 '의도한 카드 낱말' 시험도 깨져야 함) | - | 깨짐(의도) | 30 · KNOWN_DEFECT_the_same_title_wins_when_the_graphics_card_se | 기존 시험은 안 깨짐 |

| N01 | 서랍 라벨(레거시) | 서랍의 첫 항목 이름 '월간 검색량' 을 상대값 이름으로 재라벨 | - | 잡힘 | 5 · none_of_the_legacy_count_labels_borrows_the_relative_inter | - |

| N02 | 툴팁(레거시) | 행의 '월 검색량' 툴팁을 상대값 설명으로 재해석 | - | 잡힘 | 3 · none_of_the_legacy_count_labels_borrows_the_relative_inter | - |

| N03 | 명령줄 단위(레거시) | 명령줄 출력의 월간 검색 수요 단위 '회' → '점' | - | 잡힘 | 1 · the_command_line_prints_the_legacy_count_as_monthly_search | - |

| N04 | 후보 라벨(레거시) | 후보 칸 라벨 '월간 검색 수요' 를 상대값 이름으로 재라벨 | - | 잡힘 | 2 · the_command_line_prints_the_legacy_count_as_monthly_search | - |

| N05 | 행 라벨(레거시) | 행의 '블로그 문서 수' 라벨 변경 | - | 잡힘 | 1 · the_legacy_absolute_count_is_called_monthly_search_volume_ | - |

| N06 | 숫자 모양(레거시) | 검색량 숫자의 천 단위 쉼표를 뺌 | - | 잡힘 | 2 · the_legacy_absolute_count_is_called_monthly_search_volume_ | - |

| N07 | P4 가 새 문구를 더하면 | 새 Trend 라벨 키를 더함(P4 가 할 일) — '아직 없음' 시험이 의식적으로 깨져야 함 | - | 깨짐(의도) | 1 · the_screen_text_has_no_relative_interest_label_yet_so_p4_a | - |


## 4. 시험 줄 — 실제 `Ran N tests … OK` (이 PC, 모듈마다 한 번에 하나)

**보완 커밋 `4c746d6`** — 3.12.10(PySide6 없음):
```text
[NEW-3.12] py3.12.10 test_topic_protect_ui: Ran 29 tests in 1.645s OK
[NEW-3.12] py3.12.10 test_topic_protect_suggest: Ran 25 tests in 3.610s OK
[NEW-3.12] py3.12.10 test_topic_protect_candidates: Ran 19 tests in 0.115s OK
[NEW-3.12] py3.12.10 test_repo_layout: Ran 26 tests in 3.635s OK
[NEW-3.12] py3.12.10 test_content_model: Ran 34 tests in 0.013s OK
temp leftovers: 0 []
[NEWB-3.12] py3.12.10 test_ui_core: Ran 94 tests in 3.297s OK
[NEWB-3.12] py3.12.10 test_ui_adapters: Ran 25 tests in 3.321s OK
[NEWB-3.12] py3.12.10 test_errors_catalog: Ran 37 tests in 1.944s OK
[NEWB-3.12] py3.12.10 test_service_candidates_cli: Ran 60 tests in 12.701s OK
```

진짜 3.10.11:
```text
[NEW-3.10] py3.10.11 test_topic_protect_ui: Ran 29 tests in 1.308s OK
[NEW-3.10] py3.10.11 test_topic_protect_suggest: Ran 25 tests in 3.578s OK
[NEW-3.10] py3.10.11 test_topic_protect_candidates: Ran 19 tests in 0.099s OK
[NEW-3.10] py3.10.11 test_repo_layout: Ran 26 tests in 3.357s OK
[NEW-3.10] py3.10.11 test_content_model: Ran 34 tests in 0.018s OK
```

3.12.10 + PySide6 6.12.0(새 3모듈):
```text
[NEW-PySide6] py3.12.10 test_topic_protect_ui: Ran 29 tests in 1.337s OK
[NEW-PySide6] py3.12.10 test_topic_protect_candidates: Ran 19 tests in 0.142s OK
[NEW-PySide6] py3.12.10 test_topic_protect_suggest: Ran 25 tests in 4.233s OK
```

기준선 `3b1294b` 소스 위(새 시험이 기준선에서 통과해야 함):
```text
[BASE-3.12] py3.12.10 test_topic_protect_ui: Ran 29 tests in 1.800s OK
[BASE-3.12] py3.12.10 test_topic_protect_suggest: Ran 25 tests in 3.873s OK
[BASE-3.12] py3.12.10 test_topic_protect_candidates: Ran 19 tests in 0.131s OK
[BASE-3.10] py3.10.11 test_topic_protect_ui: Ran 29 tests in 1.440s OK
[BASE-3.10] py3.10.11 test_topic_protect_suggest: Ran 25 tests in 4.102s OK
[BASE-3.10] py3.10.11 test_topic_protect_candidates: Ran 19 tests in 0.158s OK
```

N1 머리 `b2096ce` 위(병합 순서 N1 → P0):
```text
[N1new-3.12] py3.12.10 test_topic_protect_ui: Ran 29 tests in 1.438s OK
[N1new-3.12] py3.12.10 test_topic_protect_suggest: Ran 25 tests in 4.257s OK
[N1new-3.12] py3.12.10 test_topic_protect_candidates: Ran 19 tests in 0.152s OK
[N1new-3.10] py3.10.11 test_topic_protect_ui: Ran 29 tests in 1.323s OK
[N1new-3.10] py3.10.11 test_topic_protect_suggest: Ran 25 tests in 3.860s OK
[N1new-3.10] py3.10.11 test_topic_protect_candidates: Ran 19 tests in 0.232s OK
```

해시 시드 0·1·4242 로 3번 반복 + 임시 폴더(TEMP)를 비운 폴더로 바꿔 누수 확인(새 3모듈, 3.12):
```text
[NEWREP-seed0] py3.12.10 test_topic_protect_ui: Ran 29 tests in 1.341s OK
[NEWREP-seed0] py3.12.10 test_topic_protect_suggest: Ran 25 tests in 3.597s OK
[NEWREP-seed0] py3.12.10 test_topic_protect_candidates: Ran 19 tests in 0.087s OK
temp leftovers: 0 []
[NEWREP-seed1] py3.12.10 test_topic_protect_ui: Ran 29 tests in 1.360s OK
[NEWREP-seed1] py3.12.10 test_topic_protect_suggest: Ran 25 tests in 3.478s OK
[NEWREP-seed1] py3.12.10 test_topic_protect_candidates: Ran 19 tests in 0.100s OK
temp leftovers: 0 []
[NEWREP-seed4242] py3.12.10 test_topic_protect_ui: Ran 29 tests in 1.346s OK
[NEWREP-seed4242] py3.12.10 test_topic_protect_suggest: Ran 25 tests in 4.208s OK
[NEWREP-seed4242] py3.12.10 test_topic_protect_candidates: Ran 19 tests in 0.157s OK
temp leftovers: 0 []
```

**1차 커밋 `1f2297b`** 에서 돌린 요청 목록 전체(기존 모듈은 코드·시험이 0줄 바뀌어 결과가 그대로 유효 — 문서를 읽는 모듈은 위에서 보완 커밋으로 다시 돌림):
```text
[A-3.12-noQt] py3.12.10 test_topic_protect_ui: Ran 25 tests in 1.921s OK
[A-3.12-noQt] py3.12.10 test_topic_protect_suggest: Ran 22 tests in 3.825s OK
[A-3.12-noQt] py3.12.10 test_topic_protect_candidates: Ran 18 tests in 0.140s OK
[A-3.12-noQt] py3.12.10 test_repo_layout: Ran 26 tests in 4.680s OK
[A-3.12-noQt] py3.12.10 test_ui_adapters: Ran 25 tests in 3.929s OK
[A-3.12-noQt] py3.12.10 test_ui_core: Ran 94 tests in 3.479s OK
[A-3.12-noQt] py3.12.10 test_suggest: Ran 113 tests in 18.644s OK
[A-3.12-noQt] py3.12.10 test_suggest_score: Ran 29 tests in 0.022s OK
[A-3.12-noQt] py3.12.10 test_suggest_data: Ran 12 tests in 7.755s OK
[A-3.12-noQt] py3.12.10 test_content_candidates: Ran 121 tests in 0.415s OK
[A-3.12-noQt] py3.12.10 test_candidate_csv: Ran 67 tests in 0.678s OK
[A-3.12-noQt] py3.12.10 test_service_write_json: Ran 19 tests in 0.702s OK
[A-3.12-noQt] py3.12.10 test_content_model: Ran 34 tests in 0.015s OK
temp leftovers: 0 []
--- 3.10.11 ---
[C-3.10] py3.10.11 test_topic_protect_ui: Ran 25 tests in 1.350s OK
[C-3.10] py3.10.11 test_topic_protect_suggest: Ran 22 tests in 3.682s OK
[C-3.10] py3.10.11 test_topic_protect_candidates: Ran 18 tests in 0.145s OK
[C-3.10] py3.10.11 test_repo_layout: Ran 26 tests in 2.959s OK
[C-3.10] py3.10.11 test_ui_adapters: Ran 25 tests in 3.832s OK
[C-3.10] py3.10.11 test_ui_core: Ran 94 tests in 3.937s OK
[C-3.10] py3.10.11 test_suggest: Ran 113 tests in 18.462s OK
[C-3.10] py3.10.11 test_suggest_score: Ran 29 tests in 0.018s OK
[C-3.10] py3.10.11 test_suggest_data: Ran 12 tests in 6.896s OK
[C-3.10] py3.10.11 test_content_candidates: Ran 121 tests in 0.400s OK
[C-3.10] py3.10.11 test_candidate_csv: Ran 67 tests in 0.582s OK
[C-3.10] py3.10.11 test_service_write_json: Ran 19 tests in 0.630s OK
[C-3.10] py3.10.11 test_content_model: Ran 34 tests in 0.018s OK
--- 3.12 + PySide6 ---
[B-3.12-PySide6] py3.12.10 test_topic_protect_ui: Ran 25 tests in 1.405s OK
[B-3.12-PySide6] py3.12.10 test_ui_adapters: Ran 25 tests in 3.393s OK
[B-3.12-PySide6] py3.12.10 test_ui_core: Ran 94 tests in 3.962s OK
```

ruff(`C:\ccgui\dev\Scripts\ruff.exe check --select F,E9,B,UP --target-version py310`): 새 시험 3개 `All checks passed!`(1f2297b·4c746d6 모두), `tests` 전체는 79건으로 기준선 `3b1294b` 와 같음(P0 가 더한 지적 0), `src` 15건도 기준선 그대로.

## 5. 델타 `4c746d6` 확인 (코디네이터 요청 ①~⑤)

범위: `git diff 1f2297b 4c746d6` = 6파일 +123 −31(`CHANGELOG` 1/1·`DECISIONS` 4/4·계획 25/25·시험 14/0·38/1·41/0). 지운 31줄은 전부 1차 P0 가 더한 줄이고(시험 1줄은 함수 안 `import` 를 모듈 위로 옮긴 것) 기준선(`3b1294b`) 대비 누적은 **여전히 같은 6파일·삭제 0·`src/` 등 0줄**, `git diff --check` 0(누적·델타 모두), 숨은 글자·BOM·탭·줄끝 공백 0, 전부 LF, 계획 396줄.

| # | 확인할 것 | 결과 |
|---|---|---|
| ① | 출처 표기 정정 — 운영자가 말하지 않은 것을 운영자 말로 쓴 곳이 없는지 | **없다.** `운영자` 낱말 전수(계획 24·결정 12·CHANGELOG 2곳)를 운영자 원문(R-131 답 1절)과 하나씩 대조. 운영자가 정한 것으로 적힌 것은 모두 원문에 있다 — 칸 이름 5개(`search_demand_count`·`trend_ratio`·`trend_status`(상승/보통/하락/데이터 부족)·`trend_period`·`trend_compared_group`), 화면 `최근 관심도(상대값)`·`월 검색량`/`회` 금지, '기존 칸 덮어쓰기·재해석 금지', '의미가 불명확하면 Migration 하지 말고 Legacy', 연결 여섯 이름·'유실되지 않게', 작업/구간 예시 값·'하나의 `status` 로 합치지 않음', 파일 이름 4개·키 제외, 네이버 A/B 만 활성, 단계 보고 6항목. 이 계획의 해석으로 적힌 것은 모두 운영자 원문에 없다 — `search_demand_source`·`trend_queried_on`·`data_status`·영문 상태 값·0~100 범위·`work_status`·`recommendation_band`·`UNRATED`·`COPIED`·`generation_enabled`·`history_enabled`·`CandidateLink`·`Provenance`. 7절 ⑥ 은 '이것은 운영자 말이 아니라 이 조사의 결론, 운영자 지시를 적용한 것'. 결정 행 상태 칸도 '운영자 승인의 범위에서 이 계획이 구체화한 결정'. 남은 표현 중 `H 실시간 이슈`(10절)·`운영자가 이슈 후보와 출처 주소를 …` 는 R-131 의 승인된 기본값(H=1)을 옮긴 것이라 맞다 |
| ② | 레거시 라벨 시험이 `월 검색량`·`월간 검색량`·`회`·툴팁을 정말 못박는지(V31) | **못박는다.** 내 변이: V31(행 라벨 `월 검색량`→`최근 관심도(상대값)`) 이제 **잡힘 4건**(`LegacyDemandLabelTest` 3개), V32(`회`→`점`) 잡힘 2건. 새 변이 N01(서랍 `월간 검색량` 재라벨)·N02(툴팁을 상대값 설명으로)·N03(명령줄 단위 `회`→`점`)·N04(후보 라벨 `월간 검색 수요` 재라벨)·N05(`블로그 문서 수` 이름)·N06(검색량 쉼표 제거) **모두 잡힘**, N07(P4 처럼 `최근 관심도(상대값)` 새 키를 더함)은 '아직 없음' 시험만 깨짐(의도 — 계획·시험 주석이 그렇게 말함). `회` 단위(V32)는 1차 때도 기존 `test_ui_core` 가 잡았고 이제 새 시험이 한 번 더 잡는다 |
| ③ | P0b 영향 설명(`season_fit` 이 보관함 후보 우선도에도 — 89.1 → 81.8)이 코드와 맞는지 | **맞다.** 경로: `candidates list --priority`(`cli.py:462`)·`show`(`cli.py:471`) → `service/suggestions.assess_rows`(`:269`, `sg.assess` 호출 `:296`) → `suggest.py:664` `season_fit`. 복사본에 그래픽카드·카드뮴만 제외하는 고침(F01)을 넣어 직접 계산: 보관함 후보 우선도 그래픽카드·카드뮴 **89.1 → 81.8**(프로필 B 있으면 **92.9 → 88.2**), 신용카드·체크카드·카드값은 **89.1 그대로**, 평범한 낱말('자전거')은 81.8. 새 `StoredCandidatePriorityTest` 3개의 숫자와 같고, F01·F02 에서 KNOWN_DEFECT 보관함 시험만 깨지며 '의도한 카드 낱말' 시험은 통과. 우선도 구간 이름('높음')은 둘 다 높음이라 안 바뀌고 점수와 이유 문장만 바뀐다 |
| ④ | 새 시험이 3.12·진짜 3.10.11 에서 통과하고 계획 문서가 400줄 이내인지 | **통과·396줄.** 3.12.10·3.10.11·3.12+PySide6 6.12.0 모두 29·25·19 = 73개 OK, 기준선 `3b1294b` 소스와 N1 머리(`b2096ce`) 위에서도 OK(4절). 문서를 읽는 `test_repo_layout`(26)·`test_content_model`(34)·`test_errors_catalog`(37)·`test_service_candidates_cli`(60)·`test_ui_core`(94)·`test_ui_adapters`(25) OK. ruff(`F,E9,B,UP`, py310) 새 파일 0건(`tests` 전체 79건은 기준선과 같음). 시험 임시 폴더 누수 0 |
| ⑤ | 새 델타에서 원문 12자 겹침이 늘었는지 | **늘지 않았다.** 1차 커밋 39곳 = 보완 커밋 39곳, 목록 완전히 같음(추가 줄 7,500자 늘었는데 새 겹침 0). 18자 이상 4곳(표 틀)도 같음 |

## 6. 구현 보고 6항목 확인 (구현자 보고서 `W\p25p0_report.md` 0절 — 보완 뒤 값 기준)

| 항목 | 구현자가 쓴 것 | 내가 확인한 것 | 판정 |
|---|---|---|---|
| ① 변경 파일 | 6개, +1,333줄, 삭제 0(보완 커밋만 보면 +123 −31). 시험 365·325·242줄, 계획 396줄, DECISIONS 41~44행, CHANGELOG 39행 | `git diff --numstat 3b1294b 4c746d6` = 1/0·4/0·396/0·242/0·325/0·365/0 (합 1,333, 삭제 0). `git diff 1f2297b 4c746d6` = 6파일 +123 −31 — 지운 31줄은 모두 P0 가 이미 더한 줄(문서 3·시험 1줄). `src/`·`scripts/`·`vendor/`·`.github/`·`VERSION`·의존성 0줄, 기존 시험 수정 0 | 맞음 |
| ② 추가·변경된 시험 | 73개(ui 29·suggest 25·candidates 19), 변경한 기존 시험 0, KNOWN_DEFECT 11개, 모든 시험 위 주석 73/73 | 3.12·3.10.11 에서 29·25·19 = 73 확인. 정적 검사: 시험 73개 전부 표준 주석 있음, KNOWN_DEFECT 이름 11개(1+7+3) 모두 `KNOWN_DEFECT:` 주석 있음 | 맞음 |
| ③ 전체 시험 결과 | 전체 `discover` 는 안 돌림, 모듈별 실제 줄 | 같은 모듈 줄을 내가 다시 돌려 개수·OK 가 모두 같음(아래 4절). 전체 `discover`·CI 네 칸은 나도 못 돌림 | 맞음(정직하게 '전체는 안 돌림') |
| ④ 기존 기능 영향 | 없음 — `src/` 0줄·기존 시험 0줄·새 시험은 현재 동작만 못박음·새 시험이 변이 52곳을 모두 잡음 | `src/` 0줄·기존 시험 0줄 맞음, 새 시험은 기준선 `3b1294b` 소스에서도 73개 통과(3.12·3.10). '변이 52곳 모두 잡음' 은 구현자 변이에 한해 맞고, 내가 새로 설계한 변이는 일부 놓침(3절) — '촘촘함' 일반화는 약간 과장 | 사실상 맞음(과장 한 줄) |
| ⑤ 다음 단계 동작 변화 | P0b: 제안 결과 + 보관함 후보 우선도(`candidates list --priority`·`show`)가 바뀐다(89.1 → 81.8) | 보관함 후보도 같은 `season_fit` 을 쓴다는 것이 코드와 맞음(`suggest.py:664`, `service/suggestions.py:296`, `cli.py:462·471`). 그래픽카드·카드뮴만 제외하는 고침을 복사본에 넣어 직접 돌린 값: 89.1 → 81.8(프로필 B 92.9 → 88.2), 신용카드·체크카드·카드값은 89.1 그대로. 바뀌는 동작은 '계절 낱말 일치'의 두 쓰임(제안·보관함 후보)뿐이고 다른 곳에서 `season_fit` 을 쓰는 곳은 없다(`grep`) | 맞음(1차 보고의 '제안만' 은 델타로 정정됨) |
| ⑥ 데이터 마이그레이션 | 없음 — 새 데이터는 별도 `topic_engine.db` + JSON 셋, `chanceblog.db`(판 2) 불변 | P0 는 데이터·스키마 파일을 안 건드림(변경 6개가 모두 시험·문서). '판 3' 표현 0건(`git diff` 추가 줄 전수 검색). 보관함 판 고정 시험(`DdlFreezeTest`)과 `SCHEMA_VERSION = 2`·`MIGRATIONS = {1: …}` 그대로 | 맞음 |

## 7. 운영자 조건 8항목 반영 확인 (`r131_operator_answer.md` 2절 '확정 사항' 1~8 ↔ 계획 문서·결정 행·보고)

| # | 확정 사항 | 계획 문서 | DECISIONS | 보고 | 판정·지적 |
|---|---|---|---|---|---|
| ① | 결정 A~H 모두 1 '운영자 승인' | 머리말·10절 표(A~H 선택 1, 확정 내용, 이어지는 곳) | D-36(D)·D-37(E)·D-38(G)·D-39(A·C·F) 상태 칸 '운영자 승인(…)의 범위에서 이 계획이 구체화한 결정' | 있음 | **B(채널 이름 대응)·H(실시간 이슈)는 결정 행이 없다**(계획 5.2·10절에만) — 낮음 |
| ② | Trend 필드 이름 7개 + `data_status`, Legacy 유지·자동 이전 없음, 재라벨 금지 | 4.2 표(8칸, '누가 정했나' 열: 운영자 5·이 계획 3), 4.2 불릿 3개 | D-37 ①~⑤ | 있음 | 맞음. 이름·값(4+4)·화면 글(상승·보통·하락·데이터 부족)·`search_demand_count` 출처 필수 모두 일치. 재라벨 금지는 새 시험 `LegacyDemandLabelTest` 가 못박음(V31·N01~N06 잡힘) |
| ③ | 연결 추적 6개·출처 스냅샷·`draft_plan_id` 열린 항목 | 4.3 표, 11절 1번 | D-36 ④ | 있음 | 맞음(운영자 조건 2 의 여섯 이름 그대로, `CandidateLink`·`Provenance` 는 '이 계획의 이름' 표기) |
| ④ | 상태 두 축 이름·값·HOLD 구분 | 5.1 표·HOLD 두 축 설명 | D-36 ② | 있음 | 맞음(저장 5값 + 계산 4값, 구간 4값 + `UNRATED`, 두 축 HOLD 구분 명시, 이름은 '이 계획의 이름' 표기) |
| ⑤ | 저장: 별도 `topic_engine.db` + JSON 3개·백업 4개·키 제외·`chanceblog.db` 불변·마이그레이션 없음 | 4.4·4.5·4.6, 8.1 P3 행 | D-39 ①~⑤ | 있음 | 맞음. **'판 3' 표현 0건**, `chanceblog.db`(판 2) 불변, 백업 4파일·API 키 제외 |
| ⑥ | P0b 회귀 예 5개와 순서 | 8.3 표(그래픽카드·카드뮴 ✗, 신용카드·체크카드·카드값 ✓)·순서 문장 | — | 있음 | 맞음. 다섯 낱말의 현재 값 `(70, '연말정산 준비')` 를 시험이 못박고, 현실적인 고침 F01·F02 에서 의도대로 두 낱말만 깨짐 |
| ⑦ | 활성 채널 네이버 A·B, 나머지 3채널은 프로필·이력 읽기·정규화만(`generation_enabled`·`history_enabled`) | 4.6 표·1절 원칙 7 | D-36 ⑥ | 있음 | 맞음(`generation_enabled` 는 `naver_a`·`naver_b` 만 True, `history_enabled` 5채널) |
| ⑧ | 단계 보고 6항목 순서 | 8.2 표 | D-36 ⑦ | 보고서 0절이 맨 앞 | 맞음(순서·이름 동일) |

전략 문서(비공개) 숫자 대조: 계획 6.1 가중치 5열×6행(각 열 합 100)·4.6 지속형:실시간 비율·후보 경로 비율(30·20·20·15·15)·6.3 구간(80/65/50)과 상위 5·묶음 2·보류 90일·6.4 중복 구간(40/60/75)과 채널 간 최대 2·소제목 4 를 내가 전략 문서 §6·§7·§13·§14·§17 과 숫자로 대조해 모두 일치.

## 8. 기존 `search_demand` 의미 조사 — 내가 코드에서 다시 구한 답과 계획 7절 비교

같은 다섯 질문에 구현자의 글을 보지 않고 `grep`·파일 읽기로 다시 답했다(기준선 `3b1294b`).

| 질문 | 내가 코드에서 직접 구한 답 | 계획 7절 | 일치 |
|---|---|---|---|
| ① 값이 들어오는 길 | 명령줄 `candidates add --search-demand`(`cli.py:627`, 모으는 곳 `:502`)·CSV 열 별칭(`candidate_csv.py:47`, 읽기 `:370`)·코드 `Candidate.new`. 후보 값을 고치는 다른 길은 없다(`edited(` 는 `project_id` 연결에만 쓰임, `service/candidates.py:484·492`; CLI `edit` 는 원고용). 제안은 보관함 후보 값을 **읽기만**(`suggest.py:210-220`), 제안을 후보로 넣을 때도 지표 없음(`service/suggestions.py:256`). 수집 코드 없음 — `README.md:61` '아직 모으지 않으므로 비어 있고' | 같음(줄 번호 모두 맞음) | 일치 |
| ② 공급자·측정 기간을 적는 칸 | 없음. 저장 키 24개(`candidates.py:355` `_KEYS`)에서 출처에 가까운 것은 `data_date`(지표가 하나라도 있으면 필수, `:423-426`)와 자유 글 `reason` 뿐. CSV '출처'·'기간' 열은 별칭표에 없어 모르는 열로 무시(`candidate_csv.py:41-58`, 시험이 못박음) | 같음 | 일치 |
| ③ 문서·설계 흔적 | 뜻은 '월간 검색 수요(회)'로 일관(`candidates.py:70·370`, `ARCHITECTURE.md:128·140`, `README.md:65`, `UI_DESIGN_SPEC.md:62·100`, `UI_STATES.md:18`). `connections.py:138` `naver_openapi`(검색·데이터랩) '지표 칸을 채우는 데'·`:142` `naver_searchad`(검색광고) '키워드 도구의 월간 검색 수'(준비 중) — 둘 다 호출 코드 없음(`ARCHITECTURE.md:74-75`). `PC+모바일`·`모바일 합`·`합산`·`월간검색수`·`상대지수`·`상대값`·`상대 지표` 낱말은 소스·문서·시험 어디에도 0건(`git grep` at `3b1294b`), `relative` 는 경로·문법 이야기로만 나온다(`mobile_share` 는 별개 칸) | 같음(`PC+모바일 합계` 는 **추정** 표시, 상대지수 설명 없음 표시) | 일치. 단 N1 병합 뒤에는 `connections` 부분이 달라짐(M1) |
| ④ 점수 환산 | 로그 눈금, 10만 회에서 100점(`suggest_score.py:48·111-112`), 기회도의 수요 몫 50%(`:47·119-120`), 기회도는 우선도의 15%(`:22`). 제안(`suggest.py:417`)과 보관함 후보 평가(`:668`)가 모두 씀. 상대지수 87 이 들어오면 38.89점 | 같음 | 일치 |
| ⑤ 화면 라벨 | `ui/adapters.py:60` → `Topic.demand`(`services.py:31`) → 행 `월 검색량`(`text.py:28`)·서랍 `월간 검색량`(`:39`)·단위 `회`(`:74-75`)·툴팁 '한 달 동안 … 어림잡은 값'(`:29`). 명령줄 `{:,}회`(`format.py:236`) | 같음 | 일치 |

결론 비교: 구현자의 결론 '출처 불명확 → Legacy 유지·자동 이전 없음' 은 위 근거와 맞고, 다르게 읽히는 증거는 찾지 못했다. 다만 ①(**귀속**) 1차 계획은 이 결론과 근거를 '운영자의 결론'이라고 적었는데 운영자 원문에는 조건부 지시(의미가 불명확하면 Legacy 유지)뿐 — 델타로 정정됨. ②(**시점**) N1 병합 뒤에는 `naver_openapi` 가 '옛 항목', `naver_apihub` 가 '관심도 변화' 조회로 바뀌므로 '공급자가 한 곳이 아니다' 근거가 약해진다(M1). 결론 자체는 어느 쪽이든 같다.

## 9. 원문 복사·민감 정보

- 전략 문서(비공개, `(KCY 폴더의 chanceblog_content_topic_selection_strategy_v1.0.0.md — 이전 PC 에만 있던 원문, 운영자가 다시 첨부해야 읽을 수 있음)`)와 `3b1294b..4c746d6` 의 추가 줄을 공백 무시·NFKC 로 비교해 **12자 이상 연속으로 같은 곳을 자동 대조**: 1차 커밋(`1f2297b`) 39곳, 보완 커밋(`4c746d6`) 39곳 — **목록이 완전히 같아 델타가 겹침을 늘리지 않았다**. 39곳의 정체는 식별자(`source_topic_id`·`github_pages`·`monetization_tags`·`search_intent`·`topic_cluster`·`target_reader`·`candidate_id`·`trend_status`·`topic_engine` 등)·표 틀(`|---|---|GitHub Pages|`)·`Search Trend` 낱말 조각이고, 문장 조각은 `숫자만으로 자동 삭제하지 않는다`(15자)와 표 칸 둘(`전체 후보에 저장`·`중복 또는 기존 글 업데이트 후보`)뿐. 18자 이상은 표 틀 4곳. → 설명은 새로 썼고 값·규칙 수준만 겹침(낮음 10).
- 실제 Seed 목록(대분류>중분류>씨앗)·키·토큰·절대 경로·개인 이메일·개인 정보: 변경분에 없음(`test_repo_layout` 의 키 모양·개인 이메일 훑기도 통과). 협찬·수익 전략: 가중치 숫자(수익화 25·20·10)·후보 경로 비율(협찬 준비형 15)·'협찬 고지 문구는 P6' 같은 **숫자 설정값·일반 설명뿐**, 구체 상품·업체명·수익 목표 없음 → 선을 넘지 않음. 계획에 '대구 기준 지역 목록'이 두 번 나오지만 지역 이름 하나이고 주소·개인 정보가 아니다.
- 시험 예시 프로필의 낱말은 일반 낱말(낮음 10).

## 10. 결정 번호·문서 일관

- 새 결정 행은 **D-36~D-39**, N1 은 D-35 — 겹치지 않는다(`git show b2096ce:docs/DECISIONS.md` 41행이 D-35, P0 의 41행이 D-36). 둘 다 표 끝(D-34 다음 줄)에 더해서 병합 때 `DECISIONS.md`·`CHANGELOG.md` 에서 충돌한다 — `git merge-tree --write-tree n1 p0new` 로 확인(그 두 파일뿐, 계획 문서·시험·`src/` 는 자동 병합). P0 만 먼저 병합하면 D-35 가 비지만 `test_repo_layout` 은 '부르는 번호 ⊆ 정의된 번호' 만 보므로 통과하고 P0 의 문서·시험은 `D-35` 글자를 쓰지 않았다(변경분 전수 검색 0건).
- `tests/test_repo_layout.py`(번호 규칙 포함)·`VersionTest`(VERSION ↔ CHANGELOG 맨 위 `## [0.0.0]`)·`test_content_model` 은 3.12·3.10 모두 통과. CHANGELOG 는 기존 방식(한 구역에 항목 덧붙임)대로 한 줄, `VERSION` 은 그대로.
- 계획 문서가 `R-131` 요청 글(`W\r131_draft.md`)과 모순되는 곳: R-131 의 '보관함 판 2→3'·'`월 검색량` 을 `최근 관심도(상대값)` 로 바꿈'·'바뀌는 시험 … 화면 문구 3곳' 은 운영자 답(별도 `topic_engine.db`·재라벨 금지)으로 대체됐고 계획 문서는 대체된 쪽을 따른다. 남은 흔적은 8.1 P4 행의 '화면 문구 3곳'(낮음 5). 나머지(P0~P6 단계·등급·결정 번호 D-36 부터·A~H 기본값)는 일치.
- 시험이 못박는 문서 절 제목: `docs/ARCHITECTURE.md`(§7·§8·§3 등)·`TROUBLESHOOTING.md`·`SECURITY.md`·`README.md` 는 변경 0 — 건드리지 않았다.
- 쉬운 한국어·표 중심: 계획 문서는 표 28개(구조 점검: 모든 표의 열 수가 머리줄과 같음), 영어 이름은 코드 이름뿐이고 설명은 한국어. `Legacy`·`Provenance`·`Migration` 같은 낱말은 운영자 글에서 온 것(`Legacy`·`Migration`·`Provider`)이거나 코드 이름이라 허용 범위. 396줄(한도 400 이내). 결정 행은 한 행이 1~2천 자로 길다(읽기에는 무겁지만 기존 D-33 은 1만 7천 자).

## 11. 못 확인한 것

- **GitHub·CI 네 칸(Windows·Ubuntu × 3.10·3.12)**: push·진짜 GitHub 호출을 하지 않아 못 봤다. Ubuntu 는 이 PC 에서 못 돌렸다(새 시험은 경로·줄바꿈·로캘에 기대지 않고 `tempfile` 만 쓰며 `-X utf8` 없이도 쓰기·읽기에 `encoding="utf-8"` 을 명시 — 정적 검토만).
- **`origin/main` 이 20:02:59(마지막 fetch) 이후 움직였는지**: 로컬 `cd_repo` 의 `origin/main` = `3b1294b`(같음)이지만 이후는 모름(GitHub 금지). 로컬 `main` 은 낡은 'Initial commit' 이라 기준이 아니다.
- **전체 `discover` 시험**: 지시대로 모듈별로만 돌렸다(새 3모듈 + 요청 목록 + 문서를 읽는 모듈 몇 개). Qt 시험(`test_ui_qt*`)은 돌리지 않음 — 변이 V31 을 Qt 시험이 잡는지 보려던 시도는 CPU 부하로 240초 시간 초과, 델타로 새 시험이 잡게 되어 불필요해져 중단(내가 시작한 프로세스 트리만 끝냄).
- **변이는 3.12(PySide6 없음)에서만**. 구현자 변이(M01~M52)는 재현하지 않았다.
- `topic_engine.db`·백업·`draft_plan_id` 같은 **P3 설계의 실현 가능성**(코드 없음)과 블로그 쪽 `posts.json`·`blogger*_history.json` 형식(구현자도 못 봄).
- 계획 4.1·2절의 '조사 때 같은 뜻 4·부분 8·없음 13'(구현자 조사 보고서 기반)은 대조하지 않았다.
- 전략 문서 대조는 숫자(가중치·비율·구간·중복 기준·상위 N·소제목·보류일)만 했다.


---
작성: 2026-11-04 21:06:22 (시작 20:10:34, 마감 21:25:34). 내가 만든 도구·결과는 `W\ver_p0_x\` (`tools\mutations.py`·`mutate.py`·`copycheck.py` …, 변이 결과 `mut_results*.json`).
