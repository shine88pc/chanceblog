# 붙여 쓸 `NEWS_SOURCES` 뼈대 초안 (k) — 2026-11-04

> **2026-11-05 갱신 — 이 초안 가운데 6곳(§1 FTC 보도자료·§3 FEDS Notes·§5 집행위 R&I·EMPL·§6 영국 CMA·§7 NSF)은 R-119 A(기본값 — 답이 없으면 기본값으로 진행하고 병합이 곧 승인)에 따라 구현했다**(현재 `generator.py` 구조에 맞춰 옮겨 쓰고 일부 규칙은 실제 피드 표본을 보고 고쳤다 — `docs/DEFECT_REGISTER.md` D-88, `generator.py` 의 `_FTC_*`·`_FEDS_*`·`_NSF_*`·`_CMA_*`). 나머지 항목은 아래 설명 그대로 적용 전 초안이다.
>
> **저장소에 적용하지 않은 초안입니다.** 운영자가 번호 요청으로 승인하면 구현합니다(새 소스·정책 = T3, `generator.py` 로직 = T2 — `docs/CHARTER.md` §5). 근거와 수치는 `S\k_sources_report.md` 에 있습니다(`S` = 작업 폴더). 약관 문구는 의역했고, 원문에서 가져온 것은 기관이 정한 출처 표시 형식 몇 단어뿐입니다. `checked` 는 2026-11-04 입니다.
>
> 구조 메모: 아래 코드 블록은 각각 **독립 실행되는 파이썬**이라 `generator.py` 의 `_EC_*`·`_GOVUK_*`·`HEALTH_RULE`·`_CC_BY` 정의 뒤, `NEWS_SOURCES = [` 앞에 상수를 두고 `NEW_SOURCES_*` 리스트의 항목을 `NEWS_SOURCES` 에 옮겨 붙이면 됩니다. 시험(`tests/test_generator_slots.py::SourceListTest`)은 ① 소스 이름·분야·피드 주소 사전이 고정돼 있어 항목을 더할 때 그 사전을 같이 고쳐야 하고 ② 모든 `allowed`·`pending` 소스에 `checked`(날짜)·`terms.url`(https)·`notice`(ko·en)를 요구하며 ③ 피드 호스트가 그 분야의 신뢰 목록에 있어야 하고 ④ 정규식이 컴파일돼야 하고 ⑤ 인용 틀이 `{title}`·`{date}`·`{url}` 만 쓰고 채워지는지 봅니다. 아래는 이 조건을 맞춘 형태입니다.

---

## 0. 신뢰 도메인 추가 (`TRUSTED_SOURCE_DOMAINS`)

```python
# 분야별로 더할 도메인(기존 항목은 그대로). 새 소스의 피드·기사 호스트가 여기에 없으면 UNTRUSTED/HOST_MISMATCH 로 전부 떨어진다.
TRUST_ADDITIONS = {
    "economy":    ("ftc.gov", "dol.gov", "mods.go.kr", "cedefop.europa.eu", "www.gov.uk"),   # www.gov.uk 는 GOV.UK CMA(§6)를 경제로 쓸 때만
    "society":    ("dol.gov", "mods.go.kr", "cedefop.europa.eu"),
    "daily_life": ("ftc.gov", "fda.gov", "ecdc.europa.eu", "mods.go.kr"),
    "technology": ("nsf.gov",),
}
# 이미 있어서 더할 필요 없는 것: federalreserve.gov(경제), ec.europa.eu(경제·사회·기술 — 일상·마음에는 없음), nist.gov(기술),
#   kostat.go.kr·mfds.go.kr·korea.kr(국가데이터처의 새 도메인은 mods.go.kr 이라 별도 추가).
```

## 1. FTC — 보도자료(경제·일) + 소비자 경고(일상·마음)

약관: `https://www.ftc.gov/policy-notices/website-policy` — 대부분 공공영역, 출처 표시 권장(형식 예: "Source: United States Federal Trade Commission, www.ftc.gov"), FTC 보증·제휴를 암시 금지, 제3자 저작물 제외. robots 통과(Crawl-delay 5초/소비자 사이트 10초). 소비자 경고 피드는 날짜 형식 때문에 **`_parse_date` 변경(§12 ①)이 먼저 필요**합니다.

```python
_FTC_TERMS = {"status": "allowed", "checked": "2026-11-04", "url": "https://www.ftc.gov/policy-notices/website-policy"}
_FTC_CITATION = "“{title}.” Source: United States Federal Trade Commission, www.ftc.gov, {date} <{url}>"
_FTC_NOTICE = {
    "ko": "이 글은 AI 도구가 미국 연방거래위원회(FTC)가 공개한 자료를 요약·재구성해 작성했습니다. FTC는 이 글을 검토하거나 보증하지 않았으며, 이 글은 FTC의 공식 입장이나 공식 문서가 아닙니다.",
    "en": "This article was written with an AI tool by summarising and restructuring material published by the U.S. Federal Trade Commission. The FTC has not reviewed or endorsed it, and it is not an official FTC publication or position."}
_FTC_PROMPT_RULE = ("FTC가 제기한 소송·조치와 업체의 해명·합의를 구분하세요. 법원이 확정하기 전의 내용은 'FTC는 …라고 주장했다'(영어 글은 'the FTC alleges')처럼 주장으로 쓰고, "
                    "특정 업체나 사람을 단정적으로 비난하지 마세요. 독자에게 법률·금융 조언을 하지 말고, FTC가 이 글을 검토·보증했거나 FTC의 공식 입장인 것처럼 쓰지 마세요. "
                    "요약 앞머리의 'By BCP Staff'는 글쓴이 표기이니 글에 쓰지 마세요.")
# 독자 글감이 못 되는 공지: 의견 모집·기한 연장·정책 철회·위원 성명·최종 명령 승인·연도별 수수료 안내
_FTC_EXCLUDE_TITLE = (r"\b(?:extends?|seeks?) (?:the )?(?:public )?comments?\b|\bwithdraws?\b|\bcommissioner\b|\bchairman\b"
                      r"|\bstatement (?:from|by|of|on)\b|\bapproves? final\b|\bannounces? 20\d\d\b.*\bfees\b")

NEW_SOURCES_FTC = [
    {"name": "FTC · press (consumer protection)", "display_name": "Federal Trade Commission", "lane": "economy",
     "url": "https://www.ftc.gov/feeds/press-release-consumer-protection.xml",
     "terms": _FTC_TERMS, "exclude_title": _FTC_EXCLUDE_TITLE, "no_page_fetch": True,
     "citation": _FTC_CITATION, "notice": _FTC_NOTICE, "prompt_rule": _FTC_PROMPT_RULE},
    {"name": "FTC · consumer alerts", "display_name": "Federal Trade Commission", "lane": "daily_life",
     "url": "https://consumer.ftc.gov/blog/gd-rss.xml",
     "terms": _FTC_TERMS, "no_page_fetch": True,
     "citation": _FTC_CITATION, "notice": _FTC_NOTICE, "prompt_rule": _FTC_PROMPT_RULE},
]
```
제안·관찰: 보도자료 요약이 전문(중앙 3,520자)이라 gfix 의 입력 상한(1,500~2,000자)과 "문장을 그대로 옮기지 말라" 지침을 함께 쓰세요. 소비자 경고(일상·마음)는 하루 0.24건이라 경제·일 소스와 한 피드에서 나눠 쓰지 않았습니다.

## 2. DOL 보도자료(경제·일 / 사회·정책) — 정치 톤 결정(Q2) 뒤에만

약관: `https://www.dol.gov/general/aboutdol/copyright` — 공공영역은 허락 없이 사용·복제·배포 가능, DOL 제휴·보증 암시 금지, 인장·로고·제3자 저작물 제외. robots 통과. **행정부 홍보 톤**이 섞여 이전 GOV.UK 재무·DWP·DBT 제외 결정과 같은 쟁점입니다.

```python
_DOL_TERMS = {"status": "allowed", "checked": "2026-11-04", "url": "https://www.dol.gov/general/aboutdol/copyright"}
_DOL_CITATION = "“{title}.” U.S. Department of Labor, {date} <{url}>"
_DOL_NOTICE = {
    "ko": "이 글은 AI 도구가 미국 노동부(U.S. Department of Labor)가 공개한 자료를 요약·재구성해 작성했습니다. 노동부는 이 글을 검토하거나 보증하지 않았으며, 이 글은 노동부의 공식 입장이나 공식 문서가 아닙니다.",
    "en": "This article was written with an AI tool by summarising and restructuring material published by the U.S. Department of Labor. The Department has not reviewed or endorsed it, and it is not an official Department publication or position."}
_DOL_PROMPT_RULE = ("미국 노동부(행정부)가 발표한 내용임을 분명히 하고 정부의 정책 주장·성과 홍보와 확인된 사실을 구분하세요. '큰 성과' 같은 보도자료의 홍보 표현은 옮기지 말고, 정당·선거·"
                    "장관 개인에 대한 평가는 쓰지 마세요. 위반 사실을 전할 때는 노동부가 확인한 내용·합의·법원 결정을 구분하고 업체를 단정적으로 비난하지 마세요. "
                    "노동부가 이 글을 검토·보증했거나 공식 입장인 것처럼 쓰지 마세요.")
# 적발·벌금 제안(주장), 인사·지명, 성명, 정치·군사 소재는 글감에서 뺀다
_DOL_EXCLUDE_TITLE = (r"\bcites?\b|\bciting\b|\bproposed penalties\b|\bappoints?\b|\bnominat|\bstatement (?:from|by|of)\b|\bjoint statement\b"
                      r"|\bcondolences\b|\belections?\b|\bpolitical\b|\bmilitary\b|\bsanctions?\b|\bsecretary\b.*\b(?:remarks|visits?|travels?)\b")
_DOL_ECONOMY = (r"unemployment|jobless|claims|wage|overtime|back wages|jobs?\b|employment|apprentice|retirement|pension|benefits?|workforce|labor market|productivity|trade")
_DOL_SOCIETY = (r"apprentice|workforce|job training|worker|wage|overtime|union|retirement|pension|benefits?|unemployment|safety|mine|child labor|disabilit|veteran|older workers|skills|paid leave")

NEW_SOURCES_DOL = [
    {"name": "U.S. Department of Labor · economy", "display_name": "U.S. Department of Labor", "lane": "economy",
     "url": "https://www.dol.gov/rss/releases.xml",
     "terms": _DOL_TERMS, "exclude_title": _DOL_EXCLUDE_TITLE, "topic_regex": _DOL_ECONOMY, "no_page_fetch": True,
     "citation": _DOL_CITATION, "notice": _DOL_NOTICE, "prompt_rule": _DOL_PROMPT_RULE},
    {"name": "U.S. Department of Labor · society", "display_name": "U.S. Department of Labor", "lane": "society",
     "url": "https://www.dol.gov/rss/releases.xml",
     "terms": _DOL_TERMS, "exclude_title": _DOL_EXCLUDE_TITLE, "topic_regex": _DOL_SOCIETY, "no_page_fetch": True,
     "citation": _DOL_CITATION, "notice": _DOL_NOTICE, "prompt_rule": _DOL_PROMPT_RULE},
]
```

## 3. 연준 FEDS Notes(경제·일)

기존 `Federal Reserve` 소스와 같은 약관 근거(`disclaimer.htm`, 이번에 다시 읽음: 별도 표시가 없으면 이사회 사이트 정보는 공공영역이라 허락 없이 복사·배포 가능, 인장·로고·제3자 저작물 제외). robots.txt 는 404(규칙 없음).

```python
_FED_TERMS = {"status": "allowed", "checked": "2026-11-04", "url": "https://www.federalreserve.gov/disclaimer.htm"}
_FEDS_NOTICE = {
    "ko": "이 글은 AI 도구가 미국 연방준비제도 이사회 연구진이 공개한 FEDS Notes를 참고해 작성했습니다. 노트의 분석과 결론은 저자의 것이며 연준이나 이사회의 공식 입장이 아니고, 이사회는 이 글을 검토하거나 승인하지 않았습니다.",
    "en": "This article was written with an AI tool using FEDS Notes published by staff of the Federal Reserve Board. The analysis and conclusions are the authors' own and do not represent the Board or the Federal Reserve; the Board has not reviewed or approved this article."}
_FEDS_PROMPT_RULE = ("FEDS Notes는 연구진의 분석이라 연준이나 이사회의 입장·결정으로 쓰지 마세요. 분석에 쓴 자료·가정·한계와 결과를 구분하고, 요약에 없는 수치·기간은 만들지 마세요. "
                     "독자에게 투자 조언을 하지 마세요.")

NEW_SOURCES_FEDS = [
    {"name": "Federal Reserve · FEDS Notes", "display_name": "Federal Reserve Board", "lane": "economy",
     "url": "https://www.federalreserve.gov/feeds/feds_notes.xml",
     "terms": _FED_TERMS, "no_page_fetch": True,
     "notice": _FEDS_NOTICE, "prompt_rule": _FEDS_PROMPT_RULE},
]
```

## 4. ECDC(일상·마음, 공중보건)

약관: `https://www.ecdc.europa.eu/en/ecdc-intellectual-property-notices` — 별도 표시가 없으면 CC BY 4.0(상업·가공 가능), 조건 3가지: ECDC 를 만든 이로 밝힘, CC BY 4.0 링크, 바꾼 곳 표시. 제3자 저작물 제외. robots 통과. **건강 가드레일 필수**(`HEALTH_RULE`).

```python
_CC_BY = "https://creativecommons.org/licenses/by/4.0/"   # generator.py 에 이미 있는 상수(시험용으로 다시 적음)
HEALTH_RULE = "건강·의료 정보는 정책과 통계 사실만 전하고 진단·치료·복용·예방 효과를 조언하지 마세요."   # generator.py 에 이미 있는 상수

_ECDC_TERMS = {"status": "allowed", "checked": "2026-11-04", "url": "https://www.ecdc.europa.eu/en/ecdc-intellectual-property-notices"}
_ECDC_CITATION = ("“{title}.” © European Centre for Disease Prevention and Control (ECDC), {date} <{url}>. "
                  "Licensed under CC BY 4.0 (" + _CC_BY + "); changes were made.")
_ECDC_NOTICE = {
    "ko": "이 글은 AI 도구가 유럽질병예방통제센터(ECDC)가 공개한 자료를 요약·재구성해 작성했으며 원문에서 바뀐 부분이 있습니다. 원문은 CC BY 4.0 라이선스(" + _CC_BY + "deed.ko)로 제공됩니다. "
          "ECDC는 이 글을 검토하거나 보증하지 않았으며, 이 글은 ECDC의 공식 권고가 아닙니다.",
    "en": "This article was written with an AI tool by summarising and restructuring material published by the European Centre for Disease Prevention and Control (ECDC); changes were made to the original. "
          "The original is licensed under CC BY 4.0 (" + _CC_BY + "). ECDC has not reviewed or endorsed this article, and it is not ECDC guidance."}
_ECDC_PROMPT_RULE = ("ECDC가 발표한 위험 평가·감시 결과와 일반 상식을 구분하세요. " + HEALTH_RULE
                     + " 감염병 발생 소식은 개인 행동 지침처럼 쓰지 말고 기관이 밝힌 사실과 권고 범위만 전하며, ECDC가 이 글을 검토·보증했다고 쓰지 마세요.")
# 정기 감시 보고·상황 갱신·공고류는 글감이 못 된다
_ECDC_EXCLUDE_TITLE = (r"\bcommunicable disease threats report\b|\bweekly\b.*\b(?:threats?|surveillance)\b|\bepidemiological update\b|\bsituation update\b"
                       r"|\bcall for\b|\bvacanc|\btender\b|\bwebinar\b")

NEW_SOURCES_ECDC = [
    {"name": "ECDC", "display_name": "European Centre for Disease Prevention and Control (ECDC)", "lane": "daily_life",
     "url": "https://www.ecdc.europa.eu/en/taxonomy/term/1307/feed",
     "terms": _ECDC_TERMS, "exclude_title": _ECDC_EXCLUDE_TITLE, "no_page_fetch": True,
     "citation": _ECDC_CITATION, "notice": _ECDC_NOTICE, "prompt_rule": _ECDC_PROMPT_RULE},
]
```

## 5. 집행위 R&I(기술·미래) · EMPL(사회·정책) · GROW·TAXUD·FISMA·AGRI·MOVE(경제·일)

집행위 법적 고지(`https://commission.europa.eu/legal-notice_en`, 이번에 다시 읽음 — 별도 표시가 없으면 EU 소유 콘텐츠는 CC BY 4.0, 출처·변경 표시, 제3자 저작물·로고 제외) 상수를 그대로 씁니다. 교통(MOVE)은 경제·일로 둡니다(경제 신뢰 목록에는 `ec.europa.eu` 가 있고 일상·마음에는 없음). 푸터 고지 링크는 R&I·EMPL·GROW 만 이번에 확인했고 TAXUD·FISMA·AGRI·MOVE 는 **확인 전**(Q10).

```python
_EC_TERMS = {"status": "allowed", "checked": "2026-10-26", "url": "https://commission.europa.eu/legal-notice_en"}      # generator.py 의 기존 상수(시험용)
_EC_NOTICE = {"ko": "…", "en": "…"}                                                                                   # 기존 상수(생략)
_EC_PROMPT_RULE = "…"                                                                                                 # 기존 상수(생략)
_EC_EXCLUDE_STATEMENTS = r"^(?:joint )?statements?\b|^speech(?:es)?\b|\bremarks\b"                                    # 기존 상수(줄임)
_EC_EXCLUDE_VISITS = r"^(?:(?:executive )?vice-president|commissioner) [\w’'-]+ (?:in|visits?|meets?)\b"              # 기존 상수(줄임)
_EC_EXCLUDE_APPLY = r"\bapply now\b|(?:^|[?:!.] )apply for\b"                                                         # 기존 상수
_EC_EXCLUDE_LINK = r"/eurostat/|/horizon-magazine/|/commission/presscorner/"                                          # 기존 상수


def _ec_citation(creator):                                                                                            # 기존 함수(시험용)
    return "“{title}.” " + creator + ", {date} <{url}>. © European Union, licensed under CC BY 4.0."


def _ec_dg(name, host, lane, creator, topic=None, extra_exclude=""):
    """집행위 DG 사이트 피드(`https://<호스트>/node/2/rss_en`)를 읽는 소스 항목. 약관·고지·지침은 기존 집행위 상수를 그대로 쓴다."""
    src = {"name": f"European Commission · {name}", "display_name": f"European Commission ({name})", "lane": lane,
           "url": f"https://{host}/node/2/rss_en", "terms": _EC_TERMS,
           "exclude_title": (_EC_EXCLUDE_STATEMENTS + "|" + _EC_EXCLUDE_VISITS + "|" + _EC_EXCLUDE_APPLY
                             + r"|\bcall for (?:applications|tenders|proposals|experts|feedback|evidence)\b|\bwebinar\b|\bpodcast\b" + extra_exclude),
           "exclude_link": _EC_EXCLUDE_LINK, "no_page_fetch": True,
           "citation": _ec_citation(creator), "notice": _EC_NOTICE, "prompt_rule": _EC_PROMPT_RULE}
    if topic:
        src["topic_regex"] = topic
    return src


_RTD_TOPIC = (r"artificial intelligence|\bAI\b|quantum|fusion|supercomput|semiconductor|\bchips?\b|robot|space|satellite|digital|\bdata\b|cyber|biotech|bioeconomy"
              r"|battery|hydrogen|photonic|innovation|open science|research infrastructure")

NEW_SOURCES_EC = [
    _ec_dg("R&I", "research-and-innovation.ec.europa.eu", "technology", "European Commission, DG Research and Innovation", topic=_RTD_TOPIC),
    _ec_dg("Employment & Social Affairs", "employment-social-affairs.ec.europa.eu", "society",
           "European Commission, DG Employment, Social Affairs and Inclusion"),
    _ec_dg("Single Market & Industry", "single-market-economy.ec.europa.eu", "economy",
           "European Commission, DG Internal Market, Industry, Entrepreneurship and SMEs"),
    _ec_dg("Taxation & Customs", "taxation-customs.ec.europa.eu", "economy",
           "European Commission, DG Taxation and Customs Union"),
    _ec_dg("Financial Services", "finance.ec.europa.eu", "economy",
           "European Commission, DG Financial Stability, Financial Services and Capital Markets Union", extra_exclude=r"|\bnewsletter\b"),
    _ec_dg("Agriculture", "agriculture.ec.europa.eu", "economy",
           "European Commission, DG Agriculture and Rural Development"),
    _ec_dg("Mobility & Transport", "transport.ec.europa.eu", "economy",
           "European Commission, DG Mobility and Transport", extra_exclude=r"|\bjoint press release\b"),
]
```
메모: ① 집행위 `pubDate` 는 최종 수정 시각일 수 있어 인용 줄의 날짜가 실제 첫 발행일과 다를 수 있습니다(이전 조사). ② 집행위 보건(`health.ec.europa.eu`)은 의료기기 지침 위주라 뺐고, ECFIN(`economy-finance…`)은 가장 새 항목이 2025-10-23 이라 뺐습니다. ③ 위 피드의 링크가 `ec.europa.eu/commission/presscorner/…` 로 가는 항목은 기존 제외 규칙이 거릅니다.

## 6. 영국 CMA (GOV.UK 방식 그대로, 경제·일)

GOV.UK 약관(OGL v3.0, 이번에 다시 읽음 — 대부분의 콘텐츠가 OGL, 조건에 맞게 복제 가능, 제휴·보증 암시 금지). 기존 상수 재사용. 경제 신뢰 목록에 `www.gov.uk` 추가 필요(§0).

```python
_GOVUK_FEED = "https://www.gov.uk/search/news-and-communications.atom?"                                              # 기존 상수(시험용)
_GOVUK_TERMS = {"status": "allowed", "checked": "2026-10-26", "url": "https://www.gov.uk/help/terms-conditions"}      # 기존 상수
_GOVUK_EXCLUDE_TITLE = r"\bappoints?\b|\bapply now\b"                                                                # 기존 상수(줄임)
_GOVUK_EXCLUDE_LINK = r"^(?!https://www\.gov\.uk/government/news/)"                                                  # 기존 상수
_GOVUK_CITATION = "“{title}.” GOV.UK, {date} <{url}>. Contains public sector information licensed under the Open Government Licence v3.0."   # 기존 상수(줄임)
_GOVUK_NOTICE = {"ko": "…", "en": "…"}                                                                                # 기존 상수
_GOVUK_PROMPT_RULE = "…"                                                                                              # 기존 상수

NEW_SOURCES_GOVUK = [
    {"name": "GOV.UK · Competition & Markets", "display_name": "GOV.UK", "lane": "economy",
     "url": _GOVUK_FEED + "organisations%5B%5D=competition-and-markets-authority",
     "terms": _GOVUK_TERMS, "exclude_title": _GOVUK_EXCLUDE_TITLE, "exclude_link": _GOVUK_EXCLUDE_LINK, "no_page_fetch": True,
     "citation": _GOVUK_CITATION, "notice": _GOVUK_NOTICE, "prompt_rule": _GOVUK_PROMPT_RULE},
]
```
메모: 보도 기사(`/government/news/`)만 쓰는 기존 규칙 때문에 CMA 의 공개 서한(`/government/publications/…`)은 제외됩니다. 요약이 짧은 편(중앙 116자, 20%가 100자 미만)이라 `SHORT_SUMMARY` 로 일부 떨어집니다.

## 7. 미 NSF · NIST (기술·미래)

NSF 약관: `https://www.nsf.gov/policies/digital` — 글은 정부 직원 저작물이라 자유 복사(출처 크레딧은 선택), **이미지·그래픽은 허가 필요(쓰지 않음)**. NIST 약관: `https://www.nist.gov/copyrights-disclaimers` — 표시된 저작물 외 공공 정보로 복사·배포 가능, 바이라인·크레딧 요청, 상품 보증 암시 금지. robots 통과(둘 다 AI 이름 없음).

```python
_NSF_TERMS = {"status": "allowed", "checked": "2026-11-04", "url": "https://www.nsf.gov/policies/digital"}
_NSF_CITATION = "“{title}.” Source: U.S. National Science Foundation, {date} <{url}>"
_NSF_NOTICE = {
    "ko": "이 글은 AI 도구가 미국 국립과학재단(NSF)이 공개한 자료를 요약·재구성해 작성했습니다. NSF는 이 글을 검토하거나 보증하지 않았으며, 이 글은 NSF의 공식 입장이 아닙니다. 사진·그래픽은 사용하지 않았습니다.",
    "en": "This article was written with an AI tool by summarising and restructuring material published by the U.S. National Science Foundation. NSF has not reviewed or endorsed it, and it is not an official NSF position. No NSF images or graphics are used."}
_NSF_PROMPT_RULE = ("NSF가 지원한 연구라고 해서 NSF가 결과를 보증하거나 이 글을 검토한 것처럼 쓰지 마세요. 연구자의 주장과 확인된 결과를 구분하고, 팟캐스트 소개 글이면 "
                    "요약에 없는 발언·수치를 만들지 마세요.")

_NIST_TERMS = {"status": "allowed", "checked": "2026-11-04", "url": "https://www.nist.gov/copyrights-disclaimers"}
_NIST_CITATION = "“{title}.” Credit: NIST, {date} <{url}>"
_NIST_NOTICE = {
    "ko": "이 글은 AI 도구가 미국 국립표준기술연구소(NIST)가 공개한 자료를 요약·재구성해 작성했습니다. NIST는 이 글을 검토하거나 보증하지 않았으며, 언급된 상품·서비스를 NIST가 추천하는 것은 아닙니다.",
    "en": "This article was written with an AI tool by summarising and restructuring material published by the U.S. National Institute of Standards and Technology (NIST). NIST has not reviewed or endorsed it, and any commercial product mentioned is not recommended by NIST."}
_NIST_PROMPT_RULE = ("NIST의 지침·표준·보고서는 연방 기관이나 일반 조직을 위한 권고이며 법적 의무가 아닐 수 있음을 구분하세요. NIST가 이 글을 검토·보증했거나 특정 상품을 "
                     "추천한 것처럼 쓰지 마세요.")

NEW_SOURCES_TECH = [
    {"name": "NSF news", "display_name": "U.S. National Science Foundation", "lane": "technology",
     "url": "https://www.nsf.gov/rss/rss_www_news.xml",
     "terms": _NSF_TERMS, "no_page_fetch": True,
     "citation": _NSF_CITATION, "notice": _NSF_NOTICE, "prompt_rule": _NSF_PROMPT_RULE},
    {"name": "NIST news", "display_name": "NIST", "lane": "technology",
     "url": "https://www.nist.gov/news-events/news/rss.xml",
     "terms": _NIST_TERMS, "no_page_fetch": True,
     "citation": _NIST_CITATION, "notice": _NIST_NOTICE, "prompt_rule": _NIST_PROMPT_RULE},
]
```

## 8. FDA 소비자·보도자료(일상·마음)

약관: `https://www.fda.gov/about-fda/about-website/website-policies` — 별도 표시가 없으면 글·그림 모두 저작권 없음, 허락 없이 재게시 가능. robots 통과이나 **Crawl-delay 30초**(한 실행에서 FDA 피드를 두 번 읽지 않게, 기사 페이지는 읽지 않음). 신약 승인 중심의 보도자료는 일상·마음에 약하므로 승인·허가 소식을 제외합니다.

```python
HEALTH_RULE = "건강·의료 정보는 정책과 통계 사실만 전하고 진단·치료·복용·예방 효과를 조언하지 마세요."   # generator.py 의 기존 상수(시험용)
_FDA_TERMS = {"status": "allowed", "checked": "2026-11-04", "url": "https://www.fda.gov/about-fda/about-website/website-policies"}
_FDA_CITATION = "“{title}.” Source: U.S. Food and Drug Administration, {date} <{url}>"
_FDA_NOTICE = {
    "ko": "이 글은 AI 도구가 미국 식품의약국(FDA)이 공개한 자료를 요약·재구성해 작성했습니다. FDA는 이 글을 검토하거나 보증하지 않았으며, 이 글은 의학적 조언이 아닙니다.",
    "en": "This article was written with an AI tool by summarising and restructuring material published by the U.S. Food and Drug Administration. The FDA has not reviewed or endorsed it, and it is not medical advice."}
_FDA_PROMPT_RULE = (HEALTH_RULE + " FDA의 승인·허가·경고·지침 사실만 전하고, 치료 효과를 약속하거나 복용·사용을 권하는 표현은 쓰지 마세요. "
                    "FDA가 이 글을 검토·보증한 것처럼 쓰지 마세요.")
# 신약·치료제 승인 소식과 자문위원회 안내는 일상 글감이 못 된다
_FDA_EXCLUDE_TITLE = r"\bapproves?\b|\bgrants? (?:accelerated )?approval\b|\bclears?\b|\badvisory committees?\b"

NEW_SOURCES_FDA = [
    {"name": "FDA · consumer updates", "display_name": "U.S. Food and Drug Administration", "lane": "daily_life",
     "url": "https://www.fda.gov/about-fda/contact-fda/stay-informed/rss-feeds/consumers/rss.xml",
     "terms": _FDA_TERMS, "no_page_fetch": True,
     "citation": _FDA_CITATION, "notice": _FDA_NOTICE, "prompt_rule": _FDA_PROMPT_RULE},
    {"name": "FDA · press announcements", "display_name": "U.S. Food and Drug Administration", "lane": "daily_life",
     "url": "https://www.fda.gov/about-fda/contact-fda/stay-informed/rss-feeds/press-releases/rss.xml",
     "terms": _FDA_TERMS, "exclude_title": _FDA_EXCLUDE_TITLE, "no_page_fetch": True,
     "citation": _FDA_CITATION, "notice": _FDA_NOTICE, "prompt_rule": _FDA_PROMPT_RULE},
]
```

## 9. 국가데이터처(구 통계청) 보도자료 — 한국어, 세 분야 분할, **`pending` 으로 시작**

약관: `https://www.mods.go.kr/menu.es?mid=a10706000000`(저작권정책) — 공공누리가 붙은 저작물은 허락 없이 이용 가능. 1유형=출처표시만으로 상업 이용·변경 허용, 2유형 상업 금지, 3유형 변경 금지, 4유형 둘 다 금지. 모든 유형에서 **출처(발행연도·기관 이름과 홈페이지·작성자)** 표시. 공공누리가 안 붙은 자료는 사전 협의. **보도자료 항목에 실제 붙는 유형을 확인하기 전에는 `allowed` 로 바꾸지 마세요(Q1).** robots 통과(AI 이름 없음). 피드 항목: 날짜 `YYYYMMDDHHMM`, 링크 호스트 `mods.go.kr`.

```python
_MODS_FEED = "https://www.mods.go.kr/board.es?mid=a10301010000&bid=a103010100&act=rss"
_MODS_TERMS = {"status": "pending", "checked": "2026-11-04", "url": "https://www.mods.go.kr/menu.es?mid=a10706000000",
               "blocker": "보도자료 항목 페이지의 공공누리 유형(1유형인지)과 영문 기관명을 사람이 확인해야 한다(저작권정책: 공공누리가 없는 자료는 담당자와 사전 협의)"}
# 한국어 출처 문구를 글 언어별로 나누는 생성기 변경(§12 ②) 전에는 이중 언어 한 줄을 쓴다. 공공누리 1유형이 요구하는 발행연도·기관명·주소가 들어 있다.
_MODS_CITATION = ("출처: 국가데이터처, 「{title}」, {date}, <{url}> (공공누리 제1유형) · "
                  "Source: Ministry of Data and Statistics (Korea), “{title}”, {date}, <{url}> (KOGL Type 1)")
_MODS_NOTICE = {
    "ko": "이 글은 AI 도구가 국가데이터처가 공공누리 제1유형으로 개방한 보도자료를 요약·재구성해 작성했습니다. 원문에서 바뀐 부분이 있으며, 국가데이터처는 이 글을 검토하거나 보증하지 않았습니다. 수치와 기준 시점은 국가데이터처의 발표를 따릅니다.",
    "en": "This article was written with an AI tool by summarising and restructuring a press release that the Ministry of Data and Statistics (Korea) published under the KOGL Type 1 licence (attribution). "
          "Changes were made to the original, and the Ministry has not reviewed or endorsed this article. Figures and reference periods follow the Ministry's release."}
_MODS_PROMPT_RULE = ("국가데이터처 발표의 수치·단위·기준 시점(월·분기·연도)과 비교 기준(전년동월대비 등)을 요약에 적힌 그대로 쓰세요. 영어 글에서 '만·천' 단위를 옮길 때(예: 662만 5천명) 값이 바뀌지 않게 쓰고 "
                     "반올림하지 마세요. 통계 발표를 정부 정책의 성패 평가로 확대 해석하지 말고, 국가데이터처가 이 글을 검토·보증한 것처럼 쓰지 마세요. "
                     "건강·의료 정보는 통계 사실만 전하고 진단·치료·예방 효과를 조언하지 마세요.")
# 행사·포상·홍보·인사 글과 자동으로 다시 쓰기에는 민감한 주제(자살·마약·성폭력·가정폭력·학대·살인)는 쓰지 않는다
_MODS_EXCLUDE_TITLE = (r"포상|유공|전수식|개최|협약|채용|공모|설명회|시상|기념|토론회|출범|워크숍|세미나|간담회|혁신을 이끈|인사|임명|발령|보도참고|설명자료"
                       r"|자살|마약|성폭력|성범죄|가정폭력|학대|살인")
_MODS_ECONOMY = (r"물가|고용|실업|취업자|산업활동|소매판매|광공업|서비스업|생산|소비|온라인쇼핑|가계동향|소득|지출|부채|수출입|무역|기업|사업체|임금|근로|경기|건설|주택|부동산"
                 r"|농가|재배면적|가공식품|에너지|국내총생산|GDP")
_MODS_SOCIETY = r"인구|가구|출생|사망|혼인|이혼|인구이동|고령|청년|다문화|외국인|교육|학생|범죄|사회조사|사회통합|복지|장애인|아동|여성|노인"
_MODS_LIFE = r"생활인구|삶의 질|건강|여가|문화|1인 ?가구|수면|주거|통근|출산|결혼|가족|청소년|생활시간|돌봄|반려|스포츠|관광"

NEW_SOURCES_MODS = [
    {"name": "국가데이터처 · 경제", "display_name": "국가데이터처", "lane": "economy", "url": _MODS_FEED,
     "terms": _MODS_TERMS, "exclude_title": _MODS_EXCLUDE_TITLE, "topic_regex": _MODS_ECONOMY, "no_page_fetch": True,
     "citation": _MODS_CITATION, "notice": _MODS_NOTICE, "prompt_rule": _MODS_PROMPT_RULE},
    {"name": "국가데이터처 · 사회", "display_name": "국가데이터처", "lane": "society", "url": _MODS_FEED,
     "terms": _MODS_TERMS, "exclude_title": _MODS_EXCLUDE_TITLE, "topic_regex": _MODS_SOCIETY, "no_page_fetch": True,
     "citation": _MODS_CITATION, "notice": _MODS_NOTICE, "prompt_rule": _MODS_PROMPT_RULE},
    {"name": "국가데이터처 · 일상", "display_name": "국가데이터처", "lane": "daily_life", "url": _MODS_FEED,
     "terms": _MODS_TERMS, "exclude_title": _MODS_EXCLUDE_TITLE, "topic_regex": _MODS_LIFE, "no_page_fetch": True,
     "citation": _MODS_CITATION, "notice": _MODS_NOTICE, "prompt_rule": _MODS_PROMPT_RULE},
]
```
※ **Q1 후속(2026-11-04 16:14)**: 상세 페이지 4건에서 공공누리 제1유형(출처표시) 표시와 영문 기관명 "Ministry of Data and Statistics" 를 확인했습니다. 위 뼈대(`pending`·citation·notice)를 어떻게 고칠지는 **적용하지 않고 보고서 부록 B 에 제안만** 적었습니다 — 이 코드 블록은 그대로 둡니다.

메모: ① 세 항목이 같은 피드를 세 번 받습니다(분야 대체 때 최대 3번, 약 18KB) — 캐나다 통계청과 같은 방식입니다. ② 월별 반복 발표(물가·고용·산업활동)는 지난달 글과 제목이 비슷해 중복(유사도 0.6)으로 걸립니다. ③ 공공누리 유형이 3·4인 항목이 있으면 그 항목은 요약·번역이 변경에 해당해 쓸 수 없으니, 항목별로 유형을 알 수 있는 방법(페이지의 표시를 읽는 코드)이 필요하면 따로 요청하세요.

## 10. 조건부 보류 — Cedefop (사회·정책 / 경제·일), 승인 전 질문 Q6

법적 고지: `https://www.cedefop.europa.eu/en/content/legal-noticedisclaimer` — "출처를 밝히면 복제 허용(별도 표시가 있으면 예외)"만 적고 요약·번역 같은 가공은 적지 않음. 아래는 `pending` 으로 두었습니다.

```python
_CEDEFOP_TERMS = {"status": "pending", "checked": "2026-11-04", "url": "https://www.cedefop.europa.eu/en/content/legal-noticedisclaimer",
                  "blocker": "법적 고지는 '출처를 밝히면 복제 허용'만 적고 요약·번역(가공) 허용은 적지 않아, 집행위 재사용 결정(2011/833/EU)에 따른 가공 허용 여부를 사람이 확인해야 한다"}
_CEDEFOP_CITATION = "“{title}.” © Cedefop, {date} <{url}>"
_CEDEFOP_NOTICE = {
    "ko": "이 글은 AI 도구가 유럽직업훈련개발센터(Cedefop)가 공개한 자료를 요약·재구성해 작성했습니다. Cedefop은 이 글을 검토하거나 보증하지 않았습니다.",
    "en": "This article was written with an AI tool by summarising and restructuring material published by Cedefop. Cedefop has not reviewed or endorsed it."}
_CEDEFOP_PROMPT_RULE = "Cedefop의 보고서·정책 소개와 각국 사례를 구분하고, 요약에 없는 국가별 수치·예산·시행 시기는 만들지 마세요. Cedefop이 이 글을 검토·보증한 것처럼 쓰지 마세요."
_CEDEFOP_EXCLUDE_TITLE = r"\bcall for\b|\bvacanc|\btender\b|\bwebinar\b|\bsave the date\b"

NEW_SOURCES_CEDEFOP = [
    {"name": "Cedefop news", "display_name": "Cedefop", "lane": "society",
     "url": "https://www.cedefop.europa.eu/en/news.rss",
     "terms": _CEDEFOP_TERMS, "exclude_title": _CEDEFOP_EXCLUDE_TITLE, "no_page_fetch": True,
     "citation": _CEDEFOP_CITATION, "notice": _CEDEFOP_NOTICE, "prompt_rule": _CEDEFOP_PROMPT_RULE},
]
```

## 11. 분야·소스 공통 제외 규칙 모음(스팸·인사·채용·행사)

| 거를 것 | 영어 규칙(`exclude_title`) | 한국어 규칙 |
|---|---|---|
| 인사·지명·사임 | `\bappoints?\b\|\bnominat\|\bsteps? down\b` | `인사\|임명\|발령` |
| 채용·공모·조달 | `\bvacanc\|\btender\b\|\bcall for\b` | `채용\|공모\|입찰` |
| 행사·웨비나·기념 | `\bwebinar\b\|\bsave the date\b` | `개최\|설명회\|기념\|토론회\|세미나\|워크숍` |
| 성명·연설·의견 모집 | `\bstatement (?:from\|by\|of)\b\|\bseeks? public comment\b` | `성명\|담화\|의견수렴` |
| 자동으로 다시 쓰기에 민감한 주제 | 기존 `_STATCAN_EXCLUDE`·`_GOVUK_EXCLUDE_TITLE`(자살·자해·성폭력·학대·테러 등) 재사용 | `자살\|마약\|성폭력\|가정폭력\|학대\|살인` |
| 정치 소재 | `\belections?\b\|\bpolitical\b` | `선거\|정당` |

## 12. `generator.py` 변경 목록 (T2 — 독립 검증·드라이런 필요)

① **`_parse_date` 에 두 형식 추가** — FTC `November 3, 2026 | 8:56AM`(동부시간), 국가데이터처 `202611031531`(KST). 지금은 둘 다 `None` 이 되어 **72시간 검사를 건너뛰고 '신선'으로 통과**합니다.

```python
def _parse_date_extra(text):
    """_parse_date 가 못 읽은 두 형식. 시간대는 FTC=미국 동부(-5시간으로 근사), 국가데이터처=KST."""
    m = re.fullmatch(r"([A-Za-z]{3})[a-z]* (\d{1,2}), (\d{4}) \| (\d{1,2}):(\d{2})(AM|PM)", text.strip())
    if m:
        month = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"].index(m.group(1).lower()) + 1
        hour = int(m.group(4)) % 12 + (12 if m.group(6) == "PM" else 0)
        return datetime.datetime(int(m.group(3)), month, int(m.group(2)), hour, int(m.group(5)), tzinfo=timezone(timedelta(hours=-5)))
    m = re.fullmatch(r"(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})", text.strip())
    if m:
        return datetime.datetime(*(int(g) for g in m.groups()), tzinfo=KST)
    return None
```

② **출처 문구를 글 언어별로** — `citation` 이 `{"ko": …, "en": …}` 사전이면 글 언어(`_content_lang`)에 맞는 것을 쓰고 `{year}` 자리를 더합니다(지금은 문자열 하나, 날짜는 영어 표기). 한국어 소스의 공공누리 1유형 출처 표시를 깔끔하게 하려면 필요합니다(없어도 이중 언어 한 줄로 임시 가능).

③ **날짜 없는 항목 처리 옵션** — 소스에 `"require_date": True` 를 두면 날짜를 못 읽은 항목을 `NO_DATE` 로 떨굽니다(지금은 AGE 검사를 건너뜀). `DROP_LABELS` 에 코드와 설명도 더하고 `test_every_drop_code_has_a_label` 에 추가합니다.

④ **요약 입력 상한** — `parse_feed` 의 요약 기본 300자 때문에 FTC(중앙 3,520자)·DOL(2,117자)·국가데이터처(562자)는 앞부분만 모델에 갑니다. gfix 묶음이 1,500~2,000자로 늘리면 풀립니다(한국어는 300자가 영어 300자보다 정보가 많아도 표·수치는 뒤에 있음).

⑤ **시험 갱신** — `test_source_names_are_unique_and_every_feed_lane_and_publisher_is_pinned` 의 고정 사전에 새 이름·분야·피드 주소를 더하고, 새 도메인 신뢰 시험(`_trusted_domain`)과 새 정규식 컴파일 시험, 인용 틀 채우기 시험(`October 23, 2026`)을 통과시킵니다. `pending` 소스는 `test_prompt_grounding` 의 '모든 소스에 지침' 시험도 통과해야 합니다(`prompt_rule` 있음).

⑥ **FDA Crawl-delay 30초** — 기사 페이지를 읽지 않는 설정(`no_page_fetch`)이므로 한 실행에 FDA 피드 요청이 한 번뿐이어야 합니다. 분야 대체로 같은 피드를 여러 번 받는 구조라면 `page_delay` 와 별개로 호스트별 최소 간격이 필요합니다(현재 엔진은 요청 사이에 기다리지 않음).

## 13. 시험 삼아 확인한 것(이 초안의 정규식)

초안 코드 블록은 작성 후 파이썬으로 구문·정규식 컴파일을 시험했습니다(결과는 `S\k_progress.md` 마지막 줄).
