# 조사 보고 A — 후보·제안·보관함·프로필 코드 (읽기 전용 조사)

대상: `…\scratchpad\cd_wt_ts` = chanceblog-desktop main 3b1294b (`src/chanceblog_desktop` · 시험 93개 항목·시험 함수 3,688개). 전략 문서는 §번호로만 인용한다(원문 복사 없음).
표기: `파일:줄` = 근거, **(추정)** = 코드에서 직접 확인하지 못한 판단, **(확인 못 함)** = 이번 조사로 알 수 없었던 것.

## 0. 요약 10줄

1. 후보 모델 `Candidate`(schema 1, 24개 저장 키)는 이미 5채널 키(github_pages·blogger_en·blogger_ko·naver_a·naver_b)·지표 9종·작업 상태 5종을 갖췄다. 전략 §29 의 25개 최상위 필드 중 **동일 의미 4 · 부분/의미 다름 8 · 없음 13**(§2.6).
2. 후보 상태(NEW·REVIEW·SELECTED·HOLD·REJECTED)는 **사람의 작업 흐름**이고 전략 §14 의 80/65/50 점수 구간 상태와 다른 축이다. 전이표는 `docs/ARCHITECTURE.md §9` 와 시험이 글자 단위로 못박아 두었다 → 상태를 늘리지 말고 **파생 구간 필드를 따로** 두는 편이 안전(§2.7).
3. `search_demand`(월간 검색 수요, 횟수)와 `trend`(상승·보합·하락)는 필드가 분리돼 있으나 **값의 종류를 막는 장치가 없다**: `search_demand=87` 을 넣으면 '월간 검색 수요 87회'로 통과(실측), `opportunity()` 는 이 값을 10만 회에서 100점인 로그 눈금 절대 횟수로 계산한다 → Search Trend 상대지수는 **새 필드**여야 한다(§2.8).
4. `candidates suggest` 는 100% 규칙 기반·결정적(같은 입력 → 같은 JSON 실측 확인, 난수·현재 시각·네트워크·AI 호출 없음, `today` 는 인자). 입력은 프로필의 주제·카테고리·기본 태그와 보관함의 글 제목·후보·달뿐이고, Seed 저장소·채널별 캘린더·실시간·후속·협찬·6항목 점수·Topic Cluster 는 **없다**(§3).
5. **실측 결함**: 계절 매칭이 부분 문자열이라 '그래픽카드'가 '카드'로 '연말정산 준비' 시기에 걸린다 → Naver B(AI·PC 부품) 11월 1위 제안이 '연말정산 준비 시기에 챙겨 볼 그래픽카드 정리'(점수 100). 의미 조합 차단·건강·브랜드 규칙도 없다('영양제'·'불면증 해결'·'삼성 갤럭시' 씨앗 통과)(§3.5).
6. 보관함은 SQLite `chanceblog.db` 판 2: 후보는 **열 5개 + JSON 덩어리(`data`)**. 새 표·열은 반드시 **판 3 올리기 단계**로 더한다 — `_V2_CANDIDATES` 해시 고정, `SCHEMA_VERSION==2`·`MIGRATIONS=={1}` 시험, 새 이름은 `candidates%` 로 시작하면 시험이 깨진다(§5.4).
7. 후보 JSON 은 모르는 칸을 거절하므로(`from_dict`), **판을 올리지 않고 필드만 더하면** 구버전 앱이 그 후보를 '깨진 후보'로 보고 목록 전체를 막는다(`list_candidates` 가 CANDIDATE_CORRUPT 로 멈춤) → 필드 추가도 판 3 으로(§5.3).
8. 동시 실행은 `service/lock.py`(발행 전용)를 쓰지 않는다. SQLite `BEGIN IMMEDIATE`+5초 대기+객체별 RLock 이고, `Store.add_candidates(plan)`(쓰기 잠금 뒤 읽기→판단→저장 한 트랜잭션)이 새 기능의 본보기다(§5.3).
9. 프로필: `NaverProfile` 은 naver_a/b 와 `blog.naver.com` 주소만 받고 `settings.json` 은 알 수 없는 칸을 `SETTINGS_INVALID` 로 거절 → 5채널 프로필은 `connections.json` 식 **별도 파일/표**가 안전. 엔진(`suggest`·`Candidate.blogs`·`PLATFORMS`)은 이미 5채널 키를 받고, 막는 곳은 `service/suggestions.profile_for` 와 설정 저장뿐(§6).
10. 재사용 지도(12영역): **그대로 1**(데이터 부족 재정규화) · **확장해서 5**(확장어·캘린더·중복·작성 가능성·상위 N) · **새로 6**(Seed 저장소·6항목 점수·상태 구간·후속 후보·90일 보류함·협찬 태그)(§7).

---

## 1. 범위·방법·한계

| 항목 | 내용 |
|---|---|
| 읽은 코드 | `content/` candidates(523줄)·candidate_csv(406)·store(962)·suggest(681)·suggest_data(241)·suggest_score(210)·suggest_text(142)·profiles(239)·status(88)·post_types(머리말) / `service/` candidates(618)·suggestions(303)·context(287)·cli(candidates·suggest 구간)·lock(머리말)·doctor(저장소 점검 구간) / `check/` similarity(150)·profile_options(44) / `docs/` ARCHITECTURE §5·§9·§10, DECISIONS D-29·D-23~D-24 |
| 시험 | 전체 실행 안 함. 시험 이름·고정값만 `grep`/줄 수로 확인(§7 표의 수치) |
| 실측 | 읽기 전용 파이썬 3회(메모리 안에서 `NaverProfile`·`suggest()`·`season_fit()`·`Candidate.new()` 호출 — 보관함·설정 파일을 열지 않음, 임시 스크립트는 scratchpad `an_a_tmp/`). 호출이 남긴 `__pycache__` 는 지움(`git status` 깨끗) |
| 못 본 것 | 전체 시험 통과 여부, `ui/`·CI·문서 전체(다른 조사원 몫), 실제 사용자 데이터 폴더의 보관함 |

---

## 2. `content/candidates.py` — 후보 데이터 모델

### 2.1 상수·한도

| 상수 | 값 | 줄 |
|---|---|---|
| SCHEMA(JSON 저장 모양 판) | 1 | candidates.py:26 |
| MAX_TOPIC / MAX_KEYWORD(=profiles.MAX_PHRASE) / MAX_SUB_KEYWORDS / MAX_REASON | 200자 / 60자 / 20개 / 300자 | :27-30 |
| MAX_SEARCH_DEMAND / MAX_RELATED_RESULTS / MAX_REVISION | 1e9 / 1e10 / 1e9 | :31-33 |
| SHORT_ID(화면 번호 길이) / MIN_YEAR / STAMP_FORMAT | 8 / 2000 / `%Y-%m-%dT%H:%M:%SZ`(UTC) | :34-36 |
| 상태 코드 | NEW·REVIEW·SELECTED·HOLD·REJECTED | :48-49 |
| 허용 지표 이름(ALLOWED_TERMS) | 키워드 기회도·콘텐츠 작성 우선도·블로그 프로필 적합도·최근 관심도 변화·관련 블로그 검색 결과 수(5개 — '월간 검색 수요'는 LABELS 에는 있고 여기엔 없다) | :74 |

### 2.2 `Candidate` 필드(frozen dataclass, `:361-387`)

| 필드 | 타입 | 기본값 | 검증 규칙(`_validate :392-439`) |
|---|---|---|---|
| candidate_id | str | 필수 | `[A-Za-z0-9_-]{1,64}`. `Candidate.new` 가 `uuid4().hex`(32자)를 만든다(:446) |
| topic | str | 필수 | 1~200자·한 줄·마크업·금지 표현 거절(`_line :266`) |
| keyword | str | 필수 | 1~60자·글자/숫자 1개 이상(`_keyword :283`) |
| blogs | tuple | 필수 | `PLATFORMS` 중 **1~5개**·겹침 불가·list/tuple 만(`_blogs :316`) |
| sub_keywords | tuple | () | ≤20개, 핵심 키워드·서로와 `keyword_key` 중복이면 거절(:400-408) |
| post_type | str | '정보형' | `POST_TYPES` 5종(정보형·비교형·문제 해결형·제품·서비스 소개형·장소·업체 정보형) |
| search_demand | int\|None | None | 0~1e9 정수 |
| related_blog_results | int\|None | None | 0~1e10 정수 |
| trend | str\|None | None | 상승·보합·하락 |
| mobile_share | float\|None | None | 0~100 |
| seasonality | tuple\|None | None | 달(1~12) 겹침 없이 1~12개, 정렬해 저장(`_months :326`) |
| duplicate | bool\|None | None | 예·아니오·비움 |
| profile_fit·priority·keyword_opportunity | float\|None | None | 0~100(`_score :307`) — **사람이 적거나 CSV 값**, 제안은 채우지 않는다(ARCH §9) |
| reason | str | "" | ≤300자 한 줄(금지 표현 검사 포함) |
| data_date | str\|None | None | `YYYY-MM-DD`. **지표 9개 중 하나라도 있으면 필수**(:423-426) |
| status | str | NEW | 5종 |
| selections | tuple | () | ((블로그, UTC 시각)…) 플랫폼 순서, NEW 상태에는 있을 수 없음(:430) |
| project_id | str\|None | None | 연결한 글. DB 에서는 **열이 기준**(자료 JSON 에는 안 적음) |
| revision | int | 1 | 1~1e9, 바뀔 때마다 +1 |
| created_at / updated_at | str | "" → `new` 가 채움 | UTC `…Z`, `updated_at ≥ created_at`(:438) |

### 2.3 상태와 전이(`TRANSITIONS :51-57`, `Candidate.moved :464`, `Store._put_candidate :695`)

| 현재 | 갈 수 있는 곳 | 비고 |
|---|---|---|
| NEW | REVIEW·SELECTED·HOLD·REJECTED | 새 후보로는 되돌아갈 수 없음 |
| REVIEW | SELECTED·HOLD·REJECTED | |
| HOLD | REVIEW·SELECTED·REJECTED | **수동 보류**(만료일·사유 필드 없음) |
| REJECTED | REVIEW | `restore` 가 이 이동만 허용 |
| SELECTED | HOLD·REVIEW | 같은 상태에서 블로그를 더 고르는 것은 이동이 아니라 `selections` 추가(:473) |

- 초안 이후(작성 중·완료·복사·발행)는 후보 상태를 만들지 않고 글(프로젝트)의 네이버 흐름 상태에 대응(`FOLLOW_ON :61`). **주의: `FOLLOW_ON` 은 '상태 대응'이지 전략 §18 '후속 후보'가 아니다 — 새 기능 이름을 겹치지 말 것.**
- 전이는 저장 단계에서도 다시 강제된다(`_put_candidate :695-697`). 불변 객체라 `edited()`·`moved()` 가 새 후보를 돌려주고 판 번호가 오른다.

### 2.4 검증·금지 표현

- 모든 글칸은 **한 줄만**(제어·보이지 않는 글자·겹친 공백은 고쳐 받지 않고 거절, `_one_line :254`), 빈칸처럼 보이는 글자(`_BLANK_LOOKALIKES :43`)·쌓인 결합 문자(`:45`)·원시 HTML/이벤트/스크립트 주소/Liquid 표기(`profiles.find_markup`) 거절.
- 결과 약속 표현 금지(`forbidden_claim :165`): 한국어 6규칙(상위노출 보장·노출·순위 보장·노출 확률·검색 1위·수익 보장, `:89-96`) + 영어(`guarantee` 근처의 rank/serp/income, 확률, `:102-162`). 띄어쓰기·전각·한자·NFD 우회 방어, 바로 뒤 부정('보장하지 않습니다')과 경계 글('보장 업체 피하는 법')은 통과. **주제·키워드·보조 키워드·추천 이유 전부에 적용**.
- 키 비교는 `keyword_key :176`(NFKC·소문자·글자숫자만, `+`·`#`·숫자 사이 소수점은 보존 — C++≠C#).

### 2.5 저장 모양

- `to_dict :498` = 24키(`schema` 포함), `from_dict :509` = **엄격**: 모르는 칸·필수 9칸(`schema·candidate_id·topic·keyword·blogs·status·revision·created_at·updated_at`) 누락 → `CANDIDATE_INVALID`. 필수 외 칸은 빠져 있으면 기본값(옛 자료 읽기용).
- `selections` 는 JSON 에서 `{블로그: 시각}` 객체. DB `data` 열 = `to_dict()` 에서 `project_id` 를 뺀 compact·`sort_keys` JSON(`store.py:214,677`).
- 시험이 모양을 고정: `test_content_candidates.py` JsonShapeTest(:567-580 — `KEYS` 목록 = dataclass 필드 + schema, `schema == 1`), LABELS = 필드 − 내부 칸(:548).

### 2.6 전략 §29 최소 후보 모델 ↔ 현재 필드 (25개 최상위 필드)

| # | 전략 필드 | 현재 필드 | 판정 | 메모 |
|---|---|---|---|---|
| 1 | candidate_id (`candidate-20261104-001`) | `candidate_id`(uuid hex 32자, 정규식은 64자까지 허용) | 의미 다름(형식) | 전략식 ID 는 앞 글자가 모두 같아 `resolve` 의 '앞 4자 이상 접두 선택'·`short_id`(앞 8자)·`DELETE_PREFIX=8` 과 충돌 → uuid 유지+표시용 `display_id` 별도(추정) |
| 2 | source_topic_id | 없음 | 없음 | 공통 원천 주제 저장소 자체가 없음 |
| 3 | seed_id | 없음 | 없음 | 제안은 `Suggestion.seed`(글)·`seed_source`(주제/카테고리/태그)를 계산 결과에만 두고 저장하지 않음 — 보관함에는 `reason` 앞머리 `프로필 제안 —`(`suggest.py:31`)만 남음 |
| 4 | source_type (seed/follow_up/seasonal/…) | 없음 | 없음 | |
| 5 | candidate_type (evergreen/…) | 없음 | 없음 | |
| 6 | channel (단일) | `blogs`(1~5개 tuple) + `selections`(블로그별 선택 시각) | 의미 다름 | 전략은 후보 1건=채널 1개(최대 2채널 재사용)인데 현재는 한 후보가 최대 5채널 |
| 7 | language | 없음 | 없음(파생 가능) | `blogger_en`=영어, 나머지 한국어 |
| 8 | topic | `topic`(≤200자) | **대응** | 전략 §26 '후보 주제≠발행 제목'과 같은 구조(`draft plan` 이 제목 후보 3개를 따로 만든다) — 전략 §29 예시 문장도 `Candidate.new` 검증 통과(실측) |
| 9 | primary_keyword | `keyword`(≤60자) | **대응** | |
| 10 | secondary_keywords | `sub_keywords`(≤20) | **대응** | |
| 11 | search_intent | 없음 | 없음 | `draft plan` 이 '예상 검색 의도'를 계산하지만 저장 안 함 |
| 12 | content_type (buying_guide…) | `post_type` 5종 | 의미 다름 | 분류 체계가 다름 → 매핑표 필요(예: buying_guide ≈ 비교형/제품·서비스 소개형) |
| 13 | topic_cluster | 없음 | 없음 | |
| 14 | topic_angle | 없음 | 없음 | |
| 15 | target_reader | 없음 | 없음 | 프로필 `audience` 가 블로그 단위로만 있음 |
| 16 | scores(6항목+final) | `profile_fit`·`priority`·`keyword_opportunity`(0~100, 사람/CSV 입력) | 의미 다름 | 6항목 구조 아님. 제안이 만든 후보는 점수가 비어 있고 표시할 때 `assess()` 로 다시 계산(저장 안 함) |
| 17 | trend_status (rising…) | `trend`(상승·보합·하락) | 부분 | 값이 3개뿐, '데이터 부족'·'API 장애' 값 없음 |
| 18 | data_status (sufficient…) | 없음 | 없음 | `has_data()`·`data_date` 로 '있음/없음'만 |
| 19 | duplicate_status (different_angle…) | `duplicate`(bool\|None) | 의미 다름 | 이진값 |
| 20 | similar_post_ids | 없음 | 없음 | `project_id` 는 '연결한 글' 1개뿐 |
| 21 | monetization_tags | 없음 | 없음 | |
| 22 | selection_reasons(목록) | `reason`(한 줄 ≤300자) | 부분 | 선정 이유/처리 오류 분리 없음 |
| 23 | status (recommended…) | NEW·REVIEW·SELECTED·HOLD·REJECTED | 의미 다름 | §2.7 |
| 24 | created_at (+09:00) | `created_at`(UTC `…Z`, 초 단위) | **대응**(표기 다름) | 화면은 KST 로 환산(`service/candidates.py:330`) |
| 25 | review_expires_at | 없음 | 없음 | |

합계: 대응 4(8·9·10·24) · 부분/의미 다름 8(1·6·12·16·17·19·22·23) · 없음 13.

### 2.7 전략 §14 상태 구간 ↔ 현재

| 전략 구간 | 처리 | 현재 |
|---|---|---|
| 80~100 우선 추천 | 기본 화면 상위 후보 | 없음 — 우선도 라벨 `높음` 은 **70 이상**(`suggest_score.py:28`) |
| 65~79 일반 후보 | 전체 후보에 저장 | 없음 (`보통` 은 40 이상, `:29`) |
| 50~64 보류 | 보류함 90일 | `HOLD` 는 사람이 누르는 상태일 뿐 점수·만료와 무관 |
| 0~49 제외 | 생성 이력·제외 사유만 | `REJECTED` 는 후보 전체를 그대로 보존(사유 칸 없음), 지우기는 별도 `delete`(되돌릴 수 없음) |

- 점수↔상태 연결은 코드 어디에도 없다(우선도는 표시용 라벨, `Priority(level, score)`). **(추정)** 구간은 `Candidate` 의 새 파생 필드(예: `recommendation_band`)나 계산 함수로 두고 `status` 는 그대로 두는 편이 기존 시험·문서·`ui/adapters.STATUS`(`ui/adapters.py:33`)를 건드리지 않는다.

### 2.8 관심도·수요 필드가 '상대지수와 실제 횟수'를 섞지 않게 막혀 있는가

| 관점 | 현재 | 판정 |
|---|---|---|
| 필드 분리 | `search_demand`(월간 검색 수요·회, int)·`related_blog_results`·`trend`(3값)·`mobile_share`·`seasonality` 가 따로 있음(:370-374) | 이름만 분리 |
| 표시 이름 고정 | `LABELS`(:68-73), 허용 이름 5개(:74) — 지표를 '검색량 예측·노출' 같은 말로 부르지 못하게 하는 장치 | 이름 규칙뿐 |
| 조회일 필수 | 지표가 하나라도 있으면 `data_date`(:423-426), 30일 넘으면 '오래된 데이터'(`suggest_score.py:53`) | 있음 |
| **값의 종류 구분** | **없음** — 실측 `Candidate.new(…, search_demand=87, data_date=…)` 통과·'월간 검색 수요 87'로 저장 | **없음** |
| 점수 환산 | `opportunity()`(`suggest_score.py:115-129`)가 `search_demand` 를 로그 눈금(10만 회=100점, `:48,111`)으로, `related_blog_results` 는 1천만 건=0점으로 바꿔 우선도 15% 에 반영. `external_from`(`suggest.py:210-220`)이 **키워드 단위로 블로그와 무관하게** 후보의 지표를 모아 점수에 넣음 | 상대지수 0~100 이 들어오면 점수가 왜곡됨 |
| CSV | 열 별칭에 `search volume`·`monthly searches`(`candidate_csv.py:47`)가 있고 `트렌드` 열은 상승/보합/하락 글자만 받음(`parse_trend`) → 숫자 지수 열은 `trend` 로는 거절되지만 `검색량` 이름 열은 그냥 받음 | 부분 |
| 데이터 부족 | 없는 값은 `None`('데이터 없음'), 점수에서 빼고 재정규화(`combine :81-93`) — 0점 처리 안 함 | 전략 §15 와 같은 방향 |
| 장애/부재 구분 | 호출 코드가 없어 구분 필요도 없음 | 없음 |

결론: 전략 §23.3·§23.5(상대지수를 월간 검색량·예상 조회수로 표시 금지)를 지키려면 (a) 상대지수 전용 새 필드(값+기준 기간·비교군+조회일)와 `trend_status`·`data_status` 를 두고, (b) `search_demand` 는 **실제 횟수 출처가 있을 때만**(검색광고 API 등) 쓰도록 출처 표시를 더하고, (c) `opportunity()` 와 `external_from` 이 새 필드를 섞지 않게 별도 요인으로 분리해야 한다(추정). `trend`(3값)는 상대지수에서 파생한 방향 표시로 재사용 가능.

---

## 3. 후보 자동 제안 — `content/suggest*.py` + `service/suggestions.py`

### 3.1 입력과 출력

| 구분 | 내용 | 근거 |
|---|---|---|
| 호출 | `suggest(profile, *, today, existing_titles, candidates, blog, count, month, selections, external, post_type)` → `Report` | suggest.py:554 |
| 프로필(`ProfileView`) | display_name·topic·audience·categories·tags(default_tags)·excluded(제외 주제)·forbidden(금지 표현)·reuse_days·post_type. 같은 이름의 칸을 가진 값이면 `NaverProfile` 이 아니어도 됨(`getattr`) | :65-91 |
| 기존 글 | 보관함 원고 제목 + '선택됨' 후보 주제만. **연결 저장소 `_posts`·GitHub posts.json·Blogger JSON·네이버 발행 글 외부 목록은 읽지 않음**(알려 둔 한계) | service/suggestions.py:24,41-43 |
| 보관함 후보 | 같은 블로그·같은 키워드는 숨김, 후보의 지표를 키워드 단위로 모아 점수에 사용(`external_from`) | suggest.py:210-220,369 |
| 달·날짜 | `today`(KST 달력 날짜, `ctx.stamp()` 에서) · `month`(없으면 today 의 달) | suggestions.py:58 |
| **입력이 아닌 것** | 클라우드 주제·공통/채널별 Seed 저장소·Search Trend·AI·시계(`today` 외)·난수 | grep 결과 없음(random·datetime.now·http·socket·assist 0건) |
| 출력 `Report` | `suggestions`(rank·keyword·sub_keywords·topic·post_type·reason·priority{level,score}·profile_fit·season·metrics·data_date·computed_on·data·factors[]·seed·seed_source·frame), `generated`(걸러내기 전 조합 수), `filtered`(이유별 개수), `hidden_ranks`, `seeds`, `seed_total`, `guidance`, `notes`, `more`(JSON 에는 안 실림) | :473-551 |
| 보관함에 넣을 때 | `--add 번호 --yes` → `Candidate.new(topic, keyword, (blog,), sub_keywords, post_type, reason="프로필 제안 — …")`. **점수·지표·seed 정보는 저장하지 않음** | suggestions.py:231-265 |

### 3.2 처리 단계(`suggest()` :554-616)

| 단계 | 하는 일 | 한도 |
|---|---|---|
| ① 씨앗 | 프로필 `topic` → `categories`(네이버 카테고리·원고 분류 이름) → `default_tags` 순, 쉼표·가운뎃점·'및' 등으로 구를 나눠 낱말 3개 이하면 구 하나, 넘으면 낱말마다. 군더더기 낱말(`FILLER_WORDS` 30개) 제거. 비밀 모양·경험 단정·결과 보장 낱말(`_RISKY`)이 든 씨앗은 버리고 개수를 알림 | 24개·2~24자 |
| ② 조합 | 씨앗 × 틀 23개(시기 틀 6개는 그 달 시기 항목과 이어지는 씨앗에만) | 조합 수 제한 없음 |
| ③ 관문 | 한 함수 `_gate`(:309): 글자·낱말 한도 → 제외어 → 금지 표현 → 형식(`Candidate.new` 시도) → 최근 선택 → 보관함에 이미 있음 → 기존 글과 비슷함. 첫 번째 걸린 이유 하나만 센다. 개수 상한·예외 삼키기 없음(실패 열림 없음) | `GATE_ORDER :44` |
| ④ 점수 | 5요인 가중 평균(§3.3) | |
| ⑤ 다양화 | 점수 순(같으면 조합 순서)으로 훑으며 같은 키워드·낱말집합 겹침 0.7↑ 건너뜀, 한 씨앗 40%·한 틀 20%·한 글 유형 40%(요청 개수 올림) 상한, 모자라면 상한만 풀어 채움. 최근·보관함 제안은 숨기되 **번호는 그대로**(같은 `--add 1,2` 되풀이 안전) | `:423-457` |

### 3.3 점수 요소와 가중치(`suggest_score.py`, D-29 + 시험이 값 고정 — `test_suggest_score.py:31-41`)

| 요인 | 가중치 | 계산 |
|---|---|---|
| fit 블로그 프로필 적합도 | 30 | 씨앗 출처 강도(주제 90·카테고리 75·태그 60) + 글 유형이 프로필 기본 글 유형과 같으면 +10(최대 100) |
| season 시기 적합 | 20 | 글에 그 달 시기 낱말 있음 100 · 시기와 이어지는 주제 70 · 무관 50 · 외부 계절성 있는데 이번 달 아님 30 |
| freshness 신선도 | 20 | 기존 글 제목과 낱말집합 Jaccard 0→100, 0.6→0 직선 |
| balance 주제 균형 | 15 | 같은 씨앗을 다룬 기존 글 1편마다 −20 |
| opportunity 키워드 기회도 | 15 | 수요 50(로그, 10만 회=100)·경쟁 30(관련 블로그 검색 결과 1천만=0)·관심도 20(상승 100·보합 50·하락 0), **없는 하위 점수·요인은 빼고 가중치 재분배** |
| 구간 | — | 70↑ 높음 · 40↑ 보통 · 아래 낮음(표시 전용) |

### 3.4 중복 경고·결정성·AI·계절·후속·협찬

| 질문 | 답 | 근거 |
|---|---|---|
| 중복 경고 방식 | 제안 단계에서 **숨김/제외**(경고 문구가 아니라 `filtered` 개수로 알림): 최근 선택(같은 블로그·같은 키워드, 프로필 `topic_reuse_days` 기본 90일, 한국 달력) · 보관함에 있음(같은 블로그·같은 키워드) · 비슷한 글(씨앗을 모두 담은 기존 제목과 낱말집합 Jaccard ≥0.6, 또는 두 낱말 이상 키워드가 한 제목에 모두 있음) | suggest.py:309-332, suggest_score.py:43 |
| 규칙 기반인가·AI 호출 | 100% 규칙. AI·네트워크 호출 코드 0. `assist/` 디렉터리도 `src` 에 없음(ARCH §7 은 '기본 꺼짐 예정') | grep, `ls src/chanceblog_desktop` |
| 결정성 | **있음** — 정렬 키 `(-점수, 조합 순서)`, 틀 `frame_id` 고정, `today` 는 인자. 실측: 같은 입력 두 번 → 같은 JSON(4개 경우 모두 True) | :591, 실측 §3.5 |
| 시계·난수 | 쓰지 않음(날짜는 인자). 단 서비스 층이 `ctx.stamp()` 로 오늘을 정함 | suggestions.py:58 |
| 계절·월 | 있음 — `SEASONS`(12개월 × 10~11항목 = 122항목: 시기 낱말·한 줄 이유·이어지는 낱말), 시험이 8~15항목·'입니다' 끝·수치/통계 금지를 확인 | suggest_data.py:38-185, `test_suggest_data.py:54-78` |
| 후속 후보 | 없음(`후속|파생` 검색 0건) | grep |
| 협찬 | 없음. 오히려 `_RISKY` 가 '체험단·체험기·후기·내돈내산' 낱말이 든 씨앗을 버림('협찬' 낱말 자체는 목록에 없음) | suggest.py:106 |
| 영어 | 영어 후보의 금지 표현 검사만 있고 영어 틀·Seed·계절표 없음(전부 한국어) | candidates.py:102-162 |

### 3.5 실측(읽기 전용, 메모리 안 호출 — 프로필 A: 소형가전·제습기·숙박·여행·PC 주변기기, 프로필 B: AI 서비스·PC 부품·업무 자동화·그래픽카드)

| 경우 | 결과 | 의미 |
|---|---|---|
| A·11월 | 씨앗 7개·137조합 → 1위 '쇼핑 행사 시기에 챙겨 볼 소형가전 정리'(100점), 2~3위 '늦가을 여행 시기에 챙겨 볼 **여행** 정리'(제목에 같은 낱말 반복) | 시기 틀이 상위 독점, 제목이 기계적 |
| A·6월 | '에어컨 시기에 챙겨 볼 소형가전', '장마 시기에 챙겨 볼 제습기' 등 | 가전 계절 후보는 작동 |
| **B·11월** | 1위 **'연말정산 준비 시기에 챙겨 볼 그래픽카드 정리'(100점)** | `그래픽카드` ⊃ `카드` 부분 문자열이 '연말정산 준비'의 이어지는 낱말('카드')에 걸림 — `_is_related :141-149`(`word in token`). `season_fit('그래픽카드', 11)`=70·'카드 혜택'도 70 |
| B·6월 | 시기 맞춤 없음 안내 + '… 처음 알아볼 때 꼭 짚어 둘 기본 정리' 류 정보형·비교형 | 틀이 주제 무관 |
| 위험 씨앗 | '영양제'·'불면증 해결'·'삼성 갤럭시' 통과(건강·브랜드 표시 없음), '체험단 모집'은 버려짐 | 전략 §20·§21·§22 규칙 없음 |
| 결정성 | 4경우 모두 동일 JSON | |
| 지표 | `Candidate.new(search_demand=87, data_date=…)` 통과 | §2.8 |
| 필드 추가 시도 | `edited(topic_cluster=…)`·`monetization_tags`·`scores` → `CANDIDATE_INVALID`(모르는 칸 거절) | 새 칸은 클래스 수정 필요 |

### 3.6 전략 §6~§18 등 ↔ 현재 (있음/부분/없음)

| 전략 | 요구 | 현재 | 판정 |
|---|---|---|---|
| §6 | 후보 발생 5경로·비율 30/20/20/15/15 | 경로 1개(프로필 씨앗×틀×시기) + 수동·CSV. 비율 로직 없음(`_diversify` 40/20/40 은 씨앗/틀/유형 쏠림 방지) | 없음 |
| §7 | 채널별 지속형/실시간 비율 | 구분 없음 | 없음 |
| §8 | Seed 3단계(대분류>중분류>Seed·우선·제외), 공통 30+채널별 20, 승인 등록, 180일 미선택 비활성화 *제안*, 협찬 태그, 영어 Seed | 씨앗은 프로필 낱말에서 **그때그때 추출·저장 안 함**. 제외어는 프로필 `excluded_topics` 1단계뿐 | 부분(제외어)·나머지 없음 |
| §9 | Seed 유형별 최초 3~5·보관 2~3, 같은 검색 의도 통합 | 씨앗당 23틀 조합 → 요청 개수만 선택, 씨앗 몫 40%, 키워드 겹침 0.7 건너뜀 | 부분(근사) |
| §10 | 공통 확장어 10·채널별 방향·Seed 유형별 허용 확장·의미 안 맞는 조합 차단 | 확장은 **글 유형 틀 23개**(기본 정리·체크리스트·질문·방법·종류 비교·장단점·대안·문제 해결·실수·활용·기능·필요·비용·업체·위치·지역·시기 틀). 확장어 목록·Seed 유형·채널별 방향 없음, 의미 조합 차단 없음(B·11월 실측) | 부분(틀만)·차단 없음 |
| §11 | 공통+채널별 캘린더, 준비 시작·발행 기간·피크·반복·마지막 평가일, Trend 보정 | 월별 공통 표만, 월 단위 낱말 매칭만 | 부분 |
| §12 | 실시간 이슈(공식 1/독립 2 출처·48시간 안정화) | 없음 | 없음 |
| §13 | 채널별 6항목 가중치(합 100) | 5요인 한 벌(30/20/20/15/15)·채널별 없음·'작성 가능성'·'근거'·'수익화' 요인 없음 | 부분(틀) |
| §14 | 80/65/50 구간, 상위 5·같은 Topic Cluster ≤2·80↑ 부족 시 65~79 보충·50~64 보충 금지·'기준 충족 N개' 안내 | 상위 N(`count` 기본 10, 최대 50)·낮은 품질 안내문 비슷한 것('조건에 맞는 제안이 N개뿐', :613)은 있음. 구간·Cluster·보충 규칙 없음 | 부분 |
| §15 | 데이터 부족 시 재정규화, 0점 처리 금지, 장애/부재 구분, Blogger B 미적용 | `combine()` 재정규화·'외부 데이터 없음' 표기 있음. 장애 구분·채널별 미적용 없음 | 있음(부분) |
| §16 | 작성 가능성 8항목 검사+7단계 자동 보완+'작성 기반 부족' 보류 | 형식 검사(`Candidate.new` 시도)·틀 6단계(소제목 6개)·경험 지어내기 차단(`claims`·`_RISKY`)은 있음. 자동 보완 단계·보류 사유 없음. 프로필 소제목 기본 3~5(`profiles.py:154-155`) | 부분 |
| §17 | 채널 내 40/60/75% 4구간, 채널 간 최대 2채널, 숫자만으로 삭제 금지 | 제안: 0.6 하나(숨김). 초안 A/B: `check/similarity` 경고 0.40·높음 0.60. 75% 구간·키워드·검색 의도·Cluster·Angle·독자 결합 없음. **자동 삭제는 하지 않음**(일치). 채널 수 제한 없음(`blogs` 1~5) | 부분 |
| §18 | 글당 후속 후보 ≤3, 일반 후보와 같은 평가 | 없음 | 없음 |
| §19 | 50~64 보류함 90일·재평가 트리거·90일 뒤 이력만 유지 | `HOLD` 수동 상태만 | 없음 |
| §20·§21 | 미사용 제품·브랜드 규칙, 건강 주제 확인 필요/자동 초안 중지 | 경험 단정 차단은 강함(`claims`·`post_types.premise_of`). 브랜드·건강 규칙 없음 | 부분/없음 |
| §22 | 협력 유형 표시·경제적 이해관계 9종·고지문 자동 배치 | 프로필 `disclosure`(AI 활용 고지)만 | 없음 |
| §23 | Search Trend(일 100·월 27,000, 장애 시 규칙 기반 계속) | 호출 코드 없음(`connections.PURPOSES` 의 `naver_openapi` 는 '호출 코드 없음', 한도 틀 `quota.py` 는 별도) — 다른 조사원 | 없음 |
| §24 | 기존 발행 이력(제목·카테고리·언어·태그·날짜, posts.json·`_posts`·Blogger JSON) | 보관함 원고 제목+선택됨 주제만 | 부분 |
| §25 | AI 는 문장 다듬기만, AI 없이도 계속 | 일치(AI 호출 0) | 일치 |
| §26 | 후보 주제 ≠ 발행 제목 | 일치(`topic` vs `draft plan` 제목 후보) | 일치 |
| §27 | 자동 실행 주기 | 예약 작업 없음(`jobs/` 디렉터리 없음, ARCH 는 '예정') | 없음 |

---

## 4. CSV 가져오기·후보 서비스·명령줄

### 4.1 CSV(`content/candidate_csv.py` + `service/candidates.import_csv :548-611`)

| 항목 | 규칙 |
|---|---|
| 파일 | UTF-8(BOM 허용)→cp949 순서로 읽기, UTF-16·NUL·빈 파일 거절, ≤5MB(`:27`), 자료 줄 ≤2,000(`:28`), 보통 파일만(장치 이름·폴더 거절) |
| 구분자 | 머리줄에 가장 많은 것(쉼표·탭·세미콜론), 큰따옴표 속 줄바꿈 허용 |
| 열(16칸 별칭표 `:41-58`) | topic·keyword(필수) · blogs(필수, `--blog` 로 대신 가능) · sub_keywords·post_type·search_demand·related_blog_results·trend·mobile_share·seasonality·duplicate·profile_fit·priority·keyword_opportunity·reason·data_date. 한·영 별칭, 띄어쓰기·대소문자·밑줄 무시, **모르는 열은 무시하되 알림**(`unknown_columns`), 같은 뜻의 열 둘이면 거절 |
| 블로그 칸 | 코드(`naver_a`)나 이름('네이버 A', 'Blogger 한글' …, `BLOG_NAMES :60-66`), 쉼표·`;`·`|`·`/` 로 여러 개 |
| 값 | 없음 표기(빈칸·`-`·`N/A`·`데이터 없음`)=None, 천 단위 쉼표·`%` 허용, 지표가 있으면 조회일 필수(열 또는 `--data-date`), 조회일은 오늘(UTC)+1일까지 |
| 검증 | 후보 규칙은 `Candidate` 가 그대로 거절(금지 표현·마크업 등), **줄 단위 거절**(줄 번호·이유), 나머지는 저장 |
| 중복 | 같은 `keyword_key`+같은 주제+블로그 부분집합이면 건너뜀(`find_duplicate :211`) → 다시 가져와도 겹치지 않음 |
| 저장 | 줄 검사는 보관함을 열기 전에 끝내고, 이미 있나 확인→저장은 `Store.add_candidates(plan)` **한 트랜잭션**(하나라도 실패하면 전부 저장 안 됨) |
| 내보내기 | 없음(`safe_cell :396` 규칙만 시험으로 먼저 고정) |
| 전략 확장 시 | `topic_cluster` 같은 새 열은 별칭표+`Candidate` 에 없으면 '모르는 열'로 **조용히 무시**됨(거절하지 않음) |

### 4.2 후보 연산(`service/candidates.py`)

| 연산 | 함수:줄 | 규칙 |
|---|---|---|
| 번호 고르기 | `resolve :86` | 순번(1~999, 만든 시각 순)·번호 전체·**앞 4자 이상**(겹치면 CANDIDATE_AMBIGUOUS) |
| 목록 | `list_candidates :149` | 읽기 전용(`ctx.reading_only()`), 상태·블로그 거르기(블로그는 `blogs` 에 포함된 것), 순번은 거르기 전 전체 기준 |
| 보기 | `show_candidate :187` | 연결한 글의 제목·플랫폼별 상태 포함 |
| 추가 | `add_candidate :266` | 중복이면 넣지 않고 기존 후보 알림, 한 트랜잭션 |
| 선택 | `select_candidate :340` | 블로그별 `selections` 기록, 같은 핵심 키워드를 같은 블로그용으로 프로필 `topic_reuse_days`(기본 90) 안에 이미 골랐으면 **경고만**(막지 않음), 추천 대상 밖 블로그도 허용(표시) |
| 보류·제외·검토 | `move_candidate :363` | `TRANSITIONS` 표대로, 아니면 CANDIDATE_TRANSITION_INVALID |
| 되살리기 | `restore_candidate :373` | REJECTED→REVIEW 만 |
| 지우기 | `delete_candidate :428` | **번호 앞 8자 이상 + `--yes`** 만(순번으로는 안 지움), 연결한 글은 남음, 깨진 후보도 번호로 지움. 복구 불가(휴지통 없음) |
| 글 연결 | `link_candidate :478` | `expected_revision` 낙관적 잠금, STORE_CONFLICT 시 최대 3번 재시도 |
| 보관함 상호작용 | 읽기: `ctx.reading_only().store()`(없으면 'missing', 옛 구조면 'old_structure' — 파일을 만들거나 올리지 않음) / 쓰기: `ctx.store()`(열면서 옛 구조를 올리고 `.v<판>.bak` 사본) | context.py:235-252 |

### 4.3 명령줄 입출력 계약(`service/cli.py`)

공통: JSON 은 `{"ok": <종료코드==0>, "command": "candidates list", "data": …}`, 오류는 `{"ok": false, "command", "error": {…}}`(`cli.py:1082,1090`). 종료 코드 **0 정상 · 1 처리된 오류 · 2 사용법 오류**(`:1-8`). 모든 출력은 `security.mask` 를 거침.

| 명령 | 접근 | JSON `data` 모양 | 종료 코드 특이점 |
|---|---|---|---|
| `candidates list [--status --blog --priority]` | 읽기 전용 | `candidates[]`(후보 24키+`ordinal`+`status_name`[+`priority_info`]), `total`, `shown`, `status`, `blog`, `store` | |
| `candidates show 번호` | 읽기 전용 | `candidate{…, project{project_id,title,statuses,error}, priority_info}` | |
| `candidates suggest [--blog --count --month --type]` | 읽기 전용 | `blogs[]{blog, profile_name, month, today, count, suggestions[], generated, filtered[{code,label,count,hidden}], hidden_ranks, seeds[], seed_total, guidance, notes, post_type}`, `store`, `limits[]` | `--blog` 는 5채널 키를 받지만 네이버 외에는 안내문만(`OTHER_BLOG_GUIDANCE`) |
| `candidates suggest --add 번호\|범위\|all\|"키워드" [--yes]` | `--yes` 없으면 읽기 | `blog, confirmed, items[]{label,action,reason,suggestion}, added[], late_skips[]` | 못 찾는 번호는 SUGGESTION_NOT_FOUND(아무것도 안 넣음) |
| `candidates add …` | 쓰기 | `added, candidate, duplicate_of` | |
| `candidates import-csv 파일` | 쓰기 | `file, summary, rows, added[], skipped[], rejected[]{line,reason}, unknown_columns[], blank_lines` | **거절 줄이 있으면 종료 코드 1·`ok:false`**(나머지는 이미 저장됨, `cli.py:512`) |
| `select·hold·reject·review·restore` | 쓰기 | `candidate, before, blog, warnings[], outside_recommended_blogs, again` | |
| `delete 번호8자 --yes` | 쓰기 | `deleted, ordinal, topic` | `--yes` 없으면 CONFIRMATION_REQUIRED(1) |
| `link·unlink` | 쓰기 | `candidate, project, changed, previous_project_id` | |

시험: `test_service_candidates_cli.py`(60)·`test_service_suggest_cli.py`(36)·프로세스 시험 `test_service_candidates_process.py`(18)·`test_service_suggest_process.py`(7).

---

## 5. `content/store.py` — SQLite 보관함

### 5.1 표·열·색인·파일

| 항목 | 내용 | 줄 |
|---|---|---|
| 파일 | `%LOCALAPPDATA%\ChanceblogDesktop\chanceblog.db`(`Workspace.store_path`), 저장소·프로그램 폴더 안은 `DATA_DIR_UNSAFE` 로 거절 | context.py:44-53,121 |
| 이름표 | `PRAGMA application_id = 0x43424450('CBDP')`, `user_version = SCHEMA_VERSION(2)`, `secure_delete=ON`, `foreign_keys=ON`(WAL 설정 없음 — 기본 저널) | store.py:44-45,305-306,358-359 |
| `projects` | project_id PK·title·revision·created_at·updated_at·data(JSON 원고) / 색인 `projects_updated` | :73-74 |
| `revisions` | (project_id, revision) PK·saved_at·data — 프로젝트당 50판 | :75-77 |
| `drafts` | project_id PK·text·saved_at(자동 저장) | :78 |
| `candidates` | **candidate_id PK · keyword_key · status · project_id(FK→projects, ON DELETE SET NULL) · revision · created_at · updated_at · data(JSON)** / 색인 `candidates_status(status, updated_at DESC)`·`candidates_keyword(keyword_key, status)` | :62-68 |
| 후보가 저장되는 방식 | **열은 조회·무결성용 5개**(keyword_key·status·project_id·revision·시각), **나머지 전부는 `data` JSON 한 덩어리**(project_id 제외). 채널·점수·만료일로 SQL 조회하려면 지금은 불가 → 파이썬에서 전부 읽어 거름(`list_candidates :763`) | :677-679,750-763 |
| 점검 | `check()` 가 JSON 과 열(keyword_key·status·revision·시각)이 같은지, 연결한 글이 있는지 본다 | :856-887 |

### 5.2 마이그레이션·사본·복구

| 항목 | 내용 | 줄 |
|---|---|---|
| 방식 | `MIGRATIONS = {1: _add_candidates}`(판 1→2), 한 번에 한 단계·한 트랜잭션, 판 번호도 같은 트랜잭션 안에서 올림 | :124,379-409 |
| 순서 | 쓰기 잠금(`BEGIN IMMEDIATE`) → 잠금 쥔 채 판 번호 재확인(다른 창이 이미 올렸으면 성공 처리) → 사본 `<파일>.v<번호>.bak` → 단계 실행 → `user_version` → COMMIT | :381-409 |
| 사본 | 읽기 전용 다른 연결로 SQLite backup, 임시 이름 `.tmp` 로 만들어 점검 후 이름 변경, 이미 있는 사본은 **덮어쓰지 않음**(같으면 재사용·다르면 `.v1.2.bak`…, 최대 20개 이름), 경로 260자 제한 사전 점검 | :431-480 |
| 실패 | 되돌려 파일 그대로. 잠김→`STORE_LOCKED`, 디스크 가득·읽기 전용·사본 불가→`MIGRATION_BLOCKED`, 그 외 `MIGRATION_FAILED`, 열 때 이름표·더 새 판(`STORE_VERSION_UNSUPPORTED`)·`quick_check`·표/열 모양 불일치→`STORE_CORRUPT`(**파일을 한 바이트도 안 바꿈**) | :363-377,411-424 |
| 읽기 전용 열기 | `Store.open(경로, migrate=False)` — 파일을 만들거나 올리지 않음, 옛 구조는 `needs_migration`, 후보 표가 없으면(`_version<2`) '후보 0개' | :257-301,658-660 |
| 백업·복구 | `backup(폴더)`(임시→점검→이름 변경, 10개 보관), `restore_from(백업, safety_folder)`(이름표·판·모양을 **바꾸기 전에** 확인, 옛 판 백업이면 올림) | :894-962 |
| DDL 고정 | 판 2 올리기 DDL(`_V2_CANDIDATES`)은 **고치지 않는다**(해시 시험). 표를 바꾸려면 판 3 단계를 따로 | :59-61, `test_content_migration.py:857-886` |

### 5.3 동시 실행 보호·후보 쓰기 규칙

| 항목 | 내용 |
|---|---|
| `service/lock.py` | **쓰지 않는다** — 글 올리기(`publish/<글번호>.lock`)·저장소 `.git/chanceblog-desktop-publish.lock` 전용(`pages_flow.py`·`connections.py` 만 사용, grep 확인) |
| 보관함 보호 | 쓰기는 모두 `Store._write(work)`(RLock + `BEGIN IMMEDIATE` … COMMIT, 실패 시 ROLLBACK, `:527`), 대기 5초(`BUSY_SECONDS`), SQLite 오류를 `STORE_LOCKED`·`DISK_FULL`·`FILE_WRITE_FAILED`·`STORE_CORRUPT` 로 번역(`:127-132`). 여러 프로세스 시험: `store_race_child.py`·`test_service_candidates_process.py` |
| 후보 저장 규칙 | `save_candidate(expected_revision)` 은 **내가 불러온 판에서 바뀐 것만** 저장(아니면 `STORE_CONFLICT`), 같은 판 같은 내용 재저장은 무시, 상태는 저장 시점에도 전이표 검사 |
| 본보기 패턴 | `add_candidates(plan)`: 쓰기 잠금 뒤 **지금 있는 후보를 읽어 `plan(existing)` 에 넘기고 돌려받은 새 후보를 모두 한 트랜잭션으로 저장**(plan 은 순수 계산, 안에서 Store 호출 금지) — 읽고 판단하고 쓰는 사이 끼어들 수 없다. Seed 저장소·후속 후보 생성도 이 패턴이면 된다 |
| 깨진 행 | 후보 한 행이 깨지면 `list_candidates` 가 CANDIDATE_CORRUPT 로 **목록 전체가 멈춤**(그 후보만 `delete` 로 지울 수 있음, `doctor` 가 안내) |
| **새 필드의 위험** | `from_dict` 가 모르는 칸을 거절하므로 판 번호를 올리지 않고 JSON 칸만 더하면 구버전이 새 후보를 깨진 것으로 보고 목록을 막는다 → 필드 추가도 `SCHEMA_VERSION` 을 올려 구버전이 `STORE_VERSION_UNSUPPORTED` 로 안전하게 멈추게 해야 함(추정·코드 추적 결과) |

### 5.4 새 표(Seed 저장소·후보 이력·보류함·캘린더) 또는 새 후보 칸을 더하려면 건드릴 곳

| # | 곳 | 할 일 | 깨질 수 있는 시험 |
|---|---|---|---|
| 1 | `store.py` 상수 | 새 DDL 묶음 `_V3_*` 를 **따로** 만들고(`_V2_CANDIDATES` 불변), `SCHEMA_VERSION = 3`(:45) | `test_content_store.py:183`(`(50,10,5.0,2)`), `test_content_candidates_store.py:885`, `test_content_migration.py:861` |
| 2 | `store.py` `MIGRATIONS` | `{1: …, 2: _add_topic_tables}`, 같은 `IF NOT EXISTS`·'다시 돌려도 안전'·'끝나면 모양 확인' 규칙 | `test_content_migration.py:862`(`set(MIGRATIONS)=={1}`) |
| 3 | `_SCHEMA`(:71-80)·`_SHAPES[3]`(:83-87 방식)·`_V3_INDEXES` | 새 파일 = 옛 파일을 올린 것이 되게 같은 DDL 을 `_SCHEMA` 에 추가, `_shape_problem` 의 색인 검사(`:99-104` 는 `_V2_INDEXES` 만 봄)를 3판까지 확장 | `DdlFreezeTest.test_the_step_is_safe_to_run_twice…`(`:897-909`: `LIKE 'candidates%'` 이름이 정확히 3개여야 함 → **새 표·색인 이름을 `candidates` 로 시작하지 말 것**, 예 `topic_seeds`·`candidate_history`) |
| 4 | `_has_candidates()`(:658) 같은 가드 | 읽기 전용으로 연 판 2 파일에는 새 표가 없으므로 `_version >= 3` 가드 | `test_content_migration.py` 읽기 전용 열기 구간(:1024-1058) |
| 5 | `check()`(:856)·`restore_from`(:929) | 새 표 점검·판 3 백업 복구 모양 검사 추가 | `test_content_store.py`·`test_content_migration.py` |
| 6 | `Candidate` 새 칸 | `_KEYS`(:355)·dataclass·`_validate`·`to_dict`·`LABELS`·(JSON `schema` 올릴지 결정 — `from_dict` 는 `schema==SCHEMA` 만 받음) | `test_content_candidates.py` JsonShapeTest(:567-580)·LABELS(:548)·`test_content_candidates_batch.py`·`test_candidate_csv.py` |
| 7 | 후보 연결 새 표 | 후보 삭제가 하드 삭제이므로 새 표의 `candidate_id` 외래 키는 ON DELETE 정책(CASCADE/SET NULL)을 정해야 함 | `test_content_candidates_store.py` |
| 8 | 문서·오류 코드 | `docs/ARCHITECTURE.md` §9·§10, `DECISIONS.md` 새 D-nn, 새 오류 코드는 `errors/catalog.py`+`docs/TROUBLESHOOTING.md` 에 코드·칸(slot) 일치 | `test_errors_catalog.py`·`test_repo_layout.py`·`test_content_candidates.py` DocumentTest(:176-215) |
| 9 | 시험 도움 파일 | v1 파일 생성기 `tests/store_v1.py`, 충돌 자식 프로세스 `store_crash_child.py`·`store_race_child.py` | — |

---

## 6. 프로필·유사도 — `content/profiles.py`·`check/profile_options.py`·`check/similarity.py`

### 6.1 `NaverProfile`(frozen dataclass, `profiles.py:134-160`) 전체 필드

| 필드 | 타입·기본 | 검증 | 용도 |
|---|---|---|---|
| key | `naver_a`·`naver_b` 만(`KEYS :18`) | 그 외 CONTENT_INVALID | 블로그 구분 |
| display_name | 1~60자 필수 | 한 줄 | 표시명 |
| blog_url | 필수 | https·`blog.naver.com`/`m.blog.naver.com`·경로 있음·쿼리/자격 없음(`_blog_url :120`) | **네이버 주소만 가능** |
| topic·audience·tone·image_spec·publish_cycle | "" | ≤200자 한 줄 | **`topic` 이 제안의 첫 씨앗 출처** |
| disclosure | "" | ≤300자 | AI 활용 고지(비면 기본 문구) |
| categories | () | ((원고 분류, 네이버 카테고리)…) ≤50쌍 | 제안의 둘째 씨앗 출처, 카테고리 변환 |
| default_tags / forbidden_phrases | () | ≤30개×30자 / ≤100개×60자, 중복 불가 | 셋째 씨앗 / 금지 표현 |
| min_chars·max_chars·max_title_chars·paragraph_max_chars·max_tags | 800·6000·60·180·10 | 정수 범위 | 글 길이·문단·태그 |
| intro_style·difficulty·ending_style | "" | 한 줄·마크업 거절 | 초안 안내(저장만) |
| subheading_min / max | **3 / 5** | 1~20 | 소제목 수 경고(`check/profile_options.py`) — 전략 §16 '4개 이상'보다 낮은 기본값 |
| excluded_topics | () | ≤100개×60자·list/tuple 만·마크업 거절 | 제안의 제외어·글 경고 |
| topic_reuse_days | 90 | 0~3650 | 같은 키워드 재선택 경고·제안의 '최근 선택' |
| post_type | '정보형' | 5종 | 기본 글 유형(적합도 +10) |

### 6.2 저장·로드·검증

| 항목 | 내용 | 줄 |
|---|---|---|
| 저장 위치 | **보관함이 아니라 `settings.json`**(`naver_profiles` 아래 키별 dict), `write_json`(임시 파일→fsync→교체) | context.py:159-207,73-87 |
| 코드 기본값 | 프로필이 없으면 `NAVER_PROFILE_MISSING`(제안은 안내문+빈 목록), 코드에 내장된 기본 프로필은 없음 | context.py:186-190 |
| 설정 파일 검증 | `set(raw) == {"schema","repo_path","naver_profiles"}`·`schema==1`·프로필 키 ⊂ `NAVER_KEYS` — **다른 최상위 칸이 있으면 SETTINGS_INVALID** | context.py:165-176 |
| 저장 모양 | `to_dict`: 새 8개 칸은 **기본값에서 벗어난 것만** 적음(옛 프로필 저장 모양이 한 글자도 안 바뀌게 — 시험 고정) | profiles.py:217-229, 시험 `test_naver_profile_options.py:61-63`(옛 JSON 왕복·저장 키 고정)·`:85`(`_KEYS` = dataclass 필드) |
| 읽기 | `from_dict`: 모르는 칸 거절·빠진 칸은 기본값(key·display_name·blog_url 필수), 값 오류는 `SETTINGS_INVALID` 로 번역 | profiles.py:232, context.py:192-196 |
| 변경 경로 | CLI `naver-profile set`(`service/naver_flow.py`) → `Settings.save_naver_profile` | naver_flow.py:133-138 |

### 6.3 유사도 — `check/similarity.py`(A/B **초안** 비교용) ↔ 전략 §17

| 항목 | 현재 | 전략 §17 |
|---|---|---|
| 방식 | NFKC·구두점 제거 후 **글자 3개 묶음(3-gram) Jaccard**(본문·도입부·태그 낱말), 제목은 편집거리 비율(양방향 평균), 문단 길이 흐름, 이미지 식별자 겹침 — AI 없음 | 방식 미정(유사도 숫자+키워드·검색 의도·Cluster·Angle·독자 결합) |
| 가중치 | 제목 .20·도입 .15·본문 .35·구성 .10·이미지 .05·태그 .15(`:23`) | — |
| 임계값 | 전체 경고 0.40·높음 0.60 / 본문 .35·.60 / 제목 .60·.85 / 도입 .50·.75(`Thresholds :26-36`), 항목 하나라도 넘으면 그 단계 | 채널 내 0~39/40~59/60~74/75↑ 4구간 |
| 결과 처리 | `ok·warn·high` 3단계, `high` 는 운영자 직접 승인(`NAVER_SIMILARITY_HIGH`) 없으면 복사 단계 불가 | 숫자만으로 삭제 금지·'다른 관점 필요'·'업데이트 후보' |
| 대상 | **네이버 A·B 글 한 쌍**(패키지) — 후보 단계·채널 간(GitHub/Blogger)에는 안 씀. `draft_plan.compare_plans` 가 A/B 계획 비교에 재사용 | 후보·기존 글·채널 간 |
| 제안 단계 중복 | 별도 구현: 제목 낱말집합 Jaccard `SIMILAR_FROM=0.6`, 키워드 겹침 0.7 | — |

→ 숫자 40·60 은 우연히 비슷하지만 75% 구간·4단계 의미·결합 판정은 없다. 두 구현(3-gram vs 낱말집합)이 공존하므로 후보 단계 판정은 **새 모듈**로 두고 `check/similarity.py` 는 초안 단계용으로 그대로 두는 편이 안전(추정).

### 6.4 5채널 표현의 걸림돌

| # | 걸림돌 | 근거 | 영향 |
|---|---|---|---|
| 1 | 프로필 클래스가 네이버 전용(`KEYS`·네이버 주소 검증·네이버 카테고리) | profiles.py:18,120-130,166 | GitHub·Blogger 프로필 저장 불가 |
| 2 | `settings.json` 엄격 검증 — 새 최상위 칸 불가 | context.py:173-175 | 채널 프로필 추가 시 `SETTINGS_SCHEMA` 올림이나 완화 필요. 더 안전한 길: `connections.json`·`quota_state.json` 처럼 별도 파일(`Workspace` 프로퍼티) 또는 보관함 새 표 |
| 3 | `service/suggestions.profile_for` 가 네이버 외에는 None 반환, `OTHER_BLOG_GUIDANCE` | suggestions.py:63-72,25 | 제안 서비스가 네이버 2채널 한정 |
| 4 | 전략의 채널 프로필 항목(언어·지속형/실시간 비율·6항목 가중치·허용 확장·캘린더·수익화 태그·Search Trend 사용 여부·상위 N·Cluster 상한·중복 기준)이 프로필에 없음 | §31-3 대비 | 새 `ChannelProfile`(순수 데이터) 필요 |
| 5 | 채널 키 이름: 전략 `blogger_a`(한글)·`blogger_b`(영문) ↔ 코드 `blogger_ko`·`blogger_en` | status.py:21-29 | 매핑표 필요(A=ko, B=en) |
| 6 | 후보는 1~5채널, 전략은 후보 1채널(최대 2채널 재사용) | candidates.py:316-323 | 정책 차이 — 코드 제한이 없어 새 규칙 필요 |
| 7 | 이미 5채널 키를 받는 곳(걸림돌 아님) | `PLATFORMS`(status.py:29), `Candidate.blogs`, `suggest(blog=…)` 의 `st.PLATFORMS` 검사(:560), CSV `BLOG_NAMES`, `PLATFORM_KO` | 엔진·후보·CSV 는 5채널 가능 |
| 8 | `NaverProfile` 에 작성자 전략 정보가 없음: `excluded_topics`(제외 키워드 1단계)·`topic`(자유 글) 만 | — | Seed 3단계는 프로필 밖 저장소 필요 |

---

## 7. 재사용 지도 (전략 영역별 판정)

시험 수 = `def test_` 개수(시험 파일 줄 수). 'ARCH/DEC' = 문서와 값 일치를 시험이 확인.

| 영역 | 판정 | 재사용할 것(파일:줄) | 새로 필요한 것 | 이유·주의 | 건드리면 깨질 수 있는 시험 모듈 |
|---|---|---|---|---|---|
| Seed 저장소 | **새로 만들기** | 씨앗 정화 규칙 `seed_report`·`is_secret_shaped`·`is_risky`(suggest.py:109-153)는 '씨앗 입력 검증'으로 그대로 재사용 | 새 표(`topic_seeds`·대분류/중분류·우선/제외·태그·마지막 선택일)+판 3 올리기, 공통/채널별 구분, 승인 흐름 | 지금 씨앗은 프로필 낱말에서 즉석 추출·미저장. 130개 규모는 JSON 덩어리보다 표가 낫다(추정) | `test_content_store`(70)·`test_content_migration`(69)·`test_content_candidates_store`(88)·`test_suggest`(113) |
| 확장어 규칙 | **확장해서 재사용** | `FRAMES` 23틀·`suggest_text.render/attach`(조사)·`generate()`(suggest.py:268) | Seed 유형(제품·장소·서비스·PC 부품·문제·습관·이슈·정책) → 허용 확장어 표, 채널별 확장 방향, 의미 안 맞는 조합 차단 관문 | 틀은 글 유형 중심·채널 무관. 새 관문은 `_gate` 순서에 끼움(`GATE_ORDER :44`) | `test_suggest_data`(12: 틀 규칙·경험 낱말 금지·약 5만 조합 전수 `:158-198`)·`test_suggest`·`test_suggest_text`(16) |
| 계절 캘린더 | **확장해서 재사용** | `SEASONS` 구조(SeasonItem)·`season_fit`·`related_items`(suggest_score.py:152-168)·월 입력(`--month`) | 일정 필드(준비 시작·발행 시작/종료·피크·반복·채널·Trend 상태·마지막 평가일), 채널별 캘린더, **`_is_related` 부분 문자열 결함 수정**(그래픽카드→카드) | 실측 오작동이 Naver B 11월 1위를 만든다 | `test_suggest_score`(29)·`test_suggest_data`(월별 8~15항목·'입니다' 끝·수치 금지)·`test_suggest`(순서·점수 고정) |
| 점수(6항목 채널별 가중치) | **새로 만들기**(결합 틀은 재사용) | `combine()`(None 요인 제외 재분배)·`clamp`·`level_of` 패턴(suggest_score.py:72-93) | 6요인 계산(채널 적합도·작성 가능성·차별성·시기·근거·수익화)과 채널별 가중치 표(프로필 데이터), 점수 스냅샷 저장 | 기존 `WEIGHTS`(30/20/20/15/15)는 D-29·시험이 못박음 → **수정하지 말고 병행** | `test_suggest_score`(:31-41)·`test_suggest_assess`(22)·`test_service_suggestions`(47)·ARCH/DEC D-29(`test_repo_layout`) |
| 중복 판정 | **확장해서 재사용** | `TitleIndex`(낱말집합 색인, suggest.py:156)·`tx.jaccard`·`keyword_key`·`find_duplicate`(service/candidates.py:211) | 40/60/75 4구간, 채널 간 최대 2채널 규칙, Topic Cluster/Angle/검색 의도/독자 결합 판정, 자동 삭제 금지 유지 | `check/similarity.py` 는 초안용 3-gram 이라 그대로 두고 후보 단계는 별도(추정) | `test_suggest`·`test_service_suggestions`·`test_check_similarity`(36)·`test_service_candidates`(121) |
| 상태 구간(80/65/50) | **새로 만들기** | `level_of` 패턴만 | 파생 구간 값(`recommendation_band`)·`review_expires_at`·보류/제외 사유 | 작업 상태 `TRANSITIONS` 는 ARCH §9·시험이 고정 → 건드리지 않음. `ui/adapters.STATUS`(ui/adapters.py:33)가 5상태를 가정 | `test_content_candidates`(121: DocumentTest `:176-215`)·`test_ui_adapters`(25)·`test_service_candidates` |
| 작성 가능성 검사 | **확장해서 재사용** | `Candidate.new` 형식 검사(suggest.py:320)·`post_types.template_steps`(틀마다 6단계)·`claims`/`premise_of`(경험 지어내기 차단) | 8항목 검사 결과·7단계 자동 보완·'작성 기반 부족' 사유 | 틀이 이미 소제목 6개라 구조는 만족. 프로필 소제목 기본 3(<4) 확인 필요 | `test_content_post_types`(37)·`test_content_draft_plan`(126)·`test_check_claims*` 5개 |
| 후속 후보 | **새로 만들기** | 입력은 `store.list()`/`load()` 의 글(제목·`published_url`)·`recent_days`·`TitleIndex` | 글당 ≤3 생성·중복 방지 키(project_id+후속 유형)·`source_type=follow_up` | 이름 충돌: `FOLLOW_ON`(candidates.py:61)은 상태 대응 | `test_content_candidates`·`test_content_draft_plan`(후보 연결) |
| 90일 보류함 | **새로 만들기** | `HOLD` 상태·`Store.set_candidate_status`(store.py:765) | 만료일·재평가 트리거·보류 사유, 90일 뒤 정리 시 **이력 표**(정규화 키워드·요약·처음 생성일·마지막 평가일·보류/제외 사유) | 후보는 최신 행만 저장(판 기록 없음)·삭제는 하드 삭제 → 이력은 별도 표 필요 | `test_content_candidates_store`·`test_content_migration`·`test_service_candidates_cli` |
| 채널당 상위 5·Cluster ≤2 | **확장해서 재사용** | `_diversify`(suggest.py:423-457: 몫 상한+모자라면 풀기 패턴), `count` 옵션 | Cluster 필드·상한, 80↑ 부족 시 65~79 보충·50~64 보충 금지, '기준 충족 N개' 안내 | `DEFAULT_COUNT=10`·`MAX_COUNT=50`·번호 고정 규칙이 CLI·시험에 묶여 있음 → 5개는 채널 프로필 값으로 | `test_suggest`(몫·번호)·`test_service_suggest_cli`(36)·`test_service_suggestions` |
| 데이터 부족 재정규화 | **그대로 재사용** | `combine`(suggest_score.py:81-93)·`DataAge`·'외부 데이터 없음' 표기 | `data_status` 값('API 장애' vs '실제 부재')만 추가 | 이미 전략 §15 와 같은 규칙 | `test_suggest_score`·`test_suggest_assess` |
| 협찬 태그 | **새로 만들기** | — (`check/claims.py` 의 협찬 낱말 규칙은 '지어내지 않기' 검사용이라 건드리지 말 것) | `monetization_tags` 칸·태그 사전·경제적 이해관계 9종·고지문 자동 배치, `_RISKY` 의 '체험단' 씨앗 제외와의 조정 | 현재는 협찬 개념 0 | `test_candidate_csv`(67)·`test_content_candidates`·`test_check_claims*` |

---

## 8. 위험·권고 (순서 제안 — 추정 포함)

| 순위 | 제안 | 이유 |
|---|---|---|
| 1 | **엔진을 새 모듈로 분리**(`content/` 아래 새 파일들)하고 `suggest*.py`·`candidates.py` 는 건드리지 않는다 | 후보·CSV·제안 시험 약 770개(보관함 시험 포함 약 920개, `def test_` 개수 합)와 문서(D-29·ARCH §9)가 값을 못박고 있어 직접 수정 시 파급이 큼 |
| 2 | 저장은 **판 3 한 번**으로(새 표 + 후보 JSON 새 칸 + 필요하면 `ALTER`/부속 표) | 필드 단독 추가는 구버전이 목록 전체를 막음(§5.3). DDL 고정 시험·이름 규칙(`candidates%` 회피) 준수 |
| 3 | 계절 매칭 결함은 Naver B 시험 운영 전에 고친다 | 11월 1위가 무의미한 제안(실측) |
| 4 | 상대지수는 새 필드, `search_demand` 는 실제 횟수 출처 있을 때만 | §2.8 |
| 5 | 채널 프로필·가중치·확장 표는 코드 상수가 아니라 **데이터**(별도 파일/표)로 | `settings.json` 엄격 검증·`NaverProfile` 네이버 전용(§6.4) |
| 6 | `status` 5종은 그대로, 점수 구간은 파생 값 | ARCH §9 전이표·`ui/adapters.STATUS` 보호 |

## 9. 확인 못 한 것

- 전체 시험 통과 여부(실행 안 함), `ui/` 화면이 후보 필드를 어디까지 쓰는지 상세(`ui/adapters.py:53-62` 의 `to_topic` 만 확인), CI 구성.
- `draft_plan.py` 가 후보 칸을 어떻게 읽는지 상세(다른 조사원 몫) — 새 필드를 더해도 `Candidate` 를 그대로 받는 코드(`draft_plan.py:23`)는 모르는 칸을 무시하는지 **(확인 못 함)**.
- 실제 운영자 PC 의 보관함 내용·옛 `.v1.bak` 존재 여부.
- `quota.py`·`connections.py`(Search Trend 한도)·네이버 Search Trend 어댑터 설계 — 다른 조사원 담당.
