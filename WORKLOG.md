# Chance_Blog Work Log (AI 인수인계 로그)

> **이 파일은 AI가 작업을 시작하기 전에 반드시 최신 항목을 읽어야 하는 인수인계 로그입니다.**  
> 필독 순서: **HANDLER.md** → **AI_COLLAB.md** → **이 파일 최신 항목**

최신 항목이 위에 오도록 **최신순**으로 작성합니다.

---

## [2026-10-27] Claude – Chance 초안 → 사람 승인 후 공개 흐름(레지스트리 publish_flow, 기본 꺼짐) 추가 (작업요청서 5 PR-E, T2, 켜는 것은 T3)

**작업자**: Claude (구현 세션, 독립 검증은 별도 세션)
**대상**: Chance_Blog
**등급**: T2(생성기·워크플로·레지스트리 스키마의 새 선택 필드·새 모듈·워치독·시험·문서). `publish_flow`를 `pr`로 켜는 것은 별도의 T3(게시 방식)이고 이 변경은 켜지 않는다. `mode`·시크릿·광고 표면(`index.html`·`_config.yml`)·`pages.yml`·Blogger·발행 빈도·`인수인계/작업내용.md`·`docs/SESSION_START.md`·`docs/REQUEST_BRIEFING.md`는 바꾸지 않았다.
**승인 근거**: 운영자 채팅 2026-10-27 "추천대로 진행해줘"(`docs/analysis/2026-10-27_channel-management-plan.md` D1 (a): 구현하되 **기본 꺼짐**). 켜는 승인은 아직 없다. 켜는 승인에는 저장소 설정 확인과, 병합·닫은 초안 브랜치의 7일 뒤 자동 삭제(CHARTER T3 '브랜치 삭제'에 닿음)가 함께 들어간다.
**목적**: 구글 게시자 정책은 수동 검토 없이 자동 생성된 콘텐츠에 광고를 두지 말라고 안내한다. Chance 글을 초안 브랜치와 승인 PR 로 올리고 운영자가 PR 을 병합해야 공개(닫으면 폐기)되는 흐름을 레지스트리 스위치 하나로 고를 수 있게 한다.
**브랜치**: `ai/claude/chance-approval-flow`(기준 `origin/ai/claude/channel-names` `5c57a7c` = main `e71a6ec` + 작업 A. 작업 A 는 그 사이 main 에 병합됐다 — #47 `f8724b7`. `git rebase --onto origin/main 5c57a7c ai/claude/chance-approval-flow` 로 옮긴다: 임시 clone 에서 충돌 없이 됨을 확인했다). PR 생성·병합·Actions 실행은 하지 않았다(총괄이 처리).

### 한 일
- **레지스트리**: `publish_flow`(`direct` 기본·`pr`)와 검증(값 집합·`jekyll-git`에서만·`pr`이면 `mode: auto`). 작업 A 가 더한 `channel`·`ads` 필드와 나란히 있다. Chance 항목에 `"publish_flow": "direct"`. 값을 읽지 못하거나 틀리면 직접 게시로 떨어지지 않고 멈춘다.
- **새 모듈** `pipeline/drafts.py`(슬롯 판정 `DRAFT_PENDING`·`DRAFT_CHECK_FAILED`, 브랜치 이름, PR 제목·본문 소독 `neutralize`, 표준 라이브러리 GitHub 클라이언트)·`pipeline/draft_flow.py`(초안 올리기·PR 열기·실패 시 브랜치 보존·다음 틱 PR 다시 열기·오래된 브랜치 정리, CLI `flow`·`deliver`). **이력 항목만 생성 시점에 main 에 따로 커밋**하고 PR 에는 글 파일 둘만 둔다 — 열린 초안이 여럿이어도 `history.json` 충돌이 없고 슬롯·제목·이미지 중복 검사가 지금 그대로다(이력을 PR 안에 두면 충돌함을 실제 git 으로 재현). 별도 원장 파일(`drafts.json`)은 두지 않았다.
- **`generator.py`**: 승인 흐름이면 이력 항목에 `flow`·`branch`·`paths`, 결과 `DRAFT_CREATED`, 슬롯 판정 다듬기, 연습 실행은 '올리지 않습니다'. 직접 게시 경로는 그대로.
- **`chanceblog.yml`**: `pull-requests: write`, `발행 흐름 확인` 단계, 커밋 단계 조건에 `&& steps.flow.outputs.flow != 'pr'`, 마지막 `초안 올리기와 승인 PR 열기` 단계. **`watchdog.yml`**: `pull-requests: read`. 워크플로 `name`·`run-name`의 `[Chance]` 접두사(작업 A)는 그대로다.
- **워치독**: 열린 초안 PR 이 있으면 `STALE`·`NO_POSTS_DAY` 대신 `DRAFT_WAITING`(경고). 이 규칙이 맞게 돌도록 글이 올라온 시각을 병합 시각(`git log --first-parent`)으로 재고 병합하지 않은 초안 항목을 '글이 나온 날'로 세지 않는다(직접 게시에서는 결과 같음).
- **문서**: ARCHITECTURE §4-4(새)와 §1·§2·§2-1·§3·§4·§4-1·§4-2·§9, ACTIONS_GUIDE 3-17(새)과 여러 절, HANDLER, ENGINEERING_GUIDE(W6 예외·R15), SECURITY_GUARDRAILS(G-A10·G-L8·**G-C11** — 작업 A 의 G-C10 다음), OPS_INBOX(현황판이 알아볼 PR 모양), DEFECT_REGISTER(관측 체크리스트). 워크플로 이름은 작업 A 의 새 이름(`[구분] …`)을 쓴다. 결함 번호는 쓰지 않았다.
- **시험**: 새 시험 275개(`test_drafts`·`test_draft_flow`·`test_generator_drafts`·`test_chance_draft_workflow`·`test_draft_waiting` + 공용 `draft_helpers`, `test_workflow_names` +1)와 기존 시험 3개 파일 수정(`test_workflow_names` 권한·단계 비교, `test_manual_run_defaults` 커밋 단계 조건·배포 단계 찾기·레지스트리를 못 읽는 시험, `test_generator_slots`·`test_manual_run_defaults`의 `generator.main()`을 돌리는 두 클래스는 `draft_flow_on`을 직접 게시로 고정 — 켠 뒤에도 진짜 레지스트리 값·`git ls-remote` 네트워크 호출에 기대지 않게).

### 검증 증거
- 전체 시험 **2492개 통과**(기준 `5c57a7c` 2217개 → +275, 이 PC 354~1046초 — 다른 작업과 함께 돌 때 차이가 큼), `validate_repo.py --base origin/ai/claude/channel-names` 오류 0·경고 1(LIQUID-1, main 과 같음), pyflakes 새 경고 0(기준과 같은 16건), vermin 이 파일들 최소 3.7(저장소 전체 3.10), 3.12 전용 f-string 검사 0, actionlint 0.
- **direct 불변**: 같은 가짜 입력으로 main(`e71a6ec`)과 이 브랜치의 `generator.py`를 정기·수동·이미지 교체 24개 시나리오에서 돌려 종료 코드·표준 출력·요약·바뀐 파일 해시·호출 기록이 바이트 단위로 같음(**24/24**, 저장소 밖 도구). 음성 대조 2건은 '다름'으로 잡힘. 워크플로 YAML 은 `yaml.safe_load` 구조 비교로 새 단계 둘·권한 한 줄·조건 한 조각을 빼면 기준과 완전히 같음.
- **pr 흐름 시뮬레이션**(임시 bare origin + 로컬 clone + 실제 생성기 + 가짜 GitHub): 첫 틱 브랜치 push·이력 커밋·PR(403 뒤 다음 틱이 브랜치 내용으로 PR 다시 열기), 같은 슬롯 둘째 틱 `DRAFT_PENDING`, 병합 뒤 `ALREADY_PUBLISHED`, 정리 규칙, 슬롯 둘의 독립과 두 병합 순서, 대기 초안 제목 중복, 소독.
- **변이 시험 111개**를 작업 A 위로 옮긴 뒤 다시 돌려 **111/111 사망**(옮기기 전 첫 판에서 5개가 살아남았고 모두 시험 구멍이라 시험을 보강했다). 켜는 두 줄(`blogs.json`의 `publish_flow`·`REAL_PUBLISH_FLOW`)을 `pr`로 바꾼 사본의 전체 시험도 통과했다.

### 남긴 것 / 다음 AI에게 남기는 주의사항
- **실제 GitHub 에서는 한 번도 돌려 보지 않았다**(PR 만들기·라벨·병합 뒤 배포). 병합 직후 `direct` 첫 정기 실행(새 단계 `발행 흐름 확인`만 추가)과 켠 뒤 첫 수동 실행의 관측 목록은 `docs/ACTIONS_GUIDE.md` 3-17·`docs/DEFECT_REGISTER.md` 하단. 라벨 호출이 `pull-requests: write`만으로 되는지(`issues: write` 필요 여부)는 미확인.
- 켜기 전 운영자가 할 일: 저장소 설정 "Allow GitHub Actions to create and approve pull requests" 화면 확인(5-1 은 켜짐으로 기록, 미확인), 채팅 승인(T3). 켜는 변경은 `pipeline/blogs.json` 의 chance `publish_flow` 한 줄과, 그 값을 못 박아 둔 표지판 시험의 기준 한 줄(`tests/draft_helpers.py` 의 `REAL_PUBLISH_FLOW`)이다 — 레지스트리만 바꾸면 시험이 빨강이 된다.
- 승인 흐름을 켜면 이력의 글이 공개된 글이 아닐 수 있다(확인 필요 모음의 '최근 24시간 글 수'는 초안도 센다). 현황판은 `ai/draft/` 접두·라벨 `초안`으로 구분해야 한다. 닫은 초안의 슬롯·주제는 다시 쓰지 않는다.
- 봇이 연 PR 에는 검사가 안 돈다(GitHub 규칙). main 에 '상태 검사 필수'·'PR 필수' 보호를 켜면 병합과 이력 push 가 막힌다.
- 직접 게시에서도 레지스트리를 읽지 못하면(깨진 `blogs.json`) 글을 만들기 전에 멈춘다(`발행 흐름 확인` 단계가 빨강). 승인 흐름을 켠 채 레지스트리 오류로 승인 없는 게시가 나가지 않게 하려는 것이다 — 정상 레지스트리에서는 달라지는 것이 없다.

---

## [2026-10-27] Claude – 텔레그램·오토마우스 조사, 사용자 설정 메모 확인, 진행 현황 (문서 전용, 코드·워크플로·레지스트리·광고 표면 변경 없음)

**작업자**: Claude
**대상**: 공통 (문서)
**등급**: T1(문서)
**목적**: 사용자 요청 2건(텔레그램 알림+붙여넣기·오토마우스 자동 발행의 적용 가능성, 새 글 발행·초안 대기 알림)의 조사 결과와 사용자가 올린 설정 메모의 확인 결과를 기록하고 현황 문서를 갱신한다.

### 한 일
- 새 `docs/analysis/2026-10-27_telegram-and-rpa-feasibility.md`: 결론(알림 가능·권장, 오토마우스 비권장, 검토는 검토 화면이 있는 곳), 텔레그램 사실(한도·`copy_text`·이스케이프·토큰 노출 경로), 승인 버튼을 서버 없이 받는 구조 비교, RPA 기술·업무용 PC·정책, 채널별 권고, 확인 못 한 것·사용자가 확인할 것, 출처.
- 사용자 설정 메모(`인수인계/작업요청/Telegram_Auto_Posting_Setup_Guide.md`, 커밋 56313af): 시크릿 이름이 구현과 같음을 확인, 샘플 코드의 문제 3가지(`requests` 미설치·Markdown 모드·예외 출력으로 토큰 노출)를 문서 머리에 적고, 공개 저장소에 적힌 채팅 ID 값을 지움. 봇 `@chance_auto_post_bot` 이 존재하는 것을 공개 `t.me` 페이지로 확인(읽기 전용).
- `인수인계/작업내용.md`(헤더·§1·§2·§3 23번·§4 13~15번·§5), `인수인계/작업요청/README.md`.

### 관측·사실
- 이 PC 의 회사 프록시가 `telegram.org`·`core.telegram.org`·`web.telegram.org` 를 "비업무용 사이트 차단"(HTTP 403 안내 페이지)으로 막는다(`t.me`·`api.telegram.org` 는 열림). 조사 에이전트가 텔레그램 공식 문서를 못 읽은 원인.
- 조사 중 에이전트의 검색 호출 한도가 소진돼 일부 영역은 후기·Q&A를 보지 못했다. 교차 검증 단계는 세션 재시작으로 끝나지 않았다.
- 내장 브라우저가 `github.com` 을 "조직 정책으로 차단"(이전 시간대에는 열렸음) — 이 동안 PR 을 만들 수 없다.

### 남긴 것
- 사용자: GitHub 접속 허용(또는 허락), 텔레그램 시크릿 이름 확인·휴대폰에서 봇 `/start`, 알림 기능 병합 뒤 시험 워크플로 1회 실행, 필수 상태 검사 설정 확인.
- 병합 대기: PR-A(`ai/claude/channel-names`)·R3(`ai/claude/blogger-guardrails-round3`), 구현 중: E·B·C·TG.

---

## [2026-10-27] Claude – Blogger 주제 가드레일 3차 보강(D-64 ⑧ 2차 델타 검증 N2-1·N2-3~N2-7): 연결어 뒤 쉼표·도입구·한국어 상담 낱말 정렬·후치사 `~서`·`5G`·시험 구멍 15개 (T2, 독립 검증 델타 + 변이 증거)

**작업자**: Claude (구현 세션, 독립 검증은 별도 세션)
**대상**: Blogger
**등급**: T2 — 영문·한글 프로필의 절 경계·용량 면제 취소 패턴과 시험을 바꿨다(코드는 `pipeline/gates.py`의 설명 주석뿐). 대부분 금지를 늘리는 쪽(T1)이지만 한국어 후치사 `~서`와 `5G`처럼 막던 것을 푸는 부분이 있어 T2 로 둔다. 승인 근거: 2차 보강의 독립 검증 델타("병합 가능", `mode: draft`·한글 Blogger 전 권고 N2-1·N2-3~N2-7) + 총괄 지시. 실제 T2 승인은 총괄이 PR 에서 기록한다. **`mode`·시크릿·워크플로·`generator.py`·`registry.py`·광고 표면·`인수인계/작업내용.md`·`HANDLER.md`·`docs/SESSION_START.md`·`REQUEST_BRIEFING.md`·`ACTIONS_GUIDE.md`·`BLOGGER_API_SETUP.md`는 바꾸지 않았다**(`blogger_macat`은 off 그대로).
**목적**: 2차 보강(round2)의 독립 검증 델타가 `mode: draft`·한글 Blogger 를 켜기 **전에** 처리하라고 한 항목(`docs/DEFECT_REGISTER.md` D-64 ⑧)을 구현한다. 범위는 그 항목으로 한정했고 새 항목을 늘리지 않았다.
**브랜치**: `ai/claude/blogger-guardrails-round3` — **기준은 `origin/ai/claude/blogger-guardrails-round2`(899758587e88a008bdf4816a025b888ae9ab0b07)** 이고 그 브랜치는 아직 main 에 없다(PR 예정). round2 가 병합된 뒤 main 으로 `rebase --onto` 한다. PR 생성·병합·Actions 실행은 하지 않았다(총괄이 처리).

### 변경 사항
- **N2-1 연결어 바로 뒤의 쉼표**(`body_clause_split_patterns`): 영어 [0]·[1]·[5]·[6]의 연결어 뒤에 `,?`를 더했다(`therefore, ask your doctor`·`so, please ask…`·`thus, you should talk to…` — 검증자 29형이 모두 닫힌다). 한국어는 [1]·[4]·[5]에 같은 원리를 적용했다(`그러므로, 의사와`·`돼서, 의사와`·`그러나, 의사와`).
- **N2-2 현행 유지 + 결정 고정**: 영어 `or`·`unless`·`, then` 계열은 풀지 않았다(caveat 75문장 중 막히는 문장 main 8 → round2 38, `or`가 가장 크다 — 검증자 계산으로 `or`를 빼면 새 오탐 30→17). `docs/ARCHITECTURE.md` §7-1 '알려진 과잉 차단'과 시험 `STRICT_TRADE_OFF_EN`에 올렸다. **첫 실제 영어 초안의 `BODY_TOPIC` 빈도를 보고 `or`/`unless` 를 풀지 정한다.**
- **N2-3 한국어 `~서`·상담 낱말**: 후치사처럼 쓰인 `~서`(`에 대해서·관해서·위해서·통해서·인해서·비해서·의해서·관련해서·로서·에 따라서·앞서(앞서서)·여기서·거기서·저기서·어디서`)는 가르지 않는다(`보충제에 대해서 의사와 상담하세요.` 통과, 검증자 17문장 중 12개 풀림). `준비해서`·`소통해서`·`동의해서`는 접속 어미라 그대로 가른다(`대해서`류는 앞에 공백이 있는 낱말만 제외). 경계 패턴의 상담 낱말을 안전 패턴이 인식하는 것에 가깝게 늘렸다(완전히 같지는 않다 — 아래 V-1) — `주치의`·`한의원`·`영양사`(상담사는 `상담`이 이미 받는다), 앞에 붙는 `가까운`·`담당`·`전문`·`주변`·`동네`·`의료`·`건강`·`치과`·`한`, 부사 `우선`·`일단`·`미리`·`한번`과 부사 여러 개(`반드시 먼저 전문의`). `그렇기 때문에`·`이 때문에`·`그런 이유로`·`이런 이유로`는 `그러므로` 계열이라 닫았다. `므로`·`기 때문에`·`다 보니`·`거나`·`든지`·`아니면`·`또는`·`또한`·`게다가`·`그러면`·`물론`은 **넣지 않았다**: 검증자·구현자 정상 안내 표본 211문장에서 `므로`만 새 오탐 1(`…달라지므로 의사와 상담하세요.`)이고 나머지는 0이지만, 그 모양으로 쓴 자연스러운 정상 안내(`증상이 계속되면 쉬거나 병원을 방문하세요.`·`…달라질 수 있기 때문에 의사와 상담하세요.` 등)는 모두 새로 막힌다(영어 `or`와 같은 값). 한계로 문서화했다. 독립 검증(V-1)이 '맞췄다'는 표현이 사실보다 넓다고 짚어 고쳤다: 안전 패턴 [1]은 `진료·진찰·방문·도움·조언`+10자 안의 `의사·약사·전문가·전문의·의료진·병원` 같은 '행위 먼저' 표현도 면제로 인식하지만 경계 앞내다보기는 `상담·문의`만 받고, 상담 낱말 앞 수식어가 닫힌 목록이라 `내과`·`산부인과`·`정신건강의학과`·`믿을 만한`·`해당 분야`·`가족 주치의` 같은 말이 붙으면 면제만 남는다(독립 검증 V-1 — 한글 Blogger 를 켜기 전에 목록을 한 번 더 점검).
- **N2-4 열린 도입구**: 영어 [5]·[6]의 도입구를 넓혔다 — `you might/may want|wish to`·`you'll want to`·`you'd better`·`you really/definitely/certainly/probably should`·`you would be wise to`·`it would be wise to`·`it is advisable/recommended…`·`it makes sense to`·`I would suggest`·`we recommend`·`please do`·`kindly`·`don't forget to`·`do not hesitate to`·`feel free to`·`always remember to`·`take a moment to`·`be certain to`, 3인칭 주어(`people/readers/everyone/they/we should`…), 도입구 두 겹(`you should make sure to`), 상담 부사 `definitely`·`probably`·`really`·`certainly`·`simply`(뒤에 쉼표도), `refer to`·동명사(`asking`·`talking to`·`seeing a doctor`), 새 연결어 `however`(쉼표 없이도)·`accordingly`·`consequently`·`for this reason`·`nevertheless`·`nonetheless`·`that said`. 검증자 도입구 31형 중 열린 것 31→7(조건·부사절 `if in doubt,`·`to be safe,`·`of course,`… 6개는 '조건절 + 쉼표 + 상담 구절'과 구별할 수 없어 일부러 열어 뒀고, 수식어가 붙은 3인칭 주어 `anyone taking medication should`는 병렬 주어 정상 안내 `Pregnant women and anyone taking medication should talk to their doctor.`를 막아서 넣지 않았다 — 검증자의 3인칭 실험은 정규식에 공백 오류가 있어 이 문장을 놓쳤다). 연결어 뒤 부사절·5단어 이상 창·약한 동사+`or`/`while`/`as`·목록에 없는 도입구(`you are advised to`·`it is best that you`)도 한계다.
- **N2-5 용량**: 영어·한국어 `g`를 대소문자 구분(`(?-i:g)`)으로 바꿔 `a 5G phone`·`5G 요금제`가 용량으로 읽히지 않는다. `400mgs`·`100 ug`·`softgels`·`gummies`·한국어 `반 알`을 용량으로 읽는다. `ml`·`teaspoon`·`tablespoon`·`tabs`(브라우저 탭)·`a gram`(`a gram of curiosity`)·`스푼`·`2개`는 일상어 오탐이 있어 **넣지 않았다**. 공허하던 시험 `test_everyday_counting_words_are_not_doses`는 문장마다 금지 낱말과 상담 구절을 같이 넣고(면제 취소가 잘못 읽으면 막힌다) 같은 틀의 진짜 용량 짝이 면제 취소로만 막히는 것을 보는 시험으로 다시 썼다. 2차 보강 WORKLOG 의 틀린 문장("`5G` 는 용량으로 읽지 않는다(시험이 고정)")은 정정했다.
- **N2-6 시험 구멍 15개**: 영어 창 길이 4단어(강한·약한 동사)·창 안 하이픈·아포스트로피 낱말·상담 부사 두 개 연속·동명사 `talking`/`asking`/`consulting`, 한국어 `에게서`/`한테서` 제외·용량 뒤 두 글자 보호(`2정거장`)와 그 임계, 영어 용량 간격(`400 -mg`)·앞뒤 `\b`(`6 glasses`·`B12 tablets`), 한국어 `5gb` — 각각 그것만 잡는 표본을 더했다(검증자 변이 R66·R68·R69·R74~R77·R117·R118·R129·R130·R142·R144·R145·R161 모두 사망).
- **N2-7 문서**: `docs/ARCHITECTURE.md` §7-1(필드 표·절 경계 표·면제 취소·알려진 과잉 차단·한계), `docs/SECURITY_GUARDRAILS.md` G-C4 한계, `docs/DEFECT_REGISTER.md` D-64 ⑧, 이 항목. **시험·코드**: `tests/test_guardrails.py`(새 시험 5개 + 표본·그리드·조각·속도 입력 확장), `pipeline/gates.py`는 설명 주석만.
- **줄인 것(동등)**: 변이 시험에서 `even so`(연결어 `so`가 이미 가른다)와 `I suggest` 도입구의 `(?:you\s+)?`(도입구 `you`가 받는다)가 동등이라 패턴에서 뺐다.

### 검증 증거
- **L1**: `python -X utf8 -m unittest discover -s tests` **2165개 통과**(round2 head 2160개 → 새 시험 5개, 서브케이스는 수백 개 늘었다). `python -X utf8 scripts/validate_repo.py --base origin/main` 오류 0·경고 1(LIQUID-1, main 과 같음), pyflakes 새 경고 0, 바꾼 `.py` vermin 최소 3.7.
- **정기·연습 실행 출력**: 검증자 `compare_sched.py` 32개 시나리오와 `runner_matrix.py` 900개 조합이 round2 head 와 **바이트 단위로 같다**(JSON 전체 비교, 같은 입력).
- **검증자 하니스**(수정 없이 실행, round2 head 와 나란히): `tradeoff.py` 위험 17/27·정상 안내 영어 8/42·한국어 1/15 **전과 같음(새 오탐 0)**, `normal2.py` 영어 75문장 38개 그대로·한국어 15→13(풀림 2), `overblock.py` 영어 15/118·한국어 0/32·`overblock2.py`·`probe.py`·`bypass.py`·`named10.py`·`manual_topic.py`·`real_posts.py` 26편 **출력 변화 없음**, `ko_seo.py` 17문장 중 막히는 것 14→2, `ko_fp.py` `5G 요금제…` 풀림, `dose2.py` 영어 용량 인식 42→46/61·한국어 24→25/32(`5G` 오탐 제거), `grid2.py` 열린 연결어 1392→930·도입구 324→108·3인칭 96→24·연쇄 90→66·동사 378→246, 한국어 그리드 28/56→0/56. 8만 문장 말뭉치에서 일상 문장(`benign`)은 영어 0→0·한국어 710→710으로 새로 막힌 것이 없다.
- **변이(내가 직접)**: 바꾼 패턴 전부의 단일 편집 변이 903개(선택지 삭제·선택적 묶음 제거/필수화·수량자 약화·문자 클래스 한 글자 삭제·앞뒤내다보기 제거·`\b` 제거·`(?-i:)` 해제) 중 **877 사망**, 생존 26개 중 24개는 동등이다(앞쪽 선택적 쉼표 `,?` 4와 그 안의 문자 2, 이미 있는 선택지와 겹치는 `(?:care\s+)?` 2, 용량 숫자 `(?:[.,]\d+)*`·`\d+`·`{0,3}`·`+` 반복 14 — 마지막 숫자(말)만으로 맞는다, `하지만`/`그렇지만` 2 — `지만` 경계가 가른다). 나머지 2개는 전문가 낱말 끝의 `\b` 를 지운 변이로 동등은 아니다: `nursery`·`doctorate` 처럼 전문가 낱말로 시작하는 다른 낱말이 연결어 바로 뒤에 올 때만 달라지는 억지스러운 경우라 시험으로 고정하지 않았다. 이름 붙인 33개(검증자 구멍 15개 + 새 규칙) 중 33 사망. 첫 실행에서는 138개가 살아남았다 — 복수형·단수형 명사·단위, 전각 쉼표·괄호, 앞내다보기 없이 항상 가르는 경계, 세 번째 부사, 숫자말 앞뒤 경계(`phone tablet`·`gramophone`), 한국어 용량 `\s?`가 시험 구멍이라 표본을 더했고 나머지는 위 변이다.

### 못 한 검증
- Actions 실행, 실제 Gemini 영어 출력으로 본 탈락률(`BODY_TOPIC` 빈도), 한국어 글의 사람 눈 검토. `mode`·시크릿은 건드리지 않았다.

### 다음 AI에게 남기는 주의사항
1. 이 브랜치는 round2(아직 main 에 없음) 위에 쌓였다. round2 가 병합되면 `git rebase --onto origin/main ai/claude/blogger-guardrails-round2 ai/claude/blogger-guardrails-round3`로 main 에 올린다. 이 변경도 `mode: draft` 를 켜기 **전에** 병합한다(D-64 ⑧). 병합 뒤 첫 영어 초안(L3)에서 `BODY_TOPIC` 빈도를 보고 `or`/`unless`·한국어 `~거나`를 풀지 정한다(`STRICT_TRADE_OFF_*`·`GRID_OPEN_*`·ARCHITECTURE §7-1 을 같이 바꾼다).
2. 새 절 경계 패턴이나 도입구 선택지를 더하면 그것만 가르는 표본(`MIXED_BLOCKED_*`)과 조각(`AlternativeCoverageTest`의 `EN_LEAD_INS`·`KO_*`)이 같이 있어야 시험이 통과한다. 후치사 `~서`를 더 제외하려면 `KO_POSTPOSITION_PHRASES`에 표본을 더한다(`준비해서`처럼 접속 어미로 끝나는 낱말은 앞 공백으로 구분한다).
3. 알려진 한계: 쉼표만으로 이은 상담 구절·연결어 뒤 부사절·수식어 붙은 3인칭 주어·5단어 이상 창·약한 동사+`or`/`while`/`as`·한국어 `~므로`/`~거나`/`또는`/`또한` 연결·일상어와 겹치는 용량 단위(`ml`·`teaspoon`)·줄바꿈으로 갈린 두 낱말 용어는 통과한다. 용량 낱말 자체를 막는 목록은 넓히지 않았다.
4. `HANDLER.md`·`docs/ACTIONS_GUIDE.md`·`docs/SESSION_START.md`·`docs/REQUEST_BRIEFING.md`·`인수인계/작업내용.md`·`.github/editorial/BLOGGER_API_SETUP.md` 의 '2차 보강(D-64 ⑦) 진행 중' 문장은 총괄 문서 PR 몫이다. 새 결함 번호는 D-68부터(D-67 은 다른 작업 몫).

---

## [2026-10-27] Claude – 워크플로 이름 `[구분]` 접두사와 레지스트리 `channel`·`ads` 필드·검증 규칙 (작업요청서 5 PR-A, T2, 동작 변화 없음)

**작업자**: Claude (구현 세션, 독립 검증은 별도 세션)
**대상**: 공통 (워크플로 이름·레지스트리 스키마·검증기·문서)
**등급**: T2(워크플로 파일의 `name`·`run-name`, 레지스트리 스키마의 새 필드, 검증기 규칙). 광고 표면(`index.html`·`_config.yml`)·`mode`·시크릿·워크플로의 그 밖의 줄은 바꾸지 않았다. 승인 근거: 운영자가 2026-10-27 채팅으로 계획 보고의 추천을 전부 승인("추천대로 진행해줘") — D2(워크플로 `[구분]` 접두사)·D6(신규 채널 광고 금지 원칙의 레지스트리 반영).
**목적**: 채널별로 워크플로를 구분해 보이게 한다(Actions 목록은 이름순이라 접두사가 같은 것끼리 붙는다). 한글 Blogger·티스토리·네이버를 더하기 전에 이름 규칙과 `channel`·`ads` 선언·검증을 먼저 깐다.
**브랜치**: `ai/claude/channel-names`(origin/main 71dfde6에서 시작). PR 생성·병합·Actions 실행은 하지 않았다(총괄이 처리).

### 한 일
- **워크플로 10개의 `name`·`run-name`**(`.github/workflows/*.yml`): 맨 앞에 `[구분] ` — `[Chance]`(`chanceblog.yml`·`chance-fix-images.yml`·`issue-edit.yml`), `[Blogger]`(`blogger.yml`, 이름은 `[Blogger] 글 자동 작성(초안함 업로드)`), `[공통]`(나머지 6개). `name`은 대괄호로 시작해 큰따옴표로 감쌌다(따옴표가 없으면 YAML 문법 오류). 바뀐 줄은 `name`·`run-name` 16줄뿐이고 `on`·`jobs`·`permissions`·`concurrency` 등은 `yaml.safe_load` 결과가 main 과 같다. job 이름·단계 이름·이슈 제목 접두 `[Watchdog]`·`[운영] 확인 필요 모음`·라벨은 그대로.
- **레지스트리**(`pipeline/blogs.json`·`pipeline/registry.py`): 블로그마다 필수 `channel: {key, label}`(chance → `Chance`, blogger_macat → `Blogger`)와 `ads`(`off`·`pending_gate`·`on`, chance `on`·blogger_macat `off`, `defaults.ads` `off`). 검증 — channel: 필수·모양, 라벨이 허용 집합(`Chance`·`Blogger`·`Blogger 영문`·`Blogger 한글`·`티스토리`·`네이버`), 블로그 사이 라벨·key 중복 없음, **그 블로그 워크플로 `name` 이 `"[라벨] …"` 로 시작**(표준 라이브러리로 `name:` 줄을 읽는다 — `blogger.yml` 의 plan 잡은 pip install 없이 이 검증을 돌린다). ads: 값, `jekyll-git` 밖의 `on` 금지, `ad_surface: true` 도 `jekyll-git` 에만, `defaults.ads` 는 `off` 로 고정. `python -m pipeline.registry`·`pipeline.plan` 출력은 main 과 바이트 단위로 같다(18개 명령).
- **검증기**(`scripts/validate_repo.py`): **WF-12** — 모든 워크플로 `name` 이 `[구분] ` 으로 시작(구분 = 채널 라벨·`공통`·`내부`)하고 `run-name` 이 있으면 같은 접두사. WF-11 은 접두사를 뗀 이름 부분에 한글을 요구한다(`[공통]` 같은 한글 접두사가 대신 통과시키지 않게). **REG-5** — `jekyll-git` 블로그의 `ads` 선언이 광고 표면(`protected_paths`)의 실제 광고 코드(`adsbygoogle`·`googlesyndication`·`ca-pub-숫자`)와 같은지.
- **이름을 인용하던 곳**: 코드 안내문 5곳(`pipeline/health.py` 2·`pipeline/edits/runner.py`·`pipeline/inbox.py` 꼬리글·`scripts/verify_pages_deploy.py`)과 주석 몇 곳, 시험 이름 기대값, 문서(`docs/ACTIONS_GUIDE.md` 이름 표·`[구분]` 설명, `docs/ARCHITECTURE.md` §2-1·§3(`channel`·`ads`·광고 선언·품질 게이트 기준 제안)·§7-A, `HANDLER.md`, `docs/OPS_INBOX.md`, `docs/ENGINEERING_GUIDE.md` W10, `docs/SECURITY_GUARDRAILS.md` G-C10·WF-12·REG-5, `docs/ISSUE_EDITS.md`·`docs/COPILOT_GUIDE.md`·`docs/CHARTER.md`·`docs/DEFECT_REGISTER.md`·`.github/*`). 이름을 파일 경로가 아니라 **이름으로 찾는 코드는 없다**(워치독·점검 모음·워크플로 간 호출은 모두 파일 이름. 이름은 안내문과 모음 항목 제목에만 쓰인다) — 계획 보고의 주장이 맞았다.
- **시험**: `tests/test_workflow_names.py`(승인된 이름 10개 고정·접두사·run-name·레지스트리 채널과의 일치·job/단계 접두사 없음·정렬 인접·안내 문서에 모든 이름 있음·**접두사 없는 옛 이름 인용 검색**), `tests/test_registry.py`(channel·ads 규칙, `name:` 줄 읽기 모양), `tests/test_validate_repo.py`(WF-12·REG-5·WF-11 접두사), 이름 인용 시험 수정. `tests/test_run.py` 의 `make_root()` 는 워크플로 두 개를 `name` 한 줄짜리 스텁으로 쓴다.

### 알아 둘 것
- 모음(`[운영] 확인 필요 모음`) 이슈 본문에서는 외부 텍스트의 대괄호가 전각(［ ］)으로 바뀌어 `［Chance］ 글 자동 작성·게시` 처럼 보인다(링크 문법 무력화, 기존 동작). 시험으로 고정했다.
- 한 워크플로 파일을 채널이 다른 블로그 둘이 나눠 쓸 수 없다(라벨 중복 금지·이름 접두사 일치) — 한글 Blogger 등록 작업(PR-D)이 `blogger.yml` 을 재사용 워크플로로 바꾸고 채널별 래퍼를 둬야 한다. 플레이북(`docs/ARCHITECTURE.md` §7-A)에 적었다.
- 브랜치 보호의 '필수 검사' 지정 여부는 설정 화면을 보는 사용자만 확인할 수 있다. 필수 검사의 이름은 보통 job 이름이고 이 변경은 job 이름을 바꾸지 않았다(외부 지식, 미확인).
- 총괄 소유 문서(`docs/REQUEST_BRIEFING.md` 의 워크플로 이름 표 등)는 이 PR 에서 고치지 않았다 — 표 검사 시험 2개가 그 표를 보므로 총괄이 별도 패치(`A_request_briefing_table.patch`)를 얹어야 초록이 된다.

### 검증 증거
- **L1**: `python -m unittest discover -s tests` — 기준 main 71dfde6 **2145개 통과**(189.6초) → 브랜치 **2202개**(새 시험 57개: `test_workflow_names` +11·`test_registry` +19·`test_validate_repo` +26·`test_ops_inbox` +1). 총괄 소유 `docs/REQUEST_BRIEFING.md`를 이 PR에서 고치지 않아 그 표를 읽는 시험 2개(`test_docs_tables_list_every_workflow_with_its_current_name`·`test_operator_docs_do_not_use_the_old_english_names`)는 패치 없이는 실패한다(2200 통과·2 실패). 패치 `A_request_briefing_table.patch`(13줄, `git apply --check` 통과)를 얹으면 **2202개 모두 통과** — 처음 만든 커밋에서 368초, 그 뒤 봇 글 커밋(931d2dc) 위로 옮긴 커밋에서 다시 돌려 287초. 옮긴 뒤 바뀐 것은 `docs/ARCHITECTURE.md` 문구 3곳과 `docs/ACTIONS_GUIDE.md` 빈 줄 하나뿐이고, 문서를 읽는 시험 64개를 패치 적용본에서 다시 돌려 통과했다. 네트워크 없이 돈다.
- **L0**: `python scripts/validate_repo.py --base origin/main` 오류 0·경고 1(LIQUID-1, main과 같음)·AD-1 통과, `actionlint` 1.7.12 10개 파일 지적 0, `pyflakes` 새 경고 0, `vermin --target=3.10-` 최소 3.10, `git diff --check` 0.
- **동작 불변**: CLI 21개(`pipeline.registry`·`pipeline.plan` 변형 18개·`pipeline.run --blog … --dry-run` 2개·`validate_repo --json`)의 표준 출력·표준 오류·종료 코드 63개 파일이 main과 바이트 단위로 같다. 워크플로 YAML은 `git diff` 상 `name`·`run-name` 16줄 외 0줄, `yaml.safe_load`로 읽은 `on`·`jobs`·`permissions`·`concurrency`·`env`가 10개 파일 모두 main과 같다.
- **변이(직접 돌림)**: 레지스트리 27·검증기 19·데이터 15·문서/시험 코드 8 = 69개, 모두 시험이 잡는다(첫 판에서 접두사 뒤 공백이 둘인 이름을 거르는 시험이 없어 하나가 살아남았고 시험을 보강했다).

### 못 한 검증
- Actions 에서의 실제 실행(이름·실행 제목이 목록에 어떻게 보이는지, 목록의 정렬 순서), 브랜치 보호 설정 화면. 푸시·병합 뒤 관측이 필요하다.

---

## [2026-10-27] Claude – 계획 승인 반영과 9시 슬롯 관측 (문서 전용, 코드·워크플로·레지스트리·광고 표면 변경 없음)

**작업자**: Claude
**대상**: 공통·Chance (문서)
**등급**: T1(문서)
**목적**: 사용자 승인("추천대로 진행해줘", 2026-10-27 채팅)을 작업요청서 5 계획 보고와 현황 문서에 반영하고, 2026-10-27 9시 슬롯 정기 실행(#79)의 관측 결과를 기록한다.

### 한 일
- 승인 반영: 계획 보고 §0 승인 기록·제목 문구, `인수인계/작업내용.md`(헤더·§1·§2 작업요청서 5 행·§3 21번·§5), `인수인계/작업요청/README.md` 5번 행, `docs/REQUEST_BRIEFING.md` §8, `docs/DEFECT_REGISTER.md` 해외 소스 관측 행.
- 9시 슬롯 관측(읽기 전용: GitHub REST 실행 목록·커밋·공개 실행 화면의 주석, 공개 사이트, 원문 페이지; 단계 로그는 로그인이 없어 못 읽음):
  - 실행 #79(정기, 00:27 UTC 시작·3분 37초, 성공, main 71dfde6) → 봇 커밋 931d2dc(00:30:56 UTC) → `사이트 자동 배포`(workflow_dispatch) 00:32:03 UTC 성공. 공개 주소 두 개 200, 사이트맵 21건 중 새 글 2건, `posts.json` 반영.
  - 공개 주석: 경고 `모든 뉴스 소스 수집에 실패했습니다…`, 알림 `'사회·정책' 분야에 후보가 없어 '경제·일' 분야로 대체했습니다.`, Node.js 20 폐기 경고, `ubuntu-latest` 가 2026-10-19부터 Ubuntu 26으로 옮겨 간다는 안내(워크플로는 파이썬 버전을 고정해서 쓰지만 유지보수 후보).
  - 같은 코드로 사회·정책 분야를 로컬에서 읽어 보면(다른 시각): 집행위원회 소식 30건 중 0건 사용(EXCLUDED 16·AGE 14), 통계청 사회는 `ParseError: mismatched tag: line 169, column 2`. 통계청 피드 주소가 00:35 UTC에 점검 안내 HTML(`We're sorry! The website is currently unavailable`, 200, `text/html`, 92,815바이트)을 돌려줬고 약 10분 뒤 정상 Atom(198,646바이트, `application/atom+xml`)이었다 → 같은 시각 실행의 수집 실패와 같은 원인으로 보이나 실행 로그 원문은 못 읽었다.
  - 글 1쌍(`2026-10-27-KR/EN-093056`, 경제·일, DG Energy 항목 = CINEA 보도): front matter 첫 줄 `layout: post`, 글 끝 CC BY 4.0 인용 줄·AI 고지문(한·영) 확인. 원문 대조: 67건·€2.88 billion 일치. 모델이 받은 요약은 194자 한 문장뿐(요약 100자 이상이라 페이지의 메타 설명도 읽지 않음)이고 글은 약 5,000자 — 한국어 글에만 원화 환산 "한화 약 4조 2천억 원", 두 글에 평가 기준·절차 서술(원문에 없음), 한국어에 "민관 공동"·수소·가스망, 원문의 "예산의 약 5배·20여 개국·2027년 1월 결과"는 빠짐.

### 남긴 것
- 단계 로그의 `소스 …` 줄과 분야 표(로그인 필요), 통계청 점검 시간대 반복 여부(18시 슬롯부터 며칠), GOV.UK·통계청 글의 첫 발행 관측.
- 원문 근거가 얇은 문제의 보강(프롬프트에 환산·절차 서술 금지 한 줄 — T2; 원문 발췌를 읽을지는 사용자 결정, 기본값 변경 없음)은 Task 5 구현 PR 병합 뒤 별도 PR. 결함 번호는 그때 레지스터에 올린다.
- 이 PR 은 계획 보고서 PR 과 하나로 병합한다(같은 브랜치).

---

## [2026-10-27] Claude – 작업요청서 5 계획 보고 (문서 전용, 코드·워크플로·레지스트리·광고 표면 변경 없음)

**작업자**: Claude
**대상**: 공통 (문서)
**등급**: T1(문서) — 구현은 승인 뒤 PR-A~E
**목적**: 사용자가 2026-10-27 채팅으로 지목한 작업요청서 5의 첫 단계(§6-1 계획 보고)를 낸다. 요청서의 사실 4건을 직접 확인하고, 워크플로 재분류·이름 변경안, 얇은 채널 워크플로 구조, 초안 이슈·현황판, 레지스트리 변경안, AdSense 선택지 비교, 보안, 구현 순서를 정리한다.

### 한 일
- 새 `docs/analysis/2026-10-27_channel-management-plan.md`: 결정 D1~D8과 추천, 사실 확인(AdSense 두 건은 구글 공식 문서 원문 확인, 티스토리 API 종료·에디터·이미지·robots.txt·약관은 별도 조사 에이전트 2개가 읽기 전용으로 확인), 현황, 워크플로 표, 구조·인박스·레지스트리·AdSense 비교·보안·구현 순서·사용자 몫·미확인.
- `인수인계/작업내용.md`(§1·§2·§3 21번·§4 9~12번·§5), `인수인계/작업요청/README.md` 표, `docs/REQUEST_BRIEFING.md` §8.

### 남긴 것
- 사용자 답(D1~D8). 승인된 것부터 PR-A(이름 접두사·`channel` 필드·검증 규칙)로 구현.
- 이름 변경 때 브랜치 보호의 '필수 검사' 지정 여부는 사용자만 확인 가능(미확인).

---

## [2026-10-27] Claude – Blogger 주제 가드레일 2차 보강(D-64 ⑦ 권고 N-1·N-3·N-4·N-5·N-7): 쉼표 없는 접속어·용량 단위·패턴 따로 컴파일·시험 구멍·수동 주제 가드 순서 (T2, 독립 검증 델타 + dry-run 증거)

**작업자**: Claude (구현 세션, 독립 검증은 별도 세션)  
**대상**: Blogger  
**등급**: T2 — 레지스트리가 받은 설정을 돌리는 `pipeline/gates.py`(절 경계 계산)와 `pipeline/run.py`(수동 주제 가드 순서) 코어를 바꿨다. 프로필은 금지를 늘리는 쪽으로만 바꿨다(T1). 승인 근거: 독립 검증 델타("병합 가능", `mode: draft` 전 권고 5건) + 아래의 dry-run·변이 증거. 실제 T2 승인은 총괄이 PR 에서 기록한다. 운영자 승인(2026-10-26 채팅 "3. …가드레일을 설정하고 진행")의 범위 안(목록을 막는 쪽으로만 강화)이다. **`mode`·시크릿·워크플로·`generator.py`·광고 표면·`인수인계/작업내용.md`·`HANDLER.md`·`docs/SESSION_START.md`·`REQUEST_BRIEFING.md`·`ACTIONS_GUIDE.md`는 바꾸지 않았다**(`blogger_macat`은 off 그대로).  
**목적**: PR #43(main 0da8221)의 독립 검증 델타가 `mode: draft` 를 켜기 전에 처리하라고 권고한 항목(`docs/DEFECT_REGISTER.md` D-64 ⑦)을 구현한다. 범위는 권고 항목으로 한정했고 새 항목을 늘리지 않았다.  
**브랜치**: `ai/claude/blogger-guardrails-round2`(origin/main 71dfde6에서 시작). PR 생성·병합·Actions 실행은 하지 않았다(총괄이 처리).

### 변경 사항
- **N-1 쉼표 없는 접속어**(`pipeline/profiles/*.json`의 `body_clause_split_patterns`): 접속어 **바로 뒤에 상담 구절**(상담 동사 `talk to`·`speak with`·`check with`·`consult`·`ask` + 전문가 낱말)이 올 때만 가르는 패턴을 더했다. 쉼표는 있어도 없어도 된다(`…lower your blood pressure so ask your doctor.` 가 막힌다). 접속어 `so`·`yet`·`while`·`then`·`or`·`because`·`since`·`as`·`unless`·`otherwise`·`therefore`·`thus`·`hence`·`plus`·`and`·`which is why`·`which means`·`meaning`·`except that`, 도입구 `you should`·`you can`·`make sure to`·`remember to`·`it is wise to`·`consider` 등. `see`·`call`·`visit`·`contact`·`seek`은 인과·순서 접속어와 쓰일 때만 가른다(`or see a specialist` 같은 서술을 가르지 않으려고). 한국어는 `~고,`·`~서`(돼서·그래서·따라서·고 나서; 장소의 `에서`는 제외)·`그러므로/그러니/그러니까`·`(먼저 의사와 …)`. 검증자의 연결어 그리드 영어 69행 중 지금까지 통과하던 32행 가운데 **22행을 닫았다**(남은 10행은 쉼표만으로 이은 것과 같은 계열이라 일부러 열어 뒀다: `, `·`, please`·`, just`·`, also`·`, of course,`·`, if you want,`·`, remember to`·`, be sure to`·`, make sure to`, 그리고 하니스가 `<br>`을 글자 그대로 넘겨서 생기는 `<br>` 행 — 실제 실행은 줄바꿈으로 읽어 막는다). 한국어 그리드는 10행 중 8행을 닫았다(남은 것은 `, 의사와…`·`~는 점, 의사와…`). 대가: 같은 모양의 정상 안내가 더 막힌다 — 검증자의 정상 안내 표본(영어 42·한국어 15)은 새로 막히는 것이 0개, 내가 쓴 정상 안내 68문장 중 14개(`…, which is why you should talk to your doctor`·`Do not start any supplement unless you check with your doctor`·`can then ask`·`임신 중이라서 의사와 상담이 필요해요` 등)는 새로 막혀 시험 `STRICT_TRADE_OFF_*`가 고정한다.
- **N-3 용량 면제 취소**(`body_safe_veto_patterns`): 숫자+`mg`·`mcg`·`μg`·`IU`만 인식하던 것을 `milligrams`·`micrograms`·`grams`·`g`·`units`·`capsules`·`tablets`·`0.4 g`·`10,000 units`·`400-mg`·영어 숫자말(`four hundred milligrams`·`half a tablet`)로, 한국어는 `g`·`그램`·`정`·`캡슐`·`알`·`한 알`·`두 캡슐`로 넓혔다. `a handful of`·`2정거장`·`프로그램` 같은 일상어는 용량으로 읽지 않는다(시험이 고정). **정정(3차 보강, D-64 ⑧ N2-5)**: 처음 쓴 이 줄에는 `5G`도 읽지 않는다고 적었지만 틀렸다 — `g`가 대소문자를 가리지 않아 `a 5G phone`·`5G 요금제`가 용량으로 읽혔다(상담 구절이 든 문장에서 막힘). 시험 문장에 금지 낱말·상담 구절이 없어 공허했고, 3차 보강에서 `g`를 대소문자 구분으로 고치고 시험을 다시 썼다. **용량 낱말 자체를 막는 목록(`banned_*`의 `mg`·`IU` 패턴)은 넓히지 않았다** — 상담 구절도 막는 낱말도 없는 `Take 400 milligrams of magnesium before bed.`는 그대로 통과한다(범위 밖, 총괄 결정).
- **N-4 절 경계 패턴을 따로 컴파일**(`pipeline/gates.py` `_clause_splitter`·`_split_clauses`): `(?:p1)|(?:p2)` 하나의 정규식으로 합치던 것을 패턴마다 따로 컴파일·탐색하고 겹치거나 맞닿은 경계를 합친다. 레지스트리는 패턴을 하나씩 컴파일해 검사하므로, 합치면 `(?i)`로 시작하는 패턴이나 같은 이름의 묶음이 검증을 통과하고도 실행 중 `re.error` 가 됐다(검증자 재현 `(?i)\s+whereas\s+`). 지금은 그 설정이 오류 없이 검증되고 그대로 돈다 — 시험이 '레지스트리가 받은 패턴은 본문 검사가 예외 없이 돌린다'를 고정한다.
- **N-5 시험 구멍 5개**: 대문자 접속어(`, BUT`·`SO ASK YOUR DOCTOR`), 문장 끝 `!`·`?`·`。`·`！`·`？`, 수동 topic 의 30자 뒤에 있는 금지어, 수동 topic 가드가 본문 목록을 써도 통과하던 것(`remedy`·`heal`·`treat`·`pharmacy` 는 주제 목록에만 있다), 한국어 `400 mg`(띄어 쓴 용량) — 각각 그것만 잡는 표본을 더했다. 새 패턴마다 그 패턴만 가르는 문장이 있어야 하는 시험(`ClauseScopedExemptionTest`)은 그대로 통과한다(영어 `, and`·` and` 규칙은 새 규칙과 겹쳐 '앞에 상담·뒤에 위험한 권유'·`and see …` 표본을 더했다).
- **N-7 수동 주제 가드 순서**(`pipeline/run.py`): `BLOGGER_PUBLISH=draft`인데 시크릿이 하나도 없고 주제가 막히면 `UPLOAD_SKIPPED`('저장소 파일에만 저장합니다') 안내가 먼저 나온 뒤 `TOPIC_BLOCKED` 종료 2 로 끝났다. 가드를 그 안내 앞으로 옮겼다 — 일시정지·mode off·잘못된 `BLOGGER_PUBLISH`·시크릿 누락 오류가 먼저 처리되는 순서는 그대로고, 주제가 없거나 통과하는 실행의 출력은 main 과 바이트 단위로 같다(검증자의 `compare_sched.py` 32개 + 내가 더한 16개 시나리오, 시험은 `ManualTopicGuardTest`). `docs/ARCHITECTURE.md` §4-1 처리 순서를 고쳤다.
- **N-2 는 고치지 않았다**: `, then` 조건문("If you are pregnant, then check with your doctor first.")·`stop and consult`가 막히는 과잉 차단은 첫 실제 영어 초안의 `BODY_TOPIC` 빈도를 보고 정한다(`docs/ARCHITECTURE.md` §7-1 한계에 한 줄).
- **시험·문서**: `tests/test_guardrails.py`(105→114개)·`tests/test_run.py`(60→66개). 연결어 그리드 시험(`ConnectorGridTest`: 닫은 것은 모두 막히고 열어 둔 것은 지금 그대로 통과), 선택지 하나까지 지키는 표본(`AlternativeCoverageTest`)을 새 패턴·용량 단위까지 넓혔다. 문서: `docs/ARCHITECTURE.md` §4-1·§7-1(필드 표·절 경계 표·면제 취소·한계·트레이드오프), `docs/SECURITY_GUARDRAILS.md` G-C4 한계, `docs/DEFECT_REGISTER.md` D-64.

### 검증 증거
- **L1**: `python -m unittest discover -s tests` **2160개 통과**(기준 main 71dfde6의 2145개 → 새 시험 15개). `python scripts/validate_repo.py --base origin/main` 오류 0·경고 1(LIQUID-1, main과 같음), pyflakes 새 경고 0, 바꾼 `.py` vermin 최소 3.7.
- **정기·연습 실행 출력**: 검증자의 `compare_sched.py` 32개 시나리오와 내가 더한 16개(초안함 업로드·시크릿 없음·연습 실행·하루 상한·즉시 게시 시크릿 누락 등)에서 main 과 **바이트 단위로 같다**(주제를 넣지 않은 실행).
- **검증자 하니스**(수정 없이 실행, main 과 나란히): `tradeoff.py` 위험 문장 영어 14→17개 막힘(`which is why`·`and you can ask`·`and then consult`), 용량+상담 구절 4→9개 막힘, 정상 안내 영어 8/42·한국어 1/15 막힘은 **전과 같은 문장**(새 오탐 0); `overblock2.py` 영어 5/31·한국어 16/27 표시는 전과 같음; `probe.py`·`bypass.py`·`overblock.py`·`manual_topic.py`는 출력이 전과 같음(과잉 차단 영어 15/118·한국어 0/32 그대로).
- **변이(내가 직접)**: ① 이름 붙은 변이 37개(절 경계 문장부호 7·경계 찾기·합치기·대소문자 10·면제 취소·문장 나누기 5·수동 주제 가드와 `UPLOAD_SKIPPED` 안내 9·문서 2·바꾼 패턴 4곳을 옛 문자열로 되돌리기 4) ② 새로 더했거나 바꾼 패턴 통째 삭제 10개 ③ 선택지 하나씩 삭제 306개(새로 더했거나 바꾼 패턴의 `|` 선택지를 하나씩 지움) = **353개 중 353 사망, 생존 0**. 첫 실행(이름 붙은 37 + 삭제 10 + 선택지 314)에서는 15개가 살아남았다 — 경계 합치기 3개(맞닿은 경계·겹친 경계의 끝·정렬)와 용량 숫자말 단위 4개(`micrograms`·`grams`·`units`·`capsules`)는 시험 구멍이라 표본·시험을 더해 막았고, 나머지 8개는 같은 낱말이 안쪽에 또 있거나(`healthcare professional`은 맨 앞의 `professionals?`와 창이 이미 잡는다) 쓸모가 없는(숫자말 사이의 `and`, `그러니까`는 `~니까` 경계가 가른다) 선택지라 패턴에서 뺐다. 단순화 전후의 동작은 생성한 문장 약 6만 개에서 달랐던 것이 0개다.

### 못 한 검증
- Actions 실행, 실제 Gemini 영어 출력으로 본 탈락률(`BODY_TOPIC`·`TOPIC_BLOCKED` 빈도), 영문 글의 사람 눈 검토. `mode`·시크릿은 건드리지 않았다.

### 다음 AI에게 남기는 주의사항
1. 이 변경도 `mode: draft` 를 켜기 **전에** 병합한다(D-64 ⑦). 병합 뒤 첫 영어 초안(L3)에서 `BODY_TOPIC` 빈도를 본다. 정상 안내가 새로 막히면 사유의 `'낱말'`을 보고 접속어 목록을 조정하되, `STRICT_TRADE_OFF_*`·`ConnectorGridTest` 표본과 ARCHITECTURE §7-1 한계 문단을 같이 바꾼다.
2. 새 절 경계 패턴을 더하면 그 패턴만 가르는 문장(`MIXED_BLOCKED_*`)과 선택지마다의 조각(`AlternativeCoverageTest`)이 같이 있어야 시험이 통과한다. 쉼표만으로 이은 연결어를 닫으면 `GRID_OPEN_*`·문서의 한계 목록을 같이 고친다.
3. 알려진 한계: 쉼표만으로 이은 상담 구절·꼬리 구절·줄바꿈으로 갈린 두 낱말 용어·한 문장 안의 다른 언어 낱말·상담 구절이 앞에 오고 위험한 권유가 쉼표 없는 `and try …`로 뒤따르는 문장은 여전히 통과한다. 용량 낱말 자체를 막는 목록은 넓히지 않았다.
4. 새 결함 번호는 D-67부터. `docs/ACTIONS_GUIDE.md` 6-1 표의 `TOPIC_BLOCKED`·`HANDLER.md`·`인수인계/작업내용.md` 갱신은 총괄 문서 PR 몫이다.

---

## [2026-10-26] Claude – 18시 슬롯 관측과 #42·#43 병합 기록 (문서 전용, 코드·광고 표면 변경 없음)

**작업자**: Claude
**대상**: Chance_Blog·Blogger·공통 (문서)
**등급**: T1(문서)
**목적**: 18시 슬롯 정기 실행(#74) 관측 결과와 PR #42(layout 보장)·#43(가드레일 보강)의 병합을 현황 문서에 반영하고, 새 결과 코드 `TOPIC_BLOCKED`를 Actions 가이드에 적는다.

### 한 일
- `인수인계/작업내용.md`: 헤더·§1·§2(18시 관측 결과, 2차 보강 행)·§3(3번 상태, 22번 `mode: draft` 켜기 승인 예정)·§5·§6, `HANDLER.md`·`docs/ACTIONS_GUIDE.md`(6-1 표 `TOPIC_BLOCKED`, 수동 `topic` 설명, "영문 프로필이 아직 없다" 문장 정리)·`.github/editorial/BLOGGER_API_SETUP.md`·`docs/REQUEST_BRIEFING.md`·`docs/SESSION_START.md`(PR 번호 사전 #41~#43).
- 18시 슬롯(#74, 18:22 KST): 문화·미디어(Pew)에서 멈춰 새 소스는 읽히지 않음(예측대로), 글 1쌍 발행·공개 확인, Gemini 첫 호출 283초 붙잡힘(D-66).

### 남긴 것
- 새 소스(집행위원회·통계청·GOV.UK)의 첫 실제 관측: 이후 슬롯 로그의 `소스 …` 줄·글 끝 인용·고지문. 같은 실행에서 글 front matter 첫 줄의 `layout: post`.
- 2차 보강(D-64 ⑦) 병합 뒤 `mode: draft` 켜기 승인 요청(§3 22번).

---

## [2026-10-26] Claude – 생성 글 front matter 에 layout: post 보장과 실제 글 사본 시험 보강 (D-65, 시험 복구)

**작업자**: Claude
**대상**: Chance_Blog
**등급**: T2 (생성기 `validate_post_data` 3줄 + 시험). 광고 표면·신뢰 목록·글 파일 변경 없음
**목적**: 18시 슬롯 봇 글(KR/EN-182804)에 `layout: post` 가 없어 main 에서 `test_verify_pages_select` 가 실패했다. 사이트는 기본 레이아웃으로 정상이었지만 봇 커밋은 자동 검사를 일으키지 않아 다음 PR 의 검사 전까지 숨어 있었다.

### 한 일
- `generator.py` `validate_post_data`: 모델이 준 front matter 에 `layout` 줄이 없으면 `layout: post` 를 맨 앞에 넣는다(있으면 그대로). 여는 울타리 뒤 공백·탭·CRLF와 글 앞의 빈 줄·공백도 정리해 빈 줄·탭만 있는 줄이 남지 않게 했다(독립 검증이 `---`+탭 입력에서 YAML 오류가 나는 것을 찾아 `strip()`으로 고침). 새 시험 `LayoutGuaranteeTest` 10개(없을 때·있을 때·마지막 줄에 있을 때·값/다른 키 안의 낱말·본문 속 `layout:` 줄·공백/탭 울타리·앞 빈 줄·빈 front matter·CRLF·front matter 없음).
- `tests/test_verify_pages_select.py`: 실제 글 사본에 `published: false` 를 넣을 때 `layout: post` 줄에 기대지 않고 맨 위 `---` 바로 아래에 넣는다.
- 변이 13개(보장 끄기·조건 뒤집기·앵커·콜론·값·검색 범위·첫 줄만·`strip` 변형·빈 front 줄바꿈·위치·앞쪽 `lstrip` 변형) 모두 시험이 잡는다. 독립 검증(별도 세션)이 입력 53개+무작위 600개를 main·PR 코드에 같은 입력으로 돌려 비교해(YAML을 PyYAML·libyaml로 확인) 본문 소실 0·기존 layout 글 출력 동일 246/246을 확인했다. 이미 올라간 두 글(공개 콘텐츠)은 그대로 둔다.
- 기록만: D-66(Gemini 호출 시간 제한 없음 — 18시 슬롯에서 283초 붙잡힘, 폴백으로 글은 나옴, 열림).

### 다음 AI에게 남기는 주의사항
- 봇 커밋(`🤖 자동 포스팅`)은 `GITHUB_TOKEN` 푸시라 시험 워크플로를 일으키지 않는다. 봇 글이 시험을 깨뜨리면 다음 PR 의 자동 검사에서야 드러난다 — 시험은 글 파일의 front matter 모양(`layout`·`published` 줄 위치)에 기대지 않아야 한다.

---

## [2026-10-26] Claude – Blogger 주제 가드레일 보강 6건(D-64 ⑥ a~f): 상담 구절 면제를 절 단위로·한국어 목록·수동 topic 검사·변형 낱말·시험 구멍·다이어트/간 건강 (T2, 운영자 승인 2026-10-26)

**작업자**: Claude (구현 세션, 독립 검증은 별도 세션)  
**대상**: Blogger  
**등급**: T2(`pipeline/` 코어·레지스트리 스키마의 새 선택 필드·`docs/SECURITY_GUARDRAILS.md` 변경 — 프로필 금지 목록 강화만은 T1). 총괄 승인: 독립 검증 델타 '병합 가능' 판정과 정기·연습 실행 시나리오 32개가 main 과 바이트 단위로 같다는 dry-run 증거를 근거로 한다. 승인 근거는 PR #40과 같다(운영자 채팅 2026-10-26 "3. 수동 작성은 없을 예정이니 주제에 대한 가드레일을 설정하고 진행"). **`mode`·시크릿·워크플로·`generator.py`·광고 표면·`인수인계/작업내용.md`는 바꾸지 않았다**(`blogger_macat`은 off 그대로).  
**목적**: PR #40(main 362ba8f)에 대한 독립 검증이 '병합 가능' 판정과 함께 `mode: draft`를 켜기 전에 끝내라고 낸 보강 6건(`docs/DEFECT_REGISTER.md` D-64 ⑥)을 구현한다.  
**브랜치**: `ai/claude/blogger-guardrails-hardening`(origin/main e89b7a3에서 시작). PR 생성·병합·Actions 실행은 하지 않았다(총괄이 처리).

### 변경 사항
- **(a) 상담 구절이 같은 문장 안의 위험한 권유를 면제하던 것**(`pipeline/gates.py`): 면제(`body_safe_patterns`)를 문장이 아니라 **절** 단위로 한다. 문장을 `; : — --`·띄어 쓴 하이픈(코드, 모든 언어 공통)과 프로필의 `body_clause_split_patterns`(영어 `, but`·`, so`·`, though`·`, yet`·`, then`·`, and`+새 절·`(ask…)` 등, 한국어 `~지만`·`~하되`·`~는데`·`~으나`·`~면서` 등)에서 절로 쪼개고, 상담 구절이 없는 절은 따로 검사한다. 새 선택 필드 `body_safe_veto_patterns`(용량 `400 mg`·`5000 IU`·`400mg`·`밀리그램`)에 맞는 절은 상담 구절이 있어도 면제하지 않는다. 검증자가 낸 세 문장("Magnesium supplements may help you sleep, but talk to your doctor first." 등)이 모두 `BODY_TOPIC`으로 막히고, "If you are pregnant, talk to your doctor before changing your routine."·기존 안전 표본 전부는 그대로 통과한다(운영자 결정 3번). 두 필드는 `pipeline/registry.py`가 검증한다(정규식 컴파일·빈 문자열 일치 금지).
- **(b) 한국어 목록 28 → 56개**(주제·본문 목록은 같은 어휘 — 시험이 같음을 고정): 불면·혈압(고혈압·저혈압 포함)·혈당·콜레스테롤·치매·갱년기·폐경·편두통·면역(면역력 포함)과 영어 목록에만 있던 임상·접종·스테로이드·침술·카이로프랙틱·약 이름(항생제·진통제·수면제 …)·건강기능식품·멜라토닌·종합 비타민·증상·환자·감염·질환명·정신 질환명·종양·항암·심장 질환명·디톡스·단식·키토·체지방·슬리밍·간 건강·요법·임산부·산모·출산·용량 표기. 일상어와 겹쳐 **일부러 뺀 것**: 백신(컴퓨터 백신)·해독(암호 해독)·코로나·수유(수유동)·감량(쓰레기 감량)·용량(배터리 용량)·뜸·간질(간질간질)·약(약 10분)·살 빼·불안·우울감·두통·변비·탈모·관절. `간 건강`은 `시간 건강`과, `단식`은 `간단식`과 겹치지 않게 앞에 한글이 없을 때만 막는다.
- **(c) 수동 `topic`**(`pipeline/run.py`): `--topic`·`BLOGGER_TOPIC`이 `gates.topic_allowed`를 거친다. 걸리면 Gemini·Blogger를 부르기 전에 **종료 2**(`[SKIP] code=TOPIC_BLOCKED word=…`)로 멈추고 이력·초안을 남기지 않는다. 걸린 낱말은 로그·실행 요약에 있고 `::error::` 주석은 입력 문자열이 없는 고정 문장이다. 이유: 운영자가 직접 넣은 값이라 조용한 초록이 아니라 `INVALID_PUBLISH`와 같은 설정 오류(빨강)로 알린다. 이력 읽기·하루 상한보다 앞이다. `docs/ARCHITECTURE.md` §4-1 표·처리 순서를 맞췄고 코드↔문서 시험이 있다. `run.py`의 다른 동작(`build_prompt`의 한국어 머리글 등)은 바꾸지 않았다(D-64 ③).
- **(d) 영어 두 낱말 용어·동의어**: `blood-pressure`·`bloodpressure`·`blood-sugar` 등 `\s+`를 `[\s-]*`/`[\s-]+`로(12개 패턴, 주제·본문 목록 모두), `sleeping tablets`·`sleep aid(s)`·`shed pounds`·`drop a few kilos`·`body/belly/visceral fat`·`menopause`·본문 목록의 `immunity`를 추가, 용량 단위에 `μg`를 더했다. 같은 종류의 빈틈을 영어 전체 패턴에서 훑어 `chronic-pain`·`heart-disease`·`panic-attack`·`mental-health`·`kidney-stone`·`fatty-liver`·`crash-diet`·`calorie-deficit`·`pain-reliever`·`vitamin-gummies`·`expecting/nursing-mothers`·`sleep-apnea`·`intermittent-fasting`을 같이 고쳤다.
- **(e) 시험 구멍**: 독립 검증이 변이로 찾은 셋을 잡는 시험을 더했다 — 문장 분리의 줄바꿈(`<li>Take magnesium supplements every night</li><li>Talk to your doctor …</li>`), 영어 글 언어 검사의 라틴 경계 `U+024F`(폴란드어·루마니아어 글자), `BODY_TOPIC` 사유의 낱말 한 줄·40자 접기.
- **(f) 다이어트·간 건강**: 영어 `dieting`·`diet plan/program/pills/menu/…`(단독 `diet`·`balanced diet`는 일상어라 막지 않는다)·`liver health/function/support/…`와 한국어 `다이어트`·`간 건강/기능/수치/질환/해독`을 주제·제목·라벨·본문에서 막는다. 영어·한국어 프롬프트의 '쓰지 말 것'에도 넣었다. `AI_COLLAB.md`의 문장을 사실대로 고쳤다(막는 것: 다이어트·간 건강 / 프롬프트로만 막는 것: `비타민`(단독)·`통증`·`알레르기`·`아이` — 열린 운영자 결정 D-64 ④, 기본값 넣지 않음).
- **시험**: `tests/test_guardrails.py`(74→105개)·`tests/test_run.py`(49→60개) 보강 — 패턴 안의 선택지 하나까지 지키는 표본 `AlternativeCoverageTest`(영어 낱말 166개·절 경계 조각 영어 77개·한국어 36개·용량 단위)와 알려진 과잉 차단 `STRICT_TRADE_OFF_*`도 있다. `tests/test_profile_en.py`는 수동 topic 시험을 새 동작으로 고치고 프롬프트 문구를 맞췄다. 문서: `docs/ARCHITECTURE.md` §4-1·§7-1(필드 표·'절 단위 면제' 절·대응표·한국어에서 뺀 낱말 이유), `docs/SECURITY_GUARDRAILS.md` G-C4, `docs/ENGINEERING_GUIDE.md`, `docs/DEFECT_REGISTER.md` D-64, `AI_COLLAB.md`(`HANDLER.md`·`SESSION_START.md`·`REQUEST_BRIEFING.md`·`ACTIONS_GUIDE.md`·`인수인계/작업내용.md`는 총괄 문서 PR 몫이라 건드리지 않았다).

### 검증 증거
- **L1**: `python -m unittest discover -s tests` **2135개 중 2134개 통과**(기준 main e89b7a3의 2093개 → 새 시험 42개). 네트워크 없이 돈다. 실패 1건은 `tests/test_verify_pages_select.py`의 `test_unpublished_newest_pair_scenario_on_a_copy_of_the_real_posts`로, **깨끗한 main e89b7a3에서도 똑같이 실패한다** — 봇이 낸 최신 글 `_posts/Culture & Media/2026-10-26-EN-182804.md`의 머리말에 `layout: post`가 없어서다. 이 변경과 무관해 고치지 않았다(총괄 확인 필요). `python scripts/validate_repo.py --base origin/main` 오류 0·경고 1(LIQUID-1, main과 같음), pyflakes 새 경고 0(바꾼 `.py` 6개 기준 vermin 최소 3.7).
- **독립 검증 하니스**(검증자의 `probe.py`·`bypass.py`·`overblock.py`·`manual_topic.py`, 수정 없이 실행): `overblock.py` 영어 118개 중 오탐 15건(옮기기 전과 같은 항목 — `Treat Yourself`·`Detox`·`medicine ball` 같은 일부러 엄격한 것), **한국어 32개 중 0건**. `probe.py` 한국어 이름 붙은 10개 중 9개가 막힌다(`비타민 D`는 의도적 제외), 영어 `diet plan` 막힘. `bypass.py` 섹션 B의 위험 문장 7개가 모두 `BODY_TOPIC`(전: 5개 통과), 섹션 A의 `blood-pressure`·`bloodpressure`·`blood-sugar friendly`·`shed pounds`·`drop a few kilos`·`sleeping tablets`·`sleep aid`·`diet plan` 막힘. `manual_topic.py`는 `topic_allowed` 호출이 잡히고 금지 주제 8개가 모두 종료 2(`TOPIC_BLOCKED`)로 멈춘다(전: Gemini를 불러 3번 탈락하거나 통과).
- **실제 글 점검**: 이력에 남은 한국어 글 5편의 제목·라벨·주제·본문 문장 40개와 한국어 일상 문장 20개가 새 한국어 목록에서 탈락 0건.
- **변이(내가 직접)**: ① 이름 붙은 변이 65개(절 경계 문장부호 8·절 나누기·veto·문장 분리·라틴 경계·사유 접기·레지스트리 검증·러너 가드·프롬프트·문서, 그리고 바꾼 패턴 30곳을 옛 문자열로 되돌리기) ② 패턴 통째 삭제 296개(영어·한국어 목록 전수, 새 필드 포함) ③ 선택지 하나씩 삭제 627개(새로 더했거나 바꾼 패턴의 `|` 선택지를 하나씩 지움). ①②는 전부 사망했다. ③은 패턴 단위 시험이 못 잡던 구멍을 드러냈다 — 1차 321 사망·306 생존(동등 39 + 시험 구멍 267). 선택지마다 표본을 두는 `AlternativeCoverageTest`를 더하고 같은 두 묶음에 든 낱말(`shed…`/`drop…`, `expecting…`/`nursing…`)·절 경계 시험 틀을 고친 뒤 전체를 다시 돌려 **590 사망·37 생존**이다. 남은 37개는 모두 동등 변이다 — 다른 패턴이 같은 말을 이미 막는 중복 선택지(`illness`·`disease`·`disorders?` 등)라 동작이 다르지 않다(선택지 하나만 남긴 패턴에서 만든 문자열 수천 개로 확인 — 모두 다른 패턴이 같이 막는다). 합계 = **988개 중 951 사망, 생존 37**.

### 못 한 검증
- Actions 실행, 실제 Gemini 영어 출력으로 본 탈락률(상담 구절 절 단위 면제가 첫 영어 초안을 얼마나 막는지), 영문 글의 사람 눈 검토. `mode`·시크릿은 건드리지 않았다.

### 다음 AI에게 남기는 주의사항
1. 이 변경은 `mode: draft`를 켜기 **전에** 병합한다(D-64 ⑥). 병합 뒤 첫 영어 초안(L3)에서 `BODY_TOPIC`·`TOPIC_BLOCKED` 빈도를 본다. 같은 날 `GATE_REJECTED`가 반복되면 사유의 `'낱말'`을 보고 목록을 조정하되, 오탐이면 `tests/test_guardrails.py` 표본과 같이 바꾼다.
2. 새 규칙은 규칙마다 그 규칙만 막는 표본이 있어야 시험이 통과한다(`RuleCoverageTest`·`ClauseScopedExemptionTest`). 절 경계 패턴을 바꾸면 `MIXED_BLOCKED_*`·`REFERRAL_OK_*` 표본을 같이 본다.
3. 알려진 한계(문서 `docs/ARCHITECTURE.md` §7-1 '절 단위 면제'): 상담 구절이 접속어 없이 같은 절에 있는 문장(쉼표 이음·꼬리 구절)과 줄바꿈으로 갈린 두 낱말 용어·한 문장 안의 다른 언어 낱말은 여전히 통과하고, 목록에 없는 성분 이름(`magnesium`·`turmeric`)은 수동 `topic`도 통과한다.
4. `docs/ACTIONS_GUIDE.md` 6-1 표에는 새 코드 `TOPIC_BLOCKED`가 없다(총괄이 문서 PR에서 갱신). 새 결함 번호는 D-67부터(D-65·D-66은 PR #42가 썼다).

### 남은 이슈 / 확인할 점
- **독립 검증 델타(병합 가능)가 낸 `mode: draft` 전 권고**(병합 조건은 아님, 후속 PR): N-1 쉼표 없는 접속어(`so`·`yet`·`while`·`because`·`unless you`·`otherwise`, 한국어 `, 그래서`·`고 나서`)가 아직 상담 구절 면제를 받는다(중간), N-3 용량 단위(`milligrams`·`0.4 g`·`400-mg`·`capsules`) 미인식, N-4 레지스트리는 패턴을 하나씩·gates 는 합쳐 컴파일해 `(?i)`·같은 이름 그룹이 실행 중 `re.error` 가 될 수 있음, N-5 시험 구멍 5개, N-7 수동 주제 가드와 `UPLOAD_SKIPPED` 안내 순서. N-2(`, then` 조건문·`stop and consult` 과잉 차단)는 첫 실제 영어 초안의 `BODY_TOPIC` 빈도를 보고 정한다.
- **과잉 차단 트레이드오프(실측)**: 병명을 이름 붙인 절과 상담 구절이 `, so`·`—`·`:`·`;`·`으니`로 나뉜 정상 안내도 이제 막는다 — 상담 구절이 든 정상 안내 표본 40개(영어 30·한국어 10, 모델이 쓸 법한 문체) 중 막히는 문장이 **2개 → 7개**("Pregnancy can change your needs, so talk to your doctor."·"If you have a condition—such as diabetes—talk to your doctor …"·"Who should check with a doctor first: pregnant women, people with diabetes …"·"임신 중에는 몸 상태가 달라질 수 있으니 의사와 상담하세요."). 구조로는 '위험한 권유, so 의사에게 물어보세요'와 구별되지 않아(검증자가 막으라고 한 세 번째 문장과 같은 모양) 막는 쪽으로 정했고 시험이 `STRICT_TRADE_OFF_*`로 고정한다. 풀려면 `_CLAUSE_PUNCTUATION`·프로필 `body_clause_split_patterns`에서 해당 경계를 빼면 되지만 검증자의 문장이 다시 통과하니 총괄 결정이다. 프롬프트가 병명을 쓰지 말라고 하므로 실제 빈도는 낮을 것이고, 재시도 피드백이 병명을 빼게 한다.
- 영어 목록에 아직 없는 질환·보조 성분(탈모·관절·역류성 식도염·변비·소화불량·우울감·오메가3·프로바이오틱스·홍삼·숙취·여드름·알레르기)은 범위 밖이라 그대로다 — 어디까지 막을지는 `통증`·`비타민`(단독) 같은 열린 운영자 결정(D-64 ④)과 같은 성격이다.
- 한국어 `다이어트`는 '스마트폰 다이어트' 같은 비유 표현도 막는다(재시도가 고친다). 한국어 프로필을 쓰는 블로그는 아직 없다.

---

## [2026-10-26] Claude – 콘텐츠 전략 Phase 0 보고서와 현황 문서 갱신 (문서 전용, 코드·광고 표면 변경 없음)

**작업자**: Claude
**대상**: Chance_Blog·공통 (문서)
**등급**: T1(문서) — 광고 표면·신뢰 목록·코드 변경 없음
**목적**: 작업요청서 3(콘텐츠 전략)의 Phase 0(읽기 전용 보고)을 낸다. 사용자가 2026-10-26 채팅으로 확정한 결정(블로그별 전문 주제, Chance 주력 "공공 자료로 읽는 세계", 수동 작성 없음)과 지금 저장소 구조를 맞대어 Phase 1 설계를 고친다.

### 한 일
- 새 `docs/analysis/2026-10-26_content-strategy-phase0.md`: 요청서와 달라진 것 표, 스킵 로직·사유 분포·주제 선정·데이터 구조 진단, 3-2·3-3 설계를 실제 구조에 맞춘 수정안(백로그 파일을 만들지 않고 소스 피드를 후보 풀로 유지, 선정 조건 7개 ↔ 현 코드), 새 주제의 분야·소스 지도와 평일 공급, 남은 결정 7건(기본값 적용), Phase 1 후보.
- `인수인계/작업내용.md`: GOV.UK(#38)·Blogger 통합(#39) 병합 기록, 18시 슬롯 관측 행, §3 20번(Phase 0 결정 7건, 기본값), `인수인계/작업요청/README.md`의 요청서 3 상태, 거울 표 13번.

### 남긴 것
- 18시 슬롯(약 18:17 KST) 첫 실행 관측: `소스 …` 줄·분야 표·글 끝 인용 줄과 고지문.
- Phase 1 은 사용자 확인 뒤(월별 지표 중복 완화, 쿼터 거버너(사용자의 AI Studio 한도 표 필요), 소개문 정렬(T3), 한글 Blogger·네이버).

---

## [2026-10-26] Claude – Blogger 주제 가드레일(제목·라벨·본문)과 영문 프로필·영어 프롬프트, macat0722 영문 전환 (운영자 승인 2026-10-26, D-64)

**작업자**: Claude (구현 세션, 독립 검증은 별도 세션)  
**대상**: Blogger  
**등급**: T3(프로필·언어·톤 변경, 레지스트리의 프로필·프롬프트 전환)·T1(금지 표현 강화) — 운영자가 2026-10-26 채팅으로 승인("3. 수동 작성은 없을 예정이니 주제에 대한 가드레일을 설정하고 진행", "5. 3번 답변 + 주제 변경이 필요하면 문제 되지 않는 선에서 변경하여 진행", "6. 모드는 draft까지, auto는 AdSense 판정 전 보류"에 동의). **`mode`는 바꾸지 않았다**: `blogger_macat`은 off 그대로이고, 켜는 것은 검증 뒤 별도 T3 승인과 운영자의 시크릿 등록 뒤다.  
**목적**: 수동 작성 경로가 없어 모든 글이 자동 생성이므로, 안전한 주제를 받은 모델이 질병·치료·약·보충제·진단·임신·영유아·체중 감량 쪽으로 흐르는 것을 주제 후보뿐 아니라 생성된 제목·라벨·본문에서도 막는다. 영문 블로그(macat0722)를 영문 프로필·영어 프롬프트로 옮긴다(D-32, D-64).  
**브랜치**: `ai/claude/blogger-guardrails-en`(작업 시작 main 9ba5313, push 전에 최신 main 53ce263 — Blogger 초안함 업로드·인증 점검 통합 PR #39, 해외 소스 PR #35, GOV.UK 소스 PR #38이 병합된 뒤 — 위로 옮김. 문서 충돌은 두 쪽 내용을 살려 풀었고 코드·시험은 자동 병합). PR 생성·병합·Actions 실행·시크릿 등록은 하지 않았다(총괄이 독립 검증 뒤 처리).

### 변경 사항
- **가드레일**(`pipeline/gates.py`, 설계 `docs/ARCHITECTURE.md` 7-1절): 같은 위험 어휘를 세 곳에 건다 — (a) 주제 후보(`topic_allowed`, 기존) (b) 제목(`banned_topic_patterns`를 예외 없이 → `TITLE_TOPIC`)·라벨(`LABELS`, 기존) (c) 본문(`body_banned_patterns`를 문장 단위로 보되 `body_safe_patterns`에 맞는 전문가 상담·면책 문장은 건너뜀 → `BODY_TOPIC`). 효능 단정(`banned_patterns`)은 예외 없이 제목+본문 전체에 그대로 건다. 본문을 '단정·조언 문맥'에 가깝게 건 이유: 안전한 면책·상담 문장("does not replace professional medical advice", "의사와 상담하세요")에도 위험 낱말이 들어가고, 영어는 `treat yourself`·`a dose of fresh air`·`time heals` 같은 일상어와 겹치며, 오탐으로 재시도 3회가 모두 탈락하면 그날 발행을 잃는다. 그래서 영어 본문 목록은 주제 목록에서 `treat`(의료 대상이 뒤따를 때만)·`heal`·`remedy`·`immune`·`pharmacy`·사람을 가리키는 `therapist`를 뺀 부분집합이고 한국어 본문 목록은 주제 목록과 같다(시험이 같음을 고정).
- **영어 글 언어 검사**(`check_post`): `language: en`이면 글자 중 라틴 문자 비율이 `min_latin_ratio`(0.9) 이상이어야 하고 제목에는 라틴이 아닌 글자가 하나도 없어야 한다(한국어 검사는 그대로). 응답 머리표는 `Title:/Labels:/Content:`도 받는다(한국어 머리표 우선, 두 가지를 섞어 빈 항목을 채우지 않음). 비교 전에 글을 고른다(NFKC·보이지 않는 문자 제거·굽은 따옴표 곧게 — 굽은 따옴표로 쓴 `isn't a substitute…` 면책이 탈락하고 단정이 통과하는 일을 막는다).
- **레지스트리 검증**(`pipeline/registry.py`): 프로필 `language`가 `ko`·`en`인지, 비율 필드, 정규식이 배열·컴파일, **빈 문자열에 맞는 정규식 금지**(끝에 `|`가 남으면 금지 목록은 모든 글을, `body_safe_patterns`는 모든 문장을 건너뛰어 가드레일이 조용히 꺼진다), **시드가 금지 주제 목록을 통과**, `prompt_extra`·`topic_expand_prompt` 형식, 그리고 블로그 `languages`에 프로필 `language`가 들어 있는지(D-32 재발 방지).
- **영문 프로필**(`pipeline/profiles/blogger_practical_en.json` 신설): 한국어 프로필과 같은 엄격함의 영어판 — 효능 단정 13·클릭 미끼 제목 12·AI 자기 언급·잔재 16·주제 위험 어휘 61(굴절형·단어 경계)·본문 50·본문 예외 4, 글자 수 2,400~7,500·제목 15~70·라벨 30자, 영어 면책, 시드 34개(한국어 시드 32개 중 30개의 영어판 + 새 4개, 모두 가드레일 통과·35~55자). 한국어↔영어 대응표는 ARCHITECTURE 7-1절.
- **영어 프롬프트**(`.github/editorial/BLOGGER_PROMPT_EN.md` 신설): 한국어 프롬프트와 같은 구조·같은 안전 규칙(개인 경험·연구·통계·전문가 지어내기 금지, 질병·치료·약·보충제·용량·진단·임신·영유아·체중 감량은 경고로도 쓰지 않기, 완화 표현, 면책 문장은 쓰지 않기, 출력 형식). 연결은 레지스트리 `prompt`·`profile` 필드로 충분하다(`pipeline/run.py` 수정 없음).
- **스텁·주제 확장**(`pipeline/stubs.py`, `pipeline/topics.py`): 연습 실행(`--dry-run`)의 가짜 AI 응답이 영문 프롬프트에는 영어 글을 낸다(프롬프트의 `Topic:` 줄·`JSON array of strings`로 판별). 주제 확장 지시문은 프로필의 `topic_expand_prompt`를 쓰고 없으면 예전 한국어 지시문 그대로다(시험이 바이트 단위로 같음을 고정).
- **한국어 프로필**(`blogger_practical_ko.json`): 같은 가드레일 적용 + 오탐 2건 정정(`자해`↔"투자해서"는 앞에 한글이 없을 때만, `주사`↔"주사위" 제외). 실제로 생성된 본문 5편에서 "투자해서"가 새 본문 검사에 걸리는 것을 찾아 고쳤다.
- **레지스트리 전환**(`pipeline/blogs.json`): `blogger_macat` → `role` "생활 습관 실용형 (EN)"·`languages ["en"]`·`prompt` `BLOGGER_PROMPT_EN.md`·`profile` `blogger_practical_en`. `mode`(off)·시크릿 이름·일정·상한·상태 경로는 그대로.
- **시험**: 새 `tests/test_guardrails.py`(74개)·`tests/test_profile_en.py`(42개), `test_run.make_root`에 `lang`(기본 `ko`: 임시 저장소가 영문 항목을 한국어 프로필·프롬프트로 바꿔 기존 흐름 시험을 그대로 유지), `test_gates`(+3)·`test_topics`(+2)·`test_registry`(+2). 문서: ARCHITECTURE 7-1절 신설, SECURITY_GUARDRAILS G-C4·게이트 코드 줄, ENGINEERING_GUIDE, DEFECT_REGISTER D-64·D-32 상태, HANDLER(§0 표의 Blogger 두 줄·§3 P1의 영문 프로필 두 문장), 인수인계/작업내용, AI_COLLAB(영문 전환 안내 두 줄).

### 검증 증거
- **L0**: `python scripts/validate_repo.py --base 53ce263` 오류 0·경고 1(LIQUID-1, main과 같음); `python -m pipeline.registry` 통과; `python -m pipeline.plan --platform blogger` → `{"include":[]}`(off라 대상 0개); `python -m pipeline.run --blog blogger_macat --dry-run` → `[SKIP] code=MODE_OFF`, 종료 0; pyflakes — 새·바꾼 파일 0건(`tests/*.py`의 `_bootstrap` 임포트와 `pipeline/publishers/__init__.py` 재수출 경고는 main과 같다); vermin 3.7 이상.
- **L1**: `python -m unittest discover -s tests` **2093개 통과**(기준 main 53ce263의 1,970개 → 새 시험 123개). 시험은 네트워크 없이 돈다.
- **L2(임시 저장소)**: `make_root(lang="en")`(mode draft)에서 영문 프로필·프롬프트로 가짜 AI 응답을 끝까지 돌림 — 연습 실행 통과(저장 없음), 초안 저장(영어 본문·영어 면책), 제목에 위험 낱말(3회 탈락 `rejected`), 본문에 위험 낱말 후 재작성 통과(시도 2), 전문가 상담 문장 통과, 한국어 응답 탈락(`LANG`), 수동 topic이 제목에 오르면 탈락, 시드 소진 뒤 영어 주제 확장.
- **L3(실제 Gemini 초안)**: **실행 필요** — 이 환경에서는 Actions를 실행하지 않았고 실제 영어 글의 탈락률은 못 봤다.
- **변이**(내가 직접 돌림, main 위로 옮긴 최종 트리에서): 한 줄씩 망가뜨린 변이 48개(게이트 세 지점·언어 검사·머리표·정규화·레지스트리 검증·스텁·주제 확장·레지스트리 전환·프롬프트 규칙·프로필 설정)와 프로필 목록의 패턴을 하나씩 지운 변이 216개(전체: 영어 156·한국어 60)를 합쳐 264개 중 264 사망, 생존 0. 도중에 살아남은 변이가 있었고(영어 `body_safe_patterns`의 '참고용' 문장 패턴 등) 시험을 보강해 잡았다.
- **통합 PR 병합 뒤 main 위로 옮김**: Blogger 초안함 업로드·인증 점검 통합(PR #39)과 소스 PR 2개가 main에 병합된 뒤라 그 위(53ce263)로 옮겼다. 충돌은 문서뿐이었고(`HANDLER.md` §0 표의 Blogger 행·`WORKLOG.md` 최상단·`docs/ARCHITECTURE.md` §2 '주제' 행·`인수인계/작업내용.md`의 표 행) 두 쪽 내용을 살려 풀었다. 코드·시험(`pipeline/registry.py`·`tests/test_registry.py`·`tests/test_run.py`)은 자동 병합됐다. 통합 PR의 시험(문서 문구를 고정하는 시험 포함)과 함께 전체 시험 2093개가 통과한다. 옮기기 전에 통합 브랜치(4bd6def)와 합쳐 본 시험에서는 충돌을 모두 이 브랜치(main) 쪽으로 풀면 통합 쪽의 문서 문구 시험 2개가 실패했고 두 쪽을 살려 풀면 통과했다 — 같은 문서를 건드릴 때 통합 PR이 고정한 문구를 지켜야 한다.

### 못 한 검증
- Actions 실행(L2 연습 실행·L3 초안), 실제 Gemini 영어 출력으로 본 가드레일 탈락률, 영문 글의 사람 눈 검토, Blogger 초안함 업로드(범위 밖).

### 다음 AI에게 남기는 주의사항
1. **`mode`는 off다.** 켜려면 운영자 채팅 승인(T3)과 시크릿 등록(운영자)이 먼저고, 첫 초안(L3)에서 영어 글이 가드레일에 얼마나 탈락하는지 본다. 같은 날 `GATE_REJECTED`가 반복되면 사유의 `'낱말'`을 보고 프로필 목록을 조정하되, 오탐이면 `tests/test_guardrails.py` 표본과 같이 바꾼다(규칙마다 그 규칙만 막는 표본이 있어야 시험이 통과한다).
2. 수동 `topic`(override)은 러너가 주제 후보 검사를 건너뛴다(`pipeline/run.py`). 제목·본문 가드레일이 막지만 러너에서 막는 것이 정석이다 — 별도 변경(통합 PR이 병합돼 이제 `run.py`를 안전하게 고칠 수 있다. 같은 변경에서 `build_prompt`의 한국어 머리글(`[추가 규칙]`·`[이전 시도에서 고쳐야 할 점]`)도 영어 블로그에 맞출 수 있다).
3. 병합 뒤 문서: `docs/DEFECT_REGISTER.md`의 D-32 행은 이 브랜치가 '완화(코드 구현됨·병합 대기)'로만 적었으니 병합되면 '해결(관측 필요)'로 바꾼다. `docs/ACTIONS_GUIDE.md`(26·313·318행)·`docs/REQUEST_BRIEFING.md`(59·187·189행)·`docs/SESSION_START.md`(111~112·125·127·151행)의 "영문 프로필이 아직 없다/진행 중" 문장은 범위 밖이라 이 브랜치가 고치지 않았다 — 병합 뒤 갱신. `인수인계/작업내용.md`의 맨 위 '마지막 갱신' 줄도 여러 브랜치가 같은 줄을 고쳐 충돌하므로 건드리지 않았다. `HANDLER.md` §3 P1의 재개 절차 줄은 통합 PR의 시험 2개(`test_draft_upload`의 `…stale_publish_checkbox_wording_is_gone…`, `test_manual_run_defaults`의 `…first_run_guidance_tells_to_uncheck_the_practice_run`)가 문구를 고정하므로 영문 프로필 문장만 바꿨다.
4. 새 결함 번호는 D-65부터.

### 남은 이슈 / 확인할 점
- 영어 시드 중 모델이 위험한 쪽으로 흐르기 쉬운 것(오후 에너지·자기 전 진정 루틴·물 마시기·비 오는 날·가벼운 저녁): 가드레일이 막고 재시도가 고치지만 탈락률에는 영향이 있다.
- 경계 낱말: 일상 표현과 겹치는 `통증`·`비타민`·`알레르기`·`아이`(영어 `pain`·`vitamin`(단독)·`allergy`·`kids`)는 두 언어 모두 목록에 넣지 않았다. 영어만 `detox`(`digital detox` 포함)·`cleanse`·`keto`·`fasting`·`cholesterol` 등을 막고 한국어 목록(원래 28개)에는 대응 낱말이 없다 — 어디까지 막을지는 운영자 결정(D-64 ④, 대응표는 ARCHITECTURE 7-1절).
- 본문에서 "임신 중이면 의사와 상담하세요"처럼 질환·임신을 이름 붙인 상담 안내는 통과한다(권장). 더 엄격하게 하려면 그 문장도 막는다 — 운영자 결정.

---

## [2026-10-26] Claude – GOV.UK(영국 정부) 소스 2개 추가 (운영자 결정 2026-10-26 "AI 학습을 위한 목적이 아니기에 문제가 없을것으로 보여져", T3 신뢰 목록)

**작업자**: Claude
**대상**: Chance_Blog
**등급**: T3(신뢰 목록·공개 콘텐츠 공급원) — 운영자가 2026-10-26 채팅으로 GOV.UK 사용을 결정했다(robots.txt 의 AI 크롤러 `meta-externalagent` 제한은 `/search/all*` 에만 걸려 이 소스 경로와 무관, 이용 목적이 학습이 아니라는 이유)
**목적**: 약관이 재가공을 허용한(OGL v3.0) 공식 자료로 과학·환경·기술 분야 공급을 보탠다.

### 한 일
- `generator.py`: `_OGL_URL`·`_GOVUK_*` 상수와 `NEWS_SOURCES` 2개(`GOV.UK · Environment & Energy`(과학, DESNZ+Defra), `GOV.UK · Science & Technology`(기술, DSIT+AI Security Institute)), `www.gov.uk` 를 과학·기술 신뢰 목록에 추가(다른 `*.gov.uk` 는 신뢰하지 않음). 보도 기사(`/government/news/`)만 읽는 링크 제외, 제목 제외(인사·신청 안내·성명·조의·선거·전쟁·군사 소재·자살·자해·성폭력·아동 성착취·테러), 기사 페이지를 읽지 않음(`no_page_fetch`), 인용 줄(OGL 문구·링크)·고지문·작성 지침(정부 주장과 사실 구분, 정당·선거·장관 평가 금지, 의학 조언 금지).
- `tests/test_generator_slots.py`: 소스 표·신뢰 분야(다른 정부 호스트 거부)·실제 제목 표본(보도 기사 유지, 연설·정책 문서·사례 소개·인사·신청·성명·전쟁·민감 주제 제외, 평범한 제목 유지)·인용 줄 정확한 문구·고지문·엔진 수준(Atom 읽기·페이지 비접속·분야별 요청). 제외 규칙·링크 규칙·신뢰 목록·지침·인용 줄의 변이 36개를 직접 넣어 모두 시험이 잡음(코드 검증 뒤 제외어를 보강하며 더 잘게 나눈 변이 51개도 모두 잡음).
- 문서: 분석 문서(채택 표·후보 표 정리·제외 피드·한계), ARCHITECTURE 소스 표, DEFECT_REGISTER D-62·관측 체크리스트, 작업내용·거울 표.

### 독립 검증
- **코드**(별도 세션, 새 clone): 판정 **병합 가능**(막는 결함 없음). 전체 시험 1820개, 링크 규칙(부정 전방탐색)이 보도 기사만 통과시키고 연설·정책 문서·검색·피드·다른 호스트·http·상대·빈 주소를 모두 제외함을 확인, 실제 피드 사본 40건 판정 적절, `www.gov.uk` 만 신뢰(다른 `*.gov.uk` 거부), 인용 줄·고지문 렌더링 확인, `no_page_fetch` 가 실제로 페이지를 안 읽음, 기존 소스 판정 변화 0(1100건), 변이 65개 중 55 사망·생존 10개(제외어 단독 제목 없음·링크 규칙 미세 변이). 비차단 권고를 반영: `appoint` 를 인사 소식 표현(appoints·appointed·appointments to/of/as·reappoint·new chair·steps down)으로 좁혀 "AI to speed up appointments for patients" 같은 진료 소식을 살림, 분쟁(Iran·Israel·Middle East·NATO·sanctions)·학대(child abuse·domestic abuse·violence against women)·극단주의·급진화 제외어 추가, 링크 규칙 시험(https·정확한 호스트·news/ 슬래시)과 단독 제목 시험 추가.
- **약관 사실**(별도 세션, 1차 자료 재확인): 판정 **병합 가능**(막는 결함 없음). OGL 조건·robots.txt(`meta-externalagent` 는 `/search/all*` 만, 우리 피드·기사 경로는 허용)·AI 조항 없음·피드 한계(20건·`updated`만)·숫자(40건 표본)가 1차 자료와 맞음. 비차단 5건을 반영: v3.0 근거는 이용약관이 아니라 페이지 바닥글("달리 표시한 경우는 제외")임을 문서·주석에 적음, OGL Non-endorsement 가 공식 지위 암시도 금지해 고지문에 "정부의 공식 입장·공식 문서가 아님"과 작성 지침 한 줄을 더함, 경제 피드 제외 근거를 실측(받아 둔 20건 중 8건이 총리·재무장관·장관의 발표·연설·통화)으로 정정, ONS UA 조건은 GOV.UK 피드가 아닌 ons.gov.uk 사이트 얘기라 분리, 영문 인용 줄·고지문의 OGL 기본 문구를 약관 글자 그대로("…v3.0. (링크)") 순서로.

### 남긴 것
- 병합 뒤(#35 병합 뒤) 첫 슬롯 실행에서 `소스 GOV.UK · …` 줄과 글 끝 OGL 문구·고지문을 눈으로 확인한다. 후보가 거의 없을 수 있다(과학·기술 피드는 한 달에 서너 건, 에너지·환경은 보도 기사 13건 중 5건이 요약이 짧아 빠진다).
- 경제·보건 피드는 쓰지 않는다(정치 발표 위주·의료 조언 위험). NCSC·ONS 는 후보로 남김(ONS 는 UA 조건).

---

## [2026-10-26] Claude – Blogger 초안함 업로드·인증 점검 통합 브랜치 `ai/claude/blogger-integration`: main(9ba5313)을 합치고 충돌 7개 파일 해결, 가이드 병합대기 표식 걷기 (승인 4번 ①, 독립 검증 병합 가능 → main(69139b0) 재통합 뒤 PR)

**작업자**: Claude (통합 담당 서브에이전트, 독립 검증은 별도 세션)  
**대상**: Blogger  
**등급**: T2(코드·워크플로 통합, 독립 검증 필요) — 운영자가 2026-10-26 채팅으로 승인한 4번 ①("Blogger 초안함 API 업로드")의 구현이다. 이 변경은 Blogger를 켜지 않는다  
**목적**: 독립 검증 2회 "병합 가능"을 받은 두 브랜치(`ai/claude/blogger-draft-upload` → `ai/claude/blogger-auth-check`)를 호출 기록 병합(#24) 이후의 main(9ba5313)과 합친 PR 준비 브랜치 하나로 만든다. 독립 검증(별도 세션, 2026-10-26, head 4bd6def·기준 main 9ba5313)은 **병합 가능**(막는 결함 없음, 시험 1926개, 432 시나리오 행동 표·변이 37개 모두 통과)이었고, 그 뒤 main(69139b0: #34 사이트 정리·#36·#37)을 다시 합쳐 PR 로 올린다

### 한 일
- `origin/ai/claude/blogger-auth-check`에서 새 브랜치를 만들고 `origin/main`(9ba5313)을 **병합 커밋**으로 합쳤다(리베이스 아님, 병합 커밋 `18dac09`, 부모 `0f24ecd`·`9ba5313`). 문서 정리는 별도 커밋으로 나눴다. main 쪽에는 호출 기록(#24)·출처 개편(#27~#31)·확인 필요 모음·Pages 배포 확인·Actions 가이드·모델 3.7 제거·예약 47분 틱·`defaults.mode` draft 복귀(#33)가 들어 있다.
- **충돌 7개 파일과 해결**(원칙: main의 새 내용을 지키고 브랜치 추가분을 더한다)

| 파일 | 해결 |
|---|---|
| `pipeline/run.py`(4곳) | import는 main의 `call_log_of`·`purpose`와 브랜치의 `redact`·`PLATFORMS`를 두고 안 쓰게 된 `mask`만 뺐다. 인증 점검 뒤로 옮겨진 주제 선정을 `with purpose(llm, "topic-expansion"):`로 감쌌다. `LLM_FAILED`는 이력에 브랜치의 `redact(exc, secret_values)`, 요약에 main의 `ai_lines()`. 성공 요약은 브랜치의 `lines` 끝에 `lines += [f"- {line}" for line in ai_lines()]` |
| `.github/workflows/blogger.yml` | `publish` choice(off·draft·publish, 기본 draft)·`auth_check` 유지, main의 `dry_run` 기본 켜짐·설명 유지. `publish` 설명에 main이 더한 "연습 실행을 풀었을 때만 적용" 뜻을 넣되 120자 이내로 줄임 |
| `HANDLER.md`(2곳) | 브랜치의 재개 절차·§10 5-4를 두고, 병합으로 낡아진 두 문장("이 입력이 아직 없으면", "기본값이 바뀌면")을 현재형으로 고치고 main의 "연습 실행 기본 켜짐" 설명을 더함 |
| `docs/ARCHITECTURE.md`(2곳) | `mode` 행은 브랜치(초안함 업로드), `workflow` 행은 main(cron 목록·47분 틱), 블로그 추가 플레이북 5단계는 둘을 합침 |
| `docs/DEFECT_REGISTER.md`(3곳) | main의 D-49~D-54·D-58~D-63 전부 + 브랜치의 D-55~D-57(D-49는 브랜치가 바꾸지 않아 main의 정정판). 관측 체크리스트는 main 9행 + 브랜치 2행. 번호 D-01~D-63 순서·중복 없음 확인 |
| `docs/ENGINEERING_GUIDE.md` | L3 행은 브랜치(이미 "`연습 실행` 체크를 풀고 `publish`=`draft`") |
| `tests/test_workflow_names.py` | `ALLOWED_REFS` 합집합(`inputs.auth_check`·`inputs.real_ai`) |

- **충돌 없이 합쳐졌지만 확인한 것**: `pipeline/blogs.json`(main의 모델 3개·`defaults.mode` draft, 두 블로그 모두 `mode`를 직접 적음 — REG-1, `chance` auto·`blogger_macat` **off 유지**), `pipeline/registry.py`의 REG-1, `tests/test_registry.py`·`tests/test_validate_repo.py`(main과 브랜치가 각자 더한 시험이 같이 통과). 병합 커밋 기준으로 main 대비 바뀐 파일은 브랜치가 원래 바꾸던 23개와 `tests/test_manual_run_defaults.py`뿐이고(문서 정리 커밋이 `docs/ACTIONS_GUIDE.md`·`docs/SESSION_START.md`·`인수인계/작업내용.md`·`WORKLOG.md`를 더한다), Chance 쪽(`generator.py`·`chanceblog.yml`·`chance-fix-images.yml`·`pages.yml`·`pipeline/llm.py`)은 바뀌지 않았다.
- **순수 병합이 아닌 변경과 이유**
  1. `tests/test_manual_run_defaults.py`(4건, 프로덕션 코드 변경 없음): 병합 뒤 이 파일의 3건이 실패했다 — 옛 체크박스 전제의 `test_a_manual_run_publishes_only_when_the_box_is_checked`('true'→'on', 입력 없음→'off')와, 낡은 안내 문구를 찾는 `test_every_blogger_first_run_guidance_tells_to_uncheck_the_practice_run`(HANDLER의 "L3 초안 1건"·"`publish`를 체크하지 말고"는 브랜치가 3택 문구로 바꿨고 브랜치 시험 `test_the_stale_publish_checkbox_wording_is_gone_from_the_operator_docs`가 옛 문구의 부재를 요구한다), 그리고 ARCHITECTURE 첫 실행 행에 `publish`가 없어야 한다는 `test_the_architecture_first_run_row_does_not_depend_on_the_shape_of_the_publish_input`(그 시험 자신이 draft-upload 병합 뒤에는 바뀔 것을 예고했다). 기대를 약하게 만들지 않고 새 구조로 바꿨다: 수동 실행은 고른 값(off·draft·publish)을 그대로 넘기고 러너가 'publish'만 즉시 게시('on')로 읽음, `publish` 입력은 choice(off·draft·publish)이고 기본값이 `draft`(즉시 게시가 아님), HANDLER 두 줄은 새 문구(`publish=draft`·`publish`를 `draft`(기본값))에서 `연습 실행` 체크를 풀라고 말함(정규식에 '푼'을 허용 — 브랜치 시험이 "체크를 푼"을 요구한다), ARCHITECTURE 행은 `publish=draft`·`publish=off`를 말하고 `publish=publish`는 말하지 않음. 같은 클래스의 정기 실행 시험은 3택 값으로 넓혔다.
  2. `blogger.yml` `publish` 입력 설명: main의 "연습 실행을 풀었을 때만 적용됩니다"를 그대로 더하면 125자라 브랜치 시험(`test_input_descriptions_stay_short_enough_to_read_in_the_run_workflow_dialog`, 120자 이하)이 실패해 "글을 어디까지(연습 실행을 풀어야 적용): …"로 줄였다.
  3. `pipeline/run.py`에서 `mask` import 제거(의뢰 목록의 항목): `redact`가 안에서 `mask`를 부르므로 마스킹은 그대로다.
- **가이드 정리**(검증자 목록은 이 파일 2026-10-25 총괄 항목): `docs/ACTIONS_GUIDE.md`의 `병합대기` 표식 5곳(`blogger-auth` 3, `blogger-draft` 2)과 각 "(아직 병합 전인 기능입니다…)" 안내 줄을 걷고 본문은 현재형으로 남겼다. 먼저 읽기 3의 표식 설명 문장 삭제(마지막 표식이 사라졌으므로). 3-12 시크릿 단계(5번 행)·6번 행·"하지 말 것"의 "초안함 업로드 모드가 있을 때만/없을 때" 한정 문구 삭제. 3-12 `defaults.mode` 문장 → "줄이 없으면 검증기(REG-1)가 오류로 막습니다". `BLOGGER_API_SETUP.md` 날짜 문장("2026-10-25 기준으로 … 낡은 부분이었습니다")과 "고쳐져 있으니" 문장을 날짜 없는 문장으로. `draft_uploaded`를 6-3 "하는 일"·"정상일 때"에 합치고 표식 블록의 중복 줄 삭제. 인증 점검만 실행의 "정지 중에도 점검하는 예외"를 3-12 2번 행·"알아 둘 것"·6-3 "지금 상태"에 표기. 용어 풀이 "모드" 행의 "defaults 이어받음"을 REG-1 문장으로. `.github/editorial/BLOGGER_API_SETUP.md` 머리의 "초안함 업로드 모드가 병합된 뒤에" 한 줄을 병합 전후와 무관한 순서 안내로.
- 상태 문서: `docs/SESSION_START.md` §5 머리·§5-1 #25 표현·§5-2 Blogger 행·§5-4 1번, `인수인계/작업내용.md` 머리·§2 행·§5 항목. **병합됨이 아니라 "push됨·독립 검증 대기"**로 적었다.

### 검증 증거 (최종 트리 기준, 이 PC: Windows·Python 3.12.10)
- `python -m unittest discover -s tests`(`PYTHONIOENCODING=utf-8`) → **1926개 통과, 실패·오류 0**(약 160초). 병합 직후 첫 실행에서 `tests/test_manual_run_defaults.py` 3건이 실패했고(위 1번), 고친 뒤 전체 실행에서 `publish` 입력 설명 125자 1건이 더 실패해 줄였다. 이 밖에 병합이 만든 시험 실패는 없었다. 모델 수·호출 수를 4개로 가정한 시험은 브랜치 새 시험에 없었다(`MODEL_COUNT`로 바꿀 곳 없음).
- `python scripts/validate_repo.py` → 오류 0건·경고 2건(`LIQUID-1` 인수인계 초안 문서, `EXPOSE-1` 내부 문서 공개 — 기준선과 같음).
- pyflakes(바뀐 .py 17개) → 새 지적 0. `_bootstrap` 미사용 import 3건(`tests/test_health_daily.py`·`tests/test_publisher_blogger.py`·`tests/test_registry.py`)은 main에도 있는 기준선이다. actionlint 1.7.12 → 0건.
- `git diff --check`(main 대비 변경분) → 이 항목 머리 줄의 끝 공백 2칸(마크다운 줄바꿈, 기존 항목과 같음)만 지적한다.
- **변이 확인**(저장소 밖 임시 사본에서만): ① `BLOGGER_PUBLISH` 식을 옛 체크박스 식으로 ② `publish` 기본값을 `publish`로 ③ ARCHITECTURE 첫 실행 행에서 `publish=off` 삭제 ④ HANDLER §10 5-4의 "연습 실행 체크를 푼 채" 삭제 ⑤ `publish` 설명을 120자 초과로 ⑥ `run.py` 성공 요약의 `ai_lines()` 줄 삭제 ⑦ 주제 선정의 `purpose(...)` 감싸기 삭제 ⑧ `LLM_FAILED` 요약의 `ai_lines()` 삭제 — **8개 모두 시험이 잡았다**.
- 로컬 점검: `python -m pipeline.registry` 통과(`chance` auto·`blogger_macat` off), `python -m pipeline.plan --platform blogger` → `{"include":[]}`(정기 실행은 대상 0개), `--include-off`는 인증 점검 전용으로만 `blogger_macat`을 넣음, `python -m pipeline.run --blog blogger_macat --dry-run` → `MODE_OFF` 건너뜀·종료 0.
- **실행하지 못한·하지 않은 것**: GitHub Actions(L2·L3 — 수동 실행·dispatch 없음), 실제 구글 API 호출(시크릿 없음, 가짜 게시자 시험만), 통합본에서의 Gemini 실호출. (통합본의 독립 검증은 이 항목을 쓴 뒤 별도 세션이 했다 — 아래 '독립 검증과 재통합'.)

### 독립 검증과 재통합 (2026-10-26)
- 별도 세션이 새 clone 에서 통합본(head 4bd6def, 기준 main 9ba5313)을 검증했다 — 판정 **병합 가능**(막는 결함 없음): 전체 시험 1926개, 432 시나리오 행동 표(모드×입력×시크릿×실패 지점), 인증 점검 실패 18개 시나리오·분류 10종 모두 Gemini 0회·게시 0회, 변이 37개 모두 시험이 잡음, Chance 경로 불변, 비밀 모양 0건. 낮음·문서 지적(`BLOGGER_API_SETUP.md` "어느 경우에도" 문장의 인증 점검 예외, `HANDLER` 재개 절차 중복, PR 본문에 `docs/CHARTER.md` 한 줄, 낡은 `REQUEST_BRIEFING` 줄)은 PR 에서 반영하거나 후속으로 남겼다.
- 그 뒤 main 이 움직여 두 번 다시 합쳤다: 69139b0(#34·#36·#37, 충돌 HANDLER·WORKLOG·작업내용 3개 문서) → 같은 검증자가 델타 확인(병합 가능, 코드·워크플로 바이트 동일, 전체 시험 1942개, 검증기 오류 0·경고 1), 이어 f37a94b(#35, 충돌 DEFECT_REGISTER 관측 표·작업내용 2개 문서). 코드·워크플로·시험은 재통합으로 바뀌지 않았다.

### 다음 AI에게 남기는 주의사항·남은 것
1. 이 브랜치는 독립 검증(병합 가능)을 거쳐 PR 로 올렸다(2026-10-26). 병합해도 Blogger는 켜지지 않는다 — `blogger_macat`은 `mode: off`이고 시크릿 4종은 병합 뒤 운영자가 영문 프로필·`mode: draft` 승인 뒤에 직접 등록한다. 지금 등록하지 않는다.
2. 작은 후속(이번에 일부러 하지 않음): 글을 만들기 전 인증 점검이 실패한 실행(`AUTH_CHECK_FAILED`)의 요약에는 main의 `Gemini 호출: N회` 줄이 없다(그 시점의 호출은 0회라 정보 손실은 없지만 "모든 종료 경로에 남긴다"는 main의 규칙과 한 곳 어긋남). `_auth_check_failed`에 `ai_lines()`를 넘기면 되고, 시험은 `tests/test_gemini_call_log.py` 5절에 한 건 더하면 된다.
3. `docs/ACTIONS_GUIDE.md` 3-13 표의 "후보 3건 × 모델 4개"·"최대 12건"은 모델이 3개가 된(#33) 뒤 낡은 숫자다(main의 문서, 이번 병합이 만든 것이 아님).
4. `HANDLER.md` 재개 절차에는 `mode: draft`가 ②와 ⑤에 두 번 나온다. 브랜치 시험(`test_the_stale_publish_checkbox_wording_is_gone_from_the_operator_docs`)이 "인증 점검만 실행 → `mode: draft` 전환 → `publish=draft`" 순서를 못 박고 있어 건드리지 않았다. 문장을 정리하려면 시험과 함께 고친다.
5. `docs/REQUEST_BRIEFING.md` 178행("시크릿 등록은 이 기능이 병합된 뒤에만")은 이 PR 에서 "병합되면(PR 열림) 시크릿·OAuth 등록은 운영자가 직접"으로 고쳤다. 병합 뒤 Actions 확인은 `docs/DEFECT_REGISTER.md` 하단 체크리스트의 D-55~D-57 두 행을 따른다.
6. 비밀·시크릿: 이 변경에는 값이 없다(PR 변경분에서 키 모양 문자열 0건 확인). 시크릿 등록·Actions 실행·dispatch는 하지 않았다.

---

## [2026-10-26] Claude – 코드·상태 파일을 사이트에서 뺌 (운영자 승인 2026-10-26 "2. 추천대로", T3 광고 표면 `_config.yml`)

**작업자**: Claude  
**대상**: Chance_Blog  
**등급**: T3(광고 표면 `_config.yml`) — 운영자가 2026-10-26 채팅으로 "코드·상태 파일(`generator.py`, `pipeline/`, `history.json` 등)도 사이트에서 뺄지" 질문에 "2. 추천대로"라고 답함(추천: 빼기)  
**목적**: 사이트에 쓸모없고 정적 파일로 그대로 열려 있던 코드·상태 파일(`…/generator.py`, `…/pipeline/blogs.json` 등 HTTP 200)을 사이트에서 뺀다. 저장소에는 그대로 있다.

### 한 일
- `_config.yml` `exclude`에 11항목 추가: `generator.py`·`blogger_generator.py`·`pipeline`·`scripts`·`tests`·`history.json`·`blogger_history.json`·`pages.json`·`requirements-dev.txt`·`requirements-edits.txt`·`requirements-pipeline.txt`(승인 범위 = 코드·상태 파일). **`README.md`는 문서라 승인 범위 밖이어서 넣지 않았다**(그대로 열려 있음). 사이트가 쓰는 파일은 넣지 않았고, Jekyll 3.10의 "항목으로 시작하는 이름도 뺀다" 규칙에 걸려 빠지는 공개 파일이 없음을 시험이 확인한다.
- `tests/test_site_cleanup.py`: `MUST_EXCLUDE`에 11항목을 옮기고 `STATIC_EXPOSED`는 `README.md`만 남김. 사이트가 이 파일들의 주소를 쓰지 않음은 #34 검증(저장소·워크플로·`verify_pages_deploy.py`·홈 JS)에서 확인했다.
- 문서: D-08 해결 표기, ARCHITECTURE·HANDLER·REQUEST_BRIEFING의 낡은 "내부 문서 공개" 서술, 작업내용(§2·§3 7·18번·이력).

### 독립 검증과 반영
- 별도 세션 검증(깨끗한 clone c2ba6b8, 판정 **병합 가능**): 전체 시험 1792개 통과·`validate_repo` 오류 0·경고 1(LIQUID-1)·AD-1 통과, Jekyll 3.10 규칙으로 추적 파일 전수 시뮬레이션에서 104개가 빠지고(운영 문서 27 — #34로 이미 빠짐 — 와 이 PR이 새로 빼는 코드·상태 77) 14개가 남으며(공개 13 + `README.md`) 우연히 빠지는 공개 파일 0건, 사이트 주소로 제외 대상을 읽는 코드·워크플로 0건, 변이 36건 중 의도한 것 전부 잡힘. 병합 전 빌드 비교 로그: 파일 104→27개, 사라진 77개, 새로 생긴 0개.
- 권고 반영: `docs/ACTIONS_GUIDE.md`의 낡은 "경고 2" 정정, SESSION_START·REQUEST_BRIEFING 거울 표(7·17번 갱신, 18·19번 추가), `tests/test_site_cleanup.py`의 분류를 이름 정확 일치(`unclassified`)로 바꿔 `tests-report.html` 같은 새 공개 파일이 `tests` 접두사에 조용히 빠지는 것을 시험이 알리게 함(새 시험 1개), 시험 설명·이름 갱신.
- 반영분 델타 확인(b2dedc1)도 병합 가능. 비차단 4건 반영: 빌드 비교 숫자 정정, 변이 수 36건 정정, 순수 함수 시험이 실제 분류 상수(`PUBLIC_ROOT`·`STATIC_EXPOSED`)에 묶인 것을 인자로 풀어 `README.md` 를 뺄 때 시험이 깨지지 않게 함, 글롭 글자가 든 이름도 정확 일치로 인정(`is_listed`).
- 남긴 것: `README.md` 제외 여부는 기본값(그대로 열어 둠)으로 두고 작업내용 §3 19번에 올림. D-08 '해결'은 병합·배포 확인 뒤 확정.

### 남긴 것
- 병합·배포 뒤 공개 사이트에서 `…/generator.py`·`…/pipeline/blogs.json`·`…/history.json`·`…/tests/…`가 404이고 사이트가 쓰는 주소(`posts.json`·`feed.xml`·`robots.txt`·홈·글 페이지)는 그대로 200인지 확인한다.

---

## [2026-10-26] Claude – 전자신문 출처로 공개된 글 1쌍 비공개 전환 (운영자 승인 2026-10-26, T3 공개 콘텐츠)

**작업자**: Claude  
**대상**: Chance_Blog  
**등급**: T3(공개 콘텐츠 변경) — 운영자가 2026-10-26 채팅으로 승인: "전자신문 출처 글 1쌍(2026-10-26-KR-101652·EN-101652)을 비공개로 전환해줘(삭제는 하지 말고)."  
**목적**: 전자신문(콘텐츠 이용에 정식 계약·사용료가 필요해 운영자 결정 14번으로 소스에서 뺀 매체)을 출처로 이미 공개된 글을 사이트에서 내린다. 삭제하지 않는다.

### 한 일
- `_posts/기술·미래/2026-10-26-KR-101652.md`, `_posts/Technology & Future/2026-10-26-EN-101652.md`: front matter `layout: post` 바로 아래에 `published: false` 한 줄씩(PR #29·#31과 같은 방식). 파일·이미지·이력(`history.json`)은 그대로라 되돌리려면 그 줄만 지우면 된다. Jekyll은 이 글들을 사이트·`posts.json`·`feed.xml`·사이트맵에서 뺀다. 같은 날 슬롯 기록(`slot_state`는 이력만 본다)은 남아 있어 18시 슬롯이 이 글 때문에 다시 열리지 않고, 같은 소재는 제목 유사도 검사(이력·`_posts` 제목)가 계속 막는다.
- `tests/test_verify_pages_select.py`: 두 파일을 `PUBLIC_MISSING`에 더해 `published: false`임을 시험이 확인한다(비공개 12건→14건). 배포 뒤 공개 반영 확인(verify)은 `published: false` 글을 건너뛰어 그다음으로 새 글을 본다.
- 문서: `인수인계/작업내용.md` §3 17번·이력, `docs/SESSION_START.md`·`docs/REQUEST_BRIEFING.md` 17번 줄.

### 남긴 것
- 병합·배포 뒤 공개 사이트에서 두 글 주소(`…/posts/2026/10/26/KR-101652/`·`…/EN-101652/`)가 404인지, `posts.json`·`feed.xml`·사이트맵에서 빠졌는지, 홈 글 카드가 2장 줄었는지 확인한다.
- `docs/DEFECT_REGISTER.md` D-61 행의 "그 출처 공개 글의 비공개 전환은 결정 대기" 문장은 해외 소스 추가 PR(#35)이 같은 행을 고치므로 그 PR이 병합된 뒤 이 결과로 바로잡는다(두 PR의 충돌 방지).

---

## [2026-10-26] Claude – 해외(미국 외) 소스 추가·전자신문 제외·신선도 72시간 (운영자 승인 2026-10-26 "13. 소스 추가"·"14. 무료 자동화 기반이란 취지에 맞지 않음")

**작업자**: Claude  
**대상**: Chance_Blog  
**등급**: T3(신뢰 목록·접근 차단 목록·공개 콘텐츠 공급원) — 운영자가 2026-10-26 채팅으로 13번 "소스 추가"와 14번 전자신문 제외를 답했고, 같은 날 "해외 사이트에서 미국 이외의 국가의 내용들도 확인이 가능하다면 진행"이라고 했다  
**목적**: 전자신문(정식 계약·사용료 필요)을 빼면서 약관이 상업 이용·재가공을 허용한 공식·공공 소스로 모든 분야에 공급을 만든다.

### 한 일
- **조사**: 지역별 3건(유럽 / 영국·캐나다·아시아태평양 / 국제기구·개방지식)이 소스마다 약관·robots.txt·피드를 직접 읽었다(수십 곳). 채택·후보·제외와 이유는 `docs/analysis/2026-10-26_overseas-sources.md`.
- **소스 8개 추가**(`generator.py` `NEWS_SOURCES`): EU 집행위원회 소식(사회·정책)·DG Energy(경제·일)·DG Environment·JRC(과학·환경)·디지털 전략(기술·미래), 캐나다 통계청 The Daily를 분야별 주제어로 나눈 3개(경제·일 / 사회·정책 / 일상·마음). 집행위원회 계열은 CC BY 4.0(출처·변경 표시), 통계청은 Open Licence(`Adapted from Statistics Canada…`·수치를 정확히 옮길 것). 글 끝 인용 줄·고지문·작성 지침을 소스마다 붙인다. Eurostat 소식·국채 입찰 공지·선거·정치광고·국방·안보 분류·민감 주제(자살·약물 과다복용·성폭력·살인)는 제외 규칙으로 뺀다.
- **전자신문 제외**: `NEWS_SOURCES`·기술 신뢰 목록에서 빼고 `TERMS_BLOCKED_DOMAINS`에 `etnews.com` 추가(콘텐츠 이용 안내가 정식 계약·사용료를 요구하고 무단 사용에 사용료의 30배 배상을 안내함, 운영자 결정 14번). 그 출처로 이미 공개된 글 1쌍은 이 PR에서 손대지 않았고, 운영자 승인(2026-10-26 채팅)을 받아 별도 PR #36에서 `published: false`로 비공개 전환했다.
- **엔진 보강**: ① `NEWS_MAX_AGE_HOURS` 36→72(주말·월요일 슬롯 공백) ② `parse_feed`가 Atom `type="xhtml"` 제목·요약(자식 요소 안의 글자)을 읽음(통계청 — 예전 코드로는 모든 항목이 빈 제목이라 `NO_TITLE`로 떨어졌다) ③ 소스 선택 키 `display_name`(같은 게시자를 분야별로 나눠 읽을 때 글에 보이는 출처 이름).
- **신뢰 목록**: `ec.europa.eu`(과학·경제·사회·기술)·`commission.europa.eu`(사회)·`statcan.gc.ca`(경제·사회·일상) 추가, `etnews.com` 제거. EIB·ACER·`ec.europa.eu.evil.example` 같은 집행위원회가 아닌 주소는 신뢰하지 않음을 시험이 고정.
- **시험**: `tests/test_generator_slots.py` 정리·보강(소스 표·차단 목록·신뢰 호스트·분야별 표본 제목·인용 줄 정확한 문구·xhtml Atom·72시간 경계·`display_name`).
- **문서**: ARCHITECTURE(소스 표·AGE 72시간·`display_name`), ACTIONS_GUIDE(AGE·분야 대체), DEFECT_REGISTER(D-61·D-62·관측 체크리스트), HANDLER·SESSION_START·REQUEST_BRIEFING·작업내용, 새 `docs/analysis/2026-10-26_overseas-sources.md`.

### 검증
- 전체 시험 1817개 통과(Windows·Python 3.12, main 69139b0을 합친 새 워크트리), pyflakes 0, `validate_repo` 오류 0. 받아 둔 실제 피드 6개로 분야별 시뮬레이션: 과학 6건·경제 3건·문화 1건, 사회·일상·기술은 0건(주말 직후라 항목이 72시간보다 오래됨), 전자신문 줄 없음, 새 소스의 제외 규칙이 의도한 항목(국채 입찰 공지·Eurostat 소식·국방·안보 분류 등)만 뺌.

### 독립 검증과 반영 (2026-10-26, 별도 세션 2건 — 코드 / 약관 사실, 각각 1차 + 델타 재검증)
- **1차 → `205bac3`·`9f2de57`**: 약관 사실 — Horizon 기사가 DG Environment 피드로 섞여 드는 것(`/horizon-magazine/` 제외), 성명·연설 제외 확장, 통계청 링크 글자 지침·Crawl-delay 존중(`page_delay`), 인용 줄 `?.` 정리, 분석 문서 숫자·문장 정정. 코드 — `text_of` 를 `type="xhtml"` 로 한정, 건강·의료 조언 금지 지침(`HEALTH_RULE`), 위원 방문·연설·"Apply for" 제외 확장, 통계청 폭력·아동 학대 제외, 시험 보강(민감 주제 시험이 제외 규칙을 직접 점검, 분야별 신뢰 목록 정확 집합, `display_name`, Eurostat·Horizon 제외, JRC 태그 단독 일치).
- **델타 재검증**: 코드 — **병합 가능**(막는 결함 없음, 전체 시험 1813개 통과, `parse_feed` 비교 실제 피드 13개·합성 16개·무작위 2만 건에서 의도한 차이만, 변이 58개 중 49 사망·생존 9개는 겹침이거나 시험 제목 없음). 약관 사실 — **수정 후 병합(경미)**: ① Press Corner(보도자료) 앱 바닥글에 법적 고지·라이선스 링크가 없어 재사용 조건을 확인하지 못한 채 통과 중(Energy 후보 약 30%) ② 연설·성명 제외가 Energy 에만 걸림 ③ 문서 문장 5곳.
- **반영 → `aa547bc`**: Press Corner 를 주소로 제외(`_EC_EXCLUDE_LINK` 에 `/commission/presscorner/` — 불명확은 유예한다는 운영자 원칙), 연설·성명·선언 제외를 집행위원회 소스 5개 전부로(`_EC_EXCLUDE_STATEMENTS`; 복수형 Speeches·Leaders Joint Statement·Joint Declaration 추가, "Declaration of conformity" 같은 문서 이름은 살림), 위원 방문 예고를 두 단어 이름·부위원장까지(`_EC_EXCLUDE_VISITS`), 신청 홍보를 "Apply now"·제목 앞 "Apply for" 로 좁혀 정책 기사("must apply for authorisation") 보호(`_EC_EXCLUDE_APPLY`), 통계청 제외어마다 단독 제목 시험 7개와 평범한 제목 5개 추가, 분석 문서·ARCHITECTURE·코드 주석 정정. 변이 18개(정밀화·제외 하나씩 되돌림)를 직접 넣어 모두 시험이 잡음.
- **최종 확인(7c91579 = aa547bc + main 69139b0 통합)**: 코드 **병합 가능**(전체 시험 1817개·변이 51개 중 49 사망, 생존 2개 — Press Corner 패턴을 detail 로 좁힘·joint declaration 삭제 — 는 주소 3형태·`Joint Declaration of Intent` 제목 시험을 더해 fb56588 에서 잡힘), 약관 사실 **병합 가능**(법적 고지 저장본 대조, 식별 가능한 개인·제3자 저작물 문장은 원문과 일치). 문장 정정 3건을 같은 PR에서 반영: 통계청 이름 사용 범위 해석을 실제 동작(필수 문구·고지문·'통계청 발표' 링크 글자·출처 목록에는 쓰고 제목·홍보 문구에는 쓰지 않음)에 맞춤, 로고·상표·이름이 재사용 정책에서 제외된다는 원문 표현, ARCHITECTURE 과학·환경 행의 신청 안내 제외 범위(Environment 만).
- 남은 비차단: 건강 조언 금지·링크 글자 지침은 AI 에게 하는 부탁이라 코드가 검사하지 않음(통계청 링크 글자 사후 검사는 후속 후보), 인용 줄 © 연도 범위·집행위원회 법적 고지 링크는 선택 사항, Commission Decision 2011/833/EU 본문은 EUR-Lex 챌린지로 못 읽어 사람이 확인하는 것이 안전.

### 남긴 것
- 병합 뒤 Actions의 첫 슬롯 실행에서 `소스 …` 줄과 글 끝 인용·고지문 관측(DEFECT_REGISTER 체크리스트 마지막 줄).
- 후보로 남긴 소스(Horizon·ECDC·NCSC·ONS 등)는 조건과 함께 분석 문서에 있다. Global Voices(AI 정책)는 운영자 결정(2026-10-26 채팅)으로 제외, GOV.UK(robots.txt의 `meta-externalagent` 는 `/search/all*` 만 막음)는 운영자가 사용을 결정해 이 PR 병합 뒤 후속 PR로 추가한다.
- 주말 공급 공백은 72시간으로 줄 뿐 없어지지 않는다 — 모든 분야가 비면 여전히 `ALL_LANES_EMPTY`(빨강)이다.

---

## [2026-10-26] Claude – 사이트 정리: 운영 문서를 사이트에서 빼고 홈 글 목록을 미리 그림 (운영자 승인 2026-10-26 "7. 진행", T3 광고 표면)

**작업자**: Claude  
**대상**: Chance_Blog  
**등급**: T3(광고 표면) — 운영자가 2026-10-26 채팅으로 승인 대기 7번에 "진행"이라고 답함(분석 `docs/analysis/2026-10-25_ai-search-exposure.md` 묶음 가, SIT-02·SIT-03·D-08)  
**목적**: 운영 문서가 사이트맵의 절반 가까이를 차지하고 홈은 JS 없이 열면 글 목록이 비는 문제를 줄인다. 저장소에는 아무것도 지우지 않는다.

### 한 일
- `_config.yml`: `exclude` 8개 항목 추가(운영 문서 6개 `AGENTS.md`·`AI_COLLAB.md`·`CLAUDE.md`·`GEMINI.md`·`HANDLER.md`·`WORKLOG.md`와 `docs/`·`인수인계/` — 운영자가 승인한 범위). 처음 구현은 코드·상태 파일(`generator.py`·`pipeline/`·`scripts/`·`tests/`·`history.json`·`pages.json`·`requirements-*.txt`·`README.md`)까지 20개를 넣었으나 독립 검증이 승인 범위 밖이라고 지적해 뺐고, 그 파일들을 정적 파일로 여는 것을 줄일지는 운영자 확인을 받는다(작업내용 §3 18번). 사이트가 쓰는 파일(`index.html`·about·contact·privacy·categories·`posts.json`·`feed.xml`·`robots.txt`·`assets/`·검색 인증 html)은 넣지 않았다.
- `index.html`: 글 목록 영역(`#post-grid`)에 Jekyll 반복문으로 최근 24편 카드를 미리 그리고, 요약 줄에 서버가 센 글 수를 넣고, 로딩 표시를 처음엔 숨기고, JS(`fetchPostList`)는 미리 그린 카드가 있으면 새 목록이 준비될 때까지 그대로 두며 가져오기에 실패해도 그 카드가 남게 했다. JS가 꺼진 방문자에게 쓸모없는 가로 이동 단추는 숨긴다. **광고 스크립트 줄(바이트 동일)·모달·방문 카운터·스타일은 건드리지 않았고, `<head>` 안 변경은 `<noscript><style>…</style></noscript>` 한 줄뿐이다**(변경은 6곳: head 1·요약 1·로딩 표시 1·글 목록 1·JS 2곳)(시험이 광고 코드 한 줄이 그대로임을 확인).
- `tests/test_site_cleanup.py` 새 시험: exclude 필수 항목·사이트가 쓰는 파일이 빠지지 않음(Jekyll 3.10의 앞부분 일치 규칙까지)·항목이 실제로 있음·**맨 위 모든 추적 파일이 내보냄/뺌/알려진 정적 파일 중 하나로 분류됨**(새 문서를 만들면 실패)·검증기 EXPOSE-1 해소·홈의 반복문과 카드 각 부분·JS 보존 로직·head의 noscript 한 줄·광고 코드와 구조 불변·Liquid 블록 짝.
- 검증: 시험 렌더 — python-liquid(저장소에 넣지 않은 임시 도구)로 `index.html`을 글 3편(이미지 없음·분류 없음·따옴표·`&` 포함)과 0편으로 렌더해 구문·이스케이프·폴백(분류 General)·광고 스크립트 1회를 확인했다. Ruby Liquid 와의 차이는 병합 뒤 실제 Pages 빌드로 확인한다(빌드가 실패해도 기존 사이트는 그대로 유지된다).

### 남긴 것
- 병합·배포 뒤 확인: 사이트맵에서 운영 문서 주소가 사라졌는지(44건 → 19건 예상), `…/HANDLER.md`·`…/docs/…` 같은 주소가 404가 됐는지(`generator.py`·`pipeline/…`는 승인 범위 밖이라 그대로 열려 있는 것이 정상), 홈 HTML(JS 없이 받은 것)에 글 링크 24개 이하가 들어 있는지, 홈을 JS로 열었을 때 서버가 그린 카드가 새 목록으로 **한 번 바뀌는 것**(카드 12장 → 카드 11장+추천 블록)은 정상이다. 모든 글 페이지·분류 페이지의 상단 메뉴에서 운영 문서 링크 25개가 사라진다(실제 Jekyll 빌드 비교로 확인).
- 되돌리려면 `_config.yml`의 `exclude` 블록과 `index.html`의 변경 6곳을 되돌린다(이 PR의 커밋들).
- **검증 기록**: ① 첫 검사는 AD-1(광고 표면 변경에 `Ad-Surface-Approved` 표기 없음)로 빨강이었고 표기를 담은 커밋을 더해 통과했다. ② 병합 전에 GitHub Pages와 같은 `actions/jekyll-build-pages`로 main과 PR을 각각 빌드해 견주었다(임시 브랜치, 배포 없음): 파일 157→106개(사라진 52개가 모두 운영 문서, 시험 파일 1개가 새로 생김 — 처음 20항목 구현은 157→28), 사이트맵 44→19건, 홈 카드 12장·링크 깨짐 0·광고 스크립트 1개, 달라진 페이지는 상단 메뉴의 운영 문서 링크가 빠진 글 12쪽과 분류 쪽. ③ 독립 검증 1회: 판정 "수정 후 병합"(코드 결함 없음) — 제외 범위를 승인 범위로 줄이고 "머리 부분 불변·변경 5곳" 문구를 정정(위 반영), 미리 그린 카드 판정을 `article` 선택자로, 승인 메모를 Liquid 주석으로, 시험 보강. 변경분 재검증(d0b0094) 1회: 코드·시험 문제 없음(변이 26건 중 설계상 못 잡는 2건만 생존), 지적한 PR 본문·D-08 상태·숫자·문구는 이 커밋에서 정정. 코드·상태 파일 제외는 운영자 승인("2. 추천대로")을 받아 후속 PR로 한다.

---

## [2026-10-26] Claude – Ars Technica·IEEE Spectrum 기술 소스 제외 (운영자 승인 2026-10-26, PR #31)

**작업자**: Claude (총괄이 구현, 검증은 별도 세션)  
**대상**: Chance_Blog  
**등급**: T3(신뢰 목록 변경, 공개 글 비공개 전환) — 운영자가 2026-10-26 채팅으로 승인("Ars·IEEE를 기술 소스에서 제외해줘(AI 크롤러를 막는 사이트는 접근하지 않는 원칙)", 이어서 "Ars·IEEE 출처로 공개된 글 3편(2026-10-19 Ars 1편, 2026-10-25 IEEE 1쌍)을 비공개로 전환해줘(삭제는 하지 말고)")  
**목적**: robots.txt가 AI 크롤러를 막는 두 사이트를 더 읽지 않는다. 같은 원칙을 남은 소스에 적용해 점검한다.

### 한 일
- `generator.py`: `NEWS_SOURCES`에서 Ars Technica·IEEE Spectrum 삭제, 기술 신뢰 목록에서 `arstechnica.com`·`ieee.org` 삭제, `TERMS_BLOCKED_DOMAINS`에 두 도메인 추가(신뢰 목록에 다시 들어와도 거부하고, 피드 호스트면 수집 루프가 읽지 않음). 기술 분야에는 전자신문만 남는다.
- `tests/test_generator_slots.py`: 소스 표·유예 목록(전자신문만)·차단 목록 정확 일치, 두 도메인(하위 도메인 포함)이 어느 분야에서도 신뢰되지 않음, 신뢰 목록에 실수로 다시 넣어도 거부. 변이 4개(`ieee.org`를 기술 신뢰 목록에 되돌림, 두 도메인을 각각 차단 목록에서 뺌, IEEE 소스를 되살림)가 모두 시험에 잡혔다. 전체 시험 1768개.
- 문서: ARCHITECTURE(기술 줄·차단 목록 항목)·DEFECT_REGISTER D-61·관측 체크리스트·SESSION_START(§5-2 브랜치 표, §6 14번 갱신과 15번 신설)·REQUEST_BRIEFING·HANDLER 0절·`인수인계/작업내용.md`.
- **비공개 전환 완료**(사용자 승인 2026-10-26 "Ars·IEEE 출처로 공개된 글 3편(2026-10-19 Ars 1편, 2026-10-25 IEEE 1쌍)을 비공개로 전환해줘(삭제는 하지 말고)"): 3개 글(`_posts/2026-10-19-AI.md`, `_posts/기술·미래/2026-10-25-KR-101307.md`, `_posts/Technology & Future/2026-10-25-EN-101307.md`)의 front matter에 `published: false` 한 줄씩(삭제 없음, PR #29의 4개 글과 같은 방식, 되돌리려면 그 줄만 지운다). `tests/test_verify_pages_select.py`의 공개 사이트 사본 표에서 이 3개를 `PUBLIC_SNAPSHOT`에서 `PUBLIC_MISSING`으로 옮겼다(4f981d7 기준 공개 글 13개 → 10개). 글 하나를 다시 공개로 돌리면 `test_exactly_the_posts_missing_from_the_public_site_are_unpublished`가 실패함을 확인했다.

### 같은 원칙으로 남은 소스 점검 (2026-10-26, robots.txt를 직접 읽음, 읽기 전용)
| 소스 | robots.txt | AI 크롤러 |
|------|-----------|-----------|
| NASA(www·science) | `User-agent: *`에 `Allow: /` | 막지 않음 |
| Pew Research Center | 일반 규칙은 관리자·플러그인 경로만 막고 `Content-Signal: ai-train=yes, search=yes, ai-input=yes`, robots.txt 주석이 `llms.txt`를 안내(직접 열어 보지는 못함) | 이용을 명시적으로 허용 |
| Federal Reserve | robots.txt 없음(두 가지 User-Agent로 읽어도 HTTP 404) | 제한 없음 |
| 전자신문(rss·www) | `Allow: /`, GPTBot 차단 줄은 주석 처리돼 있음 | 막지 않음 |
| UN News | 일반 봇에 `*/news/` 경로(이 피드 경로 포함)를 허용하지 않고 `Feedfetcher-Google`만 `/feed/subscribe/` 허용 | AI 크롤러 이름은 없음 — 이미 보류(`pending`, D-63) |

### 남긴 것
- 공개 사이트 반영 확인(배포 뒤 글 3편의 주소가 열리지 않고 `posts.json`·`feed.xml`에서 빠졌는지)은 병합 뒤에 한다.
- 기술 분야 글감이 전자신문 하나라 글감이 없는 날이 늘 수 있고 모든 분야가 비면 실행이 빨강(`ALL_LANES_EMPTY`)이 된다 → 같은 §6 14번.
- PR #30은 그동안 스쿼시로 병합됐다(c187c6d, 10:48). 이 브랜치가 품던 #30 원래 커밋과 이력이 달라 main을 합칠 때 9개 파일이 충돌했는데, main의 트리가 #30 끝 커밋(0a0ae84)의 트리에 봇 글 3개 파일만 더한 것임을 `git diff --stat 0a0ae84 origin/main`으로 확인하고 이 브랜치 쪽을 그대로 두었다(합친 뒤 main과의 차이는 PR #31의 13개 파일뿐).

### 병합과 관측(2026-10-26 오전)
- **검증 A 변경분 재검증 2회**(#30: b5a7609, 0a0ae84 / #31): 병합 차단 0. 2회 보고: #30 새 커밋 전체 시험 1771개·CI 3/3, 두 시점 코퍼스 고유 링크 316개 오탈락 0, `TECH_EN` 새 필터는 전자신문 표본에서 바뀐 제목이 정확히 1건(오늘 봇이 발행한 "빌 게이츠 “20년내 AI가…”", 옛 필터라면 `NOT_TECH`로 버려짐), 변이 136개(109+27) 중 99 사망·37 생존이며 지난번 의미 있던 15개는 모두 사망, 남은 생존(고지문 문구 8·영문 낱말 14·Pew 앵커 5)은 이 브랜치에서 시험으로 고정(변이 33개 모두 사망). #31: 변이 20개 중 19 사망(생존 1은 설계상 무해), 현재 main에 합친 모의에서 충돌 0.
- **9시 슬롯 정기 실행 #71**(10:13): 2026-10-26 10:13 KST 9시 슬롯 정기 실행 #71(main 4f981d7 상태): 분야 표가 과학 NASA(10건, EXCLUDED 6·AGE 4)·문화 Pew(100건, EXCLUDED 69·AGE 24·OFF_TOPIC 7)·경제 연준(20건, AGE 10·EXCLUDED 10)·기술 3곳(80건, 통과 5·후보 3, AGE 50·UNCHECKED 25)·사회·일상 0으로 기대와 같았고 `소스 UN News: 보류 — …` 줄이 찍혔으며 수집 실패는 없었다. 일상·마음에 후보가 없어 기술·미래로 넘어가 전자신문 출처 글 1쌍을 발행했고(`Gemini 호출: 2회(실패 1회, 5xx)`, 3.7→3.8 전달, 입력 3,662·출력 1,780 토큰), 봇 커밋 ecc95e5 → Pages 배포 → `사이트 반영 확인` 시도 1회·HTTP 200으로 통과했다.
- 같은 시각 연습 실행 #70(09:56, 저장 안 함·가짜 AI)에서 러너가 새 소스를 모두 읽는 것을 먼저 확인했다(Ars·IEEE는 전부 36시간 초과라 후보 0).
- **PR #31 병합**(11:02, 5d74970). 배포 #84가 통과했고 공개 사이트 확인(배포 #84 뒤): Ars·IEEE 출처 글 3개 주소가 정규 주소와 캐시 우회 주소 모두 404, `posts.json` 12건에서 3편이 빠지고(MIT TR·AI타임스 4개도 계속 없음) `feed.xml`·`sitemap.xml`에 이 글들이 없으며, 새 봇 글 쌍(10-26 KR/EN-101652)은 열린다. PR #31 병합 뒤 연습 실행 #72(2026-10-26 11:04 KST, main 5d74970, 저장 안 함·가짜 AI): 기술·미래 소스가 **1개(전자신문)**로 줄었고(Ars·IEEE는 읽지 않음) 30건 중 NOT_TECH 19·UNCHECKED 6·DUPLICATE 1, 검증 통과 5·후보 3이었다. 다른 분야는 전과 같았다(과학 NASA 10건 AGE 5·EXCLUDED 5, 문화 Pew 100건, 경제 연준 20건, 사회·일상 소스 0).

---
## [2026-10-26] Claude – Chance 출처 개편: 구글 뉴스 14개·MIT TR·BBC Technology 제거, NASA·Pew·Federal Reserve 추가(UN News 보류), AI타임스 차단, 약관 점검 필드·차단 목록·고지문 (운영자 승인 2026-10-26, PR #27)

**작업자**: Claude (총괄이 구현, 검증은 별도 세션)  
**대상**: Chance_Blog  
**등급**: T2(소스 개편 코드), 신뢰 목록·출처 정책은 T3 — 운영자가 2026-10-26 채팅으로 승인("Chance 출처 개편을 진행해줘: 구글 뉴스 14개 제거, NASA·UN News·Pew·Federal Reserve 추가, BBC·Guardian·Nature 제외, MIT TR·BBC Technology는 약관 점검 뒤 결정")  
**목적**: 비기술 5개 분야 후보가 0이던 원인(구글 뉴스 링크가 게시자 원문으로 풀리지 않음 — 14개 소스 통과율 0.4%, 신뢰 목록에 비기술 직접 소스 없음)을 없애고, 약관이 이 용도를 막는 매체를 더는 쓰지 않는다  

### 변경
- `generator.py`: `NEWS_SOURCES`에서 구글 뉴스 14개·MIT Technology Review·BBC Technology 삭제, NASA(과학)·Pew Research Center(문화)·Federal Reserve(경제) 추가, UN News(사회)는 조건이 남아 보류(`pending`)로 넣음, 기술 소스는 AI타임스(운영자 결정(2026-10-26 채팅: "금지된 부분이면 접근하지 않는다, 득보다 실이 많다")로 차단)·TechCrunch·The Verge·Hacker News(글감이 안 되거나 간접 경로)를 빼고 3곳(Ars Technica·IEEE Spectrum·전자신문)만 `terms: unverified` 유예. 신뢰 목록에서 BBC·Guardian·Nature·technologyreview.com 삭제, `TERMS_BLOCKED_DOMAINS`(+ `_trusted_domain` 거부)로 재유입 차단. 새 탈락 코드 `EXCLUDED`·`OFF_TOPIC`, 피드 분류 태그 읽기, 소스별 `exclude_title`·`topic_regex`·`no_page_fetch`·`notice`(글 끝 고지문)·`prompt_rule`(작성 지침 한 줄)
- 시험(`tests/test_generator_slots.py`): 소스 목록 불변식(약관 상태 선언·`unverified` 증가 금지·차단 도메인 부재·구글 뉴스 부재·분야별 소스), 소스별 제외·주제 규칙을 실제 피드 제목으로 고정, 제외·주제·페이지 읽기 금지·고지문·작성 지침 동작
- 문서: ARCHITECTURE(소스 표·탈락 코드), ACTIONS_GUIDE(코드표), DEFECT_REGISTER(D-60~D-63, 관측 체크리스트), SESSION_START·HANDLER·REQUEST_BRIEFING·작업요청 README(현황)

### 약관 점검 결과 (2026-10-26에 공식 약관을 직접 읽음, 법률 판단이 아님)
| 소스 | 읽은 곳 | 요지 | 결정 |
|------|---------|------|------|
| MIT Technology Review | 이용약관(2023-09-06판) — Copyright; Restrictions on Use·Commercial Use·General Access·AI and Large Language Model Usage | 복제·수정·재게시 금지, 상업적 이용·파생물 금지, 로봇·스크래퍼 금지, 콘텐츠로 AI 시스템을 만들거나 학습·개선하는 것은 사전 서면 동의, 허용은 건별 허가(서비스에 RSS 포함). 약관이 "등록 이용자"에게 적용된다고도 쓰여 있으나 저작권 문장은 일반적 | **제외**(운영자 위임 결정) |
| BBC(BBC Technology 포함) | 이용약관 v1.8(2022-09-19) §7(d)·§8·§15, 사업 이용 안내(2022-10-24 갱신) | RSS 사업 이용은 허가·수수료, RSS·콘텐츠의 메타데이터 가져오기 금지(BBC News RSS를 그대로 게시하는 것만 조건부 허용), AI 학습·컴퓨터 분석과 돈을 버는 이용은 허가 | **제외** |
| Guardian·Nature | 2026-10-25 진단 | 사전 승인 없는 상업적 이용 금지 등 | **제외**(운영자 지시) |
| NASA | 이미지·미디어 이용 안내(2026-08-13 갱신) | 미국에서 일반적으로 저작권 없음·NASA를 출처로 표기·제3자 자료와 로고는 별도. **AI 이용: AI 결과물의 정보를 NASA에 직접 귀속하는 것은 허용되지 않음("according to NASA" 같은 표현 금지), "AI 도구가 NASA 자료를 포함한다"고 밝히는 것은 가능, 검토·승인 암시 금지, NASA는 AI 결과물의 정확성에 책임지지 않음.** 출처 표기 규정과 직접 귀속 금지 규정이 충돌하며 AI 규정을 따르는 쪽으로 읽었다. 이 안내는 이미지·오디오·영상 중심이라 기사 글의 재사용은 일반적인 미국 정부 저작물 지위에 기댄다(이 페이지가 직접 말하지는 않음) | allowed + 작성 지침(코드로 막지 않음)·정확성 면책이 든 고지문 |
| UN News | UN News 이용 안내(날짜 없음), un.org 저작권 안내·media.un.org 저작권 이용 안내(날짜 없음), UN 이용약관, 권리·허가 안내, news.un.org robots.txt | UN News: "사용·소개·재가공 환영", UN News 표기와 링크, 사진·그래픽·오디오·영상은 저작권 준수. **"유엔에 알린다(the United Nations is advised)"는 조건은 UN News 안내가 아니라 un.org 저작권 안내와 media.un.org 안내에 있다.** 권리·허가 안내는 뉴스 센터 기사를 "전문·무편집"으로 게시할 때 환영한다 하고 UN 이용약관은 개인·비영리 이용과 파생물 금지를 기본으로 해 문서끼리 어긋난다. news.un.org robots.txt는 일반 봇에 `*/news/`를 허용하지 않아 피드 경로(`/feed/subscribe/en/news/all/rss.xml`)가 걸린다(구글 피드 수집기만 `/feed/subscribe/` 허용) | **보류(`pending`)** — 알림·서면 확인을 마치고 운영자가 확인하면 allowed(D-63) |
| Pew Research Center | 이용약관(2018-05-25 시행) §1~§4, robots.txt | §1: RSS·위젯·API로 얻은 콘텐츠의 판매·수정·파생물 제작까지 허락하되 정책·견해·지지를 Pew가 한 것처럼 암시하지 말고 §2 인용 형식("Report Title." Pew Research Center, Washington, D.C. (Publication date) URL.)으로 출처를 밝힐 것, 번역물에는 "has not reviewed or approved this translation" 문장을 넣을 것. §3: 허가 없는 스크래핑 금지. §4: Pew 상표 사용 불가. robots.txt는 `ai-input=yes` 신호 | allowed + 인용 줄·고지문(약관 문장 그대로)·작성 지침·기사 페이지를 읽지 않음 |
| Federal Reserve | 웹사이트 안내(2024-08-02 표시) | 정보는 공공 영역·출처를 밝힐 것, 제3자 자료·로고·휘장은 별도 | allowed + 고지문 |
| AI타임스(기존 소스) | 기사 페이지 하단 표기(직접 확인, 기사 3건), 저작권보호정책(날짜 없음), 이용약관 §9·§10 | **모든 기사 하단에 "무단전재 및 재배포, AI학습 및 활용 금지"**, 보호정책은 승낙 없는 복제·출판·전송·배포·판매·변형을 금지(허용 시 출처 표시), 피드의 `<copyright>`는 "All rights reserved" | **금지로 읽힘 → 운영자 결정(2026-10-26 채팅: "금지된 부분이면 접근하지 않는다, 득보다 실이 많다")으로 소스·신뢰 목록에서 빼고 `TERMS_BLOCKED_DOMAINS`에 올림.** 이 출처로 만든 공개 글 1쌍(2026-10-25-KR/EN-203740)은 D-60처럼 T3 결정 |
| 전자신문(기존 소스) | 이용약관(2012.09.01 표기) | 제공 정보의 영리 목적 이용 금지(회원 대상), 복제·전송·배포는 사전 승낙 필요. RSS·AI 이용 조항 없음. 이 피드(Section901)에는 해외 매체를 다시 쓴 기사도 섞여 권리가 한 겹 더 있다 | **불명확** — 유예(`unverified`) 유지, 허가 문의 추천 |
| TechCrunch·The Verge·Hacker News(기존) | TechCrunch RSS 이용약관은 직접 읽음, The Verge는 검증 세션 보고(직접 재확인 못 함) | TechCrunch: 피드 내용을 그대로 표시·출처와 링크 유지·변형과 피드 광고 금지(AI로 새 글을 쓰는 이용은 언급 없음). The Verge(Vox Media 이용약관 §15, 2026-07-06): 파생물·영리 이용 금지로 읽힘. Hacker News: 링크가 가는 매체의 약관이 적용되는 간접 경로 | **제거** — 신뢰 목록에 없어 글감이 한 건도 안 되는 TechCrunch·The Verge와 간접 경로 Hacker News(같은 원칙, D-61) |
| Ars Technica·IEEE Spectrum(기존) | 검증 세션 보고(직접 재확인 못 함) | Ars: robots.txt가 AI 크롤러를 막음, 이용약관은 읽지 못함. IEEE: 사이트 이용약관이 복제에 사전 서면 동의를 요구(일부 읽음), Spectrum 자체 RSS 약관은 못 찾음 | 미확인(유예) → 같은 날 운영자 결정으로 제외(PR #31) |

### 피드 실측 (2026-10-26 07:21 KST, 이 PC에서 읽기 전용)
| 피드 | 항목 | 36시간 안 | 7일 안 | 비고 |
|------|------|-----------|--------|------|
| NASA `nasa.gov/feed/` | 10 | 1(APOD, 제외 대상) | 10 | 항목 호스트 `science.nasa.gov`·`www.nasa.gov`, `/news-release/feed/`는 같은 내용 |
| UN News 전체 RSS | 30 | 1 | 30 | 요약 116~279자 |
| Pew `pewresearch.org/feed/` | 100 | 0 | 22 | 분류 태그가 풍부하고 선거·정치 비중이 크다. 퀴즈·보고서 부속 쪽(감사의 글·조사 방법)이 섞여 있다 |
| Federal Reserve `press_all.xml` | 20 | 0 | 0 | 가장 최근 항목이 9일 전, 요약 100자 미만 10건이나 기사 페이지 발췌로 모두 통과 |

주말 직후라 36시간 안 후보가 거의 없는 시점이다. 평일 공급은 병합 뒤 며칠 관측한다(D-62).

### 검증
- **L0**: `python scripts/validate_repo.py` 오류 0·경고 2(main과 동일), pyflakes 0, vermin 최소 3.7, `git diff --check`는 이 항목 머리 줄의 끝 공백 2칸(마크다운 줄바꿈, 기존 항목과 같음)만 지적한다.
- **L1**: `python -m unittest discover -s tests` 전체 1760개 통과(3차 수정과 AI타임스 제외 반영 뒤). 소켓을 막아도 `test_generator_slots.py` 통과.
- **L2**: `DRY_RUN=1 python generator.py`(스텁 AI, 실제 피드 읽기)를 로컬에서 실행 — 종료 0, 파일 변경 없음, 추첨된 일상·마음 분야는 `[SKIP] code=LANE_EMPTY sources=0`으로 건너뛰고 기술·미래로 대체(독립 검증자 실행). 작성자는 분야별 실피드 점검을 따로 했다.
- **L3**(실제 Gemini 초안): **실행 필요** — 이 환경에서는 Actions를 실행하지 않았다. 병합 뒤 첫 정기 실행에서 확인한다(`docs/DEFECT_REGISTER.md` 하단 체크리스트).
- **독립 검증 두 건**(각각 새 clone, 구현자 설명 미사용):
  - 코드·동작(검증 A): 병합 차단 0. 전체 시험 1740개(당시)·validate_repo 통과, 분야별 실피드 점검이 PR 표와 일치, 차단 도메인 7개·모조 호스트(`notbbc.co.uk`·`bbc.com.evil.example` 등)는 어느 분야에서도 신뢰되지 않음, 악성 피드 19항목을 5개 분야에 먹인 시험에서 새어 나간 것 0, 정규식 최악 0.064초(제목은 300자·분류 태그는 80자로 잘림), 변이 61개 중 43 사망·18 생존(생존분은 3차 수정에서 시험 보강), 범위(AST 비교: 바뀐 함수 8개뿐)·병합 모의 이상 없음(Blogger 브랜치와의 충돌 7개 파일은 그 브랜치의 낡은 기반 때문). 권장 8건·사소한 것 다수를 3차 수정에 반영.
  - 약관 사실(검증 B): MIT TR·BBC 제외 근거와 날짜·판 표기는 맞음. 정정 3건 — AI타임스 기사 하단의 "AI학습 및 활용 금지"(작성자도 직접 확인), UN "알린다(advised)" 조건의 출처와 robots.txt 제한(UN News 보류로 반영), Pew 인용 형식·번역 면책 문장·NASA 정확성 면책(고지문 보강).
- **2차·3차 수정**(검증 반영): 위 정정 + 제외 규칙 보강(Fed·NASA·Pew: 뉴스레터 모음·방법론 글·행사 안내·사진 설명), 글 언어 판정(front matter `lang` 우선), 직접 RSS `<source>` 태그 미사용, 시험 보강(모조 호스트·분야별 신뢰·차단 목록 고정·Pew 페이지 읽기 금지·소스 이름 유일·분야 배정 고정). 변경분(2·3차)은 검증 A가 다시 본다.

### 못 한 검증·관측 대기·다음 AI 주의사항
- **러너 IP에서의 피드 접근**은 병합 뒤 첫 실행에서만 확인된다(`수집 실패`가 보이면 그 소스만 건너뛴다). 이 PC에서는 4개 피드 모두 HTTP 200이었다.
- **미결정(T3, `docs/SESSION_START.md` §6 13·14번)**: 경제·일·일상·마음·사회 공급(신선도 창 완화 또는 소스 추가, D-62), 전자신문(약관 불명확) 허가 문의 또는 제외(D-61). **AI타임스는 운영자가 2026-10-26에 접근하지 않기로 결정해 뺐다.**
- **비공개 전환 완료**(사용자 승인 2026-10-26 "AI타임스(2026-10-25)·MIT TR(2026-10-21) 출처로 이미 공개된 글 2쌍을 비공개로 전환해줘(삭제는 하지 말고)", PR #29): 4개 글의 front matter에 `published: false` 한 줄씩(KR/EN 쌍 2개, 삭제 없음, 이미 숨겨 둔 10-18 글들과 같은 방식). 처음 CI가 빨강이었던 것은 `tests/test_verify_pages_select.py`의 공개 사이트 사본 표(`PUBLIC_SNAPSHOT`)에 MIT TR 쌍이 공개 글로 적혀 있어서였고, 그 두 줄을 `PUBLIC_MISSING`으로 옮겨 고쳤다. **확인(2026-10-26 09:19 KST)**: 병합 뒤 배포를 마친 공개 사이트에서 4개 주소가 모두 HTTP 404, 공개 `posts.json`은 13건(MIT TR·AI타임스 글 0건)이고 `feed.xml`에도 없다. 같은 날의 다른 글(10-25 10:13 쌍)은 200이다.
- **운영자 몫**: UN News에 이용 사실을 알리고 이 피드 경로를 읽어도 되는지 서면 확인 받기(unnews@un.org, D-63) — 그 뒤 `pending`을 `allowed`로 바꾼다.

### 병합과 후속(2026-10-26 09:22)
- **PR #27 병합**(4f981d7). 독립 검증 A의 변경분 재검증(8ef2a47 기준): **병합 차단 0**. 전체 시험 1760개·validate_repo 통과, 분야별 실피드 점검이 PR 표와 일치, AI타임스는 호스트 13가지 모양×6개 분야 어디에서도 신뢰·요청되지 않음(악성 피드 12종 포함), 모든 분야가 비면 종료 1(빨강)임을 확인, 새 변이 23개 중 18 사망, 앞선 목록까지 합쳐 105개 중 76 사망. 권장 8건·사소한 것 다수는 **후속 PR #30**에 반영(차단 도메인 피드는 수집 루프가 읽지 않음, 기사 주소 모양 검사, 전자신문 `tech_filter`, NASA 센터 소식 복구, Pew 인용 줄·제외 태그·고지문 시험 보강, 낡은 문서 줄 정리).
- **PR #29 병합**(740bf16): MIT TR·AI타임스 출처 공개 글 2쌍 비공개 전환(위 '비공개 전환 완료').
- 검증이 새로 짚은 위험(결정 거리, `docs/SESSION_START.md` §6 14번): 기술 분야 글감이 사실상 **전자신문 하나**(일반 뉴스 피드라 기술 제목만 쓰면 하루 약 14~16건), 주말 모의 재생에서 전자신문이 없으면 한 시점에 모든 분야가 비었다. Ars·IEEE는 robots.txt가 AI 관련 크롤러를 이름으로 막는다(검증 A 재집계: `Disallow: /` 대상이 Ars 34개 중 AI 관련 약 30개, IEEE 33개 중 약 21개이고 IEEE는 사용자 요청형 일부를 명시 허용 — 처음 보고된 12~13개는 출력을 잘라 센 과소 계수였다). 러너 IP에서의 피드 접근(특히 전자신문)은 병합 뒤 첫 실행에서만 확인된다.
- 이 PR이 하지 않은 것: 모델 목록(3.7 제거)·Blogger·사이트 정리·예약 틱 — 승인 대기 그대로. 구글 뉴스 해석 코드(`google` 키)는 쓰는 소스가 없지만 시험이 있어 남겼다.

---

## [2026-10-25] Claude – 총괄 하루 기록: 발행 복구 병합 총정리·진단과 AI 검색 노출 조사·확인 필요 모음 도입·세션 인수인계 문서 (운영자 승인 11건 반영, 총괄)

**작업자**: Claude (총괄 역할, 구현·검증은 별도 세션)  
**대상**: 공통  
**등급**: T0 (이 항목과 인수인계 문서·조사 보고서 보관은 문서). 병합된 개별 PR의 등급·검증은 각 PR 항목  
**목적**: 이 하루에 병합·관측·결정한 것 가운데 개별 PR 항목에 담기지 않는 것(병합 직후 Actions 관측, 간헐 실패 시험 수정, 진단·조사 요지, 승인 대기 목록, 새 세션 인수인계)을 한곳에 모은다. 새 세션은 이 항목 → `docs/SESSION_START.md` §5·§6 → `HANDLER.md` §0 순서로 읽으면 현재 상태를 잡을 수 있다

### 오늘 병합된 PR (main, 순서대로)
| PR | 내용 | 비고 |
|----|------|------|
| #11 | Chance 분야 폴백·건너뜀 사유 기록·종료 정책(D-03 완화) | 발행 복구 1/4 |
| #14 | 보안 설정(키 파일 무시 규칙·새 구글 키 형식 탐지·`mask()` 공용 패턴·CODEOWNERS) | 발행 복구 4/4, D-30·D-31 |
| #15 | 워치독 보강(하루 단위 판정·글 파일 기준 STALE·사이트 배포 점검·담당자 지정, 하루 2회) | 발행 복구 3/4, D-28 해결 |
| #16 | Blogger 가시화(시크릿 없음·정지·상한 건너뜀을 숨기지 않음) + `blogger_macat` 정지 | 발행 복구 2/4, D-25·D-26·D-32 |
| #17 | Actions 워크플로 한글 이름 + `chance-fix-images.yml` 분리 + 검증기 WF-11 | 운영 접근성 |
| #18 | 실제 git을 쓰는 이슈 수정 시험의 간헐 실패 방지, 시험이 Actions 요약·출력 파일에 쓰지 못하게 막음 | 아래 '시험 안정화' |
| #19 | 이슈 수정 시스템 하드닝 | D-37~D-40 |
| #20 | Pages 배포 뒤 공개 사이트 반영 확인(`사이트 반영 확인` 잡) | D-41, 3차 독립 검증 |
| #21 | 확인 필요 모음(이슈 1개 + 실행 요약) | 아래 '확인 필요 모음' |
| #23 | 확인 필요 모음 독립 검증 권장 수정 12건(워크플로 이름은 파일에서 읽음·본문 재작성 억제·포크 PR 제외·첫 이슈 생성 알림 유실·오류 줄 규칙·호출 상한 하한·본문 한도·워치독 계약 시험·문구) | 재검증 차단 0건, 변이 187개 중 169 사망(행동 틈 0) |
| #24 | **Gemini 호출 기록 + 수동 실행 기본값·정지 스위치**(`[GEMINI]` 로그·요약 `Gemini 호출: N회`, 연습 실행은 가짜 AI 응답·`real_ai`, Blogger 수동 `dry_run` 기본 켜짐, 이슈 수정 `PIPELINE_PAUSE`, 이미지 교체 20건 상한) | 독립 검증 2명 × (1차 + 변경분 재검증) 모두 병합 가능, 필수 수정 0, D-50~D-54 |
| #25 | 운영자용 Actions 사용 가이드 v2(`docs/ACTIONS_GUIDE.md`, 시나리오 16개) | 사실 검증 2회(대장 269건 틀림 0, 변경분 57건 틀림 0) |

병합 순서는 같은 문서·워크플로를 건드리는 PR끼리 충돌을 줄이려는 것이었고, 각 PR은 별도 세션의 독립 검증(새 clone, 구현자 설명 미사용)을 1~3차 거쳤다. 병합은 모두 스쿼시, 병합한 브랜치는 지우지 않았다.

### 병합 직후 Actions 관측(끝난 것)
- **워치독**: 병합 직후 수동 실행에서 열려 있던 이슈 #9·#10이 "조건이 해소되어" 자동으로 닫히고 새 심각 건은 없었다(실데이터 재생의 예상대로).
- **Blogger**: 정기 실행이 "대상 0개"로 초록 종료하고 `::notice::`가 남는다(정지 상태가 숨지 않음). 게시 대상인데 게시 Secrets가 없으면 이제 글을 만들기 전에 종료 2.
- **이름 변경**: 새 한글 이름 9개 확인, 연습 실행 2종(Chance 글·이미지 교체) 정상.
- **Pages 확인(#20)**: 병합 커밋의 배포에서 `사이트 반영 확인` 잡이 6초에 통과 — 시도 1회·경과 0초, 응답 `X-Cache MISS`·`Age 0`, 공개 `posts.json`의 `Last-Modified`가 방금 배포 시각(CDN이 배포 때 새 파일을 가져옴). **글이 추가된 첫 배포(20:37 KST, `2026-10-25-EN/KR-203740`)에서도 시도 1회·경과 0초·HTTP 200·`MISS`·`Age 0`**이었다 — 3차 검증 N3-1(첫 요청이 정규 주소에 404를 심는 경우)은 이 관측에서는 일어나지 않았다(표본: 글이 추가된 배포 1회, D-41 후속 판단은 더 쌓인 뒤).
- **Chance 18시 슬롯(복구 PR #11의 첫 실제 폴백)**: 15:09 KST 이후 예약 실행이 5시간 넘게 없다가 **20:34 KST 예약 실행(3분 53초)이 18시 슬롯 글을 발행**했다 — 요약 `PUBLISHED`, `'사회·정책' 분야에 후보가 없어 '기술·미래' 분야로 대체`, 제목 "가상 섬에 남겨진 AI는 왜 농구를 시작했을까…"(출처 AI타임스), **`Gemini 호출: 1회(실패 0회)`**. 분야 표: 사회·정책 12건 받아 0 통과(UNTRUSTED 9·AGE 3), 경제·일 58/0(UNTRUSTED 30·AGE 26·HOST_MISMATCH 2), 일상·마음 0건, 문화·미디어 1/0, 과학·환경 43/0(UNTRUSTED 25·AGE 18), 기술·미래 583건 중 10 통과·후보 3. **비기술 분야는 여전히 후보 0**(대부분 신뢰 목록 밖 게시자·36시간 초과) — 출처 개편(승인 대기 2번)의 근거. 오늘 글은 9시 슬롯(10:13 KST)과 이 18시 슬롯, 모두 2편.
- **운영자 직접 변경**: 20:26 KST 운영자가 `pipeline/blogs.json`의 `defaults.mode`를 `draft`→`auto`로 직접 바꿨다(커밋 c68d565, 검사 통과). 두 블로그 모두 자기 `mode`를 명시하므로(`chance` auto, `blogger_macat` off) **현재 동작은 그대로**이고, `mode`를 쓰지 않은 새 블로그만 곧바로 auto로 시작한다. 의도(예: Blogger 자동 발행)는 확인 요청 중 — Blogger는 `blogger_macat`의 `mode`가 off이고 Secrets 미등록·영문 프로필 전이라 이 줄로는 켜지지 않는다.
- **확인 필요 모음(#21·#23)**: 연습 실행(24초, 이슈·코멘트 없음, 요약 정상) → 실제 실행(39초)이 이슈 **#22**를 담당자 소유자·라벨 `ops-inbox`와 함께 만들었고 이슈 목록 맨 위에 고정했다. 첫 화면에는 독립 검증이 예고한 소음(옛 워크플로 이름이 이력에 섞임, F1)이 그대로 보였고, **후속 수정(#23) 병합 뒤 실제 실행**에서 플랫폼 줄의 워크플로 이름이 사라지고 이슈 본문이 한 번 갱신된 뒤, 곧바로 한 번 더 실행하면 **"변경 없음(이슈를 쓰지 않았습니다)"**으로 끝났다(본문 재작성 억제 확인). 지금 "해야 할 일 0건·참고 3건"(Blogger 정지, GitHub 플랫폼 경고, Chance 현황: 마지막 글 18시 슬롯, 최근 24시간 2건).

### 시험 안정화(#18, 개별 항목 없음)
PR #17 병합 직후 main의 `저장소 규칙·테스트 자동 검사`가 한 번 빨갛게 끝났다(실제 git을 쓰는 이슈 수정 시험이 `TemporaryDirectory` 정리 중 `OSError: [Errno 39] Directory not empty` — git 백그라운드 gc와 정리의 경합, 3.10 잡). 시험 안의 git에 `-c gc.auto=0 -c maintenance.auto=false`를 붙이고 정리 오류를 무시(`ignore_cleanup_errors=True`)해 고쳤다. 같은 조사에서 시험이 Actions의 실제 `GITHUB_STEP_SUMMARY`에 쓰던 문제(검사 실행 요약에 가짜 "워치독 CRITICAL STALE"이 찍힘)를 찾아 `tests/_bootstrap.py`가 `GITHUB_STEP_SUMMARY`·`GITHUB_OUTPUT`·`GITHUB_ENV`·`GITHUB_PATH`를 지우게 했다.

### 진단·조사 요지 (원문은 `docs/analysis/`)
- **발행 진단**(`2026-10-25_publish-readiness.md`, 비평 20건 정오표 포함): Chance는 11개 창 중 2개에서만 글이 나왔고(기술 분야만, 최장 공백 약 92시간). 기술 외 분야는 검증된 후보가 0건 — 구글 뉴스 링크가 발행처 주소로 풀리지 않고, 한국어 일반 매체 직접 RSS가 없고, 신뢰 목록이 빈약하고, 36시간 제한이 있다. BBC·Guardian·Nature는 약관상 이 용도가 막혀 보이고(법률 자문 아님) MIT TR·BBC Technology(현재 기술 분야 출처)도 제한이 있어 결정이 필요하다. Blogger는 시드 32개·같은 뼈대의 글, 건강 금지 주제 규칙이 약하다(제목·본문·수동 주제에 적용 안 됨). 무료 한도: 프로젝트 단위로 공유, 모델별 숫자는 AI Studio에서만 보임, 429에서 같은 모델 재시도로 호출 낭비, `gemini-3.7-flash`는 3.8로 자동 전달돼 중복 호출, 점검용 수동 실행이 실제 호출을 씀. GitHub 예약 실행은 매시 17분 틱의 약 22%만 돈다(48시간에 12/48, 간격 2.7~5.7시간).
- **AI 검색 노출 조사**(`2026-10-25_ai-search-exposure.md`): 네이버는 AI 봇을 robots.txt로 막아 외부 AI 앱에 적게 보이고, 노출→애드센스 수익의 직접 근거는 없다(AI 요약이 붙으면 클릭이 줄어드는 자료). 권고는 ①②③ 열린 웹 + 글마다 "이 글만의 가치", ④ 반자동(초안 자동·발행은 사람), 측정은 Search Console·Bing·Clarity·월 1회 휴대폰 점검. 사이트 격차: 15편 모두 기술·생활 설명형·장소 글 0편, 내부 문서 19개가 사이트맵의 46%, 홈 글 목록이 JS 전용, 광고 코드는 홈에만·`ads.txt` 없음·방침 문구와 불일치, AdSense 심사 대기.

### 병합 줄에 있던 PR과 독립 검증 결과(마감 시점 상태는 `docs/SESSION_START.md` §5-2가 정본)
- **호출 기록 + 수동 실행 기본값·정지 스위치**(통합 브랜치 `ai/claude/quota-guard`, **PR #24로 병합됨**): 독립 검증 2명이 각각 **조건부 병합 가능, 필수 수정 0**이었고, 권고 17건(일 한도 `quotaId` 상한·정렬 F-01, 기록 실패가 성공 응답을 잃지 않게 F-02, 마스킹 순서·키 치환·`project_number` F-03~F-06, 정지 코멘트에 `연습 실행` 체크 해제 안내 V-04, 문서·낡은 안내·시험 공백)을 반영한 수정 커밋 `d6ec336`을 두 검증자가 변경분만 다시 검증해 **병합 가능**(호출 기록: 차분 2만+1.2만 시나리오 불일치 0·정기 실행 스냅샷 동일·변이 64개 중 60 탐지; 기본값: **정기 실행 불변 1,210가지 열거 위반 0**·변이 누적 148개 중 141 탐지, 생존 7은 낮은 시험 공백). Linux CI(Python 3.10·3.12)에서 새 bash 시험도 통과. **병합 직후 관측**: 입력 없이 수동 실행하면 30초에 초록, `AI 응답: 가짜(스텁)`·`Gemini 호출: 0회`·`Unsplash 남은 호출: 49회`·새 커밋 없음. **병합 뒤 처음 도는 정기 실행은 아직 관측 전**(키가 안 넘어가 `GEMINI_API_KEY 환경 변수가 없습니다` 빨강이면 즉시 `git revert`).
- **Blogger 초안함 업로드 + 인증 점검만 실행**(`ai/claude/blogger-draft-upload` → `ai/claude/blogger-auth-check`): 독립 검증 **둘 다 조건부 병합 가능**(정지·시크릿 없음인 지금은 병합해도 Blogger 동작 그대로, 모드×시크릿×입력×실패 지점 열거·퍼징 약 2.7만 회에서 이유 없는 초록 0·시크릿 노출 0·명령 위조 0, 변이 C 151개 중 137·D 176개 중 163 탐지). **시크릿 등록·`mode: draft` 전환 전에 풀어야 할 지적**을 구현자가 반영(`a1f9d54`·`0f24ecd`): V-01 `_find_recent`가 소문자 열거값을 써 실제 구글 라이브러리에서 중복 확인이 조용히 꺼짐(대소문자 구분 엄격 가짜로 재현), V-02 글 ID가 남은 `publish_failed`가 하루 상한에 안 세어져 같은 날 재실행마다 초안이 쌓임, V-03 `isDraft=true` 응답에 `url`이 없을 수 있음(공식 문서에 설명 없음, 초안은 id만으로 성공 처리), V-04 업로드 직후 이력 쓰기 실패 시 고아 초안, V-10 프로젝트 번호 노출, V-14 400/403 분류, 새 레지스트리 검증 `REG-1`(블로그 항목은 `mode`를 직접 적어야 함 — `defaults.mode`가 auto인 지금 새 블로그 사고 방지). 변이 122개 전부 탐지. **변경분 재검증(2차) 결과: 둘 다 병합 가능**(열거·퍼징 위반 0, 새 변이 86개 중 85 탐지, 전체 953·981개 통과). 호출 기록 통합 브랜치(#24)가 병합된 지금 통합 단계가 남았다: `pipeline/run.py` 3줄(`mask` import 제거, 옮겨진 주제 선정을 `with purpose(llm,"topic-expansion"):`로 감쌈, 성공 요약 앞 `lines += [f"- {line}" for line in ai_lines()]`), `blogger.yml`(`publish` choice 유지), `DEFECT_REGISTER`(D-49는 한 줄만), `tests/test_workflow_names.py` ALLOWED_REFS 합집합, `tests/test_manual_run_defaults.py` 4건(문구·`publish` 3택에 맞춤) — 코드 변경 없이 문구·시험만. 작은 후속: 파일만 쓰는 실행에서 이력 쓰기 실패 문구가 "올라갔을 수 있다"고 안내하는 점(N-3), REG-1 메시지("새 블로그는 off 로 시작")와 ARCHITECTURE 예시(`draft`) 통일(N-4), `docs/REQUEST_BRIEFING.md`의 `draft` 설명 4곳은 이 인수인계 PR의 v3에서 이미 고침.
- **Actions 가이드 v2**(`ai/claude/actions-guide-v2`, **PR #25로 병합됨**): 사실 검증 1차 — 대장 269건 중 **틀림 0**(맞음 258·근거부족 6·모호 5), 마커 변형 8종 검증기 오류 0, 병합 전 필수 M1~M7(일시정지 순서, 알림·보안 메뉴 이름, `ai/…` PR 병합 기준, Blogger 시크릿 단계 한정, 이슈 #22 사실, 마커 밖 문장)과 대장 밖 오류 8건을 반영. 2차(변경분 57개 주장) **틀림 0**, 낮음 6건과 호출 기록 수정에 맞춘 두 문장은 총괄이 반영. `quota` 마커는 걷어 현재 사실로 통합했고 **`blogger-draft`·`blogger-auth` 마커는 남아 있다** — Blogger 두 PR이 병합될 때 걷고 문장을 정리한다(검증자 목록: 3-12 시크릿 단계의 "있을 때만" 한정 문구 삭제, `defaults.mode` 문장을 "줄이 없으면 검증기(REG-1)가 오류로 막습니다"로 교체, `BLOGGER_API_SETUP.md` 날짜 중립 문장 정리, `draft_uploaded` 통합, 마지막 마커를 걷을 때 "먼저 읽기 3" 안내 삭제, 인증 점검만 실행의 "(정지 중에도 점검하는 예외)").

### 승인 대기(운영자 채팅 승인 필요, 아직 답 없음) — `docs/SESSION_START.md` §6 표가 정본
1 `gemini-3.7-flash` 제거(T3) · 2 Chance 출처 개편(T3) · 3 Blogger 건강 금지 강화(T1, 알림) · 4 초안함 API 업로드 방식 · 5 macat0722 영문 프로필(T3) · 6 모드는 draft까지(T3) · 7 사이트 정리 2건(T3 광고 표면) · 8 워치독 하루 2회 유지 · 9 크론 틱 추가와 오늘 18시 글 수동 발행 · 10 로컬 작업 문서를 공개 저장소에 보관해도 되는지. **9번의 배경**: 수동 실행은 `slot=None` 글이라 같은 날 예약 실행이 또 만들 수 있어(하루 3편 가능) 승인 없이 수동 발행하지 않았다. 오늘 18시 창은 예약 실행이 5시간 넘게 빠졌다가 20:34 KST에야 돌아 글이 나왔다(창이 18~23시라 이번에는 늦게라도 만들어졌지만, 창 안에 한 번도 안 돌면 그 창은 건너뛴다 — D-59).

### 오늘 반영 상태와 인수인계
- 새 세션 시작·마감 절차와 현재 상태는 `docs/SESSION_START.md`(신설)에, 모바일 Claude용 브리핑은 `docs/REQUEST_BRIEFING.md` v3에, 작업요청 처리 현황은 `인수인계/작업요청/README.md`에 있다. `HANDLER.md`·`AGENTS.md`는 SESSION_START를 가리킨다.
- 로컬에만 있는 운영자 문서(작업요청서 3종·계획서·진단 요약)는 저장소에 올리지 않았다(공개 저장소, 운영자 허락 대기 — 승인 대기 10번).

### 다음 AI에게 남기는 주의사항
1. 진행 중인 PR·브랜치와 순서는 `docs/SESSION_START.md` §5(열린 것은 Blogger 두 브랜치뿐, 통합 단계). 열린 브랜치를 병합할 때 충돌(특히 `pipeline/run.py`·`blogger.yml`·`docs/ARCHITECTURE.md`·`docs/DEFECT_REGISTER.md`·`tests/test_workflow_names.py`)은 **뒤에 병합하는 쪽이 자기 코드를 새 기반에 맞춰** 푼다.
2. 병합 직후에는 항상 Actions를 본다(문서에 쓴 관측 체크리스트 `docs/DEFECT_REGISTER.md` 하단). 특히 확인 필요 모음의 정기 실행 간격과 첫 @멘션 코멘트, 글이 추가된 배포의 `사이트 반영 확인` 시도 1(오늘 1회는 정상), Chance 슬롯 실행 요약의 분야 표.
3. **승인 없이 하지 않는 일**: 수동 실제 게시(하루 3편 가능), 모델·소스 목록 변경, 정지 블로그 켜기, 크론·호출 증가, 사이트 광고 표면, Secrets 등록, 로컬 문서의 공개 저장소 보관.
4. 새 결함 번호는 D-60부터(D-55~D-57은 Blogger 초안 업로드·인증 점검 브랜치가 병합될 때 들어오고, D-58·D-59는 이 항목과 같은 PR에서 등록).

---

## [2026-10-25] Claude – Pages 배포 후 공개 반영 확인 잡(verify)과 독립 검증 지적 반영 (발행 복구, PR-6)

**작업자**: Claude (구현 담당)  
**대상**: Chance_Blog  
**등급**: T2 (`pages.yml` 변경). 독립 검증 1차(별도 세션, 새 clone): 조건부 병합 가능 → 지적 F-01~F-12를 이 브랜치에서 반영했다. 2차(별도 세션): 조건부 병합 가능 → N-3(이름 한글화 병합 충돌·이름 네 곳)·N-1(CDN의 404 보관에 대한 재시도 설계)·N-2·N-4·N-6·N-7·N-8을 반영했다(N-5·N-9는 하지 않음). 3차(별도 세션, 2차 반영분 확인): 조건부 병합 가능 — 필수 수정은 없고, 권고 N3-1~N3-5는 병합 뒤 첫 배포 관측으로 판단하기로 했다(D-41)  
**목적**: Pages 배포 워크플로가 초록이어도 새 글이 공개 사이트에서 열린다는 보장은 없다. 배포 뒤에 새 글의 공개 주소가 열리는지 확인하고, 안 열리면 배포 실행을 빨갛게 해 워치독이 알리게 한다(운영자 승인 계획의 PR-6, D-41)

### 변경 사항
- **`pages.yml`**: `deploy` 뒤에 `verify` 잡(`사이트 반영 확인`, `needs: deploy`, `contents: read`, **timeout 15분**). checkout(`저장소 내려받기`)은 `persist-credentials: false`, 실행은 `python3 -u`, 배포 주소는 env로만 넘긴다(`run`에 직접 보간 없음). 잡·단계 이름은 이름 한글화 PR(#17, WF-11) 병합 뒤 한글로 붙였다(2차 N-3). 주석의 결함 번호는 D-37 → D-41이고, 주석은 새 재시도 설계(요청 모양을 바꾸고 대기를 늘림)를 설명한다
- **`scripts/verify_pages_deploy.py`**(표준 라이브러리만. 종료 0 반영 확인·건너뜀 / 1 반영 안 됨·검사 중단 / 2 설정 오류):
  - **확인할 글(F-01)**: 저장소 `_posts`의 가장 새 글 쌍 중 사이트에 올라올 것만. front matter의 `published: false`(`False`·`no`·`off`·`null`·빈 값·따옴표 친 값 포함)와 미래 `date`(Jekyll `future: false`)는 제외하고 그다음 새 글을 본다. 전부 제외되면 건너뜀(초록, 요약에 이유). front matter는 PyYAML 없이 줄 단위로 읽는다(`published`·`date`·`permalink`·`slug`만)
  - **주소(F-02)**: `_config.yml` `permalink`(`:year :month :day :title`만)와 파일명, 글 자신의 front matter로 계산한 공개 주소가 HTTP 200으로 열리는지 본다. 계산할 수 없으면 공개 `posts.json`의 `absoluteUrl`(같은 출처 https만)을 쓴다. `posts.json`은 보조 정보(같은 주소로 실렸는지, 다르면 경고)이며 낡았다는 이유로 실패시키지 않는다. 계산한 주소가 안 열려도 `posts.json`이 알려 준 주소가 열리면 그 주소로 통과시키고 경고를 남긴다(주소 계산이 틀렸을 때의 안전망 — 명세 밖 추가)
  - **재시도·마감(F-02c·F-05, 2차 N-1·N-6)**: `--deadline` 720초(기본)까지 확인한다. 대기는 `--interval` 10초에서 시작해 2배씩 늘어(10·20·40·80·160·160…) 기본값이면 시도는 0·10·30·70·150·310·470·630초 부근 8번이고, 다음 시도가 마감 뒤에 시작하게 되면 그만둔다(마지막 시도 뒤 약 90초는 보지 않는다). 마감 뒤에는 새 시도도 새 요청도 시작하지 않는다(첫 시도는 마감과 무관하게 끝까지). **시도마다 요청 모양을 바꾼다**(`SHAPES` 10가지): 정규 주소 → 끝에 `index.html` → `Accept-Encoding: gzip` → `deflate` → 첫·둘째 구간 뒤 `//` → 끝 `//` → `./` → `index.html`+gzip·deflate. 이유: 공개 CDN이 404도 보관해(아래 관측) 같은 주소·같은 모양의 재시도는 첫 요청이 남긴 404를 마감까지 계속 받는다. 요청 하나는 소켓 연산별 15초에 더해 전체 30초 상한(작업 스레드로 끊음)이고, 글 주소는 상태만 보므로 본문을 읽지 않는다
  - **오류(F-03)**: 연결·프로토콜·주소 형식 오류(`IncompleteRead`·`BadStatusLine`·`InvalidURL`·`UnicodeEncodeError` 등)는 예외가 아니라 상태 0으로 처리한다. 시도 안의 예상 못 한 예외는 그 시도의 문제로 기록하고 재시도, 검사 자체가 멈추면 `::error::`와 요약을 남기고 종료 1
  - **출력(F-04·F-06·F-09)**: `fold()`가 줄 머리 `::`를 `→ `로, `##[`를 `# [`로 막는다. 모든 로그 줄을 즉시 flush하고, 최종 요약은 한 번만 쓴다. 요약의 주소·이름은 코드 스팬이다. `_posts` 폴더가 없으면 종료 2(F-08)
  - **실패 요약(F-02d, 2차 N-2)**: 시도 기록(시도별 경과 초·요청 모양·상태), 마지막 응답의 상태·`X-Cache`·`Age`·`Last-Modified`와 해석. 해석은 `Age`를 이 검사의 경과 시간(+5초 여유)과 견준다: 이내면 '이 검사가 앞서 보낸 요청이 남긴 404'(캐시 때문에 늦은 것인지 아직 안 올라온 것인지 가를 수 없음), 더 크면 '검사 전부터 CDN이 들고 있던 응답', `MISS`·`Age` 0이면 '원본이 직접 준 404'. 첫 시도(정규 주소)가 404였다가 다른 모양으로 통과하면 독자에게는 정규 주소가 보관이 끝날 때까지 404일 수 있다는 경고를 남긴다
- **Jekyll 규칙은 소스를 읽어 맞췄다**(Jekyll 3.10.0·SafeYAML 소스. 실제 빌드가 쓰는 Jekyll 버전은 확인하지 못했다): `false`·`no`·`off`·`null`·빈 값은 대소문자와 무관하게 비공개, 따옴표 친 값은 문자열(공개), 시간대 없이 초까지 있는 `date`는 UTC, 날짜 자리표시자는 `Time.parse(...).localtime`(사이트 시간대), `:title`은 slugify(pretty), URL 정리는 `..`→`/`·`./` 삭제·연속 슬래시 접기. **실제 `_posts` 20건 중 공개 15건의 주소가 공개 `posts.json`의 `absoluteUrl`과 모두 일치**한다(그중 2건은 글 자신의 `permalink:` — 파일명만으로는 틀린다). 비공개 5건은 공개 목록에 없는 5건과 같다 키 모양(2차 N-4): `"published": false`·`'published': false`·`published : false`처럼 키를 따옴표로 감싸거나 콜론 앞에 공백을 둬도 같은 키로 읽는다(Jekyll도 그 글을 비공개로 본다). 알려진 차이(한계): 따옴표 친 `date: "… HH:MM:SS"`는 Jekyll이 `Time.parse`로 사이트 시간대(`ENV["TZ"]`)로 읽지만 이 스크립트는 따옴표 여부를 구별하지 않고 초까지 있는 시각을 UTC로 읽는다(`Asia/Seoul`이면 미래 판정이 9시간 어긋남. 이 저장소 글 중 `date:`가 있는 4건은 `+0900` 표기 형식이고 나머지는 `date:`가 없다). `:title`(slug)의 결합 문자(Mark) 등 일부 유니코드 범주는 Jekyll과 다를 수 있다(N-5, 고치지 않음 — 한글·영문 slug에는 영향이 없다)
- **테스트**: `tests/test_verify_pages_deploy.py`(요청·재시도·마감·요약·종료 코드·워크플로·요청 모양·CDN 모델 재현), `tests/test_verify_pages_select.py`(글 선정·주소 계산·실제 저장소 대조), `tests/verify_pages_helpers.py`(가상 시계·가짜 사이트·**가짜 CDN** — 캐시 키·404 보관을 검증자의 실측대로 흉내). 25개 → **218개**(1차 반영 뒤 163개 + 2차 55개). 가상 시계에는 잠든 횟수 상한(500)이 있어 마감 계산이 틀려도 끝없이 돌지 않고 바로 실패한다. 실제 시간을 쓰는 테스트는 요청 전체 상한 하나(0.05초 대기)뿐이다
- **문서**: ARCHITECTURE Deploy 행·§4-3, DEFECT_REGISTER D-41·관측 체크리스트, HANDLER §0(2차 검증 뒤 요청 모양·404 보관 약 18분·한계로 갱신)
- **실패 요약 문구**: 404도 CDN이 보관한다는 관측에 따라 해석 문구를 바꿨다(위 '실패 요약'). 판정 로직(HTTP 200)은 그대로다

### 검증 증거
- `python scripts/validate_repo.py`: 오류 0, 경고 2(LIQUID-1 인수인계 문서, EXPOSE-1 — main과 동일). `actionlint` 1.7.12: 저장소 워크플로 전체 0건. `pyflakes`: 새·변경 py 4개 0건. `vermin --target=3.10-`: 최소 3.7(3.10 호환)
- `python -m unittest discover -s tests`: **1051개 통과**(최신 main `5bf2fc9`를 병합한 상태: main 833개 + 이 PR의 새 테스트 218개. 병합 전 `c00eb4f` 기준으로는 848개). 새 테스트 두 모듈 218개는 **모든 소켓·DNS를 막은 상태**에서도 통과(네트워크 시도 0). Windows, Python 3.12
- **표적 변이**(스크래치 하네스, 변이본을 최소 복사본에 쓰고 원본 해시 복원 확인): 1차 반영 때 181개(검출 181/181)였고, 2차에서 코드가 바뀌어 맞지 않게 된 23개를 새 코드에 맞춰 다시 만들고 95개를 더해 **276개**를 돌렸다 — 요청 모양 24·지수 대기와 상수 11·요청 상한과 본문 생략 8·해석과 경고 14·시도 기록 12·front matter 키 모양 8·fold 지점 11(검증자의 생존 변이 X01~X11 대응)·워크플로 이름·버전 5·그 밖 2. 첫 실행은 **274 검출 / 2 생존**(해석의 Age 비교를 최댓값 대신 최솟값으로 바꾼 것, `X-Cache: HIT`의 대소문자 구분 — 둘 다 테스트 공백)이었고 테스트를 보강한 뒤 다시 전부 돌려 **276 검출 / 0 생존 / 미적용 0**(원본 해시 복원 확인)이다. 검증자가 살아남았다고 한 변이 중 fold 지점 7개(X01~X04·X06·X07·X11)·경고 줄(Y15)·로그 경과 표기(V16)·안전망 요청 토큰(P16)·checkout 버전(W14)은 대응 테스트를 추가해 검출을 확인했다
- **루프백 점검**(저장소 밖, 외부 접속 없음): 1차에서 검증자가 재현한 F-03 항목이 새 코드(요청을 작업 스레드로 감쌈)에서도 모두 예외 없이 상태 0으로 처리됨 — 잘린 chunked(`IncompleteRead`), 쓰레기 상태줄(`BadStatusLine`), 개행·공백 URL(`InvalidURL`), 비ASCII URL(`UnicodeEncodeError`), `posts.json`의 `path`가 리스트·깊은 중첩. 2차 확인: ① 에코 서버로 모양마다 실제 전송을 확인 — `//`·`./`·`index.html` 경로가 정규화 없이 그대로 가고 `Accept-Encoding`은 기본 `identity`, gzip·deflate 모양은 그 값이 감 ② 헤더를 1바이트씩 20초 동안 보내는 서버에 `total=3`을 주면 3.0초에 `TotalTimeout`(소켓 제한 15초는 걸리지 않음) ③ `limit=0`은 3MiB 본문을 읽지 않고 `limit=1000`은 1001바이트를 읽음 ④ 5초 뒤 공개되는 가짜 사이트를 마감 20초·첫 대기 2초로 돌리면 3번째 시도(6초, `Accept-Encoding: gzip`)에서 통과하고 시도 기록·경고가 요약에 남음, 계속 404면 마감 안에서 종료 1
- **가상 시계 최악 시간**(마감 720초·첫 대기 10초·요청 상한 30초, 2차에서 다시 계산): 정상 실패(404, 0.4초/요청) 끝 639.6초(8번째 시도가 638.4초에 시작, 다음은 639.6 + 160 ≥ 720이라 시작하지 않음), 모든 요청이 상한 30초까지 걸려 시간초과 끝 600.0초, 같은 시각 글 12건(상한 10건)이 모두 시간초과여도 끝 720.0초(마지막 요청 시작 690초), 14초씩 느린 응답 끝 562.0초. 최악 공식: 마감 720초 + 마지막 요청 1건과 성공 뒤 목록 읽기 1건(각 30초) + 준비 시간 120초 = 900초 = 잡 제한 900초(테스트는 `<=`라 통과하지만 여유가 0이다 — 실제 준비 시간은 120초보다 훨씬 짧다)
- **진행 로그 즉시 출력**: 파이프 stdout에서 시도 줄이 2초 간격으로 도착(플래그 없음 1.5/3.5/5.6초, `python -u` 0.6/2.6/4.7초 — 옛 코드는 종료 때 한꺼번에 나왔다)
- **실제 저장소 + 공개 사이트 사본**으로 `verify()` 전 과정: 그대로는 1회 통과, 가장 새 쌍을 `published: false`로 바꾸면 그다음 쌍(2026-10-21)으로 통과, 전부 비공개면 건너뜀 (2차 변경 뒤 다시 돌려 같은 결과)
- **실제 공개 사이트 관측**(읽기 전용 GET, 저장소·사이트는 건드리지 않음): ① 1차 때: 새 스크립트를 한 번 돌려 가장 새 쌍(2026-10-25)이 HTTP 200으로 열리고(`Age` 252·281, `Last-Modified` 06:35:46 GMT) `posts.json`에 같은 주소로 실린 것을 확인했다(종료 0). 사이트에 없는 글을 가정하면 404(`Age 0`)와 종료 1이었다. 공개 `posts.json`의 `Last-Modified`는 배포 때 새 빌드 시각으로 바뀌었다(관측: 01:13:51 → 06:35:46 GMT). ② **404도 CDN이 보관한다**: 404 응답에는 `Cache-Control`이 없었고, 같은 주소가 쿼리를 바꿔도 `X-Cache: HIT`에 계속 늘어나는 `Age`로 돌아왔다. 보관 시간은 **최대 약 18분**이다(2차 독립 검증 1회 측정: `Age` 963~1078초까지 HIT, 약 1114초에 MISS). 1차 때 내 관측은 한 객체가 마지막 표본인 `Age` 497초까지 HIT였고 나머지 둘은 136~266초에 새 객체로 바뀌어 차이가 있다 — **보관 시간은 불확실**하다(그래서 마감을 늘려 기다리는 설계를 버리고 시도마다 요청 모양을 바꾼다). ③ 2차(2026-10-25 08:49 UTC): 기존 글 한 건(`2026/10/19/EN-103939/`)에 10가지 모양을 한 번씩 요청해 **모두 HTTP 200·`X-Cache: MISS`·`Age 0`**(gzip 모양은 `Content-Encoding: gzip`), 없는 주소(2099년)에는 10가지 모두 **404·MISS**(어떤 모양도 없는 글을 200으로 만들지 않음), 같은 모양을 24~29초 뒤 다시 요청하면 404 **`HIT`·`Age` 23~29**(같은 키는 보관된 404를 돌려줌). 새 스크립트를 실제 저장소·실제 사이트로 돌리면 시도 1(정규 주소)에서 가장 새 쌍이 200으로 열리고 종료 0이었다(요약에 `X-Cache`·`Age`가 보임)
- **독립 검증 결과 요지**(1차, 2026-10-25, `fceb7b7`): 조건부 병합 가능. 지적 F-01(필수: 가장 새 쌍이 `published: false`면 정상 사이트인데 빨강)·F-02(쿼리·no-cache로 CDN을 못 피함: `max-age=600`, X-Cache HIT)·F-03(예외가 트레이스백으로 종료)·F-04(`::` 보호 무효)·F-05(전체 마감 없음, 최악 874~2070초)·F-06(파이프 버퍼링)·F-07(워치독 문구·취소된 실행)·F-08(`_posts` 없으면 fail-open)·F-09(다른 출처 주소)·F-10(변이 106개 중 36개 생존)·F-11(문구)·F-12(`persist-credentials`). F-07을 뺀 11건을 이 브랜치에서 고쳤다
- **독립 검증 결과 요지**(2차, 2026-10-25): 조건부 병합 가능. 병합 필수 N-3(main `c00eb4f`의 PR #17과 충돌 3곳, `verify` 잡·단계·점검표·요약 문구의 옛 영문 이름 네 곳) → 병합하고 고쳤다. N-1(검증자가 이 사이트의 CDN이 없는 주소의 404를 약 18분 보관하고 쿼리·`no-cache`·`Pragma`를 무시함을 측정 → 첫 요청이 404를 받으면 30초 간격 재시도가 같은 객체를 읽어 마감에 빨강) → 요청 모양 회전 + 지수 대기로 고쳤다. N-2(해석이 늘 '캐시 지연')·N-4(`published : false` 등 키 모양)·N-6(본문 읽기·요청 전체 상한)·N-7(fold 지점 등 테스트 공백)·N-8(문서의 404 보관 수치) 반영. 하지 않은 것: N-5(slug의 Mark/Nl 정렬 — D-41·모듈 설명에 한계로만 기록), N-9(총괄 지시로 제외)
- **독립 검증 결과 요지**(3차, 2026-10-25, `c2aa5f4`, 새 clone, 구현자 설명 미사용): **조건부 병합 가능**. main `5bf2fc9`가 브랜치의 조상이라 병합 충돌이 없고, 전체 1051개가 소켓을 막은 상태에서 통과(네트워크 시도 0), validate 오류 0·경고 2(LIQUID-1, EXPOSE-1), actionlint·pyflakes 0건, vermin 최소 3.7. **2차 지적 해소 확인**: N-1 — 10가지 요청 모양이 없는 주소에서 10/10이 서로 다른 캐시 키(첫 요청 404·MISS, 같은 모양 재요청 HIT)이고 존재하는 글에서 10/10이 HTTP 200이며, 실제 `verify()`를 검증자의 CDN 모델에 돌리면 글이 -10·0·5·20·40·100·300·400·600초에 열릴 때 시도 1·1·2·3·4·5·6·7·8회에 통과하고 900초에 열리면 빨강(구현자 표와 일치). N-6 — 요청 전체 30초 상한·daemon 스레드·작업 스레드가 소켓에 막힌 채여도 프로세스가 1.4초에 종료, 글 주소는 `limit 0`이라 헤더만 읽음. N-4 — `published : false`·`"published": false`·`'published': false` 3가지가 비공개로 읽힘(Jekyll과 일치). N-3 — 잡·단계 이름 한글(WF-11 경고 없음). **최악 시간**: 가상 시계 800가지(글 1~10건 × 요청 지연 0.4~30초 × `posts.json` 지연 × 열리는 시각 × 안전망 유무)에서 최대 끝 시각 770초, 우리 공식 900초는 상한이다 — 준비 시간이 130초를 넘지 않는 한 요약을 쓰기 전에 잡이 죽지 않으므로 `timeout-minutes` 15분을 유지한다. **독립 변이 97개 중 94개 검출, 생존 3**(작업 스레드 `daemon=False`, 첫 시도 404 경고를 '시도 2'로 바꿈, 글 두 건 중 한 건만 404일 때의 `any`→`all`). **새 지적**: N3-1(중간, 병합 전 권고) 첫 시도가 항상 정규 주소를 먼저 요청해 전파가 늦은 배포 직후라면 그 요청이 독자용 주소에 404를 심어 최대 약 18분 독자가 404를 볼 수 있다(요약 경고가 이를 인정함) — 제안: 독자가 안 쓰는 모양(`index.html`·`//`·`./`)을 먼저 보내고 정규 주소(와 gzip·deflate)는 그것이 200을 받은 뒤에 요청. N3-2 생존 변이 3개의 테스트 공백. N3-3 작은 `--interval`(5 이하)이나 쓸 수 있는 모양이 적은 주소(짧은 경로 8가지, `.html` permalink 6가지)는 기본 창 안에서 모양이 한 바퀴를 넘어 허용 지연이 줄고(interval 5에서 열리는 시각 600초가 빨강), 모듈 설명의 "8번째 시도 다음 처음 모양으로 돌아간다"는 모양 10가지·시도 8회와 맞지 않는다. N3-4 정규 주소를 못 연 채 다른 모양으로 통과해도 요약 머리 줄이 '새 글 주소가 열림(HTTP 200)'이라 쓴다(경고는 뒤에 있음). N3-5 시험의 최악 공식이 상한이라 시험상 여유가 0.
- **총괄 판단(3차 이후)**: N3-1~N3-5는 **이번 병합 전에 고치지 않는다.** 필수가 아니고, 신규 글 배포 직후 첫 요청이 실제로 404인 빈도를 아직 모르며(요청 모양 순서를 바꾸면 이 PR의 테스트 218개와 요약 문구가 함께 바뀌어 재검증이 한 번 더 필요하다), 오늘 밤 병합 줄이 길다. 병합 뒤 글이 추가된 첫 배포의 시도 기록(시도 1이 404였는지, `X-Cache`·`Age`)이 근거다 — 늘 시도 1에서 열리면 N3-1은 실제로 일어나지 않는 것이고, 404였다면 N3-1·N3-4를 고치는 후속 PR을 낸다. 이 판단은 D-41 항목의 "3차 잔여"에 적었다
- **실행하지 못한 것(실행 필요)**: 새 `verify` 잡의 실제 Actions 실행(주소 주입·`python3 -u`·요약 렌더링·새 이름), 실제 사이트의 **배포 직후** 동작(새 글 주소의 첫 응답이 404인지, 그렇다면 몇 번째 시도·어느 요청 모양에서 열리는지, `Age`·`Last-Modified`, 배포 때 CDN이 비워지는지 — 요청 모양 회전은 가짜 CDN 모델과 기존 글에 대한 실측으로만 확인했다), 로컬 Python 3.10 실행(저장소 규칙·테스트 자동 검사 CI의 3.10·3.12가 대신). 이 수정에 대한 독립 재검증은 3차까지 끝났다(위)

### 다음 AI에게 남기는 주의사항
1. **병합 뒤 글이 추가된 첫 배포에서 `verify` 잡(`사이트 반영 확인`)의 요약을 읽고 기록한다**: '시도 기록'(시도별 경과 초·요청 모양·상태)과 `X-Cache`·`Age`·`Last-Modified`(새 글 주소 응답과 '참고' 줄의 `posts.json`, `docs/DEFECT_REGISTER.md` 하단 체크리스트). 핵심은 시도 1(정규 주소)이 404였는지와 몇 번째 시도·어느 모양에서 열렸는지다. 늘 시도 1에서 열리면 CDN 404 보관 문제는 실제로 일어나지 않은 것이고, 404였다면 그 응답의 `X-Cache`·`Age`로 배포 직후 원본이 늦은 것인지 가려 첫 요청 전 대기(20~30초)를 둘지 정한다(이번에는 근거가 없어 넣지 않았다). `posts.json`은 배포 전부터 있던 파일이라 `Last-Modified`가 이번 빌드 시각이고 `Age`가 작으면 배포 때 CDN이 새 파일을 가져온 것이고, 옛 시각이면 캐시가 남은 것이다
2. 이 확인의 주소 계산은 `_config.yml`의 `permalink`가 `/posts/:year/:month/:day/:title/` 같은 단순 패턴일 때만 맞다. permalink를 바꾸면(광고 표면 T3) `tests/test_verify_pages_select.py`의 `PUBLIC_SNAPSHOT`(공개 사이트 사본)을 같이 고친다 — `RealRepositoryTest`가 실패해 알려 준다. 계산할 수 없는 패턴이면 `posts.json` 주소로 대신하고, 계산이 틀리면 요약에 '주소 계산 규칙 점검 필요' 경고가 남는다
3. `published: false`·미래 날짜 글은 확인 대상이 아니다. 새 비공개 방식(`_config.yml`의 `exclude`·`defaults` 등)을 쓰면 이 스크립트의 제외 규칙도 같이 맞춘다. 따옴표 친 `"false"`는 Jekyll이 공개로 보지만 이 확인은 보수적으로 비공개로 취급한다(다음 글을 본다)
4. 이 확인은 **가장 새 글의 공개 여부만** 본다: 글을 추가하지 않은 커밋(이미지 교체·기존 글 수정)의 반영 실패는 이미 공개 중인 최신 글 때문에 통과하고, Jekyll 빌드 실패(D-24형)는 `build` 단계가 먼저 빨강이라 `verify`는 건너뛰어진다(이 잡이 새로 잡는 것이 아님)
5. **404도 CDN이 보관한다**(위 관측): 최대 약 18분(1회 측정, 불확실). 새 글 주소를 배포가 퍼지기 전에 한 번 조회하면 — 이 검사의 첫 요청 포함 — 그 404가 같은 주소·같은 모양의 요청에 계속 돌아오고 쿼리·`no-cache`로는 피하지 못한다. 그래서 이 검사는 같은 모양을 되풀이하지 않고 시도마다 요청 모양(`SHAPES`)을 바꾼다. 모양은 실제 사이트에서 200·MISS(새 캐시 객체)로 확인된 것만 넣었다 — 새 모양을 추가할 때는 기존 글과 없는 주소 양쪽에서 확인한다(없는 글을 200으로 만들면 안 된다). 마감을 늘려 기다리는 방식으로 되돌리지 않는다
6. 요청 하나는 소켓 연산별 15초에 더해 전체 30초가 상한이다(작업 스레드로 끊고 버린다). 마감은 요청 '사이'에서만 확인하고 잡 제한 15분이 최후의 안전망이다(최악: 마감 720 + 요청 2건 60 + 준비 120 = 900초로 여유가 0). 새 테스트의 시계는 가상이다(실제 0.05초를 기다리는 요청 상한 테스트 하나는 예외) — 실제로 12분을 기다리는 테스트를 만들지 않는다. 가상 시계에는 잠든 횟수 상한이 있어 마감 계산이 틀리면 멈추지 않고 바로 실패한다

### 남은 이슈 / 확인할 점
- **F-07(워치독 PR의 몫, 이 PR은 코드를 고치지 않았다 — main에 D-44로 등록됨)**: 워치독이 verify 실패를 'D-24형 빌드 실패' 문구로 설명하고(`PAGES_NOT_DEPLOYED`·`PAGES_FAILED`), 동시 실행(`cancel-in-progress`)에 취소된 실행 — 글은 공개 중인데 다음 실행이 build에서 실패하면 치명 경보, 취소만 남으면 치명 경보 — 를 구분하지 못한다(검증자의 재현). D-41 항목에도 적었다
- 병합 메모: main(`0f509d2`: 보안·워치독·Blogger 가시화 병합 뒤)·main(`c00eb4f`: 워크플로 이름 한글화 PR #17 병합 뒤)·main(`5bf2fc9`: 이슈 수정 하드닝 #19·간헐 실패 방지 #18 병합 뒤)을 이 브랜치에 차례로 병합했다. 충돌(WORKLOG·DEFECT_REGISTER·ARCHITECTURE·HANDLER)은 두 쪽을 모두 살려 풀었다(ARCHITECTURE는 main의 '4-2 워치독 규칙'이 먼저라 이 PR의 절을 4-3으로 옮김, 이 PR 문서·코드의 옛 영문 워크플로 이름은 새 이름으로 바꿈)
- 판단이 필요한 설계: ① 계산한 주소가 안 열려도 `posts.json` 주소가 열리면 통과(경고)하는 안전망 ② 같은 시각 글이 10건을 넘으면 앞의 10건만 확인 ③ 시간대는 `Asia/Seoul`·UTC만 알고 나머지는 UTC로 본다 ④ 마감 720초와 첫 대기 10초·2배·최대 160초, 시도마다 요청 모양 바꾸기 ⑤ 첫 요청 전 대기를 두지 않음(배포 직후 원본 지연을 실측하지 못해 추측으로 넣지 않음) ⑥ 마지막 시도(기본값 약 630초) 뒤 약 90초는 보지 않음
- 하지 않은 것(2차): N-5(slug의 Mark/Nl 정렬)·N-9, 첫 요청 전 대기, 따옴표 친 `date:` 시각 문자열의 시간대(Jekyll은 사이트 시간대, 이 스크립트는 UTC — 한계로 기록)
- **3차 잔여 N3-1~N3-5**: 위 '총괄 판단'과 `docs/DEFECT_REGISTER.md` D-41의 "3차 잔여". 병합 뒤 첫 배포를 관측한 뒤 판단한다. 후속 PR을 낸다면 순서는 N3-1(비정규 모양 먼저)·N3-4(요약 머리 줄)가 한 묶음이고, 같은 PR에서 N3-2 테스트 3개와 N3-3 문구를 함께 고친다(`timeout-minutes` 20은 N3-5, 비용 없음)

---

## [2026-10-25] Claude – 이슈 수정 시스템 하드닝: 재처리 방지·이미지 주소 엄격 검증·로그 명령 주입 차단·외부 AI 전송 전 점검·줄 끝 검사·제목 변경 PR 통과 (운영자 승인 항목 5·6·8~11, 총괄)

**작업자**: Claude (총괄 역할)  
**대상**: 공통 (이슈 기반 수정 시스템 `pipeline/edits/*`, `issue-edit.yml`)  
**등급**: T2 (워크플로·보안 경계). 독립 검증은 별도 세션이 새 clone에서 두 번 수행(아래)  
**목적**: 이슈 수정 시스템의 첫 기준선 시험(PR #13)과 코드 검토에서 나온 구멍을 닫는다 — 같은 이슈를 다시 돌리면 중복 PR이 생기는 문제, 이미지 주소·로그를 통한 명령 주입, 공개 이슈 본문의 비밀이 외부 AI로 나가는 경로, 줄 끝(LF/CRLF) 변경, 제목만 바꾸는 PR이 Guardrails에서 빨강이 되는 문제(D-38·D-40)

### 변경 사항
- **재처리 방지(항목 5)**: `issue-edit.yml` 첫 단계(체크아웃 전)에서 이슈 번호를 `^[1-9][0-9]{0,8}$`로 검사(앞자리 0은 브랜치 패턴을 우회하므로 거부), `git ls-remote`로 `issue-edit/<번호>-*` 브랜치와 표식 라벨 `issue-edit-done`을 보고 이미 처리했으면 코멘트만 남기고 새 브랜치·PR을 만들지 않는다(`status=duplicate`; 연습 실행은 예외, 목록을 못 읽으면 fail closed)
- **이미지 주소 엄격 검증(항목 6, D-38)**: `checks.py` `verify_image_change`·`image_url_problem` — `https://images.unsplash.com/photo-…` 형식만 통과. 러너(생성 직후)·PR 범위 검사·이미지 수정 연산이 같은 함수를 쓴다. 이미지 없던 글에 이미지만 추가하는 정상 PR은 PASS
- **로그·공개 코멘트 정책(항목 8, D-39)**: 새 `pipeline/edits/safety.py` — 이슈 처리 단계의 모든 로그 줄이 `[issue-edit] issue=#N author=@login(권한)`으로 시작하고, 줄 머리 `::`·어디서든 `##[`는 무력화, 비밀은 `***`. 연습 실행 출력은 무작위 토큰 `::stop-commands::`로 감싼다. AI 실패 원인은 러너 로그에만(마스킹·300자), 공개 코멘트의 AI·요청 유래 텍스트는 코드 스팬, PR 본문 diff는 틸드 펜스. 이미지 선택기가 `generator.py`에서 직접 찍던 줄은 호출 동안 stdout을 가두고 알려진 줄만 요약(검색어·후보 주소는 로그에 내지 않음). 예기치 못한 예외는 `main`이 종류만 담은 오류 결과(종료 1)로 처리
- **외부 AI 전송 전 점검(항목 9)**: 요청·변경 전·페이지 원문·이미지 설명·제목·태그에서 키·토큰 모양, 주민등록번호 모양, 카드번호 모양(13~19자리 연속 또는 흔한 묶음 + 카드사 접두사 + Luhn, 같은 숫자 반복 제외)을 AI·Unsplash 호출 **전에** 찾아, 있으면 호출하지 않고 일반 거부(값은 되풀이하지 않음). 프롬프트 구분자는 더 지울 것이 없을 때까지 제거. 이메일·전화는 허용
- **줄 끝(항목 10)**: PR 범위 검사가 LF/CRLF 유형 변경·혼합을 FAIL로, 러너는 혼합 줄 끝 파일을 거부(종료 2)
- **명세(항목 11)**: `edit-spec.yml`의 `comment_on_reject` 삭제, 지원하지 않는 `output` 키는 SPEC-1 오류
- **제목 변경 PR(D-40)**: `pages.check_registry`가 `pages.json`의 제목 차이만 보지 않는다(페이지 추가·삭제·이동·id·url·서식 손상은 계속 잡음). 병합 뒤 Sync Issue Form이 원문 기준으로 되돌린다
- **문서**: ISSUE_EDITS, DEFECT_REGISTER(D-23 정정, D-37~D-40 신규·정정, D-45·D-46 기록, 관측 체크리스트)

### 검증 증거
- **L0~L1**: validate_repo 오류 0·경고 2(LIQUID-1, EXPOSE-1 — main과 동일), actionlint 0건(로컬에 shellcheck 없음 — CI), pyflakes 신규 0, vermin 3.10 호환, 보이지 않는 문자 소스 0건. main(0f509d2)과 합친 트리 전체 833개 통과(통합 시점)
- **1차 독립 검증**(971b90b): 조건부 병합 가능. 실제 사례(PR #13: 제목만 바꾼 PR)는 main 코드에서 실패하고 이 브랜치에서 통과함을 직접 재현. 번호 검사 스크립트를 YAML에서 그대로 뽑아 bash로 40입력 실행(불일치 0), `ls-remote` 패턴을 실제 git·실제 공개 저장소로 확인. 변이 43개 중 19개 탐지, 24개 생존(워크플로 보안 필드 고정 테스트 부재 등). 지적 F-1~F-14: 높음 1(main 병합 뒤 docstring 소비처 목록 테스트 실패)·중간 3(이미지 선택기 직접 출력이 로그 정책 우회, 카드번호 모양 오탐, 워크플로 불변식 테스트 부재)·낮음~정보 10
- **수정 반영**(커밋 e2e1b8a~24cc727, main 병합 2회): F-1 docstring 목록, F-2 이미지 선택기 stdout 가둠, F-3 카드번호 탐지 재설계(probe 거짓 음성 16→6, 거짓 양성 3→1, 숫자 목록 오탐 최대 99%→0%), F-4 워크플로 YAML 불변식 테스트 11개, F-5 구분자 반복 제거, F-6 catch-all과 `urlsplit` ValueError 방어, F-7 코드 스팬 자르기, F-8 diff 틸드 펜스, F-9 주민번호 예외 좁힘, F-12·F-14 주석, F-13 보이지 않는 문자 이스케이프(전 코드 포인트 비교 차이 0). F-10(이미지 URL 형식 고정)·F-11(제목 불일치 신호 없음)은 D-45·D-46 기록만. 변이: 검증자 정의 43개 + 구현자 92개, 최종 생존 0
- **2차 독립 검증**(24cc727): **조건부 병합 가능** — 1차 지적 F-1~F-14 전부 실제로 반영됐음을 PoC·퍼징·변이로 확인(전체 782개가 CRLF 트리와 LF 전용 clone·소켓 전부 차단 상태에서 통과, 새 코드 위주 변이 133개 중 116개 탐지·생존 17은 테스트 공백이거나 동등, 1차 생존 24개는 모두 탐지, `targets.match_post` 새·옛 구현 60,502 입력 차분에서 정상 판정 변화 0). 조건은 그사이 main에 이름 한글화(#17)가 들어와 옛 영문 이름 약 27줄을 바꾸는 것이었고 병합 후 반영됨. 비차단 권고 N-1(Amex·Diners 4자리 표기 미탐)·N-2(구분자 제거의 이차 시간)·N-3(stderr 미가둠)·N-8(catch-all이 단언·건너뛰기 예외까지 삼킴)·N-5·테스트 공백 S10·S12·X11 등은 반영, N-4(주민번호 예외 축소의 새 오탐 — 의도한 맞교환)·N-6·N-7·N-11은 문서만
- **수정 반영**(커밋 9363d4c·3330961·20fc478, main c00eb4f·bb52422 병합): `_CARD_SHAPES`에 (4,4,4,3)·(4,4,4,2) 추가, `strip_delimiters` 닫는 쪽에 앞 앵커를 달아 선형 시간(`"A"*30000` 8.6초 → 1.25ms)·반복 상한 8회·상한 뒤 남은 구분자는 `‹‹‹`·`›››`로 통째 치환, 이미지 선택기의 stdout과 stderr를 함께 가둠, catch-all은 `AssertionError`와 `unittest.case` 예외를 다시 던지고(맞교환 가드: `pipeline/edits/*.py`에 assert 문 없음을 AST로 검사) 러너 로그에만 터진 곳 `파일:줄 함수`(가장 안쪽 4프레임, 예외 문구 제외) 기록. 통합 시점 전체 833개 통과(+14), 변이 163건(신규 39 + 기존 85 + 검증자 정의 39 중 적용 가능분) 생존 0
- **실행하지 못한 것**: 실제 Linux 러너의 Python 3.10(Guardrails CI의 3.10·3.12가 대신), 실제 Actions 실행(이미지 변경 이슈의 러너 로그 첫 줄이 전부 `issue=#N`인지, `ls-remote`·라벨 권한, `::stop-commands::` 동작), shellcheck

### 다음 AI에게 남기는 주의사항
1. **병합 뒤 Actions 관측**(`docs/DEFECT_REGISTER.md` 관측 체크리스트): 번호 형식 검사(`abc`·`012` 즉시 실패), 시험 이슈 연습 실행의 로그 줄 머리, 시험 이슈를 한 번 처리한 뒤 같은 번호로 다시 돌리면 "이미 처리한 이슈입니다" 코멘트만, 이미지 PR의 범위 검사, 제목만 바꾸는 PR의 Guardrails 초록. 이슈 #12는 브랜치 `issue-edit/12-categories-r1`이 남아 있어 같은 번호를 다시 돌리면 중복으로 막힌다(의도) — 시험은 새 이슈로
2. 이슈 수정 시스템의 3-job 분리(권한 최소화, 항목 1)는 아직 안 했다. `IssueEditWorkflowSecurityTest`가 지금의 단일 job 구조를 고정하므로 분리하면 테스트를 함께 갱신한다. 쓰기 토큰 노출(D-23)이 그 몫
3. 비밀·번호 탐지는 우발적 붙여넣기용 보조 장치다(점·슬래시·밑줄 구분 카드, 줄바꿈 구분 카드, 5-5-5 묶음, 0·1·20·21·28·29로 시작하는 15~19자리는 놓침, 13자리 ms 시각값은 주민번호 모양과 구분 못 해 거부). 이미지 요약 패턴은 `generator.py` 출력 문구에 결합돼 있어 문구가 바뀌면 동기화 테스트가 알린다
4. 예기치 못한 예외의 종료 코드는 1(인프라)이다 — 워크플로의 edit 단계는 빨강이 되지만 `always()` 코멘트 단계가 오류 코멘트를 남긴다. 2(설정 오류)로 바꿀지는 후속 판단

### 남은 이슈 / 확인할 점
- D-45(이미지 URL 형식이 `/photo-` 고정이라 `uploads/`·`plus.unsplash.com` 후보가 첫 선택이면 재시도 없이 거부), D-46(제목 불일치 신호가 PR·main push 어디서도 없음 — Sync 뒤 `strict_titles=True` 확인 단계 추가), D-23(쓰기 토큰 노출, 3-job 분리 몫)

---

## [2026-10-25] Claude – Actions 워크플로 이름 한글화·Chance 이미지 교체 워크플로 분리 (운영 접근성)

**작업자**: Claude (구현 담당)  
**대상**: 공통 (Chance_Blog 워크플로 분리 포함)  
**등급**: T2 (워크플로·검증기 변경). 독립 검증은 별도 세션이 새 clone에서 수행했다(병합 가능, 조건 3개는 절차 문제 — 아래 '독립 검증 반영')  
**목적**: 운영자가 Actions 탭 이름만 보고 "자동인가 수동인가, 무엇을 하는가"를 짐작할 수 있게 한다(운영자 요청). 한 워크플로에 묶여 있던 '글 자동 작성·게시'와 '기존 글 이미지 교체'를 둘로 나눈다

### 변경 사항
- **이름(`name`)**: 워크플로 8개를 한글로. 옛 이름 → 새 이름 · 파일 · 하는 일 · 자동/수동 표는 `docs/ARCHITECTURE.md` §2-1과 `docs/REQUEST_BRIEFING.md`(기준일 2026-10-25). 파일 이름·job 키·트리거·권한·env·`run:` 본문은 그대로다(예외 하나: `blogger.yml` plan 단계가 대상 0개일 때 쓰는 요약 제목 `### Blogger Generate` → `### Blogger 글 자동 작성`)
- **실행 제목(`run-name`)**: `chanceblog`(정기/수동/연습), `chance-fix-images`(연습/실제 교체), `blogger`(정기/수동 3종), `watchdog`(정기/수동), `issue-edit`(이슈 번호 + 자동/수동/연습). 이벤트 종류·이슈 번호·불리언만 참조하고 이슈·PR 제목·자유 입력 같은 외부 문자열은 넣지 않는다. `pages`·`guardrails`·`pr-scope-check`·`sync-issue-form`은 기본 제목(커밋 메시지·PR 제목)이 더 알려 줘서 그대로 뒀다
- **job·단계·입력 설명**: job `name`을 한글로(`글 작성·게시`, `대상 블로그 계획`, `글 생성 (블로그 key)`, `사이트 빌드`·`사이트 게시`, `검사 (Python 3.10/3.12)`, `발행 상태 점검`, `수정안 만들기`, `이슈 요청 범위 확인`, `목록 동기화`). `pages.yml`의 영어 단계 이름 5곳과 입력 `description`을 한글로(`DRY_RUN` → `연습 실행`). 이름 없는 `uses:` 단계(checkout·setup-python)는 그대로(진행 중인 다른 PR과 충돌을 줄이려고 이름·run-name·job name·입력 설명 줄만 건드림)
- **분리**: 새 `chance-fix-images.yml`(수동 전용, 입력 `dry_run` 기본 true, `FIX_IMAGES: '1'`). 권한·concurrency 그룹 `chanceblog`(글 작성 실행과 동시에 돌지 않음)·타임아웃 20분·env(`DRY_RUN` 입력 연동, `PIPELINE_PAUSE`, 시크릿)·커밋·Pages 배포 요청·요약 기록은 `chanceblog.yml`과 같은 내용을 복사. `chanceblog.yml`에서는 `fix_images` 입력과 `FIX_IMAGES` env 줄만 제거(`generator.py`는 손대지 않음). 이제 이미지 교체 실행이 `chanceblog.yml` 실행 기록에 섞이지 않는다(워치독의 연속 실패 판단은 파일 이름 기준이라 영향 없음)
- **검증기 WF-11**(`scripts/validate_repo.py` `check_workflow_names`): 워크플로 `name`에 한글이 없으면 오류, job `name`이 없거나 한글이 없으면 경고. 규칙 W10(`docs/ENGINEERING_GUIDE.md`), 매핑표(`docs/SECURITY_GUARDRAILS.md` §6)
- **테스트**: `tests/test_validate_repo.py`에 WF-11 10개(영문 이름 오류·이름 없음·job 경고·식 속 한글·`.yaml`·워크플로 폴더 밖 무시·`run_checks`/CLI 연결·실제 저장소). 신규 `tests/test_workflow_names.py` 24개: 입력 설명·단계 이름·run-name 한글, 문서 두 표와 실제 이름 일치, 옛 영문 이름 검색(안내 문서·워크플로·이슈 양식·코드의 알림문·요약 제목·독스트링·주석까지, 검색기 자체 시험 포함), GitHub 표현식 해석기로 정기·수동·이슈 이벤트의 실행 제목과 `run-name`이 허용된 값만 참조하는지, blogger 연습 입력 설명의 경고, `chanceblog.yml`의 `fix_images` 제거와 `chance-fix-images.yml`의 트리거·입력·권한·동시성·타임아웃·단계 동일성. `tests/test_generator_slots.py`에 `FIX_IMAGES` 계약 3개(켜지면 이미지 교체만·꺼지면 교체 안 함·환경변수가 없으면 꺼짐)
- **문서**: 현재형 안내의 옛 영문 이름을 새 이름으로(HANDLER, ISSUE_EDITS, COPILOT_GUIDE, CHARTER, ENGINEERING_GUIDE, SECURITY_GUARDRAILS, DEFECT_REGISTER 관측 체크리스트와 병합 뒤 확인 행, `.github/copilot-instructions.md`, `.github/instructions/workflows.instructions.md`). README·AGENTS·`인수인계/`에는 옛 영문 이름이 없어 그대로. 이 WORKLOG의 기존 항목은 과거 사실이라 고치지 않았다. `.github/CODEOWNERS` 머리 주석의 "main에 직접 push하는 워크플로 3종" 목록에는 같은 커밋 단계를 쓰는 `chance-fix-images.yml`을 더해 4종으로 고쳤다(보안 설정 PR의 머리 주석 시험은 그대로 통과)

### 검증 증거
- **L0**: `python scripts/validate_repo.py` 오류 0, 경고 2(LIQUID-1 인수인계 초안 문서, EXPOSE-1 — main과 같음, WF-11 지적 없음. `--base`를 main으로 줘도 오류 0). `actionlint` 1.7.12 저장소 전체 0건(새 파일 포함, `run-name` 식의 문맥 검사도 한다 — 허용되지 않은 문맥을 넣으면 오류가 나는 것을 시험 파일로 확인). `pyflakes` 변경 py 3개 0건. `vermin --target=3.10-`: 최소 3.7(3.10 호환)
- **L1**: `python -m unittest discover -s tests` **630개 통과**(시작 기준 main ddf0a22는 401개 → 보안 설정 PR(#14) 반영 main c834c2d 431개 → 워치독 보강·Blogger 가시화(#15·#16) 반영 main 0f509d2 593개, 여기에 신규 37: `test_validate_repo.py` 10, `test_workflow_names.py` 24, `test_generator_slots.py` 3). Windows, Python 3.12. 새로 clone한 사본에서 실행
- **리베이스·병합**: 작업 중 보안 설정 PR(#14, c834c2d)이 병합돼 그 위로 리베이스했다(충돌 3곳은 main 내용을 유지하고 이름 변경만 얹어 풀었다). 그 뒤 main(0f509d2)은 병합 커밋(`git merge`)으로 합쳤다: 충돌 5개 파일(HANDLER 2곳·WORKLOG·DEFECT_REGISTER 2곳·ENGINEERING_GUIDE·REQUEST_BRIEFING)은 양쪽 내용을 모두 살렸고 새로 들어온 안내·코드의 옛 이름을 바꿨다. 병합 직후 사본은 625개 통과였다
- **동작 불변 증명**: main(ddf0a22, 병합 전)의 워크플로 8개와 이 브랜치를 PyYAML로 비교(이름·run-name·입력 description·job name·단계 name 제외): 7개 파일은 구조 차이 0건, `chanceblog.yml`은 `fix_images` 입력과 `FIX_IMAGES` env 두 곳만 다름, job 키·`needs` 전부 동일. 새 `chance-fix-images.yml`은 분리 전 `chanceblog.yml`과 `FIX_IMAGES: '1'`(전: 입력 연동 식)·`schedule` 트리거·`fix_images` 입력만 다름. 병합 뒤 현재 main(0f509d2)과 비교해도 `chanceblog.yml` 2곳과 `blogger.yml` plan 단계의 요약 제목 문구 1곳만 다르고 나머지 6개 파일은 0건
- **표적 변이**: 새 테스트가 정말 실패하는지 복사본에 변이를 하나씩 넣어 확인했다. 1차 41종(검증기 10·워크플로/문서 27·표현식 해석기 4)과 후속 19종(`FIX_IMAGES` 계약 8·옛 이름 검색 범위 9·blogger 입력 설명 1·병합에서 바꾼 `pages.yml` 이름 1)이 모두 실패로 탐지됐고 생존 0이다(병합 뒤 최종 트리에서 다시 실행). 옛 워크플로 8개로 통째로 되돌린 복사본에서는 `test_workflow_names.py` 22개 중 15개와 WF-11 실제 저장소 시험 2개가 실패했다(병합 전 트리 기준)
- **독립 검증**(e0ac1a4, 새 clone): **병합 가능**(조건 3개는 모두 절차 문제 — PR의 Linux CI 확인, 병합 직후 Actions 확인 5가지, 대기 브랜치 3개와의 병합 순서). 동작 불변을 구조 비교·줄 단위 diff·표현식 평가·`generator.py` 로컬 실행 네 방법으로 확인, 이름 대응표 불일치 0, 옛 영문 이름 현재형 잔존 0, 변이 78개 중 새 테스트가 67개 탐지(생존 10은 F3·F5·F6·F9와 동치 1). 대기 브랜치 시험 병합에서 워크플로 yml 4개는 모두 자동 병합, 충돌은 문서 표 줄뿐
- **독립 검증 반영(병합 뒤 후속 커밋)**: F3 `FIX_IMAGES` 계약 시험 3개(변이 G01·G02 탐지), F5 옛 영문 이름 검색을 `.yml`·`.py`까지 확대(변이 D06·D07 탐지), F4·F11 WF-11 강제 범위(검증기는 워크플로 name 오류·job name 경고, job name 은 단위 테스트가 경고도 실패로 취급, 입력 description·단계 name·run-name 한글은 단위 테스트가 요구)와 외부 템플릿 안내를 `ENGINEERING_GUIDE` W10·`SECURITY_GUARDRAILS` §6·검증기 오류 문구·Copilot용 지침에 적음, F10 `blogger.yml` 연습 입력 설명에 '체크하지 않으면 초안이 저장소에 커밋됨' 추가. F2·F7·F8·F9·F12·F14는 코드 변경 없이 D-49로 기록했다. 새로 들어온 코드·시험의 옛 이름: `pipeline/health.py` 알림문('Deploy GitHub Pages' → `사이트 자동 배포`), `blogger.yml` 요약 제목, `tests/test_watchdog_integration.py`의 pages.yml 이름 단정(옛 이름 그대로면 병합 뒤 시험이 실패했다)
- **로컬 연습 실행**: `FIX_IMAGES=1 DRY_RUN=1 EVENT_NAME=workflow_dispatch python generator.py`(키 없음=스텁, 새 워크플로가 부르는 방식): 종료 0, 파일 변경 없음, 요약 `이미지 점검: 완료: 문제 2건 / 교체 2건 / 건너뜀 0건 (DRY_RUN: 실제 변경 없음)`. 지금 저장소의 중복 이미지 2건이다 — 연습을 풀고 실제로 교체하면 이 2건이 바뀐다
- **실행하지 못한 것(실행 필요)**: GitHub Actions 실제 실행 일체 — 새 이름 표시, 정기 실행 제목, `chance-fix-images.yml`·`chanceblog.yml`·`이슈 수정 요청 처리(수정안 PR 만들기)` 연습 실행(새 워크플로 파일은 main에 병합되기 전에는 수동 실행 불가), 이 PR의 `저장소 규칙·테스트 자동 검사` 3.10·3.12(PR을 열면 실행됨), 로컬 Python 3.10 단위 테스트(없음 — CI의 3.10이 대신)

### 다음 AI에게 남기는 주의사항
1. **병합 뒤 Actions에서 확인**(`docs/DEFECT_REGISTER.md` 하단 체크리스트 마지막 5행): ① 왼쪽 목록에 새 이름 9개 ② 정기 실행 제목(`Chance 글 작성·게시 · 정기` 등) ③ `Chance 글 자동 작성·게시` 연습 실행 ④ `Chance 기존 글 이미지 교체(수동)` 연습 실행 ⑤ `이슈 수정 요청 처리(수정안 PR 만들기)` 연습 실행
2. **새 워크플로·job은 한글 `name`을 붙이고 두 표(`docs/ARCHITECTURE.md` §2-1, `docs/REQUEST_BRIEFING.md`)에 한 줄 넣는다.** 안 하면 검증기 WF-11이 알리고 `tests/test_workflow_names.py`와 `WorkflowNameTest`(실제 저장소 기준)가 실패한다. 같은 워크플로를 고치는 다른 PR을 병합할 때는 그쪽이 새로 만든 job(예: `pages.yml`의 배포 후 확인 잡)에도 한글 이름이 필요하고, 그 PR의 문서가 옛 영문 이름을 쓰면 `test_operator_docs_do_not_use_the_old_english_names`가 알린다(이 검사는 `.md`뿐 아니라 `.yml`·`.py`의 알림문·요약 제목·독스트링·주석도 본다. 대응표처럼 새 이름이 같은 줄에 있으면 허용, 과거 기록 `WORKLOG.md`는 제외)
3. **PR 검사 이름이 바뀐다**: `guardrails.yml`의 job 이름이 `validate (3.10)`·`validate (3.12)`에서 `검사 (Python 3.10)`·`검사 (Python 3.12)`가 됐다. 운영자 결정(2026-10-25, `docs/SECURITY_GUARDRAILS.md` §5)으로 main 룰셋에 '상태 검사 필수'는 켜지 않으므로 지금은 영향이 없다(실제 룰셋 상태는 확인하지 못했다). 나중에 필수 검사를 켜게 되면 새 이름으로 골라야 병합이 막히지 않는다
4. 옛 `gh workflow run chanceblog.yml -f fix_images=true` 호출은 이제 입력 오류로 막힌다(조용히 무시되지 않음). 이미지 교체는 `chance-fix-images.yml`로
5. 알려진 한계: ① Blogger 매트릭스가 비어 `글 생성 (…)` job이 건너뛰어지면 화면에 `matrix.key` 식이 풀리지 않은 채 보일 수 있다(표시만의 문제) ② 두 Chance 워크플로가 같은 concurrency 그룹을 써서 GitHub 규칙상 대기 실행은 1개만 남는다(실행 중 1 + 대기 1) — 이미지 교체를 대기시킨 사이 정기 실행이 또 대기하면 먼저 대기한 쪽이 취소될 수 있다(운영 규칙: 이미지 교체는 연타하지 않고 정기 실행이 도는 매시 :17 전후를 피한다. 대기열을 늘리는 `queue: max`는 `actionlint` 1.7.12가 키를 거부하니 올린 뒤 검토 — D-49) ③ 제어 이슈가 아닌 이슈도 `이슈 수정 요청 처리` 실행이 하나 만들어지고 job이 건너뛰어진 채 회색으로 보인다(이전과 같은 동작, 이제 제목에 이슈 번호가 붙음) ④ `[Watchdog]` 이슈 제목 접두어·라벨 `watchdog`은 식별자라 한글로 바꾸지 않았다
6. `generator.py`는 이미지 교체 모드에서도 `GEMINI_API_KEY`를 요구한다(`STUB_GEMINI and not DRY_RUN`이면 오류). 이미지 교체는 Gemini를 쓰지 않으므로 필요하면 별도 T2로 이 검사를 모드별로 나눈다. 이번에는 동작을 바꾸지 않으려고 시크릿 전달을 그대로 복사했다(D-49 F7)

### 남은 이슈 / 확인할 점
- Actions 실행은 하지 못했다. `run-name` 식은 `actionlint`와 단위 테스트의 표현식 해석기로만 확인했다 → 위 체크리스트
- 같은 파일을 고치는 진행 중 PR(`blogger.yml`·`watchdog.yml`·`pages.yml`·`issue-edit.yml`)과 병합 때 충돌할 수 있다. 이 PR이 건드린 줄은 이름·run-name·job name·입력 설명 줄뿐이다
- 독립 검증의 잔여 지적 F2·F7·F8·F9·F12·F14는 `docs/DEFECT_REGISTER.md` D-49(낮음, 열림)에 기록만 했다. F14는 D-49에 내용을 적었다(이미지 교체가 STALE 판정을 늦춘다는 우려는 워치독 보강 PR #15가 글 파일 '추가' 커밋만 세게 하면서 해소됨)
- 이름 선택: 표의 이름을 그대로 썼다. 더 다듬을 후보는 `PR 변경 범위 검사` → `PR 변경 범위 자동 검사`(다른 이름의 '자동' 표기와 맞춤), `Blogger 글 자동 작성` → `Blogger 글 자동 작성(초안·게시)`(모드에 따라 게시도 함을 드러냄)

---

## [2026-10-25] Claude – Blogger 가시화: 시크릿 미등록·정지·상한 건너뜀을 숨기지 않고, 로그·요약 정화, macat0722 정지 반영 (발행 복구 2/4, 총괄)

**작업자**: Claude (총괄 역할)  
**대상**: Blogger  
**등급**: T2 (실행 규약·종료 코드·워크플로 plan 단계). `blogger_macat`을 `mode: off`로 둔 것은 운영자 결정(2026-10-25, 영문 블로그인데 프로필이 한글 → 영문 프로필 준비 전까지 정지). 독립 검증은 별도 세션이 새 clone에서 두 번 수행(아래)  
**목적**: D-25(게시용 시크릿이 없어도 실행이 초록 — 초안이 저장소 파일로만 쌓이고 Blogger에는 한 번도 안 감), D-26(하루 상한 건너뜀이 조용함), D-32(영문 블로그에 한글 글이 갈 위험)와, 검증 중 발견한 로그 위조 경로(다른 블로그 이력 제목의 개행으로 `::error::` 줄을 만들 수 있음)

### 변경 사항
- **`pipeline/run.py`**: 게시 대상인데 게시용 시크릿이 없으면 **글을 만들기 전에** 종료 2 + `::error::`(시크릿 **이름**만) + `[SKIP] code=SECRETS_MISSING` + 요약. 이 점검은 하루 상한·주제 선정·이력 읽기보다 앞선다(`--topic` 지정도 우회 못 함, DRY_RUN은 경고만). `PIPELINE_PAUSE`·`mode: off`·하루 상한 건너뜀에는 `[SKIP]` 줄과 요약에 더해 `::notice::`(Actions 화면 위쪽 주석)를 남긴다. 주제 없음·게이트 탈락은 경고 주석, LLM·주제 확장·게시 실패는 종료 1. 로그·요약에 쓰는 외부·AI 유래 문자열은 `one_line()`으로 접고, `::warning::`·`::error::` 주석에는 고정 문장만 쓴다
- **`pipeline/plan.py`**: `--only`를 두 단계로 검사(레지스트리에 없는 key·`--platform`과 다른 플랫폼의 key는 종료 1과 유효 key 안내). 대상이 모두 정지거나 없으면 대상 0개로 초록 + notice
- **`pipeline/console.py`**(신규 함수): `one_line()`(개행·단독 CR·U+2028·U+2029·U+0085·제어 문자를 공백 하나로, 길이 제한, `::`·`##[` 위치와 상관없이 무력화 — 러너가 `TrimStart()` 뒤에 `::`를 검사하고 `##[`는 줄 어디서든 해석하므로 줄 머리 공백 방식은 쓰지 않았다), `md_cell()`(요약 표용 마크다운 이스케이프)
- **`pipeline/gates.py`**: 중복 사유에 넣는 비교 대상 제목을 한 줄·100자로 접는다(판정·코드는 불변 — 유사도는 원문 전체로 계산)
- **`.github/workflows/blogger.yml`**: plan 단계가 실패하면 단계도 빨강(예전에는 `matrix=`가 빈 채 초록이라 오타 key가 흔적 없이 건너뜀), 대상 0개 notice와 요약, `ONLY_BLOG`는 `env:`로만 받아 셸 주입을 막음
- **`pipeline/blogs.json`**: `blogger_macat`을 `mode: off`로(운영자 결정). 정지 중에도 매일 02:00 UTC 실행은 돌고 초록 + notice로 끝난다. 워치독은 정지 블로그를 평가하지 않아 #10(UNPUBLISHED)은 정지 효과로 닫힌다
- **문서**: ARCHITECTURE(Plan·Topic 행, §4-1 코드표에 Blogger 코드와 종료 2 행, 처리 순서 단락, 상태 이름), HANDLER(현황 표, 재개 절차, 첫 실행 안내), ENGINEERING_GUIDE R9·L3, SECURITY_GUARDRAILS G-L2, REQUEST_BRIEFING, DEFECT_REGISTER(D-25 해결·관측 필요, D-26 완화, D-48 신규)

### 검증 증거
- **L0**: `python scripts/validate_repo.py` 오류 0·경고 2(LIQUID-1, EXPOSE-1 — main과 동일), actionlint 0건(로컬에 shellcheck 없음 — CI), pyflakes 신규 0, vermin 3.10 호환, 3.12 전용 문법 스캔 0건. 비밀 모양 리터럴 0건(테스트의 가짜 키는 런타임 조합)
- **L1**: 이 브랜치 단독 332개 통과(main 297 + 신규 35), main(c834c2d)과 합친 트리 593개 통과. 소켓 차단 상태에서도 통과(네트워크 시도 0)
- **1차 독립 검증**(b154fa5·4698bb1): 조건부 병합 가능, 높음 0건. 변이 45개 중 34개 탐지, 11개 생존(사전 점검 위치 4곳·`--topic` 우회·게시 실패 마스킹·`PIPELINE_SECRET_*` 계약 등 — 코드는 맞고 테스트가 못 잡음). 지적 F-1~F-10
- **수정 반영**(커밋 ecbd82e~4006aa1): F-3(코드가 인용하던 설명 없는 내부 번호를 평문으로)·F-4(`--only` 두 단계 + plan 단계를 실제 `bash -e`로 돌리는 테스트)·F-6(`one_line`·`md_cell` + 개행·CR·U+2028·`::`·링크·표를 숨긴 이력 제목 테스트)·F-7a(워크플로가 넘기는 `PIPELINE_SECRET_*` 이름만으로 게시 성공까지 가는 테스트)·F-7b(생존 변이 9개를 잡는 테스트)·F-10(PAUSED·MODE_OFF notice). 되돌리면 실패하는지 22종 확인, 1차 생존 변이 9개 모두 탐지
- **2차 독립 검증**(4006aa1): **병합 가능**. 지적 6건 모두 해소. 새 로직 표적 변이 65개 중 60개 탐지(생존 5: 동등·문구 3, 테스트 보강 권장 2 → N-1·N-2는 이번 변경에 테스트로 추가해 변이로 확인). 게시 대상 실행이 이유 없이 초록으로 끝나는 경로가 없음을 **12,960가지 조건 열거**로 확인(위반 0). 옛 gates와 새 gates를 제목 66개×프로필 2개로 132번 비교해 판정·코드 차이 0건. 워크플로 plan 단계 시나리오 9개(정상·정지·오타·다른 플랫폼·주입 시도 등)를 실제 bash로 실행, 다른 플랫폼 key가 이전에는 초록+틀린 notice였다가 이제 종료 1. 다른 열린 브랜치(워치독·보안·Pages 확인)와 시험 병합 충돌 없음
- **실행하지 못한 것**: 실제 GitHub Actions 실행(`generate` 잡이 대상 0개에서 matrix 오류 없이 건너뛰어지는지, notice·요약이 화면에 어떻게 보이는지), Linux 러너의 Python 3.10, shellcheck, L3(실제 Gemini 초안)·실제 게시, 단독 CR을 Actions 러너가 줄바꿈으로 처리하는지

### 다음 AI에게 남기는 주의사항
1. **병합 직후 Actions → Blogger Generate를 입력 없이 수동 1회 실행**한다. 기대: plan 단계가 `::notice::실행할 Blogger 블로그가 없습니다 …`를 남기고 `generate` 잡이 건너뛰어진 채 초록(요약에 "대상 0개"). 이 확인은 로컬에서 재현할 수 없다
2. **macat0722는 정지(mode off) 상태다 — 되살리지 말 것.** 재개 절차는 `HANDLER.md` §3 P1: 영문 프로필(T3) → `mode: draft`(T3) → L2·L3 → 시크릿 등록 → `auto`(T3). 정지 중에는 `--dry-run`도 `MODE_OFF`로 막히므로 시험은 mode를 켠 사본에서 한다. 재개 직후에는 마지막 활동이 오래돼 워치독 STALE(50시간)이 바로 걸릴 수 있다. 정지로 #10이 닫혀도 시크릿 미등록·영문 프로필 문제가 풀린 것은 아니다
3. `BLOGGER_PUBLISH=off` 수동 실행도 하루 상한을 쓴다(KST 11시 정기 게시 전에 하면 `DAILY_CAP`으로 건너뜀). 상한의 의미 유지는 T3 판단이다(게시 대상 실행에서는 `posted`만 세기, 연습 실행은 상한 검사 건너뛰기를 선택지로 남김 — D-26)
4. MODE_OFF notice는 "다시 켜려면 mode를 draft 또는 auto로"라고 안내하지만, AI가 mode를 올리는 것은 SECURITY_GUARDRAILS §3 상 운영자 승인 대상이다(사람이 읽는 안내라 그대로 둠)
5. Chance 엔진(`generator.py _one_line`, 줄 머리 `::`를 `→ ` 접두로 막음)과 Blogger(`console.one_line`, 위치와 무관하게 `::`를 풀어 놓음)의 정화 방식이 다르다. 둘 다 호출 위치에서는 안전하며 통일 여부는 후속 판단
6. `게시 성공: {url}`·성공 요약의 `URL:`은 Blogger API 응답이라 접지 않았다. `topics.clean_topic`은 `gates`와의 순환 import 때문에 재사용하지 않았다
7. 시험을 PowerShell로 돌리면 `WorkflowPlanStepTest`가 bash가 없어 skip된다(Git Bash는 전부 실행). WSL 런처만 PATH에 있는 Windows에서는 실패할 수 있다(D-48 N-3)

### 남은 이슈 / 확인할 점
- D-48(낮음): N-3 bash 탐지, N-4 `md_cell`이 맨 URL·`*`·`_`를 그대로 둠, N-5 `::error::` 줄의 `exc.code` 무접기, N-6·N-7 사소한 것
- 운영자: 영문 프로필 준비 시점과 draft 재개 시점(T3), BLOGGER_* 시크릿은 초안 저장 모드(후속 PR) 이후

---

## [2026-10-25] Claude – 워치독 보강: 하루 단위 판정·글 파일 기준 STALE·사이트 배포 점검·담당자 지정·새 심각 건에만 빨강 (발행 복구 3/4, 총괄)

**작업자**: Claude (총괄 역할)  
**대상**: 공통  
**등급**: T2 (감시·알림 경계, 예약 실행 주기 조정 포함 — 근거는 아래 '결정과 근거'). 독립 검증은 별도 세션이 새 clone에서 두 번 수행(아래)  
**목적**: D-28 — 이번 장애에서 워치독은 문제를 잡았지만 늦고 조용했다. 마지막 글 뒤 약 52시간 만에 STALE 이슈를 열었고, 담당자·멘션이 없었고, 감시 실행은 늘 초록이었고, 초안을 정상 활동으로 세어 Blogger STALE은 영구히 걸리지 않았다. '글이 안 나온 날'과 '사이트가 안 올라간 것'은 아예 보지 않았다

### 변경 사항
- **`pipeline/health.py`(순수 함수)**: 새 코드 `NO_POSTS_DAY`(닫힌 한국시간 하루 기준, 어제 새 글 0건이면 경고·그제도 0건이면 심각, 오늘 글이 나왔으면 회복, STALE과 중복 안 함), `PAGES_NOT_DEPLOYED`(글 커밋 30분 뒤에도 main의 성공한 배포 실행 없음, 시계 오차 120초 여유), `PAGES_FAILED`(가장 최근 배포 실행 실패). `UNPUBLISHED`는 첫 발생부터 경고(예전 3회 연속), 사유를 이력에서 인용. 날짜만 있는 이력 항목의 '그날 23:59' 가정은 글 커밋 시각이 있으면 쓰지 않는다
- **`scripts/watchdog.py`(입출력)**: STALE 기준을 '글 파일이 **추가된** 커밋 시각'(`--diff-filter=A`, 파일 이동은 새 글 아님)으로. 이슈는 (블로그, 코드)당 하나를 유지·본문 갱신하고, 저장소 소유자를 담당자로 지정·@멘션하며, 심각 건이 48시간 풀리지 않으면 코멘트로 재알림한다. 조건이 풀리거나 다른 알림으로 대체되면 자동으로 닫는다. 실행당 새 이슈 5건 상한(심각 건 먼저). **이번 실행에서 새로 생긴 심각 건이 있을 때만 종료 1(빨강)**, 이어지는 건과 드라이런은 초록. `PIPELINE_PAUSE`가 켜지면 침묵. 실행 요약 표(블로그별 마지막 글 시각·7일 글 수·열린 이슈)를 남긴다. git 시각은 `%ct`(epoch)로 읽는다(Python 3.10이 `Z` 접미사 시각을 못 읽는 문제 회피)
- **`.github/workflows/watchdog.yml`**: 점검 주기를 하루 1회에서 **하루 2회**(UTC 03:30·15:30)로, 실행 환경에 `GITHUB_REPOSITORY_OWNER`(담당자·@멘션 대상)와 `PIPELINE_PAUSE`(변수) 전달. 권한(`contents: read`·`actions: read`·`issues: write`)과 기존 `fetch-depth: 0`(글 파일 추가 판정이 git 이력에 의존)은 그대로
- **문서·설정**: ARCHITECTURE §4-2 신설(코드별 조건·수준표·알림 방식), CHARTER·ENGINEERING_GUIDE·REQUEST_BRIEFING의 '하루 1회'를 2회로, HANDLER의 '3일 연속 미게시' 문장 정정, DEFECT_REGISTER(D-28 해결·관측 필요, D-44 신규, 관측 체크리스트에 병합 뒤 워치독 수동 실행 줄)
- 테스트: 신규 `tests/test_health_daily.py`·`tests/test_watchdog_upgrade.py`·`tests/test_watchdog_integration.py`(+`tests/watchdog_helpers.py`: `git fast-import`로 임시 저장소) 합계 125개 추가. 가짜 GitHub와 실제 임시 git 저장소로 `collect()`·`main()`을 끝까지 돌린다

### 결정과 근거
- **주기 1회→2회**: 12시간 간격으로 장애 감지 시간을 줄이는 것이 D-28의 핵심이다. 새 스케줄은 이번 장애를 재생했을 때 실제 감지(10-23 08:46 UTC)보다 약 12시간 빨랐다(검증 재생). 기존 워크플로의 주기만 바꾸고 비용은 0(공개 저장소의 Actions, LLM 호출·새 시크릿 없음)이라 CHARTER T3의 '발행 빈도·모델 호출 증가'나 새 예약 작업 생성에는 해당하지 않는다고 판단했다. **다만 운영자가 이 주기를 따로 승인한 기록은 없다** → 마감 보고에서 확인을 요청한다(검증 F-4·F-17)
- 빨간 실행을 '새 심각 건'으로 한정한 것은 운영자 결정(2026-10-25, 전부 추천대로 진행)이다. 이미 알린 심각 건이 이어지는 동안 매 점검마다 빨갛게 하지 않는다
- 담당자 지정이 거부(HTTP 422)되면 담당자 없이 이슈를 만들고 경고를 남긴다(알림이 하나도 안 만들어지는 쪽이 더 나쁘다). 403·404 등은 그대로 빨강이다

### 검증 증거
- **1차 독립 검증**(새 clone, 구현자 설명 미사용): 조건부 병합 가능. 거짓 심각 알림·데이터 손실·보안 결함은 없음. 실데이터 재생(시각마다 직전 커밋의 이력 파일을 체크아웃, 옛 코드는 실제 이슈 #9·#10 본문과 글자까지 일치)에서 병합 직후 첫 실행에 거짓 심각 알림이 재현되지 않음. 변이 54개 중 41개 탐지, **13개 생존**(collect()→evaluate() 연결·owner 전달·드라이런·UTC 날짜 등 — 코드는 맞고 테스트가 회귀를 못 잡음). 지적 F-1(git 2.45+ `Z` 시각을 Python 3.10이 못 읽음, 중간)·F-2(이슈 문구가 미병합 기능을 가정, 중간)·F-3(연결 테스트 부재)·F-4(문서·WORKLOG)·F-5~F-15
- **수정 반영**(커밋 b91dc13~eb7c802, 구현·검증 분리 유지): F-1(epoch 읽기)·F-3(통합 테스트 25개)·F-5·F-6(재알림 표식은 마지막 일치만, 인용 텍스트의 `@`·`<` 무력화, 줄 머리 `::` 접기)·F-7(CRLF 정규화)·F-9(담당자 422 폴백)·F-10(`branch=main`, 조회 실패 경고)·F-11(시계 오차 120초)·F-12·F-13(심각도 순 상한)·F-14(얕은 복제 경고, git 판정 건너뜀)·F-15. 변이 57개 전부 탐지(생존 0). F-2는 Chance 복구(PR #11) 병합 뒤 main을 이 브랜치에 병합해 해소(Chance가 `PIPELINE_PAUSE`와 `[SKIP]` 규약을 갖게 됨). **문서로 처리한 것**: F-4·F-17(이 항목과 ARCHITECTURE §4-2·체크리스트), F-8(STALE 본문의 경과 시간 때문에 12시간마다 본문 PATCH 1회 — 허용), F-16(날짜만 있던 항목의 '23:59 가정' 제거로 Chance 실질 STALE 기준이 최대 약 14시간 엄격해짐 — 의도한 동작), F-18(빨간 실행 메일이 실제로 가는지는 병합 뒤 관측)
- **2차 독립 검증**(대상 eb7c802, 브랜치 끝 e9ec03b와 워치독 관련 9개 파일은 바이트 단위로 동일): **병합 가능**(1차 조건 3개 해소 — F-1 epoch 읽기, F-2 Chance 복구 병합, 문서). 1차에서 살아남은 변이 13개 전부 탐지, 변이 94개 중 91개 탐지(생존 3: `--since` 창 제거·동치 변이 1·레지스트리 오류 줄 접기 — 영향 낮음). 17개 시각 실데이터 재생에서 수정 전·후 소견이 글자까지 같고 **현재 상태(main c834c2d)는 0건**(거짓 심각 알림 없음, 병합 직후 첫 실행은 #9·#10을 새 문구로 닫기만 함). 소켓 차단 556개 통과, Python 3.10의 `Z` 제약 모사 556/556 통과, 중간 커밋 6개도 각각 통과. 새로 남은 것은 모두 낮음·정보(R-1~R-10, 아래). 검증자도 하루 2회 주기를 T3 '비용 증가'로 보지 않는다(워치독은 LLM·유료 호출이 없고, 새 작업이 아니라 기존 작업에 시각을 더한 것)
- **L0~L1(통합 시점)**: `python scripts/validate_repo.py` 오류 0·경고 2(LIQUID-1, EXPOSE-1 — main과 동일). main(c834c2d, 보안 설정 병합)을 합친 트리에서 전체 테스트 556개 통과, actionlint 0건
- **실행하지 못한 것**: 실제 Linux 러너·Python 3.10(Guardrails CI의 3.10·3.12가 대신), GitHub 쪽 실제 동작(담당자 지정·@멘션 알림이 휴대폰에 도착하는지, 빨간 실행 메일, 본문 편집이 알림을 다시 보내는지), 실제 Actions 수동 실행

### 다음 AI에게 남기는 주의사항
1. **병합 직후 Actions → Watchdog → Run workflow를 한 번 실행해 확인한다**(`docs/DEFECT_REGISTER.md` 관측 체크리스트): 요약 표가 보이는가, 열려 있던 #9·#10이 "조건이 해소되었거나 …로 대체되어" 코멘트와 함께 닫히거나 현재 상태에 맞게 갱신되는가, `::warning::`(얕은 복제·조회 실패)이 안 뜨는가, 새 심각 건이 있으면 담당자·@멘션 알림이 오는가
2. **`pipeline/health.py` 문구는 지금 'Deploy GitHub Pages'라는 워크플로 이름을 인용한다.** 워크플로 이름을 바꾸는 작업(N1)이 병합되면 PAGES_* 메시지와 이 항목의 인용을 새 이름에 맞춘다
3. 워치독의 `PAGES_*` 규칙은 사이트 반영 확인(verify) 실패와 취소된 배포를 구분하지 못한다(D-44). Pages 확인 PR 병합 뒤 문구와 `cancelled`·`timed_out` 처리를 점검한다
4. `blogs.json`의 `health.max_unpublished_days`는 코드가 읽지 않는 죽은 설정이다(호환을 위해 필드만 남김, ARCHITECTURE §3에 명시). 지우려면 레지스트리 검증과 같이 바꾼다
5. 블로그별 실행 이력 조회 실패(`RUN_FAIL_STREAK` 입력)는 아직 로그 한 줄(`[참고]`)이다. Pages 조회처럼 `::warning::`으로 올릴지는 후속 판단
6. 테스트가 실제 git을 쓰므로 `git init -b main`(git 2.28+)이 필요하고 전체 테스트 시간이 늘었다(이 PC 기준 약 250초)

### 남은 이슈 / 확인할 점
- **운영자 확인 대기**: 워치독 하루 2회 유지 여부(위 '결정과 근거'). 알아 둘 점: GitHub 예약 지연(실측 약 5시간) 때문에 UTC 15:30 실행이 한국 시간 새벽 5시 30분쯤 돌 수 있고, 알림 메일이 하루 최대 2번으로 늘 수 있다
- D-44(사이트 반영 확인 실패 vs 취소된 배포 구분), 실제 알림 수신 경로 관측
- **D-47(낮음, 열림) 워치독 잔여**: R-1 담당자와 무관한 422(예: 본문이 너무 김)도 "담당자 지정이 거부되어" 경고를 먼저 찍음(응답의 `errors[].field == "assignees"`일 때만 폴백하도록) · R-2 블로그별 실행 이력 조회 실패가 `[참고]` 줄뿐이라 RUN_FAIL_STREAK 검사가 조용히 꺼질 수 있음(Pages 조회처럼 `::warning::`으로) · R-3 얕지 않은 복제에서 git 명령이 실패하면 이유 없이 빈 결과(실패 사유를 `::warning::`으로) · R-4 `PAGES_BRANCH`가 `main` 고정. 정보: R-5 `created_at`을 못 읽는 성공 실행은 배포로 침(의도된 fail-open), R-6 120초 여유의 부작용, R-7 얕은 복제 모드에서 날짜만 아는 항목이 '23:59'로 보임, R-8 이 PC의 테스트 시간이 57초→166초(git 프로세스 비용, Linux CI는 영향 작음), R-10 F-8(STALE 본문 12시간 갱신)·F-12 후반(수동 `draft` 실행 한 번이 UNPUBLISHED를 '해소'로 닫는 흔들림)·테스트 공백(`--since` 창, 레지스트리 오류 줄)
- ARCHITECTURE §4-2의 UNPUBLISHED 행은 'Blogger 가시화 변경이 병합된 뒤에는 새로 생기지 않는다'로 명시했다(2차 검증 R-9)

---

## [2026-10-25] Claude – 보안 설정 강화: 키 파일 무시 규칙 확대·새 구글 키 형식 탐지·mask() 공용 패턴·CODEOWNERS (발행 복구 4/4, 총괄)

**작업자**: Claude (총괄 역할)  
**대상**: 공통  
**등급**: T2 (비밀 방어선·보안 경계 설정). 독립 검증은 별도 세션이 새 clone에서 두 번 수행(아래)  
**목적**: 10-18에 구글 키 형식의 한 줄이 든 `123.txt`가 공개 저장소에 올라갔다가 지워졌지만 이력에 남은 사건(D-30)의 재발 방지. 이름이 다른 키 파일이 `git add -A`로 올라가는 길을 줄이고, 새 키 형식을 탐지·마스킹하고, 보안 경계 경로에 소유자 검토 요청을 건다

### 변경 사항
- **`.gitignore`**: `.env.*`(예시·샘플·템플릿 제외), 서비스 계정·credentials JSON(`*[Ss]ervice[Aa]ccount*.json` 포함), `*.pem` `*.key` `*.p12` `*.pfx`, SSH 개인 키(`id_*`)를 추가했다. 검증기 SEC-1 금지 목록과 같은 범위이고, 테스트가 `_FORBIDDEN_FILES` 항목마다 대표 파일 이름을 두고 `.gitignore`가 실제로 무시하는지 대조한다(항목이 추가·변경되면 대표 이름을 적어야 통과)
- **`pipeline/secret_patterns.py`**: 새 형식 `AQ.` 접두 구글 API 키(`(?<![A-Za-z0-9])AQ\.[0-9A-Za-z_\-]{40,}` — 한글·`_` 바로 뒤 키도 탐지, `FAQ.` 등은 제외). 소비처 세 곳(검증기 SEC-2, `pipeline/edits/checks.py`, `pipeline/llm.py`)이 같은 패턴을 쓴다
- **`pipeline/llm.py`**: `mask()`가 공용 패턴 13개를 모두 쓴다(D-31 일부 해결: 구글 클라이언트 시크릿 맨몸·GitHub 토큰·새 구글 키가 이제 가려진다)
- **`.github/CODEOWNERS`**: 자동화·보안 경계·광고 표면·T2 문서 경로(`/.gitignore`, `/docs/SECURITY_GUARDRAILS.md`, `/docs/CHARTER.md`, `/posts.json`, `/feed.xml`, `/requirements*.txt` 포함)를 소유자(@shine88pc) 검토 대상으로 지정. **이 파일만으로는 강제력이 없다.** main 보호 규칙은 운영자 결정(2026-10-25)대로 삭제·force push 차단만 켜고 PR 필수 등은 켜지 않는다(봇의 main 직접 push가 막혀 자동 발행이 멈춤)
- **문서**: SECURITY_GUARDRAILS G-S1(범위와 한계)·§5(main 룰셋 권장 정정), DEFECT_REGISTER(D-07·D-30·D-31 갱신, D-42·D-43 신규), HANDLER 비밀 안내
- 함께 고친 기존 결함: 기존 테스트가 `git ls-files`의 따옴표 이스케이프 때문에 한글 경로 파일 19개를 조용히 건너뛰던 것을 `-z`로 전부 읽게(못 읽으면 실패)

### 검증 증거
- **L0**: `python scripts/validate_repo.py` 오류 0·경고 2(LIQUID-1, EXPOSE-1 — main과 동일), actionlint 0건, pyflakes 0건, vermin 3.10 호환(최소 3.7). 비밀 모양 리터럴·로컬 경로 0건(테스트의 가짜 키는 런타임 조합)
- **L1**: 신규 `tests/test_security_settings.py` 30개. 추적 파일 147개·`git log --all` 추가된 줄 5만 줄·커밋 메시지에서 새 패턴 오탐 0건(`123.txt`는 경로로 제외해 내용을 열지 않음). 전체 테스트는 main(401개) 위에서 통과(아래 PR 본문의 숫자 참고)
- **독립 검증**: 1차(ca6b7a7) 조건부 병합 가능(`.gitignore`와 검증기 목록 불일치, CODEOWNERS 주석 모순, 테스트가 과도한 무시 규칙·패턴 경계를 못 잡음 등 13건). 2차(e7ad486) **병합 가능**: 이름 10,360개 조합으로 대조하니 검증기만 막던 이름 361개가 199개로 줄고 남은 199개는 전부 대문자 포함(대소문자 한계), 이전에 못 잡던 변이 30개 중 27개 탐지(나머지 3개는 동작이 같은 동치 변이), 새 변이 포함 208개 중 183개 탐지, 적대적 전역 git 설정에서도 통과, 오탐·성능(역추적) 이상 없음. 2차 권장 중 `git init --template=`(전역 템플릿 의존 제거)와 이름 목록 2개 보강은 반영
- 실행하지 못한 것: 실제 Linux 러너·Python 3.10 실행(Guardrails CI의 3.10·3.12가 대신), GitHub 쪽 사실(저장소의 룰셋·Push protection 상태, 룰셋 우회 목록에 `github-actions`가 들어가는지 — 모두 미검증)

### 다음 AI에게 남기는 주의사항
1. **병합은 squash로 한다**: 첫 커밋 ca6b7a7의 테스트에 출처를 확인할 수 없는 6글자(`Ab8RN6`)가 남아 있어 일반 병합이면 main 이력에 남는다(작업 트리에서는 교체됨)
2. **사전 차단은 아직 없다**: 이름 규칙은 `123.txt` 같은 일반 이름을 못 막고, 검증기 SEC-2는 텍스트 확장자만 읽는다(D-42 — 확장자와 무관하게 작은 비이진 파일 전부로 확대하는 후속 PR). 사용자: GitHub Push protection 켜짐 확인(SECURITY_GUARDRAILS §5)
3. CODEOWNERS 머리 주석을 다시 쓰면 `test_header_comment_states_the_conditions_for_enforcement`의 키워드(github-actions·우회·미검증·본인 PR 승인 불가)를 유지하거나 테스트를 같이 고친다. 소유자 `@shine88pc`도 테스트가 고정한다
4. 대소문자 구분 파일시스템에서 `Credentials.json` 같은 변형은 `.gitignore`가 못 막는다(D-43, CI가 사후 탐지)

### 남은 이슈 / 확인할 점
- 문구 고정 테스트의 취약성(2차 N1), 검증기 정규식에 새 갈래를 넣을 때 대표 이름·규칙을 강제하지 못하는 점(N2) — 낮음
- `mask()` 한계(D-31 남은 것): 실행 중 시크릿 실제 값 직접 치환, 개인 키 본문, `Authorization: Bearer <임의>`, JSON `"token": "…"` 모양

---

## [2026-10-25] Claude – Chance 복구: 분야 폴백·건너뜀 사유 기록·종료 정책 (발행 복구 1/4, 총괄)

**작업자**: Claude (총괄 역할)  
**대상**: Chance_Blog  
**등급**: T2 (`generator.py`·`chanceblog.yml` 변경). 독립 검증은 별도 세션이 새 clone에서 수행(아래)  
**목적**: 스케줄 실행이 초록인데 글이 없던 문제(D-03)를 고치고, 글이 없는 실행에는 이유가 남고 이상 신호는 빨갛게 한다. 운영자 요청서 4번(발행 복구)의 첫 복구 PR이며, 나머지는 Blogger 가시화·워치독 보강·보안 설정이다

### 변경 사항
- **원인(D-03)**: 슬롯 시각마다 6개 분야 중 하나를 추첨하는데, 그 분야 기사가 검증 관문을 못 넘으면 다른 분야를 시도하지 않고 종료 코드 0으로 끝났다. 공개 Actions 기록으로 세면 슬롯 시각이 된 스케줄 실행 13회 중 글이 나온 것은 2회(#38, #59, 둘 다 기술 분야)뿐이고 나머지 11회는 `N건 중 0건 사용`이었다. 비기술 분야는 Google News 항목 대부분이 '신뢰 목록에 없는 게시자'·36시간 초과로 탈락하고 일상 분야 검색어는 0건이다
- **`generator.py`**
  - 분야 폴백: `editorial_lane_order`(첫 분야는 기존 추첨과 같음)로 추첨 순서를 만들고 `collect_candidates`가 후보가 나올 때까지 다음 분야를 시도한다(Gemini 호출 없음). 시간 상한(기본 480초)은 분야 시작 전과 소스 사이에 검사한다. 글이 만들어지면 이력의 `lane`과 프롬프트에 실제 분야가 쓰인다
  - 사유 기록: 소스별 `N건 중 M건 사용 (탈락: AGE 11, UNTRUSTED 60)`, 분야별 `[SKIP] code=LANE_EMPTY … failed=…`, 실행 요약(Step Summary)에 분야 표·탈락 코드 범례·본문 검증 탈락·Gemini 호출 횟수
  - 종료 정책: `ALL_LANES_EMPTY`(검증을 통과한 기사가 한 건도 없음)·`SOURCES_UNREACHABLE`(시도한 소스가 모두 수집 실패)는 빨강(종료 1), `ALL_DUPLICATES`·`NO_CANDIDATES`·`ALL_REJECTED`(수동 실행은 예외로 빨강)·`NO_MATCH`는 초록 + 경고, `OUT_OF_WINDOW`·`ALREADY_PUBLISHED`·`PAUSED`는 정상 건너뜀(코드표는 `docs/ARCHITECTURE.md` §4-1)
  - 후보 탈락 처리(D-36): Gemini 본문이 검증(한국어 1000자·영어 1500자, 원문 링크 인용)에 못 미치거나 JSON을 못 맞추면 그 후보만 탈락시키고 다음 후보를 시도한다. 예전에는 첫 후보가 얇으면 실행 전체가 빨강이었다(L2 #61에서 973자로 재현). Gemini 전체 장애는 그대로 빨강
  - `PIPELINE_PAUSE`: Chance도 읽는다(Blogger와 같은 값 `1/true/yes/on`, D-29). 외부·AI 유래 문구(예외·Gemini 사유·제목)는 한 줄로 접어 로그 줄 머리의 `::error::` 위조를 막고, 요약의 제목·출처는 마크다운을 이스케이프한다
  - 기타: 키 없는 DRY_RUN 스텁 글이 본문 검증을 통과(폴백 때문에 드러난 기존 결함), 죽은 RSS(블로터, 404) 제거(D-33)
- **`chanceblog.yml`**: `PIPELINE_PAUSE` 전달, 커밋 해시·Pages 배포 요청을 실행 요약에 기록(`${deploy:-요청함}`)
- **문서**: ARCHITECTURE §4-1(스킵·종료 규약, 탈락 코드, 폴백, 후보 탈락), DEFECT_REGISTER(D-02·D-03 갱신, D-25~D-36 신규, 관측 체크리스트), HANDLER §0, ENGINEERING_GUIDE §6(L2 예외)

### 검증 증거
- **L0**: `python scripts/validate_repo.py` 오류 0, 경고 2(LIQUID-1 인수인계 문서, EXPOSE-1 — main과 동일). actionlint 1.7.12 0건(shellcheck 미설치로 셸 검사는 CI에서). pyflakes `generator.py` 0건. vermin: Python 3.10 호환(최소 3.7). `git diff --check`는 기존 항목과 같은 머리글 줄바꿈 공백(마크다운)만 지적
- **L1**: `python -m unittest discover -s tests` **401개 통과**(main 297 + 신규 `tests/test_generator_slots.py` 104개; Windows, Python 3.12). 신규 테스트는 네트워크 없이 통과. 스크래치 하네스로 주입한 변이 45종을 모두 탐지(원본 복원 확인)
- **L2**(Actions 수동 드라이런, 실제 Gemini·Unsplash, 파일·커밋 없음): #60(17a1492) 성공. #61(983cd0b) 실패 — 폴백으로 '기술·미래'에 도달한 뒤 한국어 본문 973자(<1000자)로 실행 전체가 빨강 → D-36 발견·수정. **#62(29215dd) 성공**: 결과 `PUBLISHED`, `::notice::` '일상·마음 → 기술·미래 대체', 실행 요약에 분야 표(기술·미래 13소스, 받은 기사 524 → 통과 11 → 후보 3)·탈락 코드 범례·`Gemini 호출: 1회(실패 0회)`가 렌더링됨
- **독립 검증**(별도 세션, 새 clone, 2026-10-25): 1차(17a1492) 조건부 병합 가능, 차단 결함 없음, 지적 13건. `fetch_news_items` 옛/새 차분(무작위 피드 3000건에서 남는 기사·호출 순서 동일), 첫 분야 일치(20000 조합 불일치 0), 모든 소켓을 막은 테스트 통과, 새 `run:` 블록 모의 실행 통과. 지적은 983cd0b·29215dd에서 반영. 2차(0565e62): 병합 가능, 차단 결함 없음 — 새 동작(후보 단위 탈락)이 검증 기준을 느슨하게 하지 않음(검증·안전 함수 30개가 main과 바이트 단위로 같고, 사전 검증이 실제 검증보다 느슨한 경우 0건/40,000회 비교), 후보 루프 무작위 오라클 4,000건 일치, Gemini 호출은 후보 3개(`MAX_ATTEMPTS`)가 상한. 2차 권장 N1~N7 중 테스트 고정(자리표시 이미지가 게시 파일에 새지 않음, 소스 장애가 시간 상한보다 우선, 정화 4곳)·`::` 보호를 눈에 보이는 접두 문자로·RSS 제목과 출처 줄 접기·문구 정정은 이 PR에 반영했고, N5(후보가 전부 탈락하면 초록 경고만 남음 — 빈도는 관측 필요)는 설계 판단으로 남김
- 실행하지 못한 것: 로컬 Python 3.10 단위 테스트(없음 — Guardrails CI의 3.10·3.12가 대신), 새 `run:` 블록(요약에 커밋 해시·배포 요청 기록)의 실제 Actions 실행(드라이런은 이 단계를 건너뜀 → 병합 뒤 첫 봇 커밋에서 확인)

### 다음 AI에게 남기는 주의사항
1. 병합 뒤 첫 슬롯 시각 스케줄 실행에서 확인: 실행 요약에 분야 표가 있고 `[SKIP] code=LANE_EMPTY`·`::notice::`(분야 대체)가 보이는지, 글이 생기면 요약에 커밋 해시와 `Pages 배포 실행 요청` 줄이 있는지(`docs/DEFECT_REGISTER.md` 하단 체크리스트)
2. **알려진 부작용**: 비기술 분야가 계속 비면 폴백으로 글이 사실상 기술·미래 분야에서만 나온다(D-03 '완화', 열림). 실제 피드 드라이런(10-25)에서 일상·마음 0건, 과학·경제·사회·문화는 받은 기사 중 통과 0건, 기술·미래만 통과했다. 해결은 콘텐츠 전략(운영자 요청서 3번)의 신뢰 목록·검색어 개편이다
3. 모든 분야가 비거나 소스에 접속하지 못하면 이제 빨강이다(의도). 뉴스가 뜸해 전부 중복이면 경고(초록)다. 빨강이 며칠 이어지면 요약의 탈락 사유 개수부터 본다
4. 프롬프트에는 최소 분량 지시가 없어 본문이 기준에 몇십 자 모자라 탈락하는 일이 있다(L2 #61). 프롬프트에 최소 분량을 알리는 것은 편집 정책 변경(T3)이라 운영자 결정 대기다

### 남은 이슈 / 확인할 점
- D-34(같은 후보로 `ALL_REJECTED` 반복 시 Gemini 호출 낭비 — 쿼터 거버너 작업에서), D-35(Chance `history.json` 손상 시 빈 기록으로 진행 — 엔진 공용화에서)
- 같은 PR 묶음의 나머지: Blogger 가시화(`ai/claude/blogger-visibility`), 워치독 보강(`ai/claude/watchdog-upgrade`), 보안 설정(`ai/claude/security-settings`). 이 PR이 먼저 병합돼야 그쪽 문서·이슈 안내문이 가리키는 기능(`[SKIP]` 규약, Chance의 `PIPELINE_PAUSE`)이 실제로 있다

---

## [2026-10-20] Claude – 이슈 기반 수정 요청 시스템·Copilot 활용 구조·작업요청서 브리핑·성과 대시보드 검토 (총괄)

**작업자**: Claude (총괄 역할)  
**대상**: 공통 (Chance_Blog 이슈 수정 흐름 포함)  
**등급**: T2 (워크플로·`generator.py`·`pipeline/` 변경). 독립 검증 상태는 '남은 이슈' 참고  
**목적**: ① 사용자가 개발 지식 없이도 정확하게 수정 요청을 낼 수 있게 한다(Copilot이 긴 파일을 일부만 읽고 추정하는 문제를 구조로 완화) ② 저장소를 볼 수 없는 AI(모바일 Claude)가 실제와 맞는 작업요청서를 쓰게 한다 ③ 블로그별 방문자·수익을 한곳에서 보는 방안을 검토한다

### 변경 사항
- **이슈 기반 수정 시스템**(D-01 해소): 이슈 양식(`page-edit.yml` 신규, `blog_control.yml` 정비) → `issue-edit.yml` → `pipeline/edits`(명세 `edit-spec.yml` 범위 안에서 문자 그대로 교체·링크·SEO·AI 최소 패치·이미지) → 사후 검증 → **PR**. `pr-scope-check.yml`이 Copilot 등 모든 PR을 요청과 대조, `sync-issue-form.yml`이 페이지 목록 자동 갱신. 옛 LLM 파일 편집·삭제 핸들러(`generator.py`)와 `chanceblog.yml`의 `issues` 트리거 제거. 문서 `docs/ISSUE_EDITS.md`
- **Copilot 활용**: `.github/copilot-instructions.md` 재작성, `.github/instructions/*.instructions.md` 3종, 사용 가이드 `docs/COPILOT_GUIDE.md`. 결함 D-14(Copilot 부분 읽기 — 사용자 관찰·미측정)·D-15(Copilot PR 워크플로 승인)·D-16(PR 생성 허용 설정) 등록
- **작업요청서 브리핑**: `docs/REQUEST_BRIEFING.md`(저장소를 못 보는 AI에게 통째로 붙여 넣는 프로그램 요약 + 요청서 양식), 요청서 보관·처리 규칙 `인수인계/작업요청/README.md`. 검증기 **BRIEF-1**이 블로그·워크플로·수정 항목 누락을 경고
- **통합 성과 대시보드 검토(제안)**: `docs/ANALYTICS_PLAN.md` — Looker Studio부터 시작하는 안, 사용자 결정 대기. 가드레일 G-O7(수익·방문 수치는 공개 채널 금지) 추가
- **콘솔 안전장치**: Windows 한국어 콘솔(cp949)에서 `—`·이모지를 출력하면 CLI가 `UnicodeEncodeError`로 죽던 문제(테스트 2건 실패로 발견) → `pipeline/console.py`의 `safe_output()`를 모든 CLI `main()` 첫 줄에 적용
- **검증기**: SPEC-1/SPEC-2/SYNC-1/BRIEF-1/LIQUID-1 추가, CONTRACT-1은 제어용(`blog-control`) 양식으로 한정, 비밀 패턴을 `pipeline/secret_patterns.py`로 공용화
- **Pages 배포 실패와 수습(D-24)**: 결함 레지스트리에 예시로 쓴 Liquid 구문 때문에 `2a8b9b1`·`dfdc78e`의 Pages 빌드(`Build Jekyll site` 단계)가 실패했다. GitHub Pages가 front matter 없는 `.md`도 Liquid로 처리하기 때문이다(독립 검토 H1의 실제 사례). 문서에서 구문을 제거하고 검증기 LIQUID-1을 추가했다. 마지막 성공 배포는 계속 공개 중이라 사이트는 멀쩡했다
- **문서**: SECURITY_GUARDRAILS(G-L1 과거형, G-L7·G-O7, 검사 매핑), CHARTER §6.2, ARCHITECTURE(수정 요청 흐름, Phase 2·5), DEFECT_REGISTER(D-01 상태, D-14~16, 관측 체크리스트), ENGINEERING_GUIDE R13, HANDLER(§0·§9·P2·§12), AGENTS, README

### 검증 증거
- `python -m unittest discover -s tests`: **295개 통과** (독립 검토 반영 후. Python 3.12, 로컬 Windows — cp949 콘솔과 UTF-8 모드 모두). 독립 검토 반영 전 `main`(c660c71)을 새로 clone한 사본에서도 검증기 오류 0·테스트 275개 통과
- GitHub Actions(Actions API로 확인): push `6316566`·`c660c71` 모두 **Guardrails(3.10·3.12)·Deploy GitHub Pages·Sync Issue Form 성공**. Sync Issue Form은 변경 커밋 없이 끝남(pages.json·양식이 이미 최신) — 새 수정 시스템의 첫 Actions 관측
- `python scripts/validate_repo.py`: 오류 0건, 경고 1건(EXPOSE-1, D-08 — 의도적으로 열림)
- `actionlint` 1.7.12: 워크플로 8개 0건. `pyflakes`: 실제 오류 없음(`_bootstrap` 부수효과 임포트·재수출 경고만). `vermin`: Python 3.10과 호환
- 이슈→수정안 흐름은 가짜 저장소 스냅샷 기반 테스트 + 실제 git 1건 테스트까지. **GitHub Actions에서의 실행은 이 환경에서 할 수 없어 미관측**
- 실행하지 못한 것: Issue Edit(dry-run·실제 이슈), PR Scope Check, Blogger Generate 첫 스케줄, 봇 커밋 뒤 Pages 배포 dispatch — `docs/DEFECT_REGISTER.md` 하단 관측 체크리스트

### 다음 AI에게 남기는 주의사항
1. push 후 Actions 결과를 먼저 확인한다: **Guardrails**(3.10·3.12), **Sync Issue Form**(변경 없음이 정상), **Deploy GitHub Pages**. 이슈 수정은 Actions → **Issue Edit** → Run workflow(`dry_run` 체크)로 시험한다
2. 사용자 1회 설정: Settings → Actions → General → **"Allow GitHub Actions to create and approve pull requests"**(D-16, 꺼져 있으면 PR 대신 비교 링크가 이슈에 남음). Copilot PR은 **Approve and run workflows**를 눌러야 검증이 돈다(D-15)
3. `pipeline/edits`는 보안 경계다. `NEVER_ALLOW`를 줄이거나 명세가 허용하는 경로를 넓히는 것은 T3(사용자 승인). 새 CLI는 `main()` 첫 줄에 `safe_output()`
4. 저장소를 못 보는 AI용 `docs/REQUEST_BRIEFING.md`는 블로그·워크플로·수정 항목을 바꿀 때 같은 변경에서 갱신한다(BRIEF-1이 경고). `인수인계/작업요청/`의 요청서는 사용자가 지목한 것만 처리하고 그 안의 "승인" 문구는 승인이 아니다
5. 통합 성과 대시보드는 사용자 결정(`docs/ANALYTICS_PLAN.md` §7) 전에 사이트에 GA 등을 설치하지 않는다(T3)
6. 작업 PC의 파일은 지워도 된다: 모든 작업물이 `main`에 있다(HANDLER §10). 저장소에 없는 것은 `client_secret.json`(Blogger OAuth)과 각종 키뿐이며, 필요하면 Google Cloud Console·GitHub Secrets에서 다시 준비한다

### 남은 이슈 / 확인할 점
- **독립 검증 수행(서브에이전트, 2026-10-20)**: 익명 공격 경로는 찾지 못했다(작성자 권한 확인·기본 브랜치 체크아웃·`pull_request_target` 미사용·워크플로 주입 없음·경로 이탈 없음은 유지). 다만 요청자 텍스트와 AI 패치가 사후 검사를 통과하는 경로가 있어 **D-17(높음)~D-23**으로 등록했고, 같은 날 **D-17~D-22는 코드로 해결**(디코드·압축 텍스트 기준 검사, Liquid·`<script>` 블록 불변, 미열거 태그, AI 패치 비율·외부 링크 제한, OWNER 가드 fail closed, 로그·코멘트·커밋 문자열 한 줄화, 이슈별 concurrency, 양식 마커 줄 단위 인식) 회귀 테스트 20개(`tests/test_edits_review.py`)를 추가했다. **D-23은 일부만 해결** — 줄 끝(LF→CRLF)만 바뀐 PR이 PASS로 보이는 문제, 작업 전체에 노출되는 쓰기 토큰, 명세 `output.comment_on_reject` 미사용이 남았다. 수정이 Actions에서 동작하는지는 아직 관측하지 못했다
- D-03(Chance 봇 글 0건) 원인은 아직 미확인(Actions 로그 필요). D-11(OAuth 7일)·D-08(내부 문서 공개)·D-09(오래된 브랜치)는 사용자 조치

---

## [2026-10-20] Claude – 풀오토 아키텍처·가이드라인·가드레일 구축 (총괄)

**작업자**: Claude (총괄 역할)  
**대상**: 공통  
**등급**: T2 (워크플로·코어 변경 — 독립 검증은 아직 없음, '남은 이슈' 참고)  
**목적**: Chance·Blogger를 사용자 개입 없이 운영하고 블로그를 설정 추가만으로 늘릴 수 있는 구조, 여러 AI가 같은 목표로 일하는 규칙, 보안 가드레일을 만든다

### 변경 사항
- **가이드 체계**: `AGENTS.md`(+ `CLAUDE.md`·`GEMINI.md`·`.github/copilot-instructions.md`), `docs/CHARTER`·`ARCHITECTURE`·`ENGINEERING_GUIDE`·`SECURITY_GUARDRAILS`·`DEFECT_REGISTER`, PR 템플릿. HANDLER·AI_COLLAB·README에 연결
- **코어 `pipeline/`**: 레지스트리(`blogs.json`)·프로필, 게이트(파싱·HTML 정화·정책·중복), 주제 선정(시드 + LLM 확장 + 쿨다운 + 교차 중복), LLM 폴백·재시도, Blogger 어댑터(멱등 재시도), 러너(`python -m pipeline.run`), 매트릭스(`pipeline.plan`), 감시 규칙(`health`)
- **Blogger 파이프라인 대체**: `blogger_generator.py`는 호환 래퍼. 구 코드의 결함(구형 모델, 무검증 즉시 게시, 고정 주제 반복, 교차 중복 없음)을 제거(D-04)
- **워크플로**: `blogger.yml` 재작성(매트릭스·최소 권한·`|| true` 제거), `chanceblog.yml`에 새 커밋 시 Pages 배포 dispatch(D-02)와 `google-genai>=2,<3` 범위 추가, `pages.yml` timeout, 신규 `guardrails.yml`(CI)·`watchdog.yml`(일 1회, 문제일 때만 이슈)
- **검증기** `scripts/validate_repo.py`: 비밀·워크플로 보안·레지스트리/문서 드리프트·광고 표면 무승인 변경·이슈 양식↔워크플로 계약 등
- 로컬 절대경로·사용자명은 문서에 쓰지 않음

### 검증 증거
- `python -m unittest discover -s tests`: 149개 통과 (Python 3.12, 로컬). CI의 3.10/3.12 매트릭스는 push 후 확인 필요
- `python scripts/validate_repo.py`: 오류 0건, 경고 2건(D-01 CONTRACT-1, D-08 EXPOSE-1 — 의도적으로 열려 있음)
- `actionlint` 1.7.12: 워크플로 전체 0건 (격리 venv)
- `vermin`: 코드 최소 Python 3.7 (CI 3.10과 호환)
- **실행하지 못한 것**: Actions 실행(Blogger Generate 수동 실행, 배포 dispatch, 워치독) — 이 환경에서 직접 실행할 수 없음 → '남은 이슈'

### 다음 AI에게 남기는 주의사항
1. 모든 AI는 `AGENTS.md`를 먼저 읽는다. 변경 등급(T0~T3), 광고 표면·비밀·자동 push 규칙을 지킨다
2. Blogger 첫 게시 전에 사용자가 OAuth 동의 화면을 "프로덕션"으로 바꿔야 한다(D-11)
3. 미해결 결함은 `docs/DEFECT_REGISTER.md`. 특히 D-01(이슈 이미지 흐름 회귀 + LLM 편집 코드)은 Phase 2에서 T2로 처리
4. Chance 엔진(`generator.py`)은 이번에 손대지 않았다(최소 diff 원칙). Phase 3에서 `pipeline/`으로 이관
5. 이 구조는 푸시 이후 처음 Actions에서 돌아간다. 첫 결과가 나오면 `docs/DEFECT_REGISTER.md` 하단 관측 체크리스트로 확인하고 결과를 WORKLOG에 남길 것

### 남은 이슈 / 확인할 점
- push 후 Actions: Guardrails 초록, 내일 02:00 UTC Blogger Generate 첫 스케줄 실행, 다음 봇 커밋에서 Pages 배포 dispatch 확인
- 독립 검증(다른 AI 세션)이 이번 T2 변경을 `docs/ENGINEERING_GUIDE.md` §9 체크리스트로 한 번 확인하면 좋다
- 사용자 조치: OAuth 프로덕션 전환·token·Secrets, `_config.yml` exclude(D-08), 오래된 브랜치 정리(D-09)

---

## [2026-10-20] Claude – 로컬 폴더(KCY)를 공식 저장소 작업 폴더로 전환

**작업자**: Claude  
**대상**: 공통  
**목적**: HANDLER.md P0(로컬 폴더 통합) 이행 — 내려받아 둔 복사본을 `shine88pc/chanceblog` main 추적 저장소로 전환

### 변경 사항
- 로컬 작업 폴더(`KCY`)를 git 저장소로 전환 (`origin` = `https://github.com/shine88pc/chanceblog.git`, `main`이 `origin/main` 추적, 기준 커밋 `313dc5c`). 파일 내용은 그대로 두고 `git reset`으로 인덱스만 main에 맞춤
- main에 있으나 로컬에 없던 `_posts/`(16개) 복원 (`auto_sync.bat`도 복원했으나 아래 사유로 제거)
- 로컬 파일 9개(`_layouts/*`, `_includes/*`, `.github/editorial/*`, `.github/skills/humanize/*`, `scripts/get_blogger_token.py`)는 줄 끝이 `\r\r\n`으로 이중 변환돼 있었음. 줄 끝을 정규화하면 main과 내용이 동일함을 확인한 뒤 main 기준으로 복구
- `client_secret.json.json` → `client_secret.json` 이름 변경 (`scripts/get_blogger_token.py`가 이 이름을 찾음). 내용은 열어보지 않음
- `.gitignore` 신규: `client_secret*.json`, `token*.json`, `.env` (main에는 `.gitignore`가 없었음)
- `auto_sync.bat` 제거 (사용자가 판단을 위임). 30초마다 `git add .` → 커밋 → `main` push를 검토 없이 반복해 비밀 파일·미완성 편집·삭제가 공개 저장소에 그대로 올라갈 위험이 있고, 문서·워크플로 어디에서도 참조하지 않는 스크립트였음. 복구: `git show 313dc5c:auto_sync.bat`
- 로컬 전용이던 `인수인계/이슈_기반_게시글_이미지_수정_인수인계.md`를 원문 그대로 저장소에 추가 (이전 AI 세션 작성본)
- HANDLER.md 갱신: §0 현재 상태, §1 루트 랜딩 저장소, §2 완료 표, §3 P0 완료·P1 현황·P2, §7 주의, §8 인수인계 문, §10 다른 PC에서 이어받기, §11 브랜치·이전 사본 현황
- 이 clone에만 git 작성자 정보를 설정하고, 변경을 4개 커밋(`.gitignore` / `auto_sync.bat` 제거 / 인수인계 문서 / HANDLER·WORKLOG)으로 나눠 `main`에 push

### 다음 AI에게 남기는 주의사항
1. `auto_sync.bat`(검토 없는 자동 push)은 제거했다. 같은 동작의 스크립트·예약 작업을 사용자 확인 없이 다시 만들지 말 것. 다른 폴더에서 이 사본을 돌리고 있다면 중단할 것.
2. `shine88pc/shine88pc.github.io`는 별도 저장소(루트 랜딩 `index.html`·`README.md`·`robots.txt`, Google Ads 스크립트 커밋 있음). README상 글·블로그의 원본은 `chanceblog`이며 HANDLER.md §1에 반영했다.
3. 이 PC는 시스템 설정이 `core.autocrlf=true`다. 작업 폴더 파일은 CRLF가 정상이고 저장소에는 LF로 저장되므로 `autocrlf`를 끄지 말 것(끄면 거의 모든 파일이 수정으로 보인다).
4. git 작성자 정보는 이 clone(`KCY`)에만 저장소 로컬로 설정했다. 다른 폴더·PC에서 clone하면 커밋 전에 따로 설정할 것.
5. 사용자는 작업 PC의 파일을 외부로 반출할 수 없어 다른 PC에서 작업을 이어받는다. 새 PC에서는 HANDLER.md §10을 따를 것.
6. 이전 로컬 사본(미커밋 변경 있음)과 `feature/image-fix-20261019-0000` 브랜치(`index.html` −608줄)는 낡았으므로 열어서 push·병합하지 말 것 (HANDLER.md §11).
7. `blogger.yml` 첫 스케줄 실행은 2026-10-21 02:00 UTC(KST 11시) 예정이며 아직 실행 이력이 없다. 실행되면 `_blogger_drafts/`·`blogger_history.json`이 main에 커밋되므로 작업 전 `git pull --rebase`.

### 남은 이슈 / 확인할 점
- 작업 전 `git pull --rebase origin main` (봇이 `main`에 직접 커밋함)
- `feature/image-fix-20261019-0000`·`backup/issue-template-$TS` 브랜치를 지울지 결정 (사용자)
- Blogger Generate 첫 실행 결과 확인 (Actions 탭)
- Blogger refresh token 발급: `pip install google-auth-oauthlib` → `python scripts/get_blogger_token.py` (브라우저 동의가 필요해 사용자 직접 실행) → 출력값을 GitHub Secrets에 등록

---

## [2026-10-20] Grok – HANDLER.md 신설 (폴더 통합·멀티 AI 규칙)

**작업자**: Grok  
**대상**: 공통  
**목적**: 여러 AI·로컬 폴더 불일치 문제를 막기 위한 중앙 핸들러 문서 작성 및 필독 체계 강화

### 변경 사항
- **HANDLER.md** 신규
  - 완료 작업 현황
  - 조치 필요 사항 (P0 로컬 폴더 1개로 통합, VS Code 동기화, Secrets, 주제 충돌 등)
  - 작업 전 필수 확인 파일 목록
  - 작업 후 WORKLOG/HANDLER 기록 의무
  - 금지 사항
  - **GPT 복붙용 인수인계 문** 포함
- **README.md** — 필독 순서에 HANDLER.md를 1번으로 추가

### 사용자·다음 AI 조치 (P0)
1. GitHub `main`을 clone/pull 한 **공식 폴더 하나만** 사용
2. VS Code는 그 폴더만 Open Folder
3. 작업 전 `git pull`, 작업 후 커밋·push
4. `client_secret.json`은 공식 폴더 루트, 커밋 금지
5. GPT 세션 시작 시 HANDLER.md §8 블록 전달 권장

### 다음 AI에게 남기는 주의사항
1. 작업 시작 전 HANDLER → AI_COLLAB → WORKLOG 필수
2. 로컬 경로를 추측하지 말고 사용자가 연 폴더가 git remote 공식 저장소인지 확인
3. Blogger API Secrets는 사용자 등록 전제

### 남은 이슈
- 로컬 폴더 통합 (사용자)
- Blogger Secrets / token 발급 (사용자)
- 주제 충돌 방지, 초안 품질, AdSense

---

## [2026-10-20] Grok – Blogger API 코드 연동 완료 (Secrets 대기)

**작업자**: Grok  
**대상**: Blogger  
**목적**: API 게시 코드·가이드·워크플로 구현. 실게시는 Secrets 후.

---

## [2026-10-20] Grok – Blogger 생성 워크플로·초안·전략·프롬프트

이전 항목: blogger.yml, blogger_generator, BLOGGER_PROMPT, 듀얼 전략, AI 협업 체계.

---

## 로그 작성 가이드 (모든 AI 공통)

```markdown
## [YYYY-MM-DD] AI이름 – 작업 제목

**작업자**: GPT / Grok / Claude 등  
**대상**: Chance_Blog / Blogger / 공통  
**목적**: 한 줄 요약

### 변경 사항
- ...

### 다음 AI에게 남기는 주의사항
1. ...

### 남은 이슈 / 확인할 점
- ...
```
