# 조사 B — 채널 모델·초안 파이프라인·서비스 계층·연결/한도·데이터 이관·발행 이력

조사 일시 2026-11-04. 대상: `cd_wt_ts`(데스크톱 main 3b1294b, 읽기 전용), 참고 `cd_wt_nv`(브랜치 `ai/claude/naver-hub-safety-1`, 커밋 안 한 변경 10개 파일 — 읽기만), 전략 문서 v1.0.0(끝까지 읽음).
약칭: `cb/` = `src/chanceblog_desktop/`, `T/` = `tests/`, `D/` = `docs/`. 근거는 `파일:줄`. **[사실]** 코드·문서에서 직접 확인 · **[추정]** 내 판단 · **[확인 못 함]** 이 사본에서 확인 불가.
규모 [사실]: 소스 약 20,416줄(ui 포함), 시험 파일 92개·시험 함수 약 3,688개(`grep -c "def test_"`), CI = 모든 브랜치 push 에서 `python -m unittest discover` (Windows·Ubuntu × 3.10·3.12 네 칸, 의존성 설치 단계 없음 — `.github/workflows/ci.yml`), `requirements*`·`pyproject.toml` 없음.

---

## 요약 10줄

1. **5채널 열거는 이미 코드에 있다**: `cb/content/status.py:22-29` 의 `github_pages·blogger_en·blogger_ko·naver_a·naver_b`. 전략의 Blogger A(한글)·B(영문)는 `blogger_ko`·`blogger_en` 에 대응시켜야 한다(전략 id ≠ 코드 키 → 별칭표 필요, **운영자 확인 권장**). 열거를 늘릴 필요는 없고 **늘리면 저장된 모든 글이 열리지 않는다**(`model.py:152` 가 변형 키 집합을 정확히 요구).
2. 그러나 **프로필·변환·발행·명령줄은 네이버만 구현**: 프로필은 `NaverProfile` 하나(`profiles.py:18,133`), Blogger 는 상태 흐름·이름표·말씨표뿐(변환·발행·CLI 없음), GitHub Pages 는 변환·발행은 있으나 프로필이 없다(`service/draft.py:102-111` 가 비네이버는 프로필 없음으로 처리).
3. **채널 프로필·Seed·캘린더를 `settings.json` 에 넣을 수 없다**: `Settings._read` 가 최상위 칸 3개(`schema·repo_path·naver_profiles`)와 정확히 일치해야 읽는다(`context.py:173-175`). 새 칸을 더한 파일은 코드를 같이 고치지 않은 쪽(옛 버전·롤백된 앱·현재 시험)이 `SETTINGS_INVALID` 로 멈춘다(`D/RELEASE.md:21` 롤백 설계와 부딪힘) → 새 데이터는 **별도 파일 + 별도 `schema`**(`connections.json`·`quota_state.json` 선례).
4. **전략의 `.yaml` 은 그대로 쓸 수 없다**: 저장소 어디에도 YAML 파서·의존성이 없고(`import yaml` 0건, CI 에 설치 단계 없음) 모든 저장은 JSON. 채널 프로필·Seed 초기 목록은 JSON 으로 두거나 아주 좁은 자체 파서를 시험과 함께 만들어야 한다.
5. **초안 쪽은 이미 '후보 → 작성 기반' 순수 함수**(`draft_plan.build_plan`, 외부 입력 없이 결정적)이고 5채널 키를 받는다. 그러나 후보에서 읽는 칸은 8개뿐(`topic·keyword·sub_keywords·post_type·blogs·seasonality·data_date·duplicate`) — 전략의 `search_intent·topic_cluster·topic_angle·target_reader·monetization_tags·점수 6항목`은 초안이 읽지 않는다. `DraftPlan` 은 **항상 완성**을 돌려주므로(`draft_plan.py:238-241`) '작성 기반 부족' 판정은 새 엔진이 따로 해야 한다.
6. **'지어내지 않기'(`check/claims.py`)는 전략 §16·§20.1·§22.4 와 크게 겹치지만, §20.2 브랜드·§21 건강·§22.1 협업 표시·§22.3 경제적 이해관계 표시는 코드에 전혀 없다**(`협찬`·`제휴`·`affiliate`·`sponsor` 검색 결과: 낱말 규칙 2곳뿐). 유일한 고지 기능은 AI 활용 고지(글 **끝**에 붙임, 네이버만 — `render/naver.py:211-214`).
7. **서비스 계층 규칙이 새 모듈을 강하게 제약한다**: `T/test_service_safety.py` 가 `service/*.py` 전체를 AST 로 훑어 `urllib·socket·http·subprocess·ctypes` import 금지, 파일 쓰기는 (파일, 함수) 허용목록 — 그러므로 **실제 Search Trend HTTP 구현은 `service/` 밖**에 두고 호출자(fetcher)를 주입해야 하며, 새 JSON 저장은 `context.write_json` 경유 + 허용목록 갱신(시험 변경)이 필요하다.
8. **연결·한도**: main 에는 `naver_openapi`(일 25,000, 호출 코드 없음)뿐이고, `cd_wt_nv` 가 이를 `naver_apihub`(키 1개·내부 일 100/월 27,000·콘솔 30,000·70/80/90% 단계·Fail-Closed·호출 장부)로 교체 중이며 **호출 코드는 아직 없다**. TrendProvider 3종(없음/가짜/실제)과 `QuotaGuard.acquire → Lease/Denied(degraded) → report` 가 자연스럽게 맞는다.
9. **데이터·백업**: 앱 데이터는 `%LOCALAPPDATA%\ChanceblogDesktop\`(SQLite `chanceblog.db` 판 2 + JSON 3종). **`backup`/`restore` 는 SQLite 파일만** 대상이라(`store.py:894-960`, `projects.py:226-271`) 새 JSON 데이터는 백업 체계 밖에 놓인다. 후보 이력·보류함(90일 만료)처럼 질의·정리가 필요한 것은 SQLite 판 3 이 기존 선례(판 1→2 후보 표)와 맞다 **[추정]**.
10. **기존 발행 이력을 읽는 코드는 없다**(`posts.json`·`*_history.json`·`_posts` 제목/태그 읽기 0건). 지금 중복 검사는 파일명 stem·전문 일치(`backend.py:66-99`)와 네이버 A↔B 비교(`check/similarity.py`)뿐. `gate.split_post`(`gate.py:121-141`)가 머리말 파서로 재사용 가능하지만 **엄격 게이트**(허용 머리말 키 10개 고정 `gate.py:76,270-273`)라 읽기용으로는 관대한 별도 리더가 필요하다. Pages 머리말에는 전략 §24 의 추가 필드를 넣을 수 없으므로 **데스크톱 쪽 별도 장부**가 맞다(= '기존 Pages 운영 무변경' 원칙과 일치).

---

## 1. 채널 모델의 현재 모습

### 1.1 '채널'·'플랫폼'·'블로그'·'프로필'이 코드에서 뜻하는 것

| 낱말 | 코드에서의 뜻 | 근거 |
|---|---|---|
| 채널(channel) | **코드에 없는 낱말**(전략 문서의 용어). `grep -rniw channel src` → 화면 색 계산 변수 1건뿐 | [사실] 검색 |
| 플랫폼(platform) | 문자열 키 5개. `PlatformVariant.platform`, `ContentProject.variants` 의 키 | `status.py:22-29`, `model.py:82-96,137,152` |
| 가족(family) | 상태 흐름이 같은 묶음 3개 `pages`·`blogger`·`naver`(Blogger 영문·한글이 한 가족, 네이버 A·B 가 한 가족) | `status.py:21-22,32-61,70-71` |
| 블로그(blog) | 후보·초안 쪽에서 위 5개 키를 부르는 이름. `Candidate.blogs`, `DraftPlan.blog`, CLI `--blog`. 값은 플랫폼 키와 **같은 집합** | `candidates.py:366`, `draft_plan.py:216`, `cli.py:153-174` |
| 프로필(profile) | **네이버 A·B 만** 있다. `NaverProfile`(표시명·주소·주제·대상 독자·말투·카테고리 매핑·태그·금지 표현·글 길이·소제목 수·글 유형 …). 저장은 `settings.json` 의 `naver_profiles` | `profiles.py:18,133-188`, `context.py:159-207` |
| 말씨(voice) | 플랫폼마다 0/1 로 정한 문구 풀 번호. 5개 키 모두 있다: naver_a 0·naver_b 1·github_pages 0·blogger_en 0·blogger_ko 1 | `post_types.py:22-23` |

### 1.2 5채널이 코드 어디에 어떻게 있나 (있는 그대로)

| 채널(전략) | 코드 키 | 상태 흐름 | 프로필 | 변환(`render/`) | 발행(`publish/`) | 서비스 흐름 | CLI |
|---|---|---|---|---|---|---|---|
| GitHub Pages | `github_pages` | PAGES: NOT_STARTED→DRAFT_GENERATED→REVIEW_REQUIRED→APPROVED→COMMITTED→PUSHED→PUBLISHED (`status.py:33-42`) | **없음**(초안은 프로필 없이 공통 기본값, `draft.py:102-111`) | `render/pages.py` `render_pages_post` — Chance 글 형식, 머리말 10키 고정 | `publish/pages.py`·`gitrepo.py`·`deploy.py`(commit·push·공개 확인) | `pages_flow.py`(T2) | `review/preview/approve/revoke --platform pages`, `publish-pages`, `check-deploy` |
| Blogger A(한글) | `blogger_ko`(대응은 **[추정]**) | BLOGGER: …APPROVED→DRAFT_SAVED→PUBLISHED_MANUAL (`status.py:43-51`) | 없음 | **없음** | **없음** | `review.py` 머리말: "Blogger 는 이 묶음에서 다루지 않는다" | **없음**(`--platform` 선택지에 Blogger 없음, `cli.py:896,901,907,911`) |
| Blogger B(영문) | `blogger_en`(대응은 **[추정]**) | 위와 같음 | 없음 | 없음 | 없음 | 없음 | 없음. 초안 쪽에는 "영문 블로그용 제목 틀은 아직 없어 한국어 틀로 만들었습니다" 확인 권장(`draft_plan.py:584-585`) |
| Naver A | `naver_a` | NAVER: …REVIEW_REQUIRED→READY_TO_COPY→COPY_COMPLETED→PUBLISHED_MANUAL (`status.py:52-60`) | `NaverProfile` | `render/naver.py` `build_package`(복사 패키지) | 없음(복사 패키지, 발행은 사람) | `naver_flow.py` | `review/preview/approve/revoke`, `naver-package`, `naver-done`, `naver-profile` |
| Naver B | `naver_b` | 위와 같음 | `NaverProfile` | 위와 같음 | 위와 같음 | 위와 같음 | 위와 같음 |

보조 [사실]: ① Blogger 가 코드에 나타나는 곳은 `status.py`(흐름)·`candidate_csv.py:62-63`(CSV 별칭 'Blogger 영문/한글')·`service/draft.py:24`·`service/format.py:25`(화면 이름)·`post_types.py:23`(말씨)·`draft_plan.py:584`·`D/ARCHITECTURE.md`(§1 표 12행·§9 상태 흐름) 뿐이다. ② 연결 용도 `blogger`(OAuth 3칸)는 레지스트리에 있으나 "준비 중"(`connections.py` `Purpose("blogger"…)`). ③ 설정 `.env.example` 에 Blogger 클라이언트가 영문·한글 따로라고 적혀 있다.

### 1.3 채널 키가 하드코딩된 곳 (5채널 확대·변경 때 영향 지점)

| 위치 | 하드코딩 내용 | 성격 |
|---|---|---|
| `status.py:22-29` | `PLATFORM_FAMILY`(5키)→`PLATFORMS` 튜플. **순서가 곧 `selections` 정렬·CSV·화면 순서** | 정본. `D/ARCHITECTURE.md §9` 와 시험이 같은지 확인(`T/test_content_model.py:4,27`) |
| `model.py:93,137,152,188-191` | 변형 키 집합 == `PLATFORMS` **정확히 일치**(`CONTENT_INVALID`), 저장된 JSON 도 같은 검사 | 열거형을 바꾸면 기존 보관함의 모든 글이 열리지 않음 |
| `candidates.py:321-322,348-352,471-472` | `Candidate.blogs`·`selections` 가 `PLATFORMS` 안이어야 하고 겹침 금지, 순서는 `PLATFORMS` 순 | 후보 JSON·SQLite 열에 저장된 값이라 키 이름 변경 불가 |
| `store.py:758-759,833-834` | 블로그 인자 검증 | 〃 |
| `profiles.py:18,166-167` | `KEYS=("naver_a","naver_b")`, `NaverProfile.key` 가 이 둘만 허용 | 프로필 클래스를 5채널로 넓히려면 새 클래스 또는 일반화 필요 |
| `profiles.py:120-130` | 블로그 주소가 `blog.naver.com` https 만 | 네이버 전용 검증 |
| `context.py:173-175,186-207` | 설정 파일 칸 3개 정확히 일치, `naver_profiles` 키 ⊆ `NAVER_KEYS` | 새 칸 추가 금지(요약 3) |
| `draft_plan.py:647-648` | `build_plan` 이 `profile` 을 `isinstance(NaverProfile)` 로 강제 | 새 채널 프로필 타입을 쓰려면 이 검사 변경(또는 하위 클래스) |
| `draft_plan.py:45-46,631-638` | `_PROFILE_DEFAULTS` 가 `NaverProfile` 필드 기준, `_blog()` 는 `profile.key == blog` 요구 | 〃 |
| `draft_plan.py:582-585` | 네이버 프로필 없음/영문 블로그 안내 문구 분기 | 문구 |
| `render/naver.py:172` | `build_package` 가 `NaverProfile` 강제 | 네이버 전용 — 건드릴 이유 없음 |
| `service/draft.py:24,86-121` | `PLATFORM_NAMES`, `choose_blog`, `load_profile`(네이버만), `_other_naver`(A↔B 비교 상대) | 비교는 네이버 두 블로그 전제 |
| `service/format.py:25,483-486` | `PLATFORM_KO`, 프로필 표시 | 이름표 |
| `service/doctor.py:215` | 점검 루프가 `NAVER_KEYS` | 새 파일 점검은 새 줄 추가 |
| `service/cli.py:39,896-931` | `PLATFORM_ALIAS`(pages·naver_a·naver_b), `--platform`·`--blog` 선택지 | Blogger 명령 없음 |
| `ui/adapters.py:31` | `BLOG_KEYS = {"naver_a": "A", "naver_b": "B"}` | 화면 어댑터가 네이버 둘만 표시 |
| 시험 | 채널 키가 나오는 시험 파일 31개(예: `T/test_content_model.py` 24곳, `T/test_content_candidates_store.py` 5곳) | 열거형 변경 시 대량 수정 |

### 1.4 5채널로 넓힐 때 깨질 수 있는 곳 (구체)

| 변경 | 깨지는 것 | 이유·근거 |
|---|---|---|
| `PLATFORMS` 에 키 추가·이름 변경 | **저장된 모든 글(ContentProject)과 후보** | `model.py:152`·`from_dict` 엄격 검사(`model.py:261-286`), 후보 `blogs` 검증(`candidates.py:321`) — 마이그레이션 없이는 `CONTENT_INVALID` |
| `Settings` 에 칸 추가 | 칸 목록을 모르는 쪽의 설정 읽기(옛 버전·롤백·시험) | `context.py:173-175` `set(raw) != {…}` → `SETTINGS_INVALID`. `T/test_service_write_json.py:136` 이 설정·연결·사용량 저장 경로를 못박음 |
| `NaverProfile` 칸 추가 | 옛 프로필·`to_dict` 가 한 글자도 안 바뀐다는 시험 | `profiles.py:218-229`(기본값이면 저장 모양에 안 나타남 — 선례). 문서가 말하는 '기준 커밋과 글자 비교' 시험은 `T/test_naver_profile_*.py` 중 하나로 보이나 파일은 **[확인 못 함]** |
| `POST_TYPES` 에 글 유형 추가 | 후보 검증·CSV·프로필·글 유형 틀 5종 사전 전체 | `profiles.py:28`, `candidates.py:410-411`, `post_types.py:44(TEMPLATES)·144(AUDIENCES)·151(CAUTIONS)·159(INTENTS)·167(TITLES)·176(TAG_TAILS)` 가 5종 열쇠로 짜여 있음 → 전략의 `content_type`(buying_guide 등)은 **엔진 쪽 대응표로 5종에 투영**하는 편이 안전 **[추정]** |
| 네이버 패키지 JSON 에 칸 추가 | 이미 저장된 `rendered` 패키지 | `naver_flow.py:23,60` `set(data) != _KEYS` → `CONTENT_INVALID`. 표시 문구는 `body_html` 안에 넣거나 `build_for_blog` 에서 덧붙이는 방식이 선례 `naver_flow.py:80` |
| Pages 머리말에 `primary_keyword` 등 추가 | 게이트 거절 | `gate.py:76`(허용 머리말 키 10개), `gate.py:270-273` "허용하지 않는 키" `HEADER_VALUE`; `render/pages.py:39` 필수 키. 게다가 chanceblog 쪽 규칙 변경이라 전략 원칙(기존 Pages 무변경)과 충돌 |
| `service/` 에 새 파일 | `T/test_service_safety.py` | `FILES = service/*.py` 전체를 훑음(금지 import·조용한 except·허용목록 밖 파일 쓰기) |

### 1.5 전략 채널 id ↔ 코드 키 대응(제안)

| 전략 문서 | 코드 키 | 비고 |
|---|---|---|
| `github_pages` | `github_pages` | 같음 |
| Blogger A(한국어) | `blogger_ko` | 전략 §29 예시는 `naver_b` 만 나옴 — Blogger id 는 문서에 `blogger_a`/`blogger_b` 로만 표기 |
| Blogger B(영어) | `blogger_en` | 코드의 나열 순서는 en→ko(전략의 A→B 와 반대) — 혼동 주의 |
| `naver_a` / `naver_b` | 같음 | 같음 |

**[추정]** 코드 키는 그대로 두고 엔진 안에 `CHANNEL_ALIAS = {"blogger_a": "blogger_ko", "blogger_b": "blogger_en"}` 같은 입력 별칭표만 두는 것이 안전하다(저장값은 항상 코드 키).

---

## 2. 초안 파이프라인의 입력 계약

### 2.1 후보 → 초안: 실제로 읽는 칸

`service/draft.py:124-142 make_plan` → `draft_plan.build_plan(candidate, profile, options, today=, blog=, post_type=)`(`draft_plan.py:641-653`). 순수 함수 — 파일·네트워크·AI·무작위 없음(`draft_plan.py:1-11`), `draft plan` 은 보관함·설정을 **읽기만** 한다(`ctx.reading_only()`, `draft.py:1-10`).

| 후보 칸 | 쓰임 | 근거 |
|---|---|---|
| `keyword` | 제목·소제목·태그·카테고리의 중심(경험 낱말 걷어 내기 `clean_subject`) | `draft_plan.py:345-348` |
| `topic` | 제목 후보 틀의 하나(**말씨 0 이면 맨 앞**, 키워드와 다를 때만), 카테고리 추정 | `draft_plan.py:468-469` — 전략 §26(후보 주제 ≠ 발행 제목)과 부분 충돌, 아래 2.3 |
| `sub_keywords` | 보조 키워드·핵심 내용·태그 | `draft_plan.py:349-353` |
| `post_type` | 글 유형 순서 2번째(사용자>후보 추천>프로필>정보형). 후보가 '정보형'(기본값)이면 정하지 않은 것으로 봄 | `draft_plan.py:31,333-334`, 결정 D-25 |
| `blogs`, `selected_blogs` | 대상 블로그 정하기(주지 않으면 고른 블로그>추천 첫 번째) | `service/draft.py:86-99` |
| `seasonality`(달 목록) | 핵심 내용에 "관심이 몰리는 달에 맞춰 올리기" 한 줄 | `draft_plan.py:507-527` |
| `data_date` | 30일 넘으면 확인 권장(`STALE_DAYS`) | `draft_plan.py:42` |
| `duplicate` | 확인 권장 문구 | `draft_plan.py`(notes) |
| `status` | `REJECTED` 면 "계획만 만들었고 상태는 안 바꿈" 안내 | `service/draft.py:133-134` |
| **읽지 않는 칸** | `reason`·`search_demand`·`related_blog_results`·`trend`·`mobile_share`·`profile_fit`·`priority`·`keyword_opportunity`·`selections`·`project_id` | [사실] `grep -on "candidate\.[a-z_]*" draft_plan.py` 결과 8개 칸뿐 |

### 2.2 전략 §29 최소 후보 모델 ↔ 기존 `Candidate`(초안 입력 관점)

| 전략 칸 | 기존 후보 칸 | 상태 |
|---|---|---|
| topic / primary_keyword / secondary_keywords | topic / keyword / sub_keywords | 있음 |
| channel | `blogs`(1~5개 튜플), 선택은 `selections` | **1:N 구조** — 전략은 채널별 점수·채널당 후보 → 정책 필요 |
| language | 없음(블로그에서 유도) | 없음 |
| search_intent | 없음(틀 `pt.INTENTS[post_type][voice]` 에서 유도) | 없음 |
| content_type | `post_type` 5종 | 대응표 필요(1.4) |
| topic_cluster / topic_angle / target_reader | 없음(대상 독자는 선택 입력·프로필·틀에서 `pick`) | 없음 |
| scores 6항목+final | 지표 중 `priority`(0~100) 하나 | 구성 점수 칸 없음 |
| trend_status / data_status | `trend`(상승·보합·하락)·`data_date` | '데이터 부족' 상태 칸 없음 |
| duplicate_status / similar_post_ids | `duplicate`(참/거짓/None) | 세분 없음 |
| monetization_tags | 없음 | 없음 |
| selection_reasons / processing_errors | `reason`(한 줄 하나) | 분리 칸 없음 |
| status(recommended 등) | NEW·REVIEW·SELECTED·HOLD·REJECTED | 전략의 80/65/50 구간과 다른 상태 체계 |
| review_expires_at | 없음 | 없음 |

(후보 데이터 모델 자체는 다른 조사원의 담당이라 여기서는 초안 입력 관점만 적었다.) **[추정]** `Candidate` 는 5상태·9지표를 시험이 못박고 있으므로 엔진이 자체 '엔진 후보' 자료를 두고 **기존 `Candidate` 로 투영**(topic·keyword·sub_keywords·post_type·blogs·priority·reason·seasonality)해서 `draft plan` 에 넘기는 편이 기존 UI·초안 보호 원칙과 맞다.

### 2.3 값 적용 순서와 기본값

- 순서: **사용자 입력 → 블로그 프로필 → 글 유형 틀 → 후보 → 공통 기본값**, 각 값이 어느 층에서 왔는지 `sources` 에 남는다(`draft_plan.py:28-31,95-101,289-292`, D-25). 글 유형만 사용자 → 후보 → 프로필 → 정보형(`TYPE_ORDER` `:31`).
- 기본값이 클래스 기본값이면 '정하지 않은 것'으로 본다: 글 길이 800~6,000(프로필 기본)이면 공통 1,500~2,000 사용(`:45-46,394-404`), 소제목 3~5(`:36`, 프로필 기본 `profiles.py:154-155`), 제목 60자·태그 10개·문단 180자(`:37-39`).
- 선택 입력(`DraftOptions`) 11칸은 모두 선택·하나도 없어도 종료 코드 0(`draft_options.py:1-10,36-40`, D-27). 참고 URL 은 열지도 가져오지도 않는다.
- **전략 §16 "소제목 4개 이상"과의 차이 [사실]**: 기본 소제목 수 범위가 3~5 라서 3개짜리 계획이 나온다. 채널 프로필 `subheading_min=4` 로 두면 `structure()` 가 `EXTRA_STEPS` 로 채운다(`draft_plan.py:408-440`, `:420`). **그래서 '소제목 4개 이상'은 채널 프로필 값으로 충족 가능**하고, `DraftPlan` 은 실패하지 않으므로 '작성 기반 부족'은 엔진이 따로 판정해야 한다.
- 전략 §16 항목 대응: 대상 독자(`audience` 항상 값이 있음 — '명확함'은 판정 안 함) · 글 유형(`post_type`) · 검색 의도(틀의 `INTENTS`) · 소제목별 핵심 포인트(`key_points`·`step_points`) · 경험 의존 금지(`premise_of` 안전 대체 `:335-343`) · 채널에 맞는 결론(`ENDING_LINES`·사용자 `conclusion`).

### 2.4 `check/claims.py`(근거 없는 경험 표현 차단) ↔ 전략 §16·§20·§21·§22

[사실] claims: 위반 7분류(직접 사용·방문·구매·수익·체감·실제 대화/댓글·실제 사례)와 확인 권장 4분류(가격·날짜·시각·통계), 한국어 낱말 규칙(어간×어미), 선형 시간(`claims.py:26-48`, D-26·D-33). 사용자가 경험을 입력하면 **같은 문장만** 위반에서 면제(`experience_given`). `draft_plan` 은 계획 문장 전체를 이 검사로 거른다(`draft_plan.py:301-326,458-505`).

| 전략 조항 | 코드의 대응 | 겹침 |
|---|---|---|
| §16 확인되지 않은 경험에 의존하지 않음 | claims 7분류 + `post_types.premise_of/strip_premise`(후기·방문·체험 전제 후보 → 정보형 안내 글로 **안전 대체**, 바꿨다는 사실을 확인 권장에 기록) `draft_plan.py:335-343,580-` | **높음** |
| §20.1 미사용 제품: 허용(공식 사양 분석·선택 기준·호환성) / 금지(실제 사용 주장·체감 효과·존재하지 않는 장단점·직접 방문·구매 주장) | 금지 중 사용·체감·방문·구매 단정은 문장 수준 차단. **'존재하지 않는 장단점 생성'은 경험 표지가 없으면 통과** **[추정]**. 허용 항목은 `제품·서비스 소개형` 틀 | 부분 |
| §20.2 브랜드명(일반 후보는 제품군 중심, 브랜드는 조건부 허용) | **없음** — 브랜드 판별·제한 코드 없음 | 없음 |
| §21 건강(가벼운 습관 허용 / 피로·불면·통증·자세·체중·영양제 → `건강 정보 확인 필요` / 진단·치료·효과 단정 시 자동 초안 중지) | **없음**. 가장 가까운 것: claims `experience_effect`(효과·느낌을 체감했다는 주장), 후보의 결과 약속 금지(`candidates.forbidden_claim` — 상위노출·수익 보장), 일반 주의문 `GENERAL_CAUTIONS`("결과를 장담하거나 과장하는 표현은 쓰지 않습니다") `draft_plan.py:75` | 거의 없음 |
| §22.1 협업 가능 유형 표시(소형가전·PC 주변기기·숙박 …) | **없음** | 없음 |
| §22.2 협찬 전 콘텐츠는 일반 정보형 | 정보형 기본(`DEFAULT_POST_TYPE`), 협찬 전용 분기는 없음 | 정신만 같음 |
| §22.3 경제적 이해관계 유형 기록(9종) + **본문 첫 부분** 표시 문구 자동 배치 + 임의 삭제 경고 | **없음**. 가장 가까운 것은 AI 활용 고지 한 가지: `NaverProfile.disclosure`/`DEFAULT_DISCLOSURE`(`profiles.py:19,214-215`), 패키지 **끝**에 `<p>` 로 붙임(`render/naver.py:211-214`), 이미 본문에 있으면 중복 안 붙임, 체크리스트 한 줄(`:239`), CLI `--no-ai-disclosure`(`cli.py:849`), Pages·Blogger 에는 없음 | 자리만 있음 |
| §22.4 실제 경험 입력(사용 기간·환경·장단점·방문일·가격·사진·불편) | `DraftOptions.experience`(한 칸 1,000자)·`price_date`(항목 10개)·`message`·`opinion` — **구조화된 칸 아님**. 경험이 있으면 경험 단락이 목차에 더해진다(`pt.template_steps(experience=True)`) | 부분 |
| §22.4 입력 없으면 정보 소개·구매 가이드로 전환 | `premise_of` 안전 대체 + 확인 권장 문구(`draft_plan.py:580-598`) | **높음** |
| §26 후보 주제 ≠ 발행 제목 | 제목 후보 3개는 글 유형 틀로 따로 만든다(`draft_plan.py:458-505`). **단 말씨 0(naver_a·github_pages·blogger_en)은 후보 `topic` 글이 제목 후보 맨 앞**(`:468-469`) | 부분 — 의도 확인 필요 |

**협찬·경제적 이해관계 표시 기능: 없음 [사실].** 붙일 자리 **[추정]**: ① 값 입력은 `NaverOptions`(`naver_flow.py:27-34`)나 별도 입력 객체, ② 문구 삽입은 `render/naver.build_package` 가 새 프로필 항목을 읽지 않는다는 시험이 있어(`D/ARCHITECTURE.md` 프로필 점검 절) 변환을 건드리지 말고 `naver_flow.build_for_blog`(`:75-81`, `profile_options.option_warnings` 덧붙임 선례)에서 덧붙이는 방식, ③ '임의 삭제 경고'는 승인 시점 점검(`review.grant_approval`)에서 본문 첫 문단에 문구가 남았는지 확인, ④ 패키지 JSON 칸은 늘리지 않는다(위 1.4).

---

## 3. 서비스 계층·명령줄

### 3.1 모듈 역할과 새 '주제 엔진 서비스'가 끼는 자리

| 모듈(`cb/service/`) | 줄 | 하는 일 | 새 엔진과의 관계 [추정 포함] |
|---|---|---|---|
| `context.py` | 287 | `Workspace`(데이터 폴더 경로 속성), `Settings`, `Context`(부품 묶음 — 시계·git·backend·keystore 를 바꿔 끼움), `write_json`(임시 파일→`fsync`→`replace`), `keep_bad_copy`, `make_context` | 새 부품(TrendProvider·발행 이력 리더)을 **`Context` 필드로 주입**하고 새 파일 경로를 `Workspace` 속성으로 더하는 것이 기존 관례(`Context.keystore`·`backend`) |
| `backend.py` | 177 | `GitPagesBackend` — 읽기 전용 git(`inspect·unpushed_count·duplicates·same_content·expected_url`)+쓰기 위임(`commit/push/discard`)+배포 확인(`check_deployed`, fetcher 주입) | Pages 발행 전용. 이력 읽기는 여기에 섞지 말고 별도 리더 객체 권장 |
| `gate.py` | 370 | Pages 글 발행 전 검사 8종(fail closed) | 주제 단계와 무관. '작성 가능성 검사'는 같은 정신(의심스러우면 보류)으로 별도 이름 |
| `projects.py` | 312 | 글 만들기·불러오기·목록·고치기·지우기·`backup_store`·`restore_store` | **백업 대상은 SQLite 한 파일뿐**(5절) |
| `previews.py` | 135 | Pages 글·네이버 패키지·두 블로그 비교를 **만들어 보여 주기만** | 엔진의 '미리 보기(dry run)' 관례 선례 |
| `review.py` | 174 | 검토 요청→승인→승인 취소(Blogger 제외 명시) | 후보→글 연결 이후 단계 |
| `journal.py` | 101 | `publish/<글번호>.json` 발행 기록(`schema`·정확한 `_KEYS`·모양 틀리면 `SETTINGS_INVALID`) | **새 JSON 파일의 모양 선례** |
| `lock.py`/`liveness.py` | 355/73 | 글 잠금(`publish/<글번호>.lock`)·저장소 잠금(`.git/…lock`, `O_EXCL`·프로세스 생존 확인) | 배치(주 1회 후보 생성 등)의 동시 실행 방지는 `connections.locked(ctx, name)`(`KeysLock`, `locks_dir`) 재사용 가능 `connections.py:318-326` |
| `doctor.py` | 292 | 읽기 전용 점검(버전·데이터 폴더·설정·연결 설정·보관함·백업·vendor·저장소·네이버 프로필) | 새 데이터 파일 점검 줄 추가 지점(`doctor.py:215` 프로필 루프가 선례) |
| `format.py` | 738 | 한국어 출력 줄·`shown_error`·`PLATFORM_KO` | 새 명령 출력 형식 |
| `cli.py` | 1092 | 명령표·`Output`·`main` | 새 명령 그룹 추가 지점 |
| `candidates.py` `suggestions.py` `draft.py` `naver_flow.py` `pages_flow.py` `quota.py` `connections.py` `unpushed.py` | 618·303·145·145·585·740·753·199 | 후보·제안·작성 기반·네이버 패키지·Pages 올리기·한도·연결·미푸시 안내 | 후보·제안은 다른 조사원 담당 |

**[추정] 끼울 자리**: `cb/<엔진 패키지>`(순수 규칙 — `content/` 처럼 `errors`·`check.claims` 정도만 가져옴) + `cb/service/topics.py`(얇은 흐름: 읽기 전용 기본·`--yes` 로만 저장, 결과 `to_dict()`) + `cli.py` 에 명령 그룹 하나. `draft.py` 가 `candidates.list_candidates` 를 부르는 방식(읽기 전용 열기 → 순수 계산 → `PlanResult.to_dict()`)이 그대로 틀이 된다.

### 3.2 결과 봉투·오류 코드·게이트·잠금·로그

| 항목 | 현재 모양 | 근거 |
|---|---|---|
| 결과 봉투 | 서비스는 값 객체(예 `PlanResult`)+`to_dict()`, CLI 가 `Output(lines, data, code)` 로 감싼다. `--json` 이면 정상 `{"ok":true,"command":…,"data":…}`, 오류 `{"ok":false,"command":…,"error":{code,message,action,retry,detail}}`. 모든 글은 `mask` 통과(`_mask_deep`) | `cli.py:7,62-65,1035-1092`, `draft.py:47-54`(`read_only: True` 키) |
| 종료 코드 | 0 정상 · 1 처리된 오류 · 2 사용법 오류 | `cli.py:6` |
| 오류 코드 | `AppError(code, slots, detail)`; 표는 `D/TROUBLESHOOTING.md`(코드 87행, 영역별 절) → `scripts/sync_errors.py` → `errors/catalog.py`(직접 수정 금지, `ROWS`); 문구 자리표시자 `「이름」`; '재시도' 칸은 5가지 문구만(`errors/model.py` `parse_retry`); 표에 없는 코드는 `UNEXPECTED_ERROR` | `errors/render.py:62-74`, `errors/table.py:1-29`, `AGENTS.md:46` |
| 새 실패 경로 | 표에 행 추가 → `sync_errors.py` 재생성 → 시험이 문서=카탈로그 확인. 서비스가 올리는 모든 코드가 카탈로그에 있는지도 시험(`T/test_service_safety.py` `test_every_error_code_the_service_raises_is_in_the_catalog`) | 〃 |
| 실패 닫힘 | AGENTS.md 규칙 4. lock: `.git` 에 잠금 못 만들면 올리지 않음. quota: 잠금·상태 쓰기 실패 시 `Denied`(실패 열림 없음). **`Denied(degraded)` 는 오류가 아니라 '데이터 없음으로 계속'** | `AGENTS.md:27`, `quota.py` 머리말, `lock.py` 머리말 |
| 동시 실행 잠금 | 글 잠금·저장소 잠금·연결/사용량 잠금(`locks/`). 모두 `O_EXCL` 파일 + 프로세스 번호·시작 시각·실행 번호, 죽은 프로세스는 상태 읽기로 판정(Windows `os.kill(pid,0)` 금지) | `lock.py`, `liveness.py` 머리말 |
| 로그 | **앱 전용 로그 파일 없음**. `jobs/`(작업 로그)·`update/`·`assist/` 는 설계에만 있고 `src` 에 없다(`ls` 확인). 현재는 `AppError.log_line()`(가림 적용)과 stderr 진행 출력뿐 | `D/ARCHITECTURE.md:59-62`(§5 표의 `update/`·`jobs/`·`assist/` 행은 설계), [사실] 디렉터리 목록 |

### 3.3 `cli.py` 명령 목록 (이름·인자·JSON `data`)

공통: `--json`·`--data-dir`·`--repo` 등 `_common()`(`cli.py` `_common`), 한국어 도움말(`KoreanParser`), 줄임말 옵션 거절.

| 명령 | 주요 인자 | 읽기/쓰기 | `--json` `data` 계약(요지) |
|---|---|---|---|
| `doctor` | `--online` | 읽기 | 점검 줄 목록(ok/warn/fail/skip) |
| `connect` | 폴더 | 설정 쓰기 | 연결한 저장소 |
| `new`·`import-html`·`list`·`show`·`edit`·`delete` | `--title --file/--text --ref --image`·글번호·`--yes` | 글 보관함 | 글(프로젝트) 값 |
| `review`·`preview`·`approve`·`revoke` | 글번호 `--platform {pages,github_pages,naver_a,naver_b}` | review=저장, preview=읽기 | 플랫폼별 렌더링·검사 결과 |
| `publish-pages`·`check-deploy` | 글번호 `--yes --no-wait --wait --cancel` | 기본 미리 보기, `--yes` 만 commit·push | 단계(APPROVED→…→PUBLISHED) |
| `naver-package`·`naver-done`·`naver-profile` | `--blog {naver_a,naver_b}`·`--url`·프로필 옵션 20여 개 | 쓰기 | 복사용 글·발행 주소·프로필 |
| `backup`·`restore` | 파일·`--latest --yes` | SQLite 한정 | 백업 경로 |
| `candidates` | `list·suggest·show·add·import-csv·select·hold·reject·review·restore·delete·link·unlink`(`cli.py:593-657`, `D/ARCHITECTURE.md:69`) | list·show 는 읽기 전용 | 후보 행·순번 |
| `keys` | `purposes·list·add·remove·state·order·usage·policy·test` | `add` 는 숨김 입력 | 용도·항목·사용량 |
| `draft plan` | 후보 `--blog --post-type` + 선택 입력 11칸 | **읽기 전용** | `PlanResult.to_dict()` (`draft.py:47-54`) |

### 3.4 계층 규칙 (문서·시험으로 못박힌 것)

[사실] 현재 import 방향(`grep` 집계): `errors` ← {`check`, `security`} ← `content` ← `render` ← `publish` ← `service` ← `ui`. `content` 는 `errors`·`check.claims/similarity`·`echo`·(늦게)`security.mask` 만, `render` 는 `content.model/profiles`·`errors`·`core`, `publish` 는 `security.mask`·`errors`·`core`·`render.pages` 를 가져오고 **`content/render/check/publish/errors/security` 가 `service`·`ui` 를 가져오는 곳은 0건**.

| 규칙 | 근거 | 시험 |
|---|---|---|
| 서비스 코드: `subprocess·socket·urllib·http·ssl·webbrowser·ctypes·requests·asyncio` 등 import 금지 | `T/test_service_safety.py` `FORBIDDEN_IMPORTS`, `:98` | `FILES = service/*.py` 전체 |
| 서비스 코드가 쓰는 파일은 **(파일, 함수) 허용목록**(`FILE_WRITERS`·`OS_CALLS`)뿐 — `context.write_json`·`journal.remove`·`lock` | 〃 `:206-229` | 새 쓰기 함수는 이 시험 수정 필요 |
| 조용한 실패 금지(`except: pass`), `contextlib.suppress` 는 알려 둔 둘뿐 | 〃 `:82-96` | |
| 읽는 환경 변수는 `CHANCEBLOG_DESKTOP_DATA`·`CHANCEBLOG_LOCAL_REPO`·`LOCALAPPDATA`·`XDG_DATA_HOME` 뿐, 영어 비밀 낱말 문자열 금지 | 〃 `:230-246` | |
| git 은 읽기 전용 명령만 직접, 쓰기는 `publish/pages.py` 만 | 〃 `:130-158` | |
| 화면: `ui/core`·`adapters`·`launcher` 는 PySide6 를 가져오지 않는다. 화면은 서비스를 직접 부르지 않고 어댑터가 읽기 전용으로만 | `D/ARCHITECTURE.md:89-106`, `T/test_ui_core.py:1098-1113` | AST |
| `vendor/` 는 고치지 않는다(해시 시험) | `AGENTS.md:53`, `T/test_vendor_core.py` | |
| 코드↔문서 동기: §9 상태 흐름·후보 규칙은 문서와 코드가 같다는 시험, §7·§8 절 제목을 시험이 읽는다 | `T/test_content_model.py:4,27`, `T/test_content_candidates.py:38`, `T/test_repo_layout.py:187,203` | 문서 절 제목을 바꾸면 시험 실패 |
| 오류 문구는 규칙 기반, 새 실패는 표에 행 추가 | `AGENTS.md:46` | `T/test_errors_catalog.py` |
| 시험은 네트워크·실제 시크릿 없이(가짜 공급자·가짜 클라이언트), 파이썬 3.10 문법 | `AGENTS.md:47-48` | `socket` 패치 선례 `T/test_service_draft.py:132` |
| content→service 역방향 금지를 **직접** 못박는 시험 | — | **[확인 못 함]** (실제로는 0건) |

---

## 4. 연결·한도·키 보관

### 4.1 main 의 현재 상태 [사실]

| 항목 | 내용 | 근거 |
|---|---|---|
| NAVER 용도 | `naver_openapi`(클라이언트 ID·시크릿, 제공자 '네이버', 한도 **일 25,000**(제3자 문서 기준), `implemented=False` = 호출 코드 없음)·`naver_searchad`(고객 ID·액세스 라이선스·비밀 키, 한도 미확인, 호출 코드 없음) | `connections.py:138-146`, `D/ARCHITECTURE.md:70-77`(표) |
| 용도 레지스트리 | `PURPOSES`(데이터)·`Purpose`(칸·제공자·한도 창·`implemented`·`identity_field`)·항목 3개/용도·한도 묶음(같은 앱/프로젝트) | `connections.py:103-163` |
| 키 보관 | `KeyStore` 규약 `put/get/delete/exists/list_refs`, `WindowsCredentialStore`(ctypes, 대상 `ChanceBlogDesktop:<용도>:<항목번호>`, 값 2,560바이트 한도)·`MemoryStore`·시험 전용 `FileFakeStore`, `default_keystore` 는 환경 변수 없으면 진짜 보관소만 | `keystore.py:138,183,308,360,440` |
| 메타데이터/사용량 | `connections.json`(이름·상태·순서·확인 시각, 키 값 없음), `quota_state.json`(묶음별 창·막힘 해제 시각) — 둘 다 `write_json` | `context.py:129-134` |
| 한도 장치 | `QuotaGuard.acquire(purpose, calls=1, *, priority=NEW, cached=False, request=None)` → `Lease`/`Denied(degraded)`, `report(lease, outcome, retry_after, reset_at, headers)` → `ReportResult`. 우선순위 `bulk_refresh>new_candidate>selected_candidate>critical`, 남겨 둘 몫 30/20/10/0%(마지막 10% 필수 전용=절약 모드). 결과 10종 중 **전환 가능한 것은 4가지**(`rate_limited·quota_exhausted·transient_error·timeout`)뿐 | `quota.py:30-52,318,424,511,530,725` |
| 정책 | 기본은 전환이 아니라 **절약**(D-31). 캐시 먼저, 예산 줄면 우선순위대로 거절, 그래도 안 되면 `Denied(degraded=True)` — 호출하는 쪽은 '데이터 없음'으로 계속. 키가 없는 것도 오류가 아님. 어떤 오류에도 다른 키로 자동 전환하지 않는 제공자 = `rotation: never`(Unsplash). **어느 용도도 아직 실제 API 를 부르지 않는다**(`keys test` 는 '준비 중') | `quota.py:1-25`, `D/ARCHITECTURE.md:70-77`, D-30·D-31 |

### 4.2 `cd_wt_nv` 가 바꾸는 방향 [사실 — 미커밋 작업물, 읽기만]

변경 파일: `security/shape.py`·`service/cli.py`·`service/connections.py`·`service/format.py`·`service/quota.py`(+611줄) + 시험 5개. 브랜치 HEAD 는 4250c7e(현재 main 3b1294b 보다 오래됨 — `diff --stat origin/main` 에 보이는 CHANGELOG·UI 파일은 이 작업의 변경이 아니라 main 이 앞선 부분).

| 변경 | 내용(`git diff HEAD`) |
|---|---|
| 새 용도 `naver_apihub`("NAVER API HUB 검색어 트렌드") | 칸 `client_id`·`client_secret`(영숫자·`-_` 8~128자, 공식 문서에 모양 없어 느슨), **`max_entries=1`**(키 하나만, 한도 늘리려는 돌려 쓰기 금지 `ENTRY_LIMIT_DETAIL`), `rotation=ROTATION_NEVER` |
| 한도 값 | 내부 **일 100·월 27,000**, 콘솔 월 한도 **30,000**(참고값, 단계 비율의 기준) — 전략 §23.2 와 수치 일치 |
| `Provider` 새 칸 | `ledger`(시도·성공 따로 세고 호출 장부)·`fail_closed`(사용량·시계·계수·인증 상태를 확인 못 하면 신규 호출 막음)·`console_limit`·`stages`·`stop_text` |
| `Stage` | 70% 안내만 / 80% 자동 새로고침·배치 중지(직접 시작한 분석은 한 번에 5회까지) / 90%(=내부 월 한도 27,000) 신규 호출 전부 중지. 이름 `notice·limited·closed` |
| `Window.kind="month"` | 한국 시간 달력 월, 다음 달 1일 0시에 0 |
| `quota.py` | `SCHEMA_LEDGER=2`(장부 있는 파일만 판 2, 판 1 은 그대로 읽음), 호출 장부 최근 200건, `condition_hash`(민감 이름 제외), 시계 이상(5분 초과 역행) 시 자동 해제 안 함, `HOLD_STATE_LOST`(기록이 사라지면 `acknowledge` 전 호출 금지), `acquire(..., kind="", condition=None)`·`record_cache_hit`·`acknowledge` |
| 옛 용도 | `naver_openapi` 는 `legacy_to="naver_apihub"` — 읽기만 하고 새 항목 추가 불가(키는 지우지 않음) |
| 문구 | `APIHUB_STOP_TEXT`: "…새로운 데이터 조회를 사용할 수 없습니다. 저장된 정보와 기본 주제 선정 규칙으로 후보 생성을 계속합니다." — 전략 §23.4 와 같은 정신 |
| 호출 코드 | **없음**(용도 설명에 "준비 중 — 안전 장치만 있고 호출 코드는 아직 없습니다") |

**전략 §23 과의 대조 [사실+확인 필요]**: 수치(일 100·월 27,000·콘솔 30,000)·키 순환 금지(`§23.5`)·장애 시 규칙 기반 계속은 맞는다. 전략의 "알림 시작 50%"는 NCP 콘솔 쪽 알림 설정으로 보이며 nv 의 단계(70/80/90%)와 **층이 다르다** — 앱이 50% 에서도 안내를 줄지는 **운영자 확인 필요**.

### 4.3 'Search Trend 를 선택적 Provider 로 격리' — 자연스러운 모양 [추정]

```text
TrendProvider(규약)
  availability()   -> ok | no_key | quota_closed | fail_closed | error     # API 장애와 '데이터 부재'를 구분(전략 §15)
  relative_index(keyword_groups, period, device) -> TrendResult          # 상대지수(0~100)만. 검색량 칸 자체가 없음(전략 §23.5)
    TrendResult.state: ok | no_data | unavailable(reason)                  # '데이터 부족' 후보 유지·점수 재정규화는 호출하는 쪽(엔진)이 한다
NullTrendProvider      키 없음·꺼짐·시험 기본 → 항상 unavailable(no_key) — 엔진은 규칙 기반으로 계속
FakeTrendProvider      고정 표(시험·화면 시연, `sample=True` — `ui/core/services.py` 의 FakeHomeProvider 선례)
ApiHubTrendProvider    실제: QuotaGuard.acquire("naver_apihub", priority=…) → Lease 면 fetcher(주입) 호출 → report(lease, outcome)
                       Denied(degraded) → unavailable(quota_closed), 인증 불명확(`auth_state`) → unavailable(fail_closed)
```

- **우선순위 대응(전략 §27)**: 자동 주기 실행(일 1회 실시간 확인·주 1회 계절 점검) = `bulk_refresh`(80% 이후 중지), 사용자가 직접 시작한 분석 = `new_candidate`, 선택된 후보의 후속 확인 = `selected_candidate`.
- **캐시**: "동일 데이터를 반복 조회하지 않는다"(전략 §27) = `acquire(cached=True)`/nv 의 `record_cache_hit` 와 같은 개념 — 캐시 저장소(키워드 그룹+기간+기기 → 결과·조회일)는 새로 필요(5절).
- **위치**: `service/` 는 `urllib·http` 를 가져올 수 없으므로(3.4) 실제 구현은 **`service/` 밖의 새 패키지**(예 `cb/trend/`)에 두고, 호출자(fetcher)를 `Context` 로 주입한다. 이미 있는 선례는 `GitPagesBackend(fetcher=…)`(`backend.py:35-41,176-177`)와 `deploy.check_deployed(fetcher=…)`(`deploy.py:96`).
- **설정 유무**: 엔진은 Provider 가 `Null` 이어도 전 기능이 동작해야 한다(`D/ARCHITECTURE.md §8`·AGENTS.md 규칙 5 와 같은 정신).

### 4.4 지금 코드의 유일한 HTTP 코드와 '시험에서 네트워크 금지' 관례 [사실]

| 항목 | 내용 | 근거 |
|---|---|---|
| 유일한 HTTP | `vendor/scripts/verify_pages_deploy.py`(chanceblog 원본 그대로, 해시 시험): `urllib.request`·`http.client` 로 공개 사이트 주소 확인(`fetch(url, timeout, opener=urlopen, limit, headers, total)`). 앱은 `publish/deploy.py` 가 이 모듈을 불러 `fetcher`·`sleep`·`clock` 을 **주입**받는다 | `verify_pages_deploy.py:50,60,428,434,438`, `deploy.py:96-106` |
| git 네트워크 | `gitrepo.run_git`(시간 제한 90초·`fetch/push/ls-remote/pull/clone` 만 네트워크로 분류) | `gitrepo.py:25,31,184` |
| 시험 관례 | 가짜 `backend`·가짜 `fetcher`·가짜 키 보관소(`MemoryStore`·`FileFakeStore`), 필요하면 `socket.socket`·`getaddrinfo` 를 `AssertionError` 로 패치해 네트워크 시도를 잡음 | `T/test_service_draft.py:132`, `T/test_content_draft_options.py:13`, `AGENTS.md:47` |
| 시험에 쓰는 시계 | `Context.clock` 주입(`ctx.now()`) — 시간대 없는 시각은 거절 | `context.py:225-230` |

---

## 5. 데이터 위치·이관

### 5.1 앱 데이터 위치 [사실]

기본 `%LOCALAPPDATA%\ChanceblogDesktop\`(`context.py:35-41`). `--data-dir`·`CHANCEBLOG_DESKTOP_DATA` 로 바꿀 수 있으나 **git 저장소 안·프로그램 폴더 안이면 `DATA_DIR_UNSAFE`**(`context.py:44-53,110-118`, AGENTS.md 규칙 2).

| 파일/폴더 | 내용 | 스키마·형식 | 백업/복구 대상? |
|---|---|---|---|
| `chanceblog.db` | `projects`·`revisions`(글당 50판)·`drafts`(자동 저장)·`candidates`(후보) | SQLite, `application_id=0x43424450`, `user_version=2`(`store.py:44-46`) | **예**(`backup`/`restore`) |
| `settings.json` | 연결한 chanceblog 폴더 경로·`naver_profiles`(키·토큰 없음) | `schema=1`, 칸 3개 정확히 일치 | **아니오** |
| `connections.json` | 키 항목의 이름·상태·순서·정책(키 값 없음) | `schema`, 엄격 | **아니오** |
| `quota_state.json` | 한도 사용량 | `schema=1`(nv: 1·2) | **아니오** |
| `publish/<글번호>.json`·`.lock` | 올리는 중인 글 기록·글 잠금 | `schema=1`, `_KEYS` 정확히 일치 | **아니오** |
| `locks/` | 연결·사용량 잠금 | 파일 잠금 | 아니오 |
| `backups/` | `chanceblog-YYYYMMDD-HHMMSS.db` 최근 10개, `before-delete/`·`before-restore/` 안전 사본 | SQLite 사본 | — |
| (저장소 쪽) `.git/chanceblog-desktop-publish.lock` | 연결한 저장소 잠금 | | |
| Windows 자격 증명 관리자 | 키 값(`ChanceBlogDesktop:<용도>:<번호>`) | | **앱 백업 대상 아님**(OS 보안 저장소) |

### 5.2 이관·백업·복구 설계(문서) vs 구현

| 문서 | 내용 | 구현 상태 |
|---|---|---|
| `D/MIGRATION.md` | **회사 PC→개인 PC 이관** — 코드는 clone 으로 끝, 키·세션·원고·절대경로는 옮기지 않음, 새 PC 준비 순서. **앱 데이터(데이터 폴더) 이관은 다루지 않는다**(원고 보관함을 옮기는 방법·파일 목록 없음) | 문서 완성, 데이터 폴더 이관 절차 없음 **[사실]** |
| `D/RELEASE.md:20-21` | 업데이트 전 SQLite backup API 스냅샷 → 적용 → 첫 실행에서 `PRAGMA user_version` 순방향 마이그레이션 → 자체 점검 → 실패·연속 기동 실패 2회면 백업 복원+이전 릴리스 재설치 | **`update/` 패키지 없음**(설계). 마이그레이션·백업 부품(`Store`)만 구현 |
| `D/ARCHITECTURE.md:144-149`(§10) | 데이터 폴더 구성·구조 올리기 설계 | `store.py` 구현 |
| `projects.py:203-229,255-271` | `delete` 직전 `backups/before-delete` 백업, `restore --yes` 직전 `backups/before-restore` 백업 | 구현, **SQLite 한정** |
| 개인 PC 이관(별도 운영자 요구 16항목: 설치 파일·백업·마이그레이션 복구 등) | 메모에 따르면 최종 단계 — 저장소 문서에는 위 `RELEASE.md` 뿐 | 대부분 미구현 |

### 5.3 스키마 버전을 올릴 때의 관례 [사실]

| 대상 | 관례 | 근거 |
|---|---|---|
| SQLite | `SCHEMA_VERSION`(현재 2)·`MIGRATIONS = {1: _add_candidates}`(**from-판 → 단계 함수**)·DDL 상수는 **이미 나간 판이라 고치지 않고**(시험이 해시로 지킴) 바꿀 일이 생기면 **다음 판 단계를 따로** 만든다. **쓰기 잠금을 잡은 뒤** 판 번호를 다시 읽고(여러 창 동시 열기 안전), 사본 `<파일>.v<번호>.bak`(이미 있으면 같은 내용이면 재사용, 다르면 `.v1.2.bak`)을 임시 이름으로 만들어 점검한 뒤 이름을 바꾸고, 한 트랜잭션으로 올리며 판 번호도 같은 트랜잭션·COMMIT 앞에서 올린다. 실패는 원래 파일 그대로(`MIGRATION_FAILED`·`MIGRATION_BLOCKED`·`STORE_LOCKED`). **더 새로운 판 파일은 한 바이트도 안 바꾸고 `STORE_VERSION_UNSUPPORTED`**. 읽기 전용 열기 `Store.open(path, migrate=False)` | `store.py:45-62,90,124,379-490`, `D/ARCHITECTURE.md:148` |
| JSON | 최상위 `schema` 숫자 + 정확한 칸 집합(모르는 칸 거절), 쓰기는 `write_json`(임시 파일→`fsync`→`os.replace`, LF·UTF-8·키 정렬), 읽을 수 없는 파일은 `keep_bad_copy` 로 `.bak` 이름 보존. **판을 올리는 선례**: `quota_state.json` 은 판 1·2 를 둘 다 읽고 장부가 생긴 파일만 판 2 로 올려 쓴다(nv 작업) | `context.py:61-100`, `T/test_service_write_json.py`, nv `quota.py` `SCHEMAS` |
| 옛 프로필 호환 | 새 프로필 칸은 기본값이면 `to_dict` 에 **나타나지 않아** 쓰지 않는 프로필의 저장 모양이 한 글자도 안 바뀐다 | `profiles.py:35,218-229` |
| 문서·시험 | `D/ARCHITECTURE.md §9·§10`·`CHANGELOG`·`VERSION`·시험이 같이 움직임 | `T/test_repo_layout.py`, `T/test_content_migration.py` |

### 5.4 새 데이터(Seed·후보 이력·보류함·캘린더·채널 프로필)를 더할 때 지킬 것

| # | 지킬 것 | 이유(근거) |
|---|---|---|
| 1 | 사용자 데이터 폴더 안에만 저장. 저장소·프로그램 폴더 금지 | AGENTS.md 규칙 2, `unsafe_reason` |
| 2 | **`settings.json` 에 칸을 넣지 않는다** — 새 파일(예 `topics/…json` 또는 SQLite 새 표) | `context.py:173-175` |
| 3 | 파일마다 `schema` + 정확한 칸 집합 + 모르는 칸 거절, 구버전 읽기·필요할 때만 올려 쓰기 | `journal.py:58-63`, `quota_state.json` 선례 |
| 4 | 쓰기는 `context.write_json` 만 — 새 쓰기 함수는 `T/test_service_safety.py` 의 `FILE_WRITERS`·`OS_CALLS` 갱신(시험 변경 = 리뷰 대상) | 3.4 |
| 5 | 동시 실행: `locks/` 아래 이름 있는 잠금(`connections.locked`) | `connections.py:318-326` |
| 6 | **질의·만료·이력이 필요한 것은 SQLite 새 표(판 3)가 선례에 맞다** — 후보 이력(정규화 키워드·요약·처음 생성일·마지막 평가일·보류/제외 사유 유지, 상세는 90일 뒤 정리: 전략 §19)·보류함 90일·Trend 조회 캐시. 사람이 보고 고치는 설정(채널 프로필·Seed·캘린더)은 JSON **[추정]** | `store.py` 판 2 표 추가 선례, 전략 §19 |
| 7 | 판 3 DDL 은 새 상수·`MIGRATIONS[2]` 단계 추가, 판 2 상수는 고치지 않음(해시 시험), `_shape_problem`(판마다 있어야 하는 표·열) 갱신, 사전 사본·원복. **판 3 으로 올린 뒤 옛 앱으로 롤백하면 옛 앱은 그 파일을 열지 못한다**(`STORE_VERSION_UNSUPPORTED`) → 롤백 절차에 마이그레이션 직전 사본 `.v2.bak` 복원이 들어가야 한다 **[추정]**(`D/RELEASE.md:21` 롤백 설계와 연결) | `store.py:62,90-124,368-370` |
| 8 | **백업·복구·doctor 에 넣을지 결정**: 지금 `backup` 은 SQLite 만. JSON 새 파일을 만들면 `restore` 로 되돌려도 JSON 은 그대로(어긋남). SQLite 안에 넣으면 자동 포함 | `store.py:894-960` |
| 9 | 새 오류 코드는 `D/TROUBLESHOOTING.md` 표 행 + `sync_errors.py` | AGENTS.md:46 |
| 10 | **의존성 추가 금지(표준 라이브러리만)**: PyYAML 불가 → 전략의 `*.yaml` 은 JSON 으로 또는 좁은 자체 파서 | requirements 없음·CI 설치 단계 없음 |
| 11 | 파이썬 3.10 문법, Windows 경로·CRLF(`.gitattributes`)·`PYTHONUTF8=1` | AGENTS.md:48, MIGRATION.md |
| 12 | Seed 초기 목록(공통 30+채널별 20)을 **저장소에 올려도 되는 일반 키워드만**으로 만들 것(공개 저장소). 협찬·제품·브랜드 관련은 비밀이 아니어도 신중 | AGENTS.md 규칙 1·2, 전략 §31(4) **[추정]** |
| 13 | 코드↔문서: `D/ARCHITECTURE.md §9`(데이터 모델)·§10(데이터 폴더)·`CHANGELOG`·`DECISIONS`(새 결정 번호)를 같은 PR 에서 갱신. **절 제목은 바꾸지 말 것**(§7·§8 을 시험이 읽음) | `T/test_repo_layout.py:187,203` |

---

## 6. 기존 발행 이력 읽기

### 6.1 지금 데스크톱이 연결한 chanceblog 저장소에서 읽는 것 [사실]

| 읽는 것 | 어디서·어떻게 | 근거 |
|---|---|---|
| 저장소 상태(origin·main·저장 안 한 변경·올리지 않은 commit) | `gitrepo.inspect_repo`(읽기 전용 git) | `gitrepo.py:291`, `backend.py:44-64` |
| 같은 주소(slug) 파일 | `_posts` 폴더를 `rglob(stem + ".*")` + 마지막으로 받아 둔 원격 `origin/main` 의 `ls-tree` | `backend.py:66-77` |
| 내용이 한 글자도 같은 글 | `_posts` 전체를 크기 비교 후 바이트 비교 + `ls-tree` 의 blob 해시 비교(백업 복구로 같은 글 재공개 방지) | `backend.py:79-99` |
| 사이트 주소 | `_config.yml` 의 `url`·`baseurl` 만 정규식으로 읽음(YAML 파서 아님) | `deploy.py:41-57` |
| 글 경로 모양 | `POST_PATH`(`_posts/<분야>/YYYY-MM-DD-KR|EN-HHMMSS.md`) | `publish/pages.py:40` |
| 머리말·본문 파싱 | `gate.split_post(text)`(머리말 한 줄 JSON 값 파싱) — **올리려는 글을 검사할 때만** 쓴다 | `gate.py:121-141` |
| 앱이 만든 글의 발행 정보 | `PlatformVariant.published_url/published_at/remote_id`, `publish/<글번호>.json` | `model.py:82-102`, `journal.py` |
| 후보↔글 연결 | `candidates.project_id`(연결은 이 열이 기준) | `store.py` `_V2_CANDIDATES`, `D/ARCHITECTURE.md:140` |

### 6.2 없는 것과 필요한 것

| 대상 | 지금 | 필요한 것 |
|---|---|---|
| 로컬 `_posts/**/*.md` 의 제목·분야·태그·언어·날짜 읽기 | **없음**(파일명·전문 일치만) | 읽기 전용 리더. 머리말은 값이 한 줄 JSON 이라 표준 라이브러리로 읽힌다(`gate.py:136-139`). 단 `split_post` 는 `front_matter_problems` 로 엄격 검사하고(허용 키 `HEADER_KEYS` 10개), 실제 글에서 실패하면 후보 생성이 멈출 수 있으므로 **관대한 별도 리더(실패한 파일은 경고·건너뜀)** 권장 **[추정]** |
| 공개 `posts.json` | **0건**(`grep` 확인) | 사이트가 만드는 파일. 로컬 저장소에 커밋되는지 빌드 산출물인지 **[확인 못 함]**(이 사본에 chanceblog 가 없음). 네트워크로 읽으면 Provider+주입 fetcher 로 |
| Blogger 이력 JSON(`blogger*_history.json`) | **0건** | chanceblog 저장소 안에 있을 것으로 추정 — 형식·위치 **[확인 못 함]**. 읽기 전용·관대한 리더 |
| 네이버 발행 이력 | 앱 보관함의 `published_url` 이 유일(앱 밖에서 직접 올린 글은 모름) | 운영자가 입력한 발행 주소가 쌓일수록 정확. 전략 §24 에는 네이버 이력 파일이 없음 → 앱 보관함(프로젝트·변형·후보)이 이력 원천 |
| 전략 §24 권장 추가 필드(`primary_keyword`·`topic_cluster`·`candidate_id` …) | Pages 머리말은 허용 키 고정이라 **넣을 수 없음**(`gate.py:76,270-273`) | **데스크톱 쪽 별도 장부**(후보 ID↔글 번호↔발행 URL·키워드·클러스터)를 데이터 폴더에 두고 chanceblog 는 변경하지 않는다 **[추정]** |

### 6.3 중복 검사를 지금 어디서 하나 [사실]

| 위치 | 무엇을 | 근거 |
|---|---|---|
| `pages_flow.py:186-190,271-285` + `backend.duplicates/same_content` | 같은 주소(slug)·같은 내용의 글 → `DUPLICATE_SLUG`·`DUPLICATE_CONTENT` | 3.1 |
| `check/similarity.py` → `naver_flow.compare_with_other`(`:102-109`) → `review.grant_approval` | 네이버 A↔B 제목·도입부·본문·문단 구성·이미지·태그·발행일 유사도. 기준값 `Thresholds` 기본: high(전체 0.60·본문 0.60·제목 0.85·도입부 0.75), warn(0.40·0.35·0.60·0.50). 기준 이상이면 `NAVER_SIMILARITY_HIGH` 로 사람이 직접 승인 | `similarity.py:27-36,110,145` |
| `draft_plan.compare_plans` | 같은 후보로 만든 두 네이버 계획의 비슷함 경고 | `draft_plan.py:656-682` |
| 후보 쪽 | 같은 핵심 키워드(`keyword_key`)를 **같은 블로그용**으로 `topic_reuse_days`(기본 90) 안에 이미 고른 후보가 있으면 `Store.recent_selections` 경고, `add`·`import-csv` 는 같은 키워드·주제·블로그 후보를 겹치지 않게 | `store.py:824`, D-23 |
| **없음** | **'새 후보 주제 ↔ 기존 게시물'** 유사도 판정(전략 §17: 0~39/40~59/60~74/75+ 구간·다른 채널 간 허용·핵심 키워드+검색 의도+Topic Cluster+Topic Angle+대상 독자 종합) | `similarity.compare` 는 `Comparable(title, body, tags, images, date, intro)` 두 개를 재는 일반 함수라 **측정 핵심은 재사용 가능**하나, 기준값(`Thresholds`)은 네이버 쌍용이고 전략의 구간·종합 평가 규칙은 새로 필요 **[추정]** |

---

## 7. 위험·결정 필요(요약) — 전부 [추정] 또는 확인 필요

| # | 쟁점 | 내가 본 위험 | 제안 방향 |
|---|---|---|---|
| R1 | 채널 id 대응(Blogger A/B ↔ `blogger_ko`/`blogger_en`) | 순서·이름이 반대라 데이터가 뒤바뀔 수 있음 | 운영자에게 한 번 확인 후 별칭표 고정 |
| R2 | `.yaml` 파일명 | 의존성 없음 → 그대로는 못 읽음 | JSON 채택(또는 좁은 파서) — 운영자가 파일 형식에 의미를 두는지 확인 |
| R3 | 새 데이터를 JSON vs SQLite 판 3 | JSON 은 백업·복구 밖, SQLite 는 판 3 마이그레이션(시험·해시) 부담 | 이력·보류함·캐시=SQLite 판 3, 프로필·Seed·캘린더=JSON(+`backup` 확장 결정) |
| R4 | 협찬·경제적 이해관계 표시 | 코드에 없음, 패키지 JSON 칸 추가는 기존 저장분을 깨뜨림 | `build_for_blog` 에서 본문 첫 문단 삽입 + 승인 시 삭제 경고, 패키지 칸은 그대로 |
| R5 | 브랜드·건강 안전 규칙(§20.2·§21) | 코드에 없음 — 낱말 규칙(`claims` 방식)으로 새로 | 선택 보조가 아닌 규칙 기반(AI 금지 원칙 AGENTS.md 규칙 5)으로 |
| R6 | 영문 Blogger B | 제목 틀이 한국어뿐(`draft_plan.py:584`), 제목 반복 제한(§3.3) 코드 없음 | Naver 우선 범위에서는 영향 없음 — 5채널 확장 전 별도 설계 |
| R7 | `Candidate` 1:N(`blogs`) vs 전략 채널별 점수 | 기존 5상태·9지표 시험 | 엔진 후보를 따로 두고 `Candidate` 로 투영 |
| R8 | 전략 §23.1 '알림 시작 50%' vs nv 단계 70/80/90% | 층이 다름 | 앱 안내 시작점을 50% 로 낮출지 운영자 확인 |
| R9 | `topic` 이 제목 후보 맨 앞(말씨 0) — 전략 §26 | 후보 주제가 그대로 제목 후보로 노출 | 엔진 후보의 내부 문장은 `topic` 에 넣되 `draft plan` 투영 시 제목 후보로 쓰이지 않게 할지 결정(코드 변경 최소화 위해 투영 쪽에서 `topic=keyword` 로 두는 우회 가능 **[추정]**) |
| R10 | 'Search Trend 실제 호출' T 등급 | 새 시크릿 사용·네트워크는 T2~T3 | nv 가 병합된 뒤, Provider 규약·Null·Fake 먼저(키·네트워크 없이) |

## 8. 확인하지 못한 것

- chanceblog 쪽 `posts.json` 의 생성 방식(커밋 vs 빌드 산출물)과 `blogger*_history.json` 의 위치·형식(이 사본에 chanceblog 없음).
- `content→service` 역방향 금지를 직접 못박는 시험이 있는지(import 방향은 현재 지켜지고 있음을 grep 으로만 확인).
- `D/ARCHITECTURE.md` 는 줄이 매우 길어(95KB) §5 표의 긴 단락(Pages 올리기·검사·연결 설정·후보 명령줄)을 줄마다 앞쪽 1,800~2,500자만 읽었다 — 위 인용은 읽은 부분과 코드 직접 확인 기준.
- §3.3 의 `--json` `data` 계약은 `draft plan`(`draft.py:47-54`)·`keys` 일부만 코드로 직접 확인했고, 나머지 명령의 `data` 모양은 요지다.
- `nv` 작업은 미커밋이며 병합 시 형태가 바뀔 수 있음(특히 `Stage` 이름·단계 비율·`acquire` 인자).
- 시험 전체를 실행하지 않았다(규칙) — 시험 수는 `grep -c` 로만 셈.
