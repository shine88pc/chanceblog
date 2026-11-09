"""규칙 기반 한국어 초안 조립기 — AI 없음. `assemble(recipe, facts, today, *, records, source, params=None)` 순수 함수.

Fact 와 출처 기록을 Recipe(`pipeline/recipes.py`)에 넣어 `AssembledPost`(제목·설명·본문·분류·태그·쓴 Fact·계산 결과·근거 텍스트·출처)를 만든다. 같은 입력이면 바이트까지 같은 글이다
(입력 순서도 상관없다). 표준 라이브러리와 이 경로의 새 모듈(`pipeline/facts.py`·`pipeline/calc.py`·`pipeline/recipes.py`)만 쓰고 입출력·시계·난수·네트워크가 없다.

근거 없는 문장으로 분량을 채우지 않는다. 데이터가 모자라 분량 하한(국문 1,000자, 출처 목록 제외)을 못 맞추면 글을 만들지 않고 `Insufficient`(사유 코드와 우리 문장)를 돌려준다.
만든 글은 마지막에 스스로 검사한다(`post_problems`): 숫자는 모두 근거 텍스트에 있고, 표시 문자·Liquid 문자·물결표·금지 표현·섞인 글자 체계가 없고, 제목·설명·절 순서·표·분량이 맞는지.
검사에 걸리면 글 대신 `Insufficient("QUALITY_CHECK_FAILED")` 다 — 조용히 내보내지 않는다(fail closed).

`SourceInfo` 는 Provider 의 공식 데이터 이름·페이지 주소를 인자로 받는다(SRC 의 Registry 에서 오는 값 — 이 모듈은 SRC 모듈을 import 하지 않는다).
`assemble` 은 어떤 입력에서도 예외를 올리지 않고 글(`AssembledPost`)이나 `Insufficient` 를 돌려준다(예상 밖 오류는 `INTERNAL_ERROR` — 글을 내보내지 않는다).
설명: docs/FACT_PATH.md
"""
import re
from dataclasses import dataclass
from typing import Any

from pipeline import calc as C
from pipeline import fact_topics as T
from pipeline import facts as F
from pipeline import recipes as R
from pipeline.recipes import Insufficient

ATTRIBUTION_PREFIX = "- 이용 조건: "
LANG = "ko"
MAX_TAGS = 6
MIN_DISTINCT_FORMULAS = 2    # 원자료 대비 추가 분석: 서로 다른 계산식이 둘 이상(관문 ③)

_SOURCE_NAME_RE = re.compile(r"[가-힣A-Za-z0-9 ·.,&'\-]{1,80}")
_BRACES = ("{", "}")


@dataclass(frozen=True)
class SourceInfo:
    """글에 밝힐 공식 데이터 이름·페이지 주소와 Provider(ProviderLike). attribution_template·reader_notes 는 Provider 에서 읽는다(없으면 비어 있다)."""
    provider: Any
    name: str
    url: str

    @property
    def domain(self):
        return F.source_domain(self.url)

    @property
    def attribution_template(self):
        return F.field_of(self.provider, "attribution_template", None)

    @property
    def reader_notes(self):
        """독자에게 보일 수 있게 승인된 숫자 없는 짧은 문장들(Provider 의 선택 필드, 기본 비어 있음). SRC 의 `exceptions`(약관 감사 메모)는 읽지 않는다."""
        notes = F.field_of(self.provider, "reader_notes", ()) or ()
        return (notes,) if isinstance(notes, str) else tuple(notes)


@dataclass(frozen=True)
class AssembledPost:
    """조립기의 결과. body_markdown 에는 표시 문자가 없다. template_markdown 은 렌더링 전 틀(Fact id 참조) — 첫 문단부터 '주의' 절까지(출처·안내 줄은 제외)로, 숫자가 모두 참조 표시임을 나중에 다시 검사할 수 있다."""
    title: str
    description: str
    body_markdown: str
    category: str
    tags: tuple
    facts_used: tuple
    derived: tuple
    evidence_text: str
    source_name: str
    source_url: str
    source_domain: str
    lang: str
    recipe_id: str
    as_of: str
    template_markdown: str
    source_records: tuple
    dedupe_key: str
    skipped: tuple
    formulas: tuple
    recipe_version: int
    decimals: tuple = ()        # 글의 숫자를 보인 소수 자리 [(단위, 자리)] — 같은 모양으로 다시 그려 보려면 `dict(post.decimals)` 를 `facts.render(context=…)` 에 준다


# ----------------------------------------------------------------------------
# 글을 스스로 검사한다
# ----------------------------------------------------------------------------
_SEPARATOR_ROW = re.compile(r"(?m)^[ \t]*\|?[ \t]*:?-{3,}:?[ \t]*(?:\|[ \t]*:?-{3,}:?[ \t]*)*\|?[ \t]*$")
_LINK_TARGET = re.compile(r"\]\([^)]*\)")
_NUMBER_TOKEN = re.compile(r"\d[\d,]*(?:\.\d+)?")
_FOREIGN_SCRIPT = re.compile(r"[぀-ヿ㐀-鿿]")
_SOURCE_HEADING = re.compile(r"(?m)^## " + re.escape(R.H_SOURCE) + r"[ \t]*$")
_HEADING = re.compile(r"(?m)^## (.+?)[ \t]*$")


def story_of(body):
    """본문에서 출처 절 앞부분('진짜 본문')."""
    found = _SOURCE_HEADING.search(body)
    return body[:found.start()] if found else body


def readable_chars(story):
    """분량을 재는 글자 수: 생성기(`generator._validate_editorial_body`)와 같은 방식이되 표의 구분줄(`---`)은 세지 않는다(그래서 생성기가 세는 수보다 같거나 작다 — 보수적)."""
    text = _SEPARATOR_ROW.sub(" ", story)
    text = re.sub(r"!\[[^\]\n]*\]\([^)\n]*\)", " ", text)
    text = re.sub(r"\[([^\]\n]+)\]\([^)\n]*\)", r"\1", text)
    text = re.sub(r"<[^>\n]+>|[`*_>#|~]", " ", text)
    return len(re.sub(r"\s+", "", text))


def number_tokens(text):
    """글 속 숫자 덩어리(쉼표 뺌). 링크 주소와 맨 주소 안의 숫자는 주장이 아니라서 센 대상에서 뺀다."""
    plain = F.strip_fixed_numeric_terms(re.sub(r"https?://\S+", " ", _LINK_TARGET.sub("]", text)))
    return [token.replace(",", "") for token in _NUMBER_TOKEN.findall(plain)]


def forbidden_found(text):
    """text 에 든 금지 표현 [(범주, 표현)]. 부분 문자열로 찾고 공백·가운뎃점·하이픈을 지운 글에서도 찾는다(`무 조건` 도 `무조건` 이다). 제공처 이용 조건 줄(법적 출처 표시 문구)은 검사하지 않는다 —
    독자용 안내 문장(`reader_notes`)은 우리 글과 같이 검사한다."""
    kept = "\n".join(line for line in text.split("\n") if not line.startswith(ATTRIBUTION_PREFIX))
    spaced = set(T.found_phrases(kept, [phrase for phrases in R.FORBIDDEN_PHRASES.values() for phrase in phrases]))
    return [(category, phrase) for category, phrases in R.FORBIDDEN_PHRASES.items() for phrase in phrases if phrase in kept or phrase in spaced]


def blocked_found(text):
    """text 에 든 차단 낱말(건강·금융·법률·과장·단정) [(범주, 낱말)] — 공백 등을 지운 글에서. 우리 글(틀·라벨)에는 없어야 한다."""
    kept = "\n".join(line for line in text.split("\n") if not line.startswith(ATTRIBUTION_PREFIX))
    return T.blocked_in(kept)


def traceable_numbers(post):
    """글에 나와도 되는 숫자: 쓴 Fact·계산 결과의 값(글에 보인 모양)과 기준일·수집일의 숫자. Fact 의 id·해시·계산식 번호 같은 내부 번호의 숫자는 들어 있지 않다(D-131)."""
    context = dict(post.decimals)
    allowed = set()
    for item in (*post.facts_used, *post.derived):
        if isinstance(item, F.DerivedFact) or item.kind in F.NUMERIC_KINDS:
            if item.value is not None:
                allowed |= set(number_tokens(F.format_with_unit(item.value, item.unit, signed=True, context=context)))
        elif item.value is not None:
            if item.kind in F.DATE_KINDS:
                allowed |= set(number_tokens(F.format_date_ko(item.value)))
            elif item.kind == F.KIND_DATETIME:
                allowed |= set(number_tokens(F.format_period_ko(item.value)))
            else:
                allowed |= set(number_tokens(str(item.value)))
        if item.as_of:
            allowed |= set(number_tokens(F.format_period_ko(item.as_of)))
    for record in post.source_records:
        allowed |= set(number_tokens(F.format_period_ko(record.retrieved_at[:10])))
    return allowed


def latin_words(text):
    return re.findall(r"[A-Za-z]{2,}", _LINK_TARGET.sub("]", text))


def particle_problems(template):
    """앞말의 받침에 따라 달라지는 조사가 참조 표시·닫는 괄호 바로 뒤에 붙었는지(틀 단계) — 있으면 사유 목록."""
    out = []
    for pattern in R.VARYING_PARTICLE_PATTERNS[:2]:
        if re.search(pattern, template):
            out.append("받침에 따라 달라지는 조사가 참조 표시·괄호 바로 뒤에 붙음")
    return out


def post_problems(post, *, allowed_latin=(), min_story_chars=R.MIN_STORY_CHARS):
    """AssembledPost 를 검사해 문제 목록 `["코드 사유", …]` 을 돌려준다(비어 있으면 정상). 값은 싣지 않는다."""
    problems = []
    body, title, description = post.body_markdown, post.title, post.description
    story = story_of(body)
    for name, text in (("제목", title), ("설명", description), ("본문", body)):
        if any(mark in text for mark in R.BLOCKED_TEXT_CHARS):
            problems.append(f"MARKUP {name}에 표시 문자·중괄호·물결표가 있음")
    for category, phrase in forbidden_found("\n".join((title, description, body))):
        problems.append(f"FORBIDDEN 금지 표현({category})이 있음")
        break
    for category, word in blocked_found("\n".join((title, description, body))):
        problems.append(f"FORBIDDEN 차단 낱말({category})이 있음")
        break
    # 제목
    if not title or len(title) > R.MAX_TITLE_CHARS or "\n" in title:
        problems.append("TITLE 제목이 비었거나 길거나 여러 줄임")
    # 설명: 한 문장, 길이 안, 첫 문단과 같음
    plain_desc = re.sub(r"(?<=\d)\.(?=\d)", "", description)
    if not (R.DESCRIPTION_MIN <= len(description) <= R.DESCRIPTION_MAX) or "\n" in description \
            or plain_desc.count(".") != 1 or not plain_desc.endswith(".") or any(mark in plain_desc for mark in "?!"):
        problems.append("DESCRIPTION 설명이 한 문장(60자 이상 155자 이하)이 아님")
    first_paragraph = body.split("\n\n", 1)[0]
    if first_paragraph != description:
        problems.append("DESCRIPTION 설명이 본문 첫 문단과 다름")
    # 절 순서와 표
    headings = _HEADING.findall(body)
    if tuple(headings) != R.SECTION_ORDER:
        problems.append("STRUCTURE 절 제목이 정해진 순서가 아님")
    if not _SEPARATOR_ROW.search(story):
        problems.append("STRUCTURE 표가 없음")
    # 분량
    if readable_chars(story) < min_story_chars:
        problems.append("TOO_SHORT 출처 목록을 뺀 본문이 분량 하한에 못 미침")
    # 숫자: 본문(출처 목록 앞)·제목·설명의 숫자는 모두 쓴 Fact·계산 결과의 값이나 기준일·수집일이고, 근거 텍스트에도 그 숫자뿐이다(id 의 숫자가 '근거'로 세어지지 않는다)
    traceable = traceable_numbers(post)
    if not set(number_tokens(story)) <= traceable or not set(number_tokens(title + "\n" + description)) <= traceable:
        problems.append("UNTRACED 본문에 쓴 값·기준일에서 오지 않은 숫자가 있음")
    if not set(number_tokens(post.evidence_text)) <= traceable:
        problems.append("EVIDENCE 근거 텍스트에 값이 아닌 숫자(내부 번호)가 있음")
    if F.untraced_numbers(post.template_markdown):
        problems.append("UNTRACED 틀에 참조 표시 없는 숫자가 있음")
    # 글자 체계
    allowed = {w for w in allowed_latin}
    if any(word not in allowed for word in latin_words(story + "\n" + title)) or _FOREIGN_SCRIPT.search(story + title):
        problems.append("LANGUAGE 한글 글에 영문·한자·가나가 섞임(라벨·단위로 온 낱말만 허용)")
    # 반복
    seen, repeated = set(), False
    for block in re.split(r"\n\s*\n|\n", story):
        text = " ".join(block.lstrip("-* ").split())
        if len(text) >= 12 and not text.startswith("|"):
            repeated = repeated or text in seen
            seen.add(text)
    if repeated:
        problems.append("REPEAT 같은 문장이 반복됨")
    # 조사 — 틀 단계와 렌더링 결과
    problems += [f"PARTICLE {p}" for p in particle_problems(post.template_markdown)]
    if re.search(R.VARYING_PARTICLE_PATTERNS[2], body):
        problems.append("PARTICLE 조사를 괄호로 둘 다 적은 표현(은(는) 등)이 있음")
    if any(bad in body for bad in F.FORBIDDEN_TEMPLATE_CHARS):
        problems.append("MARKUP Liquid 문자가 있음")
    return problems


# ----------------------------------------------------------------------------
# 조립
# ----------------------------------------------------------------------------
def _source_problem(source):
    if not isinstance(source, SourceInfo):
        return "SourceInfo 가 아님"
    if not isinstance(source.name, str) or not _SOURCE_NAME_RE.fullmatch(source.name) or source.name != source.name.strip():
        return "공식 데이터 이름 모양이 맞지 않음"
    if T.text_problem(source.name) is not None:
        return "공식 데이터 이름에 건강·의료·금융 투자·법률 주제나 과장·단정 낱말이 있음"
    if F.request_url_problems(source.url) or any(ch in source.url for ch in "()") or source.domain is None:
        return "공식 데이터 페이지 주소가 비밀 없는 https 주소가 아님"
    return None


def _note_problem(text):
    """독자용 안내 문장(`reader_notes`)이 쓸 수 있는 글인지: 한 줄·120자 안·숫자나 수 표현 없음·표시 문자 없음·차단 낱말과 금지 표현 없음. 문제 사유 또는 None."""
    if not isinstance(text, str) or not text.strip() or "\n" in text or len(text) > 120:
        return "비었거나 여러 줄이거나 120자를 넘음"
    if F.untraced_numbers(text) or any(c in text for c in R.BLOCKED_TEXT_CHARS) or any(b in text for b in F.FORBIDDEN_TEMPLATE_CHARS):
        return "숫자·수 표현이나 표시 문자가 있음"
    if T.text_problem(text) is not None or forbidden_found(text):
        return "차단 낱말이나 금지 표현이 있음"
    return None


def _attribution_line(source, record):
    """attribution_template 의 `{title}`·`{date}`·`{url}` 만 바꿔 한 줄로. 템플릿이 없으면 빈 문자열, 그 밖의 중괄호가 남으면 None(쓸 수 없다)."""
    template = source.attribution_template
    if not template:
        return ""
    text = template.replace("{title}", source.name).replace("{date}", F.format_period_ko(record.retrieved_at[:10])).replace("{url}", source.url)
    text = " ".join(text.split())
    return None if any(b in text for b in _BRACES) or any(m in text for m in ("⟦", "⟧", "~")) else text


def _sentence(text):
    """독자용 안내 문구를 한 문장으로(끝에 마침표가 없으면 붙인다)."""
    text = " ".join(text.split())
    return text if text[-1] in ".!?" else text + "."


def _closure(ids, pool):
    """참조한 id 에서 계산 결과의 입력을 따라 내려가 쓰인 Fact 와 계산 결과 전부를 모은다(시작 id 는 정렬해 — 문제가 둘 겹쳐도 사유가 해시 시드와 무관하게 같다, D-144)."""
    facts, derived, stack = {}, {}, sorted(ids)
    while stack:
        ident = stack.pop()
        obj = pool.get(ident)
        if isinstance(obj, F.Fact):
            facts[ident] = obj
        elif isinstance(obj, F.DerivedFact) and ident not in derived:
            derived[ident] = obj
            stack.extend(obj.input_fact_ids)
    return facts, derived


def _template_ids(templates, slots):
    ids = set()
    for template in templates:
        for _kind, name in F.references(template):
            if name == "record":
                continue
            target = slots.get(name)
            if target is not None:
                ids.add(getattr(target, "fact_id", None) or getattr(target, "record_id", None))
    return ids


def _describe_derived(obj, pool, depth=0):
    """계산 결과의 라벨·지역(첫 입력을 따라 내려가 찾는다)."""
    for ident in obj.input_fact_ids:
        inner = pool.get(ident)
        if isinstance(inner, F.Fact):
            return inner.label_ko, inner.region_label_ko
        if isinstance(inner, F.DerivedFact) and depth < 8:
            found = _describe_derived(inner, pool, depth + 1)
            if found != (None, None):
                return found
    return None, None


def evidence_text_of(records, facts_used, derived, pool, context=None):
    """렌더링한 Fact 표를 평문으로(Gate 의 근거 텍스트가 된다). 본문에 나온 값과 같은 글자 모양을 쓴다(같은 표시 소수 자리 `context`).
    **값·단위·기준일·지역 이름만** 싣는다 — Fact id·출처 기록 id·Provider id·계산식 번호(`F01`)처럼 숫자를 품은 내부 번호는 싣지 않는다
    (실려 있으면 그 숫자가 '근거 숫자'로 세어져 본문에 끼워 넣은 숫자를 못 잡는다 — 독립 검증 V-03, D-131)."""
    lines = ["근거 자료(규칙 기반 조립, Fact 표)"]
    for record in records:
        lines.append(f"수집: {F.format_period_ko(record.retrieved_at[:10])}")
    lines.append("자료값")
    for fact in facts_used:
        lines.append(f"- {F.describe(fact, context)}")
    lines.append("계산값")
    for item in derived:
        label, region = _describe_derived(item, pool)
        parts = [C.FORMULA_LABELS.get(item.formula_id, "계산값")] + [part for part in (label, region) if part]
        if item.as_of:
            parts.append(F.format_period_ko(item.as_of))
        parts.append(F.format_with_unit(item.value, item.unit, signed=True, context=context))
        lines.append("- " + " | ".join(parts))
    return "\n".join(lines) + "\n"


def _first_fitting(options, slots, pool, fits, context=None):
    """선호 순서의 틀에서 렌더링한 결과가 조건에 맞는 첫 것(틀, 글). 이 자료에는 없는 칸(UnboundSlot)이나 값이 없는 Fact(MissingValue)를 쓰는 틀만 건너뛴다 —
    참조 없는 숫자(UntracedNumber)·깨진 표시 같은 틀의 결함은 건너뛰지 않고 그대로 올라가 글을 만들지 않게 한다."""
    for template in options:
        try:
            text = F.render(F.bind(template, slots), pool, context=context)
        except (F.UnboundSlot, F.MissingValue):
            continue
        if fits(text):
            return template, text
    return None


def _fits_title(text):
    return 0 < len(text) <= R.MAX_TITLE_CHARS and "\n" not in text


def _fits_description(text):
    return R.DESCRIPTION_MIN <= len(text) <= R.DESCRIPTION_MAX and "\n" not in text


def assemble(recipe, facts, today, *, records, source, params=None):
    """(Recipe, Fact 들, 오늘) → AssembledPost 또는 Insufficient. records 는 Fact 들이 가리키는 SourceRecord 들, source 는 SourceInfo.
    params 는 Recipe 에 주는 선택 인자(`key`·`region`·`as_of`)다. 같은 입력이면 항상 같은 글이다.
    **어떤 입력에서도 예외를 올리지 않는다**(fail closed): 값이 범위를 넘거나(VALUE_OUT_OF_RANGE)·자료의 소수 자리가 표시 한도를 넘거나(PRECISION_LIMIT) 예상 밖 오류(INTERNAL_ERROR)면
    글 대신 Insufficient 다(D-137). INTERNAL_ERROR 는 시험(퍼징)이 0 임을 확인한다 — 나오면 틀의 결함이다."""
    try:
        return _assemble(recipe, facts, today, records=records, source=source, params=params)
    except F.PrecisionLimit:
        return Insufficient("PRECISION_LIMIT", "자료의 소수 자리가 표시 한도를 넘어 값을 깎지 않고 글로 쓰지 않는다")
    except F.FactFormatError:
        return Insufficient("VALUE_OUT_OF_RANGE", "값이나 계산 결과가 다룰 수 있는 범위를 넘어 글을 만들지 않는다")
    except F.FactError as exc:
        return Insufficient("PLAN_ERROR", type(exc).__name__)
    except Exception as exc:      # noqa: BLE001 — 글을 내보내지 않는 쪽으로 닫는다(fail closed). 시험이 이 코드가 나오지 않음을 확인한다
        return Insufficient("INTERNAL_ERROR", type(exc).__name__)


def _assemble(recipe, facts, today, *, records, source, params=None):
    try:
        today_date = F.as_date(today)
    except F.FactFormatError:
        return Insufficient("BAD_TODAY", "오늘 날짜 형식이 맞지 않음")
    problem = _source_problem(source)
    if problem:
        return Insufficient("SOURCE_INFO_INVALID", problem)
    inactive = F.provider_active_problem(source.provider)
    if inactive:
        return Insufficient("PROVIDER_NOT_ACTIVE", inactive)
    provider_id = F.field_of(source.provider, "provider_id")
    records_by_id = {}
    for record in records:
        found = F.validate_record(record)
        if found:
            return Insufficient("INVALID_FACTS", "출처 기록이 검증을 통과하지 못함: " + found[0])
        records_by_id[record.record_id] = record
    mine = {}
    for fact in facts:
        found = F.validate_fact(fact)
        if found:
            return Insufficient("INVALID_FACTS", "Fact 가 검증을 통과하지 못함: " + found[0])
        if fact.provider_id == provider_id:
            mine[fact.fact_id] = fact
    ctx = R.PlanContext(recipe, tuple(sorted(mine.values(), key=lambda f: f.fact_id)), today_date, dict(params or {}))
    draft = recipe.plan(ctx)
    if isinstance(draft, Insufficient):
        return draft

    # 쓰인 출처 기록 — 모든 슬롯에서 시작해 계산 입력까지 내려간 Fact 의 기록
    pool = {fact.fact_id: fact for fact in ctx.facts}
    pool.update(draft.registry)
    base_facts, _derived = _closure({getattr(obj, "fact_id", None) for obj in draft.slots.values() if getattr(obj, "fact_id", None)}, pool)
    used_records = []
    for fact in base_facts.values():
        record = records_by_id.get(fact.source_record_id)
        if record is None:
            return Insufficient("MISSING_RECORD", "Fact 가 가리키는 출처 기록이 없음")
        if record.provider_id != provider_id:
            return Insufficient("INVALID_FACTS", "출처 기록의 Provider 가 다름")
        if F.record_expired(record, today_date):
            return Insufficient("RETENTION_EXPIRED", "출처 기록의 보관 기한이 지나 쓰지 않는다")
        if F.period_start(F.parse_as_of(record.retrieved_at)) > today_date:
            return Insufficient("FUTURE_RECORD", "출처 기록의 수집일이 오늘보다 뒤라 쓰지 않는다")
        if record not in used_records:
            used_records.append(record)
    used_records.sort(key=lambda r: (r.retrieved_at, r.record_id))
    latest_record = used_records[-1]
    slots = dict(draft.slots)
    slots["record"] = latest_record
    pool[latest_record.record_id] = latest_record

    notes = list(source.reader_notes)              # 독자용으로 승인된 안내 문장뿐 — Provider 의 `exceptions`(약관 감사 메모)는 읽지 않는다(D-138)
    for text in notes:
        if _note_problem(text) is not None:
            return Insufficient("READER_NOTE_UNSAFE", "독자용 안내 문장이 한 줄·숫자 없음·차단 낱말 없음 규칙을 지키지 못해 옮기지 않는다")
    attribution = _attribution_line(source, latest_record)
    if attribution is None:
        return Insufficient("ATTRIBUTION_TEMPLATE_INVALID", "출처 표시 문구에 쓸 수 없는 중괄호·표시 문자가 있음")

    try:
        context = dict(draft.context)
        title_pick = _first_fitting(draft.titles, slots, pool, _fits_title, context)
        lead_pick = _first_fitting(draft.leads, slots, pool, _fits_description, context)
        if title_pick is None:
            return Insufficient("TITLE_LENGTH", "제목이 60자 안으로 만들어지지 않음")
        if lead_pick is None:
            return Insufficient("DESCRIPTION_LENGTH", "설명이 60자 이상 155자 이하의 한 문장으로 만들어지지 않음")
        title_template, title = title_pick
        lead_template, lead = lead_pick
        parts = [lead_template, R.INTRO_TEMPLATE]
        for heading, blocks in draft.sections:
            parts.append("## " + heading + "\n\n" + "\n\n".join(blocks))
        caution_lines = list(R.CAUTION_COMMON) + list(draft.caveats)
        parts.append("## " + R.H_CAUTION + "\n\n" + "\n".join(caution_lines + [R.READER_NOTE_PREFIX + _sentence(text) for text in notes]))
        template = "\n\n".join(parts)
        bound = F.bind(template, slots)
        rendered = F.render(bound, pool, context=context)
    except F.UntracedNumber as exc:
        return Insufficient("TEMPLATE_UNTRACED", "틀에 참조 표시 없는 숫자·수 표현: " + ", ".join(exc.numbers[:3]))
    except F.FactError as exc:
        return Insufficient("RENDER_ERROR", type(exc).__name__)

    link = f"[공식 자료]({source.url})"
    rendered = rendered.replace(R.SOURCE_LINK_TOKEN, link)
    source_lines = [f"- [{source.name}]({source.url}) — 열람 {F.format_period_ko(latest_record.retrieved_at[:10])}"]
    if attribution:
        source_lines.append(ATTRIBUTION_PREFIX + attribution)
    notice = F.render(R.NOTICE_TEMPLATE, pool, context=context)
    body = rendered + "\n\n## " + R.H_SOURCE + "\n\n" + "\n".join(source_lines) + "\n\n---\n\n" + notice + "\n"

    base_facts, derived = _closure(_template_ids([template], slots) | {latest_record.record_id}, pool)
    facts_used = tuple(sorted(base_facts.values(), key=lambda f: (f.key, f.region or "", f.as_of or "", f.fact_id)))
    derived_used = tuple(sorted(derived.values(), key=lambda d: (d.formula_id, d.fact_id)))
    evidence = evidence_text_of(used_records, facts_used, derived_used, pool, context)
    topic = draft.topic
    tags, seen_tags = [], set()
    for tag in draft.tags:
        if tag and tag not in seen_tags and len(tag) <= 20:
            seen_tags.add(tag)
            tags.append(tag)
    post = AssembledPost(
        title=title, description=lead, body_markdown=body, category=R.TOPIC_CATEGORY[topic], tags=tuple(tags[:MAX_TAGS]),
        facts_used=facts_used, derived=derived_used, evidence_text=evidence, source_name=source.name, source_url=source.url,
        source_domain=source.domain, lang=LANG, recipe_id=recipe.recipe_id, as_of=draft.as_of, template_markdown=bound,
        source_records=tuple(used_records), dedupe_key="|".join(draft.dedupe), skipped=tuple(draft.skipped),
        formulas=tuple(sorted({d.formula_id for d in derived_used})), recipe_version=recipe.version, decimals=tuple(sorted(context.items())))
    allowed_latin = set()
    for fact in facts_used:
        for text in (fact.label_ko, fact.region_label_ko, fact.unit):
            allowed_latin.update(re.findall(r"[A-Za-z]{2,}", text or ""))
    problems = post_problems(post, allowed_latin=allowed_latin, min_story_chars=recipe.min_story_chars)
    if problems:
        code = problems[0].split(" ", 1)[0]
        return Insufficient("TOO_SHORT" if code == "TOO_SHORT" else "QUALITY_CHECK_FAILED", problems[0])
    if len({d.formula_id for d in derived_used}) < MIN_DISTINCT_FORMULAS:
        return Insufficient("NO_ANALYSIS", "자체 계산이 모자라(서로 다른 계산식 둘 미만) 글을 만들지 않는다")
    return post

