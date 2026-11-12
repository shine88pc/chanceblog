"""최소 품질 Gate 시험이 함께 쓰는 가짜 후보 글. 기관·제품·사람 이름은 모두 지어낸 것이고 실제 블로그 이름·주소는 쓰지 않는다.

fixture_source()   — 모델에 준 근거(피드 항목)
fixture_data()     — 그 근거만으로 쓴, 모든 규칙을 통과하는 국문·영문 글 한 쌍(검증을 통과한 data 의 모양: kr_*·en_* 키)
make_data(...)     — 본문을 바꿔 끼운 변형
"""
import datetime
import json

import _bootstrap  # noqa: F401
from pipeline import quality_gate as qg, registry

LINK = "https://www.example-agency.europa.eu/news/household-income-2026"
DOMAIN = "www.example-agency.europa.eu"
KST = datetime.timezone(datetime.timedelta(hours=9))
AS_OF = datetime.date(2026, 11, 9)

SUMMARY = (
    "The statistics office published its annual household income survey on November 4, 2026. The survey covered 1,250,000 households. "
    "Median household income rose 3.4 percent in 2025 to 48,200 dollars. About 12.5 percent of households reported income below the poverty line. "
    "The office said the sample was weighted to match population totals. Read the full release for methods and tables."
)
TITLE = "Household income survey: median income up 3.4 percent in 2025"

KO_FILLER = (
    "중위 소득은 가구를 소득 순서대로 세웠을 때 한가운데 가구의 소득을 뜻합니다.",
    "평균과 달리 아주 높은 소득이 섞여도 크게 흔들리지 않아 생활 수준을 읽는 데 자주 쓰입니다.",
    "조사 방식이 해마다 같은지 확인하는 일은 숫자를 해석할 때 가장 먼저 해야 할 점검입니다.",
    "소득이 늘었다는 사실만으로 살림이 나아졌다고 말할 수는 없고 물가와 함께 보아야 합니다.",
    "가중 방식이 바뀌면 같은 숫자라도 비교할 수 있는 범위가 달라지므로 방법 설명을 함께 읽어야 합니다.",
    "이 글은 발표된 요약 자료만 근거로 삼았기 때문에 표와 부록에 있는 세부 내용은 다루지 않습니다.",
    "소득이 오른 가구와 그렇지 못한 가구가 어떻게 나뉘는지는 요약 자료만으로는 알 수 없습니다.",
    "독자는 자신이 속한 지역과 직업의 사정이 평균적인 흐름과 다를 수 있다는 점을 염두에 둘 수 있습니다.",
    "정책을 논의하는 사람들은 이런 숫자를 근거로 지원의 대상과 규모를 정하려 합니다.",
    "숫자를 읽는 일은 결론을 서두르기보다 무엇을 세었고 무엇을 세지 않았는지 묻는 데서 시작합니다.",
    "같은 조사가 다음 해에 나오면 이번 값과 나란히 놓고 변화의 방향을 확인할 수 있습니다.",
    "표본 조사의 숫자는 늘 오차를 품고 있어서 작은 차이를 크게 해석하지 않는 편이 안전합니다.",
)
EN_FILLER = (
    "Median income is the income of the household in the middle when all households are ranked from lowest to highest.",
    "Unlike the average, it does not move much when a few very high incomes are added, so it is often used to describe living standards.",
    "Checking whether the survey method stayed the same from year to year is the first step when reading any figure.",
    "A rise in income alone does not show that households are better off, because prices have to be considered together with income.",
    "If the weighting method changes, the same number can cover a different range of households, so the method note should be read too.",
    "This article relies only on the published summary, so the detailed tables and appendices are not covered here.",
    "The summary does not show how income gains were split between households that gained and households that did not.",
    "Readers can keep in mind that conditions in their own region and occupation may differ from the overall pattern.",
    "People who discuss policy often use figures like these to decide who should receive support and how much.",
    "Reading a figure begins with asking what was counted and what was not, rather than rushing to a conclusion.",
    "When the same survey appears next year, the new value can be placed beside this one to see the direction of change.",
    "Figures from a sample survey always carry some error, so it is safer not to read small differences too strongly.",
)


def pad(sentences, minimum, count_chars):
    """문장을 반복해 붙여 읽기 글자 수(공백 제외)가 minimum 이상이 되는 문단 목록을 만든다."""
    paragraphs, current, total, index = [], [], 0, 0
    while total < minimum:
        sentence = sentences[index % len(sentences)]
        index += 1
        current.append(sentence)
        total += count_chars(sentence)
        if len(current) == 3:
            paragraphs.append(" ".join(current))
            current = []
    if current:
        paragraphs.append(" ".join(current))
    return paragraphs


def _chars(text):
    return len("".join(text.split()))


def ko_body(link=LINK, source_list="### 출처\n- [예시 기관 보도자료](" + LINK + ")", extra="", minimum=1100):
    head = (f"통계청이 2026년 11월 4일 연간 가구 소득 조사를 공개했습니다. [원문]({link})에 따르면 이번 조사는 1,250,000가구를 대상으로 했고, "
            "2025년 중위 가구 소득은 3.4% 늘어 4만 8,200달러가 되었습니다. 소득이 기준선 아래인 가구는 12.5%였습니다.")
    paragraphs = [head] + pad(KO_FILLER, minimum - _chars(head), _chars)
    paragraphs.insert(2, "### 무엇을 읽어야 하나")
    body = "\n\n".join(paragraphs)
    if extra:
        body += "\n\n" + extra
    if source_list:
        body += "\n\n---\n\n" + source_list
    return body + "\n\n![Thumbnail](https://example.invalid/kr.jpg)\n"


def en_body(link=LINK, source_list="### Sources\n- [Example agency release](" + LINK + ")", extra="", minimum=1700):
    head = (f"The statistics office published its annual household income survey on November 4, 2026. According to the [release]({link}), the survey covered "
            "1,250,000 households, and median household income rose 3.4 percent in 2025 to 48,200 dollars. About 12.5 percent of households were below the poverty line.")
    paragraphs = [head] + pad(EN_FILLER, minimum - _chars(head), _chars)
    paragraphs.insert(2, "### What to read in the figures")
    paragraphs.insert(4, "- The median is the middle household.\n- The sample was weighted.\n- Details are in the tables.")
    paragraphs.insert(6, "### Limits of this summary")
    body = "\n\n".join(paragraphs)
    if extra:
        body += "\n\n" + extra
    if source_list:
        body += "\n\n---\n\n" + source_list
    return body + "\n\n![Thumbnail](https://example.invalid/en.jpg)\n"


def front(title, lang):
    return f"---\nlayout: post\ntitle: {json.dumps(title, ensure_ascii=False)}\ncategory: \"예시\"\ntags: []\nlang: {lang}\nimage: \"https://example.invalid/x.jpg\"\n---\n\n"


KO_TITLE = "가구 소득 조사: 2025년 중위 소득 3.4% 증가"
EN_TITLE = TITLE


def make_data(ko=None, en=None, ko_title=KO_TITLE, en_title=EN_TITLE):
    """국문·영문 본문(머리말 앞의 본문)을 받아 data(kr_*·en_* 키)를 만든다. 본문을 주지 않으면 통과하는 기본 본문을 쓴다."""
    ko = ko_body() if ko is None else ko
    en = en_body() if en is None else en
    return {
        "kr_category": "예시", "kr_title": ko_title, "kr_tags": [], "kr_content": front(ko_title, "ko") + ko,
        "en_category": "Example", "en_title": en_title, "en_tags": [], "en_content": front(en_title, "en") + en,
    }


def fixture_data():
    return make_data()


def fixture_source(**overrides):
    item = {
        "title": TITLE, "source": "Example Agency", "link": LINK, "publisher_domain": DOMAIN, "summary": SUMMARY,
        "published": datetime.datetime(2026, 11, 4, 3, 0, tzinfo=datetime.timezone.utc),
    }
    item.update(overrides)
    return item


def health_profiles():
    return tuple(registry.load_profile(name) for name in qg.HEALTH_PROFILE_NAMES)


def make_config(languages=("ko", "en")):
    return qg.GateConfig(health_profiles=health_profiles(), languages=tuple(languages))


def run_gate(data=None, source=None, history=(), config=None, as_of=AS_OF):
    return qg.check_candidate(fixture_data() if data is None else data, fixture_source() if source is None else source,
                              history=history, config=config or make_config(), as_of=as_of)
