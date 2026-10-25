"""신뢰할 수 없는 텍스트(이슈 본문·AI 출력·예외 문구)를 로그·코멘트·PR 본문에 안전하게 옮기는 순수 함수 모음(I/O 없음).

막으려는 것
- Actions 로그의 워크플로 명령: 줄 시작의 `::`(러너는 앞 공백을 지운 뒤 인식한다)와 줄 어디서든 인식되는 레거시 `##[`
- 마크다운 렌더링: 이미지·링크·멘션이 공개 코멘트·PR 본문에서 그대로 살아나는 것 → 코드 스팬·코드 펜스에 넣는다
- 비밀 모양 문자열이 로그에 출력되는 것

이 모듈은 pipeline/edits 의 다른 모듈에서만 가져다 쓰고, 다른 pipeline/edits 모듈을 import 하지 않는다(순환 방지).
"""
import re

from pipeline.llm import mask
from pipeline.secret_patterns import SECRET_PATTERNS, find_secrets

# ----------------------------------------------------------------------------
# 외부 AI(Gemini)·이미지 검색(Unsplash)으로 보내기 전 점검
# ----------------------------------------------------------------------------
# 이슈·PR 본문은 공개다. 소유자가 실수로 키·주민등록번호·카드번호를 요청문에 붙여 넣으면 외부 서비스와 공개 PR 로 나간다.
# 이메일·전화번호는 연락처 페이지 수정이 정당한 용도라 막지 않는다.
_DASHES = "‐‑–—"
# 주민등록번호 모양: 생년월일(월 01-12·일 01-31) + 선택적 구분 + 성별 자리 1-8 + 6자리의 13자리. 앞뒤에 숫자·영문·밑줄·하이픈이 붙어 있으면
# 식별자의 일부(예: Unsplash 사진 id `photo-1507146426996-…` 의 13자리 시각값)로 보고 건너뛴다.
_RRN = re.compile(rf"(?<![0-9A-Za-z_-])[0-9]{{2}}(?:0[1-9]|1[0-2])(?:0[1-9]|[12][0-9]|3[01])[-{_DASHES} ]?[1-8][0-9]{{6}}(?![0-9A-Za-z_-])")
# 카드번호 모양: 숫자 15~19개(숫자 묶음 사이에 공백·하이픈 하나까지 허용) + Luhn 검사 통과. 전화번호(10~11자리)·13자리 시각값은 걸리지 않는다
_DIGIT_RUN = re.compile(r"[0-9]+(?:[ -][0-9]+)*")
# 프롬프트 구분자: `<<<REQUEST`·`REQUEST>>>` 처럼 대문자 이름에 붙은 꺾쇠 세 개(요청문이 구분자를 흉내 내 블록을 닫지 못하게 지운다)
_DELIMITER = re.compile(r"<<<[ \t]*[A-Z][A-Z_]*|[A-Z][A-Z_]*[ \t]*>>>")


def neutralize(line):
    """한 줄 문자열이 Actions 로그에서 워크플로 명령으로 해석되지 않게 한다: `##[` 는 어디에 있든, 줄 시작의 `::` 는 `: :` 로 깨뜨린다."""
    while "##[" in line:
        line = line.replace("##[", "# #[")
    if line.lstrip().startswith("::"):
        line = line.replace("::", ": :", 1)
    return line


def one_line(text, limit=90):
    """한 줄로 접고 자르며 멘션(@)과 워크플로 명령 모양을 무력화한다(커밋 제목·PR 제목·사유 문장·로그용)."""
    flat = re.sub(r"\s+", " ", str(text)).strip()[:limit].replace("@", "@​")
    return neutralize(flat)


def code(text, limit=90):
    """신뢰할 수 없는 문자열을 한 줄 코드 스팬으로(마크다운·멘션·줄 시작 트레일러·워크플로 명령을 무력화)."""
    return "`" + re.sub(r"[`\s]+", " ", str(text)).strip()[:limit] + "`"


def fenced(text, info=""):
    """내용을 바꾸지 않고 코드 펜스에 넣는다. 펜스는 틸드(~)이고 길이는 내용 속 가장 긴 틸드 연속보다 길다(최소 4개).

    백틱 펜스는 내용 속 ``` 줄이 닫아 버릴 수 있다. 길이를 내용에 맞추면 내용을 고치지 않고도 펜스를 닫을 수 없다."""
    longest = max((len(run) for run in re.findall(r"~+", text)), default=0)
    fence = "~" * max(4, longest + 1)
    return f"{fence}{info}\n{text}\n{fence}"


def redact(text):
    """비밀로 보이는 문자열(SECRET_PATTERNS 와 llm.mask 가 아는 형식)을 `***` 로 가린다 — 로그·DRY_RUN 출력용."""
    out = mask(text)
    for _label, rx in SECRET_PATTERNS:
        out = rx.sub("***", out)
    return out


def log_text(text, limit=300):
    """로그 한 줄: 비밀을 가리고 한 줄로 접어 limit 자로 자른다(무력화로 늘어난 글자까지 포함해 limit 를 넘지 않는다)."""
    return one_line(redact(text), limit)[:limit]


def _luhn_ok(digits):
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2:
            d = d * 2 - 9 if d > 4 else d * 2
        total += d
    return total % 10 == 0


def _card_like(text):
    for run in _DIGIT_RUN.findall(text):
        groups = re.split(r"[ -]", run)
        for start in range(len(groups)):          # 다른 숫자 뒤에 붙어 있어도 이어지는 묶음의 모든 시작점을 본다
            digits = ""
            for group in groups[start:]:
                digits += group
                if len(digits) > 19:
                    break
                if len(digits) >= 15 and _luhn_ok(digits):
                    return True
    return False


def sensitive_kinds(text):
    """text 안의 비밀·민감 식별자 종류(라벨)만 돌려준다 — 값은 돌려주지 않는다. 이메일·전화번호는 대상이 아니다."""
    text = text or ""
    kinds = [label for label, _preview in find_secrets(text)]
    if _RRN.search(text):
        kinds.append("주민등록번호 모양")
    if _card_like(text):
        kinds.append("카드번호 모양")
    return kinds


def outbound_problems(named_texts):
    """외부로 보내기 전 점검. named_texts: {표시 이름: 텍스트}. 걸린 항목마다 (표시 이름, [종류, …]) 를 돌려준다(값은 없다)."""
    found = []
    for name, text in named_texts.items():
        kinds = sensitive_kinds(text)
        if kinds:
            found.append((name, kinds))
    return found


def outbound_refusal(problems):
    """거부 사유 문장(공개 코멘트에 들어간다). 값은 되풀이하지 않고, 이슈가 공개라 붙여 넣은 키는 폐기·재발급하라고 안내한다."""
    where = "; ".join(f"{name}: {', '.join(kinds)}" for name, kinds in problems)
    message = (f"AI·이미지 검색으로 보내지 않았습니다 — 비밀 값이나 민감한 식별자(주민등록번호·카드번호)로 보이는 문자열이 있습니다({where}). "
               "이 이슈는 공개되어 있으므로 키·토큰을 붙여 넣었다면 이미 노출된 것입니다: 즉시 폐기하고 새로 발급하세요"
               "(값은 이 코멘트에 적지 않았습니다). 해당 부분을 지우고 새 이슈로 다시 요청해 주세요.")
    if any(name == "페이지 원문" for name, _kinds in problems):
        message += " 페이지 원문에 들어 있다면 먼저 그 페이지에서 해당 값을 지워야 AI 수정이 가능합니다."
    return message


def strip_delimiters(text):
    """프롬프트에 넣는 필드에서 구분자 문자열(`<<<REQUEST`·`REQUEST>>>` 같은 꼴)을 지운다."""
    return _DELIMITER.sub("", text or "")
