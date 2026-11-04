시작 시각: 2026-11-04 21:34:12 (마감 약 22:00, 시작 후 25분) — 델타 `4c746d6..23ca08e` 재확인(읽기·시험만, push·네트워크 없음) · 끝 21:53

# 델타 2 재확인 보고 — WIP 3 `23ca08e` (부모 `4c746d6`, 기준 `3b1294b`)

**결론: 조건부 병합 가능** — 이전 중간 2건은 해소됐다(M1 의 `connections.py` 부분은 N1 머리에서 줄까지 정확, M2 의 Qt 시험은 `ast` 로 바뀌어 V85 를 잡고 V86·V87 에 안 깨진다). 남은 조건은 **계획 7절 머리 문장 한 줄**의 정정뿐이다(그 문장이 '`connections.py` 의 줄만 밀린다·나머지 인용은 같은 줄을 확인했다' 고 하는데 `docs/ARCHITECTURE.md` 인용 4개도 N1 뒤에 밀린다). 새 시험 76개는 3.12·진짜 3.10.11·N1 머리 위에서 통과하고, 새로 설계한 변이 110곳 중 **모든 시험이 놓치는 것은 0곳**이다.

## 지적 (심각도순)

### 높음
없음.

### 중간
없음. (1차 최종 보고의 중간 M1·M2 는 아래 2절에서 해소 확인.)

### 낮음
1. **[병합 전 한 줄 정정 권장] 계획 7절 머리 문장이 N1 뒤의 인용 상태를 틀리게 말한다.** 문장: '`service/connections.py` 의 줄만 밀리고 … `cli.py`·`format.py` 등 나머지 인용은 N1 병합 가지 머리(`r134-naver-hub-safety-2`)에서도 같은 줄임을 확인했다'.
   - 재현: `W\ver_p0_x\tools\cite_check.py`(계획의 `파일:줄` 인용 42개를 `3b1294b` 의 그 줄 글과 N1 머리 `82ef399`·`3b0194f` 의 같은 줄 글로 비교). 32개는 같고 10개가 다르다 — `connections.py` 5개(기준 `:138`·`:142`, N1 쪽 `:176`·`:181`·`:198` — 의도된 이동), **`docs/ARCHITECTURE.md` 4개**(`:85`→`:89`, `:128`→`:132`, `:140`→`:144` 로 +4줄 밀리고 `:74-75` 는 '옛 항목' 행으로 내용이 바뀜), 표기 1개(`candidate_csv.py:41-58` — 디렉터리 생략). `cli.py`·`format.py`·`candidates.py` 등 코드 인용은 모두 같은 줄이다.
   - 가지 이름도 낡았다: 지금 N1 병합 가지는 `r134-naver-hub-safety-3`(`82ef399`, 트리 = N1 WIP `2cc6b5a`)이고 `-2`(`3b0194f`)와는 문서 5개만 다르다(`connections.py` 줄은 같음 — ③ 의 N1 뒤 줄 번호는 둘 다 맞다).
   - 고칠 방향: '… N1 병합 뒤에는 `connections.py`(138→198·142→181·새 용도 176)와 `docs/ARCHITECTURE.md`(+4줄)의 줄이 밀리고 코드 인용(`cli.py`·`format.py` 등)은 같은 줄이다(`r134-naver-hub-safety-3` `82ef399` 기준)'.
2. **'시험이 실제 시계를 읽지 않는다'(구현자 보고 낮음 8 줄·계획 9.2 '실제 시계 없이')는 한 시험에서는 사실이 아니다.** 재현: `W\ver_p0_x\tools\clocktrap2.py` — `datetime.now()`·`date.today()` 를 부르면 터지게 하되 `isinstance` 는 살리는 덮개로 새 3모듈을 돌리면(엄격) 76개 중 `StrictShapeTest.test_a_candidate_carries_one_to_five_channels_so_one_candidate_can_name_every_channel` 의 하위 시험 5개가 터진다. `Candidate.new(…, bad)` 를 `now=` 없이 불러 `utc_now()` 를 읽는다(값은 안 쓰인다 — 어차피 `CANDIDATE_INVALID`). 기록 모드로는 76개가 모두 통과하고 시계를 읽는 곳은 그 한 줄(5회)뿐이다. 구현자 보고의 '`date.today()`·`datetime.now()` 를 부르면 터지게 바꿔 놓고 76개를 돌려 통과' 는 이 덮개로는 재현되지 않았다(구현자의 덮개 방식은 알 수 없음). 고칠 방향: 그 호출에 `now=NOW` 를 주고 보고·계획 문장은 그대로 둔다(고친 뒤 참이 된다).
3. **`ast` 시험이 억지 변이 하나에 속는다(P10).** 조건을 지역 변수에 담았다가(`is_home = state.page == "home"`) 바로 다음 줄에서 다른 값으로 덮어쓰면(`is_home = state.page == "settings"`) 별칭으로 읽힌 채 통과한다 — 이름 대입을 흐름 없이 모으기 때문. 일부러 만들지 않으면 생기지 않는 모양이고 변수에 홈이 아닌 값을 처음부터 담는 경우(P09)는 잡히므로 허용 범위. 계획 9.1 의 '주석·정리에 속지도 깨지지도 않는다' 는 '자연스러운 정리' 에 한한 말로 읽으면 맞다.
4. **'뒤집는 단계가 없다' 주석이 Legacy KNOWN_DEFECT 셋에만 있고 넷째가 빠졌다.** `test_topic_protect_suggest.RelativeIndexScoreEffectTest`(상대값 87 이 우선도를 81.8→72.6 으로 내림)도 같은 종류인데 새 주석도 계획 9.2 의 '셋(상대값 87·CSV 검색량·기회도 38.89)' 도 이것을 빼놓는다. 고칠 방향: 주석 한 줄과 '셋'→'넷'.

### 내가 1차 최종 보고에서 틀린 것
**낮음 8('`make_ctx` 의 실제 `Clock()` 을 쓴다')은 틀렸다.** `tests/service_support.py` 72행의 `Clock` 은 '가짜 시계 — 고정된 시각을 돌려주고 advance 로만 흐른다' 인데 나는 운영 코드의 시계로 잘못 읽었다. 구현자의 반박(`make_ctx` 의 `Clock` 은 고정 가짜 시계)이 맞다. 다만 구현자가 고친 '화면 시험의 `AppState(today=…)`' 는 진짜 시계 읽기를 막는 올바른 수정이다(`date_text(None)` 이 `datetime.date.today()` 를 부른다 — `ui/core/text.py:85-86`).

## 1. 확인 표 ⑴~⑺

| # | 확인할 것 | 결과 |
|---|---|---|
| ⑴ [중간] 7절 ③·⑥ 의 `connections.py` 인용 | **③·⑥ 은 정확하다.** N1 병합 가지 머리 `82ef399`(트리 `2f274e7…` = N1 WIP `2cc6b5a` 와 같음)에서 직접 대조: `connections.py:176` = `Purpose("naver_apihub", "NAVER API HUB 검색어 트렌드", "네이버 데이터랩 '검색어 트렌드' 로 키워드의 관심도 변화를 조회해 후보의 지표를 보정하는 데 씁니다(준비 중 — 안전 장치만 있고 호출 코드는 아직 없습니다)…`, `:181` = `naver_searchad`(그대로), `:198` = `naver_openapi` 이름 '옛 항목 — 네이버 오픈 API(검색·데이터랩)'(읽기만·새 항목 못 더함) — 계획 ③ 의 N1 뒤 문장·줄 번호와 일치. 기준 쪽 `:138`·`:142` 도 `3b1294b` 에서 맞다. ⑥ 의 '(3b1294b 기준)'·'N1 뒤 근거가 약해진다·남는 것은 이미 든 값이 무엇이었는지 알 수 없다는 쪽뿐·결론은 같다' 도 코드와 맞는다. **다만 7절 머리 문장은 낮음 1 처럼 틀렸다** |
| ⑵ [중간] Qt 시험의 `ast` 전환 | **V85(옛 줄을 주석으로 남기고 서랍을 모두 보임) 이제 잡힘**, V86(조건을 변수로 뺌)·V87(줄 바꿈)·P01(주석만 덧붙임)·P02(단추 변수 이름 바꿈)·P07(따옴표만 바꿈)·P05(기존 추세 서랍 이름을 '최근 관심도 변화' 로) **통과(오경보 없음)**. 깨뜨리는 변이는 모두 잡힘: V82·V83·V84, P06(서랍 조건에 `or` 더함)·P08(서랍 호출을 조건 없이 한 번 더)·P09(지역 변수가 `"settings"` 를 가리킴)·P11(홈 조건을 `!=` 로). 허점은 P10 하나(낮음 3) |
| ⑶ [낮음 12건] 반영 상태 | **1** V11·V30·V34 → 새 시험 3개(`test_the_three_trend_words_become_up_flat_and_down…`·`test_loading_new_data_puts_the_chip_back_to_all…`·`SeasonGenericWordTest`)가 이제 잡음, 파생 변이 P12(하락→flat)·P03(`마무리` 뺌)·P04(`행사` 뺌)도 잡힘 ✓ **2** 계획 9.1 '기존 시험과 합쳐서 보호한다' 문장 — 나열한 모듈 `test_suggest_score`·`test_suggest`·`test_service_suggestions` 가 내 기존 시험 대조(V37·V38·V46→`test_suggest_score`, V42·V45→둘, V50→`test_suggest`, V81→`test_service_suggestions`)와 일치 ✓ **3** D-40(채널 이름 대응)·D-41(실시간 이슈) 추가 ✓ — B=1·H=1 승인 범위·`PLATFORMS` 순서·별칭표 내용이 R-131 초안과 같고 D-40 의 시험 이름 `ChannelEnumerationTest` 가 실제로 있다. D-41 의 '전략 문서 §12 — 공식 출처 한 곳이거나 독립 출처 두 곳' 과 '발표 뒤 48시간 안정화' 는 전략 §12.1·§12.4 와 맞고 'AGENTS.md 절대 규칙 3·6'(외부 글은 데이터·로그인·세션 자동화 금지)도 맞다. 번호 충돌 없음(N1 머리 D-35 뿐, 조정 가지 `r135-p0-topic-protect-2` 는 D-35~D-41) ✓ **4** 결정 A 행·D-39 ④ 가 같은 말('시험용 가짜 예시만, 전략 문서에서 뽑은 시작 목록도 실제 Seed 라 `seeds.json` 에만') — 충돌 해소 ✓ **5** P4 행 구체화 ✓ 사실 확인: `test_ui_core.py:598-600`(`nav("topics")` 뒤 `soon_btn` 단언)·`test_ui_qt.py:137-138`(자리표시 화면) 이 실제로 있다 **6** 좁힘 ✓ (P05 통과·N07 잡힘) **7** 주석 3개 ✓ (넷째 빠짐 — 낮음 4) **8** 내가 틀렸고(위) 시계 문장은 낮음 2 **9** 의존 방향 정리 ✓ D-36 ①·3.1 `model.py` 행·3.2 도식이 같은 말(`content` 의 순수 부품만, `content.store`·`service`·`ui` 금지)이고, `content.candidates` 가 `errors`·`content.status`·`content.model`·`content.profiles` 만 가져오며 `content/__init__` 이 `store` 를 안 가져옴을 확인 **11** 비공개 이름 주석 2곳 ✓ **미반영 10·12 의 이유는 타당**: 10(예시 프로필 낱말) — 'B 의 그래픽카드는 운영자 오탐 예시 자체이고 A·B 첫 셋 제안이 손으로 옮긴 스냅샷이라 바꾸려면 값을 다시 구해야 한다'; 계획·결정 행에는 채널 분야 낱말이 없음을 확인(`grep` 0건). 12(README 링크) — 이번 라운드가 '기존 문서 줄은 안 바꾼다' 라 범위 밖, 병합 때 링크할지는 코디네이터 판단 ✓ |
| ⑷ 새 시험 76개·변이 재현 | **통과**: 3.12.10 ui 31·suggest 26·candidates 19, `test_repo_layout` 26, `test_content_model` 34 / 진짜 3.10.11 같은 숫자 모두 OK(아래 시험 줄). N1 머리 `82ef399` 트리 위에서도 3.12·3.10 OK, 해시 시드 7 로도 OK(임시 폴더 누수 0). **변이: 내가 110곳을 새 3모듈로 전부 다시 돌렸다**(V87·F04·N07·새 P12) — 구현자 변이 67곳 중 M53~M67 15곳은 P01~P05·V82~V87·V11·V30·V34·N07 로 직접 재현했고(M61·M62·M63 은 V11·V30·V34, M66 은 N07, M64·M65 는 P03·P04, M59·M60 은 P01·P02, M67 은 P05, M53~M58 은 V82~V87) 라벨 시험 7곳(M43~M49)도 V31·V32·N01~N06 으로 겹쳐 재현, 모두 구현자 표와 같은 결과 |
| ⑸ 출처 오귀속 재점검 | `운영자` 낱말 53곳(계획 24·결정 27·CHANGELOG 2)을 다시 전수 확인, 새로 생긴 줄은 H 행 주석·D-40·D-41 뿐이고 오귀속 0. D-40 '운영자 승인(… B=1)의 범위에서 이 계획이 구체화한 결정 — 별칭표의 모양은 해당 단계에서 확정', D-41 '운영자가 이슈 후보와 출처 주소를 입력하거나 CSV 로 넣으면…(H=1 의 승인된 기본값)·운영자 승인(… H=1)의 범위' — 둘 다 R-131 초안의 B·H 기본값과 같고 칸 모양·별칭표는 '해당 단계에서 확정' 으로 해석임을 밝힘 |
| ⑹ 400줄·`src`·기존 시험·숨은 글자 | 계획 396줄(한도 400 이내). 기준선 대비 누적 6파일(`CHANGELOG` +1/−0·`DECISIONS` +6/−0·계획 +396·시험 245/338/449줄 모두 새 파일), `src/`·`scripts/`·`vendor/`·`.github/`·`VERSION` 0줄, 기존 시험 변경 0, `git diff --check` 0(누적·델타), BOM·보이지 않는 글자·탭·줄끝 공백 0·전부 LF, 새 비ASCII 는 `· — → ①~⑦ ⊂ ≠ § × ↔` 뿐. 전략 문서 12자 겹침은 델타 전과 같은 39곳(새 겹침 0), 18자 이상은 표 틀 4곳. 병합 충돌은 N1 머리 `82ef399`·`2cc6b5a` 와 `CHANGELOG.md`·`docs/DECISIONS.md` 두 곳뿐 |
| ⑺ 새 부작용 | 낮음 1~4 외에 발견하지 못했다. 확인한 것: `ast` 시험의 `function_named` 는 함수가 하나가 아니면 단언해 `render`·`_sync_overlays` 이름이 바뀌면 시끄럽게 깨진다(안전, P4 가 어차피 고침) · 화면 시험의 `today=TODAY` 로 시험이 날짜에 안 기댄다 · `LegacyDemandLabelTest` 의 '상대값만 보는' 좁힘으로도 N01~N07 이 모두 잡히고 `d_trend` 개명(P05)은 안 깨진다 · D-36 의 `content` 순수 부품 허용이 `content.store` 를 막은 채 P1 지시와 맞는다 · CHANGELOG 의 `D-36~D-41`·계획 머리의 `D-36~D-41` 이 결정 행과 맞는다 |

## 2. 1차 최종 보고의 중간 2건 — 해소 확인
- **M1(연결 인용)**: ③·⑥ 의 N1 뒤 문장·줄 번호는 `82ef399`·`3b0194f` 두 머리에서 모두 정확하다. 남은 것은 7절 머리 문장(낮음 1)뿐.
- **M2(Qt 글자 훑기 시험)**: `ast` 기반으로 바뀐 뒤 헐렁함(V85)·깨지기 쉬움(V86·V87)이 모두 사라졌다. 남은 허점은 억지 변이 P10 하나(낮음 3).

## 3. 시험 줄 — 실제 `Ran N tests … OK` (한 번에 한 모듈씩, 이 PC)
```text
[D2-3.12] py3.12.10 test_topic_protect_ui: Ran 31 tests in 0.822s OK
[D2-3.12] py3.12.10 test_topic_protect_suggest: Ran 26 tests in 3.187s OK
[D2-3.12] py3.12.10 test_topic_protect_candidates: Ran 19 tests in 0.084s OK
[D2-3.12] py3.12.10 test_repo_layout: Ran 26 tests in 3.469s OK
[D2-3.12] py3.12.10 test_content_model: Ran 34 tests in 0.013s OK
[D2-3.10] py3.10.11 test_topic_protect_ui: Ran 31 tests in 0.746s OK
[D2-3.10] py3.10.11 test_topic_protect_suggest: Ran 26 tests in 3.355s OK
[D2-3.10] py3.10.11 test_topic_protect_candidates: Ran 19 tests in 0.080s OK
[D2-3.10] py3.10.11 test_repo_layout: Ran 26 tests in 2.839s OK
[D2-3.10] py3.10.11 test_content_model: Ran 34 tests in 0.015s OK
N1 머리 82ef399 트리 위(새 3모듈):
[N1m-3.12] py3.12.10 test_topic_protect_ui: Ran 31 tests in 0.765s OK
[N1m-3.12] py3.12.10 test_topic_protect_suggest: Ran 26 tests in 3.318s OK
[N1m-3.12] py3.12.10 test_topic_protect_candidates: Ran 19 tests in 0.080s OK
[N1m-3.10] py3.10.11 test_topic_protect_ui: Ran 31 tests in 0.756s OK
[N1m-3.10] py3.10.11 test_topic_protect_suggest: Ran 26 tests in 3.293s OK
[N1m-3.10] py3.10.11 test_topic_protect_candidates: Ran 19 tests in 0.073s OK
해시 시드 7 + 임시 폴더 누수 확인(3.12):
[D2REP-seed7] py3.12.10 test_topic_protect_ui: Ran 31 tests in 0.801s OK
[D2REP-seed7] py3.12.10 test_topic_protect_suggest: Ran 26 tests in 3.174s OK
[D2REP-seed7] py3.12.10 test_topic_protect_candidates: Ran 19 tests in 0.079s OK
temp leftovers: 0 []
```
총 31+26+19 = **76개** 모두 통과. 이 델타에서는 PySide6 설치 3.12 와 기준선 `3b1294b` 소스 위 실행을 다시 하지 않았다(앞 커밋에서 통과, 델타가 `src/` 를 안 바꿔 의미가 같다).

## 4. 변이 결과 (새로 설계한 110곳, `23ca08e` 복사본에서 한 곳씩, 3.12)
- 동작을 깨뜨린 **97곳 중 새 시험이 90곳을 잡았다.** 놓친 7곳(V37·V38·V42·V45·V46·V50·V81)은 **모두 기존 시험이 대신 잡는다**(1차에는 V11·V30·V34 가 모든 시험을 통과했으나 이번에 새 시험이 잡는다). **모든 시험이 놓치는 변이는 0곳.**
- 동작이 같은 정리 6곳(V86·V87·P01·P02·P05·P07)은 **모두 통과(오경보 0)**, 동작은 바뀌었는데 글자만 남긴 V85 는 **잡힘**, 억지 변이 P10 은 통과(낮음 3).
- '결함 고치기' 5곳(F01 그래픽카드·카드뮴만 제외·F02 자료 쪽 수정·F03 제외 후보 상태·F04 정확 일치(과격)·N07 새 Trend 라벨 키)은 KNOWN_DEFECT·'아직 없음' 시험이 의도대로 깨진다. 라벨 변이 N01~N06 과 V31·V32 는 모두 잡힌다.
- 도구: `W\ver_p0_x\tools\mutations.py`(변이 목록)·`mutate.py`·결과 `mut_resultsP1.json`·`mut_resultsP2.json`.

## 5. 못 확인한 것
- GitHub·CI 네 칸(Windows·Ubuntu × 3.10·3.12), `origin/main` 이 마지막 fetch(20:02) 이후 움직였는지 — push·네트워크 금지로 못 봤다. 전체 `discover` 시험도 돌리지 않았다(지시).
- 구현자 변이 67곳 중 앞의 52곳(M01~M52)은 재현하지 않았다(M53~M67·라벨 변이만).
- N1 가지는 `82ef399`·`3b0194f`(둘 다 로컬 저장소 안의 객체)로 대조했고 GitHub 의 현재 상태는 보지 않았다. 병합 가지 `r135-p0-topic-protect-2` 는 열어 보지 않았다.
