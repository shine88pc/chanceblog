"""얇음 측정(S2c-1) — 조립된 글(`AssembledPost`)이 값이 달라져도 변하지 않는 틀 글자에 얼마나 기대는지를 재는 **순수 함수**. 표준 라이브러리와 이 경로의 모듈(`facts`·`recipes`·`fact_assembler`)만 쓰고
시계·난수·파일 입출력·네트워크·AI 가 없다. 같은 글이면 같은 값이다.

왜 필요한가: 지금의 품질 그림자 보고서는 '표 행 수·직접 계산 낱말' 로 직접 작업 신호를 세어 얇은 글도 모두 '있음' 으로 나온다(얇음을 가르지 못한다). 이 모듈은 글을 만들 때 **틀을 아는 상태에서**
(참조 표시가 든 틀과 계산 결과 목록을 가진 채로) 일곱 값을 센다 — 글자만 읽는 도구보다 정확하다.

| 칸 | 뜻 |
|---|---|
| `fixed_pct` | 고정 글자 비율(%) — 틀에서 참조 표시를 지운 글자 ÷ 본문(출처 목록 앞) 글자. 글자 수는 생성기 방식(공백·표시 기호·표 구분줄 제외). `tests/fact_helpers.quality_metrics` 와 같은 정의라 전후를 견줄 수 있다 |
| `pure_units` | 값 참조가 하나도 없는 문장·항목 수(순수 고정 문장) — 날짜·이름·단위 칸만 있는 문장은 세지 않는다 |
| `value_units` | 값 참조(`F`·`S`·`A`·`V`)가 든 문장·항목 수 |
| `c_units` | 값 문장 가운데 'C 등급 계산'(표 밖 값이나 기준과 견주는 계산: `C_FORMULAS`)이 든 것의 수 |
| `calc_claims` | '이 글이 직접 계산했다·골랐다·셌다' 를 말하는 문장·항목 수(`CALC_CLAIM_RE`) |
| `date_marks` | 받은 날짜를 독자에게 말하는 곳의 수 — 틀의 수집일 참조(`T`) + 출처 절에 적힌 열람일 |
| `evidence_chars` | 근거 텍스트의 글자 수(품질 관문의 상한 `MAX_EVIDENCE_CHARS` 와 견준다) |

문장·항목은 문단의 문장·목록 항목뿐이다(소제목과 표 줄은 세지 않는다). **어느 값도 판정이 아니라 사람이 먼저 볼 순서를 정하는 신호다**(품질 그림자의 원칙) — 이 모듈은 보류 코드를 만들지 않고 글을 바꾸지도 않는다.
설명: docs/FACT_PATH.md §16-7
"""
import re

from pipeline import fact_assembler as A
from pipeline import facts as F
from pipeline import recipes as R

VALUE_KINDS = frozenset("FSAV")           # 값을 글에 싣는 참조 표시: F 값+단위·S 부호 있는 값·A 크기·V 값만(날짜 D·T·이름 L·지역 R·단위 U 는 값이 아니다)
# 'C 등급' 계산: 글의 표 안에서 눈으로 뺄 수 있는 값(재배열·산술)이 아니라 표 밖의 값이나 기준과 견주는 계산 — 전년 같은 기간·순위·범위 안의 위치·중앙값·기준 이상 개수와 S2c-1 의 같은 달 순위·마지막으로 낮은 달
C_FORMULAS = frozenset({"F03_yoy", "F04_rank", "F11_range_position", "F14_median", "F16_count_between", "F17_season_rank", "F18_last_lower"})
CALC_CLAIM_RE = re.compile(r"직접 (?:계산|골랐|센)|이 글이 (?:센|직접)")
FIELDS = ("fixed_pct", "pure_units", "value_units", "c_units", "calc_claims", "date_marks", "evidence_chars")
COUNTED_KINDS = ("sentence", "bullet")      # 세는 단위: 문단의 문장과 목록 항목(소제목·표 줄은 세지 않는다)


def split_units(template):
    """결합한 글 틀(`AssembledPost.template_markdown`) → [(구역 이름, 종류, 글)]. 종류: heading(소제목)·table_head(표 머리줄)·table_row(표 자료줄)·bullet(목록 항목 한 줄)·
    sentence(문단 한 줄을 마침표·물음표·느낌표 뒤 공백에서 나눈 문장)."""
    units, section = [], "머리"
    for block in re.split(r"\n\n+", template):
        block = block.strip("\n")
        if not block:
            continue
        if block.startswith("## "):
            heading, _sep, body = block.partition("\n")
            section = heading[3:].strip()
            units.append((section, "heading", heading))
            block = body.strip("\n")
            if not block:
                continue
        lines = block.split("\n")
        if all(line.lstrip().startswith("|") for line in lines):
            units.append((section, "table_head", lines[0]))
            units.extend((section, "table_row", line) for line in lines[2:])
        elif all(line.startswith("- ") for line in lines):
            units.extend((section, "bullet", line) for line in lines)
        else:
            for line in lines:
                if line.startswith("- "):
                    units.append((section, "bullet", line))
                elif line.lstrip().startswith("|"):
                    units.append((section, "table_row", line))
                else:
                    units.extend((section, "sentence", sentence) for sentence in re.split(r"(?<=[.!?])\s+", line.strip()) if sentence)
    return units


def classify(text, formula_of):
    """문장·항목 하나의 틀 글 → (종류, 값 참조가 가리키는 계산 결과의 계산식 번호 집합). 종류: pure(참조 없음)·stamp(날짜·이름·단위 참조뿐)·value(값 참조가 있음).
    formula_of 는 {계산 결과 id: 계산식 번호}."""
    refs = F.references(text)
    value_refs = [ref for kind, ref in refs if kind in VALUE_KINDS]
    cls = "pure" if not refs else ("value" if value_refs else "stamp")
    return cls, {formula_of[ref] for ref in value_refs if ref in formula_of}


def _source_section(body):
    marker = "## " + R.H_SOURCE
    return body.split(marker, 1)[1] if marker in body else ""


def date_marks_of(post):
    """받은 날짜를 말하는 곳: 틀의 수집일 참조(`⟦T:…⟧`) 수 + 출처 절(출처 줄·이용 조건 줄)에 적힌 수집일의 횟수. 표 칸의 기준일과 겹치지 않는다."""
    refs = sum(1 for kind, _ref in F.references(post.template_markdown) if kind == "T")
    sources = _source_section(post.body_markdown)
    dates = {F.format_period_ko(record.retrieved_at[:10]) for record in post.source_records}
    return refs + sum(sources.count(text) for text in dates)


def measure(post):
    """조립된 글 → 일곱 값의 사전(`FIELDS` 순서, 모두 정수). 판정이 아니라 신호다. 글(`AssembledPost`)의 칸 `template_markdown`·`body_markdown`·`derived`·`source_records`·`evidence_text` 만 읽는다."""
    story = A.story_of(post.body_markdown)
    total = A.readable_chars(story)
    literal = A.readable_chars(F.REF_RE.sub("", post.template_markdown).replace(R.SOURCE_LINK_TOKEN, ""))
    formula_of = {item.fact_id: item.formula_id for item in post.derived}
    pure = value = c_units = claims = 0
    for _section, kind, text in split_units(post.template_markdown):
        if kind not in COUNTED_KINDS:
            continue
        cls, formulas = classify(text, formula_of)
        pure += cls == "pure"
        value += cls == "value"
        c_units += cls == "value" and bool(formulas & C_FORMULAS)
        claims += bool(CALC_CLAIM_RE.search(text))
    return {"fixed_pct": round(100 * literal / total) if total else 0, "pure_units": pure, "value_units": value, "c_units": c_units, "calc_claims": claims,
            "date_marks": date_marks_of(post), "evidence_chars": len(post.evidence_text)}
