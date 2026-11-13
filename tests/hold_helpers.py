"""S2C0-a(재개 직후 글감 순서 안전장치) 시험의 공통 도구. 네트워크·시계 없음.

`fact_candidates` 의 두 상수(`HELD_SPEC_IDS` 임시 제외·`FIRST_SPEC_IDS` 처음 낼 글감)의 **기본값**은 운영 동작을 바꾼다. 글감 여섯 전부를 가정하고 쓴 기존 시험 모듈은 단언을 하나도 바꾸지 않고
두 상수를 빈 튜플로 비운 채 돌린다(`module_fixtures`) — 빈 튜플은 이전 동작과 바이트까지 같다는 것이 이 묶음의 약속이라 기존 시험이 그대로 '이전 동작의 증거' 가 된다. 기본 상수의 동작은 새 시험
(`tests/test_fact_hold.py`)이 따로 시험한다.

`PRODUCTION_HELD`·`PRODUCTION_FIRST` 는 이 모듈을 가져올 때 읽은 값이다. 시험 모듈은 모두 시험이 돌기 전에 한꺼번에 가져오므로(`unittest discover`) 아직 어떤 대체도 걸리기 전의 기본 상수 그대로다.
"""
from unittest import mock

import _bootstrap  # noqa: F401

from pipeline import fact_candidates as K

PRODUCTION_HELD = K.HELD_SPEC_IDS
PRODUCTION_FIRST = K.FIRST_SPEC_IDS


def policy_off():
    """임시 제외·처음 낼 글감을 모두 끈(빈 튜플) 대체 — 이 변경 전의 선택 정책이다. `start()`·`stop()` 하거나 `with` 로 쓴다."""
    return mock.patch.multiple(K, HELD_SPEC_IDS=(), FIRST_SPEC_IDS=())


def policy(held, first):
    """두 상수를 시험이 정한 값으로 대체한다."""
    return mock.patch.multiple(K, HELD_SPEC_IDS=tuple(held), FIRST_SPEC_IDS=tuple(first))


def module_fixtures():
    """(setUpModule, tearDownModule) 한 쌍 — 시험 모듈 하나 전체를 두 상수를 비운 채 돌린다. 모듈 최상위에서 `setUpModule, tearDownModule = HH.module_fixtures()` 로 받는다."""
    started = []

    def up():
        patch = policy_off()
        patch.start()
        started.append(patch)

    def down():
        while started:
            started.pop().stop()
    return up, down
