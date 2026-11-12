"""허용 목록(Source Registry) 시험이 함께 쓰는 가짜 Provider. 기관·주소는 모두 지어낸 것이다(`.example` 호스트) — 실제 기관·블로그 이름·계정 번호를 쓰지 않는다.

good_provider(**바꿀 값)   — 모든 ACTIVE 규칙(A0–A10)을 통과하는 enabled 구조화 Provider 한 건(JSON 객체). 최상위 키만 덮어쓴다.
cell(...)                  — 칸 하나(기본: ALLOWED/EXPLICIT, 근거 문서 이름·열람일 있음)
registry_data(*providers)  — 파일 전체 모양({"schema_version": 1, "providers": [...]})
with_cell(provider, name, **칸 값) / with_access(provider, **경로 값) — 한 칸·한 경로만 바꾼 사본
"""
import copy

import _bootstrap  # noqa: F401
from pipeline import source_registry as sr

TODAY = "2026-11-09"
GOOD_HOST = "api.fixture-stats.example"


def cell(state="ALLOWED", basis="EXPLICIT", evidence="Fixture Agency Terms of Use", read_at="2026-11-09"):
    return {"state": state, "basis": basis, "evidence": evidence, "read_at": read_at}


def good_provider(**overrides):
    provider = {
        "provider_id": "fixture_stats",
        "name": "Fixture Statistics API (지어낸 기관)",
        "class": "data",
        "policy": {name: cell() for name in sr.CELLS},
        "strict_tier": 2,
        "permissive_interpretation": 2,
        "effective_status": "자동화 가능",
        "access": [{"kind": "api", "hosts": [GOOD_HOST], "paths": ["/v1/"], "auth": "KEY", "rate_limit": "100 per day", "robots_checked_at": "2026-11-09"}],
        "reference_hosts": [],
        "snapshot": {"terms_pages": ["Fixture API Terms"], "read_at": "2026-11-09", "content_hash": "", "expires_at": "2027-02-07"},
        "attribution_template": "Source: Fixture Agency",
        "exceptions": [],
        "retention_days": 30,
        "enabled": True,
    }
    provider.update(copy.deepcopy(overrides))
    return provider


def registry_data(*providers):
    return {"schema_version": 1, "providers": list(providers) or [good_provider()]}


def with_cell(provider, name, **values):
    out = copy.deepcopy(provider)
    out["policy"][name].update(values)
    return out


def with_access(provider, index=0, **values):
    out = copy.deepcopy(provider)
    out["access"][index].update(values)
    return out


def has(problems, code, *needles):
    """problems 중 `[code]` 태그와 모든 needle 을 가진 문장이 있는가."""
    return any(f"[{code}]" in p and all(n in p for n in needles) for p in problems)


def codes(problems):
    """문제 문장에 든 규칙 번호 집합."""
    import re
    return {m for p in problems for m in re.findall(r"\[([A-Z]\d+)\]", p)}
