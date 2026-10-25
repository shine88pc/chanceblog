"""신뢰할 수 없는 텍스트(이슈 본문·AI 출력·예외 문구)를 로그·코멘트·PR 본문에 안전하게 옮기는 순수 함수 모음(I/O 없음).

막으려는 것
- Actions 로그의 워크플로 명령: 줄 시작의 `::`(러너는 앞 공백을 지운 뒤 인식한다)와 줄 어디서든 인식되는 레거시 `##[`
- 마크다운 렌더링: 이미지·링크·멘션이 공개 코멘트·PR 본문에서 그대로 살아나는 것 → 코드 스팬·코드 펜스에 넣는다
- 비밀 모양 문자열이 로그에 출력되는 것

이 모듈은 pipeline/edits 의 다른 모듈에서만 가져다 쓰고, 다른 pipeline/edits 모듈을 import 하지 않는다(순환 방지).
"""
import re
import unicodedata

from pipeline.llm import mask
from pipeline.secret_patterns import SECRET_PATTERNS, find_secrets

# ----------------------------------------------------------------------------
# 외부 AI(Gemini)·이미지 검색(Unsplash)으로 보내기 전 점검
# ----------------------------------------------------------------------------
# 이슈·PR 본문은 공개다. 소유자가 실수로 키·주민등록번호·카드번호를 요청문에 붙여 넣으면 외부 서비스와 공개 PR 로 나간다.
# 이메일·전화번호는 연락처 페이지 수정이 정당한 용도라 막지 않는다.
KIND_RRN = "주민등록번호 모양"
KIND_CARD = "카드번호 모양"
PERSONAL_KINDS = (KIND_RRN, KIND_CARD)      # 키·토큰이 아닌 종류(거부 안내문이 키 폐기 안내와 갈린다)
_DASHES = "\N{HYPHEN}\N{NON-BREAKING HYPHEN}\N{FIGURE DASH}\N{EN DASH}\N{EM DASH}\N{HORIZONTAL BAR}\N{MINUS SIGN}"
# 주민등록번호 모양: 생년월일(월 01-12·일 01-31) + 선택적 구분 + 성별 자리 1-8 + 6자리의 13자리. 더 긴 숫자의 일부(앞뒤에 숫자)는 건너뛰고,
# Unsplash 사진 id(`photo-1507146426996-…`, `premium_photo-…`)의 13자리 시각값만 예외로 한다. 영문·밑줄·하이픈이 앞에 붙은 값은 예외가 아니다
# (`ID900101-1234567`·`_9001011234567`).
_RRN = re.compile(rf"(?<![0-9])(?<!photo-)[0-9]{{2}}(?:0[1-9]|1[0-2])(?:0[1-9]|[12][0-9]|3[01])(?: ?[-{_DASHES}] ?| )?[1-8][0-9]{{6}}(?![0-9])")
# 카드번호 모양: 흔한 카드번호(PAN) 탐지기와 같은 방식 — 숫자 묶음 모양 + 길이별 카드사 식별 번호(IIN) 접두사 + Luhn 검사 + 같은 숫자 반복 제외.
# 공백·하이픈으로 이은 일반 숫자 목록(연도·번호표·일련번호)과 13~14자리 시각값·ISBN·바코드는 묶음 모양이나 접두사가 맞지 않아 걸리지 않는다.
_SEPARATOR = rf"[-{_DASHES} ]{{1,3}}"
# AdSense 게시자 id(`ca-pub-` + 16자리)는 카드번호가 아니다
_DIGIT_RUN = re.compile(rf"(?<![0-9])(?<!pub-)[0-9]+(?:{_SEPARATOR}[0-9]+)*")
# 널리 쓰는 묶음(자릿수): 4-4-4-4(16)·4-4-4-4-1~3(17~19)·4-6-5(15, Amex)·4-6-4(14, Diners)·4-4-4-1(13, 예전 Visa). 13~19자리 연속 숫자도 후보다
_CARD_SHAPES = frozenset({(4, 4, 4, 4), (4, 4, 4, 4, 1), (4, 4, 4, 4, 2), (4, 4, 4, 4, 3), (4, 6, 5), (4, 6, 4), (4, 4, 4, 1)})
_CARD_PREFIX = {13: re.compile(r"4"), 14: re.compile(r"3[0689]")}     # 짧은 길이는 실제 쓰이는 카드사로 좁힌다(Visa · Diners)
_CARD_PREFIX_DEFAULT = re.compile(r"2[2-7]|[3-9]")                    # 15~19자리: 0·1·20·21·28·29 로 시작하는 값(시각값·일련번호 등)은 카드가 아니다
# 보이지 않는 서식 문자(제로폭 공백·방향 표시·단어 결합자·소프트 하이픈·BOM). 소스에 문자를 직접 쓰지 않고 코드 값으로 만든다.
_INVISIBLE = re.compile("[" + "".join(chr(c) for c in (*range(0x200B, 0x2010), *range(0x202A, 0x202F), *range(0x2060, 0x2065), 0x00AD, 0xFEFF)) + "]")
# 프롬프트 구분자: `<<<REQUEST`·`REQUEST>>>` 처럼 대문자 이름에 붙은 꺾쇠 세 개(요청문이 구분자를 흉내 내 블록을 닫지 못하게 지운다)
_DELIMITER = re.compile(r"<<<[ \t]*[A-Z][A-Z_]*|[A-Z][A-Z_]*[ \t]*>>>")


def neutralize(line):
    """한 줄 문자열이 Actions 로그에서 워크플로 명령으로 해석되지 않게 한다: `##[` 는 어디에 있든, 줄 시작의 `::` 는 `: :` 로 깨뜨린다."""
    while "##[" in line:
        line = line.replace("##[", "# #[")
    if line.lstrip().startswith("::"):
        line = line.replace("::", ": :", 1)
    return line


def clip(text, limit, markdown=False):
    """한 줄로 접고 limit 자로 자른다. markdown=True(공개 코멘트용)면 자른 지점이 코드 스팬 안일 때 열린 스팬을 통째로 뺀다.

    코드 스팬(`…`) 한가운데를 자르면 닫는 백틱이 사라져 뒤의 글자가 마크다운으로 살아난다. 코드 스팬 안의 텍스트에는 백틱이 없으므로
    (`code()` 가 지운다) 자른 결과의 백틱 수가 홀수이면 마지막 백틱이 닫히지 않은 스팬의 시작이다."""
    flat = re.sub(r"\s+", " ", str(text)).strip()[:limit]
    if markdown and flat.count("`") % 2:
        flat = flat[:flat.rfind("`")].rstrip()
    return flat


def one_line(text, limit=90, markdown=False):
    """한 줄로 접고 자르며 멘션(@)과 워크플로 명령 모양을 무력화한다(커밋 제목·PR 제목·사유 문장·로그용). markdown: `clip` 참고."""
    return neutralize(clip(text, limit, markdown).replace("@", "@\N{ZERO WIDTH SPACE}"))


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
    # mask() 는 지금 SECRET_PATTERNS 를 이미 모두 적용하므로 이 반복은 중복이다(무해). mask() 구현이 바뀌어도 공용 패턴은 가린다는 보장을 이 모듈에 남겨 둔다.
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


def _card_candidates(run):
    """숫자 묶음 한 줄(공백·하이픈으로 이은 숫자들)에서 카드번호 모양인 숫자열을 하나씩 돌려준다.

    13~19자리 연속 숫자 하나, 또는 `_CARD_SHAPES` 의 묶음 모양이 이어진 숫자들. 다른 숫자 뒤에 붙어 있어도("주문번호 123 4111 …")
    찾도록 모든 시작점을 본다."""
    groups = re.split(_SEPARATOR, run)
    for start in range(len(groups)):
        if 13 <= len(groups[start]) <= 19:
            yield groups[start]
        for count in range(2, 6):
            window = groups[start:start + count]
            if len(window) == count and tuple(len(group) for group in window) in _CARD_SHAPES:
                yield "".join(window)


def _card_like(text):
    for run in _DIGIT_RUN.findall(text):
        for digits in _card_candidates(run):
            if (len(set(digits)) > 1                                                  # 0000…·8888… 같은 자리 채우기 값은 Luhn 을 우연히 통과해도 번호가 아니다
                    and _CARD_PREFIX.get(len(digits), _CARD_PREFIX_DEFAULT).match(digits) and _luhn_ok(digits)):
                return True
    return False


def _fold(text):
    """전각 숫자·NBSP·U+2011 같은 호환 문자를 ASCII 꼴로 접고 보이지 않는 서식 문자를 지운다 — 웹·PDF 에서 복사한 번호가 그 꼴로 붙어도 같게 본다."""
    return _INVISIBLE.sub("", unicodedata.normalize("NFKC", text))


def sensitive_kinds(text):
    """text 안의 비밀·민감 식별자 종류(라벨)만 돌려준다 — 값은 돌려주지 않는다. 이메일·전화번호는 대상이 아니다."""
    text = text or ""
    kinds = [label for label, _preview in find_secrets(text)]
    folded = _fold(text)
    if _RRN.search(folded):
        kinds.append(KIND_RRN)
    if _card_like(folded):
        kinds.append(KIND_CARD)
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
    """거부 사유 문장(공개 코멘트에 들어간다). 값은 되풀이하지 않는다. 안내는 걸린 종류에 맞춘다:
    키·토큰은 이슈가 공개라 폐기·재발급, 주민등록번호·카드번호 모양은 실제 번호일 때의 대응과 번호가 아닐 때(숫자 표 등) 고치는 법."""
    where = "; ".join(f"{name}: {', '.join(kinds)}" for name, kinds in problems)
    found = [kind for _name, kinds in problems for kind in kinds]
    message = f"AI·이미지 검색으로 보내지 않았습니다 — 비밀 값이나 민감한 식별자(주민등록번호·카드번호)로 보이는 문자열이 있습니다({where})."
    if any(kind not in PERSONAL_KINDS for kind in found):
        message += (" 이 이슈는 공개되어 있으므로 키·토큰을 붙여 넣었다면 이미 노출된 것입니다: 즉시 폐기하고 새로 발급하세요"
                    "(값은 이 코멘트에 적지 않았습니다).")
    if any(kind in PERSONAL_KINDS for kind in found):
        message += (" 숫자 묶음이 주민등록번호·카드번호처럼 보입니다. 실제 번호라면 이 공개 이슈에 이미 노출된 것이니 이슈를 삭제하고 카드사 등 해당 기관에 알려 주세요"
                    "(값은 이 코멘트에 적지 않았습니다). 번호가 아니라 일련번호·숫자 표라면 숫자 묶음을 줄이거나 설명 문장으로 바꿔 주세요.")
    message += " 해당 부분을 지우고 새 이슈로 다시 요청해 주세요."
    if any(name == "페이지 원문" for name, _kinds in problems):
        message += " 페이지 원문에 들어 있다면 먼저 그 페이지에서 해당 값을 지워야 AI 수정이 가능합니다."
    return message


def strip_delimiters(text):
    """프롬프트에 넣는 필드에서 구분자 문자열(`<<<REQUEST`·`REQUEST>>>` 같은 꼴)을 지운다.

    한 번만 지우면 남은 조각이 이어 붙어 구분자를 다시 만든다(`REQUEST<<<X>>>` → `REQUEST>>>`). 더 지울 것이 없을 때까지 되풀이한다 —
    매번 글자가 줄어드므로 끝난다."""
    text = text or ""
    while True:
        stripped = _DELIMITER.sub("", text)
        if stripped == text:
            return text
        text = stripped
