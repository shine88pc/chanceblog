# 해외(미국 외) 소스 조사 — 2026-10-26

> **이 문서는 조사 기록이지 결정이 아닙니다.** 운영자 승인(2026-10-26 채팅 "13. 소스 추가", 그리고 "해외 사이트에서 미국 이외의 국가의 내용들도 확인이 가능하다면 진행")에 따라 지역별 조사 3건(유럽 / 영국·캐나다·아시아태평양 / 국제기구·개방지식)이 소스마다 **약관·robots.txt·피드를 직접 읽은** 결과를 한곳에 줄인 것입니다. 실제 적용 상태는 `generator.py`의 `NEWS_SOURCES`·`TRUSTED_SOURCE_DOMAINS`·`TERMS_BLOCKED_DOMAINS`와 `docs/DEFECT_REGISTER.md` D-61·D-62가 정본이고, 약관 해석은 법률 판단이 아닙니다.
>
> 확인 시각은 2026-10-26 03:17~03:59 UTC(한국 월요일 낮)입니다. **주말 직후라 "36시간 안" 건수는 평소보다 적고**, 건수는 피드마다 한 번씩만 받은 값입니다(사이트당 요청 6회 안팎, 차단·챌린지는 우회하지 않고 "접근 불가(미확인)"로 적음, 사내 프록시 경유). 약관 페이지에 개정일이 없는 곳이 많아 확인한 날짜를 `terms.checked`에 적었습니다 — 소스를 오래 쓰면 다시 읽어야 합니다.

## 1. 고른 기준

1. 약관이 **상업 이용과 재가공(각색)을 출처 표시·변경 표시 같은 조건으로 허용**한다(CC BY 계열·정부 공개 라이선스). 비상업(NC)·변경 금지(ND)·허가 필요·"광고 옆 링크 금지" 같은 문구가 있으면 뺀다.
2. robots.txt가 AI 크롤러를 이름으로 막지 않는다(운영자 원칙 2026-10-26 "AI 크롤러를 막는 사이트는 접근하지 않는다").
3. 영어 피드가 있고 우리 UA(`Mozilla/5.0 (compatible; ChanceBlogBot/2.0)`)로 HTTP 200이며 항목에 요약이 있다(없으면 기사 페이지 소개 문구로 보충 가능).
4. 계약·사용료가 필요 없다("무료 자동화 기반").
5. 채택한 소스에는 **AI 학습·텍스트 마이닝을 금지하는 조항이 없다**(허용한다고 쓴 곳도 없음 — "사용·재가공·상업 이용" 문언으로 판단). 그래도 아래 §5의 주의가 있다.

## 2. 채택 — `generator.py`에 구현함

| 소스 | 분야 | 피드 | 라이선스·조건 | 비고(처리) |
|------|------|------|----------------|-----------|
| EU 집행위원회 소식 | 사회·정책 | `https://commission.europa.eu/node/2/rss_en` | **CC BY 4.0** — 법적 고지(`https://commission.europa.eu/legal-notice_en`): "달리 표시하지 않은 한 … 적절한 출처 표시와 변경 사실 표시를 조건으로 재사용 허용". 사람이 나오는 자료·제3자 자료·로고·상표는 제외 | RSS 2.0, 30건(약 5주). 주 8건 안팎이고 30건 중 8건(약 1/4)이 국채 입찰 공지(요약 25~30자)라 제외. 선거·정치광고·`democracy` 분류도 제외(중립). 보도자료(Press Corner)는 자바스크립트 앱이라 RSS 여부와 법적 고지를 확인하지 못했음(Energy 피드 30건 중 9건이 이 호스트 링크 — 연설·성명·공동 선언 제목은 제외). robots.txt는 Drupal 기본(AI 크롤러 이름 없음) |
| 집행위원회 DG Energy | 경제·일 | `https://energy.ec.europa.eu/node/2/rss_en` | 같은 고지(바닥글이 연결) | 최근 7일 11건은 요약이 모두 100자 이상(30건 전체로는 2건이 93·97자). 링크 호스트가 energy.·ec.(보도자료·Eurostat 소식)·finance.·cinea.·eu-mayors.이고 **EIB·ACER 기사도 섞임**(집행위원회 자료가 아님 → 신뢰 목록 밖이라 탈락). Eurostat 소식은 Eurostat 자체 고지(출처 표기·면책 문구)가 따로 있어 제외 |
| 집행위원회 DG Environment | 과학·환경 | `https://environment.ec.europa.eu/node/92/rss_en` (`/node/2/rss_en`은 404) | 같은 고지 | 주 6건. Eurostat 소식(예: 포장재 쓰레기 통계) 제외 |
| 집행위원회 JRC(공동연구센터) | 과학·환경 | `https://joint-research-centre.ec.europa.eu/node/2/rss_en` | 같은 고지 | 주 2~3건, 요약의 약 1/3(30건 중 10건)이 100자 미만이라 기사 페이지 소개 문구로 보충. 국방·안보 분류 글 제외 |
| EU 디지털 전략(AI Act·디지털서비스법) | 기술·미래 | `https://digital-strategy.ec.europa.eu/en/rss.xml` | CC BY 4.0 — 이 사이트의 법적 고지(`…/en/pages/legal-notice`)가 출처 표시를 "작품 제목·유럽연합 귀속·원문 주소"로 안내 | 10건(약 5주), 주 2건. 요약 앞에 "Anonymous (not verified) 날짜" 잡음. robots.txt가 `/*?`·`/node/*`·`/taxonomy/*`를 막지만 `/en/rss.xml`·`/en/news/<슬러그>`는 허용 |
| 캐나다 통계청 The Daily | 경제·일 / 사회·정책 / 일상·마음(소스 3개) | `https://www150.statcan.gc.ca/n1/rss/dai-quo/0-eng.atom` | **Statistics Canada Open Licence**(`…/en/terms-conditions/open-licence`): "sell" 포함 상업 이용과 재가공물(Value-added Products) 허용. 조건: 재가공물에 `Adapted from Statistics Canada, <상품명>, <기준일>. This does not constitute an endorsement by Statistics Canada of this product.`, 정보를 **정확히** 옮길 것, 보증 암시·오도 금지, 통계청 이름·로고·문장·기타 상징·도메인 이름과 캐나다 정부 공식 상징(Canada wordmark·국기 등)을 출처 표기 밖에서 서면 허가 없이 쓰지 말 것("Advertising and Publicity") | Atom 280건(100일), 평일 12:30 UTC에 4~6건. 피드 호스트(`www150.`)와 기사 호스트(`www.statcan.gc.ca`)가 다름. 제목·요약이 `type="xhtml"`이라 글자가 자식 요소 안에 있음(`parse_feed`가 읽도록 고침). 요약 100자 미만 약 21%. robots.txt: 피드 허용, Crawl-delay 2, AI 크롤러 이름 없음. 기술 공지·부문 물가지수·공급 처리표와 자살·약물 과다복용·성폭력·살인 주제는 제외 |

글 끝에는 소스마다 코드가 **인용 줄과 고지문**을 붙입니다(집행위원회 계열은 "제목·기관·날짜·원문 주소·© European Union·CC BY 4.0 링크"와 "AI 작성·원문에서 바뀐 부분 있음·집행위원회가 검토·보증하지 않음", 통계청은 약관의 `Adapted from …` 문구). 통계청 글은 인용 줄에 통계청 주소를 쓰지 않고, 본문의 원문 링크(엔진이 반드시 요구해 주소에 `statcan.gc.ca`가 들어감)는 글자를 설명 문구로 쓰고 주소를 글자로 보이지 않게 하라는 작성 지침과 수치를 그대로 쓰라는 지침을 더했습니다. 기사 페이지를 연달아 읽을 때는 사이트의 Crawl-delay(2초)만큼 기다립니다.

## 3. 후보로 남김 — 조건을 채우면 추가할 수 있음

| 소스 | 라이선스 | 지금 못 넣은 이유 / 넣으려면 |
|------|----------|------------------------------|
| **Horizon**(EU 연구혁신 매거진) | CC BY 4.0, "all our articles are free to republish" — ① 원 기자 이름(byline) ② 원문 링크 ③ 바닥글 "This article was originally published in Horizon, the EU Research and Innovation magazine." 필수, 번역 허용 | `parse_feed`가 기자 이름(`dc:creator`)을 아직 읽지 않아 보류(그래서 DG Environment 피드에 섞여 드는 Horizon 기사 링크 `…/en/horizon-magazine/…`는 집행위원회 계열 소스의 `exclude_link`로 뺀다). 주 2건, 편집 품질이 가장 좋고 요약 전부 100자 이상. `https://projects.research-and-innovation.ec.europa.eu/en/horizon-magazine/articles.xml`(분야별 16개 피드: health 등) |
| **ECDC**(유럽질병예방통제센터) | CC BY 4.0 + ECDC를 만든 이로 표기·라이선스 링크·변경 표시 3조건 | 감염병·보건 글은 의료 조언 위험(YMYL)이라 건강 주제 가드레일을 정한 뒤. `https://www.ecdc.europa.eu/en/taxonomy/term/1307/feed` 주 3~4건 |
| **GOV.UK**(영국 정부) — **사용 결정(2026-10-26 사용자 "AI 학습을 위한 목적이 아니기에 문제가 없을 것으로 보여져")**, 후속 PR로 추가 | OGL v3.0 — "Contains public sector information licensed under the Open Government Licence v3.0." (+ 라이선스 링크) | Atom `https://www.gov.uk/search/news-and-communications.atom?organisations[]=<부처 슬러그>`(부처 조합별). **추가할 피드**: DESNZ+Defra(에너지·환경·식품·농촌, 주 10건, 과학·환경 분야)와 DSIT+AI Security Institute(기술 분야, 14일에 1건뿐이지만 AI 소식). **뺄 피드**: 재무부·DWP·DBT 경제 피드(20건 중 총리·장관·재무장관 발표와 연설이 대부분이라 정치 중립 원칙과 맞지 않음). Atom `updated`는 마지막 수정 시각(새 글이 아닐 수 있음). robots.txt는 AI 학습 크롤러 `meta-externalagent`를 검색 경로 `/search/all*`에만 막고(성능 이유 주석) 우리가 읽는 피드 경로는 막지 않는다 — 사용자가 이용 목적이 학습이 아니라는 이유로 문제가 없다고 판단 |
| 영국 의회 Commons·Lords Library·POST | Open Parliament Licence v3.0 | 영국 정치 위주, 주 0~10건 |
| NCSC(영국 사이버보안센터) | OGL v3.0 | 주 2~4건, CVE 정확성 문제 |
| ONS(영국 통계청) | OGL v3.0 + 공정 이용 정책: UA가 운영자 이름과 연락처(주소)를 밝혀야 함 | 현재 UA에 주소가 없음 |
| 네덜란드 통계청(CBS) | CC BY 4.0, 보증 암시 금지 | 피드에 요약이 없고(기사 페이지 소개 문구 210자 확인) 파피아멘토어 중복이 약 20%. `https://www.cbs.nl/en-gb/rss-feeds/all-news-items` |
| 노르웨이 통계청(SSB) | CC BY 4.0 | 피드에 3일치뿐, 데이터셋형 제목 |
| 스웨덴 통계청(SCB)·독일 Destatis | CC BY 4.0 / 자체 고지(상업 재이용 허용, 출처·변경 표시) | 스웨덴어·독일어. SCB는 "가공하면 통계청을 출처로 쓸 수 없다"는 문구가 모호. Destatis는 robots.txt의 `Disallow`가 `Allow`보다 앞에 있어 파이썬 `urllib.robotparser`가 막힌 것으로 오판(RFC 9309 기준으로는 허용) |
| ECB(유럽중앙은행) | "자유 이용, ECB를 출처로 밝힐 것, 수정한 정보는 명시" | 연설·인터뷰 위주(15건 중 12건), 요약 없음, 문구가 느슨 |
| 캐나다 중앙은행 | 자체 약관(자유 이용·출처·변경 표시) | 주 1건, '상업·재가공' 문구가 명시되지 않음 |
| Taiwan Today(대만 외교부) | 정부 공개 데이터 이용 허가 v1.0(OGDL): "any purpose, including … Derivative Works" | 근거가 data.gov.tw 카탈로그(사이트 자체엔 © 문구뿐), pubDate가 날짜만, 기사 전문 제공. 포털 피드는 링크 호스트가 4곳 |
| 360info(호주 대학 연구 해설) | CC BY 4.0 | 주 2~3건, 발행이 몰림 |
| Our World in Data·eLife·Frontiers·SciDev.Net | CC BY 계열(조건부) | OWID는 "수정 금지" 문구를 먼저 문의해야 함(licensing 주소), eLife·Frontiers는 논문 초록 중심에 날짜만 있는 시각, SciDev는 CC BY 2.0/3.0 버전 충돌·저빈도 |
| WIPO·Copernicus ACP(CC BY 4.0) | CC BY 4.0 | 저빈도, ACP 항목 링크가 `doi.org`(너무 넓은 해석기)라 신뢰 목록에 넣기 곤란 |
| ESO(유럽남방천문대) | CC BY 4.0 + "AI로 수정했다면 분명히 밝힐 것" | 월 1~2건과 주 1건 사진 해설이라 너무 드묾 |

## 4. 제외와 이유

- **약관상 상업 이용·재가공을 허용하지 않거나 허가·알림이 필요**: BIS(비상업), UNEP·UNDP·ITU·WMO·ESA(개인·비상업, 파생물 불가), UNCTAD(알림 필요), WHO·FAO(비상업·CC BY-NC-SA), World Bank(비상업, 파생물 불가), 영국 BoE(상업 재이용 금지)·UKRI(CC BY-NC-SA)·NICE("AI purposes … not covered")·Met Office(RSS 수정 금지), 캐나다 Canada.ca 부처들(상업 재배포는 사전 허가), 호주 CSIRO·BoM(상업 금지·스크레이핑 금지), 싱가포르 MAS·IMDA, 일본 AIST·JST(RSS 비상업·무수정)·JAXA·RIKEN·BoJ, 독일 DLR(이미지 CC BY-NC-ND), 프랑스 CNIL(CC BY-ND), The Conversation(CC BY-ND), 유럽의회("전체를 그대로 재생산"할 때만), EFSA("광고 옆에 링크 표시 금지"·상업·재가공 문구 없음), ENISA(출처 표시만, 피드 못 찾음), CERN(텍스트 라이선스 없음, 피드 404).
- **운영자 결정으로 제외**: Global Voices(CC BY 3.0, 공급은 가장 좋았음 — 일 3건. 이 단체의 자체 "AI 정책"(2026-09-09)이 AI가 쓴 글을 받지 않는다고 밝혀 재사용 제한은 아니지만 평판·항의 위험이 있어 사용자가 2026-10-26 채팅에서 "제외해줘").
- **robots.txt가 AI 크롤러를 이름으로 막음**: UNESCO·UNEP·WHO(CCBot 등)·The Conversation(`Disallow: /` 그룹 167개, 그중 AI 관련 38개 이상)·아일랜드 정부 gov.ie(ClaudeBot·GPTBot 등 `Disallow: /`)·climate.copernicus.eu(`meta-externalagent` 전체 차단 + 라이선스 미확인). (Ars Technica·IEEE는 앞선 결정으로 제외.)
- **라이선스는 허용이지만 쓸 피드가 없음**: Eurostat(서술형 피드는 robots.txt가 막고 열린 피드는 데이터셋 코드 갱신뿐), EEA(`Disallow: /*/rss.xml`), CORDIS(공개 피드 주소 없음), INSEE(RSS 목록이 JS로 생성), 덴마크 통계(피드 못 찾음, robots.txt에 GPTBot 이름), 호주 ABS·뉴질랜드 Stats NZ·아일랜드 CSO(CC BY 4.0이나 피드 없음), 영국 ICO(RSS 중단)·FSA(옛 사이트 폐쇄)·NHS(뉴스 피드 미확인), 일본 METI(영문 Atom이 2026-06-19에 멈춤)·MOF(제목만), OECD·ILO(약관은 허용이나 피드 없음; ILO robots는 `ai-train=no` 신호), Wikinews(피드 폐지·robots.txt가 피드 경로를 막음), Copernicus.eu(사이트 보관, 피드 2026-04-23 이후 정지).
- **접근 불가(미확인)**: 호주 RBA·뉴질랜드 RBNZ·영국 Ofcom(403), 뉴질랜드 Beehive(Imperva 챌린지), canada.ca·health.gov.au(시간 초과), IMF·IEA(403), Eurofound(Vercel 429), 유럽연합 이사회(Cloudflare 403 — 피드만 응답), 핀란드 통계(502), MDPI(우리 UA로 403, 브라우저 UA는 200).
- **불명확**: 인도 PIB(우리 UA로 403, 힌디 피드에 날짜·요약 없음, "정확히 재생산"만 허용), SingStat("adapt/translate 금지"와 "derive 허용"이 충돌, RSS 없음).

## 5. 확인하지 못한 것과 주의

- 조사는 피드마다 **한 번만** 받았고 건수는 월요일 낮 스냅샷입니다. 평일 낮에는 더 좋아 보이는 소스가 있고(eLife·Frontiers·ACP·360info처럼 평일 발행) 주말에는 공공기관 발표가 적어 72시간 신선도 창으로도 분야가 빌 수 있습니다.
- **엔진은 robots.txt를 실행 중에 읽지 않습니다.** 소스를 더할 때 사람이 읽어야 하고, 파이썬 `urllib.robotparser`는 와일드카드·최장 일치를 처리하지 못해 Eurostat·EEA를 허용으로, Destatis를 차단으로 잘못 판정합니다(RFC 9309 기준으로 직접 판단).
- 집행위원회 계열은 사이트별 법적 고지 쪽을 일일이 읽지 않고 바닥글이 같은 고지(`commission.europa.eu/legal-notice_en`)로 연결되는 것만 확인했습니다. 개별 항목이 따로 저작권 표시를 달 수 있다고 고지가 말하므로 **글만 쓰고 이미지는 쓰지 않습니다**(대표 이미지는 Unsplash가 따로 채움).
- 짧은 요약만으로 글을 쓰므로 **얇은 재작성**이 되기 쉽습니다. 광고 심사 중이라 원문 요약을 넘는 설명·맥락을 더하고 출처 상자를 보이게 두는 것이 필요합니다(편집 템플릿과 작성 지침이 이미 요구).
- 기사 페이지 소개 문구로 짧은 요약을 보충하는 경로(`_fetch_source_excerpt`)는 **거의 효과가 없습니다**: 코드 검증이 JRC 2건(피드 67·77자)과 통계청 1건(79자)에서 확인했는데 페이지의 meta description이 피드 요약과 똑같아 여전히 100자 미만(`SHORT_SUMMARY`)으로 버려졌습니다(JRC 약 1/3, 통계청 약 21%가 영향). 그래도 요청은 소스당 실행당 최대 5회 소비합니다.
- 통계청 월별 반복 발표(Retail trade·소비자물가·고용 등)는 제목이 이전 달 글과 매우 비슷해(유사도 0.82~0.95, 임계 0.6) **중복(`DUPLICATE`)으로 막힐 수 있어** 통계청 경제 소스가 실제로 내는 새 글감은 주 1건 남짓으로 보는 것이 맞습니다(100일 모의: 주제어 통과 63건 중 새로 쓸 수 있는 것 19건).
- 집행위원회 피드의 `pubDate`는 최종 수정 시각일 수 있어 링크의 날짜와 2일 이상 차이나는 항목이 101건 중 19건(최대 34일)입니다. 72시간 신선도 판정과 인용 줄의 날짜가 실제 첫 발행일과 다를 수 있습니다.
- `ec.europa.eu`를 과학·경제·사회·기술에서 통째로 신뢰하는 것은, 바닥글이 같은 법적 고지로 연결됨을 직접 확인한 하위 사이트(energy·environment·joint-research-centre·cinea·finance·eu-mayors)와 보도자료 경로가 대부분이기 때문입니다. 확인하지 못한 하위 사이트(예: `research-and-innovation`, Press Corner의 법적 고지)와 Horizon 매거진은 제목·링크 제외 규칙으로 줄였지만, 새 하위 사이트 항목이 피드에 섞이면 같은 신뢰로 통과할 수 있어 병합 뒤 첫 글들을 눈으로 봅니다.
- **집행위원회 재사용 결정**(Commission Decision 2011/833/EU)의 본문은 EUR-Lex가 자동 접속을 막아(AWS 챌린지) 읽지 못했습니다. 법적 고지가 이 결정을 근거로 든다고 하므로 "원래 의미를 왜곡하지 말 것" 같은 조건이 더 붙을 수 있어 작성 지침에 "원문의 의미를 왜곡하지 말 것"을 넣었습니다. 사람이 브라우저로 읽어 확인하는 것이 안전합니다.
- 인용 줄의 날짜는 피드의 게시·갱신 시각이라 원문 페이지 날짜와 하루쯤 다를 수 있고, 저작권 표시 `© European Union`에는 피드·사이트가 쓰는 연도 범위(1995-2026)를 붙이지 않았습니다(경미).
- 엔진은 요청 사이에 기다리지 않습니다. 통계청만 `page_delay`(2초)로 기사 페이지를 연달아 읽을 때 Crawl-delay를 지키고, 분야 대체 때 같은 통계청 피드(204KB)를 최대 3번 받을 수 있습니다(하루 두 번 실행).
- AI 학습·텍스트 마이닝 신호(`/.well-known/tdmrep.json`, 페이지 `tdm-reservation` 메타)는 요청하지 않았습니다(저장된 응답 헤더·HTML에서는 `Content-Signal`·`X-Robots-Tag`·`noai`가 보이지 않음).
- 조사 노트 원문(약관 인용·요청 기록)은 작업 세션의 임시 폴더에 있었고 이 문서가 그 요약입니다. 채택 소스는 `NEWS_SOURCES`의 `terms.url`에서 근거 쪽을 다시 열 수 있습니다.
