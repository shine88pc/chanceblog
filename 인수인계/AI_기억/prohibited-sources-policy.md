---
name: prohibited-sources-policy
description: "사용자 방침 — 약관·표기·robots.txt(AI 크롤러 차단)가 이 용도를 막는 소스는 접근하지 않는다(득보다 실이 많다), 허가 전까지 유예하지 않고 제외"
metadata:
  node_type: memory
  type: feedback
  originSessionId: (세션 번호)
  modified: 2026-10-26T06:13:04.554Z
---

사용자(2026-10-26 채팅, AI타임스 처리 질문에 대한 답): "금지된 부분이라면 접근하지 않는 걸로 해. 득보다 실이 많은 것으로 판단돼". 그래서 AI타임스(기사 하단 "AI학습 및 활용 금지")를 소스·신뢰 목록에서 빼고 `TERMS_BLOCKED_DOMAINS`에 올렸고, 글감이 안 되던 TechCrunch·The Verge·Hacker News도 같은 원칙으로 뺐다(PR #27). 앞서 BBC·Guardian·Nature는 사용자가 직접 제외했고 MIT TR·BBC Technology는 약관을 읽은 뒤 제외했다.

같은 날 두 번째 결정(Ars·IEEE 제외 질문에 대한 버튼 답, 2026-10-26): "Ars·IEEE를 기술 소스에서 제외해줘(AI 크롤러를 막는 사이트는 접근하지 않는 원칙)". 즉 약관 문구뿐 아니라 **robots.txt가 AI 크롤러(ClaudeBot·GPTBot 등)를 이름으로 막는 사이트**도 같은 원칙으로 접근하지 않는다(PR #31). 우리 봇 UA(ChanceBlogBot)가 `*` 규칙으로 허용돼도 마찬가지다. 남은 소스(NASA·Pew·연준·전자신문)는 같은 날 robots.txt를 읽어 해당 없음을 확인했다(Pew는 `Content-Signal: ai-train=yes, ai-input=yes`로 이용 명시 허용).

2026-10-26 오후 세 번째 결정: 전자신문은 콘텐츠 이용에 정식 계약·사용료가 필요해 "무료 자동화 기반" 취지에 맞지 않는다며 제외(14번)하고, 그 출처 공개 글 1쌍도 비공개 전환(PR #36). **GOV.UK**는 robots.txt가 Meta의 AI 학습 크롤러(`meta-externalagent`)를 검색 경로 `/search/all*`에만 막는 것에 대해 사용자가 "AI 학습을 위한 목적이 아니기에 문제가 없을 것"이라 판단해 **사용을 허용**했다 — 즉 robots.txt가 AI 크롤러를 이름으로 막더라도 **이용 목적(학습 아님)·막는 경로(우리가 읽는 피드 경로 아님)가 다르면 제외하지 않을 수 있다**(Ars·IEEE처럼 AI 크롤러 다수를 `Disallow: /`로 막는 경우와 구분). 애매하면 사용자에게 묻는다. **Global Voices**(CC BY 3.0이지만 자체 AI 정책이 AI 작성 글을 받지 않음)는 사용자가 "제외해줘".

2026-10-26 오후 네 번째(기본값 적용): EU 집행위원회 **Press Corner 보도자료**(`ec.europa.eu/commission/presscorner`)는 앱 바닥글에 법적 고지·라이선스 링크가 없어 재사용 조건을 확인하지 못해 "불명확은 유예" 원칙대로 주소로 제외했다(PR #35 약관 검증 지적). 같은 맥락으로 Horizon 매거진(기자 이름 표기 의무)·Eurostat(자체 고지)도 주소로 뺐다.

**Why:** 광고(AdSense)가 붙는 자동 발행 사이트라 매체의 저작권·AI 이용 금지 표기를 어기면 삭제 요청·계정 위험이 있고, 공급이 줄어드는 손해보다 위험이 더 크다고 사용자가 판단했다("의심스러우면 게시하지 않는다" 원칙과 같은 방향). Ars·IEEE는 실제 공급도 거의 없었다(2026-10-26 월요일 오전 러너 실행에서 후보 0, 전부 36시간 초과).
**How to apply:** 새 소스를 넣거나 기존 소스를 점검할 때 약관·기사 하단 표기·robots.txt(AI 크롤러 이름 그룹, `Content-Signal`)를 먼저 읽고, 금지(또는 허가 필요)로 읽히면 '유예·허가 문의'를 제안하기 전에 접근하지 않는 쪽을 기본으로 한다. 금지로 읽힌 매체는 소스·신뢰 목록에 두지 않고 차단 목록에 올린다. 불명확한 소스(전자신문 등)는 유예로 두되 사용자에게 허가 문의 여부를 묻는다. 이미 공개된 해당 매체 출처 글의 비공개 전환은 별도 승인(T3)이다(MIT TR·AI타임스 2쌍은 승인받아 전환했고, Ars·IEEE 출처 3편은 승인 대기 15번). 관련: [[handover-single-work-file]] [[blog-project-principles]]
