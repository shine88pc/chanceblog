"""Unsplash 사진의 출처 표시와 추적 값(ixid) 처리 — 순수 함수 모음(표준 라이브러리만, 입출력 없음).

Unsplash API 지침(2026-11-03 원문 확인): ① API 가 준 사진 주소의 `ixid` 는 크기 등을 바꿔 쓸 때도 **남긴다**(앱의 사진 조회 보고) ② 사진을 보여 줄 때
작가와 Unsplash 를 밝히고 작가 프로필 링크를 건다 ③ Unsplash 로 가는 링크에는 `?utm_source=앱이름&utm_medium=referral` 을 붙인다. 이 모듈은 그 세 가지를 Chance(`generator.py`)·
이슈 수정(`pipeline/edits`)·Blogger(`pipeline/main_image.py`)가 같은 규칙으로 쓰게 하는 작은 공용 부분이다.

- `with_ixid`: `urls.raw` 의 `ixid` 값이 `[A-Za-z0-9_\\-=]{1,200}` 에 정확히 맞고 하나뿐이면 새 주소에 남기고, 아니면 빼고(옛 동작) 글 발행은 막지 않는다.
- `clean_name`·`safe_profile_url`·`credit_markdown`: 작가 이름·프로필 주소를 검사·정리해 출처 한 줄(일반 마크다운 문단)을 만든다. 외부 문자열이라 보이지 않는 문자·제어 문자를 지우고
  길이를 제한하며(Blogger 의 `main_image._plain`·`safe_author_url` 과 같은 수준), 마크다운 특수문자는 이스케이프하고, Jekyll 의 Liquid 가 읽는 중괄호는 지운다(마크다운 이스케이프로는 막을 수 없다).
- `is_credit_line`·`strip_credit_lines`·`place_credit`: `credit_markdown` 이 쓸 수 있는 줄만 '우리 줄'로 본다(꼬리 `CREDIT_MARKER`·틀이 맞고, 이름 칸을 풀어 다시 쓴 줄과 글자까지 같은 줄).
  글에 이미 있는 우리 줄은(모델이 흉내 낸 것이든 옛 사진의 것이든) 모두 지우고 새 줄 하나를 이미지 줄 바로 다음에 넣는다 — 몇 번 해도 같은 결과(멱등)다. 모델 출력은 데이터라서 위조된 출처 줄이
  살아남지 못한다. 틀만 닮고 이름에 이스케이프되지 않은 마크다운·HTML·보이지 않는 문자가 든 줄은 우리 줄이 아니라서 지우지도 않고(그 글은 다른 검사의 몫) 이슈 수정의 사후 검증이 '우리 줄 교체'로 통과시키지도 않는다.

값은 모두 데이터다: 이 모듈의 어떤 함수도 파일·네트워크를 만지지 않고, 틀린 입력에는 예외 대신 빈 값(문자열 `""`, `None`, 빈 목록)을 돌려준다.
"""
import re
import unicodedata
import urllib.parse

UTM = "utm_source=chanceblog&utm_medium=referral"   # 출처 표기 링크의 utm 값(초안 패키지 pipeline/publishers/issue_package.py 의 UNSPLASH_UTM 과 같아야 한다 — 시험이 대조한다)
SITE_HOST, IMAGE_HOST, API_HOST = "unsplash.com", "images.unsplash.com", "api.unsplash.com"
SITE_URL = f"https://{SITE_HOST}/?{UTM}"
CREDIT_MARKER = f" on [Unsplash]({SITE_URL})*"       # 우리가 만든 출처 줄의 고정 꼬리 — 이 꼬리와 아래 틀이 모두 맞는 줄만 '우리 줄'이다
IXID_MAX, NAME_MAX, URL_MAX, LINE_MAX, QUERY_MAX = 200, 80, 500, 600, 2000

_IXID_RE = re.compile(r"[A-Za-z0-9_\-=]{1,%d}" % IXID_MAX)
_AUTHOR_PATH_RE = re.compile(r"/@[A-Za-z0-9_.\-]{1,64}")
_IMAGE_PATH_RE = re.compile(r"/photo-[A-Za-z0-9_\-]{1,64}")
_DOWNLOAD_PATH_RE = re.compile(r"/photos/[A-Za-z0-9_\-]{5,40}/download")
_LOOKUP_ID_RE = re.compile(r"[0-9]{6,20}-[0-9A-Za-z]{6,20}")
_BAD_URL_CHARS = re.compile("[\\s\\x00-\\x1f\\x7f<>\"'`\\\\]")
# 우리 줄의 대략의 틀: `*Photo by [이름](https://unsplash.com/@사용자?utm…) on [Unsplash](https://unsplash.com/?utm…)*`. 이름 칸은 `\X`(이스케이프 한 쌍) 또는 `\`·`]`·줄바꿈이 아닌 글자의 반복이라
# 두 갈래의 첫 글자가 겹치지 않아 되돌아가기가 늘지 않는다(선형). 이 틀은 1차 거름망이고, is_credit_line 은 이름을 풀어 같은 줄을 다시 만들어 보고 글자까지 같은 줄만 '우리 줄'로 본다.
_CREDIT_RE = re.compile(
    "\\*Photo by \\[(?P<name>(?:\\\\.|[^\\\\\\]\\n])+)\\]\\(https://unsplash\\.com/@(?P<user>[A-Za-z0-9_.\\-]{1,64})\\?" + re.escape(UTM) + "\\)" + re.escape(CREDIT_MARKER))
_UNESCAPE_RE = re.compile(r"\\(.)")

_BACKSLASH = chr(92)
_MD_SPECIAL = frozenset(_BACKSLASH + "[]()<>*_`|#")  # 마크다운에서 글자 뜻을 바꾸는 문자: 앞에 역슬래시를 붙여 글자 그대로 보이게 한다
_LIQUID_BRACES = frozenset("{}")                     # 출처 줄은 Liquid(`{{`·`{%`)를 처리하는 .md 글에 들어가고, Liquid 는 마크다운보다 먼저 읽으므로 이스케이프로는 못 막는다 → 지운다
_DROP_CATEGORIES = frozenset({"Cf", "Cs", "Co"})     # 서식(폭 없는 공백·방향 제어·BOM·소프트 하이픈…)·짝 없는 서로게이트·사용자 정의 영역: 지운다
_SPACE_CATEGORIES = frozenset({"Cc", "Zl", "Zp"})    # 제어 문자·줄·문단 구분자: 공백으로 바꾼다
_BLANK_LOOKALIKES = frozenset(chr(code) for code in (0x115F, 0x1160, 0x3164, 0xFFA0, 0x2800, 0x180E))   # 모양 없이 자리만 차지하는 글자(한글 채움 문자·점자 빈칸·몽골 모음 구분자) — 코드 포인트로 쓴다


class Credited(str):
    """사진 주소(문자열 그대로)에 그 사진의 출처 줄(마크다운 한 줄, 없으면 빈 문자열)을 `credit` 로 얹은 값. 이미지 선택기가 돌려준다 — 일반 문자열을 돌려주는 선택기와도 섞어 쓸 수 있다."""
    credit = ""


# ----------------------------------------------------------------------------
# 사진 주소와 ixid
# ----------------------------------------------------------------------------
def ixid_from_query(query):
    """질의 문자열(`a=b&c=d`)에서 `ixid` 값을 읽는다. 값이 정확히 하나이고 모양(영숫자·`_`·`-`·`=`, 1~200자)이 맞을 때만 그 값을, 아니면 빈 문자열을 돌려준다."""
    if not isinstance(query, str) or not query or len(query) > QUERY_MAX:
        return ""
    values = [value for key, value in urllib.parse.parse_qsl(query, keep_blank_values=True) if key == "ixid"]
    if len(values) != 1:
        return ""
    return values[0] if _IXID_RE.fullmatch(values[0]) else ""


def with_ixid(url, query, params):
    """질의 없는 사진 주소 `url` 에 크기·형식 매개변수 `params`(`?a=b&c=d` 꼴)를 붙인다. 원래 주소의 질의 `query` 에 올바른 ixid 가 있으면 `?ixid=<값>&…` 로 맨 앞에 남기고, 없거나 모양이 맞지 않으면
    ixid 없이 `url + params`(옛 동작) — 글 발행을 막지 않는다."""
    ixid = ixid_from_query(query)
    if not ixid:
        return f"{url}{params}"
    rest = params[1:] if params.startswith("?") else params
    return f"{url}?ixid={ixid}" + (f"&{rest}" if rest else "")


def _https_parts(raw, host):
    """https 이고 호스트(userinfo·포트 없이)가 정확히 host 인 주소의 urlsplit 결과. 따옴표·공백·제어 문자·꺾쇠·역슬래시가 있거나 길면 None."""
    text = raw.strip() if isinstance(raw, str) else ""
    if not text or len(text) > URL_MAX or _BAD_URL_CHARS.search(text):
        return None
    try:
        parts = urllib.parse.urlsplit(text)
    except ValueError:
        return None
    return parts if parts.scheme == "https" and parts.netloc == host else None


def photo_url_ok(url):
    """쓸 사진 주소(`https://images.unsplash.com/photo-<번호>` + 질의)의 모양 검사: 호스트가 정확히 images.unsplash.com 이고 경로가 `/photo-<번호>` 인가."""
    parts = _https_parts(url, IMAGE_HOST)
    return parts is not None and _IMAGE_PATH_RE.fullmatch(parts.path) is not None


def safe_download_url(raw):
    """`links.download_location` → 호스트가 정확히 api.unsplash.com 인 `/photos/<id>/download` 주소만(키가 따라가므로). 아니면 빈 문자열."""
    parts = _https_parts(raw, API_HOST)
    return raw.strip() if parts is not None and _DOWNLOAD_PATH_RE.fullmatch(parts.path) else ""


def photo_lookup_id(path_id):
    """고정 목록의 사진 번호(`1558494949-ef010cbdcc31` 꼴) → `GET /photos/<id>` 에 쓸 `photo-<번호>`. 모양이 다르면 빈 문자열."""
    return f"photo-{path_id}" if isinstance(path_id, str) and _LOOKUP_ID_RE.fullmatch(path_id) else ""


# ----------------------------------------------------------------------------
# 작가 이름·프로필 → 출처 줄
# ----------------------------------------------------------------------------
def clean_name(value, limit=NAME_MAX):
    """작가 이름(외부 문자열)을 한 줄 일반 글로: 보이지 않는 문자·서식 문자·Liquid 중괄호를 지우고, 제어 문자·특수 공백은 공백으로 바꿔 접고, limit 자로 자른다(넘으면 끝에 '…').
    보이는 글자(글자·숫자·기호·문장부호)가 하나도 없거나 문자열이 아니면 빈 문자열."""
    if not isinstance(value, str):
        return ""
    kept = []
    for char in value:
        category = unicodedata.category(char)
        if category in _DROP_CATEGORIES or char in _BLANK_LOOKALIKES or char in _LIQUID_BRACES:
            continue
        kept.append(" " if category in _SPACE_CATEGORIES else char)
    text = " ".join("".join(kept).split())
    if len(text) > limit:
        text = text[:limit - 1].rstrip() + "…"
    return text if any(unicodedata.category(char)[0] in "LNSP" for char in text) else ""


def escape_md(text):
    """마크다운 특수문자(`\\ [ ] ( ) < > * _ ` | #`)마다 앞에 역슬래시를 붙인다(링크 글자·강조·표·제목·코드·HTML 로 읽히지 않게)."""
    return "".join(_BACKSLASH + char if char in _MD_SPECIAL else char for char in text)


def safe_profile_url(raw):
    """`user.links.html` → `https://unsplash.com/@<사용자>`(질의·조각은 버린다). https·호스트가 정확히 unsplash.com·경로가 `/@사용자` 꼴(길이 제한)인 것만, 아니면 빈 문자열."""
    parts = _https_parts(raw, SITE_HOST)
    if parts is None or _AUTHOR_PATH_RE.fullmatch(parts.path) is None:
        return ""
    return f"https://{SITE_HOST}{parts.path}"


def _render(clean, profile):
    """정리를 마친 이름과 검사를 마친 프로필 주소로 출처 줄을 쓴다(검사는 부르는 쪽이 한다)."""
    return f"*Photo by [{escape_md(clean)}]({profile}?{UTM}){CREDIT_MARKER}"


def credit_markdown(name, profile_url):
    """출처 한 줄: `*Photo by [이름](프로필?utm…) on [Unsplash](https://unsplash.com/?utm…)*`(영어 한 가지 문구 — 한국어 글에도 같다). 이름이 정리 뒤 비거나 프로필 주소가 검사에 걸리면 빈 문자열."""
    clean, profile = clean_name(name), safe_profile_url(profile_url)
    return _render(clean, profile) if clean and profile else ""


def author_of(item):
    """Unsplash 사진 응답 한 건(`/search/photos` 의 항목 또는 `/photos/<id>`)에서 (이름, 프로필 주소)를 읽는다 — 이름은 `user.name`(없으면 `user.username`), 주소는 `user.links.html`.
    검사·정리를 통과해 출처 줄을 만들 수 있을 때만 정리된 값 한 쌍을, 아니면 None(그 사진은 출처를 못 적으니 쓰지 않는다)."""
    user = item.get("user") if isinstance(item, dict) else None
    if not isinstance(user, dict):
        return None
    links = user.get("links") if isinstance(user.get("links"), dict) else {}
    name = clean_name(user.get("name")) or clean_name(user.get("username"))
    profile = safe_profile_url(links.get("html"))
    return (name, profile) if name and profile and credit_markdown(name, profile) else None


# ----------------------------------------------------------------------------
# 글 안의 출처 줄 찾기·지우기·넣기
# ----------------------------------------------------------------------------
def is_credit_line(line):
    """한 줄이 우리가 만든 출처 줄인가(앞뒤 공백은 무시). 꼬리(`CREDIT_MARKER`)와 틀이 맞고, 이름 칸을 풀어 `credit_markdown` 으로 다시 만든 줄과 **글자까지 같아야** 한다 —
    그래서 이름에 이스케이프되지 않은 마크다운·HTML·보이지 않는 문자·중괄호가 있거나 80자를 넘거나 링크가 우리 틀과 다른 줄은 흉내만 낸 줄이라 '우리 줄'이 아니다."""
    text = line.strip() if isinstance(line, str) else ""
    if not (text and len(text) <= LINE_MAX and text.startswith("*Photo by [") and text.endswith(CREDIT_MARKER)):
        return False
    match = _CREDIT_RE.fullmatch(text)
    if match is None:
        return False
    name = _UNESCAPE_RE.sub(r"\1", match.group("name"))
    profile = f"https://{SITE_HOST}/@{match.group('user')}"
    return clean_name(name) == name and safe_profile_url(profile) == profile and text == _render(name, profile)


def credit_lines(text):
    """글 안의 우리 모양 출처 줄(앞뒤 공백을 뺀 것)을 나오는 순서대로."""
    return [line.strip() for line in str(text or "").split("\n") if is_credit_line(line)]


def strip_credit_lines(text):
    """글에서 우리 모양의 출처 줄을 모두 지운다(그 줄이 빈 줄 둘 사이에 있었으면 빈 줄 하나를 더 지워 빈 줄이 겹치지 않게). 없으면 글이 그대로다."""
    lines = str(text or "").split("\n")
    out, i = [], 0
    while i < len(lines):
        if not is_credit_line(lines[i]):
            out.append(lines[i])
            i += 1
            continue
        after = i + 1
        while after < len(lines) and is_credit_line(lines[after]):
            after += 1
        between_blanks = bool(out) and not out[-1].strip() and after < len(lines) and not lines[after].strip()
        i = after + 1 if between_blanks else after
    return "\n".join(out)


def _image_line_re(image_url):
    return re.compile("!\\[[^\\]\\n]*\\]\\(" + re.escape(str(image_url)) + "\\)")


def place_credit(text, image_url, credit_line):
    """글의 출처 줄을 `credit_line` 하나로 맞춘다: 우리 모양의 줄(옛 사진의 것·모델이 흉내 낸 것)을 모두 지우고, 유효한 `credit_line` 이 있으면 `![…](image_url)` 줄 바로 다음 줄에 넣는다.
    그 이미지 줄이 글에 없으면 줄을 넣지 않는다. 몇 번을 해도 결과가 같다."""
    stripped = strip_credit_lines(text)
    if not credit_line or not is_credit_line(credit_line):
        return stripped
    target = _image_line_re(image_url)
    lines = stripped.split("\n")
    for index, line in enumerate(lines):
        if target.fullmatch(line.strip()):
            lines.insert(index + 1, credit_line.strip() + ("\r" if line.endswith("\r") else ""))
            break
    return "\n".join(lines)


def credit_problems(text, image_url):
    """글 안의 우리 모양 출처 줄이 규칙을 지키는지 본다(검증용): 둘 이상이면 안 되고, 하나면 `![…](image_url)` 줄 바로 다음 줄이어야 한다. 어긋난 이유 목록(비어 있으면 정상)."""
    lines = str(text or "").split("\n")
    found = [index for index, line in enumerate(lines) if is_credit_line(line)]
    problems = []
    if len(found) > 1:
        problems.append("출처 줄이 둘 이상입니다.")
    if found and not (found[0] > 0 and _image_line_re(image_url).fullmatch(lines[found[0] - 1].strip())):
        problems.append("출처 줄이 새 대표 이미지 줄 바로 다음에 있지 않습니다.")
    return problems
