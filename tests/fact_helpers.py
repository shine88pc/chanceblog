"""구조화 Fact 경로 시험의 공통 도구: 오프라인 가짜 Provider(`mock_stats`)로 수집 기록·Fact 를 만들고 조립기를 부른다. 네트워크·시계·난수 없음.

고정 시각은 시험이 정한다(코드는 시계를 읽지 않는다): 수집 2026-04-18T02:30:00Z, 오늘 2026-04-20.
"""
import functools
import re

import _bootstrap  # noqa: F401

from pipeline import fact_assembler as A
from pipeline import facts as F
from pipeline import recipes as R
from pipeline.adapters import mock_stats as M

RETRIEVED_AT = "2026-04-18T02:30:00Z"
TODAY = "2026-04-20"
UNEMP = "labour.unemployment_rate"


@functools.lru_cache(maxsize=None)
def mock_bundle():
    """(Provider, 수집 기록, Fact 튜플) — 가짜 Provider 의 JSON 응답 전체를 읽은 결과."""
    provider = M.MockProvider()
    adapter = M.MockStatsAdapter(provider)
    access = provider.access[0]
    raw = adapter.fetch(access, {}, M.make_mock_opener())
    record, facts = adapter.parse(raw, access, RETRIEVED_AT, {})
    return provider, record, tuple(facts)


def source_info(provider=None):
    return A.SourceInfo(provider or M.MockProvider(), M.SOURCE_NAME, M.SOURCE_URL)


def obs(region, period, series="unemp", facts=None):
    """가짜 데이터에서 계열·지역·기간의 Fact 하나(없으면 AssertionError)."""
    key = M.SERIES[series][0]
    found = [f for f in (facts if facts is not None else mock_bundle()[2]) if f.key == key and f.region == region and f.as_of == period]
    assert len(found) == 1, (series, region, period, len(found))
    return found[0]


def series_of(region, series="unemp", facts=None):
    key = M.SERIES[series][0]
    return sorted((f for f in (facts if facts is not None else mock_bundle()[2]) if f.key == key and f.region == region), key=lambda f: f.as_of)


def make_fact(value, *, key=UNEMP, region="R01", period="2026-03", unit="%", level="province", provider="mock_stats", label="실업률",
              region_label="가상 지역 가", kind=F.KIND_OBSERVATION, record_id="s0000000000000000"):
    """시험용으로 만든 Fact 한 개(수집 기록 없이 — 계산 시험용)."""
    return F.Fact.create(provider, record_id, kind, key, value, unit=unit, as_of=period, region=region, region_level=level,
                         region_label_ko=region_label, label_ko=label)


def run(recipe, *, params=None, facts=None, records=None, today=TODAY, provider=None, source=None):
    """조립기를 가짜 데이터로 부른다. recipe 는 Recipe 이거나 그 id. facts·records·provider·source 를 바꿔 끼울 수 있다."""
    prov, record, all_facts = mock_bundle()
    recipe = recipe if isinstance(recipe, R.Recipe) else R.RECIPES[recipe]
    return A.assemble(recipe, all_facts if facts is None else facts, today, records=[record] if records is None else records,
                      source=source or source_info(provider or prov), params=params)


R01_PARAMS = {"key": UNEMP, "region": "R01"}
R02_PARAMS = {"key": UNEMP}
GOLDEN = {"R01_time_series": R01_PARAMS, "R02_region_compare": R02_PARAMS, "R03_record_position": R01_PARAMS}


def quality_metrics(post):
    """글의 분량과 '틀 고정 글자 비율'을 센다(글자 수는 생성기 방식 — 공백·표시 기호·표 구분줄 제외, 출처 목록 제외). 독립 검증의 글 품질 평가를 숫자로 확인하는 데 쓴다:
    story = 본문 분량 · caution = 그 가운데 '이 숫자를 읽을 때 주의' 절 · pure = 주의 절을 뺀 분량 · fixed = 틀에서 참조 표시를 지운 고정 글자 수 · fixed_percent = fixed 가 story 의 몇 %."""
    story = A.story_of(post.body_markdown)
    start = story.index("## " + R.H_CAUTION)
    literal = F.REF_RE.sub("", post.template_markdown).replace(R.SOURCE_LINK_TOKEN, "")
    total, fixed = A.readable_chars(story), A.readable_chars(literal)
    return {"story": total, "caution": A.readable_chars(story[start:]), "pure": A.readable_chars(story[:start]), "fixed": fixed, "fixed_percent": round(100 * fixed / total)}
