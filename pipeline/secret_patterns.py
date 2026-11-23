"""비밀 값으로 보이는 문자열 패턴(단일 원천).

저장소 검증기(scripts/validate_repo.py), 이슈 수정 사후 검증(pipeline/edits/checks.py),
이슈 수정의 로그 정제·외부 전송 전 점검(pipeline/edits/safety.py), 병합 알림 자동화의 보낼 글 거르기(pipeline/auto_notice.py),
로그·이력 마스킹(pipeline/llm.py 의 mask())이 함께 쓴다. 패턴을 추가·수정하면 모두에 적용된다.
`find_secrets` 와 검증기는 원문과 함께 검사용 사본(`scan_copy`: 전각·보이지 않는 글자·결합 글자를 접은 것)도 본다 — 키를 그런 글자로 쪼개도 걸린다(D-352).
(소비처 목록은 tests/test_security_settings.py 가 실제 import 와 대조한다.)
"""
import re
import unicodedata

SECRET_PATTERNS = [
    ("Google API 키", re.compile(r"AIza[0-9A-Za-z_\-]{35}")),
    # 2026-10-18 공개 이력에 남았던 123.txt(D-30)의 형식: 점이 든 접두사 'AQ.' + 영숫자·-·_ 40자 이상(총 53자 안팎).
    # 앞 글자가 영문자·숫자면 제외한다(FAQ. 같은 단어 끝). 단어 경계(\b) 대신 look-behind 를 쓴다: \b 는
    # 한글·밑줄 바로 뒤에 붙은 키('키는AQ.…')를 놓친다.
    ("Google API 키(새 형식)", re.compile(r"(?<![A-Za-z0-9])AQ\.[0-9A-Za-z_\-]{40,}")),
    ("Google OAuth 클라이언트 시크릿", re.compile(r"GOCSPX-[0-9A-Za-z_\-]{20,}")),
    ("Google refresh token", re.compile(r"\b1//0[0-9A-Za-z_\-]{40,}")),
    ("Google access token", re.compile(r"\bya29\.[0-9A-Za-z_\-]{30,}")),
    ("GitHub 토큰", re.compile(r"\bgh[pousr]_[0-9A-Za-z]{36,}")),
    ("GitHub PAT", re.compile(r"\bgithub_pat_[0-9A-Za-z_]{40,}")),
    ("개인 키 블록", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY(?: BLOCK)?-----")),
    ("Slack 토큰", re.compile(r"\bxox[baprs]-[0-9A-Za-z\-]{10,}")),
    ("AWS 액세스 키", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    # 텔레그램 봇 토큰: '<봇 번호 숫자>:<영숫자·-·_ 35자>'(실제 8~10자리·35자, 여유를 둬 6~12자리·30~50자). 이 서비스는 토큰이 요청 주소의 경로
    # (https://api.telegram.org/bot<토큰>/sendMessage)에 들어가 오류 문구·스택트레이스에 주소째 새기 쉽다 — 알림 모듈(pipeline/notify.py)이
    # 정확한 값 치환에 더해 이 모양으로도 한 번 더 가린다(docs/SECURITY_GUARDRAILS.md G-C12). 앞에는 제한이 없다 — 주소 경로에서는 'bot' 글자 바로 뒤에 붙는다
    # (…/bot<토큰>/…). 비밀 절반 뒤에 영숫자·-·_ 가 더 이어지면 토큰이 아니라 다른 긴 문자열이라 제외한다.
    ("Telegram 봇 토큰", re.compile(r"[0-9]{6,12}:[A-Za-z0-9_\-]{30,50}(?![A-Za-z0-9_\-])")),
    ("sk- 형식 API 키", re.compile(r"\bsk-[A-Za-z0-9]{32,}\b")),
    # 값이 환경변수 이름(대문자_숫자_밑줄)이면 시크릿이 아니라 레지스트리의 '이름 매핑'이다
    ("client_secret JSON 값", re.compile(r'"client_secret"\s*:\s*"(?![A-Z][A-Z0-9_]*")[^"]{8,}"')),
    ("키/토큰 할당", re.compile(r"""(?i)\b(?:api[_-]?key|secret|token|passwd|password)\b\s*[:=]\s*['"][A-Za-z0-9_\-/+=]{24,}['"]""")),
]


# 검사용 사본(D-352): 키를 보이지 않는 글자·전각 글자·결합 글자로 쪼개 붙여 넣어도 같은 키로 읽는다. **원문은 바꾸지 않고** 검사에만 쓴다.
#  ① NFKD 로 푼다 — 전각 글자(`ｇｈｐ＿`)·호환 글자는 ASCII 꼴이 되고, 악센트가 붙은 글자는 '글자 + 결합 글자' 로 나뉜다(NFKC 는 다시 한 글자로 합쳐 악센트가 남는다).
#  ② 서식 글자(Cf: 제로폭 공백·결합자·방향 표시·소프트 하이픈·BOM·태그 글자 …)·결합 글자(Mn·Me: 악센트·결합 문자 연결자·변이 선택자 …)·제어 글자(Cc, 줄바꿈·탭은 남긴다)·
#     짝 없는 서로게이트(Cs)·아직 배정되지 않은 글자(Cn — 기본으로 안 그려지는 미배정 글자 3769개가 여기 든다)·사용자 정의 영역(Co)과,
#     종류로는 못 잡는 눈에 안 보이는 글자(한글 채움 글자·점자 빈칸)를 지운다.
#  ③ NFC 로 다시 합친다 — NFKD 는 한글 음절을 자모 두세 개로 풀어 글자 수가 늘고, 길이 조건이 있는 패턴(`client_secret` 값 8자 이상)이 3자에서 7자 사이의 한글 값(`"비밀번호"`)에 잘못 걸렸다(검증자 Q 의 QP-1).
# 긴 글은 조각으로 나눠 처리한다: 결합 글자가 길게 이어진 입력에서 정규화가 제곱 시간이라(8만 자에 6초 넘게) 조각마다 하면 선형에 가깝다. 지울 글자뿐이라 조각 경계는 결과에 영향이 없다.
# 못 막는 것(한계): 모양만 닮은 다른 문자(키릴 문자 'а' 로 쓴 'a' 등), 공백·줄바꿈·보이는 기호로 나눈 키. 파이썬 3.10(유니코드 13)과 3.12(유니코드 15)는 글자 범주가 조금 달라 새로 배정된 글자는 결과가 다를 수 있다.
_SCAN_DROP_CATEGORIES = frozenset({"Cc", "Cf", "Cs", "Mn", "Me", "Cn", "Co"})
_SCAN_KEEP = frozenset("\t\n\r")
_SCAN_DROP_EXTRA = frozenset(chr(code) for code in (0x115F, 0x1160, 0x2800))     # 한글 초성·중성 채움 글자와 점자 빈칸 — 종류(Lo·So)로는 못 잡는다(U+3164·U+FFA0 은 NFKD 로 U+1160 이 된다)
_SCAN_CHUNK = 2048


class _ScanTable(dict):
    """`str.translate` 용 표: 처음 보는 글자만 파이썬으로 판정해 기억하고, 그 뒤로는 C 속도로 지나간다(저장소 전체를 줄마다 훑는 검증기에서도 느려지지 않게).
    blank 가 None 이면 지울 글자를 지우고, 공백 글자 번호이면 그 자리를 공백으로 바꾼다."""

    def __init__(self, blank=None):
        super().__init__()
        self.blank = blank

    def __missing__(self, codepoint):
        char = chr(codepoint)
        drop = char in _SCAN_DROP_EXTRA or (unicodedata.category(char) in _SCAN_DROP_CATEGORIES and char not in _SCAN_KEEP)
        self[codepoint] = self.blank if drop else codepoint
        return self[codepoint]


_SCAN_TABLE = _ScanTable()
_BLANK_TABLE = _ScanTable(blank=0x20)


def _scan(text, table, recompose):
    text = "" if text is None else str(text)
    if text.isascii() and text.isprintable():       # 보이는 ASCII 뿐이면 풀고 지울 것이 없다(결과가 같다) — 저장소 전체를 줄마다 훑는 검증기가 느려지지 않게 바로 돌려준다
        return text
    pieces = []
    for start in range(0, len(text), _SCAN_CHUNK):
        piece = unicodedata.normalize("NFKD", text[start:start + _SCAN_CHUNK]).translate(table)
        pieces.append(unicodedata.normalize("NFC", piece) if recompose else piece)
    return "".join(pieces)


def scan_copy(text):
    """비밀 모양을 찾기 위한 검사용 사본(위 설명). 원문은 그대로 두고 새 문자열을 돌려준다. None 은 빈 문자열."""
    return _scan(text, _SCAN_TABLE, True)


def scan_copy_spaced(text):
    """`scan_copy` 와 같되 지울 글자 자리를 지우지 않고 공백으로 바꾼 사본. 숫자 묶음 바로 앞뒤에 지울 글자와 숫자가 붙은 입력(`4111…1111` + 널 + `5`)은 지운 사본에서는 숫자가 이어 붙어
    번호 모양을 놓치므로, 번호 점검은 지운 사본과 이 사본을 둘 다 본다(검증자 S 의 SP-6 — 옛 접기는 그 글자를 경계로 남겨 잡았다)."""
    return _scan(text, _BLANK_TABLE, False)


def find_secrets(text):
    """text 안에서 비밀로 보이는 값의 (라벨, 마스킹된 미리보기) 목록. 값 전체는 돌려주지 않는다.

    원문과 검사용 사본(`scan_copy`) 둘 다 본다 — 보이지 않는 글자·전각 글자·결합 글자로 쪼갠 키도 같은 라벨로 걸린다."""
    text = text or ""
    folded = scan_copy(text)
    found = []
    for label, rx in SECRET_PATTERNS:
        match = rx.search(text) or (rx.search(folded) if folded != text else None)
        if match:
            found.append((label, match.group(0)[:4] + "***"))
    return found
