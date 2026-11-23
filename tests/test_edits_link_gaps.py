"""AI 수정의 새 외부 링크 검사(D-353)에 독립 검증이 남긴 틈 닫기(결함 D-365·D-367, 검증자 S 의 SP-12·SP-14–SP-16, Q 의 QR2-1·QR2-2).

1. 슬래시 없는 앱 스킴(SP-12): `bitcoin:`·`tg:`·`ms-word:` 처럼 `//` 없이 `스킴:값` 으로 쓰는 링크는 알려진 15개 밖이면 주소로 안 읽혀 지나갔다. 이제 앱·결제·처리기 스킴 목록과 접두사(`ms-`·`web+`)를
   **눌리는 링크 자리**(링크 대상·꺾쇠 대상·HTML 속성·참조식 정의·자동 링크 …)에서 값이 있을 때 읽는다 — 콜론 뒤 공백·탭·줄바꿈 뒤의 값도(`[x](tg: resolve)`) 읽되 꺾쇠 없는 정의의 같은 줄은 값이 주소 모양일 때만 읽는다(D-393, 새 시험 파일 test_edits_definition_lines). 글에 가까운 두 자리 — 각주 정의(라벨이 kramdown 각주 ID 꼴 `[^낱말]`
   일 때)의 본문과 `cite` 속성 — 에서는 읽지 않는다: 거기에는 영문 글머리(`News: …`·`Market:KOSPI`)가 흔하다(SP-4 오탐이 되살아나지 않게). `[^]`·`[^.]`·`[^a b]`·`[^각주]` 같은 라벨은 각주가 아니라 참조식 정의라 읽는다.
   값이 없는 글머리(`News:`)는 어느 자리에서도 주소가 아니다.
2. image-set(SP-14): 따옴표 주소 안에 `)` 가 있으면 지나갔고, 닫는 괄호 없는 `image-set(` 을 되풀이하면 제곱 시간이었다. 이제 따옴표·괄호를 세는 상태기계 하나가 한 번에 읽는다(선형, 상한 없음).
3. 참고(SP-15·SP-16): 링크 대상·속성·자동 링크의 끝 문장부호는 그대로 견준다는 것, 주소 안 보이지 않는 글자·srcset 이름 경계·목록 밖 스킴의 꺾쇠 자동 링크를 못박는다.
시험 안의 표는 코드의 목록을 import 하지 않는 독립 목록이다 — 코드의 목록에서 낱말 하나를 빼면 한 칸씩 빨개진다. 가짜 값만 쓴다.
"""
import random
import re
import time
import unicodedata
import unittest

import _bootstrap  # noqa: F401
from pipeline.edits import checks

LIMITS = {"max_changed_files": 1, "max_changed_lines": 80, "max_file_chars": 80000}
BASE = "안녕하세요. 소개 문장입니다.\n문의는 [GitHub](https://github.com/owner/repo) 로 주세요.\n"


def verify(before, after):
    return checks.verify_changes({"about.md": (before, after)}, ["about.md"], LIMITS, ai_patch=True)


def link_reasons(reasons):
    return [reason for reason in reasons if "외부 링크" in reason]


def blocked(payload, before=BASE):
    return len(link_reasons(verify(before, before + payload + "\n"))) == 1


# 슬래시 없이 `스킴:값` 으로 쓰는 앱·결제·처리기 스킴 — 시험의 독립 목록(종류별). 코드의 `_APP_SCHEMES` 와 같은 낱말이어야 한다.
PAYMENT = ("bitcoin", "bitcoincash", "litecoin", "ethereum", "monero", "dogecoin", "dash", "zcash", "lightning", "nostr", "solana", "tron", "stellar")
MESSENGER = ("tg", "whatsapp", "viber", "weixin", "wechat", "line", "signal", "sgnl", "threema", "zalo", "slack", "discord", "msteams", "zoommtg", "zoomus", "webex",
             "smsto", "mmsto", "mms", "imessage", "facetime-audio")
APPS = ("steam", "spotify", "market", "itms", "itms-apps", "itms-services", "intent", "maps", "geo", "vscode", "vscode-insiders", "obsidian", "notion")
REMOTE = ("ssh", "sftp", "git", "svn", "irc", "ircs", "telnet", "rdp", "vnc", "smb", "nfs", "afp", "ldap", "ldaps", "gopher", "news", "snews", "nntp", "tftp", "rtsp", "rtmp",
          "webcal", "webcals", "feed", "dict", "rsync")
BROWSER_AND_WINDOWS = ("search", "search-ms", "about", "chrome", "chrome-extension", "edge", "blob")
PREFIXED = ("ms-word", "ms-excel", "ms-powerpoint", "ms-msdt", "ms-settings", "ms-appinstaller", "ms-officecmd", "web+mastodon", "web+example")
LISTED = PAYMENT + MESSENGER + APPS + REMOTE + BROWSER_AND_WINDOWS
ALL_APP_SCHEMES = LISTED + PREFIXED

# 링크를 쓰는 자리 네 곳(`{s}` 는 스킴)
PLACES = (
    ("마크다운 링크", "[x]({s}:evil.example/a)"),
    ("HTML 속성", '<a href="{s}:evil.example/a">x</a>'),
    ("참조식 정의", "[x][1]\n\n[1]: {s}:evil.example/a"),
    ("꺾쇠 자동 링크", "<{s}:evil.example/a>"),
)

# 검증자(S·Q)가 'R1 은 거절하는데 R2 는 통과' 라고 짚은 실제 모양의 링크
VERIFIER_PROBES = (
    "bitcoin:1BoatSLRHtKNngkdXEeobR76b53LETtpyT", "ethereum:0x32Be343B94f860124dC4fEe278FDCBD38C102D88", "litecoin:LbTjMGN7gELw4KbeyQf6cTCq859hD18guE",
    "tg:resolve?domain=evil", "ms-word:ofe|u|evil.example/doc.docx", "ms-excel:ofe|u|evil.example/x.xlsx", "ms-msdt:/id", "search-ms:query=x", "steam:run/1",
    "spotify:track:abc", "whatsapp:send?phone=1", "viber:chat?number=1", "intent:#Intent;scheme=evil;end", "market:details?id=evil", "weixin:dl/business", "zoommtg:join",
    "webcal:evil.example/a.ics", "irc:evil.example", "news:alt.x", "geo:37.78,-122.40", "maps:q=evil", "about:blank", "chrome:flags", "git:evil", "svn:evil", "ssh:evil@host",
    "sftp:evil@host", "gopher:evil.example/1", "slack:open", "nntp:evil.example", "telnet:evil.example",
)


# 각주 라벨(2차 검증 S-1·R-2·SQ-1): kramdown 의 각주 ID 는 영문·숫자·밑줄로 시작하고 영문·숫자·밑줄·하이픈이 이어지는 낱말뿐이다. 그 밖의 `[^…]` 라벨은 각주가 아니라 참조식 정의다.
NOT_FOOTNOTE_LABELS = ("^", "^.", "^ ", "^!x", "^-x", "^,", "^a b", "^1.", "^각주", "^a.b", "^a:b", "^ a", "^^")
FOOTNOTE_LABELS = ("^1", "^note", "^note-2", "^a_b", "^A1", "^_x", "^9-9")
LABEL_PAYLOADS_ALWAYS_READ = ("//evil.example/a", "tg://evil.example/a", "ssh://evil.example/a", "foo://evil.example/a", "skype:evil.example")
LABEL_PAYLOADS_APP = ("bitcoin:1BoatSLRHtKNngkdXEeobR76b53LETtpyT", "tg:resolve?domain=evil", "ms-msdt:/id", "Market:KOSPI", "News:연합뉴스", "About:me")
# 눌리는 링크 자리에서 콜론 뒤에 공백·탭·줄바꿈이 오고 값이 이어지는 꼴(2차 검증 R-1) — `{s}` 는 스킴. 값 첫 마디는 `resolve?x=1`. 꺾쇠 없는 정의의 같은 줄 공백 뒤 값은 주소 모양(`resolve?x=1`)일 때만 읽힌다 — 아래 세 행이 M103 그대로이고 값이 낱말이면 글이다(D-393 — test_edits_definition_lines 가 갈래를 못박는다).
SPACED_FORMS = (
    ("마크다운 링크의 콜론 뒤 공백", "[x]({s}: resolve?x=1)"),
    ("그림", "![x]({s}: resolve?x=1)"),
    ("꺾쇠 대상", "[x](<{s}: resolve?x=1>)"),
    ("콜론 뒤 탭", "[x]({s}:\tresolve?x=1)"),
    ("콜론 뒤 줄바꿈", "[x]({s}:\nresolve?x=1)"),
    ("콜론 뒤 여러 공백", "[x]({s}:   resolve?x=1)"),
    ("참조식 정의의 콜론 뒤 공백", "[x][r]\n\n[r]: {s}: resolve?x=1"),
    ("인용문 안 정의", "[x][r]\n\n> [r]: {s}: resolve?x=1"),
    ("제목이 붙은 정의", "[x][r]\n\n[r]: {s}: resolve?x=1 \"제목\""),
    ("주소 토큰이 줄 끝인 정의", "[x][r]\n\n[r]: {s}:\nresolve?x=1"),
    ("꺾쇠 정의", "[x][r]\n\n[r]: <{s}: resolve?x=1>"),
    ("인용문 안 꺾쇠 정의", "[x][r]\n\n> [r]: <{s}: resolve?x=1>"),
    ("제목이 붙은 꺾쇠 정의", "[x][r]\n\n[r]: <{s}: resolve?x=1> \"제목\""),
)


class SlashlessAppSchemeTest(unittest.TestCase):
    def test_every_listed_scheme_written_without_slashes_is_an_external_address_in_every_place_a_link_can_be_written(self):
        for scheme in ALL_APP_SCHEMES:
            for place, template in PLACES:
                with self.subTest(scheme=scheme, place=place):
                    text = template.format(s=scheme)
                    self.assertEqual(checks.external_links(text), {f"{scheme}://evil.example/a"})
                    self.assertTrue(blocked(text))

    def test_the_scheme_is_read_without_regard_to_case(self):
        self.assertEqual(checks.external_links("[x](BitCoin:abc) <a href='TG:resolve?x=1'>y</a> [z](MS-Word:ofe)"), {"bitcoin://abc", "tg://resolve?x=1", "ms-word://ofe"})

    def test_the_slashless_links_the_verifiers_found_open_are_rejected_as_link_targets_and_as_attributes(self):
        for probe in VERIFIER_PROBES:
            with self.subTest(probe=probe):
                self.assertTrue(blocked(f"[x]({probe})"))
                self.assertTrue(blocked(f'<a href="{probe}">x</a>'))

    def test_an_english_lead_word_followed_by_a_colon_and_a_space_is_text_in_a_footnote_a_cite_or_with_no_value(self):
        """영문 각주(라벨이 각주 ID 꼴)의 본문·`cite` 속성의 글머리(`News: …`·`Market: …`)·값이 없는 `낱말:` 은 주소가 아니다 — SP-4 의 오탐이 되살아나지 않는다. (링크 대상·참조식 정의의 `낱말: 글` 은 kramdown 이 링크로 만드니 읽는다 — 아래 시험.)"""
        for scheme in ALL_APP_SCHEMES:
            for word in (scheme.capitalize(), scheme.upper()):
                for text in (f"문장입니다[^1]\n\n[^1]: {word}: Some source text", f"문장입니다[^note]\n\n[^note]: {word}: Some source text", f'<q cite="{word}: 2020">y</q>',
                             f"[x]({word}:)", f"[^1]: {word}:", f"<{word}: >"):
                    with self.subTest(text=text):
                        self.assertEqual(checks.external_links(text), set())

    def test_a_value_attached_to_the_colon_is_text_in_a_footnote_definition_and_a_cite_attribute_but_a_link_in_a_link_place(self):
        """각주 정의의 본문과 cite 속성은 글에 가까운 자리다: `[^1]: Market:KOSPI`·`<q cite="Market:서울">` 처럼 값이 콜론에 붙어도 주소가 아니다(검토자가 짚은 오탐). 눌리는 링크 자리의 같은 꼴은 주소다."""
        for scheme in ALL_APP_SCHEMES:
            word = scheme.capitalize()
            for text in (f"[^1]: {word}:KOSPI 지수", f"[^1]: {word}:연합뉴스 보도", f"> - [^2]: {word}:me", f'<q cite="{word}:서울">y</q>', f"<q cite='{word}:me'>y</q>", f"<q cite={word}:me>y</q>"):
                with self.subTest(text=text):
                    self.assertEqual(checks.external_links(text), set())
            with self.subTest(scheme=scheme, place="링크 대상"):
                self.assertEqual(checks.external_links(f"[x]({word}:KOSPI)"), {f"{scheme}://kospi"})

    def test_a_footnote_definition_and_a_cite_attribute_still_read_slashes_and_known_schemes(self):
        for text in ("[^1]: //evil.example/a", "[^1]: tg://evil.example/a", '<q cite="//evil.example/a">y</q>', '<q cite="foo://evil.example/a">y</q>', "[^1]: skype:evil.example"):
            with self.subTest(text=text):
                self.assertTrue(blocked(text))

    def test_a_space_after_the_colon_does_not_hide_an_app_link_in_a_clickable_attribute(self):
        """눌리는 속성은 콜론 뒤 공백도 값으로 센다(브라우저가 그 꼴을 처리기에 넘기는지는 확인하지 못했다 — 막는 쪽이 안전하다). 링크 대상은 공백에서 끊기므로 `[x](News: 글)` 는 글이다."""
        for text in ('<a href="ms-msdt: /id PCWDiagnostic">x</a>', '<a href="tg: resolve?domain=evil">x</a>', "<a href='bitcoin: 1BoatSLR'>x</a>"):
            with self.subTest(text=text):
                self.assertTrue(blocked(text))


    def test_a_label_that_is_not_a_kramdown_footnote_id_makes_a_reference_definition_that_is_read_in_full(self):
        """`[^]`·`[^.]`·`[^a b]`·`[^각주]` 는 각주가 아니라 참조식 정의라 `//` 주소도 앱 스킴도 읽는다(2차 검증 S-1: 시작점이 막던 `[^]: //host` 가 통과로 바뀌었다 · R-2·SQ-1: 앱 스킴이 지나갔다)."""
        for label in NOT_FOOTNOTE_LABELS:
            for payload in LABEL_PAYLOADS_ALWAYS_READ + LABEL_PAYLOADS_APP:
                with self.subTest(label=label, payload=payload):
                    self.assertTrue(blocked(f"[눌러][{label}]\n\n[{label}]: {payload}"))

    def test_a_real_footnote_id_keeps_the_body_a_text_for_app_schemes_but_not_for_slashes_or_known_schemes(self):
        for label in FOOTNOTE_LABELS:
            for payload in LABEL_PAYLOADS_APP:
                with self.subTest(label=label, payload=payload):
                    self.assertEqual(checks.external_links(f"[x][{label}]\n\n[{label}]: {payload}"), set())
            for payload in LABEL_PAYLOADS_ALWAYS_READ:
                with self.subTest(label=label, payload=payload):
                    self.assertTrue(blocked(f"[x][{label}]\n\n[{label}]: {payload}"))

    def test_a_space_or_a_line_break_after_the_colon_does_not_hide_an_app_link_in_a_link_target_or_a_definition(self):
        """링크 대상·꺾쇠 정의, 주소 토큰이 줄 끝인 정의는 콜론 뒤 공백·줄바꿈 뒤 값을 읽는다 — `[x](tg: resolve…)`·`[x](<tg: …>)`·`[r]: <tg: …>`(2차 검증 R-1: 첫 L6 머리는 거절했고 시작점은 통과시켰다). 꺾쇠 없는 정의의 같은 줄은 값이 주소 모양일 때만 읽는다(D-393)."""
        for scheme in ALL_APP_SCHEMES:
            for place, template in SPACED_FORMS:
                with self.subTest(scheme=scheme, place=place):
                    text = template.format(s=scheme)
                    self.assertEqual(checks.external_links(text), {f"{scheme}://resolve?x=1"})
        self.assertTrue(blocked("[x](tg: resolve?domain=evil)"))
        self.assertTrue(blocked("[x][r]\n\n[r]: <bitcoin: 1BoatSLRHtKNngkdXEeobR76b53LETtpyT>"))

    def test_a_listed_word_followed_by_a_colon_and_a_space_is_read_in_a_link_target_and_in_a_definition(self):
        """`[x](News: 글)`·`[News]: <News: 글>`·`[News]: News:` + 다음 줄 값은 링크 자리라 읽는다 — 그런 글은 실제 글에 없다(저장소 글에서 `](` 바로 뒤의 스킴은 https·mailto 뿐). 꺾쇠 없는 정의의 같은 줄 `[News]: News: 글` 은 값이 낱말이면 영문 글머리라 읽지 않는다(D-393). 각주·cite 의 같은 글머리도 위 시험처럼 글이다."""
        for scheme in ("news", "market", "line", "search", "about", "tg"):
            word = scheme.capitalize()
            for text in (f"[x]({word}: some text)", f"[{word}]: <{word}: some text>", f"[{word}]: {word}:\nsome text", f"[x](<{word}: some text>)"):
                with self.subTest(text=text):
                    self.assertEqual(checks.external_links(text), {f"{scheme}://some"})

    def test_a_colon_followed_by_a_space_and_nothing_or_a_title_is_still_text_and_unknown_words_stay_text(self):
        for scheme in ("tg", "news", "market", "ms-word"):
            for text in (f"[x]({scheme}: )", f"[x]({scheme}: \"title\")", f"[x](<{scheme}: >)", f"[x][r]\n\n[r]: {scheme}:", f"[x]({scheme}:\n)"):
                with self.subTest(text=text):
                    self.assertEqual(checks.external_links(text), set())
        for text in ("[x](Source: BBC)", "[x](foo: bar)", "[Update]: Fixed: yes", "[x](Note: see below)", "[x](file: config.yml)", "[x](smith: 2020)", "[1]: See: //comment"):
            with self.subTest(text=text):
                self.assertEqual(checks.external_links(text), set())

    def test_a_listed_word_inside_a_path_or_without_a_colon_is_not_an_address(self):
        for word in ("news", "market", "tg", "about", "ms-word"):
            for target in (word, f"posts/{word}:abc", f"/{word}:abc", f"?t={word}:abc", f"#{word}:abc", f"{word}-extra"):
                with self.subTest(target=target):
                    self.assertEqual(checks.external_links(f"[x]({target})"), set())

    def test_mail_and_phone_links_stay_outside_this_check_and_unknown_words_still_need_slashes(self):
        self.assertEqual(checks.external_links("[a](mailto:someone@example.com) [b](tel:+82101234567) [c](foo:abc) [d](smith:2020)"), set())
        self.assertEqual(checks.external_links("[c](foo://evil.example/a)"), {"foo://evil.example/a"})

    def test_an_app_link_the_page_already_has_may_stay_move_and_repeat_but_a_new_one_is_rejected(self):
        before = BASE + "[문의](tg:resolve?domain=owner)\n"
        self.assertEqual(verify(before, before.replace("문의", "연락")), [])
        self.assertEqual(verify(before, before + "다시 [문의](tg:resolve?domain=owner)\n"), [])
        self.assertEqual(len(link_reasons(verify(before, before + "[더](tg:resolve?domain=other)\n"))), 1)
        self.assertEqual(len(link_reasons(verify(before, before + "[돈](bitcoin:abc)\n"))), 1)

    def test_normal_edits_of_a_page_with_english_footnotes_are_still_accepted(self):
        before = BASE + "문장입니다[^1]\n\n[^1]: IMF: World Economic Outlook\n"
        for after in (before.replace("문장입니다", "문장 입니다"), before + "추가 문장[^2]\n\n[^2]: News: BBC 2020\n", before + "[^3]: Market: KOSPI 지수\n",
                      before + '<q cite="Search: 2020">y</q>\n', before + "[Update]: Fixed: yes\n", before + "[x](Source: BBC)\n", before + "[^note]: Market:KOSPI 지수\n",
                      before + "[Update]: Line: 12\n", before + "[1]: News: BBC 2020\n"):
            with self.subTest(after=after[-40:]):
                self.assertEqual(verify(before, after), [])


# --- image-set (SP-14) -----------------------------------------------------------------------------------------------------------------------------

def reference_image_set_strings(text):
    """시험 안의 느리고 단순한 기준 구현: `image-set(` 마다 따로 앞에서부터 읽는다(코드는 한 번에 읽는 상태기계다). 깊이 상한 6·안 닫힌 따옴표 300자는 코드와 같은 약속이다.
    역슬래시는 바로 뒤가 image-set( 이 아닐 때만 다음 글자를 이스케이프한다(CSS 는 역슬래시와 i 를 i 로 읽으니 그 꼴도 함수다). 안 닫힌 따옴표는 지울 글자를 먼저 지우고 `)"'<>` 앞에서 자른다."""
    found = []
    for start in re.finditer(r"(?i)(?<!\w)image-set\(", text):
        quote, opened, depth, index = None, 0, 1, start.end()
        while index < len(text):
            char = text[index]
            if char == "\\" and text[index + 1:index + 11].lower() != "image-set(":
                index += 2
                continue
            if quote:
                if char == quote:
                    found.append(text[opened:index])
                    quote = None
            elif char in "'\"":
                quote, opened = char, index + 1
            elif char == "(":
                depth = min(depth + 1, 6)
            elif char == ")":
                if depth == 1:
                    break
                depth = depth - 1 if depth < 6 else depth
            index += 1
        else:
            if quote:
                cleaned = "".join(ch for ch in text[opened:] if not ch.isspace() and unicodedata.category(ch) not in ("Cc", "Cf"))
                found.append(re.split(r"[)\"'<>]", cleaned, 1)[0][:300])
    return found



STYLE = '<div style="background-image:{value}">x</div>'
IMAGE_SET_READS = {
    "주소 안에 닫는 괄호": (STYLE.format(value="image-set('//evil.example/a).png' 1x)"), {"//evil.example/a).png"}),
    "둘째 후보의 주소 안에 닫는 괄호": (STYLE.format(value="image-set('/ok.png' 1x, '//evil.example/a).png' 2x)"), {"//evil.example/a).png"}),
    "큰따옴표와 닫는 괄호": ("<div style='background-image:image-set(\"//evil.example/a).png\" 1x)'>x</div>", {"//evil.example/a).png"}),
    "접두사 붙은 이름과 닫는 괄호": (STYLE.format(value="-webkit-image-set('//evil.example/a).png' 1x)"), {"//evil.example/a).png"}),
    "여는 괄호가 든 주소": (STYLE.format(value="image-set('//evil.example/a(1.png' 1x)"), {"//evil.example/a(1.png"}),
    "url() 뒤에 이어 쓴 문자열 후보": (STYLE.format(value="image-set(url(a.png) 1x, '//evil.example/b.png' 2x)"), {"//evil.example/b.png"}),
    "image-set 안의 image-set 뒤 후보": (STYLE.format(value="image-set(image-set('/a.png' 1x) 1x, '//evil.example/c.png' 2x)"), {"//evil.example/c.png"}),
    "이스케이프한 따옴표 뒤 후보": (STYLE.format(value="image-set('x\\'' 1x, '//evil.example/b.png' 2x)"), {"//evil.example/b.png"}),
    "공백으로 아주 길게 밀어낸 주소": (STYLE.format(value="image-set(" + " " * 20000 + "'//evil.example/a.png' 1x)"), {"//evil.example/a.png"}),
    "주석으로 아주 길게 밀어낸 주소": (STYLE.format(value="image-set(/*" + "x" * 20000 + "*/ '//evil.example/a.png' 1x)"), {"//evil.example/a.png"}),
    "앞의 가짜 image-set 과 짝 없는 따옴표가 따옴표 짝을 어긋나게 해도": ("image-set( ' stray image-set('//evil.example/a.png' 1x)", {"//evil.example/a.png"}),
    "앞에 닫힌 image-set 이 있고 뒤에 역슬래시가 앞선 image-set": ("<p style=\"background:image-set()\">x</p><p style=\"background:\\image-set('//evil.example/a.png' 1x)\">x</p>", {"//evil.example/a.png"}),
    "역슬래시가 앞선 대문자 이름": (STYLE.format(value="image-set('/ok.png' 1x) \\IMAGE-SET('//evil.example/a.png' 1x)"), {"//evil.example/a.png"}),
    "같은 주소가 여러 번": (STYLE.format(value="image-set('//evil.example/a.png' 1x, '//evil.example/a.png' 2x)"), {"//evil.example/a.png"}),
    "대문자 이름": (STYLE.format(value="IMAGE-SET('//evil.example/a.png' 1x)"), {"//evil.example/a.png"}),
    "읽을 것 없음(사이트 안 경로)": (STYLE.format(value="image-set('/a.png' 1x, 'b.png' 2x)"), set()),
    "읽을 것 없음(따옴표 없는 url)": (STYLE.format(value="image-set(url(/a.png) 1x)"), set()),
}


def best_cpu_time(text, repeat=3):
    """세 번 중 가장 짧은 CPU 시간(벽시계가 아니다 — 다른 프로세스가 CPU 를 나눠 써서 느려져도 값이 안 흔들린다)."""
    best = None
    for _ in range(repeat):
        started = time.process_time()
        checks.external_links(text)
        spent = time.process_time() - started
        best = spent if best is None else min(best, spent)
    return best


class ImageSetTest(unittest.TestCase):
    def test_the_quoted_addresses_of_an_image_set_are_read_wherever_the_closing_paren_is(self):
        for name, (text, expected) in IMAGE_SET_READS.items():
            with self.subTest(name=name):
                self.assertEqual(checks.external_links(text), expected)

    def test_an_address_whose_string_is_never_closed_is_still_read(self):
        """CSS 는 글 끝에서 열린 문자열을 닫는다 — 따옴표를 닫지 않은 주소도 호스트를 읽는다."""
        keys = checks.external_links(STYLE.format(value="image-set('//evil.example/a.png 1x)"))
        self.assertTrue(any(key.startswith("//evil.example/a.png") for key in keys), keys)

    def test_an_unterminated_string_pushed_far_by_blank_characters_is_still_read_as_an_address(self):
        """안 닫힌 따옴표 뒤에 공백·탭·줄바꿈·폭 없는 공백을 수백 개 끼워도(브라우저는 주소 앞의 공백을 지운다) 지운 뒤에 자르므로 주소를 읽는다(검토자가 짚은 우회: 299개부터 통과했다)."""
        for pad in (" ", "\t", "\n", chr(0x200B)):
            with self.subTest(pad=repr(pad)):
                self.assertEqual(checks.external_links(STYLE.format(value="image-set('" + pad * 400 + "//evil.example/a.png")), {"//evil.example/a.png"})

    def test_a_broken_css_string_in_the_original_does_not_turn_a_later_edit_into_a_new_address(self):
        """원문에 닫히지 않은 따옴표가 든 깨진 CSS 가 있어도 키는 주소 부분(호스트·경로)까지만이라, 그 뒤 문장을 고치는 정상 수정이 새 외부 링크로 거절되지 않는다. 주소 자체를 바꾸면 거절된다."""
        broken = "<div style=\"background-image:image-set('//cdn.example/a.png 1x)\">x</div>"
        before = BASE + broken + "\n뒤 문장입니다.\n"
        self.assertEqual(verify(before, before.replace("뒤 문장", "뒤 문구")), [])
        self.assertEqual(len(link_reasons(verify(before, before.replace("//cdn.example/a.png", "//other.example/a.png")))), 1)


    def test_an_unterminated_address_is_cut_at_three_hundred_characters(self):
        """안 닫힌 따옴표 뒤 주소는 지운 글 기준 300자까지만 키가 된다(2차 검증 SQ-2: 상한을 키워도 시험이 초록이었다)."""
        keys = checks.external_links(STYLE.format(value="image-set('//evil.example/" + "a" * 400))
        self.assertEqual({len(key) for key in keys}, {300})
        self.assertTrue(all(key.startswith("//evil.example/aaaa") for key in keys))

    def test_a_nesting_deeper_than_six_is_read_on_as_if_the_function_never_closed(self):
        """괄호 깊이 6 을 넘는 중첩은 닫히는 곳을 모른다고 보고 계속 읽는다(넓게 잡는 쪽) — 깊이 상한을 키우면 이 뒤의 주소를 안 읽게 된다(2차 검증 SQ-2)."""
        text = STYLE.format(value="image-set(" + "(" * 8 + ")" * 9 + " '//evil.example/a')")
        self.assertEqual(checks.external_links(text), {"//evil.example/a"})

    def test_a_new_image_set_address_is_rejected_in_an_ai_patch_and_a_kept_one_is_not(self):
        text = STYLE.format(value="image-set('//cdn.example/a).png' 1x)")
        self.assertTrue(blocked(text))
        before = BASE + text + "\n"
        self.assertEqual(verify(before, before.replace("소개 문장", "소개 문구")), [])
        self.assertEqual(len(link_reasons(verify(before, before + STYLE.format(value="image-set('//cdn.example/b).png' 1x)") + "\n"))), 1)

    def test_the_state_machine_agrees_with_a_slow_independent_reader_on_random_input(self):
        pieces = ("image-set(", "-image-set(", "IMAGE-SET(", "\\image-set(", "'", '"', "(", ")", "a", " ", "\t", "<", ">", chr(0x200B), "//e.example/p", "\\'", '\\"', "\\\\", "url(", "x)", "image-set('", 'image-set("')
        rng = random.Random(20261122)
        for _ in range(1500):
            text = "".join(rng.choice(pieces) for _ in range(rng.randint(1, 45)))
            with self.subTest(text=text):
                self.assertEqual(set(checks._image_set_strings(text)), set(reference_image_set_strings(text)))

    def test_reading_time_grows_in_proportion_to_the_text_not_with_its_square(self):
        """닫는 괄호가 없거나 따옴표가 맞물린 `image-set(` 이 되풀이되는 글에서 시작마다 끝까지 훑어 제곱 시간이었다(검증자 S 의 SP-14: 8만 자에 3.5초). 크기를 두 배로 하면 시간은 3배 미만이다."""
        for label, unit, tail in (("닫는 괄호 없음", "image-set(", ""), ("접두사", "-webkit-image-set(", ""), ("괄호가 맨 끝에 하나", "image-set(", ")"),
                                  ("따옴표가 맞물림", "image-set('", ")"), ("중첩 괄호", "image-set((", ")")):
            with self.subTest(label=label):
                small, large = best_cpu_time(unit * 6000 + tail), best_cpu_time(unit * 12000 + tail)
                self.assertLess(large, 3.0 * small + 0.5, (small, large))                # 선형이면 두 배 안팎, 제곱이면 네 배 — CPU 시간의 눈금이 거칠어(약 0.016초) 작은 쪽이 0 에 가까울 때를 위해 0.5초 여유(새 코드는 0.1초 안팎)
                self.assertLess(large, 10.0)


# --- 참고(SP-15·SP-16) ---------------------------------------------------------------------------------------------------------------------------

class TrailingPunctuationOfLinksTest(unittest.TestCase):
    def test_only_a_bare_address_in_prose_loses_its_closing_punctuation_a_link_is_compared_exactly(self):
        """글 속 맨주소는 끝 문장부호·강조 기호를 떼고 견준다(GFM 자동 링크 규칙과 같다 — 이 사이트의 kramdown 은 글 속 맨주소를 링크로 만들지 않아 눌리지도 않는다). 같은 주소를 링크 대상·HTML 속성·
        꺾쇠 자동 링크로 쓰면 눌리는 링크라 그대로 견주므로 `alice` 에 `alice_` 를 덧붙인 링크는 새 주소로 거절된다(검증자 S 의 SP-15 — 글 속 맨주소 쪽은 고치지 않기로 했다)."""
        before = BASE + "참고 https://x.example/alice 입니다\n"
        for tail in ("_", chr(0x7E), "!", ",", ".", ";", "?", "*", ":"):
            for template in ("[t](https://x.example/alice{t})", '<a href="https://x.example/alice{t}">t</a>', "<https://x.example/alice{t}>"):
                add = template.format(t=tail)
                with self.subTest(add=add):
                    self.assertEqual(len(link_reasons(verify(before, before + add + "\n"))), 1)


class ReadingBoundariesTest(unittest.TestCase):
    def test_invisible_format_characters_inside_an_address_do_not_make_it_a_different_address(self):
        """주소 안의 폭 없는 공백·소프트 하이픈 같은 서식 글자는 브라우저가 무시하거나 주소를 깨뜨릴 뿐이다 — 지운 꼴로 읽어 같은 주소로 본다(검증자 S 의 SP-16: 안 지우는 변이가 살아남았다)."""
        zero_width, soft_hyphen = chr(0x200B), chr(0x00AD)
        self.assertEqual(checks.external_links("[x](ht" + zero_width + "tps://evil.example/a)"), {"https://evil.example/a"})
        self.assertEqual(checks.external_links("[x](https://ev" + soft_hyphen + "il.example/a)"), {"https://evil.example/a"})
        self.assertEqual(checks.external_links('<a href="//evil.example/a' + zero_width + '">x</a>'), {"//evil.example/a"})
        self.assertEqual(checks.external_links("[x][1]\n\n[1]: " + zero_width + "//evil.example/a"), {"//evil.example/a"})

    def test_a_name_that_only_ends_in_srcset_is_not_the_srcset_attribute(self):
        for text in ('<x data-srcset="//evil.example/a.png">y</x>', "<x my-srcset=//evil.example/a.png>y</x>", "<x xsrcset='//evil.example/a.png'>y</x>", '<x a:srcset="//evil.example/a.png">y</x>'):
            with self.subTest(text=text):
                self.assertEqual(checks.external_links(text), set())
        self.assertEqual(checks.external_links('<img SRCSET="/a.png 1x, //evil.example/b.png 2x">'), {"//evil.example/b.png"})

    def test_an_automatic_link_with_a_scheme_outside_the_prose_list_is_read_as_an_address(self):
        for scheme in ("gopher", "ssh", "telnet", "foo", "irc", "git"):
            with self.subTest(scheme=scheme):
                text = f"<{scheme}://evil.example/a>"
                self.assertEqual(checks.external_links(text), {f"{scheme}://evil.example/a"})
                self.assertTrue(blocked(text))


if __name__ == "__main__":
    unittest.main()
