"""구조화 Fact 후보 공급 — 오늘 낼 글 후보를 **한 군데에서** 만드는 순수 오케스트레이터(S2b). 표준 라이브러리와 이 경로의 모듈만 쓰고 시계·난수·파일 입출력이 없다.
네트워크는 호출한 쪽이 주입한 `opener` 로만 닿는다 — 연결 코드(생성기 한 군데)가 그 `opener` 를 허용 목록 관문·호출 예산으로 감싸서 넘긴다(이 모듈은 SRC 모듈을 import 하지 않는다).

`supply(today=, retrieved_at=, history=, provider=, opener=, accept=, limit=)` 가 하는 일:
1. 이력에서 지난 Fact 글을 읽어(`fact_candidates.made_from_history`) 오늘 낼 수 있는 글감을 **먼저 낼 차례** 순서로 받는다(`fact_candidates.select_candidates` — 가장 오래 전에 낸 글감 먼저·같은 묶음은 이어서·
   같은 제품을 읽은 글과 자료 창만큼 띄움·이번 기간에 이미 낸 묶음은 닫힘).
2. 차례대로: 글감이 읽는 제품마다 어댑터가 `fetch`→`parse` 한다(한 제품은 한 실행에서 **한 번만** 부른다 — 받은 응답과 실패를 모두 기억해 같은 제품을 읽는 다음 글감이 다시 부르지 않는다. 실패 뒤 곧바로 되부르는 재시도는 없다)
   → 조립기 `assemble`. 어댑터 오류·`Insufficient`·중복(`dedupe_key` 가 이력에 있음)·`accept` 의 거절은 그 글감만 `skipped` 에 사유 코드와 함께 적고 **다음 글감으로 넘어간다**(대표가 못 만들면 같은 묶음의 다음 글감이 이어진다).
3. `limit` 편(기본 1 — 오늘 낼 수 있는 첫 글 하나)을 만들면 멈춘다. 같은 묶음에서 한 편이 나오면 그 묶음의 나머지 글감은 더 시도하지 않는다.
4. 차례인 글감이 시각 때문에 아직 읽을 수 없으면(일별 제품의 협정 세계시 하한) 건너뛰어 다른 글감을 먼저 내지 않고 **기다린다**(`waiting`) — 건너뛰면 그 글감이 늘 새벽 실행에 밀려 굶는다.

사유 코드(`skipped` 의 둘째 칸, 고정 글자뿐 — 외부 글을 싣지 않는다): `ADAPTER:<어댑터 오류 코드>`(예: `EGRESS_DENIED`·`BUDGET_DENIED`·`OPENER_FAILED`·`BAD_SHAPE`)·`ADAPTER:UNEXPECTED_ERROR`·`INSUFFICIENT:<조립기 사유 코드>`·
`DUPLICATE:DEDUPE_KEY`·`REJECTED:<accept 가 돌려준 사유(영문·숫자·`_.:-` 60자)>`·`BAD_INPUT:TODAY`·`BAD_INPUT:RETRIEVED_AT`. 이 함수는 입력이 이상해도 예외를 올리지 않고 글 대신 사유를 돌려준다.
`SupplyResult.notes`(S2C0-b)는 이 실행이 읽은 제품에서 어댑터가 **쓰지 않고 버린 행**의 기록이다(어댑터의 `notes` — 오늘(UTC) 날짜의 일별 흑점수 행·이번 달의 월별 행, 우리 낱말의 고정 문장) — 건너뜀이 아니라 알림이라 `skipped` 와 따로 두고
글을 못 만든 날의 결과 코드(`FACT_ALL_SKIPPED` 등)를 바꾸지 않는다.

`thin_of(post)`(S2c-1)는 그림자 결과의 `thin` 블록(얇음 측정 일곱 값)을 조립된 글에서 만든다 — 순수 모듈 `fact_thin` 을 감싸고 실패해도 예외를 올리지 않는다.

`gate_source(post, provider)` 는 최소 품질 Gate 에 넘기는 후보의 `source` 사전을 만든다 — 키는 `GATE_SOURCE_KEYS` 아홉 개이고 `provider_hosts` 는 **레지스트리의 Provider 접근 경로 호스트 전체**에서만 채운다
(글·응답에서 읽은 값을 쓰지 않는다). Gate 쪽은 별도 묶음(S2BG)이 이 모양을 읽게 고친다.

설명: docs/FACT_PATH.md §15
"""
import re
from dataclasses import dataclass

from pipeline import fact_assembler as A
from pipeline import fact_candidates as K
from pipeline import fact_thin as THIN
from pipeline import facts as F
from pipeline.adapters import noaa_swpc as N
from pipeline.adapters.base import AdapterError

PROVIDER_ID = "noaa_swpc_json"           # 이 경로가 읽는 허용 목록 Provider(NOAA 우주날씨 JSON — 규칙 기반 경로 전용)
GATE_SOURCE_KEYS = ("fact_post", "evidence_text", "source_url", "source_domain", "source_name", "provider_hosts", "dedupe_key", "recipe_id", "as_of")
MAX_REASON_CHARS = 60
_UNSAFE_REASON_CHARS = re.compile(r"[^A-Za-z0-9_.:\-]")


@dataclass(frozen=True)
class SupplyResult:
    """공급 결과. posts·candidates 는 같은 순서의 짝(글 하나마다 그 글을 낸 후보 — candidate_key 가 이력에 남는다). skipped 는 ((글감 spec_id, 사유 코드), …) 시도한 순서,
    waiting 은 시각 때문에 기다리는 글감 spec_id(없으면 빈 글자), considered 는 차례가 와서 살펴본 글감 spec_id 들(순서대로), notes 는 읽은 제품에서 쓰지 않고 버린 행의 기록(고정 문장, 없으면 빈 튜플 — S2C0-b)."""
    posts: tuple = ()
    candidates: tuple = ()
    skipped: tuple = ()
    waiting: str = ""
    considered: tuple = ()
    notes: tuple = ()


def _entries(value):
    return value if isinstance(value, (list, tuple)) else ()


def provider_hosts(provider):
    """레지스트리 Provider 의 접근 경로(`access`)에 적힌 호스트 전체(중복 없이 적힌 순서대로). 호스트 모양이 아닌 값(글자가 아님)은 건너뛴다."""
    found = []
    for access in _entries(F.field_of(provider, "access", ())):
        for host in _entries(F.field_of(access, "hosts", ())):
            if isinstance(host, str) and host and host not in found:
                found.append(host)
    return found


def gate_source(post, provider):
    """Gate 에 넘기는 Fact 후보의 `source` 사전(키 아홉 개 — `GATE_SOURCE_KEYS`). `fact_post` 는 정확히 True 이고 나머지는 조립된 글(`AssembledPost`)과 레지스트리 Provider 에서만 온다."""
    return {"fact_post": True, "evidence_text": post.evidence_text, "source_url": post.source_url, "source_domain": post.source_domain, "source_name": post.source_name,
            "provider_hosts": provider_hosts(provider), "dedupe_key": post.dedupe_key, "recipe_id": post.recipe_id, "as_of": post.as_of}


def api_access(provider):
    """Provider 접근 경로 가운데 NOAA 호스트를 가진 api 경로(없으면 None)."""
    for access in _entries(F.field_of(provider, "access", ())):
        if F.field_of(access, "kind") == "api" and N.HOST in _entries(F.field_of(access, "hosts", ())):
            return access
    return None


def product_id_of_url(url):
    """제품 파일의 https 주소 → 제품 id(`kp_estimated` 등 — 우리 제품 표 `noaa_swpc.PRODUCTS` 의 id). 표에 있는 주소와 **글자 하나까지 같은** 것만 알아본다(질의·조각·대소문자가 다른 호스트·끝 공백·다른 호스트는 None).
    그림자 실행의 원본 응답 보관이 파일 이름을 정할 때 쓴다(S2C0-c) — 주소의 어떤 조각도 파일 이름이 되지 않는다."""
    if not isinstance(url, str):
        return None
    for product_id in N.PRODUCTS:
        if url == N.product_url(product_id):
            return product_id
    return None


def thin_of(post):
    """그림자 결과에 싣는 얇음 측정 블록(S2c-1) — 조립된 글에서만 계산하는 일곱 정수(`fact_thin.measure`: 고정 글자 비율·순수 고정 문장 수·값 문장 수·C 등급 계산 문장 수·직접 계산 표명 수·받은 날짜 표기 수·근거 텍스트 글자 수).
    판정이 아니라 사람이 먼저 볼 순서를 정하는 신호다. 계산이 예상 밖으로 실패해도 그림자 실행의 본 결과는 그대로이고 블록에는 예외 이름(우리 고정 글자가 아닌 파이썬 이름뿐)만 남는다(`{"error": …}`)."""
    try:
        return THIN.measure(post)
    except Exception as exc:      # noqa: BLE001 — 측정은 보조 신호다: 실패가 그림자 실행의 본 결과를 막지 않게 한다
        return {"error": type(exc).__name__}


def _reason(text):
    """accept 가 돌려준 사유를 고정 글자 모양으로(영문·숫자·`_.:-` 만, 60자) — 외부·모델 글이 사유 코드에 섞이지 않게 한다."""
    cleaned = _UNSAFE_REASON_CHARS.sub("_", str(text))[:MAX_REASON_CHARS]
    return cleaned or "UNKNOWN"


def _load(product_id, provider, access, opener, retrieved_at, loaded):
    """제품 하나를 이 실행에서 한 번만 읽는다(성공도 실패도 기억). 돌려주는 값: (수집 기록, Fact 튜플, 실패 코드 또는 None, 버린 행의 기록 튜플)."""
    if product_id not in loaded:
        try:
            adapter = N.NoaaSwpcAdapter(provider, product_id)
            raw = adapter.fetch(access, {}, opener)
            record, facts = adapter.parse(raw, access, retrieved_at)
            loaded[product_id] = (record, tuple(facts), None, tuple(adapter.notes))
        except AdapterError as exc:
            loaded[product_id] = (None, (), exc.code, ())
        except Exception:      # noqa: BLE001 — 어댑터 하나의 예상 밖 오류가 다른 글감까지 막지 않게 그 글감만 건너뛴다(고정 코드만 남긴다)
            loaded[product_id] = (None, (), "UNEXPECTED_ERROR", ())
    return loaded[product_id]


def supply(*, today, retrieved_at, history, provider, opener, accept=None, limit=1):
    """오늘 낼 Fact 글 후보를 만든다(위 설명). today: 글을 내는 날(KST 날짜 — date·`YYYY-MM-DD`), retrieved_at: 수집 시각(시간대 포함 ISO — 협정 세계시 `…Z`), history: 이력 항목 목록,
    provider: 허용 목록의 Provider(읽기 전용 객체 — `enabled` 가 참이고 자동화 가능이어야 어댑터가 만들어진다), opener: `opener(url, timeout=, max_bytes=) -> bytes`(이미 관문·예산으로 감싼 것),
    accept: `accept(post, candidate) -> 거절 사유(글자) 또는 None`(머리말·Gate 같은 호출한 쪽의 검사 — 거절하면 그 글감은 건너뛴다), limit: 낼 글 수 상한(1 이상)."""
    try:
        day = F.as_date(today)
    except F.FactFormatError:
        return SupplyResult(skipped=(("(all)", "BAD_INPUT:TODAY"),))
    moment = F.parse_as_of(retrieved_at)
    if moment is None or moment.granularity != "instant":
        return SupplyResult(skipped=(("(all)", "BAD_INPUT:RETRIEVED_AT"),))
    made = K.made_from_history(history)
    ordered = K.select_candidates(day, made, minutes_utc=(moment.ordinal % 86400) // 60)
    access = api_access(provider)
    cap = limit if isinstance(limit, int) and not isinstance(limit, bool) and limit >= 1 else 1
    loaded, posts, chosen, skipped, considered, waiting, closed = {}, [], [], [], [], "", set()
    for candidate in ordered:
        spec_id = candidate.spec.spec_id
        if K.GROUP_OF[spec_id] in closed:
            continue
        if len(posts) >= cap:
            break
        considered.append(spec_id)
        if not candidate.ready:
            waiting = spec_id
            break
        if access is None:
            skipped.append((spec_id, "ADAPTER:BAD_ACCESS"))
            continue
        records, facts, failure = [], [], None
        for product_id in candidate.products:
            record, product_facts, failure, _left_out = _load(product_id, provider, access, opener, retrieved_at, loaded)
            if failure:
                break
            records.append(record)
            facts.extend(product_facts)
        if failure:
            skipped.append((spec_id, f"ADAPTER:{failure}"))
            continue
        recipe = K.get_recipe(candidate.recipe_id)
        if recipe is None:
            skipped.append((spec_id, "INSUFFICIENT:UNKNOWN_RECIPE"))
            continue
        first = candidate.products[0]
        post = A.assemble(recipe, facts, day, records=records, source=A.SourceInfo(provider, N.product_source_name(first), N.product_url(first)), params=dict(candidate.params))
        if not isinstance(post, A.AssembledPost):
            skipped.append((spec_id, f"INSUFFICIENT:{post.code}"))
            continue
        if post.dedupe_key in made.dedupe:
            skipped.append((spec_id, "DUPLICATE:DEDUPE_KEY"))
            continue
        rejected = accept(post, candidate) if accept is not None else None
        if rejected:
            skipped.append((spec_id, f"REJECTED:{_reason(rejected)}"))
            continue
        posts.append(post)
        chosen.append(candidate)
        closed.add(K.GROUP_OF[spec_id])
    notes = tuple(note for _record, _facts, _failure, left_out in loaded.values() for note in left_out)      # 읽은 제품마다 한 번만(제품은 한 실행에 한 번 읽는다) — 읽은 순서대로
    return SupplyResult(tuple(posts), tuple(chosen), tuple(skipped), waiting, tuple(considered), notes)
