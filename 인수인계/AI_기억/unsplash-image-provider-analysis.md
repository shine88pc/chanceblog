---
name: unsplash-image-provider-analysis
description: 운영자 질문(2026-11-03 20:2x) '이미지는 블로그가 쓰는 Unsplash API 와 같은 방향으로 하면 되나, 문제는?' — 공식 문서(20:26 확인)의 한도·핫링크·다운로드 알림·출처 표시·'비자동' 취지·키 비밀·라이선스 사실, 데스크톱 이미지 공급자 설계 영향, 블로그 Chance 갈래의 출처 표시 누락·`ixid` 버림(Blogger 갈래는 준수), 다음 결정 요청에 올릴 항목 — 이후 운영자가 상세 명세 v1.0.0 을 올렸다([[unsplash-integration-spec-v100]], 구현·결정의 기준은 그쪽)
metadata:
  node_type: memory
  type: reference
  originSessionId: (세션 번호)
  modified: 2026-11-03T11:41:49.371Z
---

**질문(채팅 20:2x):** "이미지 관련해서는 unsplash 에서 현재 API로 이미지를 생성하고 있잖아 그것과 같은 방향으로 적용하면 될꺼 같은데 문제가 있을까?" → 답(채팅): **같은 방향 가능, 주의 5가지.** 구현 반영: 키 보관 'k' 에 `image_provider` 첫 항목 Unsplash(Access Key 한 칸, Secret 안 받음)·호출 예산, GUI 'g' 에 IMAGE_PROVIDER·IMAGE_ASSET_POLICY 문서 내용 전달(20:27~20:30).

**공식 문서로 확인한 사실(2026-11-03 20:26 KST, WebFetch — 요약 도구를 거친 것이라 운영 전 원문 대조):**
- 한도(문서 `unsplash.com/documentation`): **데모 앱 시간당 50회, 정식(Production) 승인 뒤 시간당 1,000회**(대시보드의 'Apply for Production', 가이드라인 준수·출처 표시 필수). **`api.unsplash.com` JSON 요청만 센다 — `images.unsplash.com` 사진 파일 요청은 안 센다.** 검색 `GET /search/photos`: `query·page·per_page(최대 30)·order_by·content_filter(low/high)·orientation·color·collections`, `lang` 은 베타(메일 신청). 사진 크기 `thumb` 200·`small` 400·`regular` 1080 px, 주소에 `w`·`q` 를 붙여 바꿔도 `ixid` 는 유지.
- API 가이드라인(`help.unsplash.com/en/articles/2511245-unsplash-api-guidelines`): ① **핫링크 필수**("All API uses must use the hotlinked image URLs returned by the API") ② 다운로드와 비슷한 동작을 하면 `photo.links.download_location` 으로 **다운로드 알림 요청**을 보낸다 ③ **출처 표시: Unsplash 와 사진작가를 쓰고 작가의 Unsplash 프로필로 링크, Unsplash 로 가는 모든 링크에 `?utm_source=앱이름&utm_medium=referral`** ④ Access Key·Secret 은 비밀(클라이언트 쪽이면 프록시) ⑤ API 취지는 "non-automated, high-quality, and authentic experiences"(자동화된 사용이 아니라 사람이 고르는 경험) ⑥ 너무 많은 요청을 빨리 보내면 접근이 꺼진다 ⑦ 앱 이름에 Unsplash 금지·Unsplash 핵심 경험 복제 금지·무수정 사진 판매 금지 ⑧ 사용자가 자기 개발자 계정을 만들 필요가 없어야 한다(공유 키+프록시).
- API 약관(`unsplash.com/api-terms`): 이미지를 보여줄 때마다 Unsplash·작가 출처 표시+링크(§9), 핫링크(§6), 다운로드·사용 알림 위반은 중대한 위반(§6), **저장·캐시는 약관에 없음**(가이드라인도 침묵), 앱 개수 제한은 없지만 자격 증명을 제3자와 공유 금지(§2)·**한도를 넘기려 하거나 우회 금지**(§12), 접근은 언제든 바꾸거나 중지될 수 있음(§11·19), 머신러닝·AI 용도는 별도 심사.
- 라이선스(`unsplash.com/license`): 상업 이용 가능, **라이선스 자체는 출처 표시를 요구하지 않음**(권장) — 그러나 **API 로 가져온 사진은 가이드라인상 표시 의무**. 경쟁 서비스용 모음 금지·무수정 판매 금지. 사진 속 사람·상표 권리는 언급 없음(민감한 사용은 따로 확인).

**내가 내린 결론(질문에 대한 답의 근거):**
1. **'생성'이 아니라 '검색'**: Unsplash 는 사진작가의 실제 사진을 검색해 가져온다(AI 생성 아님). 글에서 '직접 찍은 경험 사진'처럼 보이게 쓰지 않는다(콘텐츠 정책 '경험을 지어내지 않기').
2. **한도 공유**: 클라우드 파이프라인(`generator.py`)의 데모 키는 시간당 50회 — 데스크톱이 같은 키를 쓰면 한도를 같이 쓴다. 길: ① 데스크톱용 Unsplash 앱을 따로 등록(운영자 일·계정 관련 → 번호 요청) ② 정식 신청(출처 표시가 먼저 고쳐져야 함) ③ 같은 키라면 QuotaGuard 로 예약(일반 45회+다운로드 알림 5회)·캐시·지연 로딩. 한도는 헤더 `X-Ratelimit-Remaining/Limit` 로 읽는다.
3. **저장 정책 충돌**: 명세의 '썸네일 30일 캐시'는 핫링크 원칙과 어긋날 수 있다 → 기본값 제안: **사진 파일은 저장하지 않고 `images.unsplash.com` 주소로 바로 표시**, 검색 결과 메타데이터(사진 id·작가·프로필·`download_location`·주소)는 짧게(24시간~7일) 캐시, **사용자가 고른 사진만** 내려받아 저장(그때 다운로드 알림 호출). 운영자 결정 항목.
4. **출처 표시 누락(블로그 Chance 갈래만 — 2026-11-03 20:38 코드 재확인으로 정정)**: Blogger 갈래(`pipeline/main_image.py`)는 작가 이름·프로필 링크·Unsplash 링크를 UTM 과 함께 글 맨 위에 넣고 다운로드 알림도 보낸다(규칙 준수). **Chance(GitHub Pages) 갈래(`generator.py`)는 핫링크·다운로드 알림은 하지만 작가·출처 표시가 없고**(고정 풀 `IMAGE_POOL`·`index.html` 기본 썸네일도 마찬가지), 두 갈래 모두 주소를 새로 만들며 `ixid` 를 버린다. 후속 PR 제안(T2): Chance 글에 'Photo by 작가 on Unsplash' + UTM 링크 + 시험, `ixid` 유지, 한도 초과 시 고정 풀 대체 재검토 — 사이트 템플릿(`index.html`)을 건드리면 광고 표면 점검 필요. 정식 신청 전에 먼저. 상세는 [[unsplash-integration-spec-v100]] '블로그 현재 코드'.
5. **'비자동' 취지**: 데스크톱(제안 → 사람이 고름)은 취지에 맞다. 클라우드의 완전 자동 선택은 회색지대(정식 신청 심사에서 걸릴 수 있음) — 사람이 고르는 단계가 없다는 점을 알리고 운영자가 판단.
6. **키**: Access Key 는 비밀 취급(§2) — 데스크톱에서는 운영자 본인 키를 자격 증명 관리자에 두고 설치 파일에는 넣지 않는다(항목 2, [[installer-personal-pc-migration]]).
7. **검색어**: Unsplash 는 영어 검색이 정확 → 한국어 주제는 영어 검색어로(키 없이도 되는 용어표, Gemini 가 있으면 선택적으로).

**다음 `decision` 요청에 올릴 것(기본값 포함):** ⓐ 데스크톱용 Unsplash 앱을 따로 등록할지(기본: 같은 키 + 호출 예약) ⓑ 정식 신청 시점(기본: 출처 표시 수정 뒤) ⓒ 이미지 저장 정책(기본: 파일 저장 없음·메타 7일·선택 사진만 저장) ⓓ 블로그 쪽 출처 표시 고치기(기본: 고친다 — T2 PR, 광고 표면 영향 없는 본문 하단 표기) ⓔ 후보 공급자 Pexels·Pixabay 추가 여부(기본: 안 함 — 레지스트리 자리만).

관련: [[gui-polish-spec-v11-and-keys]] [[installer-personal-pc-migration]]
