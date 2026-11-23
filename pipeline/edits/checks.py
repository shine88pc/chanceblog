"""수정 후 사후 검증: LLM·사용자 입력이 무엇을 만들었든, 아래를 통과하지 못하면 파일을 쓰지 않는다.

1. 바뀐 파일은 허용 경로 안에 있고 절대 금지 경로가 아니다
2. 바뀐 파일 수·바뀐 줄 수·파일 크기 상한, 갑작스러운 축소 금지
3. 광고(AdSense) 스니펫 개수가 바뀌지 않는다(추가·삭제 모두 불가)
4. 위험한 마크업(script·iframe·이벤트 속성·javascript: 등)이 늘어나지 않는다
5. front matter 는 방식별로 허용된 범위만 바뀐다
6. 새 비밀 값이 들어가지 않는다, 새 http:// 링크가 들어가지 않는다
7. AI 가 쓴 변경은 원문에 없던 외부 링크(주소 단위: `//host`·같은 호스트의 새 경로·참조식 정의·srcset 포함)를 넣지 못한다(D-353)
"""
import difflib
import html
import re
import unicodedata

from pipeline import unsplash_credit
from pipeline.edits import frontmatter, safety, spec as spec_mod
from pipeline.secret_patterns import find_secrets

AD_PATTERNS = [re.compile(p, re.IGNORECASE) for p in (r"adsbygoogle", r"googlesyndication", r"ca-pub-\d+")]
# 엔티티를 풀고 제어 문자를 공백으로 바꾼 텍스트에서 센다(&#106;avascript:, 속성 안의 개행 등으로 숨긴 것을 드러낸다)
DANGEROUS = [
    ("<script", re.compile(r"<\s*script\b", re.I)),
    ("<iframe", re.compile(r"<\s*iframe\b", re.I)),
    ("<object/<embed", re.compile(r"<\s*(?:object|embed|applet)\b", re.I)),
    ("<form", re.compile(r"<\s*form\b", re.I)),
    ("<style/<link/<base/<meta", re.compile(r"<\s*(?:style|link|base|meta)\b", re.I)),
    ("<svg/<math/<frame", re.compile(r"<\s*(?:svg|math|frame|frameset)\b", re.I)),
    ("javascript:", re.compile(r"javascript\s*:", re.I)),
    # 이벤트 핸들러 규칙은 둘이고 각각 따로 개수를 비교한다(D-406, 검증자 S 의 V1). ① 옛 규칙 — 시작점 그대로(앞 글자가 공백·따옴표·슬래시인 `on…=`). 지우거나 아래 새 규칙과 합치지 않는다:
    # 새 규칙은 옛 규칙이 센 것을 모두 세지만 더 많이 세므로 하나로 대체하면, 앞글에 새 규칙만 세는 꼴(`?online=1`)이 있을 때 같은 수정이 그 꼴을 지우며 진짜 핸들러(` onclick=`)를 넣어도 개수가 늘지 않아 통과한다.
    # 두 규칙의 이름이 같아 거절 문구는 한 번만 나온다(verify_changes). 옛 규칙이 막던 것은 항상 막히고 새 규칙은 더 막기만 한다.
    ("이벤트 핸들러 속성(on…=)", re.compile(r"""[\s"'/]on[a-z]{3,}\s*=""", re.I)),
    # ② 새 규칙: 속성 이름의 일부가 아닌 모든 글자 뒤의 `on…=` 를 센다(D-406). 옛 규칙은 앞 글자가 공백·따옴표·슬래시일 때만 잡아서 kramdown 속성 목록 `글{:onclick="…"}` 를 놓쳤다 —
    # 속성 목록은 `{:` 바로 뒤, 정의형 `{:이름:onclick="…"}` 은 이름 뒤 콜론 바로 뒤에서 속성이 시작한다(속성 읽기가 문자열 처음과 공백을 구분자로 받는다 — 소스 기억 기준, 이 PC 에 Ruby 가 없어 렌더는 확인하지 못했다).
    # 영숫자·밑줄·하이픈 바로 뒤는 더 긴 이름(`data-onclick`·`monitor=`)이라 뺀다. 추정에 기대 보수적으로 막으므로 질의 문자열 `?online=1` 도 새로 넣으면 거절한다(개수가 늘 때만 막는다).
    ("이벤트 핸들러 속성(on…=)", re.compile(r"(?<![A-Za-z0-9_-])on[a-z]{3,}\s*=", re.I)),
    # ③ 속성 목록 안(`{:` 부터 `}` 까지, 안쪽 탐색은 400자 상한)만 따로 센다(3차, 검증자 Q 의 F1·S 의 W1): ② 는 질의 문자열 `?online=1`·코드 조각 `f(online=1)` 도 세므로 앞글에 그런 꼴이 있으면 같은 수정이 그것을
    # 지우며 `x{:onclick=…}` 를 넣어도 개수가 같아 통과했다(V1 과 같은 구조 — 시작점 대비 약화는 아니지만 속성 목록은 이 묶음이 새로 막는 꼴이다). 속성 목록 안은 질의 문자열이 올 수 없는 곳이라 이 항목은 가려지지 않는다.
    # 400자 너머에 숨긴 핸들러는 앞이 공백이라 ① 이 센다. 세 항목의 이름이 같아 거절 문구는 한 번만 나온다.
    ("이벤트 핸들러 속성(on…=)", re.compile(r"\{:[^}]{0,400}?(?<![A-Za-z0-9_-])on[a-z]{3,}\s*=", re.I)),
]
# 공백까지 지운 소문자 텍스트에서 센다(java<개행>script: 같은 분할 표기)
COMPACT_DANGEROUS = [
    ("javascript:/vbscript: 주소", re.compile(r"(?:javascript|vbscript):")),
    ("data: 주소", re.compile(r"""(?:href|src|action|formaction|srcdoc|poster|background)=["']?data:|\]\(data:""")),
]
LIQUID = re.compile(r"\{%|\{\{")
_AD_BLOCK = re.compile(r"(?is)<\s*script\b.*?(?:<\s*/\s*script\s*>|\Z)|<\s*ins\b[^>]*>")
_EXTERNAL_HOST = re.compile(r"""(?i)\bhttps?://([^/\s)"'<>?#:\\]+)""")
_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f\u200b-\u200f\u2028\u2029\ufeff]")
_HTTP_LINK = re.compile(r"""\bhttp://[^\s)"'<>]+""", re.I)
MIN_SHRINK_BASE = 500
AI_MIN_LINES, AI_MAX_RATIO = 12, 0.3   # AI 패치는 작은 파일에서도 '일부'만 바꿔야 한다(절대 한도 80줄은 작은 페이지에서 무의미)

# 게시글 대표 이미지로 허용하는 주소: 호스트는 아래뿐이다(호스트를 늘리는 것은 자동 수정 범위 확대이므로 T3).
IMAGE_HOSTS = ("images.unsplash.com",)
# `https://<호스트>/photo-<id>` + 선택적 질의(영숫자 _ . = & - 와 %XX 만). userinfo(@)·포트·프래그먼트·경로 추가·따옴표·괄호·공백·개행은 모두 불일치
_IMAGE_URL = re.compile(r"https://(?P<host>[a-z0-9.\-]+)/photo-[A-Za-z0-9_\-]{1,64}"
                        r"(?:\?(?:[A-Za-z0-9_.=&\-]|%[0-9A-Fa-f]{2}){1,300})?")
_IMAGE_LINE = re.compile(r"image\s*:")


def _decode(text):
    """엔티티를 반복해서 풀고 제어·보이지 않는 문자를 공백으로 바꾼다."""
    for _ in range(3):
        step = html.unescape(text)
        if step == text:
            break
        text = step
    return _CONTROL.sub(" ", text)


def _compact(text):
    return re.sub(r"\s+", "", _decode(text)).lower()


def _ad_blocks(text):
    """페이지 안의 <script> 블록과 <ins> 태그 전체(공백 정규화). 하나라도 달라지면 광고·스크립트가 바뀐 것이다."""
    return sorted(re.sub(r"\s+", " ", m.group(0)).strip() for m in _AD_BLOCK.finditer(text))


def _hosts(text):
    return {h.lower() for h in _EXTERNAL_HOST.findall(_decode(text))}


# ----------------------------------------------------------------------------
# AI 가 더한 외부 링크(D-353)
# ----------------------------------------------------------------------------
# 옛 검사(`_hosts`)는 `http`·`https` 스킴 주소의 호스트 집합만 견줬다. 그래서 프로토콜 상대 주소(`//host`)·같은 호스트의 새 경로·`host:80@evil` 처럼 ':' 에서 호스트가 끊겨 읽히는 주소·참조식 정의·srcset·
# 탭·줄바꿈으로 쪼갠 스킴(`ht&#9;tps://…` — 브라우저는 주소 안의 탭·줄바꿈을 지우고 읽는다)이 지나갔다. 여기서는 링크 '대상' 을 모아 정규화한 주소(스킴·호스트는 소문자, 나머지는 그대로)를 견준다:
# AI 수정으로 원문에 없던 외부 주소가 하나라도 생기면 거절하고, 원문에 이미 있던 주소는 위치를 옮기거나 되풀이해도 괜찮다(허용 목록 = 원문의 링크).
# 외부 주소 = 스킴이 있는 주소와 `//host`. mailto·tel 은 연락 수단이라 뺀다(전과 같다). javascript·data·vbscript 는 위험 마크업 규칙이 따로 막는다.
_NOT_EXTERNAL_SCHEMES = frozenset({"mailto", "tel", "javascript", "vbscript", "data"})
# 슬래시 없이 `스킴:낱말` 만으로도 밖으로 나가는 스킴 — 브라우저가 호스트로 읽는 것(http·https·ftp·ftps·ws·wss)과 다른 프로그램을 여는 것. 그 밖의 `낱말:`(영문 각주·정의의 `IMF:`·`Source:` 같은 글머리)은
# 뒤에 `//` 가 따를 때만 주소로 본다 — 그러지 않으면 정상 수정이 `imf://` 같은 없는 주소로 거절된다(검증자 S 의 SP-4).
_OPEN_SCHEMES = frozenset({"http", "https", "ftp", "ftps", "ws", "wss", "skype", "sip", "sips", "xmpp", "magnet", "sms", "facetime", "callto", "view-source"})
# 슬래시 없이 `스킴:값` 으로 쓰는 앱·결제·처리기 스킴(검증자 S 의 SP-12·Q 의 QR2-1). 위 15개 밖의 `낱말:` 은 `//` 가 따를 때만 주소로 보므로(영문 각주 오탐을 피하려고 좁혔다) 지갑 결제
# (`bitcoin:`)·메신저 딥링크(`tg:`)·윈도 프로토콜 처리기(`ms-msdt:`)처럼 `//` 없이 쓰는 링크가 같이 풀렸다. 아래 스킴은 **눌리는 링크 자리**(링크 대상·꺾쇠 대상·HTML 속성·참조식 정의·자동 링크·url()·srcset·image-set)에서
# 값이 있으면(`tg:resolve?x=1`) 주소로 읽는다 — 콜론 뒤 공백·줄바꿈 뒤의 값도 읽되(아래 `_SPACED_TARGET_PATTERNS`) 주소가 공백을 가질 수 있는 자리에서만이다: 링크 대상(`[x](tg: resolve)`)·꺾쇠 대상(`[x](<tg: …>)`·`[r]: <tg: …>`)·
# 주소 토큰 `tg:` 가 줄 끝이고 값이 다음 줄에 있는 정의. 꺾쇠 없는 정의의 같은 줄 `낱말: 값` 은 값이 **주소 모양일 때만** 읽는다(D-393, 아래 `_SAME_LINE_DEFINITION`) — 영문 글머리 `[1]: News: BBC 2020`·`[Update]: Line: 12` 는 글이다.
# `News:` 처럼 값이 없는 글머리는 아니다. 글에 가까운 두 자리는 읽지 않는다:
# 각주 정의의 본문(`[^1]: Market:KOSPI` — 라벨이 kramdown 각주 ID 꼴 `[^낱말]` 일 때만; `[^]`·`[^.]`·`[^a b]`·`[^각주]` 는 각주가 아니라 참조식 정의라 읽는다)과 `cite` 속성(인용 출처 메모라 눌리지 않는다).
# 그 자리에는 영문 글머리(`News: …`·`Market:KOSPI`·`About:me`)가 흔하다. 접두사 `ms-`(윈도 처리기)와 `web+`(웹 사용자 정의 처리기)는 이름을 다 셀 수 없어 접두사로 본다.
# 한계: 목록 밖의 처리기는 여전히 `//` 가 따를 때만 주소로 본다(전부 막으려면 영문 정의의 오탐을 감수해야 한다).
_APP_SCHEMES = frozenset({
    "bitcoin", "bitcoincash", "litecoin", "ethereum", "monero", "dogecoin", "dash", "zcash", "lightning", "nostr", "solana", "tron", "stellar",                # 결제·지갑
    "tg", "whatsapp", "viber", "weixin", "wechat", "line", "signal", "sgnl", "threema", "zalo", "slack", "discord", "msteams", "zoommtg", "zoomus", "webex",
    "smsto", "mmsto", "mms", "imessage", "facetime-audio",                                                                                                 # 메신저·통화·화상회의
    "steam", "spotify", "market", "itms", "itms-apps", "itms-services", "intent", "maps", "geo", "vscode", "vscode-insiders", "obsidian", "notion",             # 앱·상점·지도
    "ssh", "sftp", "git", "svn", "irc", "ircs", "telnet", "rdp", "vnc", "smb", "nfs", "afp", "ldap", "ldaps", "gopher", "news", "snews", "nntp", "tftp", "rtsp", "rtmp",
    "webcal", "webcals", "feed", "dict", "rsync",                                                                                                          # 원격 접속·옛 프로토콜·구독
    "search", "search-ms", "about", "chrome", "chrome-extension", "edge", "blob",                                                                          # 브라우저·윈도 검색
})
_APP_SCHEME_PREFIXES = ("ms-", "web+")
_SCHEME = re.compile(r"(?i)([a-z][a-z0-9+.\-]*):")
# 끝 문장부호·강조 기호 떼기는 **글 속 맨주소에만** 쓴다. 링크 대상·HTML 속성·꺾쇠 자동 링크는 눌리는 링크라 끝 글자까지 그대로 견준다(`alice` 에 `alice_` 를 덧붙인 링크는 새 주소로 거절).
# 글 속 맨주소의 끝 밑줄·물결표까지 떼는 것은 GFM 자동 링크 규칙과 같고, 이 사이트는 GitHub Pages 기본 설정(kramdown)이라 글 속 맨주소를 링크로 만들지 않는 것으로 보인다(이 PC 에 렌더러가 없어
# 직접 확인하지는 못했다) — 그렇다면 눌리지 않는 글이다. 이 떼기 목록은 기존 시험(`test_trailing_punctuation_and_emphasis_are_not_part_of_a_prose_address`)이 못박은 동작이라 바꾸지 않는다 —
# 검증자 S 의 SP-15(끝 밑줄·물결표를 떼기 목록에서 빼자는 제안)는 그래서 고치지 않기로 했다(D-368). 밑줄로 감싸는 정상 수정이 통과하는 것은 이 목록 덕이고, 밑줄을 벗기는 정상 수정이 거절되는 것은 호스트 검사 `_hosts` 쪽 사정이다(이 묶음 밖 — 2차 검증 SQ-4).
_TRAILING_PUNCTUATION = ".,:;!?*_" + chr(0x7E)       # 글 속 주소 뒤에 붙는 문장부호·강조 기호(끝 마침표·쉼표·굵게 표시 등) — 주소가 아니다
# 탭·줄바꿈·CR 을 뜻하는 문자 참조(브라우저가 주소 안에서 지운다). 숫자 참조는 그 숫자로 **끝날 때만** 맞춘다 — 그렇지 않으면 `&#104;`(h)·`&#100;`(d)·`&#xA9;` 의 앞부분이 잘려 나간다.
_ENTITY_BLANK = re.compile(r"(?i)&(?:#0*(?:9|10|13)(?![0-9]);?|#x0*[9ad](?![0-9a-f]);?|(?:tab|newline);)")
# 줄바꿈이 CR 하나뿐인 글(옛 맥)이나 CRLF 도 LF 로 통일해서 읽는다 — 정의 정규식의 줄 머리(`(?m)^`)가 LF 뒤만 줄 머리로 봐서 CR 만으로 줄을 나눈 글의 정의가 숨었다(D-395, 시작점부터 있던 틈). kramdown 도 읽기 전에 같이 통일한다.
_LINE_BREAKS = re.compile(r"\r\n?")
# kramdown 의 각주 ID: 영문·숫자·밑줄로 시작하고 영문·숫자·밑줄·하이픈이 이어지는 낱말(`\w[\w-]*`, ASCII). 라벨이 `^` + 이 꼴일 때만 각주 정의(글에 가까운 자리)다. 그 밖의 `[^…]`(`[^]`·`[^.]`·`[^a b]`·`[^각주]`)는 각주가 아니라
# 참조식 정의라서 `[눌러][^.]` 가 눌리는 링크가 된다 — 그런 라벨까지 각주로 보면 시작점이 막던 `[^]: //host` 가 지나가고 앱 스킴도 지나간다(2차 검증 S 의 S-1·R-2, Q 의 SQ-1).
_FOOTNOTE_ID = r"\^[A-Za-z0-9_][A-Za-z0-9_-]*"
# 다른 정의의 머리(`[이름]:` — 인용문·목록 표시가 앞서도)는 앞 정의의 대상 글자가 아니다: 대상이 빈 `[a]:` 줄 뒤(빈 줄이 끼거나 바로 다음 줄)에 이어지는 정의 `[r]: //host` 를 앞 정의가 대상으로 삼켜 못 읽던 틈을 닫는다(D-394, 시작점부터 있던 틈).
# 줄바꿈 개수는 제한하지 않는다 — 빈 줄 뒤의 글도 옛대로 대상으로 읽어 시작점보다 덜 읽지 않는다(실패 닫힘). 공백 위치는 표시 글자도 `[` 도 아니라 바로 통과하므로 공백 반복에서 느려지지 않는다.
_NOT_A_DEFINITION_HEAD = r"(?![>*+\-0-9.)][ \t>*+\-0-9.)]*\[[^\]\n]+\]:|\[[^\]\n]+\]:)"
_TARGET_PATTERNS = (
    re.compile(r"\]\(\s*<?\s*([^)\s>]*)"),                                          # 마크다운 [글](주소 "제목") · ![그림](주소)
    re.compile(r"(?m)^[ \t>*+\-0-9.)]*\[(?!" + _FOOTNOTE_ID + r"\])[^\]\n]+\]:\s*(?:<\s*)?" + _NOT_A_DEFINITION_HEAD + r"([^\s>]+)"),                 # 참조식 정의 [이름]: 주소 (인용문·목록 표시 안에서도, 주소가 다음 줄이어도) — 라벨이 각주 ID 꼴인 각주 정의는 아래 글에 가까운 자리 · 꺾쇠 `<` 뒤 공백·탭·줄바꿈도 건너뛴다(`[r]: < //host>`, D-397)
    re.compile(r"""(?i)(?<![\w:-])(?:href|src|action|formaction|poster|background|data|ping|xlink:href|longdesc|manifest|codebase|usemap)"""
               r"""\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'<>`=]+))"""),                # HTML 속성(따옴표 없는 값 포함)
    re.compile(r"(?i)<\s*([a-z][a-z0-9+.\-]*:[^\s<>]*)\s*>"),                       # 꺾쇠 자동 링크(스킴이 붙은 주소)
    re.compile(r"""(?i)(?<!\w)url\(\s*(?:'([^']*)'|"([^"]*)")"""),                  # url('…')·url("…") 의 따옴표 안 글 전체 — 앞 공백·탭이 있어도(`url(' //host')`) 읽는다(D-396); 글자 지우기는 `_external_key` 가 한다
    re.compile(r"""(?i)\burl\(\s*['"]?([^)'"\s]*)"""),                              # 인라인 style 의 url(…) — 그림·글꼴을 밖에서 불러온다
)
# 글에 가까운 자리: 슬래시 없는 앱 스킴(`News:값`)은 읽지 않고 `//`·알려진 스킴만 주소로 본다 — 각주 정의의 본문, cite 속성(위 설명)
_TEXT_LIKE_PATTERNS = (
    re.compile(r"(?m)^[ \t>*+\-0-9.)]*\[" + _FOOTNOTE_ID + r"\]:\s*(?:<\s*)?" + _NOT_A_DEFINITION_HEAD + r"([^\s>]+)"),                 # 각주 정의의 본문 — 꺾쇠 `<` 뒤 공백·탭·줄바꿈도 건너뛴다(D-397)
    re.compile(r"""(?i)(?<![\w:-])cite\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'<>`=]+))"""),
)
# 눌리는 링크 자리에서 콜론 뒤에 공백·탭·줄바꿈이 오고 값이 이어지는 꼴 — `[x](tg: resolve?…)`·`[x](<tg: …>)`·`[r]: <tg: …>`·`[r]: tg:` 다음 줄의 값(2차 검증 R-1). 읽는 자리는 주소가 공백을 가질 수 있는 곳이다:
# 링크 대상(꺾쇠 포함)·꺾쇠 정의, 그리고 꺾쇠 없는 정의에서는 주소 토큰 `스킴:` 이 줄 끝인 꼴(값이 다음 줄에 있다 — 실패 닫힘). 꺾쇠 없는 정의의 같은 줄 `[r]: tg: resolve` 는 정의의 주소가 첫 토큰 하나라 링크 정의인지
# 렌더러로 확인하지 못했다(소스 기억이 갈린다 — D-393): 영문 글머리(`[1]: News: BBC 2020`·`[Update]: Line: 12`)는 통과시키되 값이 주소 모양일 때만 읽는다(아래 `_SAME_LINE_DEFINITION`, 총괄 결정 (B)).
# 스킴과 값 첫 마디를 이어 붙여 읽는다. 공백 길이에 상한을 두지 않는다(공백 정규식이 한 곳씩만 변하는 꼴이라 선형이다). 값이 없거나 제목(따옴표)이면 아니고, 다른 정의의 머리는 값이 아니다.
_SPACED_TARGET_PATTERNS = (
    re.compile(r"""\]\(\s*(?:<\s*)?([A-Za-z][A-Za-z0-9+.\-]*:)\s+([^)\s>"']+)"""),                                                                                      # 링크 대상(꺾쇠 포함)
    re.compile(r"""(?m)^[ \t>*+\-0-9.)]*\[(?!""" + _FOOTNOTE_ID + r"""\])[^\]\n]+\]:\s*<\s*([A-Za-z][A-Za-z0-9+.\-]*:)\s+([^\s>"']+)"""),                          # 꺾쇠 정의
    re.compile(r"""(?m)^[ \t>*+\-0-9.)]*\[(?!""" + _FOOTNOTE_ID + r"""\])[^\]\n]+\]:\s*([A-Za-z][A-Za-z0-9+.\-]*:)[^\S\n]*\n\s*""" + _NOT_A_DEFINITION_HEAD + r"""([^\s>"']+)"""),  # 꺾쇠 없는 정의 — 주소 토큰이 줄 끝
)
# 꺾쇠 없는 정의의 같은 줄 `앱스킴: 값`(D-393 (B)): 영문 글머리는 통과시키되 M103 이 막던 지갑·딥링크는 풀지 않도록 값이 **주소 모양일 때만** 읽는다 — 값에 `/?=@%&#:+` 나 역슬래시가 있거나, 글자로 시작하는 점이 든 호스트 꼴(`evil.example`·`alt.x`)이거나,
# 숫자가 7개 이상 이어지거나, IPv4 꼴(`10.0.0.1`)이거나, ASCII 영숫자가 16개 이상이면 주소 모양이다. 평범한 낱말·짧은 숫자·날짜·버전(`BBC`·`12`·`2026-11-22`·`120.0.6099.71`)은 글이다. 남는 틈은 값이 평범한 낱말인 꼴(`tg: resolve`·`slack: open`)뿐이다 — 처리기에 넘길 내용이 거의 없다.
# `]:` 뒤 공백은 줄바꿈을 건너 대상이 다음 줄이어도 읽는다(M103 처럼). 같은 줄 공백 뒤 값만 이 규칙이고, 값이 다음 줄에 있는 꼴은 위 `_SPACED_TARGET_PATTERNS` 의 셋째가 맡는다.
# 스킴 콜론과 값 사이의 구분은 줄바꿈만 뺀 모든 공백 글자다(`[^\S\n]` — M103 의 공백 읽기와 같은 폭: NBSP·VT·유니코드 공백 포함). ASCII 공백·탭으로 좁히면 M103 이 막던 꼴이 풀린다(검증자 S 의 p24).
_SAME_LINE_DEFINITION = re.compile(r"""(?m)^[ \t>*+\-0-9.)]*\[(?!""" + _FOOTNOTE_ID + r"""\])[^\]\n]+\]:\s*([A-Za-z][A-Za-z0-9+.\-]*:)[^\S\n]+([^\s>"']+)""")
_ADDRESS_SHAPE = re.compile(r"[/?=@%&#:+\\]|(?<![A-Za-z0-9-])[0-9-]*[A-Za-z][A-Za-z0-9-]*\.[A-Za-z0-9]|[0-9]{7}|(?<![0-9.])[0-9]{1,3}(?:\.[0-9]{1,3}){3}(?![0-9.])")   # 호스트 꼴은 덩어리의 시작에서만 시도한다(글자마다 시도하면 긴 덩어리에서 제곱 시간)
_ADDRESS_ALNUM_LIMIT = 16


def _address_shaped(value):
    """꺾쇠 없는 정의의 같은 줄 `앱스킴: 값` 의 값이 영문 글머리가 아니라 주소 모양인가(위 설명)."""
    return bool(_ADDRESS_SHAPE.search(value)) or sum(ch.isascii() and ch.isalnum() for ch in value) >= _ADDRESS_ALNUM_LIMIT


_SRCSET = re.compile(r"""(?i)(?<![\w:-])srcset\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'<>`=]+))""")                  # 따옴표 없는 값도(`<img srcset=//host/a.png>`)
# CSS image-set('//host/a.png' 1x, '//host/b.png' 2x) 의 문자열 주소들. 따옴표 안의 `)` 는 함수의 끝이 아니다(검증자 S 의 SP-14: 정규식 `[^)]*` 가 거기서 끊겨 못 읽었다). 또 닫는 괄호 없는
# `image-set(` 이 되풀이되면 시작마다 글 끝까지 훑어 제곱 시간이었다(8만 자에 3.5초) — 정규식 대신 글을 한 번만 훑는 상태기계로 읽는다(`_image_set_strings`).
_IMAGE_SET_START = re.compile(r"(?i)(?<!\w)image-set\(")
_IMAGE_SET_TOKEN = re.compile(r"""(?i)(?<!\w)image-set\(|['"()]|\\(?!image-set\()[\s\S]""")                       # 상태가 바뀌는 곳만: 시작·따옴표·괄호·이스케이프(바로 뒤가 `image-set(` 인 역슬래시는 함수 이름 앞 글자 — CSS 는 `\i` 를 i 로 읽는다)
_IMAGE_SET_MAX_DEPTH = 6                                                                                        # 괄호 깊이 상한 — 넘는 중첩은 닫히는 곳을 모른다고 보고 계속 읽는다(안전한 쪽)
_IMAGE_SET_UNTERMINATED_LIMIT = 300                                                                             # 글 끝까지 안 닫힌 따옴표는 CSS 가 글 끝에서 닫듯 거기까지(최대 300자)를 문자열로 읽는다
_BARE_URL = re.compile(r"""(?i)(?<![a-z0-9+.\-])(?:(?:https?|ftps?|wss?):[/\\]*|(?:sftp|file):[/\\]{2,})[^\s<>"'`)\]/\\][^\s<>"'`)\]]*""")   # 글 속의 주소(슬래시가 모자라거나 역슬래시여도 — sftp·file 은 `//` 가 있을 때만)


def _app_address(name, after):
    """`_APP_SCHEMES`·접두사의 스킴이고 값이 있나 — `News:` 처럼 값이 없는 글머리는 아니다. after 는 공백을 뺀 콜론 뒤 글."""
    return bool(after) and (name in _APP_SCHEMES or name.startswith(_APP_SCHEME_PREFIXES))


def _unterminated_address(rest):
    """글 끝까지 안 닫힌 따옴표 뒤의 글에서 주소 부분만 낸다: 브라우저가 지우는 공백·제어·서식 글자를 먼저 지우고(아주 긴 공백으로 주소를 밀어내도 읽도록) 속성·함수를 닫는 글자(`)"'<>`)에서 자르고 300자까지.
    뒤따르는 글 전체를 키에 넣지 않으므로 깨진 CSS 가 원문에 있어도 그 뒤 문장을 고치는 정상 수정이 새 주소로 거절되지 않는다."""
    cleaned = "".join(ch for ch in rest if not ch.isspace() and unicodedata.category(ch) not in ("Cc", "Cf"))
    return re.split(r"""[)"'<>]""", cleaned, 1)[0][:_IMAGE_SET_UNTERMINATED_LIMIT]



def _image_set_strings(text):
    """text 안의 모든 `image-set(` 안에서 따옴표로 묶인 문자열(따옴표는 뺀다)의 목록.

    `image-set(` 마다 따로 앞에서부터 읽는 것과 같은 결과를 글을 한 번만 훑어 낸다(시험이 느린 기준 구현과 견준다): 토큰(`image-set(`·따옴표·괄호·이스케이프)마다 읽기들의 상태 (따옴표 상태, 괄호 깊이)를
    옮긴다. 같은 상태의 읽기는 하나로 합쳐지므로 읽기는 (따옴표 상태 3 × 깊이 6)개를 넘지 않고, 시간은 글 길이에 비례한다. 앞에 짝 없는 따옴표가 있어 따옴표 짝이 어긋나도 `image-set(` 마다 새 읽기가 시작해 놓치지 않는다.
    안에 든 괄호 함수(`url(…)`)는 깊이로 세어 그 닫는 괄호에서 끝내지 않는다. 읽기는 자기 `image-set(` 이 닫히면(깊이 1 에서 `)`) 끝난다."""
    first = _IMAGE_SET_START.search(text)
    if not first:
        return []
    found, live, last = [], set(), {"'": 0, '"': 0}      # live: 읽기들의 상태 (따옴표 상태: 0 밖·1 홑따옴표 안·2 큰따옴표 안, 괄호 깊이) · last: 마지막 따옴표 위치
    for token in _IMAGE_SET_TOKEN.finditer(text, first.start()):
        piece = token.group()
        if piece[0] == "\\":
            continue                                                  # 이스케이프한 글자(`\'`·`\)`)는 따옴표·괄호가 아니다
        if len(piece) > 1:                                            # `image-set(` — 읽고 있던 읽기에게는 여는 괄호 하나이고, 새 읽기가 하나 시작한다
            live = {(state, min(depth + 1, _IMAGE_SET_MAX_DEPTH) if state == 0 else depth) for state, depth in live}
            live.add((0, 1))
        elif piece in ("'", '"'):
            kind, moved, closing = (1 if piece == "'" else 2), set(), False
            for state, depth in live:
                if state == 0:
                    moved.add((kind, depth))                          # 따옴표 밖의 읽기는 문자열을 연다
                elif state == kind:
                    moved.add((0, depth))                             # 같은 따옴표 안의 읽기는 문자열을 닫는다
                    closing = True
                else:
                    moved.add((state, depth))                         # 다른 따옴표 안의 따옴표는 글자다
            if closing:
                found.append(text[last[piece] + 1:token.start()])
            last[piece], live = token.start(), moved
        elif piece == "(":
            live = {(state, min(depth + 1, _IMAGE_SET_MAX_DEPTH) if state == 0 else depth) for state, depth in live}
        else:                                                         # ")" — 따옴표 밖 읽기는 깊이가 1 이면 끝나고, 아니면 한 단계 얕아진다(상한에 닿은 읽기는 닫히는 곳을 몰라 그대로 둔다)
            live = {(state, depth if state or depth >= _IMAGE_SET_MAX_DEPTH else depth - 1) for state, depth in live if state or depth > 1}
    for state, _depth in live:
        if state:                                                     # 글 끝까지 안 닫힌 문자열
            found.append(_unterminated_address(text[last["'" if state == 1 else '"'] + 1:]))
    return found


def _spaced_targets(text):
    """눌리는 링크 자리의 `스킴: 값`(콜론 뒤 공백·줄바꿈 — 위 설명)에서 스킴과 값 첫 마디를 이어 붙인 주소들. 알려진 스킴(열린 스킴·앱 스킴·접두사)만 낸다 — 목록 밖 낱말은 옛대로 둔다."""
    for rx in _SPACED_TARGET_PATTERNS:
        for match in rx.finditer(text):
            scheme, value = match.groups()
            name = scheme[:-1].lower()
            if name in _OPEN_SCHEMES or name in _APP_SCHEMES or name.startswith(_APP_SCHEME_PREFIXES):
                yield scheme + value
    for match in _SAME_LINE_DEFINITION.finditer(text):
        scheme, value = match.groups()
        name = scheme[:-1].lower()
        if (name in _OPEN_SCHEMES or name in _APP_SCHEMES or name.startswith(_APP_SCHEME_PREFIXES)) and _address_shaped(value):
            yield scheme + value



def _external_key(raw, text_like=False):
    """링크 대상 하나를 정규화한다. 사이트 밖으로 나가는 주소면 `스킴://호스트…`(또는 `//호스트…`, 스킴·호스트는 소문자), 아니면 None. text_like 는 글에 가까운 자리(각주 정의의 본문·cite)라 슬래시 없는 앱 스킴은 안 읽는다."""
    target = "".join(ch for ch in raw if not ch.isspace() and unicodedata.category(ch) not in ("Cc", "Cf")).replace("\\", "/")
    scheme = _SCHEME.match(target)
    if scheme:
        name, after = scheme.group(1).lower(), target[scheme.end():]
        app = not text_like and _app_address(name, after)
        if name in _NOT_EXTERNAL_SCHEMES or (name not in _OPEN_SCHEMES and not after.startswith("//") and not app):
            return None
        prefix, rest = name + "://", after.lstrip("/")
    elif target.startswith("//"):
        prefix, rest = "//", target.lstrip("/")
    else:
        return None                                                                 # 사이트 안 경로·#앵커·?질의
    authority, tail = re.match(r"([^/?#]*)(.*)", rest, re.S).groups()
    return prefix + authority.lower() + tail


def external_links(text):
    """text 안의 외부 링크 주소(정규화한 꼴)의 집합 — 마크다운 링크·그림·참조식 정의·HTML 속성(href·src·srcset 등)·자동 링크·글 속의 주소."""
    text = str(text)
    for _ in range(3):                                                              # 문자 참조를 반복해서 푼다(&amp;#9; 처럼 겹쳐 쓴 것까지)
        step = html.unescape(_ENTITY_BLANK.sub("", text))
        if step == text:
            break
        text = step
    text = _LINE_BREAKS.sub(chr(10), text)                                          # CR 하나뿐인 줄바꿈·CRLF 도 LF 로(정의의 줄 머리 규칙이 LF 만 본다 — D-395)
    raws = []
    for rx in _TARGET_PATTERNS:
        for match in rx.finditer(text):
            raws.extend(group for group in match.groups() if group)
    raws.extend(_spaced_targets(text))
    text_raws = []                                                                  # 글에 가까운 자리(각주 정의의 본문·cite) — 슬래시 없는 앱 스킴은 안 읽는다
    for rx in _TEXT_LIKE_PATTERNS:
        for match in rx.finditer(text):
            text_raws.extend(group for group in match.groups() if group)
    for match in _SRCSET.finditer(text):
        for value in match.groups():
            raws.extend(part.split()[0] for part in (value or "").split(",") if part.split())
    raws.extend(_image_set_strings(text))
    raws.extend(match.group(0).rstrip(_TRAILING_PUNCTUATION) for match in _BARE_URL.finditer(text))
    return {key for key in map(_external_key, raws) if key} | {key for key in (_external_key(raw, True) for raw in text_raws) if key}


def changed_line_count(before, after):
    diff = difflib.unified_diff(before.splitlines(), after.splitlines(), lineterm="", n=0)
    return sum(1 for line in diff if line[:1] in "+-" and not line.startswith(("+++", "---")))


def unified_diff(before, after, path, max_lines=60):
    lines = list(difflib.unified_diff(before.splitlines(), after.splitlines(), f"a/{path}", f"b/{path}", lineterm="", n=2))
    if len(lines) > max_lines:
        lines = lines[:max_lines] + [f"... (이하 {len(lines) - max_lines}줄 생략)"]
    return "\n".join(lines)


def _front_matter_reasons(path, before, after, mode, only_fields):
    fm_b, body_b = frontmatter.split_front_matter(before)
    fm_a, body_a = frontmatter.split_front_matter(after)
    if fm_b is None:
        return [f"{path}: front matter 가 없던 파일에 front matter 를 추가할 수 없습니다."] if fm_a is not None else []
    if fm_a is None:
        return [f"{path}: front matter 가 사라졌습니다."]
    if mode == "body":
        return [] if fm_a == fm_b else [f"{path}: front matter 가 바뀌었습니다(이 수정 항목은 본문만 바꿀 수 있습니다)."]
    dict_b, dict_a = frontmatter.parse_front_matter(fm_b), frontmatter.parse_front_matter(fm_a)
    if dict_b is None or dict_a is None:
        return [f"{path}: front matter 를 해석할 수 없습니다."]
    allowed = set(only_fields or [])
    changed = {str(k) for k in set(dict_b) | set(dict_a) if dict_b.get(k) != dict_a.get(k)}
    reasons = []
    if changed - allowed:
        reasons.append(f"{path}: 허용되지 않은 front matter 항목이 바뀌었습니다: {', '.join(safety.code(k, 40) for k in sorted(changed - allowed))}")
    if mode == "front_matter" and body_a != body_b:
        reasons.append(f"{path}: 본문이 바뀌었습니다(이 수정 항목은 front matter 필드만 바꿀 수 있습니다).")
    return reasons


def image_url_problem(url):
    """게시글 대표 이미지로 허용되는 주소인지. None(허용) 또는 거부 사유. 주소 값은 사유에 쓰지 않는다(공개 코멘트에 되풀이 방지)."""
    match = _IMAGE_URL.fullmatch(url) if isinstance(url, str) else None
    if not match:
        return "이미지 주소가 허용된 형식(https://images.unsplash.com/photo-… 와 영숫자·=&.-_ 질의)이 아닙니다"
    if match.group("host") not in IMAGE_HOSTS:
        return f"허용되지 않은 이미지 호스트입니다(허용: {', '.join(IMAGE_HOSTS)})"
    return None


def is_safe_image_url(url):
    return image_url_problem(url) is None


def front_matter_image(text):
    """front matter 의 image 값(문자열, 없으면 '')과 front matter dict. front matter 를 해석할 수 없으면 (None, None)."""
    fm_text, _body = frontmatter.split_front_matter(text)
    data = frontmatter.parse_front_matter(fm_text) if fm_text is not None else None
    if data is None:
        return None, None
    value = data.get("image")
    return ("" if value is None else str(value)), data


def _without_image_line(text):
    fm_text, body = frontmatter.split_front_matter(text)
    return "\n".join(ln for ln in fm_text.split("\n") if not _IMAGE_LINE.match(ln)) + "\0" + body


def verify_image_change(before, after):
    """게시글 이미지 변경이 '대표 이미지 주소'만 바꿨는지 확인한다. 거부 사유 목록(비어 있으면 통과).

    생성 직후 검증(runner)과 PR 범위 검사(scope_check)가 같은 함수를 쓴다. 통과 조건:
    1. 새 front matter image 가 허용 형식·허용 호스트의 주소다(값은 사유에 되풀이하지 않는다)
    2. 이전 주소가 있었다면, 그것을 새 주소로 바꾼 것 말고는 본문·다른 줄이 한 글자도 다르지 않다(주소를 자리표시자로 바꿔 비교)
       — 단 하나의 예외: 우리가 만든 작가 출처 줄(`unsplash_credit` 의 모양, 이름은 이스케이프되고 링크는 unsplash.com 뿐)은 비교에서 빼고, 새 글에 그런 줄이 있다면
       하나뿐이고 새 이미지 줄 바로 다음이어야 한다(옛 사진의 출처 줄을 지우고 새 사진의 줄을 넣는 교체를 허용하되 다른 글을 끼워 넣을 수는 없게)
    3. 이미지가 없던 글에 이미지가 추가된 경우에는 front matter 의 image 줄만 늘어난 것이다
    """
    old_url, old_fm = front_matter_image(before)
    new_url, new_fm = front_matter_image(after)
    if old_fm is None or new_fm is None:
        return ["front matter 를 해석할 수 없어 이미지 변경을 확인할 수 없습니다."]
    problem = image_url_problem(new_url)
    if problem:
        return [f"새 대표 이미지: {problem}."]
    if new_url == old_url:
        return ["대표 이미지 주소가 바뀌지 않았습니다."]
    reasons = []
    if sum(1 for ln in frontmatter.split_front_matter(after)[0].split("\n") if _IMAGE_LINE.match(ln)) > 1:
        reasons.append("front matter 에 image 줄이 둘 이상입니다.")
    core_before, core_after = unsplash_credit.strip_credit_lines(before), unsplash_credit.strip_credit_lines(after)   # 우리 출처 줄은 비교에서 뺀다(아래에서 따로 본다)
    if old_url:
        marker = "\0IMAGE-URL\0"
        while marker in core_before or marker in core_after:   # 본문에 자리표시자와 같은 문자열이 있어도 속지 않는다
            marker += "\0"
        same = core_before.replace(old_url, marker) == core_after.replace(new_url, marker)
    else:
        same = _without_image_line(core_before) == _without_image_line(core_after)
    if not same:
        reasons.append("대표 이미지 주소 외의 내용(본문·다른 front matter)이 바뀌었습니다. 이미지 변경은 주소만 바꿀 수 있습니다.")
    reasons += unsplash_credit.credit_problems(after, new_url)
    return reasons


def verify_changes(changes, allowed_patterns, limits, mode="body", only_fields=None, ai_patch=False):
    """changes: {경로: (이전 텍스트, 새 텍스트)}. 거부 사유 목록(비어 있으면 통과).

    mode: body(본문만) · front_matter(only_fields 만) · image(front matter 의 image 만 + 본문 이미지 URL)
    ai_patch: AI 가 쓴 변경이면 True — 새 외부 링크를 금지하고 바뀐 비율을 더 엄격히 제한한다
    """
    reasons = []
    if not changes:
        return ["변경된 파일이 없습니다."]
    if len(changes) > limits["max_changed_files"]:
        reasons.append(f"바뀐 파일이 너무 많습니다({len(changes)}개 > {limits['max_changed_files']}개).")
    for path, (before, after) in changes.items():
        if not spec_mod.path_allowed(path, allowed_patterns):
            reasons.append(f"{path}: 이 수정 항목이 허용하지 않는 경로입니다.")
            continue
        if before == after:
            reasons.append(f"{path}: 바뀐 내용이 없습니다.")
            continue
        if len(after) > limits["max_file_chars"]:
            reasons.append(f"{path}: 파일이 너무 큽니다({len(after)}자 > {limits['max_file_chars']}자).")
            continue  # 큰 입력에 정규식 검사를 돌리지 않는다(검사 지연 방지)
        if len(before) >= MIN_SHRINK_BASE and len(after) < len(before) * 0.5:
            reasons.append(f"{path}: 수정 후 파일이 절반 이하로 줄었습니다.")
        lines = changed_line_count(before, after)
        if lines > limits["max_changed_lines"]:
            reasons.append(f"{path}: 바뀐 줄이 너무 많습니다({lines}줄 > {limits['max_changed_lines']}줄). 요청을 더 작게 나눠 주세요.")
        if ai_patch:
            cap = max(AI_MIN_LINES, int(max(len(before.splitlines()), 1) * AI_MAX_RATIO))
            if lines > cap:
                reasons.append(f"{path}: AI 수정이 파일의 큰 부분을 바꿉니다({lines}줄 > {cap}줄). 요청을 더 작게 나눠 주세요.")
            new_hosts = _hosts(after) - _hosts(before)
            if new_hosts:
                reasons.append(f"{path}: AI 수정은 새 외부 링크를 넣을 수 없습니다({safety.code(sorted(new_hosts)[0], 80)}).")
            else:     # 호스트는 그대로라도 원문에 없던 주소(같은 호스트의 새 경로·`//host`·참조식 정의·srcset·탭으로 쪼갠 스킴 …)가 생기면 같은 거절이다(D-353)
                new_links = external_links(after) - external_links(before)
                if new_links:
                    reasons.append(f"{path}: AI 수정은 새 외부 링크를 넣을 수 없습니다({safety.code(sorted(new_links)[0], 100)}).")
        for rx in AD_PATTERNS:
            if len(rx.findall(before)) != len(rx.findall(after)):
                reasons.append(f"{path}: 광고 코드({rx.pattern})가 추가되거나 삭제됩니다. 광고 표면은 이 경로로 바꿀 수 없습니다.")
        if _ad_blocks(before) != _ad_blocks(after):
            reasons.append(f"{path}: 페이지 안의 <script>·<ins> 블록이 바뀝니다(광고 ID·주소·본문 포함). 이 경로로 바꿀 수 없습니다.")
        if len(LIQUID.findall(after)) > len(LIQUID.findall(before)):
            reasons.append(f"{path}: Liquid 태그({{% … %}}·{{{{ … }}}})가 새로 들어갑니다. 템플릿 코드는 이 경로로 넣을 수 없습니다.")
        dec_before, dec_after = _decode(before), _decode(after)
        flagged = set()        # 같은 이름의 규칙이 둘 이상이어도(이벤트 핸들러: 옛 규칙 + 새 규칙) 거절 문구는 한 번만 — 규칙마다 따로 개수를 비교한다
        for name, rx in DANGEROUS:
            if name not in flagged and len(rx.findall(dec_after)) > len(rx.findall(dec_before)):
                flagged.add(name)
                reasons.append(f"{path}: 위험한 마크업({name})이 새로 들어갑니다.")
        cmp_before, cmp_after = _compact(before), _compact(after)
        for name, rx in COMPACT_DANGEROUS:
            if len(rx.findall(cmp_after)) > len(rx.findall(cmp_before)):
                reasons.append(f"{path}: 위험한 마크업({name})이 새로 들어갑니다.")
        known = {label for label, _ in find_secrets(before)}
        for label, preview in find_secrets(after):
            if label not in known:
                reasons.append(f"{path}: 비밀 값으로 보이는 문자열({label}, {preview})이 들어갑니다.")
        new_http = set(_HTTP_LINK.findall(after)) - set(_HTTP_LINK.findall(before))
        if new_http:
            reasons.append(f"{path}: 암호화되지 않은 http:// 링크가 새로 들어갑니다: {safety.code(sorted(new_http)[0], 100)}")
        fm_mode = "body" if mode == "body" else mode
        fm_only = ["image"] if mode == "image" else only_fields
        if mode == "image":
            reasons += _front_matter_reasons(path, before, after, "image", fm_only)
        else:
            reasons += _front_matter_reasons(path, before, after, fm_mode, fm_only)
    return reasons
