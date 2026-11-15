---
name: source-allowlist-tier-architecture-2026-11-09
description: "운영자 2026-11-09 ~10:00 채팅 붙여넣기 — 외부 출처 아키텍처 방향 변경(자동 수집 → Source Allowlist·Tier 0–4·UNKNOWN=Provider 비활성·구조화 Fact만·Pew 자동 열람/RSS/신규 글 중지·문의 발송 안 함·Gate 4종·무인 운영·광고/협찬 분리), 요청=기존 Provider·Source 감사표 먼저 + 공통 상위 아키텍처 설계안(공개 글·설정 변경 금지)"
metadata:
  node_type: memory
  type: project
  originSessionId: 921b6032-bba9-4b52-8c2d-b24e5509c445
  modified: 2026-11-09T01:06:37.561Z
---

**출처:** 운영자 채팅 붙여넣기(2026-11-09 ~10:00, 일정 결정 다음 메시지). 핵심 문장: "목표는 다양한 웹사이트를 자동 수집하는 것이 아니라, 권리·약관·상업 이용·AI 이용조건이 명확한 구조화 데이터만 사용해 사람의 추가 판단 없이 안정적으로 운영하는 것."

**결정 10가지:** 1 Source Allowlist 방식 전환 / 2 Registry 에 없는 출처는 자동 접근 금지 / 3 이용조건 중 하나라도 UNKNOWN 이면 Provider 비활성 / 4 '추가 문의로 사용 가능하게 만드는 절차'는 기본 운영에서 제거 / 5 외부 본문·기사·해설문 자동 수집 안 함 / 6 숫자·날짜·지역·상태·코드 같은 구조화 Fact 만 사용 / 7 자체 계산·표·비교·해석으로 독창적 콘텐츠 / 8 정책 Snapshot·Fact Provenance 저장 / 9 라이선스 변경·정책 만료 시 해당 Provider 만 자동 격리 / 10 자동화 예외는 사용자 질문이 아니라 보류·제외·Fallback.

**Tier:** 0 사용자 자료·Chance 내부 데이터·프로젝트·발행 이력 / 1 CC0·Public Domain·명확한 공공 Open Data / 2 상업 이용·자동 접근·저장·가공 조건이 명시된 공식 API / 3 일반 웹페이지·약관 모호한 연구기관·회사·언론(사람 참고만, 자동화 금지) / 4 상업 이용 금지·자동 수집 금지·로그인·유료·제3자 권리 혼합(자동화 완전 제외).

**Pew:** 웹페이지 자동 열람 중지 · Pew RSS 자동 사용 중지 · Pew 기반 신규 자동 글 중지 · Pew 차트·이미지·본문 재사용 금지 · **Pew 사용 허가 문의는 현재 발송하지 않음**(확인 요청 006 의 결정 4 를 대체 — 운영자 폴더 `Pew_이용허가_문의_메일_초안.md` 는 '보류' 표기) · 기존 Pew 글은 이용조건 명확한 공공·국제기구 자료로 교체, 불가하면 통합/비공개 후보 · 개별 공개 Dataset 이 Registry 기준을 통과할 때만 별도 Provider 검토.

**Gate 4종:** Policy(commercial_use·automated_access·derivative_use·storage·ai_input·attribution·license — 하나라도 UNKNOWN 이면 자동화 제외) / Provenance(모든 숫자·사실에 Provider·Source Record 연결) / Originality(외부 문장 복제 0 · 자체 계산·표·비교·분석 1개 이상 · 원자료 대비 추가 분석 최소 2개) / Publication(정책·근거·안전·중복·정확성·채널 적합도 통과, `publish_flow: pr` 로만, 사람 승인 없는 공개 경로 0).

**무인 운영:** 정책 불명→질문 없이 Provider OFF / 라이선스 변경→Provider 격리 / 근거 부족→후보 보류 / 이미지 권리 불명→이미지 없이 진행 / API 실패→승인된 Cache·다른 Provider·내부 Seed Fallback / 건강 C→자동 폐기 / 비교 불가→CONTEXT_ONLY 또는 폐기 / 운영자에게는 개별 질문 대신 **주간 예외 요약**만.

**광고·협찬:** Editorial Layer 와 Monetization Layer 분리 — 광고주 자료를 공식 근거로 쓰지 않음 · 협찬 가능성을 주제 점수에 직접 가산 금지 · 실제 경제적 이해관계는 명시적 상태 필요 · Affiliate Link 와 사실 판단 분리 · 직접 사용하지 않은 제품을 후기형으로 쓰지 않음.

**요청(실행 순서):** ① **현재 공개 글·설정은 변경하지 말고** 기존 Provider·Source 를 새 Tier 기준으로 분류한 **감사표부터** ② 이 기준을 생성기·공공데이터 Provider·주제 조합 엔진의 **공통 상위 아키텍처**로 반영하는 **설계안**.

**Why / How to apply:** 운영자 목표가 '출처 문의·허가 확인 같은 사람 판단이 필요한 운영'을 없애는 것 — 정책이 불명한 출처는 질문하지 말고 꺼 둔다(기본값 OFF). 감사표는 7개 정책 칸(commercial_use·automated_access·derivative_use·storage·ai_input·attribution·license)을 ALLOWED/DENIED/UNKNOWN/CONDITIONAL 로 채우고 증거(공식 약관 페이지·열람일)를 붙이며, 읽지 못한 칸은 UNKNOWN 으로 두고 추정으로 메우지 않는다. 기존 증거: `docs/analysis/2026-10-26_overseas-sources.md`, 생성기 `NEWS_SOURCES[*].terms`, `TERMS_BLOCKED_DOMAINS`. Pew 페이지는 열지 않는다. 현재 생성기의 'RSS 제목·요약(최대 1,800자)을 모델에 주어 새 글을 쓰는' 방식은 결정 5·6 과 충돌 가능성이 있어 설계안에서 정직하게 짚고 제한 재개 일정(11-16–19)에 미치는 영향을 보고한다.

관련: [[task6-adsense-audit-2026-11-09]] [[confirm-006-operator-decisions-2026-11-09]] [[prohibited-sources-policy]] [[public-data-topic-composition-plan-v100]] [[topic-selection-strategy-v100]]

**★ 후속(같은 날 ~10:50·10:55 두 건): [[desktop-independence-and-refinements-2026-11-09]] 가 우선한다(Tier 정의 갱신·Desktop 독립·strict 만 실행·Gemini 분리 등).**
