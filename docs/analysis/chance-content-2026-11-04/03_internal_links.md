# 진단 담당 — 내부 링크 후보 목록 (이슈 #114 지시서 ‘5. 3단계: 내부 링크 시스템’)

- 작성: 2026-11-04, 진단 담당. 짝 문서: `01_diagnosis.md`(진단표). **읽기만 했다** — 저장소·사이트에 아무것도 쓰지 않았고 어떤 글에도 링크를 넣지 않았다. 이 문서는 ‘어디에 무엇을 걸면 좋은가’의 후보일 뿐이다.
- 대상은 **공개 글 38편**이다. 비공개 14편은 후보에서 뺐고(보내지도 받지도 않음), 자기 자신·없는 주소도 뺐다. **한글 글은 한글 글에만, 영문 글은 영문 글에만** 연결했다(독자가 언어를 바꾸지 않게; 한·영 짝 연결은 레이아웃이 이미 ‘다른 언어 버전’으로 보여 준다).

## 요약 한 장

1. **후보 56개**(공개 38편 중 34편에 있음). 연결 강도 강 20·중 24·약 12. 그중 ‘그 이야기를 공개로 유지할 때만’ 조건이 붙은 것 8개(멘토링 S12·LDT S20 관련). 서로 걸 수 있는(양방향) 쌍은 27쌍이다.
2. **후보가 없는 글 4편**: 식품 날짜(S06) 한·영, 캐나다 청년 고용(S19) 한·영 — 사이트에 같은 분야의 글이 없어 ‘없음’으로 둔다(억지 링크 금지). **후보가 1개뿐인 글 14편**은 아래 표에 표시했다.
3. **URL**: 모든 주소는 공개 사이트의 `posts.json`(`absoluteUrl`)에서 가져왔고 `sitemap.xml` 의 글 38개 주소와 38/38 일치한다. 파일 이름으로 주소를 추측하지 않았다 — 퍼머링크 규칙(`/posts/년/월/일/제목/`)이 같아도 식품 날짜 글 2편은 머리말의 `permalink` 로 영어식 주소(`south-korea-food-date-labels`, `korean-food-date-labels`)가 따로 정해져 있고, 나머지는 파일 이름의 `KR-081916` 같은 부분이 대소문자 그대로 주소가 된다.
4. **그래프 요약**: 글들은 다섯 묶음으로 나뉜다 — ① **우주·과학**(허블 S15, 보이저 S16, MMX S02, 우주날씨 S05; 멘토링 S12는 조건부) ② **Pew 미디어 3부작**(58% S07·광고 S08·신뢰 S09) ③ **EU 기후·환경**(기후 회복력 S17, JRC 대시보드 S14, 자연 크레딧 S13) ④ **EU 에너지**(CEF S10·정유 대화 S11) ⑤ **제조 AI**(원프레딕트 S03·KIMM S04, AI 쇼핑 S01은 약한 연결, LDT S20은 조건부). **허브가 될 글**은 허블 S15(우주 묶음을 잇는 가운데 글 — 후보는 한글 2개·영문 3개이고, 표준 사례로 다시 쓰일 글이라 거기서 나가는 링크의 가치가 가장 큼)·기후 회복력 S17(JRC·자연 크레딧을 잇고, 같은 날 나온 프론텍스 S18의 이웃)·Pew 58% S07(3부작의 입구). **고립된 글**은 식품 날짜 S06·캐나다 청년 고용 S19, **약하게만 이어진 글**은 프론텍스 S18(기후 회복력 하나)·AI 쇼핑 S01(원프레딕트 하나)·CEF/정유(서로 하나씩)이다. 주제가 6개 분야로 흩어져 있어(A1 보고서) 이어질 이웃이 원래 적다 — 이 점은 억지로 메우지 않는 편이 낫다.
5. **먼저 걸 만한 연결**(양쪽 글 모두에서 ‘강’인 이야기 쌍 5개): Pew 58%↔신뢰(S07↔S09), Pew 58%↔광고(S07↔S08), CEF↔정유 대화(S10↔S11), 원프레딕트↔KIMM(S03↔S04), JRC 대시보드↔기후 회복력(S14↔S17). 한·영 모두에 있으므로 글 쌍 10개(양방향이면 링크 20개)다. 허블 이웃 링크(S15↔S16·S05·S02)는 ‘중’이지만 허블 글이 표준 사례가 되므로 함께 시험하기를 권한다.

## 지키려 한 규칙 (지시서 5단계)

- 본문 중간에 자연스러운 관련 링크 1~3개, 글 하단 ‘함께 읽으면 좋은 글’ 2~3개. 관련 글이 부족하면 억지로 채우지 않는다.
- 후보 찾는 순서: ① 같은 기술·사건 ② 같은 산업·분야 ③ 기술·역사로 이어지는 글 ④ 다음 단계로 읽을 확장 주제. 표의 ‘연결 이유’에 어느 단계인지 풀어 적었다.
- 링크 텍스트는 **연결된 글의 내용을 정확히 설명**해야 한다. 아래 링크 텍스트는 모두 ‘지금 올라가 있는 글’의 내용에 맞췄다. 대폭 수정 대상 글(진단표 14편)이 다시 쓰이면 텍스트를 다시 확인해야 한다 — 되도록 다시 써도 유지될 말(주제 이름)로 지었다.
- 기존 글에 양방향 링크를 넣는 일은 지시서가 ‘별도 변경 범위를 확인한 후’ 하라고 했다. 아래에 ‘양방향 가능’으로 표시했고, 실제로 몇 편·몇 곳을 고칠지는 운영자가 정한다(본문 수정은 T1, 근거 필수).

## 이미 있는 장치와 한계 (`_layouts/post.html` 직접 읽음)

- 글 아래에 자동으로 ‘같은 분야의 글’(같은 언어이면서 머리말 `category` 문자열이 **글자 그대로 같은** 글 최대 3개)이 붙고, 하나도 없으면 ‘이어서 읽기’(같은 언어 최신 3개)가 붙는다. 비공개 글(`published: false`)은 빠진다. 글 위쪽에는 출처 주소가 같은 짝이 ‘다른 언어 버전’으로 보인다.
- 한계: 분류명이 19종으로 갈려 있어(‘Science & Environment’ vs ‘EN - Science & Environment’ 등) 같은 이야기인데 ‘같은 분야’로 묶이지 않는 경우가 있고, 반대로 분류만 같으면 주제와 무관한 글(예: 자연 크레딧 글 S13 한글판 아래에는 같은 ‘과학·환경’이라는 이유로 가장 새로운 세 글 — 보이저·허블·JRC — 이 붙는데, 허블·보이저는 주제 연결이 약하다. 정렬 동률 처리는 코드 읽기로 추정한 것)이 붙는다. 즉 **주제 연결이 아니라 분류명 일치**다.
- 이 블록·`_layouts/` 는 광고 표면이라 **고치려면 T3(운영자 승인)**. 그래서 아래 후보는 ① 본문 속 문장 링크(T3 아님)를 기본으로 짰고, 하단 영역은 ‘적용 방법’ 절에 선택지로 적었다.

---

# 1. 공개 38편 실제 주소 대조표

`posts.json` 의 `absoluteUrl` 이고 `sitemap.xml` 에도 있다(‘사이트맵’ 열이 ‘예’). 이 목록에 없는 주소는 후보에서 뺐다.

| # | 이야기 | 언어 | 파일(`_posts/` 아래) | 실제 주소 | 사이트맵 |
|--:|---|---|---|---|:-:|
| 1 | S01 | 한글 | `2026-10-18-AI.md` | https://shine88pc.github.io/chanceblog/posts/2026/10/18/AI/ | 예 |
| 5 | S07 | 영문 | `Culture & Media/2026-10-26-EN-182804.md` | https://shine88pc.github.io/chanceblog/posts/2026/10/26/EN-182804/ | 예 |
| 6 | S08 | 영문 | `Culture & Media/2026-10-30-EN-224001.md` | https://shine88pc.github.io/chanceblog/posts/2026/10/30/EN-224001/ | 예 |
| 7 | S09 | 영문 | `Culture & Media/2026-11-03-EN-155742.md` | https://shine88pc.github.io/chanceblog/posts/2026/11/03/EN-155742/ | 예 |
| 8 | S05 | 영문 | `EN - Science & Environment/2026-10-20-EN-125000.md` | https://shine88pc.github.io/chanceblog/posts/2026/10/20/EN-125000/ | 예 |
| 9 | S02 | 영문 | `EN - Space & Robotics/2026-10-18-EN-233513.md` | https://shine88pc.github.io/chanceblog/posts/2026/10/18/EN-233513/ | 예 |
| 11 | S03 | 영문 | `EN - Tech Insights/2026-10-19-EN-103939.md` | https://shine88pc.github.io/chanceblog/posts/2026/10/19/EN-103939/ | 예 |
| 12 | S10 | 영문 | `Economy & Work/2026-10-27-EN-093056.md` | https://shine88pc.github.io/chanceblog/posts/2026/10/27/EN-093056/ | 예 |
| 13 | S11 | 영문 | `Economy & Work/2026-10-29-EN-101652.md` | https://shine88pc.github.io/chanceblog/posts/2026/10/29/EN-101652/ | 예 |
| 14 | S06 | 영문 | `Everyday Life/2026-10-20-EN-141500.md` | https://shine88pc.github.io/chanceblog/posts/2026/10/20/south-korea-food-date-labels/ | 예 |
| 15 | S04 | 영문 | `Industrial AI/2026-10-19-EN-195755.md` | https://shine88pc.github.io/chanceblog/posts/2026/10/19/EN-195755/ | 예 |
| 17 | S03 | 한글 | `KR - 테크 인사이트/2026-10-19-KR-103939.md` | https://shine88pc.github.io/chanceblog/posts/2026/10/19/KR-103939/ | 예 |
| 19 | S12 | 영문 | `Science & Environment/2026-10-28-EN-111851.md` | https://shine88pc.github.io/chanceblog/posts/2026/10/28/EN-111851/ | 예 |
| 20 | S13 | 영문 | `Science & Environment/2026-10-29-EN-235205.md` | https://shine88pc.github.io/chanceblog/posts/2026/10/29/EN-235205/ | 예 |
| 21 | S14 | 영문 | `Science & Environment/2026-10-31-EN-115025.md` | https://shine88pc.github.io/chanceblog/posts/2026/10/31/EN-115025/ | 예 |
| 22 | S15 | 영문 | `Science & Environment/2026-11-02-EN-081916.md` | https://shine88pc.github.io/chanceblog/posts/2026/11/02/EN-081916/ | 예 |
| 23 | S16 | 영문 | `Science & Environment/2026-11-02-EN-100912.md` | https://shine88pc.github.io/chanceblog/posts/2026/11/02/EN-100912/ | 예 |
| 24 | S17 | 영문 | `Society & Policy/2026-10-27-EN-221527.md` | https://shine88pc.github.io/chanceblog/posts/2026/10/27/EN-221527/ | 예 |
| 25 | S18 | 영문 | `Society & Policy/2026-10-28-EN-184844.md` | https://shine88pc.github.io/chanceblog/posts/2026/10/28/EN-184844/ | 예 |
| 26 | S19 | 영문 | `Society & Policy/2026-10-30-EN-161110.md` | https://shine88pc.github.io/chanceblog/posts/2026/10/30/EN-161110/ | 예 |
| 31 | S20 | 영문 | `Technology & Future/2026-11-01-EN-163702.md` | https://shine88pc.github.io/chanceblog/posts/2026/11/01/EN-163702/ | 예 |
| 32 | S10 | 한글 | `경제·일/2026-10-27-KR-093056.md` | https://shine88pc.github.io/chanceblog/posts/2026/10/27/KR-093056/ | 예 |
| 33 | S11 | 한글 | `경제·일/2026-10-29-KR-101652.md` | https://shine88pc.github.io/chanceblog/posts/2026/10/29/KR-101652/ | 예 |
| 34 | S05 | 한글 | `과학 환경/2026-10-20-KR-125000.md` | https://shine88pc.github.io/chanceblog/posts/2026/10/20/KR-125000/ | 예 |
| 35 | S12 | 한글 | `과학·환경/2026-10-28-KR-111851.md` | https://shine88pc.github.io/chanceblog/posts/2026/10/28/KR-111851/ | 예 |
| 36 | S13 | 한글 | `과학·환경/2026-10-29-KR-235205.md` | https://shine88pc.github.io/chanceblog/posts/2026/10/29/KR-235205/ | 예 |
| 37 | S14 | 한글 | `과학·환경/2026-10-31-KR-115025.md` | https://shine88pc.github.io/chanceblog/posts/2026/10/31/KR-115025/ | 예 |
| 38 | S15 | 한글 | `과학·환경/2026-11-02-KR-081916.md` | https://shine88pc.github.io/chanceblog/posts/2026/11/02/KR-081916/ | 예 |
| 39 | S16 | 한글 | `과학·환경/2026-11-02-KR-100912.md` | https://shine88pc.github.io/chanceblog/posts/2026/11/02/KR-100912/ | 예 |
| 44 | S20 | 한글 | `기술·미래/2026-11-01-KR-163702.md` | https://shine88pc.github.io/chanceblog/posts/2026/11/01/KR-163702/ | 예 |
| 45 | S07 | 한글 | `문화·미디어/2026-10-26-KR-182804.md` | https://shine88pc.github.io/chanceblog/posts/2026/10/26/KR-182804/ | 예 |
| 46 | S08 | 한글 | `문화·미디어/2026-10-30-KR-224001.md` | https://shine88pc.github.io/chanceblog/posts/2026/10/30/KR-224001/ | 예 |
| 47 | S09 | 한글 | `문화·미디어/2026-11-03-KR-155742.md` | https://shine88pc.github.io/chanceblog/posts/2026/11/03/KR-155742/ | 예 |
| 48 | S17 | 한글 | `사회·정책/2026-10-27-KR-221527.md` | https://shine88pc.github.io/chanceblog/posts/2026/10/27/KR-221527/ | 예 |
| 49 | S18 | 한글 | `사회·정책/2026-10-28-KR-184844.md` | https://shine88pc.github.io/chanceblog/posts/2026/10/28/KR-184844/ | 예 |
| 50 | S19 | 한글 | `사회·정책/2026-10-30-KR-161110.md` | https://shine88pc.github.io/chanceblog/posts/2026/10/30/KR-161110/ | 예 |
| 51 | S04 | 한글 | `산업 AI/2026-10-19-KR-195755.md` | https://shine88pc.github.io/chanceblog/posts/2026/10/19/KR-195755/ | 예 |
| 52 | S06 | 한글 | `일상·마음/2026-10-20-KR-141500.md` | https://shine88pc.github.io/chanceblog/posts/2026/10/20/korean-food-date-labels/ | 예 |

---

# 2. 이야기 묶음 지도

| 묶음 | 이야기 | 무엇이 이어 주나 | 허브 후보 |
|---|---|---|---|
| 우주·과학 | S15 허블, S16 보이저, S02 MMX(영문), S05 우주날씨, (S12 멘토링) | 같은 NASA·JAXA 임무 이야기, 저궤도 위성의 대기 저항(우주날씨 G3 ↔ 허블 고도), ‘계획과 실행을 구분해 읽기’ | **S15 허블** |
| Pew 미디어 3부작 | S07 58%, S08 데이터센터 광고, S09 신뢰 | 같은 조사기관·같은 시리즈(얼마나 쓰나 → 무엇이 흐르나 → 얼마나 믿나) | **S07 58%** |
| EU 기후·환경 | S17 기후 회복력, S14 JRC 대시보드, S13 자연 크레딧 | JRC 자료가 기후 회복력 정책의 근거(원문에 명시), 측정 표준화·재원 조달의 공통 쟁점 | **S17** |
| EU 에너지 | S10 CEF, S11 정유 고위급 대화 | 유럽 에너지 안보 — 인프라 투자 수요와 정유업계 대화 | (둘이 서로 하나씩) |
| 제조 AI | S03 원프레딕트, S04 KIMM, (S01 AI 쇼핑 — 약), (S20 LDT — 조건부) | 같은 도입 점검 질문, ‘디지털 트윈’ 접점 | S03↔S04 |
| 고립 | S06 식품 날짜, S19 캐나다 청년 고용 | 사이트에 같은 분야 글이 없음 — 후보 없음 | — |
| 약한 연결 | S18 프론텍스(S17 하나), S01(S03 하나) | 같은 날 나온 EU 집행위 제안 등 느슨한 접점 | — |

---

# 3. 글별 후보 (공개 38편)

한 글마다: 이 글의 주소 → 후보 1~3개(연결 강도·이유·양방향 여부·주소) → **본문 자리**(어느 문장 뒤에 거는지, 앞 소제목 포함) → 덧붙일 문장 예(링크 위치는 [대괄호]) . ‘조건’이 붙은 후보는 그 이야기를 공개로 유지할 때만 쓴다.

## S01. AI 쇼핑은 어디까지 왔나 (OpenAI 발표 정리)

### S01 · 한글 — AI 쇼핑은 어디까지 왔나: 상품 탐색은 대화창으로, 결제는 판매자 중심으로

- 이 글 주소: https://shine88pc.github.io/chanceblog/posts/2026/10/18/AI/ (`2026-10-18-AI.md`)
- 후보가 1개뿐이다 — 2~3개를 채우려고 약한 글을 끌어오지 않았다.
- **후보 1 — S03 한글**: AI 네이티브 팩토리: 원프레딕트가 제시한 공장 운영 비전, 검증 과제는? · 연결 강도 **약** · 양방향 가능(상대 글에도 이 글이 후보로 있음)
  - 주소: https://shine88pc.github.io/chanceblog/posts/2026/10/19/KR-103939/
  - 연결 이유: ‘AI 가 권고한 일을 누가 승인·책임지나’라는 같은 점검 질문(쇼핑 ↔ 공장). 억지가 될 수 있어 편집자 판단
  - 본문 자리: ‘소비자와 판매자가 확인할 것’ 절, 「자체 체크아웃을 유지한다면 상품 데이터와 연결 방식이 핵심이고, 승인된 인앱 체크아웃을 도입한다면 주문 승인, 결제 책임, 재고 동기화, 반품·고객 지원까지 점검해야 합니다.」 문장 뒤
  - 덧붙일 문장(예): AI 의 권고를 누가 승인하고 책임지는지 묻는 같은 질문을 공장 도입 사례에서 다룬 [AI 네이티브 팩토리 구상과 검증 과제를 다룬 글](https://shine88pc.github.io/chanceblog/posts/2026/10/19/KR-103939/)도 함께 볼 만합니다.
  - 링크 텍스트: AI 네이티브 팩토리 구상과 검증 과제를 다룬 글

## S02. 일본 MMX 탐사선, 포보스로 출발 (시료 10g이 알려 줄 것)

### S02 · 영문 — Japan’s MMX Mission Is on Its Way to Phobos: What the 10-Gram Sample Could Tell Us

- 이 글 주소: https://shine88pc.github.io/chanceblog/posts/2026/10/18/EN-233513/ (`EN - Space & Robotics/2026-10-18-EN-233513.md`)
- **후보 1 — S16 영문**: A 175-Year Planetary Alignment and Voyager’s Path: What Deep-Space Milestones Mean for Everyday Observers · 연결 강도 **중** · 양방향 가능(상대 글에도 이 글이 후보로 있음)
  - 주소: https://shine88pc.github.io/chanceblog/posts/2026/11/02/EN-100912/
  - 연결 이유: 심우주 임무의 경로 설계 — 중력 도움을 이용한 보이저 ‘그랜드 투어’와 현재 진행 중인 MMX 의 대비
  - 본문 자리: 「JAXA’s mission website describes the flight and its planned five-year journey.」 문장 뒤
  - 덧붙일 문장(예): For an earlier example of how mission planners shaped a deep-space route, see [how a 1977 planetary alignment and gravity assists shaped Voyager’s Grand Tour](https://shine88pc.github.io/chanceblog/posts/2026/11/02/EN-100912/).
  - 링크 텍스트: how a 1977 planetary alignment and gravity assists shaped Voyager’s Grand Tour
- **후보 2 — S15 영문**: Commercial In-Space Servicing for Hubble: What an RFI Reveals About Science Infrastructure · 연결 강도 **중** · 양방향 가능(상대 글에도 이 글이 후보로 있음)
  - 주소: https://shine88pc.github.io/chanceblog/posts/2026/11/02/EN-081916/
  - 연결 이유: 계획(RFI)과 실행(발사)의 구분 — 같은 ‘계획은 계획으로 보도한다’ 원칙
  - 본문 자리: ‘What the sample can—and cannot—tell us’ 절, 「Schedules can change, so planned outcomes should be reported as plans until the mission confirms them.」 문장 뒤
  - 덧붙일 문장(예): A different stage of space planning, an exploratory request rather than a launch, is covered in [NASA’s request for information on commercial servicing for the Hubble Space Telescope](https://shine88pc.github.io/chanceblog/posts/2026/11/02/EN-081916/).
  - 링크 텍스트: NASA’s request for information on commercial servicing for the Hubble Space Telescope

## S03. AI 네이티브 팩토리 — 원프레딕트의 공장 운영 구상

### S03 · 한글 — AI 네이티브 팩토리: 원프레딕트가 제시한 공장 운영 비전, 검증 과제는?

- 이 글 주소: https://shine88pc.github.io/chanceblog/posts/2026/10/19/KR-103939/ (`KR - 테크 인사이트/2026-10-19-KR-103939.md`)
- **후보 1 — S04 한글**: 기계연 동남권 오픈랩: 제조 AI를 현장에 연결하는 연구 공개 · 연결 강도 **강** · 양방향 가능(상대 글에도 이 글이 후보로 있음)
  - 주소: https://shine88pc.github.io/chanceblog/posts/2026/10/19/KR-195755/
  - 연결 이유: 같은 제조 AI 도입 점검 — 행사에서 실제로 공개된 정보가 무엇이었는지의 사례
  - 본문 자리: ‘실제 도입을 검토할 때 물어볼 것’ 절, 「이런 항목을 평가하려면 시험 기간, 적용 설비, 기존 기준선, 유지비와 결과가 공개돼야 합니다.」 문장 뒤
  - 덧붙일 문장(예): 실제 행사에서 어떤 정보가 공개됐고 무엇이 비어 있었는지는 [한국기계연구원 오픈랩에서 확인된 내용과 확인되지 않은 성과를 나눠 본 글](https://shine88pc.github.io/chanceblog/posts/2026/10/19/KR-195755/)에서 볼 수 있습니다.
  - 링크 텍스트: 한국기계연구원 오픈랩에서 확인된 내용과 확인되지 않은 성과를 나눠 본 글
- **후보 2 — S01 한글**: AI 쇼핑은 어디까지 왔나: 상품 탐색은 대화창으로, 결제는 판매자 중심으로 · 연결 강도 **약** · 양방향 가능(상대 글에도 이 글이 후보로 있음)
  - 주소: https://shine88pc.github.io/chanceblog/posts/2026/10/18/AI/
  - 연결 이유: ‘AI 가 권고한 일을 누가 승인·책임지나’라는 같은 점검 질문(쇼핑 ↔ 공장)
  - 본문 자리: ‘실제 도입을 검토할 때 물어볼 것’ 절, 「다음으로 데이터가 설비마다 다른 형식과 주기로 들어오는지, 기존 생산관리·제어 시스템을 연결하는 데 드는 시간과 비용은 얼마인지, AI가 권고한 조치를 누가 승인하는지 확인해야 합니다.」 문장 뒤
  - 덧붙일 문장(예): AI 가 한 일의 승인과 책임을 따지는 같은 질문은 쇼핑 분야의 [AI 쇼핑에서 상품 탐색과 결제 책임이 어디에 놓이는지 다룬 글](https://shine88pc.github.io/chanceblog/posts/2026/10/18/AI/)에서도 나옵니다.
  - 링크 텍스트: AI 쇼핑에서 상품 탐색과 결제 책임이 어디에 놓이는지 다룬 글

### S03 · 영문 — AI-Native Factory: OnePredict’s Operating Vision and the Evidence It Still Needs

- 이 글 주소: https://shine88pc.github.io/chanceblog/posts/2026/10/19/EN-103939/ (`EN - Tech Insights/2026-10-19-EN-103939.md`)
- 후보가 1개뿐이다 — 2~3개를 채우려고 약한 글을 끌어오지 않았다.
- **후보 1 — S04 영문**: KIMM’s Southeast Open Lab: Connecting Manufacturing AI Research with Industry · 연결 강도 **강** · 양방향 가능(상대 글에도 이 글이 후보로 있음)
  - 주소: https://shine88pc.github.io/chanceblog/posts/2026/10/19/EN-195755/
  - 연결 이유: 같은 제조 AI 도입 점검 — 행사에서 실제로 공개된 정보가 무엇이었는지의 사례
  - 본문 자리: ‘A practical way to assess a pilot’ 절, 「…evaluation publishes the site and equipment covered, trial period, baseline, measurement method, integration costs, and ongoing support needs.」 문장 뒤
  - 덧붙일 문장(예): What was and wasn’t disclosed at one manufacturing-AI event is described in [KIMM’s Southeast Open Lab and what the event did and did not establish](https://shine88pc.github.io/chanceblog/posts/2026/10/19/EN-195755/).
  - 링크 텍스트: KIMM’s Southeast Open Lab and what the event did and did not establish

## S04. 한국기계연구원 동남권 OPEN LAB — 제조 AI를 현장과 잇는 행사

### S04 · 한글 — 기계연 동남권 오픈랩: 제조 AI를 현장에 연결하는 연구 공개

- 이 글 주소: https://shine88pc.github.io/chanceblog/posts/2026/10/19/KR-195755/ (`산업 AI/2026-10-19-KR-195755.md`)
- **후보 1 — S03 한글**: AI 네이티브 팩토리: 원프레딕트가 제시한 공장 운영 비전, 검증 과제는? · 연결 강도 **강** · 양방향 가능(상대 글에도 이 글이 후보로 있음)
  - 주소: https://shine88pc.github.io/chanceblog/posts/2026/10/19/KR-103939/
  - 연결 이유: 같은 제조 AI 도입 점검 — 회사가 제시한 구상과 검증 과제의 사례
  - 본문 자리: ‘기업이 도입 가능성을 따질 때’ 절, 「기술 소개와 현장 성과는 다른 증거입니다.」 문장 뒤
  - 덧붙일 문장(예): 회사가 제시한 구상과 실제 성과의 차이는 [원프레딕트의 AI 네이티브 팩토리 구상과 검증 과제를 다룬 글](https://shine88pc.github.io/chanceblog/posts/2026/10/19/KR-103939/)에서도 다뤘습니다.
  - 링크 텍스트: 원프레딕트의 AI 네이티브 팩토리 구상과 검증 과제를 다룬 글
- **후보 2 — S20 한글**: 바르셀로나로 향하는 LDT CiTiVERSE EDIC: 인간 중심 AI와 도시 디지털 트윈의 행방 · 연결 강도 **약** · 양방향 가능(상대 글에도 이 글이 후보로 있음) · **조건: S20(LDT 글)을 공개로 유지할 때만**
  - 주소: https://shine88pc.github.io/chanceblog/posts/2026/11/01/KR-163702/
  - 연결 이유: ‘디지털 트윈’ 접점 — 제조 현장과 도시 행정의 적용 비교
  - 본문 자리: ‘발표된 내용과 기업 지원’ 절, 「행사에서는 디지털 트윈, 디지털 전환(DX), 인공지능 전환(AX)의 산업 적용 사례와 연구원 성과가 소개됐습니다.」 문장 뒤
  - 덧붙일 문장(예): 디지털 트윈이 도시 행정에 쓰이는 방식은 [유럽 도시 디지털 트윈과 CiTiVERSE 의 박람회 참가를 다룬 글](https://shine88pc.github.io/chanceblog/posts/2026/11/01/KR-163702/)에서 볼 수 있습니다.
  - 링크 텍스트: 유럽 도시 디지털 트윈과 CiTiVERSE 의 박람회 참가를 다룬 글

### S04 · 영문 — KIMM’s Southeast Open Lab: Connecting Manufacturing AI Research with Industry

- 이 글 주소: https://shine88pc.github.io/chanceblog/posts/2026/10/19/EN-195755/ (`Industrial AI/2026-10-19-EN-195755.md`)
- **후보 1 — S03 영문**: AI-Native Factory: OnePredict’s Operating Vision and the Evidence It Still Needs · 연결 강도 **강** · 양방향 가능(상대 글에도 이 글이 후보로 있음)
  - 주소: https://shine88pc.github.io/chanceblog/posts/2026/10/19/EN-103939/
  - 연결 이유: 같은 제조 AI 도입 점검 — 회사가 제시한 구상과 검증 과제의 사례
  - 본문 자리: ‘How a company can evaluate the next step’ 절, 「For a manufacturer, a useful pilot begins with a defined production problem and a baseline.」 문장 뒤
  - 덧붙일 문장(예): A company-side example of the same questions is covered in [OnePredict’s AI-native factory vision and the evidence it still needs](https://shine88pc.github.io/chanceblog/posts/2026/10/19/EN-103939/).
  - 링크 텍스트: OnePredict’s AI-native factory vision and the evidence it still needs
- **후보 2 — S20 영문**: LDT CiTiVERSE EDIC at Smart City Expo 2026: Human-Centric AI and the Urban Digital Twin · 연결 강도 **약** · 양방향 가능(상대 글에도 이 글이 후보로 있음) · **조건: S20(LDT 글)을 공개로 유지할 때만**
  - 주소: https://shine88pc.github.io/chanceblog/posts/2026/11/01/EN-163702/
  - 연결 이유: ‘디지털 트윈’ 접점 — 제조 현장과 도시 행정의 적용 비교
  - 본문 자리: ‘What participants were invited to examine’ 절, 「The program covered industrial applications of digital twins, digital transformation (DX), and AI transformation (AX).」 문장 뒤
  - 덧붙일 문장(예): How digital twins are used in city governance is covered in [the EU local digital twins consortium at Smart City Expo 2026](https://shine88pc.github.io/chanceblog/posts/2026/11/01/EN-163702/).
  - 링크 텍스트: the EU local digital twins consortium at Smart City Expo 2026

## S05. 우주날씨 경보 G1~G5, 생활에는 어떤 뜻일까

### S05 · 한글 — 우주날씨 경보 G1~G5, 우리 생활에는 어떤 뜻일까?

- 이 글 주소: https://shine88pc.github.io/chanceblog/posts/2026/10/20/KR-125000/ (`과학 환경/2026-10-20-KR-125000.md`)
- 후보가 1개뿐이다 — 2~3개를 채우려고 약한 글을 끌어오지 않았다.
- **후보 1 — S15 한글**: 허블 우주망원경과 민간 우주 궤도 서비스: 정보요청서가 던진 과학 자산의 지속성 질문 · 연결 강도 **중** · 양방향 가능(상대 글에도 이 글이 후보로 있음)
  - 주소: https://shine88pc.github.io/chanceblog/posts/2026/11/02/KR-081916/
  - 연결 이유: 저궤도 위성의 대기 저항 증가(G3 영향)와 허블 같은 저궤도 관측 자산의 수명 문제가 직접 이어짐
  - 본문 자리: ‘숫자는 결과가 아니라 영향 가능성입니다’ 절, 「G1에서는 약한 전력망 변동이나 위성 운용 영향이 가능하고, G3부터는 일부 보호 장치의 오경보, 간헐적인 위성 항법 문제, 저궤도 위성의 대기 저항 증가 등이 나타날 수 있다고 NOAA는 설명합니다.」 문장 뒤
  - 덧붙일 문장(예): 저궤도 관측 자산의 수명을 어떻게 이어 갈지는 [허블 우주망원경의 운영과 민간 궤도 서비스를 묻는 NASA 정보요청서를 다룬 글](https://shine88pc.github.io/chanceblog/posts/2026/11/02/KR-081916/)에서 이어서 볼 수 있습니다.
  - 링크 텍스트: 허블 우주망원경의 운영과 민간 궤도 서비스를 묻는 NASA 정보요청서를 다룬 글

### S05 · 영문 — What Does a G1–G5 Space Weather Alert Mean for Everyday Life?

- 이 글 주소: https://shine88pc.github.io/chanceblog/posts/2026/10/20/EN-125000/ (`EN - Science & Environment/2026-10-20-EN-125000.md`)
- 후보가 1개뿐이다 — 2~3개를 채우려고 약한 글을 끌어오지 않았다.
- **후보 1 — S15 영문**: Commercial In-Space Servicing for Hubble: What an RFI Reveals About Science Infrastructure · 연결 강도 **중** · 양방향 가능(상대 글에도 이 글이 후보로 있음)
  - 주소: https://shine88pc.github.io/chanceblog/posts/2026/11/02/EN-081916/
  - 연결 이유: G3 영향(저궤도 위성 대기 저항 증가)과 허블 같은 저궤도 관측 자산의 수명 문제가 직접 이어짐
  - 본문 자리: ‘A scale lists possibilities, not guaranteed outcomes’ 절, 「…corrections, false alarms in some protection systems, intermittent satellite-navigation problems, and increased drag on low-Earth-orbit satellites.」 문장 뒤
  - 덧붙일 문장(예): How long a low-orbit telescope can keep operating is the subject of [NASA’s request for information on commercial servicing for the Hubble Space Telescope](https://shine88pc.github.io/chanceblog/posts/2026/11/02/EN-081916/).
  - 링크 텍스트: NASA’s request for information on commercial servicing for the Hubble Space Telescope

## S06. 유통기한과 소비기한, 장 볼 때 무엇을 확인할까

### S06 · 한글 — 유통기한과 소비기한, 장 볼 때 무엇을 확인해야 할까?

- 이 글 주소: https://shine88pc.github.io/chanceblog/posts/2026/10/20/korean-food-date-labels/ (`일상·마음/2026-10-20-KR-141500.md`)
- **후보 없음** — 사이트에 이어 읽을 만한 같은 분야의 글이 없다(억지 링크 금지). 글 아래의 ‘다른 언어 버전’ 표시만 있으면 충분하다.

### S06 · 영문 — Food Date Labels in South Korea: What ‘Sell-By’ and ‘Use-By’ Mean

- 이 글 주소: https://shine88pc.github.io/chanceblog/posts/2026/10/20/south-korea-food-date-labels/ (`Everyday Life/2026-10-20-EN-141500.md`)
- **후보 없음** — 사이트에 이어 읽을 만한 같은 분야의 글이 없다(억지 링크 금지). 글 아래의 ‘다른 언어 버전’ 표시만 있으면 충분하다.

## S07. 미국 성인 58% ‘소셜 미디어는 뉴스를 따라가는 중요한 방법’ (Pew)

### S07 · 한글 — 미국 성인 58% "소셜 미디어가 주요 뉴스 정보원"… 퓨 리서치 조사가 보여준 미디어 수용의 전환

- 이 글 주소: https://shine88pc.github.io/chanceblog/posts/2026/10/26/KR-182804/ (`문화·미디어/2026-10-26-KR-182804.md`)
- **후보 1 — S09 한글**: 미국인의 저널리즘 신뢰 반등: 전국·지역 뉴스 신뢰는 상승, 소셜 미디어는 제자리 · 연결 강도 **강** · 양방향 가능(상대 글에도 이 글이 후보로 있음)
  - 주소: https://shine88pc.github.io/chanceblog/posts/2026/11/03/KR-155742/
  - 연결 이유: 같은 Pew 조사 시리즈 — ‘얼마나 쓰나(58%)’ 다음 질문은 ‘얼마나 믿나’
  - 본문 자리: ‘플랫폼 시대의 뉴스 리터러시’ 절, 「플랫폼 기업은 알고리즘의 투명성을 높이고 허위 정보 유통을 막기 위한 책임을 다해야 하며, 사용자 역시 정보를 접할 때 원 출처와 검증 여부를 확인하는 디지털 리터러시를 갖출 필요가 있습니다.」 문장 뒤
  - 덧붙일 문장(예): 얼마나 믿는지는 또 다른 문제입니다. 미국인의 뉴스 기관·소셜 미디어 신뢰는 [미국인의 뉴스 기관과 소셜 미디어 정보 신뢰를 다룬 Pew 조사 글](https://shine88pc.github.io/chanceblog/posts/2026/11/03/KR-155742/)에서 볼 수 있습니다.
  - 링크 텍스트: 미국인의 뉴스 기관과 소셜 미디어 정보 신뢰를 다룬 Pew 조사 글
- **후보 2 — S08 한글**: 소셜 미디어 정치 광고 속 데이터센터: 반대 57% 대 찬성 3%가 뜻하는 것 · 연결 강도 **강** · 양방향 가능(상대 글에도 이 글이 후보로 있음)
  - 주소: https://shine88pc.github.io/chanceblog/posts/2026/10/30/KR-224001/
  - 연결 이유: 같은 Pew 분석 — 피드 안에서 소비되는 정치 광고의 사례
  - 본문 자리: ‘플랫폼 중심으로 재편된 정보 소비’ 절, 「독자들은 특정 언론사의 기획이나 편집을 따라가기보다, 알고리즘이 추천하거나 지인들이 공유하는 콘텐츠 피드 속에서 시사 정보를 자연스럽게 접하고 있습니다.」 문장 뒤
  - 덧붙일 문장(예): 그 피드 속 정치 광고가 데이터센터를 어떻게 다루는지는 [소셜 미디어 정치 광고에서 데이터센터가 어떻게 다뤄지는지 분석한 Pew 글](https://shine88pc.github.io/chanceblog/posts/2026/10/30/KR-224001/)에서 확인할 수 있습니다.
  - 링크 텍스트: 소셜 미디어 정치 광고에서 데이터센터가 어떻게 다뤄지는지 분석한 Pew 글

### S07 · 영문 — 58% of U.S. Adults Call Social Media an Important News Source: Pew Research Highlights a Shifting Media Landscape

- 이 글 주소: https://shine88pc.github.io/chanceblog/posts/2026/10/26/EN-182804/ (`Culture & Media/2026-10-26-EN-182804.md`)
- **후보 1 — S09 영문**: Trust in News Organizations Rises Among Americans, While Social Media Trust Stagnates · 연결 강도 **강** · 양방향 가능(상대 글에도 이 글이 후보로 있음)
  - 주소: https://shine88pc.github.io/chanceblog/posts/2026/11/03/EN-155742/
  - 연결 이유: 같은 Pew 시리즈 — ‘얼마나 쓰나’ 다음 질문은 ‘얼마나 믿나’
  - 본문 자리: ‘Navigating the Algorithmic Information Ecosystem’ 절, 「…transparency and robust content moderation, while readers must cultivate digital literacy skills to evaluate sources and trace original reporting.」 문장 뒤
  - 덧붙일 문장(예): How much Americans trust what they find there is a separate question; see [Pew’s findings on Americans’ trust in news organizations and social media](https://shine88pc.github.io/chanceblog/posts/2026/11/03/EN-155742/).
  - 링크 텍스트: Pew’s findings on Americans’ trust in news organizations and social media
- **후보 2 — S08 영문**: Data Centers in Social Media Political Ads: 57% Opposed vs. 3% Supportive · 연결 강도 **강** · 양방향 가능(상대 글에도 이 글이 후보로 있음)
  - 주소: https://shine88pc.github.io/chanceblog/posts/2026/10/30/EN-224001/
  - 연결 이유: 같은 Pew 분석 — 피드 안에서 소비되는 정치 광고의 사례
  - 본문 자리: ‘The Shift to Platform-Centric News Discovery’ 절, 「Users increasingly encounter reporting alongside personal updates, creator videos, and sponsored posts curated by recommendation algorithms.」 문장 뒤
  - 덧붙일 문장(예): How political ads inside those feeds treat one local issue, data centers, is analyzed in [Pew’s analysis of data centers in Facebook and Instagram political ads](https://shine88pc.github.io/chanceblog/posts/2026/10/30/EN-224001/).
  - 링크 텍스트: Pew’s analysis of data centers in Facebook and Instagram political ads

## S08. 소셜 미디어 정치 광고 속 데이터센터: 반대 57% 대 찬성 3% (Pew)

### S08 · 한글 — 소셜 미디어 정치 광고 속 데이터센터: 반대 57% 대 찬성 3%가 뜻하는 것

- 이 글 주소: https://shine88pc.github.io/chanceblog/posts/2026/10/30/KR-224001/ (`문화·미디어/2026-10-30-KR-224001.md`)
- **후보 1 — S07 한글**: 미국 성인 58% "소셜 미디어가 주요 뉴스 정보원"… 퓨 리서치 조사가 보여준 미디어 수용의 전환 · 연결 강도 **강** · 양방향 가능(상대 글에도 이 글이 후보로 있음)
  - 주소: https://shine88pc.github.io/chanceblog/posts/2026/10/26/KR-182804/
  - 연결 이유: 정치 광고가 놓이는 곳(소셜 미디어 피드)이 얼마나 중요한 뉴스 통로인지에 대한 조사
  - 본문 자리: ‘플랫폼 미디어에서 인프라는 어떻게 소비되는가’ 절, 「이는 소셜 미디어라는 미디어 매체가 물리적 현실의 갈등을 어떻게 매개하는지 보여줍니다.」 문장 뒤
  - 덧붙일 문장(예): 소셜 미디어가 미국 성인에게 뉴스를 따라가는 중요한 방법이 됐다는 점은 [미국 성인이 소셜 미디어를 뉴스 파악의 중요한 방법으로 꼽는 비율을 다룬 Pew 글](https://shine88pc.github.io/chanceblog/posts/2026/10/26/KR-182804/)에서 다뤘습니다.
  - 링크 텍스트: 미국 성인이 소셜 미디어를 뉴스 파악의 중요한 방법으로 꼽는 비율을 다룬 Pew 글
- **후보 2 — S09 한글**: 미국인의 저널리즘 신뢰 반등: 전국·지역 뉴스 신뢰는 상승, 소셜 미디어는 제자리 · 연결 강도 **중** · 양방향 가능(상대 글에도 이 글이 후보로 있음)
  - 주소: https://shine88pc.github.io/chanceblog/posts/2026/11/03/KR-155742/
  - 연결 이유: 소셜 미디어 정보에 대한 신뢰 수준 — 광고 메시지가 놓인 환경의 이해
  - 본문 자리: ‘지지 메시지의 부재와 미디어 여론의 간극’ 절, 「이러한 불균형은 소셜 미디어를 통해 유통되는 정치 담론이 산업 인프라를 다루는 방식에 뚜렷한 편향을 만들어내고 있습니다.」 문장 뒤
  - 덧붙일 문장(예): 소셜 미디어 정보를 미국인이 얼마나 믿는지는 [미국인의 뉴스 기관과 소셜 미디어 정보 신뢰를 다룬 Pew 조사 글](https://shine88pc.github.io/chanceblog/posts/2026/11/03/KR-155742/)에서 볼 수 있습니다.
  - 링크 텍스트: 미국인의 뉴스 기관과 소셜 미디어 정보 신뢰를 다룬 Pew 조사 글

### S08 · 영문 — Data Centers in Social Media Political Ads: 57% Opposed vs. 3% Supportive

- 이 글 주소: https://shine88pc.github.io/chanceblog/posts/2026/10/30/EN-224001/ (`Culture & Media/2026-10-30-EN-224001.md`)
- **후보 1 — S07 영문**: 58% of U.S. Adults Call Social Media an Important News Source: Pew Research Highlights a Shifting Media Landscape · 연결 강도 **강** · 양방향 가능(상대 글에도 이 글이 후보로 있음)
  - 주소: https://shine88pc.github.io/chanceblog/posts/2026/10/26/EN-182804/
  - 연결 이유: 정치 광고가 놓이는 곳(소셜 미디어 피드)이 얼마나 중요한 뉴스 통로인지에 대한 조사
  - 본문 자리: ‘How Physical Infrastructure Enters the Digital Ad Stream’ 절, 「This shift illustrates how social media platforms mediate conflicts between digital progress and physical realities.」 문장 뒤
  - 덧붙일 문장(예): How central social media has become as a way to follow the news is covered in [Pew’s finding that most U.S. adults call social media an important way to keep up with the news](https://shine88pc.github.io/chanceblog/posts/2026/10/26/EN-182804/).
  - 링크 텍스트: Pew’s finding that most U.S. adults call social media an important way to keep up with the news
- **후보 2 — S09 영문**: Trust in News Organizations Rises Among Americans, While Social Media Trust Stagnates · 연결 강도 **중** · 양방향 가능(상대 글에도 이 글이 후보로 있음)
  - 주소: https://shine88pc.github.io/chanceblog/posts/2026/11/03/EN-155742/
  - 연결 이유: 소셜 미디어 정보에 대한 신뢰 수준 — 광고 메시지가 놓인 환경의 이해
  - 본문 자리: ‘The Asymmetry in Political Storytelling’ 절, 「This dynamic produces a sharp narrative imbalance on platforms where user attention is already fragmented.」 문장 뒤
  - 덧붙일 문장(예): How much Americans trust information from social media is covered in [Pew’s findings on Americans’ trust in news organizations and social media](https://shine88pc.github.io/chanceblog/posts/2026/11/03/EN-155742/).
  - 링크 텍스트: Pew’s findings on Americans’ trust in news organizations and social media

## S09. 미국인의 뉴스 신뢰 반등: 전국·지역 뉴스는 상승, 소셜 미디어는 제자리 (Pew)

### S09 · 한글 — 미국인의 저널리즘 신뢰 반등: 전국·지역 뉴스 신뢰는 상승, 소셜 미디어는 제자리

- 이 글 주소: https://shine88pc.github.io/chanceblog/posts/2026/11/03/KR-155742/ (`문화·미디어/2026-11-03-KR-155742.md`)
- **후보 1 — S07 한글**: 미국 성인 58% "소셜 미디어가 주요 뉴스 정보원"… 퓨 리서치 조사가 보여준 미디어 수용의 전환 · 연결 강도 **강** · 양방향 가능(상대 글에도 이 글이 후보로 있음)
  - 주소: https://shine88pc.github.io/chanceblog/posts/2026/10/26/KR-182804/
  - 연결 이유: 신뢰와 별개로 소셜 미디어가 뉴스 통로로 얼마나 쓰이는지를 보여 주는 같은 Pew 시리즈
  - 본문 자리: ‘조사 결과가 보여주는 미디어 신뢰 지점’ 절, 「이는 소셜 미디어가 매일 접하는 정보의 주요 창구로 이용되더라도, 정보의 사실성과 정확성 측면에서 소비자들이 느끼는 신뢰의 가중치는 전통적인 언론 기관에 더 기울어져 있음을 보여줍니다.」 문장 뒤
  - 덧붙일 문장(예): 소셜 미디어를 뉴스 통로로 얼마나 쓰는지는 [미국 성인이 소셜 미디어를 뉴스 파악의 중요한 방법으로 꼽는 비율을 다룬 Pew 글](https://shine88pc.github.io/chanceblog/posts/2026/10/26/KR-182804/)에서 확인할 수 있습니다.
  - 링크 텍스트: 미국 성인이 소셜 미디어를 뉴스 파악의 중요한 방법으로 꼽는 비율을 다룬 Pew 글
- **후보 2 — S08 한글**: 소셜 미디어 정치 광고 속 데이터센터: 반대 57% 대 찬성 3%가 뜻하는 것 · 연결 강도 **중** · 양방향 가능(상대 글에도 이 글이 후보로 있음)
  - 주소: https://shine88pc.github.io/chanceblog/posts/2026/10/30/KR-224001/
  - 연결 이유: 소셜 피드 안에서 유통되는 정치 메시지의 한 사례
  - 본문 자리: ‘신뢰 지형의 변화와 사회적 맥락’ 절, 「일반적으로 소셜 미디어 플랫폼은 빠른 전달력과 개인화된 추천 알고리즘을 장점으로 삼지만, 검증되지 않은 소문이나 오염된 정보가 쉽게 확산될 수 있는 구조적 한계를 지닙니다.」 문장 뒤
  - 덧붙일 문장(예): 소셜 피드 안에서 정치 메시지가 어떻게 유통되는지의 한 사례는 [소셜 미디어 정치 광고에서 데이터센터가 어떻게 다뤄지는지 분석한 Pew 글](https://shine88pc.github.io/chanceblog/posts/2026/10/30/KR-224001/)에서 볼 수 있습니다.
  - 링크 텍스트: 소셜 미디어 정치 광고에서 데이터센터가 어떻게 다뤄지는지 분석한 Pew 글

### S09 · 영문 — Trust in News Organizations Rises Among Americans, While Social Media Trust Stagnates

- 이 글 주소: https://shine88pc.github.io/chanceblog/posts/2026/11/03/EN-155742/ (`Culture & Media/2026-11-03-EN-155742.md`)
- **후보 1 — S07 영문**: 58% of U.S. Adults Call Social Media an Important News Source: Pew Research Highlights a Shifting Media Landscape · 연결 강도 **강** · 양방향 가능(상대 글에도 이 글이 후보로 있음)
  - 주소: https://shine88pc.github.io/chanceblog/posts/2026/10/26/EN-182804/
  - 연결 이유: 신뢰와 별개로 소셜 미디어가 뉴스 통로로 얼마나 쓰이는지를 보여 주는 같은 Pew 시리즈
  - 본문 자리: 「…national and local—has risen across political parties and age groups, while trust in information from social media remains virtually unchanged.」 문장 뒤
  - 덧붙일 문장(예): How widely social media is used to follow the news is covered in [Pew’s finding that most U.S. adults call social media an important way to keep up with the news](https://shine88pc.github.io/chanceblog/posts/2026/10/26/EN-182804/).
  - 링크 텍스트: Pew’s finding that most U.S. adults call social media an important way to keep up with the news
- **후보 2 — S08 영문**: Data Centers in Social Media Political Ads: 57% Opposed vs. 3% Supportive · 연결 강도 **중** · 양방향 가능(상대 글에도 이 글이 후보로 있음)
  - 주소: https://shine88pc.github.io/chanceblog/posts/2026/10/30/EN-224001/
  - 연결 이유: 소셜 피드 안에서 유통되는 정치 메시지의 한 사례
  - 본문 자리: ‘Contextualizing Media Trust and Civic Life’ 절, 「…media platforms offer speed and algorithmically customized content feeds, but they also expose users to unverified claims and unreliable sources.」 문장 뒤
  - 덧붙일 문장(예): One example of political messaging inside social feeds is analyzed in [Pew’s analysis of data centers in Facebook and Instagram political ads](https://shine88pc.github.io/chanceblog/posts/2026/10/30/EN-224001/).
  - 링크 텍스트: Pew’s analysis of data centers in Facebook and Instagram political ads

## S10. 유럽 국경 간 에너지망에 몰린 자금 수요: CEF 에너지 공모 67건·28.8억 유로

### S10 · 한글 — 유럽 국경 간 에너지망 구축에 몰린 자금 수요: CEF 에너지 공모에 28.8억 유로 신청

- 이 글 주소: https://shine88pc.github.io/chanceblog/posts/2026/10/27/KR-093056/ (`경제·일/2026-10-27-KR-093056.md`)
- 후보가 1개뿐이다 — 2~3개를 채우려고 약한 글을 끌어오지 않았다.
- **후보 1 — S11 한글**: 에너지 안보와 방위 준비태세: 유럽 정유업계와 집행위의 고위급 대화가 던진 질문 · 연결 강도 **강** · 양방향 가능(상대 글에도 이 글이 후보로 있음)
  - 주소: https://shine88pc.github.io/chanceblog/posts/2026/10/29/KR-101652/
  - 연결 이유: 유럽의 에너지 안보 논의 — 인프라 투자 수요(CEF)와 정유업계 대화가 같은 정책 흐름
  - 본문 자리: ‘인프라 병목과 에너지 전환이 맞물린 산업적 배경’ 절, 「재생에너지 간헐성을 보완하고 공급 충격을 분산하기 위해서는 개별 국가 단위의 전력망을 넘어 대륙 단위로 연결된 초고압 송전망과 저장 설비, 수소 및 관련 가스망이 필수적입니다.」 문장 뒤
  - 덧붙일 문장(예): 에너지 인프라 투자가 안보 논의와 만나는 또 다른 장면은 [집행위가 정유업계와 에너지 안보·방위 준비태세를 논의하기 시작한 소식을 다룬 글](https://shine88pc.github.io/chanceblog/posts/2026/10/29/KR-101652/)에서 볼 수 있습니다.
  - 링크 텍스트: 집행위가 정유업계와 에너지 안보·방위 준비태세를 논의하기 시작한 소식을 다룬 글

### S10 · 영문 — Demand Surges for Cross-Border Energy Grids: 67 Projects Seek €2.88 Billion in EU Co-Funding

- 이 글 주소: https://shine88pc.github.io/chanceblog/posts/2026/10/27/EN-093056/ (`Economy & Work/2026-10-27-EN-093056.md`)
- 후보가 1개뿐이다 — 2~3개를 채우려고 약한 글을 끌어오지 않았다.
- **후보 1 — S11 영문**: Energy Security and Defence Readiness: Inside the EU's High-Level Dialogue with Refining · 연결 강도 **강** · 양방향 가능(상대 글에도 이 글이 후보로 있음)
  - 주소: https://shine88pc.github.io/chanceblog/posts/2026/10/29/EN-101652/
  - 연결 이유: 유럽의 에너지 안보 논의 — 인프라 투자 수요(CEF)와 정유업계 대화가 같은 정책 흐름
  - 본문 자리: ‘The Industrial Logic Behind the Influx of Applications’ 절, 「…requires high-voltage interconnectors, expanded storage facilities, and resilient transport corridors capable of moving energy across borders.」 문장 뒤
  - 덧붙일 문장(예): Energy infrastructure also appears in Europe’s security debate; see [the European Commission’s first high-level dialogue with the oil refining industry](https://shine88pc.github.io/chanceblog/posts/2026/10/29/EN-101652/).
  - 링크 텍스트: the European Commission’s first high-level dialogue with the oil refining industry

## S11. 에너지 안보와 방위 준비태세: 집행위와 유럽 정유업계의 첫 고위급 대화

### S11 · 한글 — 에너지 안보와 방위 준비태세: 유럽 정유업계와 집행위의 고위급 대화가 던진 질문

- 이 글 주소: https://shine88pc.github.io/chanceblog/posts/2026/10/29/KR-101652/ (`경제·일/2026-10-29-KR-101652.md`)
- 후보가 1개뿐이다 — 2~3개를 채우려고 약한 글을 끌어오지 않았다.
- **후보 1 — S10 한글**: 유럽 국경 간 에너지망 구축에 몰린 자금 수요: CEF 에너지 공모에 28.8억 유로 신청 · 연결 강도 **강** · 양방향 가능(상대 글에도 이 글이 후보로 있음)
  - 주소: https://shine88pc.github.io/chanceblog/posts/2026/10/27/KR-093056/
  - 연결 이유: 공급 안정을 위한 유럽의 인프라 투자 수요(CEF) — 같은 정책 흐름
  - 본문 자리: ‘에너지 안보와 안보 자산으로서의 정유 인프라’ 절, 「특히 역내 정제 능력이 과도하게 위축될 경우 외부 수입 의존도가 높아져 지정학적 충격에 취약해질 수 있다는 점이 이번 대화 개시의 배경으로 풀이됩니다.」 문장 뒤
  - 덧붙일 문장(예): 공급 안정을 위해 유럽이 어떤 인프라에 자금을 요청하고 있는지는 [국경 간 에너지망 사업에 CEF 공모 신청이 몰린 소식을 다룬 글](https://shine88pc.github.io/chanceblog/posts/2026/10/27/KR-093056/)에서 볼 수 있습니다.
  - 링크 텍스트: 국경 간 에너지망 사업에 CEF 공모 신청이 몰린 소식을 다룬 글

### S11 · 영문 — Energy Security and Defence Readiness: Inside the EU's High-Level Dialogue with Refining

- 이 글 주소: https://shine88pc.github.io/chanceblog/posts/2026/10/29/EN-101652/ (`Economy & Work/2026-10-29-EN-101652.md`)
- 후보가 1개뿐이다 — 2~3개를 채우려고 약한 글을 끌어오지 않았다.
- **후보 1 — S10 영문**: Demand Surges for Cross-Border Energy Grids: 67 Projects Seek €2.88 Billion in EU Co-Funding · 연결 강도 **강** · 양방향 가능(상대 글에도 이 글이 후보로 있음)
  - 주소: https://shine88pc.github.io/chanceblog/posts/2026/10/27/EN-093056/
  - 연결 이유: 공급 안정을 위한 유럽의 인프라 투자 수요(CEF) — 같은 정책 흐름
  - 본문 자리: ‘Refining Infrastructure as a Strategic Asset’ 절, 「…decline too sharply, reliance on external fuel imports can heighten exposure to international trade disruptions and geopolitical pressure.」 문장 뒤
  - 덧붙일 문장(예): Which infrastructure projects Europe is asking to fund for supply security is covered in [the EU’s Connecting Europe Facility energy call and the funding requested by 67 projects](https://shine88pc.github.io/chanceblog/posts/2026/10/27/EN-093056/).
  - 링크 텍스트: the EU’s Connecting Europe Facility energy call and the funding requested by 67 projects

## S12. “무엇이 중요한지는 스스로 결정한다”: 우주 공학 현장의 멘토링

### S12 · 한글 — "너에게 무엇이 중요한지 결정하는 것": 우주 공학 현장에서 멘토링이 갖는 의미

- 이 글 주소: https://shine88pc.github.io/chanceblog/posts/2026/10/28/KR-111851/ (`과학·환경/2026-10-28-KR-111851.md`)
- 후보가 1개뿐이다 — 2~3개를 채우려고 약한 글을 끌어오지 않았다.
- **후보 1 — S16 한글**: 175년 만의 궤도와 보이저의 항해: 밤하늘 관측이 일깨우는 행성 탐사의 유산 · 연결 강도 **약** · 양방향 가능(상대 글에도 이 글이 후보로 있음) · **조건: 이 글(S12)을 공개로 유지할 때만**
  - 주소: https://shine88pc.github.io/chanceblog/posts/2026/11/02/KR-100912/
  - 연결 이유: GN&C(유도·항법·제어)의 대표 사례인 궤적 설계 이야기
  - 본문 자리: 「복잡한 우주 시스템을 다루는 GN&C 분야는 미션의 성공과 안전을 보장하기 위해 높은 수준의 공학적 판단력과 전문성이 요구되는 영역입니다.」 문장 뒤
  - 덧붙일 문장(예): 궤도를 설계하는 일의 한 예는 [행성 정렬과 중력 도움으로 외행성을 탐사한 보이저 1·2호 이야기](https://shine88pc.github.io/chanceblog/posts/2026/11/02/KR-100912/)에서 볼 수 있습니다.
  - 링크 텍스트: 행성 정렬과 중력 도움으로 외행성을 탐사한 보이저 1·2호 이야기

### S12 · 영문 — "You Decide What’s Important": How Mentorship Shapes Aerospace Engineering Talent

- 이 글 주소: https://shine88pc.github.io/chanceblog/posts/2026/10/28/EN-111851/ (`Science & Environment/2026-10-28-EN-111851.md`)
- 후보가 1개뿐이다 — 2~3개를 채우려고 약한 글을 끌어오지 않았다.
- **후보 1 — S16 영문**: A 175-Year Planetary Alignment and Voyager’s Path: What Deep-Space Milestones Mean for Everyday Observers · 연결 강도 **약** · 양방향 가능(상대 글에도 이 글이 후보로 있음) · **조건: 이 글(S12)을 공개로 유지할 때만**
  - 주소: https://shine88pc.github.io/chanceblog/posts/2026/11/02/EN-100912/
  - 연결 이유: GN&C(유도·항법·제어)의 대표 사례인 궤적 설계 이야기
  - 본문 자리: 「…on precise calculations and real-time oversight—transferring technical capability involves more than handing over standard operating procedures.」 문장 뒤
  - 덧붙일 문장(예): One example of the trajectory work such engineers do is described in [how a 1977 planetary alignment and gravity assists shaped Voyager’s Grand Tour](https://shine88pc.github.io/chanceblog/posts/2026/11/02/EN-100912/).
  - 링크 텍스트: how a 1977 planetary alignment and gravity assists shaped Voyager’s Grand Tour

## S13. EU ‘자연 크레딧 우호국’ 출범: 생물다양성 금융은 시장의 해법이 될까

### S13 · 한글 — EU의 '자연 크레딧 우호국' 출범: 생물다양성 금융은 시장의 해법이 될 수 있을까

- 이 글 주소: https://shine88pc.github.io/chanceblog/posts/2026/10/29/KR-235205/ (`과학·환경/2026-10-29-KR-235205.md`)
- **후보 1 — S14 한글**: 유럽 전역의 기후 위험을 하나의 대시보드로 보다: JRC의 지역별 통합 데이터가 던지는 변화 · 연결 강도 **중** · 양방향 가능(상대 글에도 이 글이 후보로 있음)
  - 주소: https://shine88pc.github.io/chanceblog/posts/2026/10/31/KR-115025/
  - 연결 이유: ‘기준을 맞춘 측정이 있어야 가치가 왜곡되지 않는다’는 같은 쟁점(JRC 표준화 데이터)
  - 본문 자리: ‘국제 공조가 필요한 배경과 구조적 과제’ 절, 「표준화된 지표가 부재할 경우 크레딧의 환경적 가치가 왜곡될 위험이 있습니다.」 문장 뒤
  - 덧붙일 문장(예): 자료를 같은 기준으로 맞추는 일의 가치는 [유럽 지역별 기후 위험 데이터를 하나의 대시보드로 모은 JRC 소식](https://shine88pc.github.io/chanceblog/posts/2026/10/31/KR-115025/)에서도 볼 수 있습니다.
  - 링크 텍스트: 유럽 지역별 기후 위험 데이터를 하나의 대시보드로 모은 JRC 소식
- **후보 2 — S17 한글**: 기후변화 대응의 축 이동: 선제적·시스템적 위험 관리가 공동체와 경제에 의미하는 것 · 연결 강도 **중** · 양방향 가능(상대 글에도 이 글이 후보로 있음)
  - 주소: https://shine88pc.github.io/chanceblog/posts/2026/10/27/KR-221527/
  - 연결 이유: EU 환경·기후 정책의 다른 축(위험 사전 관리) — 같은 분야 확장 주제
  - 본문 자리: ‘시장의 기대와 남겨진 검증 과제’ 절, 「제도가 실효성을 거두려면 자연 크레딧이 오염 행위를 가리는 면죄부로 전락하지 않도록 엄격한 환경적 온전성(integrity) 기준이 뒷받침되어야 할 것입니다.」 문장 뒤
  - 덧붙일 문장(예): 같은 시기 집행위가 기후 위험에 대비하는 방향도 내놓았는데, 이는 [집행위의 선제적·시스템적 기후 위험 관리 방향을 다룬 글](https://shine88pc.github.io/chanceblog/posts/2026/10/27/KR-221527/)에서 다뤘습니다.
  - 링크 텍스트: 집행위의 선제적·시스템적 기후 위험 관리 방향을 다룬 글

### S13 · 영문 — EU Launches 'Friends of Credits for Nature and Biodiversity': Can Markets Finance Ecosystem Recovery?

- 이 글 주소: https://shine88pc.github.io/chanceblog/posts/2026/10/29/EN-235205/ (`Science & Environment/2026-10-29-EN-235205.md`)
- **후보 1 — S14 영문**: Mapping Regional Hazards: Inside the JRC's Single Climate Risk Dashboard · 연결 강도 **중** · 양방향 가능(상대 글에도 이 글이 후보로 있음)
  - 주소: https://shine88pc.github.io/chanceblog/posts/2026/10/31/EN-115025/
  - 연결 이유: ‘기준을 맞춘 측정이 있어야 가치가 왜곡되지 않는다’는 같은 쟁점(JRC 표준화 데이터)
  - 본문 자리: ‘Why International Cooperation Matters’ 절, 「…and soil and water quality requires robust scientific metrics. Without common guidelines, comparing credits across regions remains challenging.」 문장 뒤
  - 덧붙일 문장(예): The same need for harmonised measurement is the point of [the JRC’s single dashboard of regional climate risk data](https://shine88pc.github.io/chanceblog/posts/2026/10/31/EN-115025/).
  - 링크 텍스트: the JRC’s single dashboard of regional climate risk data
- **후보 2 — S17 영문**: Shifting the Climate Defense: What Proactive Risk Management Means for European Communities · 연결 강도 **중** · 양방향 가능(상대 글에도 이 글이 후보로 있음)
  - 주소: https://shine88pc.github.io/chanceblog/posts/2026/10/27/EN-221527/
  - 연결 이유: EU 환경·기후 정책의 다른 축(위험 사전 관리) — 같은 분야 확장 주제
  - 본문 자리: ‘Institutional Prospects and Open Questions’ 절, 「The launch of this coalition signals an expanding effort to integrate market mechanisms into ecological protection.」 문장 뒤
  - 덧붙일 문장(예): The Commission’s approach to preparing for climate risks is covered in [the European Commission’s proactive, systemic approach to climate risk](https://shine88pc.github.io/chanceblog/posts/2026/10/27/EN-221527/).
  - 링크 텍스트: the European Commission’s proactive, systemic approach to climate risk

## S14. 유럽 전역의 기후 위험을 하나의 대시보드로: JRC 지역별 통합 데이터

### S14 · 한글 — 유럽 전역의 기후 위험을 하나의 대시보드로 보다: JRC의 지역별 통합 데이터가 던지는 변화

- 이 글 주소: https://shine88pc.github.io/chanceblog/posts/2026/10/31/KR-115025/ (`과학·환경/2026-10-31-KR-115025.md`)
- **후보 1 — S17 한글**: 기후변화 대응의 축 이동: 선제적·시스템적 위험 관리가 공동체와 경제에 의미하는 것 · 연결 강도 **강** · 양방향 가능(상대 글에도 이 글이 후보로 있음)
  - 주소: https://shine88pc.github.io/chanceblog/posts/2026/10/27/KR-221527/
  - 연결 이유: 같은 자료가 정책 근거로 쓰인 집행위의 기후 위험 사전 관리 방향
  - 본문 자리: ‘기후 과학과 지방 행정의 연결고리’ 절, 「예를 들어, 특정 기온 상승 폭에서 취약성이 급증하는 구역을 식별함으로써 과잉 투자나 과소 투자를 방지하고, 기후 재해 보험 및 인프라 유지보수 계획에 실증적 근거를 반영하는 것이 가능해집니다.」 문장 뒤
  - 덧붙일 문장(예): 이런 지역별 위험 자료가 영향평가에 쓰인 집행위의 정책 방향은 [집행위의 선제적·시스템적 기후 위험 관리 방향을 다룬 글](https://shine88pc.github.io/chanceblog/posts/2026/10/27/KR-221527/)에서 볼 수 있습니다.
  - 링크 텍스트: 집행위의 선제적·시스템적 기후 위험 관리 방향을 다룬 글
- **후보 2 — S13 한글**: EU의 '자연 크레딧 우호국' 출범: 생물다양성 금융은 시장의 해법이 될 수 있을까 · 연결 강도 **중** · 양방향 가능(상대 글에도 이 글이 후보로 있음)
  - 주소: https://shine88pc.github.io/chanceblog/posts/2026/10/29/KR-235205/
  - 연결 이유: ‘기준을 맞춘 측정이 있어야 가치가 왜곡되지 않는다’는 같은 쟁점(자연 크레딧)
  - 본문 자리: ‘단편화된 위험 정보를 넘어: 단일 플랫폼의 실질적 의미’ 절, 「이번 조치에서 주목할 점은 유럽 차원에서 '표준화(harmonised)'된 지역별 데이터 세트가 단일 대시보드로 통합되었다는 사실입니다.」 문장 뒤
  - 덧붙일 문장(예): 기준이 제각각이면 가치가 왜곡될 수 있다는 같은 문제는 [EU ‘자연 크레딧 우호국’ 출범과 생물다양성 금융을 다룬 글](https://shine88pc.github.io/chanceblog/posts/2026/10/29/KR-235205/)에서도 나옵니다.
  - 링크 텍스트: EU ‘자연 크레딧 우호국’ 출범과 생물다양성 금융을 다룬 글

### S14 · 영문 — Mapping Regional Hazards: Inside the JRC's Single Climate Risk Dashboard

- 이 글 주소: https://shine88pc.github.io/chanceblog/posts/2026/10/31/EN-115025/ (`Science & Environment/2026-10-31-EN-115025.md`)
- **후보 1 — S17 영문**: Shifting the Climate Defense: What Proactive Risk Management Means for European Communities · 연결 강도 **강** · 양방향 가능(상대 글에도 이 글이 후보로 있음)
  - 주소: https://shine88pc.github.io/chanceblog/posts/2026/10/27/EN-221527/
  - 연결 이유: 같은 자료가 정책 근거로 쓰인 집행위의 기후 위험 사전 관리 방향
  - 본문 자리: ‘Bridging Earth Systems Science and Municipal Finance’ 절, 「…face severe operational thresholds under given warming scenarios, helping prevent both costly over-engineering and disastrous under-investment.」 문장 뒤
  - 덧붙일 문장(예): The Commission’s climate-resilience proposal, whose impact assessment drew on data like these, is covered in [the European Commission’s proactive, systemic approach to climate risk](https://shine88pc.github.io/chanceblog/posts/2026/10/27/EN-221527/).
  - 링크 텍스트: the European Commission’s proactive, systemic approach to climate risk
- **후보 2 — S13 영문**: EU Launches 'Friends of Credits for Nature and Biodiversity': Can Markets Finance Ecosystem Recovery? · 연결 강도 **중** · 양방향 가능(상대 글에도 이 글이 후보로 있음)
  - 주소: https://shine88pc.github.io/chanceblog/posts/2026/10/29/EN-235205/
  - 연결 이유: ‘기준을 맞춘 측정이 있어야 가치가 왜곡되지 않는다’는 같은 쟁점(자연 크레딧)
  - 본문 자리: ‘Consolidating Fragmented Climate Hazards’ 절, 「The central development in this release is harmonisation.」 문장 뒤
  - 덧붙일 문장(예): A similar need for common measurement appears in [the EU’s ‘Friends of Credits for Nature and Biodiversity’ and biodiversity finance](https://shine88pc.github.io/chanceblog/posts/2026/10/29/EN-235205/).
  - 링크 텍스트: the EU’s ‘Friends of Credits for Nature and Biodiversity’ and biodiversity finance

## S15. 허블 우주망원경과 민간 궤도 서비스: 정보요청서(RFI)가 던진 과학 자산 지속성 질문

### S15 · 한글 — 허블 우주망원경과 민간 우주 궤도 서비스: 정보요청서가 던진 과학 자산의 지속성 질문

- 이 글 주소: https://shine88pc.github.io/chanceblog/posts/2026/11/02/KR-081916/ (`과학·환경/2026-11-02-KR-081916.md`)
- **후보 1 — S05 한글**: 우주날씨 경보 G1~G5, 우리 생활에는 어떤 뜻일까? · 연결 강도 **중** · 양방향 가능(상대 글에도 이 글이 후보로 있음)
  - 주소: https://shine88pc.github.io/chanceblog/posts/2026/10/20/KR-125000/
  - 연결 이유: 허블 같은 저궤도 관측 자산은 대기 저항으로 고도가 낮아지는데, 우주날씨가 나쁠 때 그 저항이 커질 수 있다고 NOAA 가 설명하는 글이 이미 있음(우주날씨 글 G3 설명)
  - 본문 자리: ‘궤도 내 서비스 조사가 의미하는 것’ 절, 「일반적으로 인공위성이나 궤도 망원경을 대상으로 하는 우주 궤도 서비스는 궤도 유지 및 고도 상승, 자세 제어 보조, 혹은 부품 점검 및 정비와 같은 작업을 포괄합니다.」 문장 뒤
  - 덧붙일 문장(예): 저궤도 위성은 대기 저항으로 고도가 서서히 낮아지는데, 우주날씨가 나쁠 때 이 저항이 커질 수 있다고 NOAA 는 설명합니다([우주날씨 경보(G1~G5)가 위성·전력망·항법에 줄 수 있는 영향을 정리한 글](https://shine88pc.github.io/chanceblog/posts/2026/10/20/KR-125000/)).
  - 링크 텍스트: 우주날씨 경보(G1~G5)가 위성·전력망·항법에 줄 수 있는 영향을 정리한 글
- **후보 2 — S16 한글**: 175년 만의 궤도와 보이저의 항해: 밤하늘 관측이 일깨우는 행성 탐사의 유산 · 연결 강도 **중** · 양방향 가능(상대 글에도 이 글이 후보로 있음)
  - 주소: https://shine88pc.github.io/chanceblog/posts/2026/11/02/KR-100912/
  - 연결 이유: 같은 NASA 가 오래 운용하는 공공 과학 자산 이야기 — ‘새로 만들기보다 기존 자산을 쓰는 논점’의 다른 사례
  - 본문 자리: ‘공공 연구 자산과 상업 생태계의 교차점’ 절, 「만약 궤도 감쇠를 늦추거나 관측 장비의 작동 환경을 지원할 수 있는 현실적인 방안이 존재한다면, 새로운 대형 망원경을 제작·발사하는 데 드는 막대한 비용 대비 기존 관측 인프라의 과학적 산출을 극대화할 수 있습니다.」 문장 뒤
  - 덧붙일 문장(예): 같은 NASA 의 오래된 과학 임무로는 1977년에 발사된 보이저 탐사선도 있습니다([행성 정렬과 중력 도움으로 외행성을 탐사한 보이저 1·2호 이야기](https://shine88pc.github.io/chanceblog/posts/2026/11/02/KR-100912/)).
  - 링크 텍스트: 행성 정렬과 중력 도움으로 외행성을 탐사한 보이저 1·2호 이야기

### S15 · 영문 — Commercial In-Space Servicing for Hubble: What an RFI Reveals About Science Infrastructure

- 이 글 주소: https://shine88pc.github.io/chanceblog/posts/2026/11/02/EN-081916/ (`Science & Environment/2026-11-02-EN-081916.md`)
- **후보 1 — S05 영문**: What Does a G1–G5 Space Weather Alert Mean for Everyday Life? · 연결 강도 **중** · 양방향 가능(상대 글에도 이 글이 후보로 있음)
  - 주소: https://shine88pc.github.io/chanceblog/posts/2026/10/20/EN-125000/
  - 연결 이유: 저궤도 위성의 고도 감소(대기 저항)와 우주날씨 영향의 직접 연결 — 글에 ‘re-boosting altitudes’ 가 이미 있음
  - 본문 자리: ‘Understanding the Scope of the Request’ 절, 「…encompasses satellite rendezvous, orbital maneuvering, re-boosting altitudes, attitude control assistance, or mechanical inspection and repair.」 문장 뒤
  - 덧붙일 문장(예): Low-Earth-orbit satellites lose altitude to atmospheric drag, and NOAA notes that strong geomagnetic storms can increase that drag ([what a G1–G5 space weather alert can mean for satellites and power grids](https://shine88pc.github.io/chanceblog/posts/2026/10/20/EN-125000/)).
  - 링크 텍스트: what a G1–G5 space weather alert can mean for satellites and power grids
- **후보 2 — S16 영문**: A 175-Year Planetary Alignment and Voyager’s Path: What Deep-Space Milestones Mean for Everyday Observers · 연결 강도 **중** · 양방향 가능(상대 글에도 이 글이 후보로 있음)
  - 주소: https://shine88pc.github.io/chanceblog/posts/2026/11/02/EN-100912/
  - 연결 이유: 같은 NASA 의 장기 운용 공공 과학 자산 — 기존 자산을 어떻게 활용하는가라는 논점의 다른 사례
  - 본문 자리: ‘The Intersection of Public Science and Private Capabilities’ 절, 「…can generate high-value astrophysical data without the full budget required to develop, test, and launch an entirely new flagship observatory.」 문장 뒤
  - 덧붙일 문장(예): Another long-lived public science mission is covered in [how a 1977 planetary alignment and gravity assists shaped Voyager’s Grand Tour](https://shine88pc.github.io/chanceblog/posts/2026/11/02/EN-100912/).
  - 링크 텍스트: how a 1977 planetary alignment and gravity assists shaped Voyager’s Grand Tour
- **후보 3 — S02 영문**: Japan’s MMX Mission Is on Its Way to Phobos: What the 10-Gram Sample Could Tell Us · 연결 강도 **중** · 양방향 가능(상대 글에도 이 글이 후보로 있음)
  - 주소: https://shine88pc.github.io/chanceblog/posts/2026/10/18/EN-233513/
  - 연결 이유: ‘탐색 단계(RFI)’와 ‘이미 발사된 임무’의 대비 — 계획과 실제를 구분해 읽는 같은 원칙
  - 본문 자리: 「An RFI is an exploratory mechanism rather than a contract award or a formal mission commitment.」 문장 뒤
  - 덧붙일 문장(예): For a mission that has already moved from plan to launch, see [Japan’s MMX mission to Phobos, which launched on October 20 while its sample-return goals remain planned](https://shine88pc.github.io/chanceblog/posts/2026/10/18/EN-233513/).
  - 링크 텍스트: Japan’s MMX mission to Phobos, which launched on October 20 while its sample-return goals remain planned

## S16. 175년 만의 궤도와 보이저의 항해: 밤하늘이 일깨우는 행성 탐사의 유산

### S16 · 한글 — 175년 만의 궤도와 보이저의 항해: 밤하늘 관측이 일깨우는 행성 탐사의 유산

- 이 글 주소: https://shine88pc.github.io/chanceblog/posts/2026/11/02/KR-100912/ (`과학·환경/2026-11-02-KR-100912.md`)
- **후보 1 — S15 한글**: 허블 우주망원경과 민간 우주 궤도 서비스: 정보요청서가 던진 과학 자산의 지속성 질문 · 연결 강도 **중** · 양방향 가능(상대 글에도 이 글이 후보로 있음)
  - 주소: https://shine88pc.github.io/chanceblog/posts/2026/11/02/KR-081916/
  - 연결 이유: 수십 년 전 우주 자산(허블)을 앞으로 어떻게 이어 쓸지 묻는 NASA 정보요청서 — 공공 과학 자산 논점의 연결
  - 본문 자리: ‘공공 과학 자산과 교육 현장이 나누는 혜택’ 절, 「대형 행성 탐사 프로젝트는 공공 재정이 투입되는 대규모 사업이지만, 그 결과물로 얻어진 관측 데이터와 영상은 전 세계 시민과 교육 현장에 공유되는 지식 자산이 되었습니다.」 문장 뒤
  - 덧붙일 문장(예): 오래된 우주 자산의 수명을 어떻게 이어 갈지는 NASA 가 [허블 우주망원경을 민간 궤도 서비스로 지원할 수 있는지 묻는 NASA 정보요청서를 다룬 글](https://shine88pc.github.io/chanceblog/posts/2026/11/02/KR-081916/)에서도 다뤘습니다.
  - 링크 텍스트: 허블 우주망원경을 민간 궤도 서비스로 지원할 수 있는지 묻는 NASA 정보요청서를 다룬 글
- **후보 2 — S12 한글**: "너에게 무엇이 중요한지 결정하는 것": 우주 공학 현장에서 멘토링이 갖는 의미 · 연결 강도 **약** · 양방향 가능(상대 글에도 이 글이 후보로 있음) · **조건: S12(멘토링 글)를 공개로 유지할 때만**
  - 주소: https://shine88pc.github.io/chanceblog/posts/2026/10/28/KR-111851/
  - 연결 이유: 궤적 설계 같은 일을 하는 유도·항법·제어(GN&C) 엔지니어와 인턴의 멘토링 이야기
  - 본문 자리: ‘175년 주기의 정렬과 중력 도움이 만든 기회’ 절, 「1970년대 후반의 기술로 수립된 이 궤적 설계는 천문학적 관측과 궤도역학이 어떻게 결합하여 자원의 한계를 극복했는지를 보여줍니다.」 문장 뒤
  - 덧붙일 문장(예): 이런 궤적을 계산하는 유도·항법·제어 분야의 엔지니어 이야기는 [NASA 존슨우주센터의 유도·항법·제어 엔지니어와 인턴의 멘토링 이야기](https://shine88pc.github.io/chanceblog/posts/2026/10/28/KR-111851/)에서 볼 수 있습니다.
  - 링크 텍스트: NASA 존슨우주센터의 유도·항법·제어 엔지니어와 인턴의 멘토링 이야기

### S16 · 영문 — A 175-Year Planetary Alignment and Voyager’s Path: What Deep-Space Milestones Mean for Everyday Observers

- 이 글 주소: https://shine88pc.github.io/chanceblog/posts/2026/11/02/EN-100912/ (`Science & Environment/2026-11-02-EN-100912.md`)
- **후보 1 — S15 영문**: Commercial In-Space Servicing for Hubble: What an RFI Reveals About Science Infrastructure · 연결 강도 **중** · 양방향 가능(상대 글에도 이 글이 후보로 있음)
  - 주소: https://shine88pc.github.io/chanceblog/posts/2026/11/02/EN-081916/
  - 연결 이유: NASA 의 장기 운용 과학 자산(허블) 지원 방안을 민간에 묻는 정보요청서 — 공공 과학 자산 논점
  - 본문 자리: ‘From Public Funding to Shared Civic Literacy’ 절, 「…observational tools have become durable public goods distributed freely to educators, amateur astronomy networks, and local communities worldwide.」 문장 뒤
  - 덧붙일 문장(예): How an older space science asset might be kept running is the subject of [NASA’s request for information on commercial servicing for the Hubble Space Telescope](https://shine88pc.github.io/chanceblog/posts/2026/11/02/EN-081916/).
  - 링크 텍스트: NASA’s request for information on commercial servicing for the Hubble Space Telescope
- **후보 2 — S02 영문**: Japan’s MMX Mission Is on Its Way to Phobos: What the 10-Gram Sample Could Tell Us · 연결 강도 **중** · 양방향 가능(상대 글에도 이 글이 후보로 있음)
  - 주소: https://shine88pc.github.io/chanceblog/posts/2026/10/18/EN-233513/
  - 연결 이유: 심우주 임무의 경로·계획 설계라는 같은 주제 — 현재 진행 중인 임무(MMX)와의 대비
  - 본문 자리: ‘The Mechanics of an Exceptional Alignment’ 절, 「…multiple flybys highlights how mathematical discipline and celestial geometry converged to overcome strict technological and logistical boundaries.」 문장 뒤
  - 덧붙일 문장(예): A current deep-space mission built around a different challenge, returning a sample from Mars’s moon Phobos, is described in [Japan’s MMX mission to Phobos and what a 10-gram sample could tell us](https://shine88pc.github.io/chanceblog/posts/2026/10/18/EN-233513/).
  - 링크 텍스트: Japan’s MMX mission to Phobos and what a 10-gram sample could tell us
- **후보 3 — S12 영문**: "You Decide What’s Important": How Mentorship Shapes Aerospace Engineering Talent · 연결 강도 **약** · 양방향 가능(상대 글에도 이 글이 후보로 있음) · **조건: S12(멘토링 글)를 공개로 유지할 때만**
  - 주소: https://shine88pc.github.io/chanceblog/posts/2026/10/28/EN-111851/
  - 연결 이유: 궤적 설계 같은 일을 하는 유도·항법·제어(GN&C) 엔지니어의 멘토링 이야기
  - 본문 자리: ‘The Mechanics of an Exceptional Alignment’ 절, 「…engineers planned a path that capitalized on planetary gravity to alter trajectories and boost speeds without requiring immense fuel reserves.」 문장 뒤
  - 덧붙일 문장(예): The engineers who plan such trajectories work in guidance, navigation and control; one mentor’s view of that work is in [how a Johnson Space Center guidance, navigation and control engineer mentors interns](https://shine88pc.github.io/chanceblog/posts/2026/10/28/EN-111851/).
  - 링크 텍스트: how a Johnson Space Center guidance, navigation and control engineer mentors interns

## S17. 기후변화 대응의 축 이동: 선제적·시스템적 위험 관리 (집행위 ‘기후 회복력’ 제안)

### S17 · 한글 — 기후변화 대응의 축 이동: 선제적·시스템적 위험 관리가 공동체와 경제에 의미하는 것

- 이 글 주소: https://shine88pc.github.io/chanceblog/posts/2026/10/27/KR-221527/ (`사회·정책/2026-10-27-KR-221527.md`)
- **후보 1 — S14 한글**: 유럽 전역의 기후 위험을 하나의 대시보드로 보다: JRC의 지역별 통합 데이터가 던지는 변화 · 연결 강도 **강** · 양방향 가능(상대 글에도 이 글이 후보로 있음)
  - 주소: https://shine88pc.github.io/chanceblog/posts/2026/10/31/KR-115025/
  - 연결 이유: 같은 정책의 근거 자료 — JRC 원문 기사가 지역 위험 데이터(TRACE)가 집행위 기후 회복력 프레임워크의 영향평가에 쓰였다고 밝힘
  - 본문 자리: ‘사후 복구에서 사전 대비로: 위험 관리의 구조적 변화’ 절, 「유럽연합이 제시하는 선제적 기후 탄력성(climate resilience) 접근법은 재난이 일어나기 전 위험 요소를 종합적으로 평가하고 예방적 조치를 사회 제반 인프라에 통합하는 데 초점을 맞춥니다.」 문장 뒤
  - 덧붙일 문장(예): 위험을 평가하는 데 쓰이는 지역별 자료의 하나는 [유럽 지역별 기후 위험 데이터를 하나의 대시보드로 모은 JRC 소식](https://shine88pc.github.io/chanceblog/posts/2026/10/31/KR-115025/)에서 소개했습니다.
  - 링크 텍스트: 유럽 지역별 기후 위험 데이터를 하나의 대시보드로 모은 JRC 소식
- **후보 2 — S13 한글**: EU의 '자연 크레딧 우호국' 출범: 생물다양성 금융은 시장의 해법이 될 수 있을까 · 연결 강도 **중** · 양방향 가능(상대 글에도 이 글이 후보로 있음)
  - 주소: https://shine88pc.github.io/chanceblog/posts/2026/10/29/KR-235205/
  - 연결 이유: 재원 조달 방식(민간 자본 유치) — ‘자연 크레딧’ 구상과의 접점
  - 본문 자리: ‘정책 이행의 과제와 한계’ 절, 「선제적 위험 관리가 실효성을 거두기 위해서는 제도적 상호 운용성과 지속 가능한 재원 조달이 전제되어야 합니다.」 문장 뒤
  - 덧붙일 문장(예): 재원 조달 방식의 하나로 민간 자본을 끌어들이려는 시도는 [EU ‘자연 크레딧 우호국’ 출범과 생물다양성 금융을 다룬 글](https://shine88pc.github.io/chanceblog/posts/2026/10/29/KR-235205/)에서 다룹니다.
  - 링크 텍스트: EU ‘자연 크레딧 우호국’ 출범과 생물다양성 금융을 다룬 글

### S17 · 영문 — Shifting the Climate Defense: What Proactive Risk Management Means for European Communities

- 이 글 주소: https://shine88pc.github.io/chanceblog/posts/2026/10/27/EN-221527/ (`Society & Policy/2026-10-27-EN-221527.md`)
- **후보 1 — S14 영문**: Mapping Regional Hazards: Inside the JRC's Single Climate Risk Dashboard · 연결 강도 **강** · 양방향 가능(상대 글에도 이 글이 후보로 있음)
  - 주소: https://shine88pc.github.io/chanceblog/posts/2026/10/31/EN-115025/
  - 연결 이유: 같은 정책의 근거 자료 — JRC 의 지역 위험 대시보드
  - 본문 자리: ‘Moving from Reactive Recovery to Systemic Prevention’ 절, 「…public institutions focus on identifying risk factors before disaster strikes and embedding protective measures into essential infrastructure.」 문장 뒤
  - 덧붙일 문장(예): One regional data source for assessing such risks is described in [the JRC’s single dashboard of regional climate risk data](https://shine88pc.github.io/chanceblog/posts/2026/10/31/EN-115025/).
  - 링크 텍스트: the JRC’s single dashboard of regional climate risk data
- **후보 2 — S13 영문**: EU Launches 'Friends of Credits for Nature and Biodiversity': Can Markets Finance Ecosystem Recovery? · 연결 강도 **중** · 양방향 가능(상대 글에도 이 글이 후보로 있음)
  - 주소: https://shine88pc.github.io/chanceblog/posts/2026/10/29/EN-235205/
  - 연결 이유: 재원 조달 방식(민간 자본 유치) — ‘자연 크레딧’ 구상과의 접점
  - 본문 자리: ‘Structural Challenges and Governance’ 절, 「…lower fiscal capacity may struggle to implement preventative measures, risking an uneven distribution of climate protection across communities.」 문장 뒤
  - 덧붙일 문장(예): One attempt to bring private capital into environmental protection is covered in [the EU’s ‘Friends of Credits for Nature and Biodiversity’ and biodiversity finance](https://shine88pc.github.io/chanceblog/posts/2026/10/29/EN-235205/).
  - 링크 텍스트: the EU’s ‘Friends of Credits for Nature and Biodiversity’ and biodiversity finance

## S18. 집행위의 프론텍스(유럽 국경·해안경비청) 강화 제안: 외부 국경 관리와 솅겐 체제

### S18 · 한글 — 유럽연합 집행위의 프론텍스 강화 제안: 외부 국경 관리와 솅겐 체제의 균형

- 이 글 주소: https://shine88pc.github.io/chanceblog/posts/2026/10/28/KR-184844/ (`사회·정책/2026-10-28-KR-184844.md`)
- 후보가 1개뿐이다 — 2~3개를 채우려고 약한 글을 끌어오지 않았다.
- **후보 1 — S17 한글**: 기후변화 대응의 축 이동: 선제적·시스템적 위험 관리가 공동체와 경제에 의미하는 것 · 연결 강도 **약** · 한 방향(상대 글은 이 글을 후보로 두지 않음)
  - 주소: https://shine88pc.github.io/chanceblog/posts/2026/10/27/KR-221527/
  - 연결 이유: 같은 날(10-27) 집행위가 내놓은 또 다른 제안 — ‘제안 단계’가 무엇인지 함께 이해하는 확장 주제
  - 본문 자리: 「이번 발표는 확정된 법률이나 즉각적인 집행 조치가 아니라, 집행위원회가 제출한 정책적 제안 단계입니다.」 문장 뒤
  - 덧붙일 문장(예): 집행위가 같은 날 내놓은 또 다른 정책 제안은 [집행위의 선제적·시스템적 기후 위험 관리 방향을 다룬 글](https://shine88pc.github.io/chanceblog/posts/2026/10/27/KR-221527/)에서 볼 수 있습니다.
  - 링크 텍스트: 집행위의 선제적·시스템적 기후 위험 관리 방향을 다룬 글

### S18 · 영문 — Reinforcing Frontex: The European Commission’s Proposal and the Governance of External Borders

- 이 글 주소: https://shine88pc.github.io/chanceblog/posts/2026/10/28/EN-184844/ (`Society & Policy/2026-10-28-EN-184844.md`)
- 후보가 1개뿐이다 — 2~3개를 채우려고 약한 글을 끌어오지 않았다.
- **후보 1 — S17 영문**: Shifting the Climate Defense: What Proactive Risk Management Means for European Communities · 연결 강도 **약** · 한 방향(상대 글은 이 글을 후보로 두지 않음)
  - 주소: https://shine88pc.github.io/chanceblog/posts/2026/10/27/EN-221527/
  - 연결 이유: 같은 날(10-27) 집행위가 내놓은 또 다른 제안 — ‘제안 단계’가 무엇인지 함께 이해하는 확장 주제
  - 본문 자리: 「This announcement represents a legislative and policy proposal rather than an adopted law or final operational decree.」 문장 뒤
  - 덧붙일 문장(예): Another proposal the Commission announced the same day is covered in [the European Commission’s proactive, systemic approach to climate risk](https://shine88pc.github.io/chanceblog/posts/2026/10/27/EN-221527/).
  - 링크 텍스트: the European Commission’s proactive, systemic approach to climate risk

## S19. 캐나다 청년 대졸자의 상용직 전일제 고용률 69%

### S19 · 한글 — 캐나다 청년 대졸자의 상용직 전일제 고용률 69%: 노동시장 긴장 완화가 남긴 과제

- 이 글 주소: https://shine88pc.github.io/chanceblog/posts/2026/10/30/KR-161110/ (`사회·정책/2026-10-30-KR-161110.md`)
- **후보 없음** — 사이트에 이어 읽을 만한 같은 분야의 글이 없다(억지 링크 금지). 글 아래의 ‘다른 언어 버전’ 표시만 있으면 충분하다.

### S19 · 영문 — Permanent Full-Time Employment at 69%: What Shifting Labour Market Dynamics Mean for Young Canadian Graduates

- 이 글 주소: https://shine88pc.github.io/chanceblog/posts/2026/10/30/EN-161110/ (`Society & Policy/2026-10-30-EN-161110.md`)
- **후보 없음** — 사이트에 이어 읽을 만한 같은 분야의 글이 없다(억지 링크 금지). 글 아래의 ‘다른 언어 버전’ 표시만 있으면 충분하다.

## S20. 바르셀로나로 향하는 LDT CiTiVERSE EDIC: 인간 중심 AI와 도시 디지털 트윈

### S20 · 한글 — 바르셀로나로 향하는 LDT CiTiVERSE EDIC: 인간 중심 AI와 도시 디지털 트윈의 행방

- 이 글 주소: https://shine88pc.github.io/chanceblog/posts/2026/11/01/KR-163702/ (`기술·미래/2026-11-01-KR-163702.md`)
- 후보가 1개뿐이다 — 2~3개를 채우려고 약한 글을 끌어오지 않았다.
- **후보 1 — S04 한글**: 기계연 동남권 오픈랩: 제조 AI를 현장에 연결하는 연구 공개 · 연결 강도 **약** · 양방향 가능(상대 글에도 이 글이 후보로 있음) · **조건: 이 글(S20)을 공개로 유지할 때만**
  - 주소: https://shine88pc.github.io/chanceblog/posts/2026/10/19/KR-195755/
  - 연결 이유: ‘디지털 트윈’ 접점 — 도시 행정과 제조 현장의 적용 비교
  - 본문 자리: ‘가상 공간에 구축되는 도시: 디지털 트윈의 구조’ 절, 「일반적으로 도시 디지털 트윈(Local Digital Twin)이란 실제 도시의 도로, 건물, 대중교통 흐름, 에너지 소비량, 기상 조건 등 물리적 환경 요소를 가상 공간에 3차원 데이터 모델로 똑같이 구현하는 기술 체계를 의미한다.」 문장 뒤
  - 덧붙일 문장(예): 공장에서 디지털 트윈을 쓰는 사례는 [제조 AI와 디지털 트윈 적용을 소개한 한국기계연구원 오픈랩 글](https://shine88pc.github.io/chanceblog/posts/2026/10/19/KR-195755/)에서 볼 수 있다.
  - 링크 텍스트: 제조 AI와 디지털 트윈 적용을 소개한 한국기계연구원 오픈랩 글

### S20 · 영문 — LDT CiTiVERSE EDIC at Smart City Expo 2026: Human-Centric AI and the Urban Digital Twin

- 이 글 주소: https://shine88pc.github.io/chanceblog/posts/2026/11/01/EN-163702/ (`Technology & Future/2026-11-01-EN-163702.md`)
- 후보가 1개뿐이다 — 2~3개를 채우려고 약한 글을 끌어오지 않았다.
- **후보 1 — S04 영문**: KIMM’s Southeast Open Lab: Connecting Manufacturing AI Research with Industry · 연결 강도 **약** · 양방향 가능(상대 글에도 이 글이 후보로 있음) · **조건: 이 글(S20)을 공개로 유지할 때만**
  - 주소: https://shine88pc.github.io/chanceblog/posts/2026/10/19/EN-195755/
  - 연결 이유: ‘디지털 트윈’ 접점 — 도시 행정과 제조 현장의 적용 비교
  - 본문 자리: ‘Mapping Physical Cities to Digital Environments’ 절, 「…urban planners can simulate policy adjustments, infrastructure changes, and disaster preparedness scenarios prior to physical implementation.」 문장 뒤
  - 덧붙일 문장(예): A factory-side use of digital twins is covered in [KIMM’s Southeast Open Lab on manufacturing AI and digital twins](https://shine88pc.github.io/chanceblog/posts/2026/10/19/EN-195755/).
  - 링크 텍스트: KIMM’s Southeast Open Lab on manufacturing AI and digital twins

---

# 4. 일부러 쓰지 않은 연결 (억지가 될 수 있음)

| 연결 | 왜 뺐나 |
|---|---|
| S01 AI 쇼핑 ↔ S04 KIMM | ‘발표와 입증된 성과를 나눠 본다’는 글쓰기 방식이 같을 뿐 독자가 이어서 알고 싶은 주제는 아님 |
| S10 CEF ↔ S17 기후 회복력 | 에너지 설비가 기후 충격을 견딘다는 접점이 얕고, 두 글 모두 그 접점을 다루지 않음 |
| S08 데이터센터 광고 ↔ S10 에너지망 | 데이터센터의 전력 부담은 S08 의 배경 문장일 뿐이고 S10 은 EU 지원 신청 이야기라 이어 읽을 이유가 약함 |
| S11 정유 대화 ↔ S18 프론텍스 | 둘 다 ‘안보’라는 말이 나오지만 에너지와 국경으로 독자의 관심사가 다름 |
| S19 캐나다 청년 고용 ↔ S12 멘토링 | ‘인재’라는 말만 같음. S12 는 공개 중단 검토 대상 |
| S05 우주날씨 ↔ S06 식품 날짜 | ‘경보·표시 읽는 법’이라는 형식만 같음(손질한 실용 글 두 편) — 주제 연결이 아님 |
| S16 보이저 ↔ S05 우주날씨 | 보이저 원문은 태양권 경계를 말하지만 현재 글에 그 내용이 없어 이을 문장이 없음 |
| S02 MMX ↔ S05 우주날씨 | 우주 방사선 이야기로 이을 수는 있으나 두 글 모두 그 대목이 없음 |
| S09 신뢰 ↔ S19 청년 고용 | 둘 다 통계 해설이라는 점뿐 |
| 한글 글 ↔ 영문 글(언어가 다른 연결) | 예: 한글 보이저 글에서 영문 MMX 글로. 독자가 언어를 바꾸게 되므로 뺐다. MMX 의 한글판이 생기면 그때 연결 |

---

# 5. 글 하단 ‘함께 읽으면 좋은 글’ 후보 (글마다 한눈에)

위 후보 중 ‘조건’이 없는 것을 연결 강도 순으로 적었다. 1개뿐이면 1개만 쓰고 채우지 않는다. 자기 자신·비공개 글은 없다.

| # | 이야기·언어 | 하단 추천 1 | 하단 추천 2 | 하단 추천 3 |
|--:|---|---|---|---|
| 1 | S01 한글 | S03 AI 네이티브 팩토리: 원프레딕트가 제시한 공장 운영 비전, 검증 과제… (약) | — | — |
| 5 | S07 영문 | S09 Trust in News Organizations Rises Among… (강) | S08 Data Centers in Social Media Political … (강) | — |
| 6 | S08 영문 | S07 58% of U.S. Adults Call Social Media an… (강) | S09 Trust in News Organizations Rises Among… (중) | — |
| 7 | S09 영문 | S07 58% of U.S. Adults Call Social Media an… (강) | S08 Data Centers in Social Media Political … (중) | — |
| 8 | S05 영문 | S15 Commercial In-Space Servicing for Hubbl… (중) | — | — |
| 9 | S02 영문 | S16 A 175-Year Planetary Alignment and Voya… (중) | S15 Commercial In-Space Servicing for Hubbl… (중) | — |
| 11 | S03 영문 | S04 KIMM’s Southeast Open Lab: Connecting M… (강) | — | — |
| 12 | S10 영문 | S11 Energy Security and Defence Readiness: … (강) | — | — |
| 13 | S11 영문 | S10 Demand Surges for Cross-Border Energy G… (강) | — | — |
| 14 | S06 영문 | — | — | — |
| 15 | S04 영문 (+조건부 1) | S03 AI-Native Factory: OnePredict’s Operati… (강) | — | — |
| 17 | S03 한글 | S04 기계연 동남권 오픈랩: 제조 AI를 현장에 연결하는 연구 공개 (강) | S01 AI 쇼핑은 어디까지 왔나: 상품 탐색은 대화창으로, 결제는 판매자 중… (약) | — |
| 19 | S12 영문 (+조건부 1) | — | — | — |
| 20 | S13 영문 | S14 Mapping Regional Hazards: Inside the JR… (중) | S17 Shifting the Climate Defense: What Proa… (중) | — |
| 21 | S14 영문 | S17 Shifting the Climate Defense: What Proa… (강) | S13 EU Launches 'Friends of Credits for Nat… (중) | — |
| 22 | S15 영문 | S05 What Does a G1–G5 Space Weather Alert M… (중) | S16 A 175-Year Planetary Alignment and Voya… (중) | S02 Japan’s MMX Mission Is on Its Way to Ph… (중) |
| 23 | S16 영문 (+조건부 1) | S15 Commercial In-Space Servicing for Hubbl… (중) | S02 Japan’s MMX Mission Is on Its Way to Ph… (중) | — |
| 24 | S17 영문 | S14 Mapping Regional Hazards: Inside the JR… (강) | S13 EU Launches 'Friends of Credits for Nat… (중) | — |
| 25 | S18 영문 | S17 Shifting the Climate Defense: What Proa… (약) | — | — |
| 26 | S19 영문 | — | — | — |
| 31 | S20 영문 (+조건부 1) | — | — | — |
| 32 | S10 한글 | S11 에너지 안보와 방위 준비태세: 유럽 정유업계와 집행위의 고위급 대화가 … (강) | — | — |
| 33 | S11 한글 | S10 유럽 국경 간 에너지망 구축에 몰린 자금 수요: CEF 에너지 공모에 … (강) | — | — |
| 34 | S05 한글 | S15 허블 우주망원경과 민간 우주 궤도 서비스: 정보요청서가 던진 과학 자산… (중) | — | — |
| 35 | S12 한글 (+조건부 1) | — | — | — |
| 36 | S13 한글 | S14 유럽 전역의 기후 위험을 하나의 대시보드로 보다: JRC의 지역별 통합… (중) | S17 기후변화 대응의 축 이동: 선제적·시스템적 위험 관리가 공동체와 경제에… (중) | — |
| 37 | S14 한글 | S17 기후변화 대응의 축 이동: 선제적·시스템적 위험 관리가 공동체와 경제에… (강) | S13 EU의 '자연 크레딧 우호국' 출범: 생물다양성 금융은 시장의 해법이 … (중) | — |
| 38 | S15 한글 | S05 우주날씨 경보 G1~G5, 우리 생활에는 어떤 뜻일까? (중) | S16 175년 만의 궤도와 보이저의 항해: 밤하늘 관측이 일깨우는 행성 탐사… (중) | — |
| 39 | S16 한글 (+조건부 1) | S15 허블 우주망원경과 민간 우주 궤도 서비스: 정보요청서가 던진 과학 자산… (중) | — | — |
| 44 | S20 한글 (+조건부 1) | — | — | — |
| 45 | S07 한글 | S09 미국인의 저널리즘 신뢰 반등: 전국·지역 뉴스 신뢰는 상승, 소셜 미디… (강) | S08 소셜 미디어 정치 광고 속 데이터센터: 반대 57% 대 찬성 3%가 뜻… (강) | — |
| 46 | S08 한글 | S07 미국 성인 58% "소셜 미디어가 주요 뉴스 정보원"… 퓨 리서치 조사… (강) | S09 미국인의 저널리즘 신뢰 반등: 전국·지역 뉴스 신뢰는 상승, 소셜 미디… (중) | — |
| 47 | S09 한글 | S07 미국 성인 58% "소셜 미디어가 주요 뉴스 정보원"… 퓨 리서치 조사… (강) | S08 소셜 미디어 정치 광고 속 데이터센터: 반대 57% 대 찬성 3%가 뜻… (중) | — |
| 48 | S17 한글 | S14 유럽 전역의 기후 위험을 하나의 대시보드로 보다: JRC의 지역별 통합… (강) | S13 EU의 '자연 크레딧 우호국' 출범: 생물다양성 금융은 시장의 해법이 … (중) | — |
| 49 | S18 한글 | S17 기후변화 대응의 축 이동: 선제적·시스템적 위험 관리가 공동체와 경제에… (약) | — | — |
| 50 | S19 한글 | — | — | — |
| 51 | S04 한글 (+조건부 1) | S03 AI 네이티브 팩토리: 원프레딕트가 제시한 공장 운영 비전, 검증 과제… (강) | — | — |
| 52 | S06 한글 | — | — | — |

---

# 6. 적용 방법 선택지

| 방법 | 내용 | 등급 | 장단점 |
|---|---|---|---|
| A. 본문 문장에 직접 링크 | 3장의 ‘본문 자리’에 덧붙일 문장 1~2개를 넣는다 | 본문 수정(T1, 근거 필수) — 양방향은 범위 확인 | 사이트 구조를 건드리지 않고 지금 가능. 글을 다시 쓰는 14편은 재작성 때 함께 넣는 편이 낫다 |
| B. 하단 ‘함께 읽으면 좋은 글’ 영역 신설 | 레이아웃에 영역을 만들고 글 머리말에 `related` 목록(2~3개)을 둔다. 5장 표가 그대로 목록이 된다 | `_layouts/` 는 **T3** | 주제 연결이 가장 정확해짐. 승인과 레이아웃 시험이 필요 |
| C. 지금의 자동 ‘같은 분야의 글’ 유지 + 분류명 정리 | 분류명 19종을 정리해 같은 분야 묶음을 정확히 | 사이트 구조에 닿으면 **T3 소지** | 글을 안 고쳐도 되지만 분류만 같다고 주제가 같지는 않다 |

**권장(내 의견)**: 먼저 A 를 허블 표준 글(표준 글 담당 담당)과 그 이웃 3글(S16·S05·S02)에만 시험 적용하고, 효과(체류·이어 읽기)를 한두 주 본 뒤 B 를 승인받을지 정한다. 분량을 늘리려는 링크가 아니라 ‘다음에 알고 싶은 것’으로 이어지는 링크만 남긴다.

**링크 형식(참고)**: 사이트가 `/chanceblog/` 아래에 있으므로(`_config.yml` 의 `baseurl`) 본문에는 이 문서의 전체 주소를 그대로 쓰거나 `/chanceblog/posts/…`(posts.json 의 `url` 값)처럼 baseurl 을 포함해야 한다. `/posts/…` 처럼 baseurl 이 빠진 주소는 깨진다. `post_url` 태그는 폴더 이름에 공백·한글이 있어 시험하지 않았다(쓰지 않는 편이 안전하다고 추정).

## 한계

- 연결 강도(강·중·약)와 ‘자연스러운 문장 자리’는 내 판단이다. 실제 화면에서 읽어 보며 어색한 문장은 편집자가 고쳐야 한다.
- 덧붙일 문장 예는 지금 글에 없는 새 문장이다. 사실 주장이 들어간 곳(예: 저궤도 위성의 대기 저항과 우주날씨)은 NOAA 척도 원문에서 확인한 내용으로만 썼다.
- 렌더링(실제 사이트에서의 보임)은 확인하지 않았다. 링크가 걸릴 글이 재작성되면 링크 텍스트·본문 자리를 다시 확인해야 한다.

