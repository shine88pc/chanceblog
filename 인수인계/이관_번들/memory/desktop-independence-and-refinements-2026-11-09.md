---
name: desktop-independence-and-refinements-2026-11-09
description: "운영자 2026-11-09 ~10:50·~10:55 두 번의 붙여넣기 — ① Desktop 독립 운영 기준(작업 A·B 분리, PIPELINE_PAUSE 는 외부 발행만 정지, Local Draft/External Publication Service, 갱신된 Tier 3·4 정의, 16항목 제한 재개 범위 vs 11-23–30 완성형, 작업 요청 10개) ② R-216 조립 전 반영(EU 재사용/자동 접근/AI 입력/제3자 분리·16편 개별 감사, UN News 만 제외, Gemini=AI_PROCESSOR_POLICY, 실행은 strict_tier 만, TD 는 Dataset·Endpoint 단위)"
metadata:
  node_type: memory
  type: project
  originSessionId: 921b6032-bba9-4b52-8c2d-b24e5509c445
  modified: 2026-11-09T01:51:06.196Z
---

**출처:** 운영자 채팅 붙여넣기 두 건(2026-11-09 ~10:50 '외부 출처 안전 아키텍처 및 ChanceBlog Desktop 독립 운영 기준', ~10:55 'R-216 조립 전 반영'). 앞선 결정은 [[source-allowlist-tier-architecture-2026-11-09]] — 아래가 우선하며, 충돌하는 곳은 아래로 바꾼다.

**1. 작업 분리(병행하되 서로의 완료 조건으로 묶지 않음):** A ChanceBlog Desktop 개발(P4d 저장·백업·복원, P4e 초안 작성 화면 — 로컬에서 프로필 등록·Seed·후보·초안·편집·복사·백업·복원·네이버 글쓰기 열기 → 사람이 직접 검토·게시) / B 기존 공개 콘텐츠 품질 정비(Chance·Blogger 영문·출처·중복·번역·건강·광고 적합성·루트·고정 페이지·발행 Pipeline). P4d·P4e 완료·시험 통과 시 B 가 진행 중이어도 Desktop 을 로컬 작성 도구로 설치·사용할 수 있어야 한다. **P4d·P4e 를 권리 안전 아키텍처 전체 구현 때문에 중단하지 말 것**(Installer·개인 PC 검증까지 계속).

**2. PIPELINE_PAUSE 경계:** 외부 자동 생성·게시 Pipeline 의 정지 스위치(Chance 자동 작성·게시, Blogger 자동 초안, 자동 Issue 수정, 외부 공개와 연결된 수동 Pipeline, 사람 승인 없는 게시 경로). `true` 여도 Desktop 실행·로컬 프로필·Seed·후보·초안·편집·복사·백업·복원은 정상. 금지 구조: PAUSE=true → Desktop 전체 중지. 권장: **Local Draft Service(PAUSE 독립) / External Publication Service(PAUSE·발행 정책·사람 승인)**. **Desktop 은 PIPELINE_PAUSE Repository Variable 을 등록·수정·삭제하지 않는다.** 해제 조건: Chance=publish_flow: pr·Blogger 초안 전용·auto/direct 비활성·하루 최대 1편·무승인 공개 경로 0·최소 품질 Gate·그림자 모드·PR 생성 시험 — 변수 삭제만으로 auto/direct 로 복귀 금지.

**3. Desktop 제한 기능·채널 정책:** Chance 직접 자동 게시·auto/direct·Blogger 자동 게시·초안 PR 자동 병합·사람 미확인 공개·UNKNOWN 외부 출처 초안·웹/RSS 본문 자동 수집·기존 공개 글 일괄 수정/비공개·광고 설정·ads.txt·AdSense 재검토 요청은 비활성 또는 사람 승인 경로. Naver A/B=복사 후 사람이 직접 게시 / Chance=`publish_flow: pr` 만 / Blogger=초안까지만 / 기존 공개 글=읽기 전용(승인된 정비 배치 외 수정 금지).

**4. 갱신된 Tier 정의:** Tier 0 자체 데이터(사용자 입력·Chance 내부·프로젝트 이력·발행 이력·사용자 확인 경험·자체 계산) / Tier 1 명확한 Open Data(CC0·퍼블릭 도메인·이용조건 명확한 공공 Open Data·상업·가공 조건 확인된 Dataset) / Tier 2 명확한 공식 API(공식 Endpoint·자동 접근·상업 이용·저장·가공·출처 표시·호출량 정책 확인) / **Tier 3 자동화 제외·사람 참고만: 일반 연구기관 홈페이지·회사 보도자료·언론 기사·개인 블로그·일반 웹페이지·검색 Snippet·약관 모호 사이트·외부 RSS 요약(= 유형만으로 제외 — 발행자가 정부여도 RSS 요약·페이지 본문은 자동화 입력에서 빠짐)** / **Tier 4 완전 제외: 상업 이용 금지·자동 수집 금지·로그인·유료·라이선스 불명·제3자 권리 혼합·개인정보 포함·AI 입력 금지·재배포 금지.** Pew 는 별도 예외가 아니라 Tier 3 대표 사례(웹페이지·RSS 자동 사용 중지·신규 글 중지·본문/차트/이미지/PDF 재사용 금지·허가 문의 안 함·기존 글은 공공·국제기구 자료로 근거 교체, 불가하면 통합·비공개 후보, 개별 공개 Dataset 이 Registry 기준 통과 시에만 별도 Provider 후보) — **Pew 때문에 전체 감사·정비·제한 재개 일정을 지연하지 않는다.**

**5. 자동화에 쓰는 자료:** 숫자·날짜·시각·지역·관측값·공식 상태·분류코드·가격·행사 시작/종료일·법령 시행일·API Version·구조화 통계·사용자 직접 입력·자체 계산. 제외: 외부 본문 문장·기사 문단·연구기관 해설문·회사 홍보문·검색 Snippet·외부 사이트 결론·제3자 차트 이미지·외부 사진·외부 사례 서술. 흐름: 공식 구조화 데이터 → Normalized Fact → Chance 자체 계산 → 자체 비교·분석 → 자체 문장.

**6. 공통 Gate 5개:** Policy(7칸 중 하나라도 UNKNOWN → 제외) / Provenance(Provider·Source Record ID·기준일시·단위·지역·License Snapshot·Retrieved At — 출처 없는 사실은 초안 불가) / Originality(복제 0·불필요한 직접 인용 금지·기존 글 중복 검사·한·영 단순 번역 구조 금지·자체 계산·표·비교·분석 ≥1·원자료 대비 추가 분석 ≥2) / **Safety**(건강 C 자동 중지·실제 사용·방문·구매 주장/가격/협찬 임의 생성 금지·치료·완치·보장 금지·법률·재무 결과 단정 금지) / Publication(정책·근거·독창성·안전·중복·정확성·채널 적합도 통과 시에만 초안·PR 생성). **AI 는 선택**(없어도 규칙 기반 후보·초안): 전달 가능=내부 Signal·검증된 최소 Fact·Source ID·출처 표시 필요 상태·사용자 입력·승인 채널 프로필 / 금지=외부 본문·기사 전체·해설문·RSS 요약·Raw API 전체·라이선스 불명·제3자 이미지·차트·개인정보. AI 출력에 원자료에 없는 숫자·존재하지 않는 인용·공식 등급 변경·실제 경험/방문 주장·건강 효과 단정·협찬/가격 임의 생성이 있으면 자동 보류.

**7. 무인 예외·계층:** 정책 불명→Provider OFF / 라이선스 변경→격리 / API 실패→승인된 캐시·대체 Provider·내부 Seed / 근거 부족→후보 보류 / 건강 C→초안 생성 중지 / 비교 불가→CONTEXT_ONLY 또는 폐기 / 이미지 권리 불명→이미지 없이 / AI 오류→규칙 기반 초안 또는 보류. 운영자에게는 일·주 요약만(처리 성공·정책 차단·데이터 부족·Provider 오류·건강 C 차단·사람 검토 대기·공개 대기). 계층 3개: Editorial(주제·사실·근거·분석·안전 판정) / Monetization(광고·Affiliate·협찬 상태·경제적 이해관계) / Publication(고지 문구·링크 배치·공개 상태·사람 승인). 광고주 자료를 공식 근거로 쓰지 않음·협찬 가능성을 주제 점수에 가산하지 않음·광고·협찬 때문에 출처 사용료·추가 허가비가 필요한 구조 금지.

**8. 일정:** 제한 재개(11-16–19, PR 승인형) 전 필수 16항목 = 일반 웹 크롤링 경로 비활성 / Pew 웹페이지·RSS 비활성 / **Tier 0–2 Allowlist 만** / UNKNOWN Provider 비활성 / 외부 본문·기사·해설문 저장·AI 입력 금지 / **구조화 Fact 와 자체 계산만 초안에 전달** / 최소 품질 Gate / 그림자 모드 ≥3회 / 초안 ≥10건 평가 / 필수·높음 결함 0 / 건강 C 누락 0 / 가짜 수치·인용 0 / 번역 복제 통과 0 / publish_flow: pr 시험 / 하루 최대 1편 / 사람 승인 없는 공개 경로 0. **새 완성형 상위 아키텍처 전체를 제한 재개의 선행조건으로 만들지 않는다** — 재개 뒤 병렬: 정식 Source Registry·Policy Snapshot·정책 만료·재검증·Fact Provenance·라이선스 변경 감지·Provider 자동 격리·주간 예외 요약·Editorial/Monetization 분리·전체 Provider Tier 감사(목표 11-23–30).

**9. 완료 조건:** P4d 8개(topic_engine.db 저장·JSON 설정 저장·원자적 저장·실패 시 원복·백업에서 Credential/API Key 제외·완료/부분/실패 구분·다른 PC 복원·저장 실패가 기존 기능을 막지 않음) / P4e 14개(제목 후보 3·선택 제목 1·본문 전체·핵심/보조 키워드·태그·추천 카테고리·한 줄 요약·확인 권장 항목·개별 복사·복사됨 표시·AI 미연결 규칙 기반 초안·건강 C 자동 중지·경험/방문/가격/협찬 임의 생성 금지·출처와 확인 필요 상태 표시) — 두 에이전트에 전달함(P4d aaa1833711fbc1518·P4e a900dd80c36ca8861).

**10. 작업 요청 10개(먼저 분석 보고, P4d·P4e 중단 금지):** ①Source·Provider Tier 감사표 ②현재 자동 크롤링 경로 목록 ③비활성화할 Tier 3·4 경로 ④제한 재개용 최소 Allowlist ⑤Desktop·Publication Pipeline 의존성 분석 ⑥PIPELINE_PAUSE 적용 경계 ⑦로컬 Draft Service 분리 여부 ⑧외부 Publication Service 분리 여부 ⑨최소 품질 Gate 적용 위치 ⑩제한 재개 일정 영향. 담당 에이전트: 크롤 경로 a418f0719f6db902f(`CRAWL_BRIEF.md`→`audit6/crawl/`)·Desktop 의존성 a69a76bc170dbfdea(`DESKDEP_BRIEF.md`→`audit6/desktop_dep/`).

**11. R-216 조립 전 반영(~10:55):** ① **EU 계열**: EU 소유 Text·Data 의 CC BY 4.0 재사용 / 일반 웹페이지 자동 접근 / AI 입력 / 제3자 사진·표·외부 자료를 각각 판정(자동 접근·AI 입력 UNKNOWN 이면 미래 자동화만 비활성) — **기존 공개 글 16편은 자동 접근 UNKNOWN 만으로 일괄 비공개하지 말고** 문서마다 CC BY 4.0·Attribution·변경 표시·제3자 자료·직접 복제·독립 분석을 감사해 유지·정정·통합·비공개로 분류(에이전트 a1eb8492edc1dd53b `EC16_BRIEF.md`→`audit6/ec16/`). ② **UN**: UN News Web·RSS 만 신규 자동화 제외 — 모든 UN 기관·Dataset 전면 금지로 확대하지 말고 개별 공식 Dataset·문서는 별도 평가. ③ **Gemini 는 Source Tier 표에 넣지 않음**, AI Processor 로 별도 `AI_PROCESSOR_POLICY`(필드 11개: professional_business_use·consumer_use·free_service_data_use·paid_service_data_policy·sensitive_data_allowed·medical_advice_use·input_scope·raw_source_text_allowed·credential_storage·policy_version·policy_verified_at; 초기 기본값 = Raw 외부 본문 입력 금지·Signal/검증된 최소 Fact 만·개인정보/기밀/Credential 금지·무료 서비스에 미공개 원고 전체 입력 금지·의료 조언 생성 금지·Key 는 Windows Credential Manager). 도구가 공식 약관 페이지를 못 읽어도 **우회 금지** — 공식 Browser 열람과 공식 문서만, 포럼 질문은 정책 근거로 확정 금지. ④ 엄격·관대: 보고서에 둘 다 표시 가능하나 **실행은 strict_tier 만** — 필드명 `strict_tier`(실제 자동화 결정)·`permissive_interpretation`(참고)·`effective_status`(strict 기준). ⑤ TD 한국 공공데이터: 기관 단위가 아니라 Dataset·서비스·Endpoint 단위, Text·Metadata·Image·제3자 요소 정책이 다르면 필드 단위로 분리. ⑥ 공개 글·설정·광고·ads.txt·발행 설정은 변경 금지, R-216 감사표와 상위 아키텍처 초안까지만.

**내 해석·결과(2026-11-09):** strict 만 실행이면 외부 허용 Provider 는 지금 0곳(NASA 글은 strict Tier 1 이지만 RSS·페이지 본문 경로라 유형상 Tier 3) → 제한 재개용 최소 Allowlist 는 Tier 0 + TD 가 찾는 strict 통과 Dataset·Endpoint 뿐 — **가장 큰 일정 위험**. 설계안 SA-2(IMPLIED 인정)는 '참고(permissive)'로만 남기고 실행에서 뺀다. 운영자 확인 1건(기본값 strict 유지): 'ai_input 만 UNKNOWN 이고 AI 를 쓰지 않는 규칙 기반 경로'를 자동화로 허용할지. Tier 1·2 정의에는 AI 입력 확인이 없는데 Policy Gate 는 AI 입력 UNKNOWN 도 제외한다는 정의 간 간극도 보고에 적는다.

관련: [[source-allowlist-tier-architecture-2026-11-09]] [[confirm-006-operator-decisions-2026-11-09]] [[task6-adsense-audit-2026-11-09]] [[delegation-no-response-rules-2026-11-06]]
