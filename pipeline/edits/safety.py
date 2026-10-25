"""신뢰할 수 없는 텍스트(이슈 본문·AI 출력·예외 문구)를 로그·코멘트·PR 본문에 안전하게 옮기는 순수 함수 모음(I/O 없음).

막으려는 것
- Actions 로그의 워크플로 명령: 줄 시작의 `::`(러너는 앞 공백을 지운 뒤 인식한다)와 줄 어디서든 인식되는 레거시 `##[`
- 마크다운 렌더링: 이미지·링크·멘션이 공개 코멘트·PR 본문에서 그대로 살아나는 것 → 코드 스팬·코드 펜스에 넣는다
- 비밀 모양 문자열이 로그에 출력되는 것

이 모듈은 pipeline/edits 의 다른 모듈에서만 가져다 쓰고, 다른 pipeline/edits 모듈을 import 하지 않는다(순환 방지).
"""
import re

from pipeline.llm import mask
from pipeline.secret_patterns import SECRET_PATTERNS


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
