# 허용 목록(Source Registry)·외부 호출 관문·소스 정책 스위치

> 구현: 2026-11-09, 변경 등급 T2(`pipeline/` 코어·`generator.py`·레지스트리 스키마). 독립 검증(조건부 통과, 높음 0건)의 지적을 반영한 수정 라운드(2026-11-09, 결함 D-170–D-178)와 병합 준비 라운드(2026-11-10, 결함 D-179 — 합성 트리 등록·관문 인정 오판 정정·운영자 결정 007 반영)를 거쳤고 운영자 병합 대기. **켜는 것(`source_policy: allowlist`, Provider `enabled: true`)은 T3** — 이 변경(구현 병합 시점)은 `pipeline/blogs.json` 의 값을 바꾸지 않았고 허용 목록의 모든 Provider 는 꺼져 있었다(켠 뒤의 상태는 14절과 `FACT_PATH.md` §15 의 상태 줄).
> 근거: 운영자 결정 2026-11-09(외부 출처 아키텍처 방향 변경 · Desktop 독립 운영 기준 · R-216 조립 전 반영). 상위 문서: [`CHARTER.md`](./CHARTER.md)·[`SECURITY_GUARDRAILS.md`](./SECURITY_GUARDRAILS.md)(G-L2 외부 입력은 데이터), 구조: [`ARCHITECTURE.md`](./ARCHITECTURE.md).

## 1. 한눈에

1. **자동으로 쓰는 외부 자료는 권리·약관·상업·AI 이용이 분명한 구조화 데이터(API·CSV·데이터셋)뿐**이다. 외부 RSS 요약·기사·페이지 본문·검색 스니펫·외부 사진은 발행자가 정부여도 **유형만으로 Tier 3(자동화 제외)** 이다.
2. 그런 자료는 **허용 목록(`pipeline/source_registry.json`)** 에 등록되고 이용 조건 **7칸이 모두 확인된(UNKNOWN 0) Provider** 만 켤 수 있다. 한 칸이라도 UNKNOWN·근거 없음(`IMPLIED`·`NOT_ADDRESSED`·`NOT_READ`)이면 그 Provider 는 자동화에서 꺼진다(검증기가 켜는 저장을 거부).
3. 외부로 나가는 호출의 **주소는 한 관문(`pipeline/egress.py`)이 판정**한다 — 통과하는 것은 고정 운영 호스트의 **허용 목적·허용 경로**와 허용 목록의 ACTIVE Provider 호스트(목적 `fact`)뿐이다. 지금 코드에서 관문(`check_url`)을 직접 거치는 곳은 규칙 기반 Fact 경로의 호출 한 곳이다(`generator.py` 의 `fact_opener` 가 만든 호출 도구가 호출 직전에 `egress.check_url(url, "fact", sources)` 를 부른다 — 허용 목록 밖·ACTIVE 가 아닌 제공처는 요청이 나가지 않는다). 콘텐츠 경로 셋은 `allowlist` 에서만 `source_policy.egress_gate` 가 막는다 — 그 밖의 접속 지점은 이유와 '무엇이 막는지'와 함께 등록돼 있다. 자료를 AI 처리기에 넘길 때의 관문은 `egress.check_ai_input` 이고 `ai_use` 가 NEVER 인 Provider 는 항상 거부한다(7절·14절). **호출 목록 시험(AST)은 알려진 모양의 호출을 모아 등록 목록과 비교할 뿐 우회를 막는 보증이 아니며, 사람 검토가 마지막 방어선이다**(잡지 못하는 모양은 7절의 사각지대 표).
4. 레지스트리 `chance.source_policy` 한 값이 **`legacy`(기본 — 옛 동작과 같음, 출력이 바이트까지 같다)** 와 **`allowlist`(새 모드)** 를 가른다. `allowlist` 는 피드·기사 페이지 발췌·구글 뉴스 해석기 호출이 0이고 외부 제목·요약·태그가 프롬프트·이력·로그에 들어가지 않으며, ACTIVE 콘텐츠 Provider 가 0 이면 **초록으로 끝나는 '일 없음'** 이다. **켠 뒤의 상태(새 글 0·36시간 뒤 경보 등)는 12절에 있다 — FACT 2단계 연결 전에는 켜지 않는다.**
5. 허용 목록은 Tier 감사표(2026-11-09, 69행) 중 데이터 출처 56 Provider 에 접근 경로별로 쪼갠 6곳(14절)을 더한 **62 Provider** 이고 **ACTIVE 는 1**(`noaa_swpc_json` — 규칙 기반 Fact 경로 전용) 이다. 운영자 결정 007(규칙 기반 경로에서만 AI 입력 칸을 판정에서 뺀다)로 구조화 API 세 곳이 '켤 수 있는 후보'가 됐고, 그 가운데 NOAA 제공처 조사(2026-11-10)로 칸·경로·호출 한도·출처 문구가 확인된 `noaa_swpc_json` 하나를 켰다(규칙을 모두 통과 — `enabled: true` 는 T3 별도 PR 로 바꿨다). 나머지 61곳은 모두 꺼져 있다. 다른 제공처를 켤 때도 켜기 전에 사람이 약관을 읽고 증거와 함께 PR 로 올린다.

## 2. 이 일이 맡는 제한 재개 필수 항목(1–5)

| # | 필수 항목 | 보장 | 어디서·어떻게 시험하나 |
|---|-----------|------|------------------------|
| 1 | 일반 웹 크롤링 경로 비활성 | `allowlist` 에서 피드 20개·기사 페이지 발췌·구글 뉴스 해석기를 읽지 않는다(호출 0). 외부 호출 주소는 `check_url` 한 관문이 판정하고 허용 목록 밖 호스트는 거부 | `tests/test_generator_source_policy.py`(urlopen 을 막은 채 `main()` 을 돌려 0 단언), `tests/test_egress.py`(관문 판정·호출 목록 AST — 보증 아님) |
| 2 | Pew 웹페이지·RSS 비활성 | 허용 목록의 `pew_rss`·`pew_html` 은 `자동화 제외`·`enabled: false`, `allowlist` 에서 소스 이름 `Pew Research Center` 를 읽지 않는다 | `AllowlistFetchTest.test_pew_is_not_read_by_name`, `RealFileTest.test_the_pew_web_page_and_rss_are_both_excluded_and_disabled` |
| 3 | Tier 0–2 허용 목록만 | 허용 목록 파일 + 관문 검사. Tier 3·4·UNKNOWN 은 ACTIVE 가 될 수 없다 | `tests/test_source_registry.py`·`tests/test_source_registry_007.py`(규칙 A1–A11 경계 시험), `tests/test_egress.py` |
| 4 | UNKNOWN Provider 비활성 | 검증기가 7칸 중 UNKNOWN·근거 없음이 있는 Provider 의 ACTIVE 저장을 거부한다(`validate_registry`) | `ActiveRulesTest`(칸 하나씩 UNKNOWN 으로 바꾸기) |
| 5 | 외부 본문·기사·해설문 저장과 AI 입력 금지 | 프롬프트 조립부에서 외부 텍스트(제목·요약·태그·링크·출처 이름)를 뺀다 + 이력 `topic`·로그·탈락 기록에 외부 제목을 쓰지 않는다 | `AllowlistPromptTest`·`AllowlistHistoryAndLogsTest` |

## 3. 구성 요소

| 파일 | 역할 | 입출력 |
|------|------|--------|
| `pipeline/source_registry.json` | 허용 목록 정본(Provider 62, 켜진 것은 `noaa_swpc_json` 하나 — 나머지는 `enabled: false`). 증거·링크 없이 기관·문서 이름만 | 데이터 |
| `pipeline/source_registry.py` | `validate_registry`(순수)·`load_registry`·`Registry`·`Provider`(frozen)·`split_https_url`·허용 목적 `ALLOWED_PURPOSES`·AI 처리기 정책 검증·로더, `ai_use`·구조화 호출 한도(`RateLimit`)·`parse_rate_limit`·출처 문구 모양 검증 | 파일 읽기(로더·`main` 뿐), 시각을 읽지 않음 |
| `pipeline/ai_processor_policy.json` | AI 처리기(Gemini) 정책 11칸(출처가 아니라 처리기라 허용 목록 밖). 실행 중에는 읽지 않는다(10절) | 데이터 |
| `pipeline/egress.py` | 외부 호출 관문 `check_url`·운영 호스트 규칙 `OPS_RULES`·검사된 opener `build_checked_opener`·최종 주소 재판정 `check_final_url`·AI 입력 거부 `check_ai_input`·호출 예산 `CallBudget`·`budgeted`·`run_call_cap`·등록 목록 `EGRESS_EXCEPTIONS` | 판정 함수는 없음(요청을 보내지 않는다) — opener 를 쓰는 쪽이 보낸다. 호출 예산은 한 실행의 메모리뿐(새 영구 상태 없음) |
| `pipeline/source_policy.py` | 스위치 값 검증·읽기, `allowlist` 규칙(일 없음 판정·프롬프트 입력·최근 제목·후보 필터·관문 호출), legacy 알림 한 줄 `legacy_policy_notice` | 레지스트리·허용 목록 읽기 |
| `generator.py` | 21줄: 피드·페이지 발췌·해석기를 관문 뒤로, 프롬프트 입력 정화, 후보 필터, 새 결과 코드 | 기존과 같음 |
| `pipeline/registry.py` | `source_policy` 값 검증 호출 2줄 | 기존과 같음 |
| `tests/egress_scan.py` | 호출 지점 스캐너(AST — 알려진 모양)·스캔 범위·워크플로 yml 훑기. 시험과 합성 점검이 함께 쓴다 | 소스 읽기뿐 |
| `tests/test_source_registry.py`·`test_source_registry_007.py`·`test_egress.py`·`test_egress_budget.py`·`test_source_policy.py`·`test_generator_source_policy.py`·`test_source_policy_docs.py`·`source_policy_scenarios.py`(공용) | 위 모두의 시험(네트워크·시계 없음) | — |

## 4. 허용 목록의 모양(Provider 하나)

| 칸 | 뜻 |
|----|----|
| `provider_id`·`name`·`class` | 식별자·이름·종류(`data` 출처 / `image` 외부 사진 / `internal` 자체 / `ops` 운영 도구). **`enabled: true` 는 `data` 만** |
| `policy` | 7칸 `commercial_use`·`automated_access`·`derivative_use`·`storage`·`ai_input`·`attribution`·`license`. 칸마다 `state`(ALLOWED·CONDITIONAL·DENIED·UNKNOWN)·`basis`(EXPLICIT·STANDARD_LICENSE·STATUTE·IMPLIED·NOT_ADDRESSED·NOT_READ)·`evidence`(링크 없이 문서 이름)·`read_at`(열람일) |
| `strict_tier` | **실행 기준.** 0–4. 7칸에서 다시 계산한 값(`computed_strict_tier`)보다 낮게 적힐 수 없다 |
| `permissive_interpretation` | 참고용(표준 공개 라이선스가 목적 제한 없는 재사용을 허락하면 IMPLIED 를 허용으로 읽은 값). **실행에 쓰지 않는다** |
| `effective_status` | `자동화 가능`·`자동화 제외`·`참고 전용`·`완전 제외`. 저장된 값이 `자동화 가능` 인데 7칸·경로 유형 계산이 그렇지 않으면 거부(S7), 켜려면 `자동화 가능` 이어야 한다(A9) |
| `access[]` | 경로 `kind`(`api`·`csv`·`dataset` 구조화 / `rss`·`html`·`image` 일반 웹·사진), `hosts[]`(정확 일치), `paths[]`(경계를 지키는 접두어 — **ACTIVE 는 비우거나 호스트 전체(`/`)로 둘 수 없다**, A10), `auth`(`NONE` 키·로그인 불필요 · `KEY` 키 필요 · `UNKNOWN` 모름), `rate_limit`(제공처가 공개한 `N/minute` 꼴 문구, 공식 수치 한도가 없다고 확인한 구조화 객체, 또는 모르면 null — **ACTIVE api 경로는 알려져야 한다**, A11·S10), `robots_checked_at` |
| `snapshot` | 읽은 약관 문서 이름 `terms_pages`(빈 이름·공백은 이름이 아니다, A8)·`read_at`·`content_hash`(빈 값 허용)·`expires_at`(점검 기한 — 지나면 ACTIVE 가 아니다) |
| `attribution_template`·`exceptions[]`·`retention_days`·`reference_hosts[]` | 출처 문구(조립기가 글 끝에 그대로 붙이는 사람이 쓴 일반 문구 — AI 를 거치지 않는다. 자리 표시 `{title}`·`{date}`·`{url}` 만, S9)·적용 제외(제3자 자료·로고·이미지·개인정보·읽지 않는 필드)·저장 기간 제한·글이 인용만 하는 호스트(자동 접근 경로 아님 — 거부 사유 설명에만 쓴다) |
| `ai_use` | 우리 쪽 약속(선택, 기본 `BY_CELL`). `BY_CELL` 은 7칸을 모두 판정(지금 동작 그대로)하고 `NEVER` 는 '이 Provider 의 자료는 AI 처리기에 넘기지 않고 규칙 기반 경로에서만 쓴다' 는 뜻이라 strict 판정(`computed_strict_tier`·A2·A3)이 **`ai_input` 칸만 건너뛴다**(나머지 6칸은 그대로 — 하나라도 UNKNOWN·IMPLIED·DENIED 면 막힌다). 그 칸이 DENIED·IMPLIED 여도 우리가 AI 를 쓰지 않으므로 제공처 약관과 충돌하지 않고(근거 이름·열람일 기록 A8 은 그대로 요구), 그 대신 `egress.check_ai_input` 이 그 자료의 AI 입력을 **항상 거부**한다. **아무것도 켜지 않는다** — `enabled` 는 따로 |
| `own_data_only` | 우리 쪽 약속(선택, 기본 false). true 는 '이 항목이 읽는 값은 모두 제공처 자신이 만든 것이다 — 제3자가 제공한 필드·파일은 읽지 않는다(어댑터의 필드 화이트리스트가 지킨다)' 는 뜻이다. '공공영역·연방정부 저작물' 같은 법적 주장을 담은 출처 문구는 이 값이 true 인 항목만 쓴다(S11) |
| `enabled` | **기본 false.** 켜는 것은 T3 |

**`effective_status` 계산**(`computed_status`): Tier 4 → `완전 제외` · 외부 사진(`class: image`) → `자동화 제외` · Tier ≤ 2 이고 **모든 경로가 구조화** → `자동화 가능` · Tier ≤ 2 인데 rss·html·image 경로가 있으면 `자동화 제외`(경로 유형 규칙) · Tier 3 이고 경로가 있으면 `자동화 제외`, 경로가 없으면(글이 인용만 하는 출처) `참고 전용`. 한 Provider 에 구조화 경로와 일반 웹 경로가 함께 있으면 켤 수 없다 — 경로를 나눠 판정한다(예: 통계 API 와 보도자료 RSS 는 다른 Provider).

**초기 내용**: 감사표 69행 중 `class` 가 data-source 인 64행에서 AI 처리기 1(Gemini — `ai_processor_policy.json` 으로), 분류 틀 2(공공누리·공공데이터포털 이용 정책 — Provider 가 아님), 묶음 행 5(호스트·경로가 없는 `prev_*`)를 뺀 56 Provider 에, 접근 경로별로 쪼갠 6곳(14절)을 더한 **62 Provider**: strict Tier 1 이 2, 3 이 46, 4 가 14, 상태는 `자동화 가능` 1·`자동화 제외` 33·`참고 전용` 14·`완전 제외` 14, 종류는 `data` 60·`image` 2(Unsplash·NASA 이미지). 원래 56곳의 7칸 계산 결과(저장 등급·상태·계산 등급·계산 상태)는 쪼개기 전과 바이트까지 같다(`ai_use` 기본값은 예전 계산 그대로). 칸 값은 감사의 그룹별 판정 파일에서 그대로 옮겼고 감사표 기호와 어긋나는 칸은 0이다(새 6곳 가운데 NOAA 항목의 7칸은 2026-11-10 조사로 다시 대조했다). 공공데이터포털 데이터셋 6곳과 미국 NWS API(감사 보강 7행)는 감사표 69행에 없어 이 목록에 넣지 않았다.

## 5. 검증 규칙(`validate_registry(data, today)`)

문제 문장은 `provider_id: [규칙번호] 설명` 꼴이고 시험이 번호 태그로 규칙마다 통과·탈락 예문을 확인한다. 모양 규칙(S)은 모든 Provider 에, ACTIVE 규칙(A)은 `enabled: true` 인 Provider 에만 적용한다(꺼져 있으면 UNKNOWN·rss·html 이어도 문제가 아니다). 출처 문구(S9·S11)와 호출 한도 객체(S10)의 모양은 꺼진 항목도 본다.

| 규칙 | 내용 | 통과 예 | 탈락 예 |
|------|------|---------|---------|
| S1 | 필수 칸·형식(7칸 모두, 알 수 없는 칸 없음). 파일 최상위는 `_doc`·`schema_version`(정수 1 — `true`·`1.0` 은 안 됨)·`providers` 만 | 7칸이 다 있음 | 칸 하나 누락·`access` 가 객체·최상위 칸 이름 오타 |
| S2 | 열거값(class·state·basis·kind·status·Tier 0–4·`ai_use`) | `ALLOWED/EXPLICIT`·`ai_use: NEVER` | `MAYBE`·Tier 5·`ai_use: never` |
| S3 | `provider_id` 중복 금지 | 서로 다른 id | 같은 id 두 번 |
| S4 | 호스트는 소문자 이름뿐(스킴·경로·포트·와일드카드·IP·끝 점 없음), 경로 접두어는 `/`로 시작(`..`·`//`·`%` 없음) | `api.fixture.example` | `127.0.0.1`·`*.x.example`·`/a/../b` |
| S5 | 날짜는 `YYYY-MM-DD` 또는 null | `2026-11-09` | `2026-13-01`·`20261109` |
| S6 | `enabled` 는 true/false(없으면 안 됨)·`retention_days` 는 0 이상 정수 또는 null | `false` | `"true"`·없음 |
| S7 | 저장된 `effective_status` 가 `자동화 가능` 인데 7칸·경로 유형 계산은 아니면 거부(다른 라벨은 켜지 못하므로 더 엄격하게 적는 것도, 운영자 결정으로 Pew 를 `자동화 제외` 라고 적은 것도 허용) | 계산이 `자동화 제외` 인데 `완전 제외`·`참고 전용` 으로 적음 | rss 경로인데 `자동화 가능`·DENIED 칸이 있는데 `자동화 가능` |
| S8 | 근거 이름·약관 문서 이름에 링크 금지 | `Agency Open Licence v3.0` | 주소가 든 글 |
| A0 | `enabled` 는 class `data` 만 | `data` | `image`·`internal`·`ops` |
| A1 | `strict_tier` ≤ 2 이고 7칸 계산도 ≤ 2(저장값이 계산보다 낮으면 거부, 계산이 3·4 이면 다른 규칙과 함께 항상 A1 이 나온다), 구조화 경로가 있음 | Tier 2·`api` | Tier 3·경로 없음 |
| A2 | 7칸 모두 UNKNOWN 이 아니고 `basis` 가 EXPLICIT·STANDARD_LICENSE·STATUTE(`ai_use: NEVER` 이면 `ai_input` 칸은 건너뛴다) | 칸마다 직접 근거 | `ai_input` 이 UNKNOWN·IMPLIED·NOT_ADDRESSED·NOT_READ(기본), 나머지 칸이 그런 것(NEVER 여도) |
| A3 | 어느 칸도 DENIED 가 아님(상업 이용·자동 접근 금지는 Tier 4, `ai_use: NEVER` 이면 `ai_input` 칸은 건너뛴다) | 모두 허용·조건부 | `commercial_use` DENIED |
| A4 | `snapshot.expires_at` 이 오늘보다 앞서지 않음(기한 당일은 유효), 오늘을 못 받으면 거부 | 기한 당일 | 하루 지남·`today` 없음·기한 없음 |
| A5 | 출처 표시가 CONDITIONAL 이면 `attribution_template` 이 있음 | 틀이 있음 | 틀이 없거나 공백 |
| A6 | 경로 유형 규칙: rss·html·image 경로는 Tier 1 이어도 자동화 제외 | `api`·`csv`·`dataset` | `rss`·`html`·`image`(하나라도) |
| A7 | Tier 4(7칸 계산에서 상업 이용·자동 접근·가공·AI 입력 중 하나가 DENIED)이거나 저장된 `strict_tier` 가 4 이면 완전 제외 | — | `derivative_use` DENIED·`ai_input` DENIED·저장값 4 |
| A8 | 7칸마다 근거 이름·열람일, 비어 있지 않은 약관 문서 이름이 하나 이상 | 모두 있음 | 근거 비어 있음·약관 이름이 빈 문자열이나 공백뿐 |
| A9 | `effective_status` 가 `자동화 가능` | `자동화 가능` | `자동화 제외` 등 |
| A10 | 접근 경로마다 `paths`(경로 접두어)가 비어 있지 않고 호스트 전체를 여는 `/` 한 개가 아님 — 호스트 전체를 여는 항목은 켜지 못한다(SRCV2 D5) | `["/v1/"]` | 빈 배열·칸 없음·`["/"]` |
| A11 | api 접근 경로마다 호출 한도(`rate_limit`)가 알려져 있음 — 제공처가 공개한 `N/second`·`N/minute`·`N/hour`·`N/day` 문구(`100 per day` 도 읽는다)이거나, 공식 수치 한도가 없다고 확인한 구조화 객체. csv·dataset 경로는 요구하지 않는다 | `100 per day`·구조화 객체 | null·`UNKNOWN`·`확인 필요`·`0/day`·`100/week` |
| S9 | `attribution_template` 모양(비어 있지 않으면): 자리 표시는 `{title}`·`{date}`·`{url}` 뿐, 한 줄·300자 이하, 링크(`://`·`www.`)·꺾쇠·역따옴표·대괄호·역슬래시·세로줄·물결표·표시 괄호 없음, 로고·상표 표시와 보증·승인·제휴·후원을 암시하는 알려진 표현 없음, 자료를 우리 것이라 주장하는 표현(저작권 기호·무단 전재 금지 등) 없음, 자리 표시를 뺀 일반 문구 8자 이상 | `Source: Fixture Agency` | 링크·`{name}`·자리 표시뿐·`NOAA 가 인정한 자료`·`로고` |
| S10 | `rate_limit` 객체 모양: `official`(`N/…` 문구 또는 `NONE`)·`own`(우리 자체 상한 14칸 — 빠진 칸을 기본값으로 채우지 않고 값은 범위 안, `stop_product_on_404`·`fail_closed_on_bad_response` 는 true)·`note`(한 줄 — `NONE` 이면 '공식 수치 한도 없음'·'자체 상한'·'제안'을 밝힘). 칸 사이 관계: 월 상한 ≥ 하루 상한 ≥ 글 하나가 재시도까지 쓰는 호출 수. `official` 이 `NONE` 이면 `own` 이 필수 | 14칸을 모두 적은 객체 | 칸 하나 빠짐·범위 밖·알 수 없는 칸·`NONE` 인데 `own` 없음 |
| S11 | `own_data_only` 는 true/false. '공공영역·연방정부 저작물·저작권 보호 대상이 아님' 같은 법적 주장을 담은 `attribution_template` 은 `own_data_only` 가 true 인 항목만 쓴다 | 주장 없는 문구, 또는 true 와 함께 | 제3자 자료를 읽을 수 있는 항목(false)이 그 문구를 씀 |

로더 `load_registry(path, today)` 는 문제가 있는 Provider 를 ACTIVE 로 올리지 않고 사유를 한 줄씩 남긴다(`Registry.inactive_reasons()`·`report_lines()` — 모양이 틀려 목록에서 빠진 항목은 `enabled` 가 아니어도 '모양이 올바르지 않아 목록에서 빠짐' 으로 알린다). 파일 전체를 쓸 수 없으면(JSON 오류·`schema_version`·id 중복·최상위 알 수 없는 칸) 빈 목록으로 떨어지지 않고 `SourceRegistryError` 로 멈춘다. 명령줄 확인: `python -m pipeline.source_registry --today YYYY-MM-DD`(오늘을 주지 않으면 enabled 인 Provider 는 기한을 확인할 수 없어 거부된다).

## 6. 질의 API — FACT(구조화 Fact 경로)와의 인터페이스 약속

이름과 모양을 바꾸지 않는다(구조화 Fact 경로의 어댑터·조립기는 이 모양과 같은 최소 프로토콜만 보고 짠다).

| 호출 | 돌려주는 것 |
|------|-------------|
| `load_registry(path=None, today=None) -> Registry` | 읽기 전용 허용 목록 |
| `Registry.get(provider_id) -> Provider or None` | Provider(ACTIVE 가 아니어도) |
| `Registry.active_providers() -> list[Provider]` | 검증을 통과한 enabled Provider 만(파일 순서) |
| `Registry.is_url_allowed(url, purpose) -> (bool, 사유)` | 허용 호스트·경로이고 그 Provider 가 ACTIVE 이고 목적이 허용 목적일 때만 True. 사유에는 호스트·Provider 이름만(쿼리·토큰·경로 없음) |
| `Provider`(frozen dataclass) | `provider_id`·`strict_tier`·`effective_status`·`access`·`attribution_template`·`snapshot`·`policy`·`retention_days` (+`name`·`provider_class`·`enabled`·`exceptions`·`ai_use`·`own_data_only`…). `access[].rate_limit` 은 문구·구조화 `RateLimit`·None 중 하나 |

**목적(`purpose`)은 허용 목록 방식이다.** `[a-z][a-z0-9_]{0,31}` 모양이어야 하고, 허용 목적은 **`fact`(구조화 Fact 호출) 하나뿐**(`source_registry.ALLOWED_PURPOSES`)이다. 일반 웹 읽기(`feed`·`page`·`resolve`)를 포함해 그 밖의 이름(`article`·`rss`·`web`·`crawl`·`fetch`·`read`·`news`·`summary` 등 모르는 목적)은 허용 목록에 있는 호스트·경로여도 항상 거부한다(유형만으로 Tier 3). 목적을 더하려면 코드와 이 절을 함께 바꾼다(T2). 주소는 `https` 만, 호스트는 정확히 일치(하위 도메인 와일드카드 없음), 경로는 접두어 경계를 지킨다. 사용자 정보(`@`)·443 아닌 포트·IP·역슬래시·공백·비 ASCII·`..`·`//`·퍼센트 인코딩 우회·`..;x` 같은 세미콜론 매개변수 뒤의 점 조각·이중 인코딩(`%25`)은 거부한다(`split_https_url`).

## 7. 외부 호출 관문

`egress.check_url(url, purpose, registry, own_repo=None) -> None` — 허용이면 조용히 돌아가고 아니면 `EgressDenied`(문구에 호스트·목적·사유만). **첫 주소만 판정한다.** 통과 조건은 ① **고정 운영 호스트의 허용 목적·허용 경로**(`OPS_RULES`, https·443) 또는 ② registry 의 ACTIVE Provider 가 그 호스트·경로를 접근 경로로 두고 목적이 `fact` 일 때. `registry` 가 None 이면 운영 호스트 규칙만 본다. 운영 호스트는 허용 목록으로 넘어가지 않는다(운영 규칙에 안 맞으면 거부가 끝이다). **일반 웹 읽기(`feed`·`page`·`resolve`)와 모르는 목적은 운영 호스트에서도 허용 목록에서도 항상 거부한다.**

| 운영 호스트 | 허용 목적 | 허용 경로(질의는 판정에 쓰지 않는다) | 근거 |
|-------------|-----------|---------------------------------------|------|
| `api.github.com` | `ops_repo` | `/repos/<own_repo>/` 아래 `issues`·`labels`·`pulls`·`commits`·`actions`·`check-runs` 와 `/rate_limit`. 저장소는 부르는 쪽이 `own_repo`(owner/repo 꼴)로 넘긴 것만 — 없거나 올바르지 않으면 저장소 경로는 열리지 않는다(남의 저장소 `/repos/다른소유자/다른저장소/readme` 는 거부) | 코드에 문자열 있음. 여섯 GitHub 클라이언트(`issue_package`·`drafts`·`watchdog`·`ops_inbox`·`operator_loop`·`github_status`)가 부르는 경로 머리를 시험이 AST 로 읽어 규칙 안에 있음을 확인 |
| `api.telegram.org` | `ops_notify` | `/bot<토큰>/sendMessage` 와 `/bot<토큰>/getUpdates`(토큰은 모양만 본다) | 코드에 문자열 있음 |
| `oauth2.googleapis.com` | `ops_auth` | `/token` | 코드에 문자열 있음(`TOKEN_URI`) |
| `generativelanguage.googleapis.com` | `ops_llm` | `/v1beta/models`·`/v1/models` 와 그 아래 한 조각(모델) | SDK 가 정함(코드에 문자열 없음, 공개 문서의 기본 호스트) |
| `blogger.googleapis.com` | `ops_publish` | `/v3/blogs/<블로그>`·`/v3/blogs/<블로그>/posts`(와 그 아래 글 하나) | SDK 가 정함(코드에 문자열 없음) |

`www.googleapis.com` 은 운영 호스트에서 **뺐다(D-173)** — 코드에 있는 그 이름은 OAuth 범위 이름(`…/auth/blogger`)이고 요청 목적지가 아니며, 고정한 `google-api-python-client>=2,<3` 는 번들 디스커버리 문서를 써서 호출이 `blogger.googleapis.com` 으로만 간다(이 PC 에 SDK 가 없어 번들 문서를 직접 열어 확인하지는 못했다. 실제 실행에서 그 호스트로 가는 요청이 보이면 `/blogger/v3` 접두어 하나만 되살린다). 운영 호스트의 목적 이름(`ops_repo`·`ops_notify`·`ops_auth`·`ops_llm`·`ops_publish`)은 허용 목록의 목적(`fact`)·일반 웹 읽기 이름과 겹치지 않는다.

**리다이렉트**: 관문은 첫 주소만 판정하므로 3xx 로 허용 밖으로 나가는 길을 막지 못한다. 그래서 관문 모듈이 **검사된 opener** `egress.build_checked_opener(purpose, registry, own_repo=None, max_redirects=3)` 를 준다 — 첫 요청과 따라가는 모든 리다이렉트의 새 주소를 `check_url` 로 다시 판정해 허용이 아니면 `EgressDenied`(최대 3번, `max_redirects=0` 이면 모든 리다이렉트 거부, 같은 주소로 되돌아가는 반복 거부), 다른 호스트로 따라갈 때는 인증 머리글(Authorization·Cookie·X-Api-Key 등)을 뗀다. https 처리기만 붙인다(파일·FTP·데이터 주소·환경 변수 프록시 처리기 없음). `egress.check_final_url(response_url, purpose, registry, own_repo=None)` 는 응답의 최종 주소를 요청 **뒤에** 다시 판정하는 도우미다(이미 나간 뒤라 opener 보다 약하다). **FACT 어댑터는 이 opener 를 쓰거나 최종 주소를 다시 `check_url` 로 판정해야 한다**(9절 의무). 지금 `generator.py` 의 호출은 이 opener 로 바꾸지 않았다(`legacy` 바이트 동일 — 그 호출은 `allowlist` 에서 막히거나 아래 등록 목록의 예외다).

**AI 입력 거부**: `egress.check_ai_input(provider_id, scope, registry)` 는 그 Provider 의 자료를 AI 처리기(Gemini 등)에 넘겨도 되는지 판정한다(허용이면 `None`, 아니면 `AiInputDenied` — 문구에는 Provider 식별자·범위 이름·사유만 있고 자료 내용은 없다). `ai_use` 가 NEVER 인 Provider 는 **AI 처리기 정책의 `input_scope` 와 상관없이 항상 거부**한다(ACTIVE 여도, `ai_input` 칸이 무엇이어도). 그 밖(BY_CELL)은 ACTIVE 이고 `ai_input` 칸이 알려졌고 DENIED 가 아니며 범위가 정책의 `input_scope`(Signal 과 검증된 최소 Fact)일 때만 허용한다. 정책 파일은 읽지 않는다(입출력이 없다). 지금 이 함수를 부르는 운영 코드는 없다 — AI 로 가는 자료 경로가 없기 때문이고(AI 흐름 감사), FACT 2단계가 AI 단계 앞에서 부른다.

**호출 예산**(제공처 호출 한도를 지키는 자리 — 감사 R15): `CallBudget`·`budgeted(opener, budget)`·`run_call_cap(rate_limit)`·`budget_for(provider_id, rate_limit)` 는 어댑터가 쓰는 `opener(url, *, timeout, max_bytes) -> bytes` 를 감싼다. 코드가 지키는 것: ① **한 실행의 호출 상한**(`run_call_cap` — 문구 한도는 하루 한도를 하루 실행 횟수 30 으로 나눈 몫과 초·분·시 한도, 구조화 한도는 글 하나가 재시도까지 쓰는 호출 수와 하루 상한 가운데 작은 쪽, 모르면 0 = 호출하지 않음) ② 실패가 3번 쌓이면 그 실행에서 그 Provider 건너뜀 ③ 같은 주소는 한 실행에서 1 + 재시도 횟수(기본 1)번까지 ④ 403·429 를 받으면 그 실행에서 그 Provider 중지, 404 를 받으면 그 주소만 중지 ⑤ 같은 주소의 성공 응답은 이 실행 안에서 다시 부르지 않고 재사용(호출 수에 세지 않는다) ⑥ **호출 전 선행 조건**(`precondition` — 하루·주간 발행 상한이 이미 막았으면 사유를 돌려주고 호출은 0). 관문이 거부한 호출(`EgressDenied`)은 요청이 나가지 않았으니 실패로 세지 않는다. 구조화 API 어댑터는 리다이렉트를 따라가지 않는 opener(`build_checked_opener(…, max_redirects=0)`)와 함께 써야 호출 한 번이 요청 한 번이다. **못 지키는 것(새 영구 상태를 만들지 않았다 — Actions 는 실행마다 새 환경이다)**: 하루·월 합계, 24시간 중지, 같은 파일 60초 간격 같은 호출 사이 간격, 응답 gzip 요청, 일별 제품의 00:30 UTC 이후 시각은 이 래퍼가 강제하지 못한다 — 어댑터·연결 코드의 의무이고, 하루·월 합계는 선행 조건(그날 이미 Fact 초안이 있으면 호출 0)과 한 실행 상한이 함께 막는 것이 전부다. (설계안, 만들지 않음) 정확히 지키려면 날짜별 호출 횟수와 마지막 403·429 시각을 실행 사이에 남기는 상태가 필요하다 — 후보: ① Actions 캐시(보증 없음) ② 승인 PR 본문·라벨에 횟수 기록 ③ 슬롯 창에서 같은 날 두 번째 Fact 실행을 선행 조건으로 막기(가장 단순). 켜는 변경 때 정한다.

**호출 목록 시험(`tests/test_egress.py`, 스캐너 `tests/egress_scan.py`)은 보증이 아니다.** 알려진 모양의 외부 접속 지점을 AST 로 모아 `EGRESS_EXCEPTIONS`(파일·함수·이유·**막는 장치**)와 비교한다. 새 호출이 표시 없이 생기면(그 모양이 아래 목록에 있을 때) 빨강이고 낡은 등록 항목도 빨강이다. 등록돼 있다는 것은 '이유를 적고 사람이 보았다'는 뜻이지 '막혀 있다'는 뜻이 아니다 — 막는 장치가 있으면 `gate` 칸에 어느 모드에서 무엇이 막는지 적는다. **우회를 막는 보증이 아니며 사람 검토가 마지막 방어선이다.**

- **보는 모양**: `urlopen`·`urlretrieve`·`build_opener`·`OpenerDirector`·`URLopener`·`FancyURLopener`·`HTTP(S)Handler`·`HTTP(S)Connection`·`socket.socket`·`create_connection`·`getaddrinfo`·`gethostby*`·`wrap_socket`·`open_connection` 이름(호출이든 `opener or urllib.request.urlopen` 같은 참조든), 네트워크 라이브러리 import(`requests`·`httpx`·`aiohttp`·`urllib3`·`pycurl`·`httplib2`·`feedparser`·`ftplib`·`smtplib`·`xmlrpc`·`webbrowser`·`ctypes`·`telnetlib`·`poplib`·`imaplib`·`nntplib` 등)와 구글 SDK import, `getattr`·`__dict__[…]`·`vars()`·`globals()`·`importlib.import_module`·`__import__`·`eval`·`exec` 로 이름에 동적으로 닿는 모양, URL 을 받는 파서(`xml.sax.parse`·`minidom.parse`·`pulldom.parse`·`ElementTree.parse`·`pandas.read_*`), `subprocess`·`os.system`·`os.popen`·`os.exec*`·`os.spawn*` 중 명령에 네트워크 도구(`curl`·`wget`·`git` 의 `ls-remote`·`fetch`·`clone`·`pull`·`push`·`remote`·`submodule`·`powershell`·`certutil`·`ssh`·`gh`·`pip` 등)가 글자로 들었거나 명령이 동적인 것, `subprocess.run` 을 부르지 않고 넘겨 두는 참조. 위에 더해(SRCV2 D3) 별 가져오기(`from subprocess import *` 등)·모듈을 다른 이름에 담는 대입(`sp = subprocess`)·`sys.modules` 에서 모듈 꺼내기·내장 이름(`eval`·`exec`·`compile`·`__import__` — `builtins.`·`__builtins__` 경유와 변수에 담기 포함)·`operator.attrgetter`·`methodcaller`·`functools.partial(getattr, …)`·`__getattribute__`·`pickle`·`marshal`·`yaml.load` 류·`importlib` 로더(`load_module`·`exec_module`)·`timeit` 이 글자를 실행하는 것·래퍼 프로그램(`env`·`timeout`·`busybox` 등) 뒤의 도구와 `exec` 꼴 호출(`os.execvp`·`asyncio.create_subprocess_exec`)·프로그램 이름이 변수인 글자 명령·`os.startfile`·`executable=`·`python -c`·`node -e` 같은 코드 글자 실행기·`explorer`·`openssl`·`xdg-open`·주소 글자가 든 명령·목록에 없던 네트워크 라이브러리 몇 개(`lxml`·`dns`·`treq`·`sh`·`pip._vendor`)와 `get_server_certificate`·`getfqdn`·`SocketHandler`·`RobotFileParser`·`multiprocessing.connection` 같은 이름.
- **관문 인정 기준**(전부 맞아야 하고, 확신할 수 없으면 '인정 안 함'이다 — 실패 쪽): ① 같은 함수에서 `egress.check_url` 을 문장으로 불렀고, 그 이름(`egress`·별칭·`check_url`)은 파일 안에서 **오직 `pipeline.egress` 를 가리키는 import 로만** 묶여 있다(매개변수·지역 대입·`for`/`with`/`except` 대상·정의로 같은 이름을 다시 묶거나, 다른 모듈 `egress` 를 가져오거나, import 없이 쓰거나, `from … import *` 가 있으면 인정하지 않는다) ② 첫 인자(주소 식)가 호출에 쓰는 주소 식과 `ast.dump` 로 같다(계산이 든 식은 안 된다 — 두 번 계산하면 값이 달라질 수 있다. `Request` 변수를 따라갈 때는 그 이름을 묶는 곳이 하나이고 `이름 = Request(…)` 한 줄일 때만) ③ 호출보다 앞서고 호출을 지배한다(조건문·반복문·`with`·핸들러·else·finally 안의 관문은 아니고, `try` 본문 안의 관문은 **모든 핸들러가 끝에서 무조건 `raise` 하고** `return`·`break`·`continue` 가 없을 때만) ④ 둘 사이에 주소 식의 이름과 그 이름 아래 속성·첨자에 다시 대입하지 않았고, 호출이 반복문 안에 있는데 관문이 반복문 밖이면 반복문 전체에서 대입하지 않았다 ⑤ 호출이 람다·내포·생성기식 안에 있지 않다. 상수 글자를 넘긴 관문은 같은 상수를 부르는 호출에만 인정한다. **`source_policy.egress_gate` 처럼 `legacy` 에서 아무 일도 하지 않는 호출은 관문이 아니다.** 지금 코드에는 이 기준을 채우는 호출이 없다.
- **스캔 범위**: `generator.py`·`blogger_generator.py`·`pipeline/`·`scripts/`·`인수인계/도구/`·`.github/` 아래의 모든 `*.py`. `tests/` 는 제외한다(시험 코드는 운영 경로가 아니고 가짜 소켓·urlopen 흉내가 많아 스캔하면 잡음이 된다). 스캔함·제외 어느 목록에도 없는 새 파이썬 파일(새 최상위 폴더)이 생기면 시험이 빨개진다. 워크플로 yml 은 줄 단위 글자 검색으로 `curl`·`wget`·`Invoke-WebRequest`·`git`·`gh`·`pip` 줄과 파이썬 네트워크 글자를 찾아 `YML_REGISTERED` 와 대조한다(지금 curl·wget 줄은 없다 — 생기면 등록 전까지 빨강). `.git`·`__pycache__` 는 어느 깊이에서든 건너뛰고 `node_modules`·`_site`·`venv`·`.venv`·`.ruff_cache`·`.pytest_cache` 는 저장소 맨 위에서만 건너뛴다(스캔 폴더 안쪽의 같은 이름 폴더는 읽는다 — SRCV2 D2). 워크플로 yml 은 (파일, 종류) 단위로 등록하므로 같은 종류의 줄이 늘어나는 것은 못 잡는다.
- **지금 저장소의 결과**: 알려진 모양의 지점 72곳(함수 단위, 37개 파일) 가운데 관문을 거쳤다고 인정되는 곳은 0이고 모두 등록 항목 62개로 덮인다(와일드카드 2개는 `subprocess.run` 참조라는 모양 한 가지만 면제한다). 등록 항목은 면제하는 모양 종류의 앞 조각과 지점 수를 함께 적는다 — 다른 종류의 모양이 같은 함수에 더해지면 등록 밖 지점이 되고, 지점 수를 못박은 항목은 같은 종류가 늘어도 빨개진다(다른 묶음이 계속 고치는 Fact·그림자 실행 파일의 항목은 종류만 좁히고 개수는 세지 않는다). 콘텐츠 경로 셋(C-01 피드 `fetch_news_items`·C-02 기사 페이지 발췌 `_fetch_source_excerpt`·C-03 구글 뉴스 해석기 `_resolve_article_url`)은 **`allowlist` 에서만 막힌다**(소스 건너뜀과 `source_policy.egress_gate` 가 `check_url` 로 거부 — `legacy` 에서는 열려 있다). 그 밖은 운영 호스트로만 가는 호출(GitHub·텔레그램·Blogger·Gemini)·SDK 가 직접 연결하는 호출·외부 사진 경로(Unsplash, 운영자 결정 대기)·사람이 실행하는 도구(`인수인계/도구/`의 `urlopen` 9곳 포함)·git 도우미·네트워크에 닿지 않는 동적 모양(사람이 확인 — Fact 직렬화의 칸 이름 읽기·그림자 실행의 읽기 전용 방어 코드·문법 검사 `compile` 포함)이다. 모든 호출을 관문으로 바꾸는 것은 이 일의 범위 밖이다.

**사각지대 — 고친 뒤에도 잡지 못하는 모양**(시험이 '아직 못 잡는다'를 못박고, 스캐너가 더 잘 보게 되면 시험이 알려 줘 이 표와 함께 고친다). **이 표는 알려진 예시이며 전부가 아니다**(SRCV2 D3). 못 보는 부류는 ① 파이썬 밖의 프로그램이 하는 일(다른 파이썬 파일·실행기에 넘긴 명령·네트워크 드라이브 경로) ② 목록에 없는 라이브러리·SDK와 일반 계산 라이브러리 ③ 이름이 동적으로만 정해져 알려진 이름 목록 밖에 있는 것 ④ `tests/` 와 파이썬이 아닌 스크립트다:

| 모양 | 왜 못 보나 |
|------|-----------|
| `다른 파이썬 파일을 하위 프로세스로 실행` | 그 파일이 스캔 범위 밖이면 거기서 하는 일을 볼 수 없다(범위 안이면 그 파일에서 따로 잡힌다) |
| `목록에 없는 새 SDK` | 네트워크 라이브러리·SDK 목록은 유한하다 |
| `넘겨받은 실행기가 부르는 명령` | 실행기를 부르는 자리(호출한 쪽의 `subprocess.run` 참조는 잡히지만 명령 내용은 보지 않는다) |
| `numpy.loadtxt 가 주소를 읽음` | numpy 같은 일반 계산 라이브러리는 목록에 올릴 수 없다(주소를 읽을 수 있는 함수 이름의 목록이 따로 없다) |
| `UNC 경로를 파일처럼 열기` | 네트워크 드라이브·UNC 경로는 파일 열기라 네트워크 이름이 없다 — 파일 열기는 보지 않는다 |

모양으로 적을 수 없는 사각지대도 있다: `tests/` 아래 코드와 파이썬이 아닌 스크립트(`.ps1`·`.bat`·`.sh`)는 보지 않는다 · 관문 인정은 첫 주소와 같은 식인지와 이름·그 아래 속성·첨자 대입만 보고 객체의 내용을 바꾸는 메서드 호출(`items.reverse()`)·전역을 바꾸는 함수 호출·`check_url` 에 모든 것을 허용하는 가짜 registry 를 넘기는 것(호출자 책임)·리다이렉트·DNS 는 보지 않는다 · 워크플로 yml 안의 파이썬 조각은 줄 단위 글자 검색이 전부다.

## 8. 소스 정책 스위치(`chance.source_policy`)

| 값 | 동작 |
|----|------|
| 없음 또는 `legacy`(**기본**) | **지금과 같다.** 이 모듈의 함수는 입력을 그대로(같은 객체) 돌려주거나 아무 일도 하지 않고, 허용 목록 파일을 읽지 않고 시계도 부르지 않는다 |
| `allowlist` | 아래 여섯 가지가 코드로 강제된다 |

**꺼진 기능은 출력이 바이트까지 같다(증거)**: 기준 커밋(소스 정책 도입 전 main `78c6b89`)의 `generator.py` 와 바뀐 코드를 같은 가짜 입력(가짜 피드 20개·가짜 기사 페이지·가짜 모델·가짜 사진)으로 돌려 여덟 시나리오 — 프롬프트 14가지, 모든 분야의 `fetch_news_items`(출력·후보·요청 순서), 기사 페이지 발췌·해석기, 정기·수동 `main()` 연습 실행 2종과 실제 쓰기 2종(표준 출력·실행 요약·글·이력·요청 순서), `finish_run` 의 모든 옛 결과 코드 — 의 sha256 이 같음을 확인했다. 그 값은 `tests/test_generator_source_policy.py` 의 `GOLDEN` 에 못박았고(3.12·3.10 모두 같다), 다시 만드는 법은 `tests/source_policy_scenarios.py` 머리말에 있다. 독립 검증도 시나리오 27개 × 인터프리터 2종에서 바이트까지 같음을 따로 확인했다.

| `allowlist` 에서 | 어떻게 |
|------------------|--------|
| ① `fetch_news_items` 가 ACTIVE 가 아닌 소스를 읽지 않는다 | 소스마다 `is_url_allowed(주소, "feed")`(일반 웹 읽기라 항상 거부)를 보고 건너뛴다 — 네트워크 호출 0, 로그에는 소스 이름만 |
| ② 기사 페이지 발췌·구글 뉴스 해석기 호출 0 | 소스를 건너뛰어 도달하지 않고, 만에 하나 불리면 두 함수 첫머리의 관문이 `EgressDenied` 로 거부(삼키지 않음) |
| ③ 외부 요약·제목·태그가 프롬프트로 가지 않는다 | `build_post_prompt` 가 입력을 받자마자 `source_policy.prompt_inputs` 로 후보를 **자체 제목만** 가진 사본으로 바꾼다(자체 제목이 없으면 '출처 없음 — skip' 입력). 이력의 외부 글 제목은 '최근 다룬 제목'에서도 뺀다 — 자체 제목과 다른 `topic` 은 `source_url` 이 없는 옛 항목도 외부로 본다 |
| ④ 이력 `topic` 에 외부 제목을 저장하지 않는다 | 후보 흐름에서 자체 제목(`own_title`)이 없는 후보를 뺀다 — 저장되는 `topic` 은 그 자체 제목뿐이다(`ACTIVE` 가 0 이면 후보가 없어 저장 자체가 없다) |
| ⑤ 로그·실행 요약·탈락 기록에 외부 제목이 없다 | 같은 후보 필터 덕에 `주제 시도` 줄·탈락 기록·요약의 제목은 자체 제목뿐이고, 빠진 후보는 수만 알린다 |
| ⑥ 새 결과 코드 `SOURCE_POLICY_NO_ACTIVE_PROVIDER` | ACTIVE 콘텐츠 Provider 가 0 이면 `generate_blog_posts` 가 후보를 읽기 전에 이 코드를 적고 끝난다. `finish_run` 은 **초록(종료 0) + `::notice::`** 로 끝낸다 — 빨강(종료 1)인 `ALL_LANES_EMPTY`·경고인 `ALL_REJECTED` 와 구분된다(결과 코드 표는 `ACTIONS_GUIDE.md`) |

`FIX_IMAGES`(기존 글 사진 교체)·이슈 수정·`PIPELINE_PAUSE`(정지가 가장 먼저 반환 — 허용 목록을 읽지 않는다)의 동작은 바뀌지 않는다. 사진을 자동으로 쓸지는 운영자 결정이라 이 일이 끄지 않는다(`EGRESS_EXCEPTIONS` 에 이유와 함께 등록).

덧붙임: 피드 관문 호출(`fetch_news_items` 안의 `source_policy.egress_gate(…, "feed", …)`)은 앞의 소스 건너뜀이 먼저 걸러 `allowlist` 에서 도달하지 못하는 **이중 장치**다. 지우면 생성기 변경이 늘고 가지 병합 충돌 지점이 늘어 남겨 두었다(D-178). `OUTCOME_TEXT` 의 문구 '외부 호출 0' 은 **콘텐츠 경로**에 한한 말이다 — 승인 흐름(`publish_flow: pr`)에서는 `allowlist` 여도 '일 없음' 판정 앞에서 git 이 자기 저장소 원격을 부른다(문구는 바꾸지 않았다 — 생성기 줄을 늘리지 않으려는 것). `legacy` 에서도 레지스트리(`blogs.json`)를 이전보다 더 자주 읽고, 잘못된 `source_policy` 값은 `RegistryError` 로 멈춘다(값을 못 읽었다고 느슨한 쪽으로 떨어지지 않는 fail-closed — 출력 바이트에는 영향이 없다).

## 9. FACT 와의 인터페이스 약속(요약)

1. **Registry**: 6절의 이름·모양. FACT 는 이 모듈을 직접 import 하지 않고 같은 모양의 최소 프로토콜로 짜며, 병합 뒤 연결은 2단계다. 목적은 `fact` 를 쓴다.
2. **`topic`(이력)은 자체 제목뿐**이다. 구조화 Fact 경로가 만드는 글의 제목·이력 `topic`·로그·탈락 기록에는 우리가 만든 제목만 쓴다. `allowlist` 에서 일반(피드형) 후보 흐름은 `own_title`(자체 제목) 칸을 가져야 들어오고, 외부 기사 제목을 가진 후보는 빠진다. **`own_title_batches`·`prompt_inputs` 는 Fact 후보에 쓰지 않는다**(AI 흐름 감사 F7·F14 — FACT_PATH 11절 2·8항과 같은 말): `facts` 경로는 Gemini 를 부르지 않으므로 프롬프트로 가는 제목이 없고, Fact 글의 제목은 조립기가 만든 자체 제목이다.
3. **프롬프트 입력**: `allowlist` 의 `build_post_prompt`(일반 후보 흐름)는 자체 제목만 받는다(요약·링크·출처 이름·게시 시각·태그 없음). **Fact 후보에는 이 정화를 적용하지 않는다** — `facts` 경로는 프롬프트를 만들지 않는다(Gemini 를 부르지 않는다). 사실 근거는 Fact 로 바뀌고, Fact 자료를 AI 에 쓰려면 `egress.check_ai_input` 이 허락해야 한다(입력은 Signal·검증된 최소 Fact 만 — `ai_processor_policy.json`. `ai_use` 가 NEVER 인 Provider 의 자료는 항상 거부, 7절·10절).
4. **결과 코드**: 후보를 공급하는 새 경로가 없는데 ACTIVE 콘텐츠 Provider 가 있으면 일반 흐름이 이어져 `ALL_LANES_EMPTY`(빨강)가 된다 — 배치가 어긋난 것을 드러내는 쪽으로 둔 것이다. FACT 2단계 연결이 후보를 공급하는 자리(생성기 한 곳)에서 이 경로를 대체한다.
5. **리다이렉트(의무)**: FACT 어댑터는 `egress.build_checked_opener` 가 만든 opener 로 요청하거나, 요청한 뒤 응답의 최종 주소를 `egress.check_final_url`(또는 `check_url`)로 다시 판정한다. 관문은 첫 주소만 판정한다(7절).
6. **후보의 다른 칸도 자체 문자열(의무, D-175)**: `own_title_batches` 는 제목만 자체 제목으로 바꾸고 후보의 `source`·`publisher_domain`·`citation`·`link` 칸은 고치지도 검증하지도 않고 그대로 통과시킨다. 후보에 Provider 식별자 규약이 아직 없고 Registry 와 오늘을 받으려면 생성기 호출부를 바꿔야 해 강제하지 않았다 — 그래서 후보를 만드는 쪽(FACT 2단계)이 이 칸들도 **자체 문자열**(Registry 의 Provider 이름·호스트·`attribution_template`)로만 채워야 하고, 외부 글의 출처 이름·링크·인용문을 그대로 싣지 않는다. 통과 동작은 `tests/test_source_policy.py` 가 못박는다.
7. **직접 소비자의 범위**: GATE 그림자 실행(`shadow_run.py`)처럼 `iter_candidate_lanes`·`build_post_prompt` 를 직접 쓰는 소비자는 **일반(피드형) 후보**에 같은 정화(`own_title_batches`)를 받아야 한다(의무). Fact 후보는 이 경로로 가지 않는다 — Fact 후보를 그림자 실행이 평가하려면 Gemini 를 부르지 않는 같은 함수에서 만들어야 하고(FACT_PATH 11절 8항), 지금 그림자 실행의 반복문(`shadow_run.py` 의 `_evaluate`)은 Gemini 를 직접 부르므로 Fact 후보를 그 반복문에 넣지 않는다(AI 흐름 감사 F6·F14 — 방어 묶음과 FACT 2단계 몫).

## 10. AI 처리기 정책(`pipeline/ai_processor_policy.json`)

Gemini 같은 AI 는 데이터 출처가 아니라 처리기라 허용 목록과 따로 11칸을 둔다. 값은 2026-11-09 감사가 읽은 Gemini API 추가 약관(시행일 2026-03-23)의 요지다(요약 도구를 거쳐 읽었으니 원문 확인을 권한다).

| 칸 | 값 | 비고 |
|----|----|------|
| `professional_business_use` / `consumer_use` | `ALLOWED` / `DENIED` | 이용은 업무·전문 목적으로 한정. 이 저장소의 사용이 업무·전문 목적에 해당하는지는 운영자 판단 |
| `free_service_data_use` / `paid_service_data_policy` | `USED_FOR_PRODUCT_IMPROVEMENT` / `NOT_USED_FOR_PRODUCT_IMPROVEMENT` | 무료 등급은 입력·출력이 제품 개선에 쓰이고 사람 검토자가 읽을 수 있다 → 공개 전 전체 초안을 무료 서비스에 넣지 않는다. 우리 키의 등급은 운영자만 확인 가능 |
| `sensitive_data_allowed` | `false`(고정) | 개인·기밀·자격증명 입력 금지 |
| `medical_advice_use` | `DENIED`(고정) | 의료 조언 생성 금지 |
| `input_scope` | `SIGNAL_AND_VERIFIED_MINIMAL_FACTS`(고정) | Signal 과 검증된 최소 Fact 만 |
| `raw_source_text_allowed` | `false`(고정) | 원문 외부 텍스트(기사·해설문·RSS 요약·Raw API 전체 응답) 입력 금지 |
| `credential_storage` | `WINDOWS_CREDENTIAL_MANAGER_AND_ACTIONS_SECRETS`(고정) | 키는 Windows 자격 증명 관리자(Desktop)와 GitHub Actions 시크릿에만 |
| `policy_version` / `policy_verified_at` | `gemini-api-additional-terms-2026-03-23` / `2026-11-09` | |

고정 값은 `validate_ai_policy` 가 다른 값을 거부한다 — 완화하려면 코드·문서·운영자 승인이 함께 바뀌어야 한다(T3). 모르는 값은 `UNKNOWN`.

**코드는 이 파일을 실행 중에 읽지 않는다(D-176).** 읽는 것은 검증기 점검(`python -m pipeline.source_registry`)뿐이다. `allowlist` 에서만 코드가 같은 원칙(`prompt_inputs` — 자체 제목만 입력)을 고정된 모양으로 지키며, **`legacy` 에서는 외부 기사 요약이 지금도 Gemini 입력으로 간다 — 정책 값(`raw_source_text_allowed: false`)과 어긋난 알려진 상태**다. 이 파일은 검증기와 FACT 2단계(어댑터·조립기가 입력 범위를 이 값으로 읽는다)의 계약 기준이다. `source_policy.legacy_policy_notice` 가 그 어긋남을 알릴 한 줄을 만든다 — 부르는 곳은 FACT 2단계 몫이다(생성기를 바꾸면 `legacy` 출력이 달라진다). **`ai_use` 와 `input_scope`**: 허용 목록 Provider 의 `ai_use` 가 NEVER 이면(운영자 결정 007 — 규칙 기반 경로 전용) 그 자료는 AI 처리기에 넘기지 않으므로 이 정책의 `input_scope` 는 그 Provider 에는 적용되지 않고 AI 입력은 항상 거부된다(`egress.check_ai_input`). BY_CELL 인 Provider 에만 `input_scope`(Signal 과 검증된 최소 Fact)가 범위를 정한다.

## 11. 켜는 순서(T3 — 운영자 승인)

1. 구조화 Provider 하나를 **증거와 함께 PR 로** `enabled: true`(공식 약관·robots·호출 한도를 읽어 7칸을 직접 근거로 채우고, `attribution_template`·`snapshot.expires_at`·`access[].paths`·api 경로의 `rate_limit` 을 채운다. 규칙 기반 경로 전용이면 `ai_use: NEVER`). `python -m pipeline.source_registry --today YYYY-MM-DD` 와 시험이 통과해야 한다. 약관 판독은 사람이 하고 운영 중에는 약관을 해석하지 않는다.
2. 구조화 Fact 경로(2단계)가 생성기 한 곳에서 후보를 공급하고 프롬프트에 원문 링크·출처 규칙을 대신하는 근거가 연결되도록 한다(T2). **이 단계가 끝나기 전에는 3번(`allowlist` 켜기)을 하지 않는다** — 켜야 한다면 36시간(제한 재개 잠금이 켜진 Chance 는 204시간) 경보 임계(`chance.health.max_gap_hours`) 조정이나 정지 변수 병행을 같은 승인에 묶는다(12절).
3. `pipeline/blogs.json` 의 `chance` 항목에 `"source_policy": "allowlist"` 를 더한다(T3 — 정책). 되돌리는 것(legacy)도 정책 변경이라 T3 이고, 사고 때의 비상 정지는 `PIPELINE_PAUSE` 다.
4. 확인: 연습 실행(`dry_run`)의 요약에 `SOURCE_POLICY_NO_ACTIVE_PROVIDER`(ACTIVE 0) 또는 후보 생성 줄이 보이는지, 로그에 외부 제목이 없는지.

**제한 재개 체크리스트 — Pew(P09)**: Pew 비활성은 `allowlist` 를 켠 뒤에야 효력이 있다. 지금은 운영자가 정한 정지 변수가 Chance 정기 실행을 모두 건너뛰므로 읽히지 않을 뿐이다. **정지를 풀기 전에 `allowlist` 를 켜야 하고**, 더 빨리 필요하면 `NEWS_SOURCES` 의 Pew `terms.status` 를 `pending` 으로 바꾸는 **별도 T3 변경**이 선택지다(이 변경은 코드를 바꾸지 않는다).

## 12. 한계와 남은 일

- **`allowlist` 를 켠 뒤의 상태(실험으로 확인한 사실, D-174)**:
  ① 켜면 **새 글이 0** 이다 — 실행은 `SOURCE_POLICY_NO_ACTIVE_PROVIDER`(종료 0, 초록)로 끝나고, 마지막 글로부터 `chance.health.max_gap_hours`(36시간 — 제한 재개 잠금이 켜진 Chance 는 204시간)가 지나면 `health.evaluate` 가 `STALE`(critical)을 내 워치독 경보가 울린다. **켜는 순서: FACT 2단계(후보 공급과 프롬프트 근거)가 연결되기 전에는 켜지 않는다. 켜야 한다면 임계 조정이나 정지 변수 병행을 같은 승인에 묶는다.**
  ② 가상 ACTIVE Provider 를 켜고 후보 공급이 없으면 `ALL_LANES_EMPTY`(빨강)가 매시간 반복된다 — 배치가 어긋난 것을 드러내려는 의도다(9절 4항).
  ③ 후보가 공급돼도 프롬프트에 원문 링크·출처 규칙이 없어, 실제 경로는 건너뛰거나(`검증된 출처가 제공되지 않았습니다`) 본문 검증(원문 링크 인용)에서 전부 탈락한다(`ALL_REJECTED`, 초록+경고). **연습(스텁) 실행은 스텁이 링크를 후보에서 직접 가져와 `PUBLISHED` 로 보이는 어긋남이 있다** — 연습과 실제가 다르다. FACT 2단계 설계가 풀 일이다. 이 상태는 **피드형(일반) 후보 흐름이 `allowlist` 로 돌 때**의 것이다 — Fact 후보(`content_source: facts`)는 이 흐름을 지나지 않고 프롬프트도 없다(FACT_PATH 11절). 그래서 위 계약(`prompt_inputs`·`own_title_batches`)을 Fact 후보에 적용하는 것이 아니라 FACT 2단계가 이 경로를 대체한다.
- SDK 가 직접 하는 호출(Gemini·Blogger OAuth)은 관문을 지날 수 없어 등록 목록에 있다. 운영 호스트 목록의 SDK 호스트는 코드에 문자열이 없어 확인하지 못했다(공개 문서 기준).
- 외부 사진(Unsplash, 공개 글 49편)은 이 일이 끄지 않는다(운영자 결정 대기). 사진 확인 요청(`url_ok`)은 새 글 단계의 후보 사진뿐 아니라 사진 교체 단계(`FIX_IMAGES`)에서 **기존 글 머리말의 `image:` 주소 호스트 전부(Unsplash 외 NASA 이미지 호스트 포함)** 에 HEAD 요청을 한다 — 운영자 결정(사진 자동 사용) 때 정리한다. 이력에 이미 있는 옛 외부 글 제목과 공개 글의 출처·인용 줄은 과거 기록이라 그대로이고, `allowlist` 는 앞으로의 프롬프트·이력·로그에서만 막는다.
- 허용 목록의 `attribution_template` 은 NOAA 조사로 확인된 `noaa_swpc_json` 하나만 채워져 있고(나머지는 조사 전) `content_hash` 는 모두 비어 있다 — 해시 계산 규칙(정규화)이 코드·문서에 아직 없어 발췌 파일 기준 참고값만 있다(NOAA 조사 보고서). 약관 주 1회 감시·자동 격리·점검 기한 자동 갱신은 완성형(재개 뒤) 몫이라 지금은 사람이 `snapshot.expires_at` 을 갱신한다.
- 호스트는 정확 일치만 본다(하위 도메인 와일드카드 없음). 호스트마다 `robots.txt` 를 읽는 코드는 없다(`robots_checked_at` 은 감사의 열람일을 옮긴 값).
- 감사표 69행 밖의 후보(공공데이터포털 데이터셋·NWS)는 약관 판독 뒤 같은 PR 흐름으로 더한다.
- 호출 목록 시험은 보증이 아니다(7절) — 새 외부 접속이 생기는 변경은 시험이 초록이어도 사람이 읽는다.
- 호출 한도(`rate_limit`)는 NOAA 항목만 값이 있고(공식 수치 한도 없음 + 우리 자체 상한 제안) 나머지 api 경로는 null 이라 켤 수 없다. 호출 예산은 한 실행 몫이고 하루·월 합계는 못 지킨다(7절 — 영구 상태가 필요하다).
- NOAA 항목이 규칙을 모두 통과해도 켜기 전에 남은 일이 있었다(운영자 승인으로 켠 뒤에도 기록으로 남는다) — 14절의 '켜기 전 남은 확인'(제3자 조건·Data Citation 지침 원문·G 등급 경계값 등)과 FACT 2단계(어댑터의 필드 화이트리스트·지역 없는 글 틀·문장 규칙).

## 13. 시험·검증

```
python scripts/validate_repo.py
cd tests; python -m unittest test_source_registry test_source_registry_007 test_egress test_egress_budget test_source_policy test_generator_source_policy test_source_policy_docs
python -m pipeline.source_registry --today YYYY-MM-DD
```

시험은 모두 오프라인이다(네트워크·시계·진짜 키 없음 — 검사된 opener 는 가짜 전송 처리기로 시험한다). 시험이 지키는 것: 규칙 태그별 통과·탈락 예문, 운영 호스트 규칙의 호스트×목적×경로 표, 호출 목록 AST(새 호출이 표시 없이 생기면 빨강 — 알려진 모양 한정, 독립 검증이 심은 56가지 모양 전부 적발·사각지대는 못 잡는다고 못박음), 스캔 범위, 옛 생성기와의 바이트 동일(8시나리오), `allowlist` 의 호출 0·초록 종료·외부 제목 차단, 문서의 규칙·표와 코드의 일치(`tests/test_source_policy_docs.py`). 007 반영 시험(`test_source_registry_007`·`test_egress_budget`)은 `ai_use`·출처 문구·호출 한도의 경계와 NOAA 항목에 확인된 값, AI 입력 거부와 호출 예산(가짜 opener·가짜 전송)을 지킨다.


## 14. 운영자 결정 007 반영 — 규칙 기반 경로 전용 Provider

1. **결정**(2026-11-09 20:33, 선택 2): AI 를 쓰지 않는 규칙 기반 경로에서만 AI 입력 칸을 판정에서 뺀다. 조건 셋 — ① 수집부터 발행까지 이 자료가 AI 단계로 흐르는 길이 없는지 전수 확인(끝남: 지금 0개, 2단계를 방어 없이 이으면 9곳 — AI 흐름 감사 보고서) ② 제공처별 칸 확인·호출 한도 확인·출처 표시 문구 자동 첨부 뒤에 켜는 변경은 따로 ③ 재개는 주 1–2편·사람 승인·계산이 값을 더하는 글만. **이 결정은 아무것도 켜지 않는다.**
2. **코드에 표현한 것**: `ai_use`(4절)·`egress.check_ai_input`(7절)·출처 문구 모양 S9·`own_data_only` S11·구조화 호출 한도 S10·A11·호출 예산(7절). 기본값(`ai_use` 없음 = BY_CELL)에서 원래 56곳의 7칸 계산 결과는 쪼개기 전과 바이트까지 같다(시험이 예전 계산을 기준 구현으로 두고 비교한다).
3. **세 제공처를 접근 경로별로 쪼갠 결과**(쪼갠 시점에는 전부 `enabled: false`·`chance.source_policy` 는 legacy 그대로였고, 지금은 `noaa_swpc_json` 만 `enabled: true`·`chance.source_policy` 는 allowlist 다):

| 항목 | 무엇 | 지금 상태 | 켜기 전 남은 것 |
|------|------|-----------|-----------------|
| `noaa_swpc_json` | NOAA 가 만든 값만, 제품 파일 여섯 개(Kp 추정·Kp 예보 포함·NOAA 등급·SWPC 일별 흑점수·월별 태양주기 지수의 SWPC 필드·GOES X선 플레어 7일) | NOAA 조사(2026-11-10)로 7칸 대조(일치 6·근거 이름 불일치 1 — 저장 칸 근거를 면책 문서로 교정)·경로 여섯 파일·키 불필요·robots 확인·자체 호출 상한(공식 수치 한도 없음)·출처 문구(연방법 고지 포함)가 반영돼 **켜도 규칙을 모두 통과**한다(지금은 켜져 있다). `ai_use: NEVER`·`own_data_only: true` | 켜는 변경 자체(`enabled` — T3, 켰다), 아래 5·6항, FACT 2단계(어댑터의 필드 화이트리스트·지역 없는 글 틀·문장 규칙·AI 로 안 가는 연결), 켜기 전 남은 확인 |
| `statcan_wds` | 캐나다 통계청 WDS 구조화 API | 조사 전 — 값을 채우지 않았다. 저장 등급 3·상태 자동화 제외라 A1·A9 로 막히고 출처 문구(A5)와 호출 한도(A11)가 비어 있다. `ai_use: NEVER` | 제공처 조사(7칸 재확인·호출 한도·출처 문구·WDS 메서드별 경로 좁히기) |
| `uk_govuk_api` | 영국 정부 GOV.UK Content API | 조사 전 — 값을 채우지 않았다. 쓸 경로를 모르면 `paths` 를 비워 A10 으로 막힌다(A1·A5·A9·A11 도). `ai_use: NEVER` | 제공처 조사(7칸 재확인·쓸 경로·호출 한도·출처 문구) |
| `swpc_f107_nrc`·`swpc_kyoto_dst`·`swpc_sidc_penticton_fields` | SWPC 서비스에 올라 있는 제3자 자료: F10.7 JSON 둘(캐나다 NRC 가 NRCan 과 협력해 제공)·Dst JSON(교토 대학 자료로 보임)·월별 지수 파일 안의 SIDC 흑점수와 Penticton F10.7 필드 | 7칸 UNKNOWN(읽지 않음)·조사 필요. 앞의 둘은 경로가 있어 켜도 막히고, 셋째는 파일 안의 필드라 열 경로가 없다(참고 전용) | 각 제공처(NRC·NRCan·교토 대학·SIDC)의 이용 조건 조사 — 그 전에는 쓰지 않는다 |

4. **NOAA 항목의 범위 한정(가장 중요)**: 면책 문서의 '별도 표시가 없는 한 공공영역' 문구와 17 U.S.C. 403 고지는 **NOAA 가 만든 값에만** 맞는다. 그래서 이 항목은 `own_data_only: true` 로 NOAA 가 만든 값만 읽겠다고 약속하고, 연방정부 저작물 문구가 든 출처 문구는 이 값이 true 인 항목만 쓴다(S11 — 제3자 필드를 읽는 항목이 쓰면 거절). 경로도 쓰는 파일 여섯 개로 좁혔다(`/json/` 전체·html 경로·45일 예보·F10.7·태양풍·1분 Kp·수 MB 파일은 뺐다).
5. **어댑터 필드 화이트리스트(FACT 2단계 의무 — 같은 파일 안에 제3자 필드가 섞여 있어서)**: 어댑터는 제품마다 읽는 필드의 목록을 따로 가지고 목록에 없는 필드는 읽지 않는다(모르는 필드가 생겨도 무시, 필요한 필드가 없거나 형이 다르면 그 글을 중단 — 실패 시 닫힘). 제품별 허용 필드: `noaa-planetary-k-index` 는 `time_tag`·`Kp`·`a_running`·`station_count`, `noaa-planetary-k-index-forecast` 는 `time_tag`·`kp`(소문자)·`observed`·`noaa_scale`, `noaa-scales` 는 전체, `swpc_observed_ssn` 은 `Obsdate`·`swpc_ssn`, `observed-solar-cycle-indices` 는 `time-tag`·`observed_swpc_ssn`·`smoothed_swpc_ssn` **만**(`ssn`·`smoothed_ssn`(SIDC)·`f10.7`·`smoothed_f10.7`(Penticton)은 읽지 않는다), `xray-flares-7-day` 는 전체. 시각 키가 제품마다 다르고(`time_tag`·`time-tag`·`Obsdate`) 결측 표기도 다르며(-1.0·null·레코드 없음) 정렬이 다른 파일이 있고 2026-03 에 JSON 구조가 바뀐 전례(서비스 변경 공지 26-21)가 있어 제품별 필드 표와 형 검사를 따로 둔다. 추정 Kp 는 독일 GFZ 의 공식 Kp 와 달라 글에 'NOAA 추정 Kp' 로 쓰고, 예보 값은 관측과 구분해 '예보' 로 쓴다.
6. **NOAA 항목의 호출 한도(공식 수치 한도 없음 — 아래는 우리 자체 상한 제안)**: 레지스트리 `rate_limit` 에 구조화해 적었다 — 같은 파일 60초 이상·다른 파일 5초 이상 간격, 글 하나당 제품 3개까지 각 1회, 하루 8회·월 100회 이하, 실패 시 60초 뒤 1회만 재시도, 429·403 은 24시간 중지·404 는 그 제품만 중지, gzip 요청, 일별 제품은 00:30 UTC 이후 하루 1회, 응답 검증에 실패하면 그 글 중단. 코드가 지키는 것은 한 실행의 호출 상한(글 하나가 재시도까지 쓰는 6번)·재시도 1번·403·429 중지·404 주소 중지·같은 주소 재사용·선행 조건이고(7절), 간격·하루·월 합계·24시간 중지·gzip·일별 제품 시각은 어댑터·연결 코드의 의무다. 식별 가능한 User-Agent(연락처 값은 운영자가 정함)를 권장한다(문서 요구는 없다).
7. **켜기 전 남은 확인(NOAA 조사에서 읽지 못한 것 — 운영자 승인으로 켠 뒤에도 기록으로 남는다)**: ① 제3자 조건 셋(SIDC·NRC/NRCan·교토 대학) ② Kp 입력 자력계 제공기관과 GFZ 공식 Kp 의 조건 ③ NOAA 전체 Data Citation 지침 원문, NWS 명칭을 가공 자료의 출처 표기에 쓰는 것이 허용 범위에 정확히 들어가는지 ④ NCEI 보관소의 이용 조건 ⑤ Privacy Policy·Information Quality 페이지 등 ⑥ Kp `time_tag` 가 구간 시작 시각이라는 명시 문구·`a_running` 의 정의·`station_count` 신뢰도 기준 ⑦ G 등급의 3분의 1 경계값(4.67·5.67 등) 처리 ⑧ 45일 예보 `issued` 가 6일 전인 이유·ETag 변화·확정치 대체 정책. 운영자 결정이 필요한 것: 제3자 셋을 따로 조사할지, User-Agent 의 연락처 값, '30일 폭풍 일수'를 텍스트 제품으로 할지 JSON 을 매일 쌓을지, 기관 명칭을 가공 자료의 출처 표기에 쓰는 범위.
8. **출처 문구 자리 표시**: NOAA 항목의 `attribution_template` 은 조립기가 `이용 조건:` 줄에 그대로 붙이는 한 줄이다. `{title}` 자리에는 조립기가 글에 밝히는 공식 데이터 이름(`source.name` — 한글·영문·숫자·공백·`·.,&'-` 만 1–80자, 괄호·슬래시·콜론은 쓸 수 없다. 예: `NOAA SWPC 행성 K 지수 추정값`·`NOAA 우주기상 등급 현황`·`SWPC 일별 흑점수`·`SWPC 월별 태양주기 지수`·`GOES X선 플레어 목록`)이, `{date}` 자리에는 **열람일**(자료 기준일이 아니다)이 들어간다. 이 문구의 연방법 고지 문장은 NOAA 가 만든 값에만 맞으므로 4항의 범위 한정과 S11 이 함께 묶는다. 로고·이미지·NWS 명칭·시각 식별자는 쓰지 않고 보증·제휴를 암시하는 표현·우리 것이라는 권리 주장은 검증기가 거절한다(S9).
9. **스냅샷**: NOAA 항목의 약관 문서 이름에 `Planetary K-index`·`F10.7 cm Radio Emissions`·`Solar Cycle Progression`·`GOES X-ray Flux`·`Service Change Notice 26-21` 을 더했고 열람일은 2026-11-10, 점검 기한은 90일 뒤다. 내용 해시는 비워 뒀다 — 계산 규칙(정규화)이 코드·문서에 없고 발췌 파일이 두 쪽(면책·Data Access)뿐이다.

## 15. 콘텐츠 출처 스위치(`chance.content_source`) — S2b

`source_policy`(8절)가 '외부 콘텐츠를 어떤 규칙으로 읽는가' 라면 `content_source` 는 '글감이 어디서 오는가' 다. `feed`(기본 — 적지 않아도 같다)는 옛 동작(피드 기사를 Gemini 가 쓴다)이고 `facts` 는 허용 목록의 구조화 Fact 제공처(지금은 `noaa_swpc_json` 하나)가 준 자료를 규칙 기반 조립기가 글로 만든다 — **AI·피드·기사 발췌·구글 뉴스 해석기·프롬프트·사진 선택을 부르지 않는다**([`FACT_PATH.md`](./FACT_PATH.md) §15).

- **값과 검증**: `feed`·`facts` 둘뿐이고 `jekyll-git`(Chance)에서만 쓴다. `facts` 는 `source_policy: allowlist`·`languages: ["ko"]`·`publish_flow: pr` 위에서만 받는다(`registry_errors` 가 거절한다). 값을 읽는 곳은 `source_policy.content_source_of` 한 함수이고, 읽지 못하거나 이상한 값이면 조용히 `feed` 로 떨어지지 않고 멈춘다(`source_policy` 와 같은 원칙).
- **허용 목록과의 관계**: `facts` 분기는 시작할 때 제공처가 ACTIVE(`enabled`·`strict_tier`·상태·기한·접근 경로·호출 한도)여야 하고 아니면 글을 만들지 않고 정상 종료한다(`FACT_NOT_READY`). 외부 호출은 모두 `egress.check_url(url, "fact", sources)` 관문과 호출 예산(`budget_for` — 한 실행의 호출 상한·같은 주소 성공 응답 재사용·403·429·404·실패 3회)을 지나고 호출 한도를 모르면 호출이 0 이다(7절). 그래서 제공처가 모두 꺼져 있으면(켜기 전의 값) 스위치를 `facts` 로 잘못 바꿔도 새 글이 나올 수 없다 — 지금은 `noaa_swpc_json` 하나가 켜져 있어 그 제공처의 자료로 글이 만들어진다.
- **하지 않은 것**(S2b 병합 시점): `pipeline/blogs.json`·`pipeline/source_registry.json` 의 값은 바뀌지 않았다 — 켜는 것(스위치·제공처 `enabled`)은 T3 이고(켠 뒤의 상태는 `FACT_PATH.md` §15 의 상태 줄) 순서는 [`FACT_PATH.md`](./FACT_PATH.md) §15-8 이다.
