# 통합 성과 대시보드 검토 (제안 — 사용자 결정 대기)

> 요청(2026-10-20): 블로그별 방문자·게시글·조회수 높은 글, 그리고 AdSense 사이트별 수익을 **한곳에서** 보고 싶다. 블로그가 늘어도 확인할 곳이 늘지 않게.
> 상태: **검토 완료, 구현 전.** 결정이 필요한 항목은 §7. 확인하지 못한 사실은 "확인 필요"로 표시했다.

## 1. 결론

**가능하다. 다만 "모든 플랫폼"이 아니라 공식 API가 있는 곳까지다.**

- 구글 계열(GA4 · Search Console · Blogger · AdSense)은 공식 API가 있어 한곳에 모을 수 있다.
- 네이버 블로그·서치어드바이저처럼 **조회용 공식 API를 확인하지 못한 곳**은 자동 수집이 어렵다. 로그인 화면을 긁어 오는 방식은 약관·보안 위험이 크고 쉽게 깨져 권하지 않는다. 이런 사이트는 수치를 정기적으로 시트에 옮겨 적는 수동 방식이 현실적이다.
- **권고: A(Looker Studio, 코드 없음)를 먼저** 만들고, 블로그가 3개 이상이 되거나 자동 알림·AI 피드백이 필요해지면 B(자체 수집기 + 비공개 리포트)를 추가한다.

## 2. 무엇을 어디서 가져올 수 있나

| 보고 싶은 것 | 출처 | 공식 API | 전제 | 지금 가능? |
|--------------|------|----------|------|-----------|
| 방문자·페이지뷰·인기 글 | **GA4** | Analytics Data API | 사이트에 GA4 태그 | Chance ✗(미설치) · Blogger ✓(설정에 측정 ID 입력) |
| 검색 노출·클릭·인기 페이지·검색어 | **Search Console** | Search Console API | 사이트 소유 확인(Chance는 인증 파일 있음) | ✓ 사이트를 바꾸지 않고 가능(데이터는 며칠 지연) |
| 블로그 전체 조회수(7일/30일/전체) | **Blogger API** | [`pageViews.get`](https://developers.google.com/blogger/docs/3.0/reference/pageViews/get) 확인됨. 허용 스코프가 `blogger` **하나뿐**(게시 권한 포함, 읽기 전용 아님) | 이미 준비 중인 Blogger OAuth | ✓ 단 블로그 전체 합계만(글별 조회수 없음) → 대시보드에는 GA4를 권장 |
| 게시글 수·발행 추이 | **우리 저장소 이력** | 불필요 | `history.json`·`blogger_history.json`·`_posts` | ✓ 외부 연결 없이 지금도 가능 |
| 사이트별 수익·광고 페이지뷰·클릭 | **AdSense Management API v2** | [`accounts.reports.generate`](https://developers.google.com/adsense/management/reference/rest/v2/accounts.reports/generate) — [`DOMAIN_NAME` 차원과 `ESTIMATED_EARNINGS`·`PAGE_VIEWS` 지표](https://developers.google.com/adsense/management/metrics-dimensions) 확인됨 | **승인된** AdSense 계정, 읽기 전용 OAuth | 심사 중이라 데이터 없음 → 승인 후. **주의: `DOMAIN_NAME`은 호스트 단위**다. Chance(`shine88pc.github.io/chanceblog/`)는 루트 랜딩(`shine88pc.github.io`)과 호스트가 같아 한 줄로 합쳐 보인다. 경로별로 나누려면 AdSense **URL 채널**(`URL_CHANNEL_NAME` 차원, 문서 확인됨)이 필요하고, 만드는 방법은 구현 때 확인한다 |
| 글별 수익 | GA4 + AdSense 연결 | GA4 | 연결 설정 | 확인 필요 |
| 네이버 블로그·서치어드바이저 | — | **공식 조회 API 확인 못함**(없다고 단정하지는 않음 → 네이버 개발자센터 API 목록에서 확인 필요) | — | 자동화 어려움(수동 입력) |

참고: GitHub Pages에는 방문자 통계가 내장돼 있지 않다. 그래서 Chance_Blog는 GA4 같은 분석 도구를 붙이기 전까지 방문자·인기 글 수치가 없고, 지금 볼 수 있는 건 Search Console(검색 유입)뿐이다.

## 3. 방식 비교

| | **A. Looker Studio** | **B. 자체 수집기 + 비공개 리포트** | **C. Sheets + Apps Script** |
|---|---|---|---|
| 구현 | 사용자가 클릭으로 구성(코드 없음, 무료 버전) | AI가 구현(`pipeline/metrics/`), 사용자는 API 사용 설정·동의 1회 | Apps Script로 AdSense·GA4를 시트에 적재(AdSense용 [Apps Script 서비스](https://developers.google.com/apps-script/advanced/adsense) 있음) |
| 블로그 추가 시 | GA4 스트림 추가 + 보고서 필터(약 5분) | 레지스트리에 식별자 한 줄 | 시트 열 추가 |
| 볼 곳 | 보고서 1장(모바일 가능, 비공개 공유) | 주간 요약을 **비공개 이슈/메일**로 받음 | 시트 |
| 자동 알림·AI 피드백 | 없음 | **가능**(트래픽 급락 알림, 잘 읽히는 주제를 주제 선정에 반영) | 제한적 |
| 네이버 등 API 없는 곳 | 시트 연결로 수동 | 수동 입력 파일로 병합 | 시트에 직접 입력 |
| 한계 | 블렌드는 데이터 소스 5개까지·조인은 일치 조건만([문서](https://docs.cloud.google.com/looker/docs/studio/how-blends-work-in-looker-studio)), **AdSense 커넥터는 확인 필요**(없으면 C의 시트 경유) | 구축·유지 필요, 토큰 관리 | 스크립트 유지 |

**스케일 팁**: 사이트마다 GA4 속성을 만들면 보고서에 데이터 소스가 계속 늘어난다. **GA4 속성 하나에 사이트별 데이터 스트림을 추가**하면(스트림 개수 한도는 확인하지 못함 — 구글 문서 확인 필요) 데이터 소스는 하나로 유지되고 호스트 이름으로 사이트를 구분할 수 있다. AdSense는 계정 하나에서 도메인별로 나뉘므로 소스 하나로 모든 사이트가 보인다. Search Console은 사이트별 속성이라 사이트마다 소스가 늘어난다(방식 B는 이 문제가 없다).

**같은 호스트의 사이트는 호스트로 구분되지 않는다.** GitHub Pages 프로젝트 사이트는 모두 `shine88pc.github.io` 아래에 있다. 앞으로 Jekyll 블로그를 같은 계정에 더 만들면 GA4 호스트 필터와 AdSense `DOMAIN_NAME`만으로는 합쳐 보이므로, GA4는 경로(`/chanceblog/` 등), AdSense는 URL 채널로 나눠야 한다. Blogger(`*.blogspot.com` 또는 개별 도메인)는 호스트가 달라 구분된다.

## 4. 반드시 지킬 제약

1. **공개 저장소·GitHub Pages에 수치를 올리지 않는다.** 이 저장소와 Pages 사이트는 공개다. Pages를 비공개로 게시하는 기능은 [GitHub Enterprise Cloud 전용](https://docs.github.com/en/enterprise-cloud@latest/pages/getting-started-with-github-pages/changing-the-visibility-of-your-github-pages-site)이고, Actions 로그·요약·산출물도 공개 저장소에서는 공개된다. 또 AdSense 약관의 기밀 정보 정의에 사이트 성과 통계(클릭률 등)가 포함돼 있는 것으로 보인다(2차 요약 기준 → **공식 약관 원문 확인 필요**). 어느 쪽이든 수익·성과 수치는 **비공개 채널**(Looker Studio 비공개 공유, 비공개 저장소, 메일)로만 다룬다.
2. **GA 설치는 T3**: 모든 페이지의 `<head>`가 바뀌고(광고 표면에 인접), **개인정보처리방침에 GA 사용·쿠키 고지**를 넣어야 하며(현재 `privacy.md`는 광고·쿠키 안내만 있음), AdSense 심사 중 사이트 변경이 된다. 사용자 승인 후 진행한다.
3. **OAuth는 읽기 전용 스코프만**: GA4 `analytics.readonly`, Search Console `webmasters.readonly`, AdSense `adsense.readonly`. 동의 화면은 "프로덕션"(테스트 상태는 refresh token 7일 만료 — D-11), 토큰은 비공개 저장소의 Secrets에. 서비스 계정 키 파일은 쓰지 않는다. **Blogger `pageViews`는 게시 권한이 포함된 `blogger` 스코프만 지원하므로, 게시용 refresh token을 수집기에 복사하지 않는다.** Blogger 방문자는 GA4(읽기 전용)로 본다.
4. **데이터 지연**: AdSense는 어제까지 확정이고 최근은 추정치([문서](https://developers.google.com/adsense/management/metrics-dimensions)), Search Console은 며칠 지연된다. "지금 이 순간" 수치는 아니다.
5. **지표 정의 차이**: GA4의 사용자·세션·조회수, AdSense의 광고 페이지뷰, Blogger 조회수는 서로 다른 기준이라 숫자가 맞지 않는 게 정상이다. 대시보드에 지표 이름과 출처를 함께 표기한다.

## 5. 권고안 (단계)

### Phase A — 이번 주, 코드 없음 (사용자가 클릭으로)
1. **GA4 속성 1개**를 만들고 Blogger용 데이터 스트림부터 추가한다(Blogger 설정 → 측정 ID 입력). Chance_Blog용 스트림은 **§7-2 승인 후** 설치한다.
2. **Search Console**: Chance(`https://shine88pc.github.io/chanceblog/`)와 Blogger 속성을 확인한다.
3. **Looker Studio** 보고서 1장: ① 사이트별 방문자·페이지뷰 ② 인기 글 Top 10 ③ 검색 유입(클릭·노출) ④ AdSense 사이트별 수익(커넥터가 없으면 Apps Script로 시트에 적재 → Looker Studio가 시트를 읽음).
4. 블로그를 추가할 때 체크리스트: GA4 스트림 추가 → (Blogger면 측정 ID) → Search Console 속성 → 보고서 필터.

### Phase B — 필요해지면, AI가 구현
- **비공개 짝 저장소**(예: `blog-ops-private`)에 수집기를 둔다. 읽기 전용 토큰과 일별 스냅샷은 그곳에만 있다.
- 수집기: GA4 Data API(Blogger 방문자 포함) · Search Console API · AdSense API(모두 읽기 전용) → 블로그 공통 형식으로 정규화 → **주간 요약을 비공개 이슈(메일 알림)로** 발송, 트래픽 급락·수익 이상은 즉시 알림(워치독 연동).
- **성과 피드백**: "잘 읽히는 카테고리"만 비식별 가중치(예: `topic_weights.json`)로 공개 저장소의 주제 선정에 반영한다. 원시 수치는 공개하지 않는다.
- 레지스트리 확장안(구현 전): 블로그 항목에 선택 필드 `analytics: {ga4_hostname, search_console_site, adsense_domain}`을 추가하고 `scripts/validate_repo.py`가 형식을 검사한다.

### Phase C — API 없는 사이트
수동 입력 시트(주 1회 수치 붙여 넣기)를 같은 형식으로 병합한다. 사이트가 실제로 늘어날 때 정한다.

## 6. 우리 쪽에서 이미 가능한 것 (외부 연결 없이)
게시글 수·발행 추이는 저장소의 이력 파일로 계산된다. Phase B 이전에도 워치독 요약에 "블로그별 최근 7일 발행 수"를 넣을 수 있다(소규모 변경, 수치는 비공개 이슈로만).

## 7. 결정이 필요한 것

1. **Phase A를 진행할까요?** (사용자가 Looker Studio를 직접 구성, 저는 단계별 설정 안내를 드립니다.)
2. **Chance_Blog에 GA4를 설치할까요?** (T3: `<head>` 변경 + 개인정보처리방침 문구 추가 + AdSense 심사 중 변경. 설치하지 않으면 Chance의 방문자·인기 글은 Search Console 기준만 보입니다.)
3. 네이버 블로그 등 **API 없는 사이트를 쓸 계획**이 있나요? (있다면 수동 입력 방식을 수용할 수 있는지)
4. Phase B(자체 수집기 + 비공개 리포트)를 만들까요? (비공개 짝 저장소 생성과 Google Cloud API 사용 설정·읽기 전용 동의가 1회 필요)

## 8. 한계와 위험

- AdSense는 **승인 전에는 수익 데이터가 없다**(현재 심사 중).
- Looker Studio에 의존하면 구글이 커넥터·정책을 바꿀 때 보고서가 깨질 수 있다.
- 사이트별 수익을 글 단위로 쪼개는 것은 GA4–AdSense 연결에 달려 있고, 이번 조사에서는 확인하지 못했다.
- 네이버처럼 API가 없는 곳은 대시보드의 일부가 사람의 입력에 의존한다.
