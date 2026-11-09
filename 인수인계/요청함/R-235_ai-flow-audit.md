---
id: R-235
kind: info
title: [R-235] 진행 현황 P021 — AI 흐름 전수 확인 결과(확인 요청 007 조건 ①): 지금 길 0개
summary: 확인 요청 007 조건 ① 보고입니다. 지금 병합된 코드·작업 가지·데스크톱 어디에서도 구조화 Fact 자료가 AI 단계로 흘러가는 길은 0개입니다(그 자료로 만든 글도 연결 코드도 아직 없음). 다만 2단계를 방어 없이 이으면 9곳이 열려 요구사항 18개를 세웠고 안전 기본값으로 진행합니다. 하실 일 없음.
urgency: 보통
created: 2026-11-10
no: P021
work: R-232
at: 2026-11-10 08:12
now: AI 흐름 감사 결과 보고 · 독립 검증 3건(Gate·M036 합성본·주간 상한 구현) 진행 · M036 검사 12칸 초록
changed: 007 조건 ① 감사 끝(길 0개·2단계 방어 요구사항 18개) · M036 검사 초록(PR 47)
next: M036 병합 부탁 → 방어 묶음(표식·키 미전달·방벽) → Gate·잠금·Fact·허용 목록 병합 → Fact 단계 2(규칙 기반)
eta: 블로그 병합 8–10건·데스크톱 1건 남음 — 11-14 무렵(추정). 재개는 계획 승인 뒤 11-20 전후(추정)
waiting: 운영자 답 대기 없음 · 병합 대기 없음(M036 은 검증 뒤 발송)
check: 이상 없음
---

# 진행 현황 P021 — AI 흐름 전수 확인 결과 (확인 요청 007 조건 ①)

조건 ① 은 "수집부터 발행까지 이 자료(캐나다 통계청·영국 정부 콘텐츠 API·미국 NOAA 우주날씨의 구조화 Fact 값과 그 값이 들어간 글자)가 AI 단계(번역·요약·다듬기·이미지 설명·품질 검사)로 흘러가는 길이 없는지 전수 확인 후 보고" 입니다. 읽기 전용 감사로 확인했고, 결과는 아래와 같습니다. 이 보고는 공개 글·설정·광고를 바꾸지 않습니다.

## 한눈에
- **지금 길은 0개입니다.** 지금 병합된 코드(Fact 1단계), 작업 중인 가지들, 데스크톱 앱 어디에서도 이 자료가 AI 단계로 흘러가는 길이 없습니다. 이유는 단순합니다 — 이 자료를 쓰는 코드가 아직 어디에도 연결되지 않았고, 이 자료로 만든 글이 아직 한 편도 없습니다. AI 를 부르는 곳은 코드 전체에서 정해진 9곳뿐이고 Fact 쪽 코드와 한 번도 만나지 않으며(임포트 그래프 양방향 폐포 0), 데스크톱은 AI 호출 코드 자체가 0입니다. 품질 검사·번역·요약·이미지 설명(alt)도 AI 가 하는 단계가 없습니다(AI 가 만드는 것은 영어 이미지 검색어뿐).
- **2단계(생성기 연결)를 방어 없이 이으면 9곳이 열립니다.** 가장 큰 이유는 Fact 글의 **제목에 숫자가 들어 있다**는 점입니다(예: `○○ 실업률 3.5%(2026년 3월 기준), 앞 기간보다 0.3%p 높아`). 기존 코드는 ① 새 글을 쓸 때 최근 글 제목 30개 ② 사진을 교체할 때 글 제목·태그·분류 ③ Blogger 글을 다시 쓸 때 다른 블로그 제목 ④ 이슈로 사진을 바꿀 때 글 제목·태그를 AI 에 보냅니다. 가짜 자료로 만든 글을 두고 실제 코드를 돌려 보니 네 곳 모두 제목과 숫자가 AI 입력에 들어갔습니다(첫 문단·본문은 가지 않습니다). 이 밖에 작업 중인 그림자 실행(가지 gate)이 AI 를 따로 한 번 더 부르고, 허용 목록 가지의 약속('자체 제목은 AI 에 보낸다')과 Fact 문서의 약속('facts 에서는 AI 호출 없음')이 서로 다릅니다.
- **세 제공처는 지금 켤 수 없는 상태입니다(안전한 쪽).** 'AI 에 쓰지 않는다'를 적을 칸이 없어 적으면 '완전 제외'로 계산되고, 출처 표시 문구가 비어 있고, 경로 종류가 섞여 있고, 호출 한도 값이 비어 있습니다 — 이것들은 조건 ② 의 선행 작업입니다.
- **막는 방법**: 2단계 요구사항 18개(핵심 5개 — ① 후보를 받는 함수를 하나로 하고 Fact 분기에서 AI 호출 0을 시험으로 고정 ② `facts` 로 돌 때는 AI 키를 아예 주지 않음 ③ Fact 글에 표식을 달고 사진 교체·최근 제목·이슈 수정·Blogger 가 그 글을 AI 입력에서 제외 ④ AI 호출 직전에 프롬프트를 훑어 Fact 글 제목이 있으면 막는 방벽(의역·번역은 못 막으니 ①②③ 이 먼저) ⑤ 레지스트리에 '이 자료는 AI 에 쓰지 않는다'를 적을 값을 새로 만듦)와 자동 점검 8종(시제품으로 일부러 어긴 코드 14개 중 13개를 잡음, 1개는 알려진 사각지대)을 제안받았습니다. 전체 표는 아래 부록입니다.

## 정해 둔 기본값 (위임 규칙의 안전 기본값 — 다른 뜻이 있으시면 `[요청]` 으로 알려 주세요, 안 바뀌면 이대로 진행합니다)
1. **영문판**: Fact 글은 국문 단독(`languages: ["ko"]`)이고 AI 번역은 금지입니다(감사 선택지 A). 규칙 기반 영어 틀은 큰 작업이라 별도 승인 전까지 하지 않습니다.
2. **제목**: Fact 글 제목에는 숫자·값을 넣지 않고 라벨·지역·기준일만 넣습니다(예: `○○ 실업률, 2026년 3월 기준 — 숫자로 읽기`). 이렇게 하면 위 9곳 중 6곳이 '값이 든 글자'에서 '이름만 간접'으로 내려갑니다. 값이 든 제목은 방어 묶음이 모두 선 뒤에 따로 승인받아 바꿉니다.
3. **이미지**: Fact 글은 사진 교체·보강 대상에서 제외하고(표식으로 거름) AI 가 고르는 이미지를 쓰지 않습니다. 이미지는 지금은 없음 또는 사이트 공용 이미지이고, 규칙으로 만드는 글마다 다른 그림은 별도 작업입니다.
4. **문서 확정**: 이 세 곳 자료에는 AI 서술·번역·요약·다듬기·이미지 설명 단계를 만들지 않는다는 문장을 Fact 경로 문서와 허용 목록 문서에 못박고, 두 문서가 서로 다르게 말하는 곳(F7)을 한 가지 말로 고칩니다.
5. **켜기**: 레지스트리 스키마 변경과 제공처별 확인(7칸 재확인·호출 한도·출처 표시 문구 자동 첨부)을 끝낸 뒤에야 켜는 변경을 **따로 병합 부탁**으로 올립니다(조건 ② 그대로 — 켜는 허가가 아닙니다).

## 순서와 일정에 주는 영향
- **새 '방어 묶음'**(표식·표식 소비자 제외·런타임 방벽·이미지와 Blogger 사유·읽기 경로·AI 흐름 자동 점검)을 만들어 생성기 연결(2단계)보다 **먼저** 병합합니다. 허용 목록 묶음에는 스키마 변경(`ai_blocked` 류 값)·출처 문구 자동 첨부·호출 한도 강제가 더해집니다. 병합 뒤 합쳐진 트리에서 이 감사를 한 번 더 돌립니다(감사는 가지별로만 읽었습니다).
- 진행 중인 Gate·잠금 후속·주간 상한(주 2편)·Fact 후속은 그대로입니다. 그 결과 병합이 블로그 8–10건·데스크톱 1건으로 늘어 병합은 11-14 무렵(추정), 켜는 변경과 그림자 실행 3회·초안 평가를 거친 재개는 **감사·보완 계획 승인 뒤**(앞서 말씀드린 확인 요청 008)로 11-20 전후(추정)입니다.
- 순서는 안전 쪽으로만 바꿉니다. 공개 글·설정·광고·정지 변수는 이 보고로 바뀌지 않습니다.

## 이 보고의 한계(솔직하게)
- 감사는 읽기 전용 에이전트 하나가 했고 **독립 재확인은 아직**입니다(2단계 구현 검증 때 방어 시험과 함께 다시 확인합니다). 합쳐진 트리는 가지들이 아직 병합 전이라 **미확인**이고, 정적 분석이 놓치는 이름 조립·콜백·`operator.attrgetter` 같은 것은 런타임 방벽과 키 미전달이 맡습니다.
- 공개된 뒤에 외부 AI 가 글을 읽는 것, 운영자의 코딩 AI 세션이 저장소를 읽는 것은 코드 경로 밖이라 감사하지 않았습니다. 제공처의 실제 호출 한도·약관은 사이트를 열지 않아 **미확인**입니다.
- 기존 피드 경로의 외부 기사 요약이 지금도 Gemini 입력으로 가는 것은 별개의 알려진 상태이며 이 감사의 'Fact 자료'가 아닙니다.

## 부록 — 감사 보고 전문
(아래는 감사 에이전트의 보고서를 그대로 옮긴 것입니다 — 표의 `F`·`R` 번호는 위 본문과 같은 번호입니다.)

## AI 흐름 전수 확인 보고서 (읽기 전용 감사 — 운영자 확인 요청 007 답의 조건 ①)

감사 수행: 읽기 전용 감사 에이전트(2026-11-10 07:1x–08:0x) · 코디네이터가 최종 응답을 파일로 옮김(에이전트는 보고서 파일 쓰기가 거절돼 최종 응답에 전문을 실었다). 재현 스크립트·증거·진행 기록은 같은 폴더의 `scripts/`·`evidence/`·`progress.md`.

### 1. 결론

**지금 길은 0개입니다.** 근거 네 가지입니다.

1. Fact 값이 생길 수 있는 곳은 순수 함수 모듈 8개(`facts·calc·fact_topics·recipes·fact_assembler·adapters` 3개)와 그 시험뿐입니다.
   - 운영 코드가 이 모듈을 가져오거나 부르는 곳이 0입니다(기존 `NoConnectionTest` 와 같은 결과).
   - 실제 제공처 어댑터는 없고 가짜 Provider 하나뿐입니다. 허용 목록 세 곳은 모두 `enabled: false` 입니다.
   - 직렬화 함수(`dumps_bundle`)를 부르는 운영 코드는 0입니다.
   - Fact 로 조립된 글은 어느 트리의 `_posts` 에도 없습니다(조립기의 고정 꼬리글·태그 검색 0건).
2. 임포트 그래프(추이적 폐포, 함수 안 임포트 포함)는 Fact→AI 0, AI→Fact 0, 둘을 모두 가져오는 다리 0입니다.
3. AI 호출 지점은 정해져 있습니다. SDK 가져오기는 운영 코드 2곳(`generator.py:133`, `pipeline/llm.py:446`)이고, 직접 AI 히트 함수는 9개입니다. 데스크톱은 AI SDK 도 AI 호출도 0입니다.
4. 데이터 매개체(`_posts`·`history.json`·초안·PR 본문·아티팩트)에는 Fact 글이 아직 없습니다.

**2단계에서 방어 없이 연결하면 열리는 것**: 파생 6(F1·F2·F3·F4·F6·F7), 간접 1(F8), 직접 2(F5 구조적 불가, F9 설계상 허용·미구현).
핵심 이유는 Fact 글의 제목에 값이 들어 있어서, 기존 코드가 `_posts` 의 제목·태그·분류를 AI 에 보내는 자리가 곧 Fact 값이 새는 자리라는 것입니다. 본문 전체를 AI 에 보내는 `op_llm_patch` 는 대상이 루트 고정 페이지뿐이라 `_posts` 글에는 닿지 못합니다.

### 2. 범위와 방법

| 이름 | 기준 | 머리 | 파이썬(운영/스크립트/도구/시험) | 워크플로 |
|---|---|---|---|---|
| blog_main | origin/main | 1fb895f | 49/9/18/126 | 20 |
| lane_gate | gate-wip(main 보다 10커밋 뒤) | 2aa8486 | 40/9/18/119 | 19 |
| lane_lockfix2 | lockfix2-wip | 1bcbeda | 49/9/18/126 | 20 |
| lane_factfix2 | factfix2-wip | c0706bd | 49/9/18/126 | 20 |
| lane_src | src-wip(main 보다 8커밋 뒤) | 04bddce | 41/9/18/119 | 19 |
| desktop_main | origin/main | 0d2d98a | 169/8/0/182 | 2 |
| desktop_p4e | p4e-wip | 6fce22b | 177/8/0/186 | 2 |

사본은 `git archive` 로 만들었고, 저장소는 읽기 명령만 썼습니다. 방법은 아래 8가지입니다.

1. AST 로 호출 지점 전수(SDK 가져오기·`.generate_content` 호출과 별칭 참조·`llm(...)`·팩토리·키 환경변수·동적 임포트·`exec`·서브프로세스·`getattr`·`globals()[식]`).
2. 이름 기반 호출 그래프와 '읽은 이름' 참조 간선(고정점). 과대 추정입니다.
3. 임포트 그래프 양방향 폐포(`import_graph.py`).
4. 프롬프트 빌더 입력 추적과 사람이 직접 읽은 코드.
5. 워크플로 YAML 전수.
6. 동적 재현(`flow_repro.py`): 진짜 Fact 조립기(가짜 Provider)가 만든 글을 임시 `_posts` 에 두고 블로그 저장소의 실제 함수를 실행해 AI 호출 직전의 프롬프트를 붙잡았습니다. 가짜 키·요청 함수 차단·AI 호출 대역을 썼고, 실제로 아무것도 보내지 않았습니다.
7. 방어선 시제품과 변이 점검(`proto_ai_flow_guard.py`).
8. 레지스트리 JSON 필드와 검증기 함수만 읽기(`provider_checks.py`).

**정의**
- **직접**: 원자료·값 그대로.
- **파생**: 값이 들어간 글자. 제목도 파생입니다(제목에 값이 있으므로).
- **간접**: 제공처 이름·주소·라벨 등 메타만.

### 3. AI 싱크 표

#### 3-1. 블로그 저장소(다섯 트리 동일, 줄은 blog_main 기준)

| ID | 파일:줄 | 보내는 입력(출처) | 도달 |
|---|---|---|---|
| S1 | `generator.py:130–135`, `236–259`(호출 `243–248`), `262–289` | SDK 클라이언트·모델 3개 폴백 | S1a·S1b 를 통해서만 |
| S1a | `2501–2504`(조립 `1686–1768`) | 피드 항목(제목·출처·주소·게시시각·요약≤1,800자·규칙문구) + **`recent_titles = titles[-30:]`**(`2450·2458·1729`, `_posts` 최근 제목) + 분야 문구 + 편집 템플릿 | `chanceblog.yml:77` `python generator.py`(정기 17·47분·수동) → `main 2814` → `2858/2863` |
| S1b | `557–580`(호출 `574`) ← `repair 676` ← `fix_images 712` ← `main 2833` | **글 제목·태그·분류** → 영어 검색어 | `chance-fix-images.yml:66·69`(수동, 연습+`real_ai` 도 호출, 키 식 `:61`) |
| S2 | `pipeline/llm.py:434–482`(클라이언트 `446–447`, 호출 `457`) | 호출 객체 | `run.py:740`, `edits/runner.py:286` |
| S2a | `topics.py:176` | 프로필 지시문 + 자기 블로그 이력 topic 40개(`174·143`) | `run.py:791` ← `blogger.yml:157`, `naver.yml:111`, `tistory.yml:108` |
| S2b | `run.py:815`(조립 `123–135`) | 프롬프트 파일 + 주제 + `feedback`(게이트 사유 — **다른 블로그 이력 제목이 100자까지** 실림, `gates.py:437·440`, `run.py:786`, `state.py:55–66`) | 위와 같음 |
| S2c | `main_image.py:198` | Blogger 글 제목·라벨(AI 가 쓴 글) | `run.py:861 → 535–542 → 396 → 369–376` |
| S2d | `edits/ops.py:251`(조립 `177–208`) | 요청·변경 전·**페이지 원문 전체** | `runner.py:474`(`498`·`507–510`) ← `issue-edit.yml:105`. 대상은 루트 고정 페이지뿐 |
| S2e | `edits/ops.py:309`(호출자 `341`) | 요청 + **글 제목·태그** | 위와 같음. 대상은 `_posts` 한 편 |

- **AI 키를 환경변수로 주는 워크플로 단계 7곳**: `chanceblog.yml:71`, `chance-fix-images.yml:61`, `chance-shadow.yml:76`, `issue-edit.yml:100`, `blogger.yml:149`(`blogger-en.yml:62`·`blogger-ko.yml:64` 가 시크릿을 넘김), `naver.yml:110`, `tistory.yml:107`. 나머지 13개 워크플로는 키가 없습니다.
- 인라인 파이썬 0, curl/wget 0, 제3자 액션 0입니다(공식 액션과 같은 저장소 재사용 워크플로뿐).
- **숨은 싱크**
  - 동적 로드는 운영 코드 1곳뿐입니다(`notify.py:1165–1167`이 상수 경로로 `verify_pages_deploy.py` 를 불러옵니다).
  - `exec`/`eval` 은 0입니다.
  - 서브프로세스는 `git` 과 저장소 점검 명령뿐입니다.
  - 비상수 `getattr` 은 `facts.py`(필드 읽기)와 `llm.py:138` 뿐입니다.
  - AI 제공처 주소 글자는 운영 코드에 0입니다.
  - 인수인계 도구 18개는 AI 히트 0입니다.

#### 3-2. 가지 차이

- **lane_gate**: AI 호출 지점이 하나 더 있습니다. `pipeline/shadow_run.py:398–413`(`_evaluate`)이 `g.build_post_prompt(item, ctx["recent_titles"], …)` 와 `g.call_gemini_with_fallback(prompt)` 를 직접 부릅니다.
  - `g` 는 인자로 받은 생성기 모듈이라 `shadow_run` 은 `generator` 를 import 하지 않습니다.
  - `recent_titles` 는 `492–494`, 후보는 `497`, 키는 `chance-shadow.yml:76` 입니다.
  - `content_source`·`source_policy` 를 모르는 피드 고정 반복문입니다.
  - `quality_gate.py` 는 AI 를 부르지 않습니다(임포트는 표준 라이브러리와 `pipeline.gates` 뿐).
- **lane_lockfix2·factfix2·src**: AI 가능 함수가 main 과 같습니다. src 는 `source_policy.prompt_inputs` 로 `allowlist` 에서 입력을 자체 제목만으로 줄입니다(`legacy` 기본은 그대로).
- 'AI 가능 함수'는 main 34개(gate 37개)이며 과대 추정입니다. 예컨대 `scope_check.expected_after` 는 `llm=None` 이라 실제 호출이 불가능합니다.

#### 3-3. 데스크톱(두 트리)

- AI SDK 가져오기 0, AI 호출 함수 0, 프롬프트 조립 함수 0입니다.
- 네트워크 모듈은 `vendor/scripts/verify_pages_deploy.py` 한 곳뿐입니다(자기 사이트 확인, 키 없음).
- 'AI' 가 나오는 곳은 키 등록부와 설정 카드뿐입니다(`service/connections.py:200–202`, `ui/core/services.py:360–384`, `cli.py:843·1265`). 호출하는 코드는 없습니다.
- **p4e 에 'AI 본문' 선택지는 없습니다**(`draft_text.py:10·91` "AI 없이 초안을 만들어요", 결정 D-289). 서비스 `draft_engine.py` 는 규칙 기반입니다.
- p4e 의 `test_no_ai_client_or_prompt_assembly…` 는 `src/` 의 임포트·함수 이름만 봅니다. 동적 로드(`core.py:61`)는 못 봅니다.
- Fact 경로·허용 목록 사본은 데스크톱에 아직 없습니다. 워크플로 2개는 AI 키가 없습니다.

#### 3-4. AI 처럼 보이지만 아닌 것

- 품질 검사(`gates.py`·`quality_shadow.py`·`quality_gate.py`)는 모두 규칙 기반입니다. LLM 이 글을 읽는 검사 단계는 0입니다.
- 번역 호출은 0입니다. 국문·영문 쌍은 한 번의 호출이 두 언어로 함께 씁니다(`build_post_prompt:1723`).
- 요약·발췌·메타 설명은 규칙입니다(`_description_from_markdown`, PR 본문 발췌).
- 이미지 설명(alt)은 AI 가 만들지 않습니다. AI 가 만드는 것은 영어 이미지 **검색어** 뿐입니다(S1b·S2c·S2e).

### 4. Fact 소스 표

사슬은 다음과 같습니다.

```
허용 목록 → 어댑터 fetch/parse(주입된 opener) → (SourceRecord, [Fact]) → calc f01–f14 → DerivedFact|Skipped
 → fact_topics(허용 낱말) → recipes plan_* → Draft|Insufficient → fact_assembler.assemble → AssembledPost|Insufficient
```

| 모듈 | 값이 만들어지거나 전달되는 곳 | 반환형 | 저장·직렬화 |
|---|---|---|---|
| `facts.py`(main 줄) | `SourceRecord 440`·`Fact 465`·`DerivedFact 513`·`format_with_unit 247`·`render 1025` | 불변 값 객체 | `dumps_bundle 843`·`loads_bundle 862` — **운영 호출자 0** |
| `calc.py` | `f01_change 203` … `f14_median 435` | `DerivedFact`/`Skipped` | 없음 |
| `fact_topics.py` | `fact_problem` | (코드,설명)/None | 없음 |
| `adapters/base.py`·`mock_stats.py` | `fetch`(바이트)·`parse` / 가짜 Provider | 바이트, `(SourceRecord,[Fact])` | 없음(가짜 .invalid 호스트) |
| `recipes.py` | `plan_time_series 306`·`plan_region_compare 518`·`plan_record_position 618`, `RECIPES 720` | `Draft`/`Insufficient` | 없음 |
| `fact_assembler.py` | `assemble 349` | `AssembledPost`/`Insufficient` | 없음 |
| lane_src `source_registry.py`·JSON | `get`·`active_providers`·`is_url_allowed(url,"fact")` | `Provider`(읽기 전용) | JSON(56곳, 전부 `enabled:false`) |

factfix2 가지는 같은 함수의 줄이 더 깁니다(예: `_attribution_line` main `252`, factfix2 `269`).

**`AssembledPost` 칸과 2단계에서 가는 곳**

| 칸 | 값을 담는가 | 가는 곳 | AI 가능 함수가 읽는가 |
|---|---|---|---|
| `title` | **예** | 머리말 `title`, `history.json` `topic`·`kr_title`, PR 제목 | **예**(F1·F2·F4·F3) |
| `description`·`body_markdown` | 예 | 머리말 `description`, 본문 | 아니오 |
| `tags`·`category` | 라벨·지역 이름·분류 | 머리말 | **예**(F2·F4) |
| `evidence_text` | 예 | Gate(규칙) | 아니오 |
| `source_name/url/domain` | 제공처 이름·주소(간접) | 출처 세 줄·`## 출처` 절 | 아니오(후보 `item` 의 같은 이름 칸은 legacy 에서 프롬프트로 — F8) |
| `facts_used`·`derived`·`source_records`·`dedupe_key` 등 | 예 | 저장 계획 없음 | 아니오 |

**허용 목록 세 곳**(레지스트리 JSON, 약관은 읽지 않았습니다)

| 곳 | 저장 tier·상태 | `ai_input` | 접근 경로 | `attribution_template` | `rate_limit` |
|---|---|---|---|---|---|
| statcan | 3·자동화 제외 | ALLOWED/IMPLIED | rss+html+api(`/t1/wds/rest/`) | 빈 글자 | null |
| uk_govuk | 3·자동화 제외 | ALLOWED/IMPLIED | rss+api(**경로 비어 있음**) | 빈 글자 | null |
| noaa_swpc | 3·참고 전용 | ALLOWED/IMPLIED | html+api(`/json/`) | 빈 글자 | null |

**2단계 자리(FACT_PATH §11)와 지금 코드**

| 설계 | 지금 코드 |
|---|---|
| ① `chance.content_source` 스위치 | 없음(시험 `test_the_registry_has_no_switch_for_the_new_path_yet` 이 '없음'을 못박음) |
| ② 생성기에서 `facts` 면 Gemini 대신 `assemble` | 없음 |
| ③ Gate 의 `evidence_text`·`source_ref` 만 Fact 기반 | lane_gate `quality_gate.py:445·467` 에 함수 존재(규칙 기반) |
| ⑧ '그림자 실행은 후보를 일반 실행과 같은 함수로 만든다' | **코드와 다릅니다** — `shadow_run._evaluate` 는 자기 반복문으로 Gemini 를 직접 부름(F6·F14) |
| `provenance` 표식 | 설계에 없음(R4) |

### 5. 도달 가능성

#### 5-1. 임포트 그래프(`evidence/import_reach_*.txt`)

| 트리 | F 모듈 | F→AI | AI→F | 다리 |
|---|---|---|---|---|
| blog_main·lockfix2·factfix2 | 8 | **0** | **0** | 0 |
| lane_gate | 없음 | Gate→AI 0 | — | 0 |
| lane_src | 없음 | 허용목록→AI 0 | — | 0 |
| desktop 둘 | 없음 | — | — | 0 |

최상위 임포트만 센 경우와 함수 안 임포트를 포함한 경우의 결과가 같습니다.
**임포트 그래프의 사각지대**를 둘 확인했습니다.

- `shadow_run` 은 `generator` 를 import 하지 않고 인자 `g` 로 받아 부릅니다.
- `topics.pick_topic`·`main_image.ask_queries` 는 `llm` 모듈 없이 호출 객체를 인자로 받습니다.

그래서 호출 그래프와 참조 간선, 소스 읽기를 함께 썼습니다.
기존 방어선은 `test_fact_structure.py` 입니다. `ImportsTest` 는 Fact 모듈이 표준 라이브러리와 서로만 import 함을, `NoConnectionTest` 는 다른 운영 코드가 Fact 모듈을 부르지 않음을 못박습니다. 2단계가 연결하면 `NoConnectionTest` 를 바꿔야 하고, 그때 역방향과 분기 안쪽을 지킬 장치가 없습니다(R1·R3).

#### 5-2. 데이터 매개체

| 매개체 | Fact 글이 들어오는 때 | 읽는 곳 | AI 입력인가 |
|---|---|---|---|
| `_posts` | 승인 병합 뒤 | `load_posts 613–632`(제목·태그·분류·이미지·원문), 편집 대상 색인, 측정 | **제목·태그·분류만 예**, 본문은 아니오 |
| `history.json` | **초안을 올릴 때 main 에 바로 커밋**(승인 전에도) | `existing_titles`(꼬리 30개 밖 — 지금 `_posts` 제목이 64개), 하루 상한, Blogger·Naver `other_blog_titles` | **조건부 예**(F3) |
| 초안 폴더(`_naver_drafts` 등) | Fact 글은 안 씀 | `watchdog.py:298–314` 의 커밋 시각뿐 | 아니오 |
| 초안 PR 본문 | 제목+첫 문단 260자 | 사람·`ops_inbox`·알림 | 아니오 |
| `posts.json`·`pages.json`·`feed.xml` | 사이트 빌드 | 브라우저·배포 확인·이슈 양식 | 아니오 |
| 아티팩트·캐시 | 그림자 아티팩트(14일), 캐시 단계 0 | 사람 | 아니오 |
| 이슈·텔레그램·확인 필요 모음 | 알림에 제목 | 사람·메신저 | 아니오 |
| `.github/editorial/*.md` | 사람이 쓴 고정 글 | 프롬프트 조립부 | Fact 값 없음(넣지 말 것 — R13) |

#### 5-3. 동적 재현(`evidence/flow_repro.txt`)

조립기가 만든 실제 글은 다음과 같습니다.

- 제목: `가상 지역 가 실업률 3.5%(2026년 3월 기준), 앞 기간보다 0.3%p 높아`
- 분류: `경제·일`
- 태그: `실업률`·`가상 지역 가`·`공개 통계`·`숫자로 읽기`

이 글 두 편을 공용 자체 이미지로 임시 `_posts` 에 두고 실제 함수를 실행했습니다.

| 연결 | 실제 실행한 함수 | 제목 | 값 | 태그 | 분류 | 첫 문단·본문 |
|---|---|---|---|---|---|---|
| a 새 글 | `build_post_prompt(item, existing_titles(...)[-30:])` | **있음** | **있음** | 없음 | 없음 | 없음 |
| a 대조군(`_posts` 에 없음) | 같은 함수 | 없음 | — | — | — | — |
| b 이미지 교체 | `fix_images()` 전체(둘째 글이 `duplicate` 판정 → `make_image_queries`) | **있음** | **있음** | **있음** | **있음** | 없음 |
| c Blogger 재작성 | `gates.check_post` → `build_prompt(feedback)`, `[DUP_OTHER]` 발생(기준 0.6) | **있음** | **있음** | 없음 | 없음 | 없음 |
| d 이슈 수정 | `ops.image_queries` | **있음** | **있음** | **있음** | 없음 | 없음 |
| e 본문 전체 경로 | `pages._candidates` — `_posts` 글이 후보에 든 수 | 0 | — | — | — | — |

- AI 로 가는 것은 제목·태그·분류뿐이고 첫 문단·본문은 가지 않습니다. 제목에 값이 있어 파생입니다.
- 공용 자체 이미지 한 장(FACT_PATH §11 후보 2-(b))을 쓰면 둘째 Fact 글부터 이미지 교체 대상이 되어 AI 검색어 호출로 이어집니다(R7).

#### 5-4. 영어판

- **지금**: 같은 호출 하나가 한·영을 함께 씁니다(`build_post_prompt:1723·1745·1757–1767`). 번역 호출은 없습니다.
- lane_gate 는 `chance.languages: ["ko"]` 일 때 국문 전용으로 만듭니다. 잠금 규칙 L6 은 `["ko"]`·`["ko","en"]` 만 허용합니다.
- FACT_PATH §11-2 는 `languages` 를 `["ko"]` 로만 허용합니다.

| 선택지 | 방식 | AI 로 가는 값 | 위험 | 구현량 | 판단 |
|---|---|---|---|---|---|
| A 국문 단독 | Fact 분기가 `en_*` 를 안 만듦(gate 가지 경로 재사용) | 0 | 영문 노출 없음, 국문 우선 방향과 일치 | 거의 0 | **권고** |
| B 규칙 기반 영어 틀 | 영어 Recipe 틀·`label_en` 표·영어 금지표현·숫자낱말·복수형·관사 새로 구현 | 0 | 어색한 영어, 같은 틀이면 Gate ③ '한·영 단순 번역 구조 금지'·'번역 복제 0' 에 걸릴 수 있음 | 큼(별도 단계·승인) | 범위 밖 |
| C AI 번역 | Fact 글을 Gemini 로 번역 | **값 전부** | 조건 ① 위반 | 작음 | **금지** |
| D 사람이 직접 | 승인 PR 에서 운영자가 영문 작성 | 0 | 운영자 부담 | 0 | 자동화 밖에서 선택 가능 |

### 6. 발견 목록

심각도 기준은 아래와 같습니다.
- **높음**: 자동 실행에서 값이 조건 없이 가거나 설계가 허용합니다.
- **보통**: 수동 실행이거나 조건부입니다.
- **낮음**: 확률이 낮거나 간접입니다.

| 번호 | 분류 | 지금 | 2단계 후(방어 없이) | 심각도 | 위치 | 권고 |
|---|---|---|---|---|---|---|
| F1 | 파생(제목에 값) | 아니오 | 조건부 예: Fact 글이 최근 30편 안 + 피드 글쓰기·그림자 실행이 같은 저장소에서 돎 | 높음 | `generator.py:2450·2458·1729`; gate `shadow_run.py:492–494·411` | R1·R4·R5·R6·R18 |
| F2 | 파생(제목·태그·분류) | 아니오 | 조건부 예: `chance-fix-images` 수동(연습+`real_ai`)에서 `duplicate`·깨짐·없음 판정 | 보통 | `generator.py:557–580·662–678·689–729`; `chance-fix-images.yml:61` | R5·R6·R7 |
| F3 | 파생(이력 제목 100자까지) | 아니오 | 조건부 예: Blogger·Naver 글이 Chance 제목과 유사도 0.6 이상 | 낮음 | `state.py:55–66`; `run.py:786·815`; `gates.py:437·440` | R5·R8 |
| F4 | 파생(제목·태그) | 아니오 | 조건부 예: 소유자·멤버·협업자의 '이미지 변경' 이슈 | 낮음 | `edits/ops.py:294–313·331–353`; `issue-edit.yml:35–37` | R5·R7 |
| F5 | 직접(본문 전체) | 아니오(구조적 불가) | 아니오 — 대상이 루트 고정 페이지뿐(규칙이 바뀌면 열림) | 낮음 | `ops.py:239–260`; `pages.py:28–52`; `edit-spec.yml` | R5(시험으로 고정) |
| F6 | 파생(두 번째 호출 지점) | 아니오(gate 병합 전) | **예**: 그림자 실행이 최근 제목을 AI 에 보내고 Fact 후보는 이 반복문에 없음 | 보통 | gate `shadow_run.py:398–413·492–497` | R1·R5·R9 |
| F7 | 파생(설계 불일치) | 아니오 | **예(SRC 계약대로면)**: `allowlist` 에서도 자체 제목이 프롬프트로 | 높음 | src `source_policy.py`(`prompt_inputs`·`own_title_batches`), `SOURCE_POLICY §9` 항 2·3·7 ↔ `FACT_PATH §11-2` | R1·R9 |
| F8 | 간접(제공처 이름·주소) | 아니오 | 조건부: `source_policy` 기본 legacy 에서 후보 `source`·`link` 가 프롬프트로 | 낮음 | `generator.py:1694–1704` | R9 |
| F9 | 직접(설계 허용·미구현) | 아니오(코드 0) | 만들면 열림: 완성형 'AI 서술(선택)' | 높음 | `FACT_PATH §13`; R-218 3-5; `ai_processor_policy.json` `input_scope` | R10·R11 |
| F10 | — | 없음 | 없음(데스크톱) | — | 3-3 | R16 |
| F11 | — | 없음 확인(검사·번역·요약·alt) | 없음 | — | 3-4 | — |
| F12 | 스키마 | — | — | **높음**(켜기를 막음) | `source_registry.py:253–266·407–456` | R10 |
| F13 | 코드 자리 부재 | — | — | 보통 | `fact_assembler.py:252–259·423–425`(factfix2 `269–276·441–443`); `rate_limit` 통과 필드뿐; `egress.py` | R14·R15 |
| F14 | 문서·코드 불일치 | — | — | 보통 | `FACT_PATH §11-8` ↔ `shadow_run.py:398–413`; `SOURCE_POLICY §12-③` | R17 |

- **F5 를 낮게 둔 이유**: 후보 해석이 루트 파일(`include` 목록과 `editable: true`)에서만 만들어지고, 재현 e 가 `_posts` 후보 0을 확인했습니다.
- **F12 상세**
  - `ai_input` 이 `DENIED` 면 Tier 4(완전 제외)입니다.
  - 세 곳은 `ai_input` 이 `IMPLIED` 라 A2 가 막습니다.
  - 경로 종류가 섞여 A6 이 막습니다. `uk_govuk` api 는 `paths` 가 비어 A10 이 막습니다.
  - `attribution_template` 이 모두 비어 A5 가 막습니다.

### 7. 2단계 요구사항

| 번호 | 요구 | 막는 연결 | 구현 위치 | 시험 |
|---|---|---|---|---|
| **R1** | 후보 공급을 **한 함수**로 한다(생성기·그림자·앞으로의 진입점). Fact 분기 함수는 호출·참조로 닿는 곳에 AI 가능 함수가 없다 | F6·F7·F1 | `generator.py`, `shadow_run.py` | AF4·AF5, 변이 M5·M6·M7·M11 |
| **R2** | `facts` 실행에는 **AI 키를 주지 않고** SDK 를 가져오지 않는다(워크플로 키 식, `main()` 의 키 검사 건너뜀, `get_client` 는 예외). 키 없는 실행에서 `stub_post_data` 가짜 글이 나오지 않게 한다 | 구조 방벽 | `chanceblog.yml:71`, `chance-shadow.yml:76`, 새 `content_source` 읽기 단계, `generator.py:2826–2829`, `registry.py` | AF7 + 단위(키 없이 `facts` 성공, `google.genai` 미적재), M9 |
| **R3** | 임포트 단방향 격리를 새 연결 모듈까지 넓힘. 다리는 `generator` 한 곳이고 다리 안쪽은 따라가지 않음 | F→S·S→F·다리 | `test_fact_structure.py` 개정, `tests/ai_flow_scan.py` | AF1, M1·M2·M13 |
| **R4** | **`provenance: facts` 표식**(머리말·`history.json`). 생성기만 쓰고 `front_matter_problems` 가 검증하며 모델 출력의 표식은 지운다 | F1–F4·F6 의 신호 | `generator.py`(`_fresh_front_matter`·`front_matter_problems`), `test_posts_front_matter.py` | 골든 글에 표식, 모델이 쓴 표식은 삭제 |
| **R5** | **표식 소비자**: AI 입력을 만드는 읽기에서 표식 글을 뺀다(`load_posts(for_ai=True)` 기본·`existing_titles`·`fix_images`/`repair`·`op_image`/`image_queries`·`shadow_run`·`other_blog_titles`). 고정 페이지 후보 규칙(`_posts` 제외)을 시험으로 고정 | F1·F2·F3·F4·F6, F5 고정 | `generator.py:613·754`, `edits/ops.py`, `pages.py`, `state.py:55`, `shadow_run.py` | AF6 + 단위, M8 |
| **R6** | **런타임 방벽** `ai_guard.assert_clean(prompt)`: 두 입구(`call_gemini_with_fallback`, `llm.call`)가 정규화한 프롬프트에 표식 글의 제목 전체·앞 24자·설명 앞 40자가 있으면 `AiInputForbidden`(재시도·폴백 없이 즉시, 문구에 내용 없음) | 정적 규칙이 못 보는 길의 마지막 방벽 | 새 `pipeline/ai_guard.py` | 프롬프트 4개 차단 + 대조군 통과 + 못 막는 5개를 한계로 단언 |
| **R7** | 이미지: Fact 자체 이미지가 `diagnose` 의 `duplicate`·`broken`·`missing` 으로 교체 대상이 되지 않게(글마다 다른 자체 이미지 또는 예외). `image_change` 는 표식 글에서 AI 검색어 없이 요청 문구만 쓰거나 거부 | F2·F4 | `generator.py:662–672`, `ops.py:294–353` | 공용 이미지 두 글의 `fix_images` 대상 0 |
| **R8** | Blogger·Naver 재작성 사유에 다른 블로그 제목을 싣지 않음(고정 문장) 또는 표식 항목 건너뜀 | F3 | `gates.py:437–440`, `state.py:55` | `[DUP_OTHER]` 문자열에 제목 없음 |
| **R9** | SRC 계약 개정: `prompt_inputs`·`own_title_batches` 는 Fact 후보에 쓰지 않음. `SOURCE_POLICY §9` 항 2·3·7 과 `FACT_PATH §11-2·§11-8` 을 한 가지 말로 고침 | F6·F7·F8·F14 | 문서 2개 | 표·상수 일치 시험(R17) |
| **R10** | **레지스트리 스키마**: '이 제공처 자료를 AI 에 쓰지 않는다'를 적는 값(예: `ai_input` 에 `NOT_USED`/`OWN_POLICY` + `Provider.ai_blocked`)을 신설하고 `computed_strict_tier`·A2·A3 이 알려진 칸으로 읽게 함. 실행 시 `ai_blocked` Fact 를 AI 단계에 넘기는 코드를 거부. `input_scope` 가 `ai_blocked` 에는 적용되지 않음을 명시 | F12·F9 | src `source_registry.py:253–266·407–456`, `ai_processor_policy.json` | 새 규칙 경계 시험 + 세 제공처 항목 시험 |
| **R11** | 이 세 곳 자료에는 AI 서술·번역·요약·다듬기·이미지 설명 단계를 **만들지 않음**(문서 명시 + AF4 의 AI 이름 참조 금지) | F9 | `FACT_PATH §13`, R-218 개정 | AF4·AF8 |
| **R12** | 영문: Fact 분기는 `languages: ["ko"]`, `en_*` 없음, AI 번역 0 | 영문 C 차단 | `generator.py` + gate `chance_settings` | `en_*` 없음 + AF4 |
| **R13** | 저장·읽기 경로: Fact 묶음을 저장한다면 `_posts`·`history.json`·`pages.json`·프롬프트 파일 밖 별도 폴더에 두고 `_config.yml` `exclude` 에 올림. AI 가능 함수의 읽기 경로를 허용 목록으로 고정. 프롬프트 파일에 Fact 금지 | 매개체로 새는 길 | `_config.yml`, `test_site_cleanup.py` | AF6 읽기 경로 |
| **R14** | **출처 표시 문구 자동 첨부**: 조립기가 레지스트리 `attribution_template` 로 `## 출처` 끝에 한 줄을 붙이고, 출처 표시가 `CONDITIONAL` 인데 템플릿이 비면 글을 내지 않음(지금은 비어도 글이 나감). 문구는 AI 를 거치지 않음 | F13, 조건 ② | `fact_assembler.py`(`_attribution_line`·`_assemble`), `provider_active_problem` | 템플릿 없는 Provider 로 `Insufficient`, 골든 글에 정확히 한 줄 |
| **R15** | **호출 한도**: 레지스트리 `rate_limit` 값 + ACTIVE `api` 경로 필수 규칙 + `build_checked_opener`/어댑터 래퍼가 일 호출 수·실패 3회 건너뜀·성공 재사용을 지킴(정기 실행 매시 17·47분, 후보 없을 때 슬롯 창에서 반복 → 하루 30번 안팎, `ARCHITECTURE §4-8`) | F13, 조건 ② | `source_registry.py`, `egress.py` | 상한 초과 시 호출 0 |
| **R16** | 연결 코드 사전 확인(`Registry.is_active`·`snapshot.expires_at`·`is_url_allowed(url,"fact")`·검사된 opener 만 어댑터에 주입). 데스크톱에 AI 연결 묶음이 생기면 같은 규칙을 걸고 기존 `test_no_ai_client…` 는 지우지 않고 허용 목록으로 바꿈 | 켜기 전 순서·F10 | 연결 글루, 데스크톱 후속 | 단위 + AF3 |
| **R17** | 시험·문서 보호: `NoConnectionTest` 를 '허용 연결 한 군데' 시험으로 개정. 등록 상수와 새 `docs/AI_FLOW.md` 표의 일치 시험(선례 `test_fact_docs`·`test_source_policy_docs`). 시험 약화는 T3(CODEOWNERS 는 분기 보호가 켜져야 효력) | F14 | `tests/test_ai_flow_docs.py` | 표·상수 일치 |
| **R18** | **제목 정책(결정 항목)**: Fact 제목에 값을 넣지 않음(라벨·지역·기준일만) → F1–F4·F6 이 파생에서 간접으로 내려감. 값 있는 제목은 R1–R6 이 모두 선 뒤에만 | F1–F4·F6 | `recipes.py:393–402·567–568·663–670`, 골든 글 | 골든 제목에 숫자 없음 |

### 8. 방어선

#### 8-1. 정적 규칙(`tests/egress_scan.py` 와 같은 형태)

`egress_scan.py` 는 `Site` 목록과 `EGRESS_EXCEPTIONS` 등록, 합성 변이로 구성됩니다. 같은 형태로 AI 흐름용 규칙을 제안합니다(`tests/ai_flow_scan.py`·`tests/test_ai_flow.py`).

| 규칙 | 이름 | 검사 대상 | 실패 메시지 | 막는 연결 |
|---|---|---|---|---|
| AF1 | F-IMPORTS | 운영 코드 전체(`generator.py`·`pipeline/**`·`scripts/**`·`인수인계/도구/**`) 임포트 폐포, 다리는 안쪽을 안 따라감 | `Fact 모듈이 AI 쪽 모듈 X 를 가져온다(경로 …)` / `새 다리다` | F→S·S→F·다리 |
| AF2 | AI-PRIMITIVES | SDK 가져오기·클라이언트·`.generate_content`(호출·별칭 참조) | `AI SDK 사용이 등록되지 않은 함수 F 에 있다 — AI_PRIMITIVES 에 이유와 함께 올리거나 지운다` | 새 AI 호출 |
| AF3 | LLM-CONSUMERS | `llm(...)` 호출 함수·`make_gemini_llm`/`build_llm` 호출 함수 | `호출 객체를 부르는 곳이 등록되지 않았다(F)` | 새 소비자 |
| AF4 | FACT-NO-AI | Fact 분기 진입 함수에서 호출·참조로 닿는 전부 | `Fact 분기에서 닿는 함수 F 가 AI 호출로 이어진다 — 사슬 A <- B <- 진입점` | F1·F6·F7·F9, 별칭·콜백 |
| AF5 | AI-CALL-SITES | `call_gemini_with_fallback`·`build_post_prompt`·`make_image_queries` 호출처 | `X( 를 부르는 새 지점 F — AI_CALL_SITES 에 올리거나 지운다` | 새 호출 지점(그림자) |
| AF6 | POSTS-FOR-AI | AI 가능 함수·Fact 분기의 '표식 안 거르는 글 읽기'와 읽기 경로 | `AI 가능 함수 F 가 provenance 를 거르지 않는 읽기 X 를 부른다` | F1·F2·F4 |
| AF7 | WORKFLOW-KEY | `chanceblog.yml`·`chance-shadow.yml` 의 키 식 | `AI 키 식에 content_source != 'facts' 조건이 없다` | 키 전달 |
| AF8 | NO-DYNAMIC | Fact 모듈과 Fact 분기에서 닿는 함수의 `importlib`·`exec`/`eval`·서브프로세스·비상수 `getattr`·`globals()[식]` | `Fact 분기에서 닿는 F 에 동적 실행·이름 조립이 있다` | 이름 조립 |

등록 목록은 지금 코드의 호출 지점 전부로 시작합니다. 시제품을 진짜 5개 트리에 돌리면 위반 0건입니다(gate 의 `shadow_run._evaluate` 가 `AI_CALL_SITES` 에 등록돼 있어야 0입니다).

#### 8-2. 변이 점검(`evidence/proto_guard_mutants.txt`)

방법은 이렇습니다. `blog_main` 복사본에 가짜 2단계 뼈대(Fact 분기 함수·표식 안 거르는 읽기·키 조건 워크플로)를 덧붙인 **기준선이 0건**인지 보고, 일부러 어긴 코드를 한 개씩 넣어 의도한 규칙이 빨개지는지 확인합니다.

- 기준선은 **0건**입니다. 첫 시도는 6건이었습니다. 속성 이름까지 참조 간선으로 따라가 과대 간선이 생겼고, 다리를 가져오는 모듈을 다리로 센 것이 원인이어서 규칙을 고쳤습니다.
- **13/14개가 잡혔습니다.**

| 변이 | 내용 | 기대 | 결과 |
|---|---|---|---|
| M1 | `fact_assembler` 가 `generator` 를 가져옴 | AF1 | 잡힘 |
| M2 | `calc` 가 `pipeline.llm`(마스킹 도우미)을 가져옴 | AF1 | 잡힘 |
| M3 | 새 모듈이 genai 를 가져와 `generate_content` 호출 | AF2 | 잡힘 |
| M4 | 새 모듈이 `llm(...)` 호출 | AF3 | 잡힘 |
| M5 | Fact 분기가 `call_gemini_with_fallback` 직접 호출 | AF4 | 잡힘 |
| M6 | Fact 분기가 도우미 → `make_image_queries`(추이적) | AF4 | 잡힘 |
| M7 | 등록 밖 새 지점이 `call_gemini_with_fallback` 호출 | AF5 | 잡힘 |
| M8 | AI 가능 함수 `repair` 가 표식 안 거르는 읽기 호출 | AF6 | 잡힘 |
| M9 | 워크플로가 키를 조건 없이 줌 | AF7 | 잡힘 |
| M10 | `globals()['call_gemini'+'_with_fallback']` | AF8 | 잡힘(처음엔 못 잡아 `globals()[식]` 감지를 더함) |
| M11 | AI 함수를 변수에 담아 호출 | AF4 | 잡힘 |
| M12 | Fact 모듈이 서브프로세스 실행 | AF8 | 잡힘 |
| M13 | 새 모듈이 Fact+AI 모듈을 함께 가져옴 | AF1 | 잡힘 |
| M14 | `operator.attrgetter('…')` 로 AI 함수 이름 꺼냄 | (사각지대) | **못 잡음**. 런타임 방벽과 키 미전달이 맡음 |

2단계 시험은 스캐너를 소스 글자를 받는 순수 함수로 짜서, 시험 안에 위반 소스 문자열을 심어 '빨개짐'을 증명하는 방식을 권합니다(선례 `test_egress.py:311` 의 `planted`). 작업 보고에는 FACT 1단계처럼 '원복 뒤 sha256 확인' 표를 남기고, 도구는 저장소에 넣지 않습니다.

#### 8-3. 실행 방어가 필요한가 — 필요하지만 마지막 방벽입니다(R6)

정적 규칙은 데이터를 거치는 길과 앞으로 생길 코드를 증명하지 못합니다. 시제품 결과는 아래와 같습니다.

| 프롬프트 | 판정 |
|---|---|
| a 새 글·b 이미지 교체·c Blogger 재작성·d 이슈 수정 | 모두 **차단** |
| a 대조군(Fact 글 없음) | 통과(오탐 없음) |
| 제목의 공백·대소문자만 바꿈 | 차단 |
| 제목 뒤쪽 30자만 | **못 막음** |
| 값만(`3.5%`) | **못 막음**(조각으로 쓰기엔 너무 일반적) |
| 의역·영어 번역 | **못 막음** |

그래서 1차는 구조 방벽(R1 단일 분기·R2 키 미전달·R5 표식 제외)이고, 런타임 방벽은 '값이 든 제목이 그대로 프롬프트에 들어간 사고'를 잡는 2차입니다. 못 막는 예를 시험이 '못 막는다'고 단언해 두면 방벽을 믿고 구조 방벽을 줄이는 일을 막을 수 있습니다.

`chance-fix-images.yml`·`issue-edit.yml` 은 기존 모든 글을 다루므로 키를 뺄 수 없어 R5·R6·R7 이 맡습니다. `chanceblog.yml`·`chance-shadow.yml` 은 `facts` 실행에서 키를 비울 수 있습니다.

### 9. 제공처별 추가 점검(조건 ② 입력 — 사이트를 열지 않았고 JSON 필드와 검증기 출력만 읽었습니다)

**공통**
1. **7칸 재확인**
   - `ai_input` 은 세 곳 모두 `IMPLIED` 입니다. 결정 2 를 코드로 표현하려면 R10 이 먼저입니다.
   - `automated_access` 는 `CONDITIONAL` 인데 조건의 내용(속도·식별·robots)을 적는 칸이 없고 근거 문서 이름만 있습니다.
   - `derivative_use`·`attribution`·`license` 의 `CONDITIONAL` 조건 문구는 `attribution_template` 로 옮깁니다.
   - `exceptions`(로고·명칭·제3자 자료)는 어댑터 낱말 표에서 뺍니다.
2. **robots**: `robots_checked_at` 은 감사가 읽은 날짜를 옮긴 값입니다. 코드는 robots 를 읽지 않습니다. `uk_govuk` api 호스트는 점검일이 비어 있습니다.
3. **호출 한도 확인 위치**
   - 레지스트리 `access[].rate_limit` 은 **세 곳 모두 null** 입니다. 값을 요구하는 검증 규칙도 강제 코드도 없습니다(`source_registry.py:121·368·518`).
   - 강제 자리는 `egress.build_checked_opener` 또는 어댑터 호출 래퍼입니다. `FACT_PATH §7` 3항이 '관문이 지킨다'고 정했지만 구현이 없습니다.
   - 제공처가 공개한 한도 값은 확인하지 못했습니다.
4. **출처 표시 문구 자동 첨부 자리**
   - 레지스트리 `attribution_template`(세 곳 모두 빈 글자 → A5)에서 `fact_assembler._attribution_line`(main `252–259`, factfix2 `269–276`)이 `{title}`·`{date}`·`{url}` 만 치환해 `## 출처` 절에 한 줄을 붙입니다.
   - 조립 마지막의 규칙 코드이고 AI 단계가 없습니다.
   - 조립기는 템플릿이 비어도 글을 내므로 `CONDITIONAL` 이면 중단하게 해야 합니다(R14).
   - 기존 피드 경로의 인용 문구는 `generator.py:991`(통계청)과 `1032`(영국 정부)에 있습니다. 틀의 후보지만 Fact 글에 맞는지는 약관 원문 확인이 필요합니다. NOAA 는 기존 문구가 없습니다.
5. **어댑터 체크리스트**(`FACT_PATH §7` 10항): 낱말 표·주제 허용 목록 등재·가짜 응답 시험·`UNIT_TABLE` 이 세 곳 모두 아직 없습니다.

**켜려고 할 때 검증기가 막는 규칙**(가정 입력: `enabled`·상태·tier 를 켠 것처럼 적었을 때)

| 곳 | 막는 규칙 | 칸·출처 문구를 고쳐도 남는 것 |
|---|---|---|
| statcan | S7, A1, A2, A5, A6(rss·html) | S7·A6 — Provider 를 접근 경로별로 **쪼개야** 함 |
| uk_govuk | S7, A1, A2, A5, A6(rss), **A10(api `paths` 비어 있음)** | S7·A6·A10 |
| noaa_swpc | S7, A1, A2, A5, A6(html) | S7·A6. 지역 없는 계열이라 R01·R03 틀이 `NO_REGION_SERIES` 로 글을 못 만듦(지역 없는 틀이 2단계 첫 일) |

**제공처별 메모**
- **statcan**: WDS 경로(`/t1/wds/rest/`)가 rss 와 같은 호스트라 허용이 경로 접두어로 갈립니다. 쪼개기 전에는 켜지 못해 안전합니다. 계열 코드를 우리 낱말 표로 옮겨야 합니다. 통계청 명칭·로고는 `exceptions` 의 제한 대상입니다.
- **uk_govuk**: api 항목이 호스트 전체를 엽니다(A10). 응답은 문서 단위 JSON 이라 본문 필드를 읽지 않는 필드 화이트리스트가 어댑터에 필요합니다. 실제 응답 모양과 숫자 Fact 양은 확인하지 못했습니다. 가장 마지막 순서가 맞습니다.
- **noaa_swpc**: 가장 단순한 구조화 JSON 입니다. `paths: ["/json/"]` 는 제품 전체를 여는 넓은 접두어라 실제로 쓸 제품 경로로 좁혀야 합니다. 첫 번째 후보로 맞습니다.

### 10. 한계

1. **합쳐진 트리를 읽지 못했습니다.** 병합 순서(GATE → LOCK → SHADOW → R2 → SRC → FACT)에 따라 gate·lock·src·fact 가지가 `generator.py`·`registry.py` 를 서로 다르게 고칩니다. 가지별로만 읽었고 합쳐진 상태의 AI 흐름은 **미확인**입니다. 병합 뒤 8절 규칙을 다시 돌려야 합니다.
2. 이름 기반 호출 그래프는 별칭·콜백·이름 조립·`operator.attrgetter`·`functools.partial(getattr…)`·pickle/yaml 을 놓칠 수 있습니다(M14 로 확인). 'AI 가능 함수' 수는 과대 추정입니다.
3. 의존성 주입(`llm`, 인자로 받은 모듈 `g`)은 임포트 그래프가 못 봅니다. 참조 간선과 소스 읽기로 보완했지만 새 주입 모양은 놓칠 수 있습니다.
4. 워크플로는 구조와 글자만 읽었습니다. `${{ }}` 식의 실제 평가와 셸 변수로 조립한 명령은 못 봅니다. 지금은 인라인 파이썬·curl 이 0이라 해당 없습니다.
5. 러너에 설치되는 패키지와 SDK 자체의 통신은 코드 밖이고, 의존성 버전별 동작은 확인하지 않았습니다.
6. 저장소 시험 전체는 돌리지 않았습니다. 정적 분석과 가벼운 재현 두 개만 돌렸고, 시제품은 `trees/` 사본에서만 돌았습니다. 저장소 시험이 초록이라는 주장은 하지 않습니다.
7. **공개 이후는 코드 경로가 아닙니다.** Fact 글이 Pages 와 공개 저장소에 올라가면 외부 AI·크롤러가 읽을 수 있습니다(`robots.txt` 는 모두 허용). 운영자의 코딩 AI 세션이 저장소·로그·알림을 읽는 것도 이 감사 밖입니다. GitHub 자체의 AI 기능 설정은 **미확인**입니다.
8. 레거시 피드 경로의 외부 기사 요약이 지금도 Gemini 입력으로 가는 것(`SOURCE_POLICY §10`)은 별개의 알려진 상태이며 이 감사의 'Fact 자료'가 아닙니다.
9. 키 등급(무료/유료)과 제공처의 실제 호출 한도는 **미확인**입니다.
10. 데스크톱: vendor 동기화 목록(`VENDOR.json` 5개)이 고정이라 `llm.py` 가 들어올 수 없음을 보증하는 시험은 읽지 않았습니다(현재 목록에는 없음). p4e 의 AI 금지 시험은 `src/` 의 이름·임포트만 봅니다.
11. Fact 값이 다른 형태로 바뀐 글자(단위 변환·반올림·의역)는 런타임 방벽이 못 잡습니다.
12. 'Fact 글은 `_posts` 에서 본문 전체 AI 경로에 닿을 수 없다'는 현재 대상 해석 규칙이 그대로일 때만 참입니다.

### 11. 부록

재실행 명령입니다(작업 폴더에서, `py312` = 파이썬 3.12 의 `python.exe`, 항상 `-I -X utf8`).

```
py312 -I -X utf8 scripts/run_all.py            # 아래를 하나씩 차례로(2분 반)
scripts/ai_sinks.py · import_graph.py · external_imports.py · prompt_inputs.py · workflows_scan.py [트리…]
scripts/flow_repro.py · proto_ai_flow_guard.py selftest|real · provider_checks.py
```

머리 해시는 2절 표와 같습니다. 증거 파일 70개는 `C:/work/ai/audit6/aiflow/evidence/` 에 있습니다.
