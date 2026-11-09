---
id: R-218
kind: info
title: [R-218] 진행 현황 P017 — 외부 출처 공통 상위 아키텍처 초안 v0.2(제한 재개용 최소 / 완성형, 구현 없음)
summary: 허용 목록(Source Registry)·AI Processor 정책·문 5개(정책·출처 기록·원본성·안전·발행)·Desktop 로컬 Draft/발행 서비스 분리를 담은 상위 아키텍처 초안입니다. 제한 재개용 최소(16항목)와 완성형을 나눴고 공공누리 AI유형 탐색 결과를 보강했습니다. 운영자 확인은 AI 입력 칸 해석 1건(기본값 strict 유지). 공개 글·설정 변경 없음. 다음 알림은 4시간 뒤.
urgency: 보통
created: 2026-11-09
no: P017
work: R-218
at: 2026-11-09 11:53
now: M023 병합 대기, 독립 검증 중(그림자 도구·R2·Gate·잠금), S06 최종 손질, S18·관광 정정안 작성, P4d 병합 트리 작업
changed: 상위 아키텍처 초안 v0.2 작성(R-216 분석 반영), 공공누리 AI유형 탐색(strict 통과 0), W0 정정 2차 검증 통과·M023 병합 부탁 R-217
next: M023 병합 확인 → 다음 병합 부탁(한 번에 하나) · Lane B 독립 검증 결과 · S18·관광 정정안 검증
eta: 다음 병합 부탁 약 13:00(추정, M023 병합 뒤)
waiting: M023 병합 대기(R-217) · 운영자 해석 1건 기본값 strict 유지(본문 8절)
check: 주의 외부 Provider 0곳
---

# 외부 출처 공통 상위 아키텍처 초안 v0.2 (본문 — 폰에는 싣지 않고 요청 열기로 읽습니다)

R-216 분석의 설계 쪽 결과입니다. **구현은 없고 공개 글·Blogger 글·고정 페이지·광고·ads.txt·발행 설정·정지 변수는 바뀌지 않았습니다.** 운영자 결정(2026-11-09 세 건)을 규칙으로 옮겼고, 제한 재개용 *최소*(11-16–19)와 *완성형*(11-23–30)을 나눴습니다.

## 한눈에

1. **새 방침의 핵심은 '들어오는 문'을 바꾸는 것**입니다. 외부 자료는 허용 목록(Registry)에 등록되고 이용 조건 7칸이 모두 확인된(UNKNOWN 0) 구조화 데이터(API·데이터셋)만 통과합니다. 외부 RSS 요약·기사·해설문은 발행자가 정부여도 **유형만으로 Tier 3(자동화 제외)** 입니다.
2. **통과한 것은 문장이 아니라 Fact** 입니다(숫자·날짜·지역·관측값·공식 상태·분류코드…). 모든 Fact 는 Provider·Source Record ID·기준일시·단위·지역·License Snapshot·Retrieved At 를 달고 다니며, 출처 없는 사실은 초안에 들어갈 수 없습니다.
3. **글은 'Fact → 자체 계산 → 자체 비교·분석 → 자체 문장'** 입니다. AI 는 선택 기능이고, AI 에게는 Signal·검증된 최소 Fact 만 줍니다. AI 가 없어도 규칙 기반으로 후보와 초안이 나옵니다.
4. **다섯 개의 문**(정책 → 출처 기록 → 원본성 → 안전 → 발행)을 모두 통과해야 초안 또는 PR 이 만들어집니다. 사람 승인 없는 공개 경로는 0 입니다.
5. **불확실하면 질문하지 않고 꺼 둡니다**(정책 불명 → Provider OFF, 라이선스 변경 → 격리, 근거 부족 → 보류). 운영자에게는 일·주 요약만 갑니다.
6. **Gemini 같은 AI 는 데이터 출처가 아니라 처리기**라서 Source Tier 표 밖의 `AI_PROCESSOR_POLICY` 로 따로 관리합니다.
7. **Desktop 의 로컬 작성(Local Draft Service)은 `PIPELINE_PAUSE` 와 무관하게 항상 동작**하고, 외부 공개(External Publication Service)만 정지·발행 정책·사람 승인을 받습니다. Desktop 은 `PIPELINE_PAUSE` 변수를 만지지 않습니다.
8. **일정은 둘로 나눕니다.** 제한 재개(11-16–19, PR 승인형)에는 16항목의 *최소* 범위만 필요하고, 정식 Registry·Policy Snapshot·자동 격리·주간 요약 같은 *완성형*은 재개 뒤 병렬(목표 11-23–30)입니다.
9. **지금 가장 큰 일정 위험은 'strict 로 통과하는 구조화 Provider 가 아직 0곳'** 이라는 점입니다(8절·R-216 4절). 그 경우 제한 재개용 최소 Allowlist 는 Tier 0(자체 데이터)뿐이고, 이를 풀 길은 TD 조사가 찾는 Dataset 단위 후보와 '규칙 기반(AI 미사용) 경로의 AI 입력 칸' 해석 하나입니다(운영자 확인 1건, 기본값 strict 유지).

## 1. 운영자 결정 → 설계 규칙

| ID | 규칙 | 지키는 방법 |
|---|---|---|
| R1 | 허용 목록이 정본 | `Registry` 에만 출처가 있고 코드의 출처 목록(NEWS_SOURCES·TRUSTED·BLOCKED)은 여기서 만들어 낸다 |
| R2 | 모든 외부 호출은 한 관문(egress) | 호스트가 Registry 의 ACTIVE 에 없으면 예외. 직접 네트워크 호출을 시험이 막는다 |
| R3 | 7칸 모두 알려져야 ACTIVE | UNKNOWN·미확인이 있으면 저장 단계에서 거부. **실행은 `strict_tier` 만** |
| R4 | 사람 판단은 '구성 변경 PR' 하나뿐 | 약관을 읽고 증거와 함께 올리는 PR. 허가 문의는 기본 운영에서 뺌 |
| R5 | 외부 본문·해설문·RSS 요약·스니펫·외부 사진은 자동화 입력이 아님 | 어댑터는 API·CSV·JSON 같은 구조화 응답만 읽는다 |
| R6 | Fact 레코드 | 수치·날짜·시각·지역·관측값·상태·코드 + 단위·기준일시·지역 |
| R7 | 자체 계산·비교·분석 | 결정적 함수가 계산, 원자료 대비 추가 분석 ≥2, 표·계산·비교 ≥1 |
| R8 | 출처 기록(Provenance) | Provider·Source Record ID·기준일시·단위·지역·License Snapshot·Retrieved At |
| R9 | 약관 변경·기한 만료 시 해당 Provider 만 격리 | 상태 파일에 QUARANTINED, 나머지는 계속 |
| R10 | 예외는 질문이 아니라 보류·제외·대체 | 7절 표로 고정, 운영자에게는 일·주 요약만 |
| R11 | 편집·수익화·공개 3계층 분리 | 광고·협찬은 편집 계층에서 읽을 수 없음 |
| R12 | 사람 승인 없는 공개 경로 0 | Chance 는 `publish_flow: pr` 만 |
| R13 | AI 는 선택 + 별도 정책 | `AI_PROCESSOR_POLICY`, 입력은 Signal·최소 Fact 만, 출력 검증 위반은 자동 보류 |
| R14 | 로컬 Draft Service 는 PAUSE 와 독립 | 외부 공개 경로만 PAUSE 적용, Desktop 은 변수를 등록·수정·삭제하지 않음 |

## 2. 전체 그림

```
 [허용 목록 Registry]   ← 사람이 증거와 함께 PR 로만 바꿈 (Tier·7칸·Snapshot·기한)
        │ 읽기 전용                                 [AI_PROCESSOR_POLICY] ← 별도 정책(Gemini 등)
        ▼                                                      │ 입력 범위 규칙
 [egress 관문] ── ACTIVE 가 아닌 호스트·기한 지난 Provider 는 호출 거부
        │
        ▼
 [Provider 어댑터] ─▶ [수집 기록 + Fact 저장소] ◀── [Tier 0: 시드·프로필·발행 이력·사용자 입력]
                              │
 ┌────────────────────────────┴──────────────────────────────────────────┐
 │  Local Draft Service (Desktop·로컬 — PIPELINE_PAUSE 와 독립, 항상 동작) │
 │  주제 조합 엔진 → 초안 조립기(규칙 기반 + 선택적 AI 서술) → 복사·저장   │
 └────────────────────────────┬──────────────────────────────────────────┘
                              ▼
   ① 정책 → ② 출처 기록 → ③ 원본성 → ④ 안전 → ⑤ 발행 (문 5개)
                              ▼
 ┌─────────────────────────────────────────────────────────────────────┐
 │ External Publication Service — PIPELINE_PAUSE·발행 정책·사람 승인 적용 │
 │ Naver A/B = 복사 후 사람이 게시 · Chance = publish_flow: pr 만 ·     │
 │ Blogger = 초안까지만 · 기존 공개 글 = 읽기 전용                      │
 └─────────────────────────────────────────────────────────────────────┘
 [수익화 계층: 광고·Affiliate·협찬 상태] — 편집 계층은 읽을 수 없고, '이해관계 상태'만 공개 계층으로 한 방향 전달
```

**세 시스템의 위치(+ 새로 명시된 셋)**
- *생성기(블로그 저장소)*: 위 흐름을 Actions 에서 자동으로 돌리는 곳. 지금의 `NEWS_SOURCES → AI 글` 경로가 이 흐름으로 교체됩니다.
- *공공데이터 Provider(PD0–PD8)*: 'Provider 어댑터'에 들어가는 부품. 기획서의 Provider Catalog = Registry, Signal Schema = Fact 의 신호 종류, Mock Provider = 어댑터 시험용 가짜 Provider.
- *주제 조합 엔진(데스크톱)*: Local Draft Service 안의 단계. Provider 등급(Tier)은 점수를 바꾸지 않고 **통과·제외만** 정합니다.
- *초안 생성기*: 규칙 기반 조립기가 기본, AI 서술은 선택(R13).
- *Desktop 발행 연결*: Publication Service 쪽 — 채널별 정책(복사·PR·초안)만 구현하고 PAUSE 변수는 읽기 전용으로만 알 수 있음(쓰지 않음).
- *기존 글 감사 도구*: 그림자 모드 측정(`quality_shadow`)·Gate 의 규칙을 재사용(읽기 전용, 실제 흐름에 연결하지 않음).
- *정본과 복사본*: Registry 정본은 블로그 저장소, Desktop 은 읽기 전용 복사본 + 해시 시험(SA-1).


## 3. 핵심 부품

### 3-1. Registry (허용 목록)
Provider 는 '이용 조건이 같은 묶음'이고, **접근 경로(`access[]`)마다 종류가 있습니다**(API·CSV·데이터셋·RSS·HTML·이미지). 같은 기관이라도 약관이 다른 경로(보도자료 RSS 와 통계 API)는 따로 판정하고, Dataset·서비스·Endpoint 단위로 나눕니다. Text·Metadata·Image·제3자 요소의 정책이 다르면 필드 단위로 분리해 `exceptions[]` 에 둡니다.

| 칸 | 뜻 |
|---|---|
| `provider_id`·`name`·`class` | 이름과 종류(`data` 출처 / `internal` 자체 / `ops` 운영 도구 / `image` 이미지) — **AI 처리기는 여기 없고 `AI_PROCESSOR_POLICY`(3-5)에 둔다** |
| `policy.<7칸>` | 칸마다 `state`(ALLOWED/CONDITIONAL/DENIED/UNKNOWN)·`basis`(EXPLICIT/STANDARD_LICENSE/STATUTE/IMPLIED/NOT_ADDRESSED/NOT_READ)·증거 주소·열람일 |
| `strict_tier` | **실제 자동화 결정에 쓰는 유일한 값.** IMPLIED·NOT_ADDRESSED·NOT_READ·UNKNOWN 칸이 하나라도 있으면 3, DENIED 가 있으면 4, 모두 알려지면 1(표준 공개 라이선스·법령)·2(공식 API) |
| `permissive_interpretation` | 참고용. 표준 공개 라이선스가 목적 제한 없는 재사용을 허락하면 IMPLIED 를 허용으로 인정한 값 — **실행에 쓰지 않음** |
| `effective_status` | `strict_tier` 와 경로 유형으로 계산한 상태: `자동화 가능` / `자동화 제외` / `참고 전용` / `완전 제외` |
| `snapshot` | 약관 판독 기록: 읽은 페이지·열람일·내용 해시·`expires_at`(점검 기한) |
| `access[]` | 경로: 종류·기본 주소·인증·호출 한도·`robots` 점검일 |
| `attribution_template`·`exceptions[]`·`retention_days` | 출처 문구·적용 제외(제3자 자료·이미지·로고·개인정보)·저장 기간 제한 |

**경로 유형 규칙(운영자 기준)**: 외부 RSS 요약·기사/페이지 본문·검색 스니펫·연구기관 해설문·회사 보도자료·외부 사진·제3자 차트는 **유형만으로 Tier 3** 이고 `strict_tier` 가 1이어도 자동화되지 않습니다. 구조화 API·데이터셋만 `strict_tier` 를 따릅니다. Tier 4(상업 이용 금지·자동 수집 금지·로그인·유료·라이선스 불명·제3자 권리 혼합·개인정보·AI 입력 금지·재배포 금지)는 완전 제외입니다.

**ACTIVE 조건**: Tier 0·1·2 이고 `strict_tier` ≤ 2, 구조화 경로, 7칸에 UNKNOWN·미확인 0, 상업 이용·자동 접근이 DENIED 아님, `expires_at` 이 지나지 않음, 출처 표시가 조건부면 `attribution_template` 존재. 어긋나면 저장 단계에서 거부됩니다.

**정책 상태 사다리(기획서 §16)와의 관계**: UNVERIFIED/SCORING_ONLY/EVIDENCE_ALLOWED/AI_MINIMAL_ALLOWED/FULLY_ENABLED 는 그대로 '허락된 범위'를 나타내는 두 번째 축으로 둡니다. 다만 새 방침(하나라도 UNKNOWN 이면 제외)이 이기므로, 일부 칸만 알려진 Provider 에 SCORING_ONLY 를 주지 않습니다.

### 3-2. 약관 판독 기록(Policy Snapshot)과 자동 격리 — *완성형(재개 뒤)*
- 판독은 사람(또는 조사 에이전트)이 공식 약관을 읽어 Registry 에 기록하는 **오프라인 단계**입니다. 운영 중에는 약관을 해석하지 않습니다.
- 운영 중에는 감시만 합니다: 등록된 Provider 의 `snapshot.terms_pages` 를 주 1회 가져와 내용 해시를 비교하고, `expires_at`(기본 Tier 2 API 90일·Tier 1 180일·robots 30일)이 지났거나 해시가 바뀌었거나 약관 주소가 404·차단이면 **그 Provider 만 QUARANTINED**.
- 격리는 자동, **풀기는 수동**(복구 제안 PR 을 사람이 병합). 약관을 읽을 수 없거나 사람이 확인해야 하는 곳은 질문하지 않고 OFF 로 둡니다.
- 도구가 공식 약관 페이지를 못 읽으면 **우회하지 않고** `NOT_READ` 로 둡니다. 근거는 공식 문서와 공식 Browser 열람뿐이고 포럼·질문 답변은 정책 근거로 확정하지 않습니다.

### 3-3. Fact 와 출처 기록(Provenance)
- **수집 기록(SourceRecord)**: Provider·접근 경로·요청 주소·**Retrieved At**·응답 내용 해시·그때의 **License Snapshot**·저장 기한.
- **Fact**: `fact_id`(내용 해시)·Provider·**Source Record ID**·종류(수치·날짜·시각·지역·관측값·공식 상태·분류코드·가격·행사 시작/종료일·법령 시행일·API Version)·키·값·**단위**·**기준일시**·**지역**.
- **파생 Fact**: 계산식 번호 + 입력 Fact id + 결과. 계산식은 결정적 함수이고 AI 는 계산하지 않습니다.
- 글 본문의 숫자·날짜는 `{{F:fact_id}}` 같은 참조 표시이고 렌더링 때 값이 들어갑니다. 출처 없는 사실은 초안에 넣을 수 없습니다.
- 자동화에 쓰지 않는 것: 외부 본문 문장·기사 문단·해설문·홍보문·검색 스니펫·외부 사이트 결론·제3자 차트·외부 사진·외부 사례 서술. 처리 흐름은 **공식 구조화 데이터 → Normalized Fact → 자체 계산 → 자체 비교·분석 → 자체 문장**.

### 3-4. 다섯 개의 문 (Gate)
| 문 | 검사 | 실패하면(질문 없이) |
|---|---|---|
| ① 정책 | 쓰려는 모든 Provider 가 ACTIVE(strict)이고 7칸 중 UNKNOWN 이 없다, Snapshot 유효, 출처 표기 문구 포함 | 후보를 만들지 않음(Provider OFF) |
| ② 출처 기록 | 모든 숫자·날짜·코드가 Fact 참조이고 Provider·Source Record ID·기준일시·단위·지역·License Snapshot·Retrieved At 가 연결, AI 가 쓴 새 숫자 없음 | 초안 폐기 후 후보 보류 |
| ③ 원본성 | 외부 문장 복제 0, 불필요한 직접 인용 금지, 기존 Chance 글과 중복 검사, 한·영 단순 번역 구조 금지, **자체 계산·표·비교·분석 ≥1, 원자료 대비 추가 분석 ≥2** | 폐기 또는 분석 추가 재시도 1회 후 보류 |
| ④ 안전 | 건강 C 자동 중지, 실제 사용·방문·구매 주장·가격·협찬 관계 임의 생성 금지, 치료·완치·보장 표현 금지, 법률·재무 결과 단정 금지 | 건강 C 는 초안 생성 중지, 나머지는 폐기 |
| ⑤ 발행 | 정책·근거·독창성·안전·중복·정확성·채널 적합도 통과, `publish_flow: pr` 만, 하루 최대 1편, 사람 승인 | 보류 또는 PR 로 사람 승인 대기 |

현재 구현 중인 최소 품질 Gate(`pipeline/quality_gate.py`)와 그림자 모드 측정 도구(`pipeline/quality_shadow.py`)는 ③·④·⑤ 의 일부로 그대로 들어갑니다(대응표는 GATE 구현 보고서 기준).

### 3-5. `AI_PROCESSOR_POLICY` — AI 처리기(Gemini 등)의 별도 정책
Source Tier 표에는 넣지 않고, 필드를 따로 둡니다: `professional_business_use`·`consumer_use`·`free_service_data_use`·`paid_service_data_policy`·`sensitive_data_allowed`·`medical_advice_use`·`input_scope`·`raw_source_text_allowed`·`credential_storage`·`policy_version`·`policy_verified_at`.
- **초기 기본값**: Raw 외부 본문 입력 금지 · Signal·검증된 최소 Fact 만 입력 · 개인정보·기밀·Credential 입력 금지 · 무료 서비스에 미공개 원고 전체 입력 금지 · 의료 조언 생성 금지 · Key 는 Windows Credential Manager(Desktop)·GitHub Secrets(Actions).
- **AI 에 넘기는 것**: 내부 Signal·검증된 최소 Fact·Source ID·출처 표시 필요 상태·사용자 직접 입력·승인된 채널 프로필. **넘기지 않는 것**: 외부 웹페이지 본문·기사 전체·연구기관 해설문·RSS 요약·Raw API 전체 응답·라이선스 불명 자료·제3자 이미지·차트·개인정보.
- **AI 출력 검증(위반 시 자동 보류)**: 원자료에 없는 숫자 · 존재하지 않는 인용 · 공식 등급 변경 · 실제 경험·방문 주장 · 건강 효과 단정 · 협찬·가격 임의 생성. **AI 오류·거부는 규칙 기반 초안 또는 보류**로 처리합니다.
- 현재 값(R-216 1-6): Gemini API 추가 약관 시행일 2026-03-23 — 무료는 입력·출력이 제품 개선에 쓰이고 사람 검토자가 읽을 수 있으며 유료는 쓰이지 않음, 이용은 업무·전문 목적으로 한정.

### 3-6. 편집·수익화·공개 3계층
- **Editorial**: 주제·사실·근거·분석·안전 판정. **Monetization**: 광고·Affiliate Link·협찬 상태·경제적 이해관계. **Publication**: 고지 문구·링크 배치·공개 상태·사람 승인.
- 코드 경계: 수익화 코드는 편집 코드에서 import 할 수 없고, 점수 입력 스키마에 협찬·제휴 칸이 없습니다(시험으로 확인). 광고주 자료는 Provider 로 등록할 수 없고(검증기가 거부) 공식 근거로 쓰지 않습니다. 협찬 가능성은 주제 점수에 가산하지 않습니다. 광고·협찬 때문에 출처 사용료·추가 허가비가 필요한 구조는 만들지 않습니다.
- 실제 경제적 이해관계는 명시적 상태(`NONE`·`SPONSORED`·`AFFILIATE`·`SELF_USE_VERIFIED`·`UNKNOWN`)가 필요하고, `UNKNOWN` 이면 후기형을 쓰지 못하며 직접 사용하지 않은 제품은 후기형으로 쓰지 않습니다. Affiliate Link 는 글이 만들어진 뒤 공개 계층에서만 붙고 사실 판단 코드는 볼 수 없습니다. 고지 문구와 의무의 세부는 한국 규정을 읽어야 해서 **조사 필요(SA-8)** 입니다.


## 4. 두 단계로 나눕니다 — 제한 재개용 *최소*와 *완성형*

운영자 결정: 새 권리 안전형 상위 아키텍처 **전체**를 제한 재개의 선행조건으로 만들지 않습니다. 제한 재개(목표 11-16–19, PR 승인형)에는 아래 16항목의 *최소* 범위만 필요하고, 완성형(목표 11-23–30)은 재개 뒤 병렬로 구현합니다.

### 4-1. 제한 재개 전 필수 16항목 — 지금 상태

| # | 항목 | 어떻게 보장하나(최소 구현) | 지금 상태 |
|---|---|---|---|
| 1 | 일반 웹 크롤링 경로 비활성 | 외부 호출을 한 관문으로 모으고 허용 목록에 없는 호스트는 거부 + 피드·페이지 발췌 경로를 설정 한 곳에서 끔 | 미구현 — CRAWL 목록(R-216 2절)이 끌 지점을 정리 |
| 2 | Pew 웹페이지·RSS 비활성 | 위와 같은 설정(Pew 항목 OFF). 지금은 정지 중이라 실제 호출 0 | 미구현(결정은 기록됨) |
| 3 | Tier 0–2 Allowlist 만 | 최소 `allowlist` 파일(호스트·경로·Tier·7칸 요약·`effective_status`) + 관문 검사 | 미구현 |
| 4 | UNKNOWN Provider 비활성 | 검증기: strict 7칸에 UNKNOWN 이 있으면 ACTIVE 저장 거부 | 미구현 |
| 5 | 외부 본문·기사·해설문 저장과 AI 입력 금지 | 프롬프트 조립부에서 외부 텍스트 필드 제거 + 이력 저장 필드 점검 시험 | 미구현 — 어느 필드가 들어가는지 CRAWL 이 확인 |
| 6 | 구조화 Fact 와 자체 계산만 초안에 전달 | 어댑터 1–2개 + Fact 레코드 + 규칙 기반 조립기(+ 선택적 AI 서술) | **미구현 — 가장 큰 일**(신규 경로) |
| 7 | 최소 품질 Gate | `quality_gate.py` 규칙 8가지를 생성기 한 곳에 연결, 국문 전용 경로 | 구현·시험 진행 중(GATE: 규칙 103개·연결 52개 시험 통과, 병합 전) |
| 8 | 그림자 모드 ≥3회 | `quality_shadow.py` 측정 + 읽기 전용 그림자 실행 + `chance-shadow.yml` | 도구 완성·독립 검증 중(SHADOW), 실행 경로 구현 중(GATE·LOCK) |
| 9 | 초안 ≥10건 평가 | 6 이 서야 시작 | 대기 |
| 10–13 | 필수·높음 결함 0 · 건강 C 누락 0 · 가짜 수치·인용 0 · 번역 복제 0 | 9 의 평가 결과 + Gate ③④ 가 잡는지 시험 | 대기(6·9 이후) |
| 14 | `publish_flow: pr` 시험 통과 | 발행 잠금·초안 PR 흐름·후속 5가지 | 구현 중(LOCK·R2, 병합 전) |
| 15 | 하루 최대 1편 | 코드로 강제(지금은 정기 실행 슬롯이 하루 2편을 정함) | 구현 중(LOCK) |
| 16 | 사람 승인 없는 공개 경로 0 | 공개 경로 전수 조사 + 잠금 + 시험 | 구현 중(LOCK) |

**읽는 법**: 7–8·14–16 은 이미 다른 에이전트가 만들고 있고(병합 순서 계획 그대로), 1–5 는 작은 구현(허용 목록 + 관문 + 설정), **6 이 새로 만들어야 하는 큰 부품**이며 9–13 은 6 이 선 뒤에야 측정할 수 있습니다. 즉 제한 재개의 일정은 사실상 '6 이 언제 서는가'와 'strict 로 통과하는 Provider 가 있는가'에 달려 있습니다.

### 4-2. 완성형(재개 뒤 병렬, 목표 11-23–30)
정식 Source Registry(스키마·검증기·Dataset 단위 항목) · Policy Snapshot · 정책 만료·재검증 · Fact Provenance 전체 · 라이선스 변경 감지 · Provider 자동 격리 · 주간 예외 요약 · 편집·수익화·공개 계층 분리의 코드 경계 · 전체 Provider Tier 감사(후보 목록 `open API source.txt` 포함) · 규칙 문서(`AGENTS.md`·`SECURITY_GUARDRAILS.md`) 갱신.


## 5. 하위 시스템별 반영

| 시스템 | 지금 | 새 구조에서 | 제한 재개용 최소 | 완성형(재개 뒤) |
|---|---|---|---|---|
| **생성기**(블로그 Actions) | RSS 요약·기사 소개문 → AI → 글 → 직접 게시(정지 중) | 허용 목록 → 외부 호출 관문 → Fact → 규칙 기반 조립 → 문 5개 → `publish_flow: pr` | 크롤 스위치 + 최소 허용 목록 + 구조화 Fact 경로 1–2 + Gate(진행 중) + 발행 잠금(진행 중) | 정식 Registry·Snapshot·자동 격리·주간 요약 |
| **Source Provider(어댑터)** | 피드 파서(`parse_feed`)뿐 | API·CSV·JSON 만 읽는 어댑터. HTML·RSS 본문 파서는 없음 | 어댑터 1–2개(허용 목록을 통과한 Provider 가 생기는 만큼) | Dataset 단위 어댑터 확장 |
| **공공데이터 Provider(PD0–PD8)** | 기획서 단계, 후보 목록 `open API source.txt` | **PD0 = Registry 구현.** 오늘까지 읽은 후보 21행(통계·기상·관광·법령·해외 API)은 strict 로 전부 자동화 제외 | PD0 의 첫 일 = Dataset 단위 판정과 AI 입력 칸 해석 1건(8절) | PD1–PD8 은 기획서 순서 그대로(구현 전에 7칸 증거가 먼저) |
| **주제 조합 엔진**(Desktop) | 시드·후보·점수·보류·안전 판정(구현됨), 트렌드는 인터페이스만 | 변경 없음. Provider Tier 는 점수가 아니라 통과·제외만. 트렌드 Provider 는 외부 호출 관문 뒤에 주입 | 변경 없음(P4d·P4e 계속) | 관문·허용 목록 연결 |
| **초안 생성기** | 클라우드: AI 가 전체 작성 / Desktop: 규칙 기반 본문 서비스(M022 병합됨) | 규칙 기반 조립이 기본, AI 서술은 선택(`AI_PROCESSOR_POLICY` 입력 범위 안) | 클라우드에 규칙 기반 조립기(Desktop 의 규칙 기반 본문 설계 재사용 검토) | AI 서술·출력 검증 |
| **Desktop 발행 연결** | Naver 복사 · CLI 가 Chance main 직접 push | Publication 정책 게이트: Naver 복사 허용 · Chance `pr` 만(직접 push 기본 잠금) · Blogger 초안까지 | 직접 push 기본 잠금 + 경계 시험(E1–E3·T1) | 상태 파일로 정지·PR 방식 연결 |
| **광고·협찬 처리** | 광고 로더(템플릿 계층), 협찬·제휴 없음 | 3계층 분리, 이해관계 상태 필수 | 변경 없음(광고 코드 변경 금지) | 코드 경계 시험·고지 문구(SA-8 조사 후) |
| **기존 글 감사 도구** | 감사 스크립트·그림자 모드 측정(`quality_shadow`) | Gate 규칙과 그림자 모드 재사용(읽기 전용, 실제 흐름에 연결하지 않음) | 그림자 3회·초안 10건 평가에 사용 | 정기 감사 |

## 6. Desktop 과 발행의 분리 — 요약 (자세한 분석은 R-216 5–8절)

- **Local Draft Service**(로컬 작성)는 `PIPELINE_PAUSE` 와 독립입니다: 지금도 호출 0·변수를 읽고 쓰는 코드 0·`PIPELINE_PAUSE=true` 여도 초안이 같습니다. 코드 경계(import)만 보강하면 됩니다(E1–E3·T1, 동작 변화 0).
- **External Publication Service**: `publish/`(Chance 전용 git push)가 정책 게이트 뒤로 들어갑니다. 지금은 CLI 가 정지와 `publish_flow` 를 모른 채 main 에 직접 push 할 수 있어 **기본 잠금**이 첫 조치입니다.
- **AI 처리기**는 두 곳 모두 같은 `AI_PROCESSOR_POLICY` 를 쓰고, Desktop 은 AI 코드가 아직 0이라 새로 붙일 때 입력 범위(Signal·검증된 최소 Fact 만)를 코드로 못박습니다.


## 7. 무인 운영 규칙표 (상황 → 동작) — 운영자에게는 개별 질문 없음

| 상황 | 동작 | 기록·알림 |
|---|---|---|
| 새 출처를 쓰고 싶음 | 약관을 읽어 증거와 함께 Registry 변경 PR(사람 병합 후에만 ACTIVE) | PR(병합 부탁 알림 M 번호) |
| 정책 불명(7칸 중 UNKNOWN) | Provider OFF — 질문 없음, 추가 문의 없음 | 일·주 요약의 '정책 차단' |
| 라이선스 변경·약관 해시 변경·약관 주소 404·차단·점검 기한 만료 | 해당 Provider 만 QUARANTINED, 풀기는 복구 제안 PR(사람 병합) | 요약 + 복구 제안 |
| API 실패(시간 초과·오류·한도 소진) | 지수 백오프 → 승인된 캐시(저장 조건 안) → 대체 Provider → 내부 Seed | 연속 3회 실패 시 그날 후보 생성 건너뜀, 'Provider 오류' 집계 |
| 근거 부족(Fact 부족·출처 기록 실패) | 후보 보류(HOLD, 보류 90일 재진입 규칙 그대로) | '데이터 부족' 집계 |
| 건강 C | 초안 생성 중지 | '건강 C 차단' 집계 |
| 비교 불가 | `CONTEXT_ONLY` 또는 폐기 | 후보 상태 기록 |
| 이미지 권리 불명 | 이미지 없이 진행(외부 사진은 자동화 제외) | — |
| AI 오류·AI 출력 검증 위반 | 규칙 기반 초안 또는 보류 | '처리 성공/보류' 집계 |
| 같은 Provider 에서 Gate 실패 연속 | 그 Provider 일시 중지 | 요약에 집계 |
| 모든 Provider OFF·격리 | 후보 생성 중지(발행 0 은 정상) | **즉시 정보 알림 1건**(확인 요청 아님) |

운영자에게 가는 것은 **일별·주별 요약**뿐입니다: 처리 성공 · 정책 차단 · 데이터 부족 · Provider 오류 · 건강 C 차단 · 사람 검토 대기 · 공개 대기. 기존 '[운영] 확인 필요 모음' 이슈와 텔레그램 정보 알림 한 통을 전달 통로로 씁니다(수치·비밀 금지 규칙 그대로).


## 8. 일정과 설계 결정

일정은 R-216 10절이 정본입니다: 제한 재개 11-16–19(여유 0일, 위험 3: Provider 0곳·구조화 Fact 경로·병합 속도) / 완성형 11-23–30(제한 재개의 선행조건 아님).

**R-216 보강 — 공공누리 AI유형·제0유형 구조화 데이터셋 탐색(TE) 결과**
- **strict 로 통과하는 행은 0개**입니다. 7칸을 판정한 행은 7개(공공데이터포털 데이터셋 6·미국 NWS API 1)이고 제안 Tier 는 2가 2행(조석예보 15156018·NWS API)·3이 5행입니다.
- **공공누리 AI유형·제0유형 표시가 붙은 데이터셋은 못 찾았습니다**(직접 연 데이터셋 16건 + TD 3건 = 19건에 0건). 포털 검색에는 이용허락범위 필터가 없고 키워드 검색은 라이선스로 걸러지지 않습니다.
- 읽은 19건 중 13건은 이용허락범위가 '제한 없음'인데 정의 문장이 없어 상업·가공·저장·출처·AI 5칸이 모두 `IMPLIED` 입니다 — strict 에서는 오히려 공공누리 제1유형보다 불리합니다. AI 학습을 내세운 데이터셋(행안부 정부 공문서 AI 학습데이터·AI허브·도로공사 학습데이터셋·마사회 AI기반연구용)도 AI유형 표시가 없습니다(각각 '제한 없음'·제2유형(상업 금지)·이용허락범위 칸 비어 있음·'제한 없음').
- 막힌 칸이 가장 적은 후보: 미국 NWS API(AI 입력 1칸, 단 문서는 호출을 안내하는데 API 호스트 robots 가 전면 차단이라 충돌 — 감사자 결정으로 남김), 조석예보 15156018(제1유형·제3자 표시 없음, 저장·AI 입력 2칸), 법제처 현행법령 목록 15056821('제3자 권리 포함 + 제1유형', 저장·AI 입력 2칸).
- **결론: AI유형 경로로 strict 통과 Provider 를 찾는 길은 지금 막혀 있습니다.** 그래서 R-216 4절의 **운영자 해석 1건**이 사실상 제한 재개의 열쇠입니다. 질문을 이렇게 좁힙니다: *"표준 공개 라이선스(CC BY 4.0·OGL v3.0·통계청 Open Licence)와 미국 연방 공공영역이 '목적 제한 없는 이용'을 직접 적은 문구를 AI 입력 칸의 명시 근거로 인정할까요?"* 기본값은 **아니오(strict 유지)** 이고, 인정하면 permissive Tier 1 후보 10곳 중 구조화 경로가 있는 곳(NOAA 우주기상센터·캐나다 통계청 WDS·Eurostat)이 규칙 기반 초안 경로에서 바로 허용 목록에 들어갑니다.

**설계 결정 기록**(위임 규칙 — 운영자가 답하지 않아도 기본값으로 진행, 바꾸고 싶으면 알려 주세요)

| 번호 | 결정 | 기본값 | 이유 |
|---|---|---|---|
| SA-1 | Registry 정본 위치 | 블로그 저장소가 정본, Desktop 은 읽기 전용 복사본 + 해시 시험 | 자동 실행이 블로그 쪽에서 돔 |
| SA-2 | `IMPLIED` 근거 처리 | **strict 만 실행**(IMPLIED·NOT_ADDRESSED·NOT_READ = UNKNOWN). permissive 는 참고. 위 해석 1건은 운영자 결정 | 운영자 지시(2026-11-09) |
| SA-3 | 점검 기한 | Tier 2 API 90일·Tier 1 180일·robots 30일·약관 해시 주 1회 | 약관은 API 쪽이 더 자주 바뀜 |
| SA-4 | 약관 감시 호출 | 등록된 Provider 의 약관 주소만 주 1회 | '미등록 접근 금지'의 예외를 가장 좁게 |
| SA-5 | RSS 제목·날짜·링크 '신호'도 쓸지 | 쓰지 않음(결정 5 를 보수적으로 해석) | 제목·요약도 해설문의 일부 |
| SA-7 | 이미지 | 자체 생성 표·차트·사용자가 고른 로컬 이미지가 기본, 없으면 이미지 없음. Unsplash 는 자동 선택 끔 | 감사표: Unsplash 자동 이용 Tier 4, 외부 사진은 자동화 제외 |
| SA-8 | 협찬·제휴 표시 | 협찬·제휴 글은 글머리 고지 필수, 후기형은 `SELF_USE_VERIFIED` 일 때만. 표시 문구·의무의 세부는 조사 필요(한국 규정) | 아직 읽지 않음 |
| SA-9 | 주간 예외 요약 통로 | 기존 '[운영] 확인 필요 모음' 이슈 + 텔레그램 정보 알림 한 통 | 새 통로를 만들지 않음 |
| SA-10 | MVP 첫 Provider | 위 해석 1건과 Dataset 단위 판정 결과에 따름(후보: NOAA 우주기상센터·캐나다 통계청 WDS·Eurostat·조석예보) | strict 통과가 아직 0 |
| SA-11 | Desktop 의 Chance 직접 push | **기본 잠금**, PR 방식이 서면 연결 | 운영자 채널 정책(Chance 는 PR 만) |
| SA-12 | 병합 순서 | Lane B(제한 재개 선행) 병합 우선, Desktop 병합은 블로그 병합 사이에 끼워 넣음(한 번에 하나) | 두 영역은 서로의 완료 조건이 아님 |

운영자께 **답을 요청하는 것은 위 해석 1건 하나**(기본값 strict 유지)입니다.


## 부록 A. 지금 생성기의 데이터 흐름 (변경 전, 사실 확인 — 전체 경로는 R-216 2절)

- 출처 목록 `NEWS_SOURCES` 20개(피드 19개 + Pew). 이 중 **기사 페이지 발췌 경로가 열린 소스는 10개**(NASA·Federal Reserve 보도자료·EU 집행위 본 사이트·EU Energy·EU Environment·JRC·EU Digital Strategy·통계청 3개), **닫힌 소스 9개**(Pew·GOV.UK 3개 중 에너지·환경과 과학·기술, CMA·FTC·FEDS Notes·EU R&I·EU 고용·NSF — 기사 페이지를 읽지 않고 피드 요약만), **보류 1개**(UN News — 약관 확인 보류라 읽지 않음).
- 항목마다: 제목·링크·요약(최대 1,800자)을 읽고, 제외 규칙(제목·태그·주소)·주제어·신선도·'신뢰 도메인'을 통과한 것만 후보. 요약이 100자 미만이고 페이지 발췌가 열린 소스면 기사 페이지에서 소개 문구를 가져온다(2026-10-26 조사: 거의 효과 없음). 소스당 한 번의 실행에서 페이지 읽기는 최대 5회.
- 모델(Gemini)에게 후보의 제목·요약·링크와 소스별 고지문·인용 형식·작성 지침을 주고 새 글을 쓰게 한다(요약은 '문장을 그대로 옮기지 마세요' 지침이 붙음). 글은 기존 검사를 거쳐 지금은 직접 게시(`publish_flow: direct`)이며 정지 변수로 멈춰 있다.
- 이미지: Chance 갈래는 Unsplash API 검색과 `images.unsplash.com` 핫링크(공개 글 49편), NASA 이미지 1편. 49편 중 사진작가·Unsplash 출처 표시가 있는 글은 12편, 없는 글 37편(별도 정정 후보).
- `TRUSTED_SOURCE_DOMAINS`(분야별 6목록, 합 70개 안팎)에는 피드가 없는 도메인(who.int·oecd.org·imf.org·worldbank.org·bok.or.kr·kostat.go.kr·korea.kr·mfds.go.kr·reuters.com·apnews.com 등)이 많다. 이들은 과거 뉴스 검색 경로의 잔재로, **지금은 접근 경로가 없다.** 새 구조에서는 Registry 에 없으므로 전부 '미등록 = 접근 금지'가 된다.

## 부록 B. 규칙 → 예문 → 시험 (구현 때 먼저 만들 시험 목록)

| 규칙 | 지켜지는 예 | 어기는 예 | 시험(이름은 제안) |
|---|---|---|---|
| R1 Registry 가 정본 | Registry 의 ACTIVE 만 출처 목록에 나타남 | 코드에 출처를 직접 추가 | `test_sources_derived_from_registry` |
| R2 모든 외부 호출은 egress | 어댑터가 `egress.fetch('stat_provider','daily')` 호출 | `urlopen('미등록호스트')` | `test_egress_blocks_unregistered_host`, `test_no_direct_network_calls_outside_egress`(소스 스캔) |
| R3 7칸 모두 알려져야 ACTIVE | 칸 7개가 ALLOWED/CONDITIONAL + 근거 | `ai_input: UNKNOWN` 인데 ACTIVE | `test_registry_rejects_active_with_unknown` |
| R4 허가 문의 없음 | 약관을 읽고 증거를 첨부한 변경 PR | 출처에 메일을 보내는 코드 | `test_no_outbound_mail_code`(메일 전송 모듈·문의 문구 금지) |
| R5 본문 파서 없음 | 어댑터가 JSON·CSV 만 읽음 | 어댑터가 HTML 본문을 읽음 | `test_adapters_have_no_html_parsing` |
| R6 Fact 에는 단위·기준 시점 | `{값, 단위, 기준 월}` | 단위 없는 숫자 | `test_fact_requires_unit_and_as_of` |
| R7 파생 Fact 는 결정적 계산 | 입력 Fact id 가 기록된 전월 대비 | AI 가 쓴 '약 12% 증가' | `test_derived_fact_inputs_recorded`, `test_numbers_only_from_fact_refs` |
| R8 출처 기록 필수 | 모든 Fact 에 수집 기록 id | 출처 없는 Fact | `test_fact_has_source_record` |
| R9 개별 격리 | A 만 QUARANTINED, B 는 계속 | 하나가 문제인데 전체 정지 | `test_quarantine_is_per_provider` |
| R10 무인 상태 기계 | 7절 표의 상황 → 동작이 코드의 표와 일치 | 질문 알림을 보내 사람 응답 대기 | `test_unattended_matrix_matches_doc`, `test_no_blocking_question_path` |
| R11 광고·협찬 경계 | 점수 입력에 협찬 칸 없음 | 협찬 가능성으로 점수 가산 | `test_editorial_cannot_import_monetization`, `test_score_input_has_no_sponsorship_field` |
| R12 사람 승인 없는 공개 경로 0 | 공개는 PR 병합뿐 | 직접 푸시 경로 | LOCK 의 `publish path` 시험과 연동 |
| Gate ① 만료 | 만료일 지난 Snapshot → 후보 없음 | 만료 후에도 호출 | `test_expired_snapshot_blocks_provider` |
| Gate ③ 분석 2개 | 표 + 전월 대비 2개 | 표만 있는 글 | `test_originality_requires_two_analyses` |
| 이미지 | 권리 불명 → 이미지 없음 | 불명 이미지 삽입 | `test_unknown_image_rights_renders_without_image` |

## 부록 C. 기존 자산 → 새 구조 매핑

| 지금 있는 것 | 새 구조에서 |
|---|---|
| `generator.py` `NEWS_SOURCES` 20개 | Registry 의 Provider 로 옮기되 'legacy-text' 표시, M5 에서 폐기 |
| `TRUSTED_SOURCE_DOMAINS` | Registry 로 대체(미등록은 접근 금지) |
| `TERMS_BLOCKED_DOMAINS` + 근거 주석 | Registry 의 Tier 4·OFF 항목, 근거 문장 보존 |
| `docs/analysis/2026-10-26_overseas-sources.md`, `2026-10-25_publish-readiness.md` | 초기 증거(오늘 다시 읽은 것은 감사표가 새 증거) |
| `pipeline/gates.py`(진행 중)·그림자 모드 도구 | ③ 원본성·④ 발행 문의 일부, 측정치 |
| `publish_flow: pr`·발행 잠금(LOCK)·R2 후속 | ④ 발행 문 — 사람 승인 단계 |
| `pipeline/main_image.py`·생성기의 Unsplash 호출 | `class: image` Provider(자동 선택은 끄고 사람 선택은 데스크톱에서) |
| `pipeline/llm.py` Gemini | `class: tool` |
| ops-inbox('[운영] 확인 필요 모음') | 주간 예외 요약의 전달 통로(새 이슈 만들지 않고 기존 모음에 항목 추가) |
| 데스크톱 `topics/*`(seeds·score·select·hold·safety·trend…) | 주제 조합 엔진 — Provider Tier 는 점수에 안 들어감, 신호는 Fact 로 |
| 데스크톱 `content/*`·`service/gate.py`·`check/claims` | 초안 조립기와 ③·④ 문 |
| `open API source.txt` 후보 목록 | PD0 검증 후보(전부 미검증 = OFF) |
| `docs/SECURITY_GUARDRAILS.md`·`AGENTS.md` | 규칙 문서 갱신(이 설계가 승인된 뒤) |

## 부록 D. 용어

- **Provider**: 이용 조건이 같은 출처 묶음(예: 통계 API 하나).
- **수집 기록(SourceRecord)**: 한 번 가져온 것의 기록(주소·시각·내용 해시·그때의 약관 판독 기록 번호).
- **Fact**: 구조화된 값 하나(수치·날짜·지역·상태·코드) + 단위 + 기준 시점 + 수집 기록 번호.
- **파생 Fact**: 코드가 계산한 값(비율·증감·순위·평균·차이) + 계산식 번호 + 입력 Fact 번호.
- **신호(Signal)**: 주제 점수에 쓰는 Fact(타이밍·관심도·비교). 공공데이터 기획서의 Signal 과 같은 것.
- **후보(Candidate)**: 주제 한 줄 + 근거 Fact 묶음. **초안(Draft)**: 후보로 조립한 글.
- **약관 판독 기록(Policy Snapshot)**: Provider 약관을 읽은 날·읽은 페이지·내용 해시·7칸 판독·점검 기한.
- **Tier**: 0 내부 / 1 퍼블릭 도메인·열린 라이선스 / 2 조건이 명시된 공식 API / 3 약관 모호(사람 참고만) / 4 금지(완전 제외).
- **정책 상태**: Provider 의 데이터가 갈 수 있는 범위(점수만 / 글 근거 / AI 입력 / 전부).
- **격리(Quarantine)**: 약관 변경·기한 만료 때 그 Provider 만 자동으로 끄는 상태. 풀기는 사람이 PR 로만.
- **계층(Layer)**: 편집(Fact·조합·초안)과 수익화(광고·협찬)를 코드와 데이터에서 나눈 것.
