# AI 흐름 방어 — 구조화 Fact 자료가 AI 로 새지 않게 하는 장치 (방어 묶음, 2026-11-10)

운영자 확인 요청 007 의 조건 ① — '수집부터 발행까지 이 자료가 AI 단계(번역·요약·다듬기·이미지 설명·품질 검사)로 흘러가는 길이 없는지 전수 확인' — 에 대한 코드 쪽 답이다. 전수 확인(2026-11-10)의 결론은 **지금 길은 0개이고, 2단계(생성기 연결)를 방어 없이 이으면 9곳이 열린다**는 것이었다. 이 문서의 장치는 그 9곳을 닫는다. **Fact 글이 한 편도 없는 지금 먼저 세웠고 켜는 변경은 없다**(레지스트리 값·워크플로가 하나도 바뀌지 않는다 — 2026-11-11 S2b 가 `content_source` 스위치와 Fact 분기를 코드에 이었으나 값은 없고 상태는 §12-3 에 적었다). 표식 글이 없으면(정상 입력에서) 모든 흐름의 출력은 이전과 바이트까지 같다 — 증거는 이 묶음의 작업 보고서에 있다. 새 글을 쓰는 방법도, 이슈 수정이 고치는 범위도 그대로다.

## 1. 한눈에

열리는 길의 핵심 이유는 구조화 Fact 글의 **제목에 공개 자료의 값이 들어 있다**는 것이다. 기존 코드는 `_posts` 의 제목·태그·분류를 AI 입력으로 보내는 자리가 넷 있고(연결 a–d), 그 자리가 곧 값이 새는 자리가 된다.

| 연결 | AI 로 가는 것 | 실제 함수 |
|------|---------------|-----------|
| a 새 글 쓰기·그림자 실행 | 프롬프트의 '최근 다룬 제목' 30개 | `generator.existing_titles` → `build_post_prompt` |
| b 기존 글 이미지 교체 | 글 제목·태그·분류 → 영어 검색어 | `generator.fix_images` → `repair` → `make_image_queries` |
| c Blogger·Naver 재작성 | 다른 블로그 이력 제목(최대 100자) → 탈락 사유 `[DUP_OTHER]` → 재작성 프롬프트 | `state.other_blog_titles` → `gates.check_post` → `run.build_prompt` |
| d 이슈 수정(이미지 변경) | 글 제목·태그 → 영어 검색어 | `edits.ops.op_image` → `image_queries` |

장치는 네 겹이다. **1차는 구조다**(아래 ①②), ③은 마지막 방벽이고 ④ 정적 규칙은 이 묶음 안에 있다(그 가운데 AI 키를 주지 않는 규칙 AF7 만 T3 의 워크플로 변경과 함께 더한다).

1. **출처 표식** `provenance: "facts"` — 생성기만 쓰는 머리말 한 줄과 이력 항목의 한 칸(§6). 알 수 없으면 막는다.
2. **표식 소비자** — AI 입력을 만드는 읽기(`load_posts`·`existing_titles`·`entry_titles`·`other_blog_titles`)의 기본값이 '표식 글을 거름'(`for_ai=True`)이고, `fix_images`·`repair`·`diagnose`·`op_image`·`op_llm_patch`·`pages` 가 표식 글을 AI 로 보내지 않는다(§5).
3. **런타임 방벽** `pipeline/ai_guard.py` — AI 입구 둘이 부르기 직전에 프롬프트를 훑어 표식 글의 제목·설명 글자가 있으면 모델을 부르지 않는다(§7). 못 막는 것도 시험이 '못 막는다'고 단언한다.
4. **정적 규칙** `tests/ai_flow_scan.py`(AF0–AF6·AF8 — AF4 는 S2b 가 올린 진입 함수 둘에 걸리고 AF7 은 T3 라 패치 초안만 있다) — 새 AI 호출 지점·새 `_posts` 읽기 지점·임포트 격리·Fact 분기의 AI 0 을 소스로 못박는다(§8). AI 키를 주지 않는 것(AF7)은 워크플로 변경(T3)과 함께 더한다(§12-3).

## 2. 안전 기본값 다섯 가지

코디네이터가 위임 규칙의 안전 기본값으로 정해 운영자에게 알렸다(요청 R-235). 이 묶음의 시험과 표식 설계가 전제로 둔다.

1. Fact 글은 **국문 단독**이다. AI 번역은 금지다(영문은 규칙 기반 틀을 만들지 않는 한 만들지 않는다).
2. Fact 글의 **제목에는 숫자·값을 넣지 않는다**(라벨·지역·기준일만). 이것은 2단계 `recipes` 의 몫이고, 그 전에는 값이 든 제목이 나올 수 있으므로 이 문서의 장치가 모두 먼저 서 있어야 한다.
3. Fact 글은 **사진 교체·보강 대상에서 제외**한다(표식으로 거른다). AI 가 고르는 이미지는 쓰지 않는다.
4. 세 제공처(캐나다 통계청 `statcan`·영국 정부 콘텐츠 API `uk_govuk`·미국 NOAA 우주날씨 `noaa_swpc`) 자료에는 **AI 서술·번역·요약·다듬기·이미지 설명 단계를 만들지 않는다.**
5. **켜는 변경은 이 묶음에 없다** — 레지스트리 값·`content_source`·워크플로·정지 변수·광고 표면.

## 3. 싱크 표 — AI 를 직접 부르는 곳(등록 목록)

AI SDK 를 가져오거나 클라이언트를 만들거나 `.generate_content` 를 부르는 함수(`AI_PRIMITIVES`), 호출 객체 `llm(...)` 를 부르는 함수(`LLM_CONSUMERS`), 호출 객체를 만드는 함수(`LLM_FACTORY_CALLERS`). 목록은 지금 코드(Gate 병합 뒤 main)의 전부로 시작했고, 코드와 **양쪽으로** 일치해야 한다(`tests/test_ai_flow.py`). 새 항목을 올릴 때는 이유를 쓰고 이 표도 같이 고친다(`tests/test_ai_flow_docs.py` 가 표와 상수의 일치를 본다). 등록 목록을 늘리거나 규칙을 약하게 하는 변경은 T3 다.

| 종류 | 파일:함수 | 이유 |
|------|-----------|------|
| SDK 원시 호출 | `generator.py:get_client` | Chance 생성기의 Gemini SDK 클라이언트 만들기(지연 임포트) — 모든 Chance AI 호출의 바닥 |
| SDK 원시 호출 | `generator.py:_generate.call` | Chance 생성기의 SDK 호출 한 번 — `call_gemini_with_fallback` 만 부른다 |
| SDK 원시 호출 | `pipeline/llm.py:make_gemini_llm.client` | 공용 호출 객체의 SDK 클라이언트 만들기(지연 임포트) — Blogger·Naver·이슈 수정·대표 사진·주제 확장의 바닥 |
| SDK 원시 호출 | `pipeline/llm.py:make_gemini_llm.call` | 공용 호출 객체의 SDK 호출 — 모델 폴백·재시도·시간 상한·호출 기록이 이 안에 있다 |
| 호출 객체 소비자 | `pipeline/topics.py:pick_topic` | Blogger·Naver 주제 확장 — 자기 블로그 이력 주제만 프롬프트에 싣는다 |
| 호출 객체 소비자 | `pipeline/run.py:run` | Blogger·Naver 글 쓰기 — 프롬프트 파일·주제·게이트 탈락 사유(다른 블로그 제목은 표식 항목을 건너뛴 목록에서) |
| 호출 객체 소비자 | `pipeline/main_image.py:ask_queries` | Blogger 대표 사진의 영어 검색어 — 방금 쓴 Blogger 글의 제목·라벨(AI 가 쓴 글) |
| 호출 객체 소비자 | `pipeline/edits/ops.py:op_llm_patch` | 이슈 수정의 AI 최소 패치 — 대상은 루트 고정 페이지뿐이고 표식이 있거나 표식 여부를 알 수 없는 파일은 거절한다 |
| 호출 객체 소비자 | `pipeline/edits/ops.py:image_queries` | 이슈 수정의 이미지 검색어 — `op_image` 가 표식 글을 AI 를 부르기 전에 거절한다 |
| 호출 객체 만들기 | `pipeline/run.py:run` | Blogger·Naver 러너가 호출 객체를 만든다(키가 있을 때) |
| 호출 객체 만들기 | `pipeline/edits/runner.py:build_llm` | 이슈 수정 러너의 호출 객체 만들기 |
| 호출 객체 만들기 | `pipeline/edits/runner.py:_process` | 이슈 수정 러너가 `build_llm` 을 부른다 |

데스크톱 저장소에는 AI SDK 도 AI 호출도 없다(전수 확인). 이 표는 블로그 저장소만 다룬다.

## 4. 호출 지점 표 — AI 입구·프롬프트·검색어 함수를 부르는 곳

아래 이름을 **부르거나 참조하는**(지역 변수 별칭·가져오기 줄에 적은 이름 — `from generator import call_gemini_with_fallback as ask` 의 별칭 호출도 그 줄에서 센다 — 콜백·`getattr` 에 글자 상수로 넘기는 것 포함) 함수는 이 표에 있는 것뿐이어야 한다(`AI_CALL_SITES`, 규칙 AF5). 그림자 실행(`shadow_run._evaluate`)은 `generator` 를 가져오지 않고 인자 `g` 로 받아 부르므로 임포트 그래프에 보이지 않는다 — 그래서 호출 지점 표가 막는다(감사 F6·F14).

| 이름 | 파일:함수 | 이유 |
|------|-----------|------|
| `_generate` | `generator.py:call_gemini_with_fallback` | 모델 폴백 루프 — SDK 호출 한 번은 이 함수만 부른다(그래야 입구 방벽을 거친다) |
| `get_client` | `generator.py:_generate.call` | SDK 호출 한 번이 클라이언트를 얻는 곳 — 다른 함수가 직접 얻으면 입구 방벽을 건너뛴다 |
| `get_client` | `pipeline/egress.py:<module>` | 외부 접속 예외 표에 데이터로 적힌 글자 한 줄 — 호출하지 않는다(호출 지점이 아니라 이름만 적은 표) |
| `call_gemini_with_fallback` | `generator.py:make_image_queries` | 기존 글 이미지 교체의 영어 검색어 |
| `call_gemini_with_fallback` | `generator.py:generate_blog_posts` | 새 글 쓰기 — 피드 항목과 최근 제목 30개(표식 글이 빠진 목록) |
| `call_gemini_with_fallback` | `pipeline/shadow_run.py:_evaluate` | 그림자 실행의 후보 평가 |
| `build_post_prompt` | `generator.py:generate_blog_posts` | 새 글 프롬프트 조립 |
| `build_post_prompt` | `pipeline/shadow_run.py:_evaluate` | 그림자 실행의 프롬프트 조립(같은 함수·같은 입력) |
| `make_image_queries` | `generator.py:repair` | 기존 글 이미지 교체 — 표식 글이면 부르기 전에 돌아온다 |

S2b 의 Fact 분기(`generator.py:generate_fact_post`·`pipeline/shadow_run.py:run_facts`)는 이 표의 이름을 하나도 부르지 않는다 — 그림자 실행에 새 호출 지점이 생기지 않았으므로 표는 그대로다(규칙 AF4·AF5 가 지킨다).

## 5. 소비자 표 — 표식 글을 AI 입력에서 빼는 곳

### 5-1. `_posts` 를 읽는 함수(AF6 이 AST 로 찾은 것과 일치)

`_posts` 폴더를 훑는 함수는 모두 종류와 이유를 올려야 한다(`POSTS_READERS`). 새 읽기 지점이 생기면 시험이 빨개진다. `filtered` 만이 AI 입력이 될 수 있는 읽기의 문이다.

| 파일:함수 | 종류 | 이유 |
|-----------|------|------|
| `generator.py:load_posts` | `filtered` | AI 입력이 될 수 있는 읽기의 유일한 문 — `for_ai=True`(기본)면 표식 글·표식 여부를 알 수 없는 글을 목록에서 뺀다 |
| `pipeline/edits/ops.py:used_image_keys` | `keys_only` | 이미 쓴 Unsplash 이미지 주소 키(호스트+경로)만 모은다 — 제목·태그·본문 글자를 돌려주지 않아 AI 입력이 될 수 없다 |
| `pipeline/edits/targets.py:load_post_index` | `human` | 이슈의 대상 글 찾기(주소·파일 이름·제목 비교) — 결과는 사람에게 보이는 코멘트에 쓰이고, AI 로 가는 길(`op_image`)은 글 파일 자체의 표식을 본다 |
| `scripts/verify_pages_deploy.py:find_candidates` | `human` | 배포 뒤 공개 확인의 최신 글 고르기 — 사이트 주소만 만든다 |

AI 를 부를 수 있는 함수와 Fact 분기는 `human` 읽기를 **직접** 부르지 못하고(규칙 AF6), `filtered` 읽기를 부를 때 `for_ai` 를 끄거나 변수·`**옵션`·위치 인자로 넘기지 못한다. `for_ai` 는 **키워드 전용** 매개변수라 위치로 넘기면 파이썬이 `TypeError` 로 막는다(D-197). 규칙은 직접 호출만 보므로 중립 도우미 한 단계를 거치는 우회는 규칙이 못 막는다 — 대신 `for_ai` 를 켜지 않은 채 읽는 모든 함수(5-2 의 `끔`·`식` 줄)와 사람용 읽기를 부르는 모든 함수(5-4 표)를 AI 가능 여부와 상관없이 **등록하게** 해서(`UNFILTERED_SITES`·`HUMAN_CALLERS`) 이름이 다른 도우미 한 단계는 등록 없이는 생길 수 없게 했다. 가져오기 별칭(`as`)·같은 이름을 가진 껍데기 함수·`map`/`lambda` 로 부르는 모양과 읽기 함수 이름을 변수로 옮겨 부르는 모양은 못 본다(사각지대 B13).

### 5-2. 표식을 거르는 읽기의 호출 지점 전수

`for_ai` 를 켠 채(`켬`)이거나 쓰지 않아 기본(`기본` — 기본값은 켜짐이다)으로 부르는 곳뿐이다. **사람·알림·사이트가 `for_ai=False` 로 읽는 곳은 지금 없다**(`끔` 이 하나도 없다). 그런 곳이 생기면 이 표에 이유와 함께 올린다. `식` 은 받은 `for_ai` 를 그대로 넘기는 통과 함수다(`other_blog_titles` 는 AI 를 부르지 않는다). `끔`·`식` 줄은 `tests/ai_flow_scan.py` 의 `UNFILTERED_SITES` 와 양쪽으로 같아야 한다(시험이 본다) — `for_ai` 를 켜지 않은 채 읽는 함수는 AI 를 부를 수 있든 없든 등록해야 보인다.

| 호출하는 함수 | 읽기 | for_ai | 이유 |
|---------------|------|--------|------|
| `generator.py:generate_blog_posts` | `load_posts` | 켬 | 새 글 프롬프트의 최근 제목이 이 목록에서 나온다 |
| `generator.py:generate_blog_posts` | `existing_titles` | 켬 | `titles[-30:]` 가 프롬프트의 '최근 다룬 주제/제목' 으로 AI 에 간다 |
| `generator.py:fix_images` | `load_posts` | 켬 | 표식 글은 사진 교체의 대상도 중복 판정의 기준도 아니다 |
| `pipeline/shadow_run.py:run` | `load_posts` | 기본 | 그림자 실행의 최근 제목 — 기본값(켜짐)을 쓴다 |
| `pipeline/shadow_run.py:run` | `existing_titles` | 기본 | 같은 이유 |
| `pipeline/run.py:run` | `entry_titles` | 기본 | 자기 블로그 이력의 제목(게이트 비교용) |
| `pipeline/run.py:run` | `other_blog_titles` | 기본 | 다른 블로그 이력 제목이 `[DUP_OTHER]` 사유로 재작성 프롬프트에 실린다 — 표식 항목을 건너뛴다 |
| `pipeline/state.py:other_blog_titles` | `entry_titles` | 식 | 받은 `for_ai`(기본 켜짐)를 그대로 넘긴다 |

### 5-3. AI 입력을 만드는 소비자와 처리

| 소비자 | AI 로 가려던 것 | 표식 글 처리 | 시험(`tests/test_ai_flow_consumers.py`) |
|--------|-----------------|--------------|------------------------------------------|
| `generator.load_posts`·`existing_titles` | 새 글 프롬프트의 최근 제목(연결 a) | 표식 글·표식 이력 항목·알 수 없는 글의 제목을 뺀다 | `ReadersTest`·`NewPostPromptTest` |
| `shadow_run.run`(생성기 함수를 인자로 받음) | 그림자 실행 프롬프트의 최근 제목(연결 a) | 같은 읽기의 기본값을 쓴다 | `ShadowPromptTest` |
| `generator.fix_images`·`repair`·`diagnose` | 영어 이미지 검색어(연결 b) | 목록에서 빠지고, 표식 글을 직접 받아도 `diagnose` 는 대상 아님·`repair` 는 AI 를 부르지 않고 돌아온다 | `FixImagesTest`·`ReadersTest` |
| `state.entry_titles`·`other_blog_titles`·`run.run` | 재작성 사유의 다른 블로그 제목(연결 c) | 표식 항목을 건너뛴다 — 사유 문구는 그대로다 | `BloggerRewriteTest` |
| `edits.ops.op_image`·`image_queries` | 이슈 수정 이미지 검색어(연결 d) | `op_image` 가 표식 글(알 수 없는 글 포함)을 AI 를 부르기 전에 거절한다 | `IssueEditTest` |
| `edits.ops.op_llm_patch` | 페이지 원문 전체(F5) | 표식이 있거나 표식 여부를 알 수 없는 파일은 거절한다(대상은 원래 루트 고정 페이지뿐) | `IssueEditTest` |
| `edits.pages._candidates` | 고정 페이지 후보 | `_posts` 아래 글은 후보도, `discover.include` 도 될 수 없다(`PagesError`) | `IssueEditTest` |
| `topics.pick_topic` | 자기 블로그 이력 주제 | Chance 이력을 읽지 않는다(구조) | AF3 등록 |

대조군도 같은 시험이 확인한다: 표식만 없는 같은 모양의 글은 지금처럼 최근 제목·검색어·사유에 그대로 들어간다(시험이 아무것도 안 하는 시험이 아님을 보인다).

### 5-4. 사람용(`human`) 읽기를 부르는 곳

사람용 읽기(5-1 의 `human`)를 부르는 함수는 AI 를 부를 수 있든 없든 모두 올려야 한다(`HUMAN_CALLERS`). AI 를 부를 수 있는 함수와 Fact 분기가 부르는 것은 이 등록과 상관없이 규칙 AF6 이 막는다 — 이 표는 중립 도우미 한 단계를 거친 우회가 '새 호출 지점' 으로 보이게 하는 자리다(D-197).

| 파일:함수 | 이유 |
|-----------|------|
| `pipeline/edits/runner.py:resolve_request` | 이슈의 대상 글 찾기(`load_post_index`) — 결과는 사람에게 보이는 코멘트에 쓰이고 AI 입력으로 가지 않는다 |
| `scripts/verify_pages_deploy.py:select_newest` | 배포 뒤 공개 확인의 최신 글 고르기(`find_candidates`) — 사이트 주소만 만든다 |

## 6. 표식 규칙(`pipeline/provenance.py`)

- **정본**: 글 머리말의 한 줄 `provenance: "facts"`, 이력(`history.json`) 항목의 `"provenance": "facts"`. 키는 `provenance`, 값은 정확히 `facts`.
- **읽는 곳은 한 군데**(`provenance.py`)이고 소비자는 그 함수만 쓴다. 키는 대소문자·앞 공백·따옴표·`- ` 목록 표지와 상관없이 찾는다. **읽는 문법은 좁은 허용 목록이다** — 울타리가 정확히 `---` 이고 `...` 줄이 없고 줄 안 CR 이 없고 0열 줄이 `키: 값`(평문 키·이스케이프 없는 따옴표 키)이나 `- ` 항목일 때만 읽을 수 있음으로 보고(`none`·`facts`·`other-value`), 나머지(복합 키 `?`·앵커·태그·별칭·병합 키 `<<`·이스케이프를 쓴 키·줄 머리 BOM·긴 대시 울타리·`...` 줄)는 `unknown` 으로 막는다(D-196). PyYAML 이 `provenance` 키로 읽는 모든 모양이 차단임을 시험(`YamlDifferentialTest`)이 손으로 만든 모양 표와 무작위 머리말로 못박았고, 독립 검증의 차분 도구가 108만 건에서 빠져나감 0 을 보였다 — 그러나 **YAML 이 읽는 모든 모양을 막는다고 증명한 것은 아니다**(사이트 빌더의 파서는 PyYAML 과 다를 수 있다). YAML 로는 표식이 아닌데 막는 경우(과차단)는 안전한 쪽이다.
- **쓰는 곳은 생성기뿐**이다(`with_marker`·`entry_with_marker`). 모델이 쓴 머리말의 표식은 머리말째 믿지 않고 구조화된 값으로 다시 쓰며(`_front_matter_from_model`), 최종 머리말 검사(`front_matter_problems`)는 기본(`allow_provenance=False`)에서 표식 키를 문제로 센다. 저장소의 완성된 글을 읽는 시험(`tests/test_posts_front_matter.py`)만 `allow_provenance=True` 로 읽고, 그때도 표식은 하나뿐이고 값이 정확히 `facts` 여야 한다.

| 표식 상태 | 뜻 | AI 입력에서 |
|-----------|----|-------------|
| `none` | 닫힌 머리말이 있고 표식 키가 없다 | 쓸 수 있다(오늘 동작) |
| `no-front-matter` | 머리말이 없다 — 표식이 있을 수 없다 | 쓸 수 있다(오늘 동작) |
| `facts` | 정본 표식 | 뺀다 |
| `other-value` | 표식 키는 있으나 값이 `facts` 가 아니거나 키가 둘 이상이다 | 뺀다 |
| `unknown` | 머리말이 닫히지 않았다·울타리가 정확히 `---` 가 아니다·`...` 줄이 있다·YAML 이 줄바꿈으로 읽는 글자(줄 안 CR 포함)나 제어 문자가 있다·한 줄 묶음(`{…}`) 머리말이다·0열 줄이 `키: 값` 이나 `- ` 항목이 아니다·읽을 수 없는 파일(UTF-8 아님)이다 | 뺀다 |

**알 수 없으면 막는다**: 파일을 못 읽거나 머리말이 깨져 표식 여부를 알 수 없는 글은 표식 글로 보고 AI 입력에서 뺀다. 단 `_posts` 가 없거나 비어 있는 정상 상태는 그대로 지나간다. 읽지 못하는 파일(읽기 오류·UTF-8 아님)은 목록에도 넣지 않는다 — 예전에는 UTF-8 이 아닌 글 하나가 생성기를 멈췄지만 이제는 건너뛴다. 표식 글이 없을 때 동작이 달라지는 경우는 이처럼 지금 저장소에서는 일어나지 않는 경우뿐이다 — 허용 목록 문법 밖의 머리말(머리말 없이 `---` 가로줄 사이에 산문 줄이 낀 글·값 안 줄 중간의 CR 은 옛 읽기가 표식 없음으로, 새 읽기는 알 수 없음으로 막는다. 오늘 저장소의 글·초안·페이지·문서 파일 535개와 앱 저장소 파일 21개의 판정은 하나도 바뀌지 않았다 — 독립 검증 2차)과 오류 경우(UTF-8 이 아닌 글·머리말이 닫히지 않은 글에 대한 이슈 이미지 변경·`discover.include` 에 `_posts` 를 올린 명세).

### 표식 쓰는 곳

표식을 쓰는 함수를 부르는 곳은 **생성기 안의 Fact 분기 두 군데**다(S2b, 2026-11-11 — 나머지 코드에는 없다): 글은 `generator.py:fact_check_post` 가 `with_marker` 를 한 번, 이력 항목은 `generator.py:fact_history_entry` 가 `entry_with_marker` 를 한 번 부른다. 호출 이름마다 한 곳이다(글과 이력은 서로 다른 파일). `tests/test_provenance.py` 의 `MARKER_WRITERS` 가 같은 둘을 올려 두고 시험이 `provenance.py` 밖의 다른 호출을 막으며, `tests/test_ai_flow_docs.py` 가 이 절·`MARKER_WRITERS`·코드의 실제 호출 위치가 같은 말을 하는지 본다. 새 호출 지점을 올리려면 이유를 쓰고 셋을 같이 고친다.

## 7. 런타임 방벽(`pipeline/ai_guard.py`)

**위치**: AI 입구 둘이 맨 앞에서 `assert_clean(prompt)` 를 부른다 — `generator.call_gemini_with_fallback`(생성기·그림자 실행)과 `pipeline.llm.make_gemini_llm` 의 호출 객체(Blogger·Naver·이슈 수정·대표 사진·주제 확장). 걸리면 `AiInputForbidden` 이 올라오고 모델은 한 번도 부르지 않는다(재시도·모델 폴백·대기 없음, 호출 기록에도 남지 않음). 예외 문구에는 글 내용이 없고 조각의 **종류**(`post-title`·`post-title-prefix`·`post-description`·`history-title`)만 있다. 방벽이 막은 것을 '검색어 생성 실패'·'인프라 실패'·'주제 확장 실패' 로 삼키지 않도록 `make_image_queries`·`ops.image_queries`·`op_llm_patch`·`topics.pick_topic`·`main_image.ask_queries` 는 이 예외를 `except Exception` 앞에서 그대로 다시 던진다(뒤 둘은 독립 검증이 찾아 고쳤다 — D-195). 정적 규칙은 이 재던지기를 못박지 않는다(사각지대 B8) — 일곱 장면 시험이 지금 곳을 못박는다(§10).

**무엇을 비교하나**: 표식 글(머리말 `provenance` 가 `facts` 이거나 모르는 값이거나 머리말을 읽을 수 없는 글)의 제목 전체·제목 앞 24자·설명 앞 40자, 이력의 표식 항목의 제목·주제 전체와 앞 24자. 비교는 정규화한 글(NFKC → 소문자 접기 → 글자·숫자만)에서 한다 — 공백·대소문자·문장 부호·JSON 따옴표 이스케이프가 달라도 같은 글로 본다. 훑는 곳은 지금 작업 폴더와 이 코드가 든 저장소의 `_posts`(.md·.markdown·.html 등)와 `history.json` 이다.

| 상수 | 값 | 뜻 |
|------|----|----|
| `TITLE_MIN_CHARS` | 12 | 정규화한 제목이 이보다 짧으면 조각으로 쓰지 않는다(일반 낱말과 겹쳐 정상 호출을 막는다) |
| `TITLE_PREFIX_CHARS` | 24 | 제목 앞부분 조각의 길이 |
| `DESCRIPTION_PREFIX_CHARS` | 40 | 설명 앞부분 조각의 길이 |
| `DESCRIPTION_MIN_CHARS` | 20 | 정규화한 설명이 이보다 짧으면 조각으로 쓰지 않는다 |

**비용**: 표식 글이 없으면 프롬프트를 읽지도 않고 지나간다. 조각은 파일별 (수정 시각·크기·inode) 캐시로 모으되 **호출 직전의 목록·수정 시각을 매번 확인**해 바뀐 파일만 다시 읽는다(방금 읽은 파일은 수정 시각 해상도 때문에 한동안 믿지 않고 다시 읽는다). 조각 수와 프롬프트가 아주 크면 색인 검사로 바꾼다(글자 수에 비례). `_posts` 가 수백 편이어도 호출당 ms 단위이고, 표식 글 1000편·조각 15000개·수 MB 프롬프트에서도 시간 한도 안이다(`tests/test_ai_guard.py` 의 `PerformanceTest`). `_posts` 폴더를 열 수 없거나 파일이 10만 개를 넘으면 확인하지 못한 것이므로 막는다.

**못 막는 것** — 시험(`LimitsTest`)이 '못 막는다'고 단언한다. 방벽을 믿고 구조 방벽(§5)이나 AI 키 미전달(2단계)을 줄이면 안 되는 이유다.

| 번호 | 못 막는 것 | 이유 |
|------|------------|------|
| L1 | 긴 제목의 뒤쪽 조각만 | 비교하는 것은 제목 전체와 앞 24자뿐이다 |
| L2 | 값만(`3.5%`·`103.4`) | 조각으로 쓰기엔 너무 일반적이다 |
| L3 | 의역 | 글자가 다르다 |
| L4 | 번역(영어 등) | 글자가 다르다 |
| L5 | 짧은 제목(정규화한 글자 수가 `TITLE_MIN_CHARS` 미만) | 일반 낱말과 겹쳐 정상 호출을 막는다 |
| L6 | 표식 글의 태그·분류·본문 | 일반 낱말이거나 비교 대상이 아니다(본문은 AI 로 가는 길이 없다) |
| L7 | 방벽 밖에서 AI 를 부르는 새 길 | 입구가 둘뿐이라는 전제 — 새 입구는 AF2·AF3·AF5 가 막는다 |
| L8 | 깨졌거나 목록이 아니거나 5천만 바이트를 넘는 `history.json` 의 표식 항목 | 읽지 못한 이력은 훑지 않고 지나간다(통과) — 생성기도 깨진 이력을 '빈 기록' 으로 읽어(`read_history`) 이력 제목이 그 길로는 AI 입력이 되지 않는다. **조용히 지나가지는 않는다**: 방벽이 고정 문장 한 줄(`[방벽] 이력 history.json 을 읽지 못해 …`)을 실행 로그에 남긴다(오래된 파일은 한 번만). 표식 글 파일(`_posts`)은 이와 따로 훑는다. 읽지 못하면 막는 방식은 Chance 이력 하나가 깨졌을 때 이 파일을 쓰지 않는 Blogger·Naver·이슈 수정까지 모든 AI 호출을 멈추므로 택하지 않았다(2단계에서 Fact 이력 항목이 생긴 뒤에 다시 검토) |
| L9 | 읽기 오류가 난 글 파일 | 그 호출에서는 조각을 못 만든다(통과). '조각 없음' 으로 굳혀 캐시하지 않아 다음 호출에서 다시 읽어 막는다(예전에는 오래된 파일이면 영구히 통과했다). 생성기도 같은 글을 읽지 못해 건너뛴다(`읽기 실패` 줄) |
| L10 | 수정 시각·크기·inode 가 그대로인 제자리 수정(`touch -r`·`rsync -t`·`cp -p` 처럼 시각을 되돌리는 도구로 표식을 더한 오래된 글) | 파일별 서명 캐시가 같은 파일로 본다. 방금 쓴 파일(3초 안)은 다시 읽는다 |
| L11 | `bytearray`·`memoryview` 로 든 프롬프트 | 글자로 읽지 않는다. 지금 호출자는 모두 `str` 이다 |
| L12 | 정규화가 접지 못하는 글자(키릴·그리스 동형 글자·한글 호환 자모·아랍-인도 숫자·점 없는 ı)와 글자를 바꾸는 변형(`json.dumps` 기본 `ensure_ascii=True`·`html.escape` 의 한 따옴표·URL 인코딩) | 현재 코드는 제목을 이렇게 바꿔 프롬프트에 싣지 않는다(생성기는 `ensure_ascii=False`). 제목 앞 '24자' 는 정규화한 24자라 원문 한국어는 약 33자 이상이어야 앞 조각이 만들어진다 |
| L13 | 블록 글자(`title:` 뒤에 세로선·`>` 표지를 쓴 것)·여러 줄 따옴표로 쓴 제목·설명 | 방벽은 머리말의 제목·설명을 한 줄 값으로만 읽어 YAML 과 다르게 읽는다 — 제목 조각을 놓친다(구조 방벽이 막고, 생성기가 쓰는 정본은 한 줄 큰따옴표 제목이다) |

## 8. 정적 규칙(`tests/ai_flow_scan.py`·`tests/test_ai_flow.py`)

소스 글자를 받는 **순수 함수** 스캐너다. 시험 안에 위반 소스를 심어 '빨개짐'을 증명하고(합성 변이 68개, 전부 잡힘), 지금 트리에서 위반 0 이며, 등록 목록이 코드와 양쪽으로 맞는지·등록 항목을 하나씩 빼면 규칙이 울리는지 본다. 변이는 메모리 안의 글자 바꾸기라 디스크의 파일을 건드리지 않는다. 보증이 아니다 — 알려진 모양의 목록이다.

| 규칙 | 이름 | 검사 대상 | 막는 연결 |
|------|------|-----------|-----------|
| AF0 | PARSE | 읽을 수 없거나 문법 오류인 파일, 너무 깊게 중첩되어 읽지 못한 파일(파이썬 판·운영체제마다 깊이 한계가 달라 어떤 판에서만 읽히는 소스가 있다)은 확인하지 못한 것이므로 위반 | 검사를 피하는 파일 |
| AF1 | F-IMPORTS | Fact 모듈 ↔ AI 모듈 임포트 단방향 격리(함수 안 임포트·상대 임포트·상수 글자 `import_module`·`if TYPE_CHECKING:` 의 else 가지 포함). 다리는 `BRIDGES`(지금 `generator` 하나)뿐이고 다리 안쪽은 따라가지 않는다 | Fact→AI·AI→Fact·새 다리 |
| AF2 | AI-PRIMITIVES | AI SDK 가져오기·클라이언트 생성·`.generate_content`(호출·별칭 참조)·AI 제공처 주소 글자는 등록된 함수에만 | 새 AI 호출 |
| AF3 | LLM-CONSUMERS | 호출 객체 `llm(...)` 를 부르는 함수와 호출 객체를 만드는 함수는 등록된 곳에만 | 새 소비자 |
| AF4 | FACT-NO-AI | Fact 분기 진입 함수(`DEFAULT_ENTRIES`·설정 `fact_entries`)에서 호출·참조로 닿는 곳에 AI 가능 함수·AI 이름이 없다(별칭·콜백·글자 상수 포함). **진입 함수는 둘이다**(`generator.py:generate_fact_post`·`pipeline/shadow_run.py:run_facts` — S2b 가 올렸다). 합성 소스로 규칙이 작동함도 따로 시험한다. 값으로만 쓰인 안쪽 함수의 몸통은 읽지 못한다(B16) | Fact 분기에서 AI 로 |
| AF5 | AI-CALL-SITES | `call_gemini_with_fallback`·`_generate`·`get_client`·`build_post_prompt`·`make_image_queries` 를 부르거나 참조하는(글자 상수로 넘기는 것·가져오기 줄에 적은 이름 포함 — 호출하지 않는 데이터 표에 이름만 적은 것도 세므로 이유를 '이름만 적은 표' 로 등록한다) 곳은 등록된 함수뿐 | 새 호출 지점(그림자 실행 같은) |
| AF6 | POSTS-FOR-AI | `_posts` 를 읽는 함수는 모두 등록돼 있고, AI 가능 함수·Fact 분기는 `human` 읽기를 **직접** 부르지 못하며 `for_ai` 를 켠 채로만(끄거나 변수·`**옵션`·위치 인자로 넘기지 못한다) `filtered` 읽기를 직접 부른다. 더해서 `for_ai` 를 켜지 않은 채 읽는 모든 함수(`UNFILTERED_SITES`)와 사람용 읽기를 부르는 모든 함수(`HUMAN_CALLERS`)는 AI 가능 여부와 상관없이 등록돼야 한다 | 표식을 거르지 않는 읽기 |
| AF8 | NO-DYNAMIC | Fact 모듈이 `subprocess`·`importlib`·`runpy`·`ctypes`·`multiprocessing`·`socket` 을 가져오거나 `exec`/`eval`·동적 임포트·서브프로세스 호출이 있으면 위반이고, Fact 분기에서 닿는 함수에는 이름이 동적인 `getattr`·`globals()[식]` 도 위반이다(Fact 모듈 안의 비상수 `getattr` 는 정당한 쓰임이 있어 세지 않는다 — 못 잡는다, B12) | 이름 조립·동적 실행 |

**AF7(워크플로의 AI 키 식 — `chanceblog.yml`·`chance-shadow.yml` 에서 `content_source` 가 `facts` 면 키를 비운다)은 규칙으로 더하지 않았다.** 스위치(`content_source`)는 S2b 가 코드에 이었지만 워크플로의 키 식을 바꾸는 것은 T3 라 패치 초안과 식 증명 시험만 만들었다(§12-3). 워크플로가 바뀐 뒤 규칙을 더한다.

### 사각지대 — 시험(`BlindSpotTest`)이 '못 잡는다'고 단언한다

| 번호 | 못 잡는 것 | 막는 것 |
|------|------------|---------|
| B1 | 비 Fact 코드에서 이름을 조립해 AI 함수를 부른다(`globals()['call_gemini' + '_with_fallback']`) | 런타임 방벽·AI 키 미전달 |
| B2 | 비 Fact 코드가 `importlib` 로 비상수 이름의 모듈을 불러 부른다 | 런타임 방벽 |
| B3 | 비 Fact 코드가 서브프로세스로 다른 파이썬 파일을 실행한다 | 런타임 방벽·사람 검토 |
| B4 | 경로를 인자로 받는 일반 읽기 도우미를 거쳐 `_posts` 를 읽는다 | 소비자 표(§5)의 사람 검토 |
| B5 | 목록에 없는 AI 제공처 주소 | 사람 검토 |
| B6 | AI 키를 환경변수에서 읽는다 | 2단계의 AF7(워크플로 키 식) |
| B7 | `_posts` 밖의 파생 목록(`history.json`·`pages.json`)을 직접 읽어 제목을 AI 입력으로 넘기는 새 함수 — AF6 은 `_posts` 읽기만 등록한다 | 이력 표식 항목을 거르는 `entry_titles` 기본값(§5)과 런타임 방벽의 이력 조각(§7) |
| B8 | AI 를 부르는 코드를 감싼 `except Exception` 이 방벽 예외를 삼키는 새 코드 — 재던지기 줄을 지우거나 바꿔도 규칙이 울리지 않는다 | 일곱 곳의 장면 시험(§10)이 지금 곳만 못박는다·사람 검토 |
| B9 | 호출 객체를 `llm` 이 아닌 이름으로 받아 부르거나 별칭 임포트(`make_gemini_llm as mk`)로 만들어 부른다 — AF3 은 이름 글자로 본다 | 런타임 방벽·사람 검토 |
| B10 | AI 이름과 같은 이름의 새 함수가 진짜 함수를 감싸 부른다 — 정의 자신 안의 참조는 새 호출 지점으로 세지 않는다(같은 이름 재정의·조건부 정의도 같다) | 런타임 방벽·사람 검토 |
| B11 | AF2 의 SDK 목록 밖: 목록에 없는 패키지 이름(`langchain_google_genai` 따위)·`chats.create(...).send_message` — 목록은 닫혀 있다 | 런타임 방벽·사람 검토 |
| B12 | Fact 모듈 안의 이름 조립(`globals()[이름]`·`getattr(m, 이름)`)·`os.execv`·`__builtins__['exec']` — Fact 분기에서 닿는 함수에는 이름 조립 규칙이 있지만 Fact 모듈 자체에는 없다 | 2단계 진입 함수 등록 뒤의 AF4·AF8·사람 검토 |
| B13 | 읽기 함수 이름을 변수로 옮겨 `for_ai` 를 끈다(`reader = generator.load_posts; reader(for_ai=False)`·`functools.partial`·`getattr`·가져오기 별칭 `as`·같은 이름을 가진 껍데기 함수·`map`/`lambda`) — 규칙은 호출 이름으로 본다 | 키워드 전용 `for_ai`(위치 인자는 `TypeError`)·런타임 방벽·사람 검토 |
| B14 | 비 Fact 코드가 코드 글자를 `exec`/`eval` 로 돌린다 — 글자 속 이름은 이름 글자 상수가 아니다 | 런타임 방벽·사람 검토 |
| B15 | `_posts` 읽기 탐지(AF6)는 '훑는 호출 + 알려진 이름(`POSTS_DIR`·`POSTS`·글자 `_posts`·그 함수 안의 변수)' 이다 — 함수 밖에 둔 다른 이름의 상수·상수 목록을 돌며 훑기·매개변수 기본값의 `_posts`·글 하나를 경로로 바로 읽기·이어붙인 경로는 놓친다(`generator.POSTS_DIR.glob` 같은 점 이름은 이제 잡는다) | 소비자 표(§5)의 사람 검토·표식 방벽 |
| B16 | Fact 분기 안에서 이름 있는 안쪽 함수를 부르지 않고 값으로만 넘기거나 담는다(콜백·목록·키워드 인자 — `handlers = [_cb]`) — AF4 는 안쪽 함수를 '부르는 줄' 만 따라가고 값으로 쓰인 안쪽 함수의 몸통은 읽지 않는다 | Fact 구역은 콜백을 람다·최상위 함수로 넘기고 이름 있는 안쪽 함수를 두지 않는다(`tests/test_fact_branch.py` 의 `NoNamedInnerFunctionTest`)·사람 검토 |

감사 때 사각지대였던 `operator.attrgetter('…')` 로 AI 함수 이름을 꺼내는 길(감사 M14)은 이름을 글자 상수로 넘기는 것을 참조로 세어 이제 AF5 가 잡는다. 이름을 조립한 글자(B1)는 못 잡는다. 독립 검증이 찾은 별칭 임포트(`from generator import call_gemini_with_fallback as ask`)는 가져오기 줄의 이름을 참조로 세어 이제 AF5 가 잡고, `if TYPE_CHECKING:` 의 else 가지의 임포트는 AF1 이 센다(D-198). 위 B9–B15 는 그 검증이 찾았지만 잡지 못하는 모양이다 — 못 잡는 모양은 이 표에 올리고 시험이 '못 잡는다' 고 단언한다. B16 은 S2b 가 Fact 구역을 쓰다가 찾았다: 처음에 콜백을 이름 있는 안쪽 함수로 썼을 때 AF4 가 그 몸통을 읽지 않았다(D-255 — 안쪽 함수를 부르는 줄은 따라가고 담기만 한 것은 못 본다).

## 9. 요구사항별 처리

전수 확인 보고서 7절의 요구사항 가운데 이 묶음이 하는 것과 하지 않는 것이다.

| 번호 | 내용 | 처리 |
|------|------|------|
| R3 | 임포트 단방향 격리를 새 연결 모듈까지 넓힘 | 한다 — AF1(`BRIDGES` 한 군데·다리 안쪽은 따라가지 않음). 기존 `NoConnectionTest` 는 S2b 가 '허용 연결 한 군데' 로 고쳤다(§12-3) |
| R4 | `provenance: facts` 표식(머리말·`history.json`) | 한다 — §6 |
| R5 | 표식 소비자(AI 입력을 만드는 읽기에서 표식 글을 뺌) | 한다 — §5 |
| R6 | 런타임 방벽 `assert_clean` | 한다 — §7 |
| R7 | 이미지 단계에서 표식 글 제외, `image_change` 는 표식 글을 AI 없이 거절 | 한다 — `diagnose`·`repair`·`fix_images`·`op_image` |
| R8 | Blogger·Naver 재작성 입력에서 표식 글 제외(사유 문구는 그대로) | 한다 — `entry_titles`·`other_blog_titles` |
| R13 | 읽기 경로 고정 | 한다 — AF6 의 읽기 지점 등록·`for_ai` 규칙. Fact 묶음을 저장한다면 `_posts`·`history.json`·`pages.json`·프롬프트 파일 밖 별도 폴더에 두고 `_config.yml` 의 `exclude` 에 올린다(지금은 저장 계획이 없어 시험으로 고정만 — 프롬프트 파일(레지스트리 `prompt` 와 `.github/editorial` 아래 글)에 표식 줄이 없음은 `tests/test_ai_flow.py` 의 `PromptFilesTest` 가 고정한다) |
| R16 | 연결 코드를 이어 붙이기 전의 사전 확인 | 하지 않는다 — 2단계 몫: 연결 전에 §3·§4·§5 의 표와 §12-1 의 같이 고칠 시험 단언 목록을 먼저 읽고, 새 호출 지점·읽기 지점을 등록한다 |
| R17 | 시험·문서 보호 | 한다 — 이 문서·`tests/test_ai_flow_docs.py`·`SECURITY_GUARDRAILS.md` G-L10(시험 약화는 T3) |
| R1·R2·R12·R14·R15·R18 | 후보 공급 한 함수·AI 키 미전달·영문·출처 문구 자동 첨부·호출 한도·제목 정책 | S2b(2026-11-11)가 R1(후보 공급 한 함수 — `fact_supply.supply`)·R15(호출 한도 — 연결 코드가 호출 예산을 건다)를 이었고 R12(영문 없음)·R14(출처 문구)·R18(제목 정책)은 S2a 부품을 연결했다. **R2(AI 키 미전달)는 T3 패치 초안만 있고 적용하지 않았다**(§12-3) |

## 10. 방벽이 걸렸을 때(운영 신호)

방벽이 걸리면 로그에 `AiInputForbidden: 표식 글(구조화 공개 자료로 만든 글)의 제목·설명 글자가 AI 입력에 들어 있어 AI 를 부르지 않았습니다(종류 …)` 가 남는다. 이것은 **입력을 만드는 코드의 결함 신호**다 — AI 는 한 번도 불리지 않았고 값은 새지 않았다. 운영자가 할 일은 없고, 세션형 AI 가 로그를 읽어 어느 읽기가 표식을 거르지 않았는지(`docs/AI_FLOW.md` §5 의 표와 `tests/test_ai_flow.py` 의 AF6)를 찾아 고친다. 방벽은 정상 입력을 막지 않도록 짧은 제목·일반 낱말을 비교하지 않는다(§7 한계).

예외는 **AI 를 부르는 일곱 곳 어디서도 삼켜지지 않는다** — 아래 표가 어디서 올라오고 어디서 다시 던져지는지, 사람이 로그에서 무엇을 보는지다(독립 검증이 `pick_topic`·`ask_queries` 두 곳의 삼킴을 찾아 고쳤다 — D-195). 일곱 곳은 각각 장면 시험(방벽이 실제로 불리는 SDK 계층 가짜 클라이언트)이 '예외가 나오고 모델은 불리지 않았다'와 대조군(표식 글의 글자가 없으면 모델을 부른다)을 못박는다. 이슈 수정은 이미지 변경과 본문 패치를 한 곳으로 센다.

| 번호 | AI 를 부르는 곳 | 다시 던지는 줄 | 예외가 가는 곳 | 실행·보이는 흔적 | 시험 |
|------|-----------------|----------------|-----------------|-------------------|------|
| 1 | 새 글 쓰기 `generate_blog_posts` | 없다(`except ValueError` 만 — 방벽 예외는 후보 탈락으로 다루지 않는다) | `run_cli` 가 요약을 남기고 다시 던진다 | 종료 1 · `작업 실패: AiInputForbidden …` | `NewPostPromptTest` |
| 2 | 기존 글 이미지 교체 `fix_images` → `make_image_queries` | `generator.py` 의 `make_image_queries` | `repair`·`fix_images` 를 거쳐 올라온다(그 전에 처리한 글의 호출은 남는다) | 종료 1 | `FixImagesTest` |
| 3 | 그림자 실행 `shadow_run._evaluate` | 없다(`try` 가 없다) | 그대로 올라온다 | 종료 1 | `ShadowPromptTest` |
| 4 | Blogger·Naver 생성 루프 `run.run` | 없다(`except LLMError` 만 — 방벽 예외는 `LLMError` 가 아니다) | 그대로 올라온다(이력·요약·`::error::` 없이 역추적만 남는다) | 종료 1 | `BloggerRewriteTest` |
| 5 | 이슈 수정 `op_image` → `image_queries`, `op_llm_patch` | `ops.py` 의 `image_queries`·`op_llm_patch` | `process_issue` 밖으로 나오고 명령줄 `main` 이 '예상하지 못한 오류가 발생했습니다: AiInputForbidden' 로 남긴다 | 종료 비영 | `IssueEditTest` |
| 6 | 주제 확장 `topics.pick_topic` | `topics.py` 의 `pick_topic` | `run.run` 밖으로 올라온다(예전에는 '주제 확장 LLM 호출이 실패했습니다. 키·할당량을 확인하세요' 로 오안내됐다) | 종료 1 | `ChainSmallScenesTest` |
| 7 | 대표 사진 검색어 `main_image.ask_queries` | `main_image.py` 의 `ask_queries` | 사진 단계의 바깥 `find_main_image` 는 '어떤 경우에도 예외를 올리지 않는다' 는 계약이라 이유 `UNEXPECTED(AiInputForbidden)` 한 줄로 남긴다 | 실행은 초록 · 로그 `[IMAGE] 건너뜀: UNEXPECTED(AiInputForbidden)` 한 줄과 `::notice::` 주석 · 실행 요약 '대표 사진: 없음(UNEXPECTED(AiInputForbidden))' · 글은 사진 없이 올라간다(예외 사슬 장면 `blogger_image:leak` 로 확인) | `ChainSmallScenesTest` |

일곱 곳 밖에서 `except Exception` 이 AI 호출을 감싸는 새 코드가 생기면 이 재던지기가 빠질 수 있고 정적 규칙은 그것을 못 잡는다(사각지대 B8) — 새 소비자를 올릴 때 이 표에 한 줄과 장면 시험을 더한다.

## 11. 허용 목록 묶음이 고칠 것

`docs/SOURCE_POLICY.md`(허용 목록 가지)는 이 묶음이 건드리지 않았다. 아래 문장은 전수 확인이 찾은 '문서·코드 불일치'(감사 F7·F14)를 한 가지 말로 맞추려고 허용 목록 묶음이 그 문서에서 고칠 것이다.

1. **9절 2항(`topic` 은 자체 제목뿐)** 을 이렇게 바꾼다: '구조화 Fact 경로가 만드는 글의 제목·이력 `topic`·로그·탈락 기록에는 우리가 만든 제목만 쓰고, 그 제목에는 값을 넣지 않는다(라벨·지역·기준일만). 그 글과 이력 항목에는 출처 표식(`provenance: facts`)이 붙고, AI 입력을 만드는 읽기(최근 제목·이미지 검색어·재작성 사유·이슈 수정)는 표식 글을 건너뛴다(docs/AI_FLOW.md). `allowlist` 가 자체 제목으로 정화하는 후보는 **피드 글(Gemini 로 쓰는 글)의 길**이고 Fact 분기는 다른 길이다.'
2. **9절 3항(프롬프트 입력)** 을 이렇게 바꾼다: '`allowlist` 의 `build_post_prompt` 가 자체 제목만 받는 것은 피드 글의 길이다. **Fact 분기는 프롬프트를 만들지도 AI 를 부르지도 않는다**(정적 규칙 AF4). 이 세 곳 자료에는 AI 서술·번역·요약·다듬기·이미지 설명 단계를 만들지 않는다. `ai_processor_policy.json` 의 `input_scope` 는 다른 제공처에 AI 를 쓰게 될 때만 뜻이 있고 이 세 곳에는 적용하지 않는다.'
3. **9절 7항(직접 소비자도 같은 정화)** 을 이렇게 바꾼다: '그림자 실행의 피드 후보 반복문은 지금처럼 `own_title_batches` 를 지난다. **Fact 후보는 `own_title_batches`·`build_post_prompt` 를 지나지 않는다** — `assemble` 로만 만들고 그림자 실행에서도 AI 를 부르지 않는다.'
4. **12절 ③(프롬프트에 원문 링크·출처 규칙이 없다)** 끝에 이렇게 덧붙인다: 'Fact 후보는 프롬프트 경로를 타지 않으므로 이 문제는 피드 글의 길에만 남는다.'
5. **10절·`ai_processor_policy.json`** 에 '이 세 곳(`statcan`·`uk_govuk`·`noaa_swpc`)의 자료는 AI 처리기에 보내지 않는다'를 적는다.
6. **레지스트리 스키마(R10)**: '이 제공처 자료를 AI 에 쓰지 않는다'를 적는 값(예: `ai_input` 에 `NOT_USED`·`OWN_POLICY` 와 `Provider.ai_blocked`)을 새로 만들고 `computed_strict_tier`·A2·A3 이 알려진 칸으로 읽게 한다. 실행 시 `ai_blocked` Fact 를 AI 단계에 넘기는 코드는 거부한다. 지금은 세 곳 모두 `ai_input` 이 `IMPLIED` 라 켜려 하면 A2 가 막는다.
7. **`pipeline/egress.py` 등록 두 줄**(허용 목록 가지를 이 묶음 위로 옮길 때만): 그 가지의 외부 접속 예외 표에 데이터로 적힌 글자 `get_client` 한 줄(호출하지 않는다)을 스캐너가 새 호출 지점으로 세어 `test_ai_flow`·`test_ai_flow_docs` 가 빨개진다. 스캐너를 약하게 만들지 않고 등록으로 푼다 — `tests/ai_flow_scan.py` 의 `AI_CALL_SITES["get_client"]` 에 `("pipeline/egress.py", "<module>")` 항목(이유: 호출 지점이 아니라 이름만 적은 데이터 한 줄)을 더하고, 이 문서 §4 표에 한 행(`get_client` · `pipeline/egress.py:<module>` · 이름만 적은 표)을 더한다. 등록의 부작용으로 그 파일 최상위 전체에 `get_client` 허용이 생기지만 관문 모듈이라 위험이 작다. 데이터 표가 세 곳 이상 늘면 이름만 적은 표를 따로 등록하는 방식이나 글자 상수를 호출 싱크로 흘러들 때만 세는 방식을 다시 검토한다.

## 12. 2단계가 채울 것

이 묶음은 2단계가 만들 연결 자리를 비워 두었다. 2단계(생성기 연결)가 할 일이다 — S2b(2026-11-11)가 1–6항을 이었고(AF7 은 T3 패치 초안만) 구현 상태는 §12-3 에 있다.

1. **Fact 분기 진입 함수 등록**: `tests/ai_flow_scan.py` 의 `DEFAULT_ENTRIES` 에 생성기의 Fact 분기 진입 함수(파일, 함수)를 올린다 — 올리는 순간 AF4·AF8 이 Fact 분기에 걸린다. 합성 시험(`FACT_BRANCH`)이 규칙이 작동함을 이미 보인다. `BRIDGES` 는 `generator` 하나로 둔다.
2. **`NoConnectionTest` 개정**: `tests/test_fact_structure.py` 의 '아무도 새 모듈 이름을 부르지 않는다' 를 '허용 연결 한 군데' 형태 — `generator.py` 한 군데만 허용(그 임포트 줄 정확히 하나)하고 그 밖은 금지 — 로 고친다. 역방향·분기 안쪽은 AF1·AF4 가 지킨다. 이 묶음의 시험 파일은 그 시험의 정규식에 걸리는 줄이 없게 짜 두었다(`tests/test_ai_flow.py` 의 `OtherLanesSafetyTest`).
3. **AF7**: 워크플로의 AI 키 식 규칙을 더한다 — `chanceblog.yml`·`chance-shadow.yml` 는 `content_source` 가 `feed` 일 때만 키를 넘기고 아니면 비운다(R2). **식은 닫힌 쪽(허용 목록)으로 쓴다**: 키 단계의 값은 `기존 조건 && 읽기 단계 출력 == 'feed' && 비밀 || ''` 꼴이다(GitHub 식의 겉 부호는 생략). `!= 'facts'` 는 읽기 단계가 실패해 출력이 비면 참이 되어 키가 새므로(열린 쪽) 쓰지 않는다. 새 조건은 기존 조건의 괄호 **밖**에 `&&` 로 잇는다 — 기존 `(이벤트 != 수동 실행 || !dry_run || real_ai)` 괄호 **안**에 붙이면 `&&` 가 `||` 보다 먼저 묶여 facts 실행에도 키가 샌다(전 조합 평가로 확인했다). 그래서 AF7 은 식 전체를 이벤트 종류·`dry_run`·`real_ai`·`content_source`·비밀 유무의 **모든 조합으로 평가하는 시험**을 함께 둔다. `조건 && 비밀 || ''` 에서 비밀을 가운데 두는 이유는 조건이 거짓일 때 빈 글자를 얻기 위해서다(비밀이 비어 있으면 `'' || ''` 로 빈 글자라 해가 없다). `chance-fix-images.yml:61`·`issue-edit.yml:100`·Blogger 둘(`blogger-en.yml:62`·`blogger-ko.yml:64`)은 모든 글을 다루므로 키를 뺄 수 없다 — 이 넷은 구조 방벽(R5·R6·R7)이 맡는다. `content_source` 는 레지스트리 값이라 워크플로 식에서 바로 읽지 못해 읽기 단계가 필요하다. `facts` 실행에서는 `main()` 의 키 검사를 건너뛰고 `get_client` 가 예외를 내며, 키 없는 실행에서 `stub_post_data` 가짜 글이 나오지 않게 한다.
4. **표식 쓰는 곳 한 군데**: `with_marker`·`entry_with_marker` 호출을 생성기 안 한 군데로 연결하고 `MARKER_WRITERS`(`tests/test_provenance.py`)와 §6 에 올린다. Fact 글의 최종 머리말 검사는 `front_matter_problems(content, source, allow_provenance=True)` 로 부른다 — 기본은 표식 금지(모델이 쓴 글에 표식이 끼는 것을 막는다)라서 그대로 부르면 정본 표식도 문제로 센다.
5. **후보 공급**: 그림자 실행이 후보를 만드는 반복문을 `generate_blog_posts` 와 하나로 합치거나(R1) `_evaluate` 앞에 같은 `content_source` 분기를 둔다. 어느 쪽이든 Fact 분기에서 닿는 곳에 AI 가 없어야 하고 새 호출 지점은 §4 표에 올린다. **Fact 분기는 AI 이름을 한 번도 쓰지 않는 별도 함수여야 한다** — `generate_blog_posts` 자체를 진입 함수로 올리면 그 함수가 AI 이름을 쓰므로 AF4 가 자기 자신에게 걸린다.
6. **제목 정책(R18)·이미지·영문**: Fact 제목에 값을 넣지 않고(`recipes`), 사진은 표식으로 이미 제외되며(§2 의 3), 영문은 만들지 않는다(R12).
7. **AI 서술(완성형 단계)**: 다른 제공처에 AI 서술을 쓰려면 별도 승인과 출력 검증이 먼저고, 이 세 곳에는 쓰지 않는다(§2 의 4).

### 12-1. 같이 고쳐야 하는 시험 단언 — 모르고 지나치면 시험이 빨개지는 곳

위 1–5항을 그대로 따르면 아래 1–4번은 시험이 빨개지고 5번은 시험이 초록인 채 가드가 비는 곳이다(독립 검증이 사본에서 따라 해 보고 찾았다). 2단계는 이 목록을 먼저 읽고 한 번에 고친다.

1. `tests/test_ai_flow_docs.py` 의 `HandOverTest` — '진입 함수 목록은 지금 비어 있다'(`assertFalse(S.DEFAULT_ENTRIES)`)를 못박는다. 1항으로 `DEFAULT_ENTRIES` 에 진입 함수를 올리면 빨개진다 → 그 줄을 '진입 함수가 등록돼 있다' 로 고친다.
2. `tests/test_ai_flow_docs.py` 의 `test_the_marker_writer_section_matches_the_test` — `MARKER_WRITERS` 가 비어 있고 6절이 '지금 없다' 고 적었음을 못박는다. 4항대로 표식 쓰는 곳을 올리면 빨개진다 → `tests/test_provenance.py` 의 `MARKER_WRITERS`·6절 '표식 쓰는 곳'·이 시험을 한 번에 고친다.
3. 합성 뼈대의 이름 — `tests/test_ai_flow.py` 의 `synthetic_fact_entry`(합성 Fact 분기를 쓰는 합성 변이들과 메시지 시험이 쓴다). 진짜 진입 함수의 이름은 이것과 겹치지 않게 짓는다 — 겹치면 합성 시험이 진짜 함수를 가리켜 빨개진다(이름은 처음에 `generate_fact_post` 였고 독립 검증 뒤 이렇게 바꿨다).
4. `tests/test_fact_structure.py` 의 `test_the_registry_has_no_switch_for_the_new_path_yet` — 생성기·레지스트리에 `content_source` 를 쓰는 순간 빨개진다 → `content_source` 를 허용하는 쪽으로 고친다(`blogs.json` 값은 켜는 변경이라 별도 승인).
5. 새 Fact 모듈(진입 함수가 부르는 새 `pipeline` 모듈)은 `tests/ai_flow_scan.py` 의 `FACT_MODULE_NAMES` 에도 올려야 AF1·AF8 이 덮는다 — 올리지 않으면 시험은 초록이지만 그 모듈에는 임포트 격리와 위험 모듈 규칙이 걸리지 않는다.
6. 진입 함수를 올린 뒤에는 AF4·AF8 이 실제 생성기의 그 함수에 걸린다 — 위 5항(후보 공급)의 '별도 함수' 조건을 지키지 않으면 AF4 가 진입 함수 자신에게 걸린다.

**S2b 처리(2026-11-11)**: 1–4번을 모두 고쳤다 — 1번(`HandOverTest`)은 '두 진입 함수가 등록돼 있다' 로, 2번은 `MARKER_WRITERS`·6절·이 시험을 한 번에(시험은 코드의 실제 호출 위치까지 본다), 3번은 합성 뼈대 이름과 겹치지 않는 진짜 이름(`generate_fact_post`·`run_facts`)으로, 4번은 '코드는 스위치를 알고 `blogs.json` 에는 값이 없다' 로 고쳤다. 5번(`fact_supply` 를 `FACT_MODULE_NAMES` 에 올림)과 6번(별도 함수 조건)도 지켰다. 고친 시험은 약해진 것이 아니라 새 상태를 더 좁게 못박는다(§12-3).

### 12-2. `NoConnectionTest` 개정 문안

`tests/test_fact_structure.py` 의 첫 시험을 '허용 연결 한 군데' 로 바꾼다 — 아래 코드는 클래스 안(들여쓰기 한 단계)에 넣는다. 생성기에 Fact 모듈을 부르는 줄이 정확히 한 군데면 통과하고, 두 줄·0줄·다른 파일에 한 줄 더는 빨개진다. 역방향·분기 안쪽은 AF1·AF4 가 지킨다.

```python
    ALLOWED = {"generator.py": 1}      # 허용 연결: generator.py 에 Fact 모듈을 부르는 줄이 정확히 한 군데

    def test_nobody_outside_the_new_files_names_the_new_modules_except_the_one_connection(self):
        targets = self.scan_targets()
        self.assertGreater(len(targets), 30)
        for path in targets:
            rel = path.relative_to(ROOT).as_posix()
            with self.subTest(file=rel):
                hits = self.PATTERN.findall(path.read_text(encoding="utf-8"))
                self.assertEqual(len(hits), self.ALLOWED.get(rel, 0))
```

### 12-3. S2b 구현 상태(2026-11-11)

위 1–6항을 S2b 가 이었다(7항은 이 묶음 밖이다). 켜지는 값은 하나도 없다 — `pipeline/blogs.json`·허용 목록 파일·워크플로·광고 표면은 바뀌지 않았다. 설계 결정은 [`FACT_PATH.md`](./FACT_PATH.md) §12 의 D-230–D-246, 결함 레지스터는 D-250–D-256 이다.

| 항 | S2b 에서 한 것 | 위치 |
|---|---|---|
| 1 진입 함수 등록 | `DEFAULT_ENTRIES` 에 `generator.py:generate_fact_post`·`pipeline/shadow_run.py:run_facts` 를 올렸다 — AF4·AF8 이 실제 분기에 걸린다(위반 0). `BRIDGES` 는 `generator` 하나 그대로 | `tests/ai_flow_scan.py` |
| 2 `NoConnectionTest` 개정 | '허용 연결 한 군데' — `generator.py` 에서 Fact 모듈을 부르는 줄이 정확히 하나(`from pipeline import fact_supply`)이고 그 밖은 0 | `tests/test_fact_structure.py` |
| 3 AF7 | 규칙은 더하지 않았다(워크플로가 바뀌어야 초록이 된다 — T3). 패치 초안(읽기 단계와 닫힌 쪽 식)과 식을 모든 조합으로 평가하는 시험을 만들었다. 지금 워크플로가 `content_source` 를 모른다는 사실과 패치 뒤에 기대하는 동작을 문서 시험이 못박는다 | `tests/test_fact_branch_docs.py`·[`FACT_PATH.md`](./FACT_PATH.md) §15-8 |
| 4 표식 쓰는 곳 | 두 군데: `fact_check_post`(글)·`fact_history_entry`(이력). `MARKER_WRITERS`·6절·시험을 같이 고쳤다. Fact 글의 최종 머리말 검사는 `allow_provenance=True` | `generator.py`·`tests/test_provenance.py` |
| 5 후보 공급 | 그림자 실행은 `_evaluate` 앞에 같은 분기(`run_facts`)를 두었고 후보는 두 길 모두 `generator.fact_prepare`(공급 함수 `fact_supply.supply` → 어댑터 → 조립기)로 만든다. **별도 함수 조건**을 지켰다 — 진입 함수는 AI 이름을 한 번도 쓰지 않는다. 새 호출 지점은 없다(§4 표 그대로) | `pipeline/shadow_run.py`·`generator.py` |
| 6 제목 정책·이미지·영문 | 제목 정책은 S2a(D-200)가 틀 단계에서 지키고, 이미지는 자체 카드 한 장(사진 선택 없음), 영문은 만들지 않는다(레지스트리가 `facts` 에 국문 단독을 요구한다) | `assets/fact-card.svg`·`pipeline/source_policy.py` |

**켜기 전에 남은 것**: AF7 패치(T3)는 `facts` 를 켜기 **전에** 병합해야 한다. 패치 전에는 두 워크플로가 `content_source` 를 몰라 `facts` 실행에도 Gemini 키가 환경에 간다(Fact 분기는 쓰지 않지만 키 미전달이라는 한 겹이 빠진다 — 결함 D-252). 패치 초안은 읽기 단계(`python -m pipeline.source_policy content-source` 의 한 줄 출력)와 닫힌 쪽 식(`기존 조건 && 읽기 단계 출력 == 'feed' && 비밀 || ''` 꼴 — 새 조건은 기존 조건의 괄호 밖)이고, 식은 이벤트 종류·`dry_run`·`real_ai`·출력 값·비밀 유무의 모든 조합으로 평가해 `feed` 가 아니면 키가 비는 것을 시험이 증명한다. 켜기 전 순서와 T3 목록은 [`FACT_PATH.md`](./FACT_PATH.md) §15-8 에 있다.

## 13. 한계

- 정적 규칙은 보증이 아니다(§8 사각지대). 런타임 방벽은 못 막는 것이 있다(§7 한계). 1차는 구조 방벽이고 마지막은 사람 검토다.
- 합쳐진 트리의 AI 흐름은 가지가 더 병합될 때마다 다시 확인한다 — 병합 뒤 `tests/ai_flow_scan.py` 의 규칙을 그 트리에 돌린다(`python tests/ai_flow_scan.py <저장소 루트>`). 출력의 '읽은 파일 N개' 를 함께 본다 — 읽은 파일이 0개이거나 스캔 범위가 하나라도 없으면 종료 2 와 '스캔하지 못했다' 문장이 나온다('위반 0건' 이 아니다).
- **공개 이후는 이 문서의 범위 밖이다**: 글이 Pages 에 올라가면 외부 AI·크롤러가 읽을 수 있다(`robots.txt` 는 모두 허용). 운영자의 코딩 AI 세션이 저장소·로그·알림을 읽는 것과 GitHub 자체의 AI 기능 설정도 이 문서의 범위 밖이다.
- 표식이 있는 글의 본문은 AI 로 가는 길이 없다(제목·태그·분류만 가던 길을 막았다). 본문 전체를 AI 에 보내는 `op_llm_patch` 의 대상은 루트 고정 페이지뿐이라는 규칙이 바뀌면 열리므로 `pages` 가 `_posts` 를 거절하고 `op_llm_patch` 가 표식을 거절한다.
- 레거시 피드 경로의 외부 기사 요약이 지금도 Gemini 입력으로 가는 것(`SOURCE_POLICY.md` 10절)은 별개의 알려진 상태이며 이 문서의 'Fact 자료' 가 아니다. 캐나다 통계청·GOV.UK·CMA 의 기사 제목·요약(최대 1,800자)도 레거시 피드(`NEWS_SOURCES`)를 통해 지금 AI 입력이다 — 운영자 조건 008('제공처 자료는 AI 에 안 넘김')과 충돌하는 **알려진 상태**이고 이 묶음의 범위 밖이다. Fact 경로를 켜는 변경(2단계의 `content_source`)이 그 경로를 막아야 하고, 그 전에 운영자가 정한다. S2b 의 `facts` 분기는 이 경로를 아예 부르지 않는다(피드 수집·기사 발췌·해석기·프롬프트가 없다) — 그러나 `content_source` 를 `feed` 로 두면 이 경로는 그대로이므로 운영자의 결정은 여전히 남는다.
- 방벽의 거짓 양성은 표식 글이 있는 저장소에서만 생긴다(표식 글 제목의 정규화 앞 24자와 같은 앞부분을 가진 다른 글의 제목, 설명 앞 40자와 겹치는 지시문, 일반 낱말만으로 된 12자 이상 제목이 지침 문구와 같은 경우). 2단계에서 진짜 프롬프트 틀이 `assert_clean` 을 통과하는지 보는 시험을 더하면 줄어든다. 표식 글을 거르는 읽기(`load_posts(for_ai=True)`)는 AI 입력이 아닌 판정(제목 유사도 중복 거절·`fix_images` 의 이미지 키)에서도 표식 글을 뺀다 — 의도된 결과다(Fact 중복은 `dedupe_key` 가 본다).
- 정적 규칙·시험의 환경 한계: 파이썬 3.10(윈도우)에서 약 36000단계 이상으로 깊은 한 줄 식은 파서가 예외가 아니라 프로세스를 끝낸다(사람이 쓰는 소스에서는 나오지 않는 크기, 리눅스는 확인하지 못했다). 윈도우 정션 순환이 있으면 3.10 의 `rglob` 이 죽는다(시험의 파일 탐색 한 곳 — 스캐너는 `os.walk` 를 쓴다).
- 시험 시간: 새 모듈 5개가 이 PC 에서 더하는 시간은 약 84초(여러 에이전트가 같이 돌 때)이고 검사 잡 상한은 10분이다 — 합쳐진 뒤 첫 실행의 소요 시간을 보고 여유를 확인한다.
- 'T3' 지정(G-L10·시험 약화는 T3)은 문서일 뿐 기계로 강제되지 않는다 — `.github/CODEOWNERS`·`pr-scope-check.yml` 을 이 묶음이 바꾸지 않았다(제약). 새 파일(`pipeline/ai_guard.py`·`pipeline/provenance.py`·`tests/ai_flow_scan.py`)의 변경을 자동으로 T3 로 잡는 장치는 없고, 켜기 전 결정 목록에 둔다.
- S2b 가 이은 Fact 분기의 AI 방어는 사람이 쓰는 규칙에도 기댄다: AF4 의 사각지대 B16(값으로만 쓰인 안쪽 함수)과 워크플로의 키 식(AF7 — T3, 패치 초안뿐)이다. 패치를 적용하기 전에 `facts` 를 켜면 키가 실행 환경에 가므로 켜기 전 순서에서 AF7 패치가 먼저다([`FACT_PATH.md`](./FACT_PATH.md) §15-8).
- 키 등급(무료·유료)과 제공처의 실제 호출 한도는 확인하지 못했다.
- 두 번째 독립 검증(2026-11-10)이 정보·낮음으로 남긴 것 — 고치지 않았고 동작·값 유출에는 영향이 없다: 위치 인자 상한(`FILTERED_POSITIONAL_MAX`)의 `existing_titles`·`other_blog_titles`·`entry_titles` 값과 `HEADER_SCAN_LIMIT`·`RACY_NS` 상수 값을 시험이 못박지 않는다(위치 인자는 `for_ai` 가 키워드 전용이라 실행 때 `TypeError` 가 막는다) · 기준선 위반 한 건이 사각지대 시험 여러 개를 연쇄로 빨갛게 한다(허용 목록을 합칠 때 원인은 11절 7항의 등록 두 줄이다) · 방벽이 훑는 글 확장자(`.md`·`.markdown`·`.mdown`·`.mkd`·`.html`·`.htm`)에 Jekyll 기본(`markdown`·`mkdown`·`mkdn`·`mkd`·`md`)의 `.mkdown`·`.mkdn` 이 없다(생성기와 `load_posts` 는 `.md` 만 쓰므로 지금 길은 없다 — 사람이 글 이름을 바꾸면 방벽만 못 본다).
