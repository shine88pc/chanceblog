# 조사 보고 C — UI(PySide6)·시험·CI·문서·결정 기록 (5채널 주제 선정 전략 얹기)

조사 대상: 작업 사본 `…\scratchpad\cd_wt_ts` (main 3b1294b, `VERSION`=0.0.0). 읽기 전용. 전략 문서는 §14·§22·§23·§25·§27·§28·§29 를 중심으로 끝까지 읽었다. 근거는 `파일:줄`. **사실**은 코드·문서에서 직접 읽은 것, **추정**·**확인 못 함**은 따로 표시했다.

## 0. 요약 10줄

1. 화면은 **홈 하나만 실제로 만들어져 있다.** 메뉴 6개 중 `주제 후보`(topics)를 포함한 5개는 '아직 만들고 있어요' 자리표시 화면이다(`ui/qt/shell.py:162`, `ui/core/app_state.py:312-315`). 전략 §28 의 '채널별 5개 + 전체 후보 보기'는 이미 있는 빈 자리 `주제 후보` 에 넣는 것이 자연스럽고, 메뉴를 늘릴 필요가 없다(메뉴 6개 상한은 시험이 못박음 `tests/test_ui_core.py:593`).
2. 화면 구조는 **뷰모델(순수 파이썬 `AppState`) → Qt 가 그리기만** 이라서 주제 엔진을 UI 와 분리하려는 원칙과 맞는다. 다만 **데이터 공급자 인터페이스가 홈 전용 하나(`HomeProvider.load_home`)** 이고, 불러오기 작업 키·시그널 다리(`JobBridge`)·`apply_home` 도 홈 하나에 묶여 있어 두 번째 화면용으로 일반화가 필요하다.
3. 화면 계층은 **읽기 전용 원칙**(보관함을 만들거나 바꾸지 않음, `ui/adapters.py:1`·`ui/launcher.py:3`)이다. 후보 생성·보류·재평가는 쓰기라서 새 쓰기 어댑터와 새 시험 틀이 필요하고, D-32 의 '읽기만' 문구를 새 결정 행으로 덮어야 한다.
4. **글자 규칙과 정면충돌하는 곳**: 현재 화면의 `월 검색량`·`월간 검색량`(회 단위, `ui/core/text.py:28,39,74-75`)은 전략 §23.3·§23.5(상대 지표이며 월간 검색량으로 표시 금지)와 맞지 않는다. 서랍 항목 이름이 시험으로 못박혀 있어(`tests/test_ui_core.py:720`) 의식적으로 같이 고쳐야 한다. 또 화면 글에 `보장`이 한 글자라도 들어가면 시험이 실패한다(`text.py:67` — '보장 안 함' 같은 면책 문구도 화면에는 못 쓴다).
5. 점수 체계가 **둘**이다: 현재 `작성 우선도`(D-29: 프로필 적합도 30·시기 20·신선도 20·균형 15·기회도 15, 높음/보통/낮음 = 70/40 구간, `ui/adapters.py:46-50`)와 전략 §13·§14(채널별 6항목 가중치, 80/65/50 구간). 어느 쪽이 화면의 `작성 우선도`가 되는지 새 결정(D-35 이후)이 필요하고, 현재 상수는 시험이 값을 못박고 있다(D-29 ①, `tests/test_suggest_score.py` 29개).
6. **CI 는 Qt 를 검증하지 않는다**: `ci.yml` 은 PySide6 를 설치하지 않아 `tests/test_ui_qt.py`(80)·`test_ui_qt_images.py`(10)·`test_ui_qt_scale.py`(1) = 91개가 CI 에서 건너뛰어진다(`tests/test_ui_qt.py:70`, `docs/ARCHITECTURE.md:91`). 새 화면의 시험은 '순수 뷰모델(CI 에서 돎)'과 'Qt(내 PC 에서만)'로 나눠 쓰고, 핵심 규칙은 앞쪽에 두어야 한다. CI 에 Qt 칸을 넣는 일은 `ci.yml` 변경이라 T2(독립 검증)다.
7. 시험은 `grep -c 'def test_'` 합계로 **약 3,690개**(파일 92개 = 시험 파일 85 + 헬퍼 7). 후보(490)·제안(282)·초안(314)·서비스(916)·claims 계열(488)은 두껍고, **5채널 일반화·채널별 상위 5개·Topic Cluster 상한·보류 90일·캘린더·화면 5채널 칩**은 보호할 기존 시험이 거의 없다(새로 쓰는 영역). 반대로 `BLOG_KEYS`(naver_a·b 둘뿐)·`HOME_CHIPS` 같은 현행 동작은 특성 시험을 먼저 더해야 한다.
8. 문서 갱신 의무는 시험으로 지켜진다: 문서가 부르는 `D-nn` 이 DECISIONS 에 있어야 하고(`tests/test_repo_layout.py:93`), `VERSION` 이 CHANGELOG 맨 위 제목과 같아야 하며(`:127-129`), 오류 코드 표(TROUBLESHOOTING)와 `errors/catalog.py` 가 같아야 한다(`scripts/sync_errors.py`). 다음 결정 번호는 **D-35**.
9. 진입점: 화면은 `__main__.py:5-9` 가 `gui` 만 가로채 `ui/launcher.py:54-71`; 명령줄은 `service/cli.py:857-864` 의 `add(name, handler, help)` 와 묶음 하위 명령 패턴(`:567` draft·`:593` candidates·`:784` keys). 새 화면은 `NAV`(`app_state.py:17`)에 이미 있는 `topics` 키를 쓰고 `shell.py:162,204` 의 `if state.page == "home"` 두 곳을 화면 표로 바꿔야 한다.
10. 가장 큰 결정 필요 항목: ① 점수 체계 통합 ② '월 검색량' 표기 → 상대 관심도로 교체 ③ 자동 실행 주기(§27)는 AGENTS 절대 규칙 7·D-09('앱의 감시·예약 작업은 첫 버전에 넣지 않는다')와 부딪힘 → 첫 버전은 **손으로 누르는 `주제 분석 시작`**(이미 빈 화면에 그 단추 자리가 있음 `text.py:45`)이 기본값 후보 ④ 홈의 5행/칩 5개 고정 구조와 '채널별 5개'의 관계.

---

## 1. UI 구조 (PySide6)

### 1.1 파일 지도와 줄 수

| 층 | 파일(줄 수) | 하는 일 |
|---|---|---|
| 값 | `ui/core/tokens.py`(150) | 색·글자 색 5개·글자 모양·크기·메뉴 높이 등 모든 값. 화면 코드에 `#RRGGBB` 금지(시험) |
| 글 | `ui/core/text.py`(87) | 화면 문구 표 `T`, `NO_DATA`("데이터 없음"), `FORBIDDEN`(`:67`), 숫자 서식 |
| 뷰모델 | `ui/core/app_state.py`(332) | `AppState`·`NAV`·`topic_vm`·`home_view`·`drawer_view`·오류 가리기 함수. PySide6 모름 |
| 서비스 모양 | `ui/core/services.py`(143) | `Topic`·`BlogInfo`·`HomeData` 자료, `HomeProvider`, `FakeHomeProvider`(시나리오 5가지, `:128-143`) |
| 작업 | `ui/core/jobs.py`(140) | `Job`·`JobRunner`(이름 하나에 작업 하나, 협조적 취소, 실패해도 입력 보존) |
| 그 밖 core | `icons.py`(87)·`notify.py`(34, 토스트 3.5초 규칙)·`attribution.py`(83, Unsplash 출처 두 줄)·`imagerules.py`(79, 내 사진 규칙) | 이번 조사에는 직접 영향이 작음 |
| 어댑터 | `ui/adapters.py`(115) | `ServiceHomeProvider` — `service.candidates.list_candidates` 를 읽기 전용으로 `Topic` 으로 바꿈 |
| 진입 | `ui/launcher.py`(71) | `gui [--data-dir] [--sample]`, PySide6 없으면 한국어 안내 후 종료 코드 1 |
| Qt | `qt/theme.py`(241)·`components.py`(910)·`screens.py`(329)·`shell.py`(403)·`workers.py`(20)·`app.py`(44)·`imagecheck.py`(64) | 스타일시트·부품·화면 조립·앱 틀·시그널 다리 |

### 1.2 지금 있는 화면·메뉴 (사실)

| 메뉴(`NAV` `app_state.py:17-18`) | 상태 | 근거 |
|---|---|---|
| 홈(home) | **구현** — 인사·요약 카드 4·`맞춤 주제 추천`(칩 5 + 행 5)·오른쪽 패널(내 블로그 현황·빠른 작업 4·활용 팁) | `screens.py:135-156` |
| 주제 후보(topics) | **자리표시**('이 화면은 아직 만들고 있어요' + `홈으로`) | `screens.py:272-281`, `text.py:50` |
| 초안 작성(draft)·발행 기록(history)·블로그 관리(blogs)·설정(settings) | 자리표시 | 같음 |
| 위 막대 | 로고·앱 이름·설정 아이콘 하나뿐 | `shell.py:93-106` |

'주제 후보' 화면이 이미 **연결 고리**를 갖고 있다: 홈의 `전체 보기` 링크(`screens.py:165-167`)와 요약 카드 `추천 주제`·`저장된 아이디어`의 `go="topics"`(`app_state.py:248,251`)가 모두 `topics` 로 간다. 즉 §28 의 `전체 후보 보기`의 도착지가 이미 정해져 있다.

홈이 지금 보여 주는 것(= 전략 §28 기본 화면과 가장 가까운 것):

| 홈의 요소 | 내용 | 근거 |
|---|---|---|
| 필터 칩 5 | 전체·블로그 A·블로그 B·트렌드 급상승·신규 키워드 | `app_state.py:21` |
| 추천 행 5 | `HOME_ROWS = 5`(채널별이 아니라 **칩으로 거른 전체에서 5개**), 선택 행만 큰 주 단추 | `app_state.py:22,255`, `components.py:524-528` |
| 블로그 배지 | `블로그 A`·`블로그 B` 둘만(색+글자) | `app_state.py:24`, `components.py:224-226`, `tokens.py:36` |
| 정렬 | 우선도(높음<보통<낮음) → 최신 날짜, 보류(hold)는 제외 | `app_state.py:196-200`, `services.py:16` |

### 1.3 데이터가 화면에 오는 길 (서비스 → 어댑터 → 상태 → 위젯)

```text
launcher.py:70  provider = FakeHomeProvider(delay=.3) (--sample) | ServiceHomeProvider(data_dir)
 → qt/app.py:38-44 run() → AppShell(provider) (shell.py:39-41: AppState(provider))
 → 시작 때 QTimer.singleShot(0, reload) (shell.py:79-80) → AppState.start_load (app_state.py:150-157)
 → JobRunner.start(LOAD_KEY="home-load", provider.load_home, 콜백)  [작업 스레드, jobs.py:111-119]
      adapters.py:99-115 load_home: list_candidates(ctx) → _projects(완료·발행 수) → _names(프로필 이름) → to_topic(...) → HomeData
 → JobBridge 시그널 loaded/failed/cancelled (workers.py:7-20) → [화면 스레드] shell._on_loaded → _guarded → apply_home (app_state.py:168-174)
 → render() (shell.py:156-181): 화면 통째로 다시 만든 뒤 옛 화면은 deleteLater, 포커스(focus_key)·스크롤 위치 보존
 → home_view() (app_state.py:235-285) 딕셔너리 → screens.home_screen → components 부품
```

일반화가 필요한 고정점(전부 **사실**, 새 화면을 얹을 때 부딪힌다):

| 고정점 | 위치 | 영향 |
|---|---|---|
| `AppState` 가 공급자 **하나**(`provider`)와 `load_home` 하나만 안다 | `app_state.py:121-122,152` | 후보 화면용 `load_topics` 같은 두 번째 진입점 또는 공급자 확장 필요 |
| 작업 키가 `LOAD_KEY="home-load"` 하나 | `app_state.py:23,148` | 후보 분석(쓰기)은 별도 키, 홈 새로고침과 서로 막지 않게 |
| `JobBridge` 시그널이 홈 전용(`loaded→apply_home`) | `workers.py:7-20`, `shell.py:72-75,358-377` | 결과에 종류 표를 붙이거나 다리 하나 더 |
| `render()` 가 `state.page == "home"` 이면 홈, 아니면 자리표시 | `shell.py:162` | 화면 표(`{"home": …, "topics": …}`)로 바꿔야 함 |
| 서랍은 홈에서만 `state.page == "home"` | `shell.py:204` | 주제 후보 화면에서도 서랍(후보 상세)을 쓰려면 조건 변경 |
| `nav()` 가 화면을 옮기면 서랍 상태를 지움 | `app_state.py:138-143` | 서랍 안에서 화면 이동하지 않으므로 문제 없음(참고) |
| 읽기 전용 원칙 | `adapters.py:1-3`, `launcher.py:3`, D-32 | 후보 생성·보류는 쓰기 → 별도 쓰기 어댑터·확인 흐름 |
| 화면 전체를 매번 새로 만듦 | `shell.py:163-176` | 후보 10만 개에서 `home_view()` 0.52초(`UI_DESIGN_SPEC.md:106`) — 전체 후보 목록은 쪽 나누기·가상화 필요 |

### 1.4 백그라운드 작업(jobs/workers)

| 규칙 | 사실 근거 |
|---|---|
| 작업은 `threading.Thread(daemon=True)`, 같은 key 가 돌면 `None`(중복 클릭 거절) | `jobs.py:53-60,111-119` |
| 취소는 협조적(`cancelled()`), 취소했으면 늦게 온 결과도 버림, 화면은 취소 즉시 복귀 | `jobs.py:62-63,97-101`, `shell.py:349-355` |
| 어떤 예외도 쉬운 안내(`job_failed`)+예외 이름만, 입력(payload) 보존 | `jobs.py:88-101` |
| 어댑터는 단계 사이에만 취소 확인(한 서비스 호출이 도는 동안은 끊지 못함) | `adapters.py:105-112` |
| 창 닫기: 창을 먼저 숨기고 작업 취소 후 최대 1초 대기 | `shell.py:399-403` |

→ 후보 분석(네트워크 Search Trend 호출·AI 다듬기 포함 가능)은 같은 `JobRunner` 에 **다른 key** 로 얹는 것이 기존 시험 틀(`tests/test_ui_core.py:427-564` 작업 시험 13개)과 맞다. 단, 네트워크·키·한도 계층은 이미 `service/quota.py`·`service/connections.py` 에 있다(다른 조사원 담당).

### 1.5 헤드리스(offscreen) 시험 방법 (사실)

| 항목 | 내용 | 근거 |
|---|---|---|
| 환경 | `QT_QPA_PLATFORM=offscreen` + 윈도 글꼴 폴더 + 시스템 글꼴 대신 건네기 | `scripts/ui_offscreen.py:1-13`, `tests/test_ui_qt.py:29-33,74` |
| 건너뛰기 | `HAVE = importlib.util.find_spec("PySide6") is not None` → `@unittest.skipUnless(HAVE, …)` | `tests/test_ui_qt.py:29,70` |
| 도우미 | `settle`(이벤트 처리)·`wait_until`(조건 대기)·`find_clipping`(글자 잘림 검사)·`install_system_fonts` | `test_ui_qt.py:88,98,212` |
| 사진·성능 | `scripts/ui_capture.py`(환경별 사진)·`ui_bench.py`(성능)·`ui_image_check.py` | `docs/ARCHITECTURE.md` §5.1 마지막 항목 |
| 순수 부분 | `ui/core`·`adapters`·`launcher` 는 PySide6 를 모듈 수준에서 불러오지 않음(시험이 소스 훑음) → CI 에서도 돔 | `tests/test_ui_core.py:1095-1109` |

### 1.6 재사용할 부품 / 새로 필요한 부품

| 필요 | 재사용 가능 부품 | 판단 |
|---|---|---|
| 채널 구분 탭(5채널) | `FilterChip`·`chip_flow`(`components.py:191`, `screens.py:125`) — 켜짐 상태가 있는 칩, 폭 좁으면 줄바꿈(`FlowLayout`) | **재사용**. 5개 칩은 폭 문제 없음. 채널 라벨은 `블로그 A·B` 에서 5채널 이름으로 확장 필요 |
| 후보 한 줄(카드) | `TopicRow`(`components.py:474-542`) | **부분 재사용**. 행에 `작성 우선도`·`중복`·`협업 가능 유형`이 안 보임(우선도는 접근 이름과 서랍 배지에만 있음 `app_state.py:116`, `screens.py:302`). 행의 지표 칸 3개(월 검색량·문서 수·추세)는 교체 대상 |
| 추천 채널 배지 | `Badge`(`:214` 종류 a·b·ok·info·muted)·`BlogBadge`(`:224`) | **확장 필요**: 색 토큰이 블로그 A·B 둘뿐(`tokens.py:36`). 나머지 3채널은 중립 `info` 배지(글자 포함)가 안전하고 새 색 토큰은 운영자 승인 대상(T3 '톤'에 가까움 — 추정) |
| 후보 상태(우선 추천·일반·보류·제외·데이터 부족) | `Badge("ok/info/muted")` | 재사용 가능(색만으로 구분하지 않고 글자 병기 규칙 `UI_DESIGN_SPEC.md:83`) |
| 상세 패널(점수 구성·Seed 출처 등 10항목) | `Drawer`(`:796`)+`drawer_content` 의 `필드 표`(`screens.py:309-317`) | **재사용**: `fields` 목록(label/value)만 늘리면 됨. 점수 구성 막대는 새 부품 후보(없어도 6줄 label/value 로 시작 가능) |
| 빈 상태·'기준 충족 3개' 안내 | `StateCard`(`:679`)·`Banner`(`:703`) | **재사용** (문구는 `text.py` 에 새로) |
| 접이식(고급·진단) | `Disclosure`(`:645`) — 글자 하나만 담는 구조 | 제한적. 위젯을 담는 접이식은 새로 필요할 수 있음 |
| 전체 후보 목록(표/긴 목록) | **표·목록 부품 없음**(부품 목록에 표 위젯 없음) | **새 부품 필요**. 부품은 `components.py` 한 곳에서만 만들게 시험이 막음(`tests/test_ui_qt.py:1329` 정규식은 QPushButton·QLabel·QLineEdit·QCheckBox 등 10종 직접 생성 금지) |
| 쪽 나누기·성능 | 없음 | 새로 (§1.3 마지막 줄) |
| 오른쪽 패널(블로그 현황) | `ResponsiveBody`·`FlowGrid`(`screens.py:25,62`) | 홈 전용 틀. 주제 후보 화면에서는 선택 사항 |
| 로딩·오류·오프라인·일부만 | `Skeleton`·`StateCard`·`Banner`·진단 정보 | **그대로** — 여섯 상태 규칙(`UI_STATES.md`)이 이미 있다 |
| 단추 | `Button(kind, …)`·`IconButton` | 그대로. 아직 안 되는 기능은 `notify_soon` 토스트 관례(`shell.py:293`) |

새로 만들 때 규칙(`UI_COMPONENTS.md:42-44`): ① 값은 `tokens.py` 키 ② 접근 이름·키보드·포커스 링 ③ `components.py` 한 곳 ④ 시험(접근 이름·36px·직접 색 없음은 자동으로 훑음) ⑤ `UI_COMPONENTS.md` 표에 한 줄.

---

## 2. UI 설계 규칙과 전략 §28 이 부딪히는 곳

### 2.1 새 화면에 영향을 주는 규칙 (읽은 문서: UI_DESIGN_SPEC·UI_COMPONENTS·UI_STATES)

| 규칙 | 근거 | 시험으로 못박힘 |
|---|---|---|
| 사이드바 메뉴 **6개 이하**, 이름·순서(홈·주제 후보·초안 작성·발행 기록·블로그 관리·설정) | `UI_DESIGN_SPEC.md:54`, `app_state.py:17-19` | `test_ui_core.py:593` |
| 홈 구성 고정: 요약 카드 4·칩 5·추천 행 5, 첫 행 선택 | `UI_DESIGN_SPEC.md:62` | `test_ui_core.py:602` |
| 화면은 **부품만** 쓰고 Qt 기본 위젯·`setStyleSheet`·색 직접 지정 금지 | `UI_COMPONENTS.md:3` | `test_ui_qt.py:1329-1340` |
| 값(색·글꼴 이름·배율)은 토큰에만, 순수 검정 금지 | `UI_DESIGN_SPEC.md:11-23` | `test_ui_core.py:64-95` |
| 내부 값(번호·영문 상태 코드·경로·원문 응답·오류 코드)은 기본 화면에 내지 않음. 오류 코드는 접어 둔 진단 정보에만 | `UI_DESIGN_SPEC.md:7`, `UI_STATES.md:3` | `test_ui_core.py:791`(뷰모델에 내부 번호·영문 상태 코드 없음) |
| **결과 약속 표현 금지**: `상위노출`·`노출 확률`·`검색 1위`·`수익 보장`·`수익보장`·`보장` | `text.py:2,67` | `test_ui_core.py:216-221`, `test_ui_qt.py:1010` — 모든 문구에 대어 봄 |
| 가져올 수 없는 값은 지어내지 않고 `데이터 없음`/`–` | `text.py:8`, `UI_STATES.md:18` | `test_ui_core.py:633` |
| 화면 여섯 상태(loading·normal·empty·error·partial·offline) 규칙 | `UI_STATES.md:5-14` | `test_ui_core.py:583` |
| 눌러도 아무 일 없는 단추 금지 — 없는 기능은 '다음 단계에서 열려요' 토스트만 | `UI_DESIGN_SPEC.md:58`, `UI_COMPONENTS.md:48` | `test_ui_core.py:769` |
| 기능 없는 장식(전역 검색·알림·사용자 메뉴) 금지 | `UI_DESIGN_SPEC.md:58,89` | — |
| 누르는 칸 36px 이상, Tab 한 바퀴·Enter/Space·포커스 링·접근 이름 필수 | `UI_COMPONENTS.md:36-40` | 모든 단추를 자동으로 훑음 |
| 가로 스크롤 없음 — 좁으면 배치를 바꿈(칸 4→2→1, 패널 옆→아래) | `UI_DESIGN_SPEC.md:56` | `test_ui_qt.py:160,212` |
| 입력한 글·외부 글은 화면에 나가기 전 **가리기 → 자르기** 순서 | `adapters.py:7-9`, `app_state.py:34-37` | `test_ui_core.py:998-1022` |
| 화면이 문서와 일치: 몇 가지 문장을 시험이 문서에서 찾음 | — | `test_ui_core.py:1054,1073,1080,1090` |

찾지 못한 것(**확인 못 함**): '주요 버튼 수' 상한을 직접 정한 문장은 읽은 세 문서에 없다. 관례는 '선택된 행에만 큰 주 단추 1개, 나머지는 작은 보조 단추'(`UI_DESIGN_SPEC.md:62`). `UI_VISUAL_QA.md`·`UI_ICONS.md`·`UI_IMAGES.md` 는 읽지 않았다(아이콘 새로 쓰면 `test_ui_core.py:181-210` 이 SVG 규격·사용 이름 존재를 검사한다는 것만 시험 이름으로 확인).

### 2.2 전략 §28·§22·§29 와 현 화면의 대조

| 전략 요구 | 현재 | 갭·충돌 |
|---|---|---|
| 후보 카드: 추천 포스팅 주제 | 행 제목(`vm["title"]`, `body_lg`) | 맞음. §26(후보 주제와 발행 제목 분리)도 화면에선 '주제 문장'만 보이므로 문제 없음 |
| 핵심 키워드 | `KeywordChip` 3개 | 맞음 |
| 추천 채널 | 블로그 배지(A·B만) | **5채널 확장 필요**(`BLOG_NAMES` `app_state.py:24`, `BLOG_KEYS` `adapters.py:31`) |
| 작성 우선도 | 행에는 안 보이고 접근 이름·서랍 배지에만(높음/보통/낮음) | **행에 보이게 + 점수 체계 통합 결정** (§0-5) |
| 최근 관심도 또는 `데이터 부족` | 추세(상승·보통·하락)+없으면 `데이터 없음`; 지표 칸 `월 검색량`(회) | **표기 충돌** — Search Trend 는 실제 검색 횟수가 아니고(§23.3) `월간 검색량 표시` 금지(§23.5). `T["demand"]`·`d_demand`·`tip_demand`·`fmt_demand` 를 '최근 관심도(상대값)' 계열로 바꿔야 함. 또 `데이터 부족`(전략 용어)과 `데이터 없음`(`NO_DATA`)은 말이 다름 → 하나로 정해야 함 |
| 추천 이유 | 서랍에만(`d_reason`), 행은 `desc` 한 줄 | 맞음(§28 은 카드 기본 정보에 '추천 이유' 포함 → 행의 한 줄 설명을 `selection_reasons` 요약으로 채우면 해결) |
| 중복 여부 | 서랍 `기존 작성 여부`(예/아니오/없음) 하나 | 전략 §17 은 4단계(다른 주제·유사 요소·다른 관점 필요·중복/업데이트 후보) → **새 필드·새 문구** |
| 협업 가능 유형 | 없음 | **새 배지**. 문구는 `협업 가능`형(§22.1 목록)이고 `보장` 글자를 피해야 함 |
| 후보 상세 10항목(점수 구성·Seed 출처·검색 의도·Topic Cluster·Topic Angle·기존 유사 글·작성 가능성·계절 일정·Trend 상태·협업 태그) | 서랍 8항목(월간 검색량·PC·모바일 비중·관련 검색 결과 수·최근 트렌드·계절성·기존 작성 여부·보조 키워드·데이터 조회일 — 이 목록이 시험으로 고정 `test_ui_core.py:720`) | 계절성≈계절 일정, 최근 트렌드≈Trend 상태, 기존 작성 여부≈중복의 일부 말고는 새로 필요. **기존 시험을 의식적으로 고쳐야 함** |
| 채널별 우수 후보 5개 기본 화면 + 같은 Topic Cluster 최대 2 + 80점 부족 시 65~79 보충 + 50~64 강제 보충 없음 + `기준 충족 N개` 문구 | 홈 5행은 **칩으로 거른 전체 기준 5개**(`app_state.py:255`), 클러스터·보충·부족 문구 없음 | 규칙은 **엔진(`content/`+`service/`)이나 `AppState` 에** 두어야 한다 — `screens.py` 는 거르거나 정하는 일을 못 한다(`screens.py:2`, 시험이 지킴). 현 홈의 5행 고정 시험과의 관계는 결정 필요 |
| `전체 후보 보기`(일반·보류·지역/방문·협찬 가능·데이터 부족) | 홈 `전체 보기` → `topics` 자리표시 | 칩 5개(일반·보류·지역·협찬·데이터 부족)로 `FilterChip` 재사용 가능, 목록 부품·쪽 나누기 새로 |
| 협업 가능 유형 표시 시 **표시하지 않는 정보**(예상 수익·협찬 성사 확률·상위노출 확률·수익 보장) | `FORBIDDEN` 시험이 이미 막음 | 일치 — 화면 글에서 이 표현을 안 쓰면 되고, '표시하지 않음'을 화면에 **설명하는** 문장도 `보장`/`상위노출`/`노출 확률` 때문에 못 쓴다(문서에만) |
| 영문 용어(Seed·Topic Cluster·Topic Angle) | 화면에는 한국어(`씨앗`은 D-29 가 이미 씀) | `test_ui_core.py:216-221` 이 '영문 코드 없음'을 본다고 이름은 말하지만 **본문은 읽지 못함(확인 못 함)** → 화면에는 `씨앗`·`주제 묶음`·`관점` 같은 한글 용어가 안전 |
| 건강 주제 `건강 정보 확인 필요`(§21) | 없음 | 새 문구·배지 (엔진 쪽 규칙과 함께) |
| 후보 데이터 모델 `status: recommended`·`trend_status: rising` 등 영문 코드 | 뷰모델은 영문 상태 코드를 담으면 안 됨 | 뷰모델 단계에서 한국어 라벨로 바꾸는 표가 필요(`STATUS_LABEL` `app_state.py:25` 가 선례) |

---

## 3. 시험

### 3.1 영역별 시험 개수 (`grep -c "def test_"` 합, 실제 실행 수와 약간 다를 수 있음 — 상속·부분 시험 미반영)

| 영역 | 파일(개수) | 합계 |
|---|---|---|
| 후보(모델·저장·CSV·서비스·명령줄) | content_candidates(121)·content_candidates_store(88)·content_candidates_batch(15)·candidate_csv(67)·service_candidates(121)·service_candidates_cli(60)·service_candidates_process(18) | **490** |
| 제안(프로필로 먼저 제안·점수·글 낱말) | suggest(113)·suggest_assess(22)·suggest_data(12)·suggest_score(29)·suggest_text(16)·service_suggestions(47)·service_suggest_cli(36)·service_suggest_process(7) | **282** |
| 프로필(네이버 A·B) | check_profile_options(23)·naver_profile_cli(28)·naver_profile_options(20)·naver_profiles(16) | **87** |
| 초안(작성 기반·글 유형·옵션) | content_draft_plan(126)·content_draft_options(79)·content_post_types(37)·service_draft(49)·service_draft_process(10)·service_draft_token(13) | **314** |
| 보관함(저장·모델·마이그레이션) | content_store(70)·content_model(34)·content_migration(69)·content_unc_uri(12) | **185** |
| 렌더(네이버·Markdown) | render_naver(52)·render_markdown(38) | **90** |
| 검사 'check' 계열(claims·유사도·정확도 c2) | check_claims(34)·accuracy(40)·disguise(15)·mutants(47)·regression(42)·similarity(36) + c2_fix_round(51)·c2_fix_round2(31)·c2_mutants_other(91)·c2_mutation_gaps(38)·c2b_pronoun_rule(63) | **488** |
| 서비스 층(위 제외) | service_cli(70)·cli_hardening(36)·connections(95)·doctor(45)·echo(24)·gate(25)·gate_hardening(39)·header_values(39)·keys_cli(37)·lock(41)·orphan(12)·pages_flow(66)·pages_git(11)·preview(15)·projects(31)·pushed_post(12)·quota(71)·quota_legacy_locale(3)·recovery(17)·repolock(57)·review(45)·safety(16)·unpushed(55)·workspace(35)·write_json(19) | **916** (그중 키·한도·연결 = connections 95+keys_cli 37+quota 71+3 = 206) |
| Pages 발행 | pages_repo(119)·pages_publish(99)·pages_deploy(30)·pages_render(30) | **278** |
| 보안 | security_keystore(86)·mask(50)·mask_boundary(17)·mask_sk(22)·shape(43) | **218** |
| UI | ui_core(94)·ui_qt(80)·ui_adapters(25)·ui_launcher(22)·ui_qt_images(10)·ui_qt_scale(1) | **232** (Qt 필요 91, CI 에서 건너뜀) |
| 문서·저장소 못박기 | repo_layout(26)·errors_catalog(37) | **63** |
| vendor | vendor_core(45) | 45 |
| **합계** | | **약 3,690** |

헬퍼 모듈(시험 0개): `service_support.py`(356)·`suggest_support.py`(89)·`claims_accuracy_examples.py`(676, 고정 예문)·`store_v1.py`·`store_crash_child.py`·`store_race_child.py`·`quota_race_child.py`. 고정 예시 폴더 `tests/fixtures/`(실제 Chance 글 영·한 두 편을 글자 단위로 되살림 — `ARCHITECTURE.md` §3).

### 3.2 시험 관례 (사실/추정 구분)

| 관례 | 근거 | 구분 |
|---|---|---|
| `unittest`(CI 실행 `python -m unittest discover -s tests -v`) | `ci.yml:47` | 사실 |
| **명세 못박기**: 상수·문구를 손으로 쓴 기댓값과 비교(예: 정렬 순서 `test_ui_core.py:727`, 서랍 항목 `:720`, 점수 가중치 D-29 ①) | `DECISIONS.md` D-29·D-33 | 사실 |
| **문서 ↔ 코드 일치 시험**(문서 문장을 찾아 코드와 맞는지) | `test_ui_core.py:1054,1073,1080,1090`, `test_repo_layout.py` 전체, `errors/catalog.py` ↔ TROUBLESHOOTING | 사실 |
| **소스 훑기 시험**(직접 색·글꼴·배율 곱셈·기본 위젯 생성·모듈 수준 PySide6 import 금지) | `test_ui_core.py:66-95,1095-1109`, `test_ui_qt.py:1329-1340` | 사실 |
| **변이(mutant) 시험**: 파일 이름에 mutants·mutation_gaps 가 있는 시험(`check_claims_mutants` 47·`c2_mutants_other` 91·`c2_mutation_gaps` 38) | 파일 이름·D-33 | **추정**(규칙 코드에 일부러 변형을 넣어 시험이 잡는지 보는 형식으로 보이나 본문은 읽지 못함). `scripts/` 에 변이 점검 전용 도구는 **없음**(6개 스크립트 확인) |
| **고정 예시 파일**: `claims_accuracy_examples.py`(예문 개발용·보류용 해시 홀짝 분리, D-33), `tests/fixtures/` | D-33, `ARCHITECTURE.md` §3 | 사실 |
| **네트워크 차단·가짜 공급자**: '시험은 네트워크·실제 시크릿 없이 돌아야 한다(가짜 공급자·가짜 클라이언트)' | `AGENTS.md:47` | 사실(규칙). 소켓을 막는 전용 훅은 못 찾음(**확인 못 함**) |
| **오프스크린 Qt**(`QT_QPA_PLATFORM=offscreen`) | `scripts/ui_offscreen.py` | 사실 |
| 가짜 시계·가짜 컨텍스트: `AppState(today=…)`, `make_context` 대체(`context_factory`) | `app_state.py:121-124`, `adapters.py:76-77` | 사실 |
| 여러 프로세스 시험: 다수 시험이 `subprocess` 사용(`service_support`·`suggest_support`·cli·draft_plan·migration·pages …) | `grep -ln subprocess` | 사실(느림의 한 원인 — 추정) |

### 3.3 건너뛰기·환경

| 항목 | 내용 | 근거 |
|---|---|---|
| PySide6 없음 | Qt 시험 클래스 전체 건너뛰기 | `test_ui_qt.py:29,70` |
| 파이썬 | 코드는 3.10 문법만 허용(`ast.parse(feature_version=(3,10))` 시험), CI 는 3.10·3.12 | `test_errors_catalog.py:338`, `ci.yml:34` |
| 운영체제별 건너뛰기 | `skipUnless/skipIf` 가 12개 파일에 있음(keystore 2·repolock 4·recovery 4·pages_repo 2 등) | `grep -c skip` — 개별 사유는 **읽지 못함** |
| 느린 시험 | 실행 시간은 **측정하지 않음(확인 못 함)**. CI 의 Windows 칸이 **14~15분**까지 늘었다고 기록, 한도 30분(`ci.yml:28-29`) | 사실(주석). 느린 모듈 후보(추정): 프로세스·git 을 쓰는 `pages_repo`(119)·`pages_publish`(99)·`service_repolock`(57)·`service_lock`(41)·`ui_qt`(80, 작업 스레드 대기 포함) |

### 3.4 보호가 얇은 곳 — 특성 시험을 먼저 더해야 할 곳

전략을 얹기 **전에** 현재 동작을 못박아 두면 안전한 자리(모두 '추가할 시험 제안'이며 기존 시험을 다 읽은 것은 아니다):

| # | 자리 | 왜 얇은가(사실 근거) | 추가할 특성 시험 |
|---|---|---|---|
| 1 | `to_topic` 변환·`priority_label` 70/40 경계·`BLOG_KEYS` | 어댑터 시험은 25개뿐(`test_ui_adapters.py`), 경계값·두 채널 외 후보 처리는 읽지 못함 | 경계 69/70·39/40, 알 수 없는 블로그 키 후보, `candidate.status` → STATUS 표 전부 |
| 2 | 홈 5행·칩 필터·정렬이 **후보 수·블로그 조합**에 따라 어떻게 변하는지 | 홈 시험은 예시 8개 데이터 중심(`services.py:89-106`) | 후보 0·1·5·6·50개, A만/B만/둘 다/없음, 같은 우선도 동률 정렬 |
| 3 | 서랍 항목 목록(8항목)·`d_*` 라벨 | 한 시험이 라벨 목록을 통째로 못박음(`test_ui_core.py:720`) → 항목을 늘리면 무조건 깨짐 | 항목 추가를 쉽게 하려면 '목록 못박기'를 '기존 8개는 같은 순서로 앞에 있다'로 나눠 두기(의식적 변경) |
| 4 | `Candidate` 모델 필드를 5채널·점수 6항목·Topic Cluster 로 확장할 때의 **옛 데이터 호환** | 마이그레이션 시험 69개가 있으나 후보 표 쪽 호환은 후보 조사원 영역 | 옛 후보 JSON 을 새 모델이 읽는지(`store_v1.py` 선례) |
| 5 | 점수 상수(D-29)·`suggest_score` | 값을 못박는 시험이 있어 **바꾸면 깨짐 = 보호는 두껍지만 교체 경로가 없음** | 새 점수 체계는 `suggest_score` 를 덮지 말고 **병렬 모듈**로 두고, 통합은 결정 뒤 한 묶음에서 |
| 6 | **Qt 화면 전체** | CI 에서 실행 안 됨(§0-6). 작업자 PC 에서만 | 주제 후보 화면의 규칙은 순수 뷰모델 시험으로(CI 가 돌림), Qt 시험은 얇게 |
| 7 | **읽기 전용** 보장 | 어댑터가 읽기만 한다는 시험 존재(내용은 읽지 못함 — **확인 못 함**) | 새 쓰기 어댑터가 홈 읽기 경로를 건드리지 않는다는 시험(홈 새로고침이 쓰기 어댑터를 부르지 않음) |
| 8 | 후보 분석 중 취소·중복 클릭·실패 입력 보존 | 일반 작업 시험(13개)은 있지만 홈 불러오기 한정 | 새 job key 로 같은 규칙 시험 복제(`test_ui_core.py:427-564` 형식) |
| 9 | 새 문구 전부 | `FORBIDDEN`·영문 코드 시험이 자동으로 훑음 | 새 문구를 `T` 표에만 넣으면 자동 보호(공짜). 표 밖 문자열(f-string)은 사각지대 |
| 10 | 5채널 데이터가 **없는** 채널(GitHub Pages·Blogger A/B)의 빈 상태 | 채널이 둘뿐인 가정이 코드에 박혀 있음(`app_state.py:24`, `adapters.py:114` 는 `("A","B")` 순회) | 개발 범위가 Naver A/B 이므로 '5채널 구조 + 2채널 사용'일 때 나머지 3채널이 화면에 안 나타난다는 시험 |

---

## 4. CI·빌드

| 항목 | 내용 | 근거 |
|---|---|---|
| 워크플로 | **하나뿐** `.github/workflows/ci.yml` — 이름 'CI — 시험'. 릴리스(설치 파일 빌드)는 따로(`docs/RELEASE.md`), 아직 없음 | `ci.yml:1,9` |
| 실행 시점 | 모든 브랜치 `push` + `workflow_dispatch`. **`pull_request` 없음**(D-28: PR 만들 때 13분 재실행 방지). 시험이 `on:` 두 줄을 못박음 | `ci.yml:12-14`, `tests/test_repo_layout.py:268` |
| 칸 | `ubuntu-latest`·`windows-latest` × 파이썬 `3.10`·`3.12` = **4칸**, `fail-fast: false` | `ci.yml:30-34` |
| 시간 | `timeout-minutes: 30`, Windows 칸이 14~15분까지 늘었음(2026-11-03). 병합 부탁은 네 칸 초록 확인 뒤에만(AGENTS.md:49) | `ci.yml:28-29` |
| 설치 | `actions/setup-python` 만. **`pip install` 단계 없음 → PySide6 없음**, 따라서 Qt 시험은 건너뜀 | `ci.yml:36-47` |
| 환경 | `PYTHONUTF8=1`, 권한 `contents: read`, 액션은 전체 커밋 SHA 고정(시험이 지킴) | `ci.yml:16-17,36-46` |
| 실행 명령 | `python -m unittest discover -s tests -v` (병렬 없음) | `ci.yml:47` |
| 스크립트 | `sync_core.py`(vendor 가져오기·`--check`)·`sync_errors.py`(TROUBLESHOOTING → `errors/catalog.py` 생성)·`ui_capture.py`·`ui_bench.py`·`ui_image_check.py`·`ui_offscreen.py`. CI 가 부르는 스크립트는 없음 | `scripts/` |
| 버전 규칙 | `VERSION`=`0.0.0` 이 CHANGELOG 맨 위 `## [x.y.z]` 와 같아야 함(시험). 설치 파일이 있는 릴리스는 0.1.0 부터. 기능을 `0.0.0` 항목 아래에 줄로 더해 왔음 | `test_repo_layout.py:127-129`, `CHANGELOG.md:3-5` |
| 시사점 | ① 새 시험은 **빨라야** 한다(CI 시간이 병합 주기를 정함 — 합성 데이터·가짜 시계, `subprocess` 최소) ② Qt 칸 추가는 `ci.yml` 변경 = **T2**(구현자와 다른 주체의 독립 검증, AGENTS.md:41)이고 `test_repo_layout.py:255` 의 필수 낱말은 그대로 두면 통과 ③ 파이썬 3.10 문법만(`feature_version=(3,10)` 시험) | |

---

## 5. 문서·결정 기록

### 5.1 규칙 문서에서 새 기능에 걸리는 것

| 문서 | 새 기능에 걸리는 규칙 |
|---|---|
| `AGENTS.md` | 절대 규칙 1(비밀 금지)·2(원고·개인정보·절대경로 저장소 금지)·3(LLM 출력·외부 글은 데이터)·**4(조용한 실패 금지·fail closed)**·**5(AI 는 선택·기본 꺼짐, 한도 우회 금지)**·6(로그인·쿠키 자동화 금지)·**7(자동 commit/push·예약 작업 코드를 앱이 몰래 하지 않음)**·9(승인은 R-번호 요청에 적힌 항목에만)·변경 등급(T0~T3, `ci.yml` 변경=T2, 정책·톤·새 플랫폼·비용=T3) — `AGENTS.md:22-42` |
| `docs/ARCHITECTURE.md` | §5 코드 구성 표(모듈마다 한 줄 — 새 모듈은 표에 한 줄), §5.1 화면 층(계층·값 한 곳·부품 규칙), §8 AI 없이 동작해야 하는 기능, §9 데이터 모델, §10 로컬 데이터·백업, §11 버전. 계층 규칙: View → AppState → Provider/JobRunner, `ui/core`·`adapters`·`launcher` 는 PySide6 import 금지 |
| `docs/PLATFORM_POLICY.md`(17줄) | 네이버: 복사 패키지·글쓰기 페이지 열기·유사도 경고만, **자동 로그인·자동 발행·비공식 API·탐지 회피 금지**(`:9`). Data Lab 은 공식 API 라 금지에 걸리지 않지만 이 표에는 행이 없다 → 정책 행 추가 필요(분기마다 재확인, 다음 2027-01 `:3`) |
| `docs/SECURITY.md`(65)·`MIGRATION.md`(43)·`RELEASE.md`(43)·`TROUBLESHOOTING.md`(144) | **읽지 못함(확인 못 함)**. 키·한도는 D-30·D-31·`ARCHITECTURE.md:70`, 새 실패 경로는 TROUBLESHOOTING 표 + `sync_errors.py` 규칙(`AGENTS.md:46`)을 확인 |
| 결정 기록 규칙 | 번호·날짜·근거·기본값, 바꾸려면 **새 행으로 덮고 지우지 않음**, 운영자 정책 결정이 필요한 것은 만들지 않고 '값만 정한 기본값' 으로 표시(`DECISIONS.md:3` 및 D-21·22·23 관례) |

### 5.2 DECISIONS.md — 이 일과 관련된 D-번호 (D-01~D-34, 다음은 **D-35**)

| 번호 | 한 줄 요약(원문 축약) | 전략과의 관계 |
|---|---|---|
| D-02 | 네이버 블로그 B 추가는 '확인사항'(운영자 정보 대기) 상태로 남아 있음 | 코드는 이미 naver_a·naver_b 둘 다 지원(`adapters.py:31`) → 새 행에서 상태 정리 필요(추정: 낡은 표기) |
| D-07·D-15·D-16·D-18 | AI 는 선택 보조·기본 꺼짐·AI 없이 동작해야 하는 기능 목록·AI Router 는 초기 제외(이후 D-30·31 범위 안에서만) | 전략 §25 '규칙 기반 + AI 선택'과 일치. **D-18 의 '필수 기능 목록'에 후보 생성을 더하는 새 행** 후보 |
| D-09 | 감시·예약 실행·알림은 앱에 넣지 않음(Actions 가 함) | **§27 자동 실행 주기와 충돌** → 첫 버전은 수동 실행이 기본값 후보 |
| D-17 | 오류 안내는 규칙(오류 코드+안내 문구) | 새 오류 코드(Trend 한도·후보 점수 불가 등)는 TROUBLESHOOTING 표 + `sync_errors.py` |
| D-23·D-24 | 주제 후보 명령줄(순번·번호 앞 8자·읽기 전용 list/show·CSV 5MB·2000줄·보류·제외·지우기 확인) | 후보 보관 계층이 이미 있음 — 새 상태(우선 추천/일반/보류/제외)와 90일 보류 만료(§19)는 이 위에 얹는 결정 |
| D-25·D-27 | 작성 기반(값 적용 순서 사용자→프로필→글 유형 틀→후보→공통 기본값)·`draft plan` | §16 '작성 가능성 검사'·'소제목 4개 이상' 은 이미 있는 `draft_plan.py` 를 재사용(추정) |
| D-26·D-33·D-34 | '지어내지 않기' 검사 위반 7분류·확인 권장 4분류·정확도 2차·입력값 비노출 | §20·§22.4(경험 없으면 후기 작성 금지)와 같은 방향. 변경 시 예문 세트가 시험을 지킴 |
| **D-29** | **프로필로 먼저 제안**: 작성 우선도 = 적합도 30·시기 20·신선도 20·균형 15·기회도 15, **높음 70/보통 40**, 외부 지표 없으면 기회도 빼고 가중치 재분배('데이터 없음'을 0점으로 치지 않음), 조회일 30일 초과 '오래된 데이터', 씨앗 24개·거르기 순서, 한 씨앗·틀·글 유형 상한 40·20·40% | **전략 §13·§14·§15 와 같은 계열이지만 다른 수치**. §15 '데이터 부족 → 재정규화'는 D-29 ② 와 **같은 원칙**(재사용 가능). 구간·가중치·항목은 다름 → 새 결정 필요 |
| D-30·D-31 | 연결 설정·키 보관, 한도 안전장치(절약 모드·우선순위별 예산 30/20/10/0%·전환 4결과·약관 확인) | §23.2 내부 일 100·월 27,000 한도는 이 틀에 용도로 등록(후보 조사원 담당). 다중 키 순환 금지(§23.5)는 D-31 의 'Unsplash 자동 순환 없음' 처럼 네이버에도 명시 필요 |
| **D-32** | 화면 도구 PySide6 확정, 화면 기초 G0, **메뉴 6개 중 홈만**·읽기 전용·`gui` 가로채기 | 새 화면은 '다음 묶음'으로 예고돼 있음. 읽기 전용 문구를 새 결정으로 덮어야 쓰기 흐름이 가능 |

### 5.3 새 기능을 넣을 때 갱신할 문서와 이를 지키는 시험

| 갱신 대상 | 이유·규칙 | 지키는 시험(사실) |
|---|---|---|
| `docs/DECISIONS.md` 새 행(D-35~) | 값·기본값·충돌한 이전 결정 명시(덮기) | `test_repo_layout.py:93` — 문서가 부르는 모든 `D-nn` 이 표에 있어야 함, 정규식 `^\| (D-\d{2}) \|` |
| `CHANGELOG.md` + `VERSION` | `0.0.0` 항목 아래 줄 추가가 관례, 새 버전을 쓰면 둘을 같이 | `test_repo_layout.py:127-129` |
| `docs/ARCHITECTURE.md` §5 표·§5.1·§9 | 새 모듈 한 줄, 화면 층 '알려 둔 한계'(홈 외 화면은 자리표시)·읽기 전용 문구 갱신 | 문서-코드 일치 시험 일부(`test_ui_core.py:1054-1093` 등) — 정확히 어느 문장이 걸리는지는 **확인 못 함**, 갱신 전 `grep -rn "<문장>" tests` 권장 |
| `docs/UI_COMPONENTS.md` 표·`UI_STATES.md`·`UI_DESIGN_SPEC.md` | 새 부품 표 한 줄, 새 화면 상태, 홈 구성 문장(`월 검색량` 언급 3곳 등) | `test_ui_core.py:1054,1073,1080,1090` 이 문서 문장을 찾음 |
| `docs/TROUBLESHOOTING.md` + `python scripts/sync_errors.py` | 새 실패 경로마다 행 추가, `errors/catalog.py` 는 문서에서 생성(직접 수정 금지) | `tests/test_errors_catalog.py`(37) — 표와 카탈로그 일치 |
| `docs/PLATFORM_POLICY.md` | Data Lab(Search Trend) 공식 API 사용·금지 항목(검색량 표시·키 순환) 한 줄 | (시험 직접 없음 — 추정) |
| `README.md` '명령줄로 써 보기' | 새 하위 명령(예: `topics …`) 사용법 | `test_repo_layout.py` 가 README 존재만 확인(내용은 **확인 못 함**) |
| `docs/SECURITY.md` | 키·네트워크·외부 글 취급 | **읽지 못함** |
| 화면 문구 `ui/core/text.py` | 새 문구는 `T` 표에, `FORBIDDEN` 낱말(`보장` 포함) 금지 | `test_ui_core.py:216-221`, `test_ui_qt.py:1010` |

AGENTS.md 의 작업 규칙 요점: 새 로직은 `src/` 모듈 + `tests/`, 시험은 네트워크·실제 시크릿 없이, 코드는 3.10 문법, 한 PR=한 가지 일, **먼저 시험으로 고정하고 점진적으로**, 병합 부탁은 네 칸 초록 뒤 한 번에 하나(`AGENTS.md:44-54`).

---

## 6. 진입점 — 새 하위 명령/화면을 등록하는 자리

| 목적 | 자리 | 근거 |
|---|---|---|
| `gui` 가로채기 | `__main__.py:5-9` — `argv[1] == "gui"` 이면 `ui.launcher.main` | 사실 |
| 화면 실행 옵션 | `ui/launcher.py:54-71` `build_parser`(`--data-dir`·`--sample`)·`main`(`:70` 에서 공급자 선택) | 사실. 새 공급자(후보 엔진)를 연결하는 줄 |
| 명령줄 최상위 | `service/cli.py:857-864` `sub.add_parser(...)`, 헬퍼 `add(name, handler, help)` | 사실 |
| 명령줄 묶음 하위 명령 패턴 | `draft`(`:567`)·`candidates`(`:593-597`)·`keys`(`:784-788`) — `add_subparsers(dest=…_command, parser_class=KoreanParser)` | 사실. 후보 엔진 명령줄이 필요하면 `candidates` 묶음에 하위 명령으로(예: 분석·상위 보기) 더하는 것이 선례와 일치 |
| 실행·종료 코드·가리기 | `cli.py:1035-1060` `main`(0·1·2, 사용법 오류에서 입력값 되풀이 금지) | 사실 |
| 새 화면 키 | `NAV` 에 이미 `topics`(`app_state.py:17`); 화면 분기 `shell.py:162`; 서랍 분기 `shell.py:204`; 자리표시 `screens.placeholder_screen` | 사실 |
| 화면 문구 | `ui/core/text.py` `T` 표 | 사실 |

---

## 7. 얹는 순서 제안(이 조사원 관점 — UI·시험·문서) 과 결정 필요 항목

### 7.1 순서(작은 묶음, 각각 CI 초록 확인 뒤 병합)

| 순서 | 묶음 | 등급(AGENTS.md §3 기준·추정) | 먼저 지켜 둘 시험 |
|---|---|---|---|
| 0 | **결정 행 D-35**(점수 체계·표기·실행 방식·읽기 전용 개정) — 운영자 정책이 필요한 부분은 '값만 정한 기본값'으로 표시 | T0 문서(+정책 부분 T3 확인) | `test_repo_layout` |
| 1 | **특성 시험**(§3.4 의 1·2·3·10) — 현 홈·어댑터·서랍·채널 두 개 가정을 못박기 | T0 시험 | 신규 |
| 2 | **엔진(UI 없음)**: `content/` 순수 계산(점수·상태 구간·Topic Cluster 상한·보류 90일) + 5채널 프로필 자료 + `service/` 얇은 층 + 명령줄 읽기용 | T1 | 신규(순수·가짜 시계) |
| 3 | **뷰모델**: `AppState` 에 후보 화면 뷰모델(채널별 상위 5개·'기준 충족 N개' 문구·전체 후보 칩 5개·상세 10항목)과 한글 라벨 표 — **Qt 없이 CI 에서 돎** | T1 | `test_ui_core` 형식 |
| 4 | **문구 교체**(`월 검색량` → 상대 관심도, `데이터 없음`/`데이터 부족` 통일) — 서랍 항목 시험과 `UI_*.md` 문장 동시 수정 | T1 | `test_ui_core.py:720`, 문서 시험 |
| 5 | **Qt 화면**: 화면 표 도입, `topics` 화면·서랍 확장·새 부품(채널 배지·후보 목록·접이식) — 오프스크린 시험(내 PC) | T1 | `test_ui_qt` 형식 |
| 6 | **쓰기 어댑터·분석 버튼**(`주제 분석 시작`·보류·선택): 별도 job key·취소·확인 흐름 | T1~T2(저장소 쓰기·네트워크가 들어오면 T2) | 신규 |
| 7 | (선택) CI 에 Qt 칸 | **T2** | `test_repo_layout.py:255,268` |

### 7.2 결정이 필요한 항목(기본값 후보 포함 — 추정이며 운영자 확인 대상)

| # | 결정 | 부딪히는 근거 | 기본값 후보 |
|---|---|---|---|
| 1 | 점수 체계: D-29(5요인·70/40) vs 전략(6항목·채널별 가중치·80/65/50) | `adapters.py:46-50`, D-29 ①, 시험 29개 | 전략 점수는 **새 모듈·새 필드**로 병행 계산, 화면 `작성 우선도` 라벨 구간은 전략 4구간으로 교체(D-29 는 새 행으로 덮음) |
| 2 | `월 검색량`·`월간 검색량` 표기 | §23.3·§23.5 vs `text.py:28,39,74` | `최근 관심도(상대값)` 또는 `최근 관심도` + 숫자는 0~100 상대치, `회` 단위 삭제, 툴팁 `tip_demand` 교체 |
| 3 | `데이터 부족` vs `데이터 없음` 용어 | `text.py:8` | 후보의 지표가 '아직 모음 못 함'이면 `데이터 부족`, 값 자체가 없는 칸은 `데이터 없음`으로 구분(UI_STATES 규칙에 한 줄) |
| 4 | 홈 5행 고정과 '채널별 5개' | `test_ui_core.py:602`, `app_state.py:22,255` | 홈은 그대로 두고(회귀 방지) `주제 후보` 화면에 채널 칩 + 채널별 5개를 새로 만든 뒤, 홈은 나중에 같은 뷰모델을 재사용 |
| 5 | 5채널 중 화면에 보일 채널 | 개발 범위 Naver A/B(§2) | 채널 프로필 5개를 데이터로 두고 `활성 채널 = naver_a·b` 설정으로 화면에 둘만 표시 |
| 6 | 자동 실행 주기(§27) | AGENTS.md:30 규칙 7, D-09 | 첫 버전은 수동(`주제 분석 시작`), 실행 주기는 **계산만**(마지막 평가일·`다음 점검일`을 후보 상세에 표시) |
| 7 | 읽기 전용 원칙 개정 | D-32, `adapters.py:1` | 읽기 어댑터는 그대로 두고 쓰기 어댑터를 따로(분석·보류·선택), 문구는 새 결정 행으로 |
| 8 | 새 색 토큰(채널 3개 배지) | `tokens.py:36` 가 A·B 색만 정의 | 색 없이 글자 배지(`info`)로 시작 |
| 9 | 영문 용어 표기(Seed·Topic Cluster·Topic Angle) | `test_ui_core.py:216-221`(본문 확인 못 함) | 화면은 `씨앗`·`주제 묶음`·`관점`, 영문은 문서·JSON 에만 |
| 10 | 화면 면책 문구 | `FORBIDDEN` 에 `보장` 포함 | 화면에는 쓰지 않고 `docs/` 에만 둔다(표시하지 않음이 원칙이므로 설명 자체가 필요 없음) |

### 7.3 확인하지 못한 것(정직한 목록)

- `docs/UI_VISUAL_QA.md`·`UI_ICONS.md`·`UI_IMAGES.md`·`SECURITY.md`·`MIGRATION.md`·`RELEASE.md`·`TROUBLESHOOTING.md` 본문, `DECISIONS.md` D-15~D-22·D-30·D-31·D-33 의 전문(앞부분만 읽음).
- `ui/qt/theme.py`·`icons.py`·`notify.py`·`attribution.py`·`imagerules.py` 코드 본문, `test_ui_adapters.py` 본문(경계값 시험 여부), `test_ui_core.py:216-221` 본문(영문 낱말 허용 범위), 변이 시험 3개 파일의 실제 방식, 개별 건너뛰기 사유.
- 시험 실행 시간(전체·모듈별)은 실행하지 않았다(규칙). CI 시간은 `ci.yml` 주석의 14~15분만 근거.
- 후보 모델 필드·수집(Search Trend) 코드·채널 프로필·보관함 스키마는 다른 조사원 담당이라 이 보고서의 판단(§3.4-4·§7.2)은 그쪽 결과와 맞춰야 한다.
