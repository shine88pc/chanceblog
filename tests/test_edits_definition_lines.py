"""AI 수정의 새 외부 링크 검사(D-353)의 '참조식 정의 읽기' 다듬기(결함 D-393–D-396 — L6b 가 결함 D-369 에 열림으로 남긴 ⑧·⑨·①·② 를 닫는다).

⑧ 꺾쇠 없는 정의 줄의 같은 줄 글머리(`[1]: News: BBC 2020`·`[Update]: Line: 12`)가 새 외부 링크로 거절되던 오탐 면(L6b 의 R-1 이 만든 것). 지시서는 정의의 주소가 첫 토큰 하나이고 그 뒤 글은
   제목이 아니면 정의가 아니라 영문 글머리라고 본다(렌더러로 확인하지 못한 전제 — 잠정, D-393). 공백을 건너 읽는 규칙은 링크 대상·꺾쇠 정의, 주소 토큰(`스킴:`)이 줄 끝인 정의의 다음 줄 값, 그리고 꺾쇠 없는 정의의 같은 줄에서는 값이 **주소 모양일 때만** 남긴다
   (2차: 검증 S 의 L6c-R1, 총괄 결정 (B) — 렌더러가 정의 주소의 공백을 받는지 확인할 수 없어 M103 이 막던 지갑·딥링크는 풀지 않는다) — 막던 것은 계속 막는다.
⑨ 대상이 빈 `[a]:` 줄 뒤(빈 줄이 끼거나 바로 다음 줄)에 이어지는 정의 `[r]: //evil.example/a` 를 앞 정의가 대상으로 삼켜 통과하던 틈(시작점부터). 다른 정의의 머리는 대상이 아니다.
① 줄바꿈이 CR 하나뿐인 글에서 정의의 줄 머리가 숨던 틈(시작점부터). CR·CRLF 를 LF 로 통일해 읽는다.
② style `url('…')` 의 따옴표 안 앞 공백·탭이 읽기를 막던 틈(시작점부터) — 따옴표 안 글 전체를 읽는다.
R2(2차, D-397) 꺾쇠 정의에서 `<` 바로 뒤 공백·탭·줄바꿈 뒤의 프로토콜 상대 주소(`[r]: < //evil.example/a>`)가 통과하던 틈(시작점부터 — 검증 S 의 L6c-R2).
시험 안의 낱말 표는 코드의 목록을 import 하지 않는 독립 목록이다. 가짜 값만 쓴다.
"""
import random
import time
import unittest

import _bootstrap  # noqa: F401
from pipeline.edits import checks

NL, CR, TAB = chr(10), chr(13), chr(9)
LIMITS = {"max_changed_files": 1, "max_changed_lines": 80, "max_file_chars": 80000}
BASE = "안녕하세요. 소개 문장입니다." + NL + "문의는 [GitHub](https://github.com/owner/repo) 로 주세요." + NL


def verify(before, after):
    return checks.verify_changes({"about.md": (before, after)}, ["about.md"], LIMITS, ai_patch=True)


def link_reasons(reasons):
    return [reason for reason in reasons if "외부 링크" in reason]


def blocked(payload, before=BASE):
    return len(link_reasons(verify(before, before + payload + NL))) == 1


# 슬래시 없이 `스킴:값` 으로 쓰는 앱·결제·처리기 스킴 — 시험의 독립 목록. 코드의 `_APP_SCHEMES` 와 같은 낱말이어야 한다.
LISTED = ("bitcoin", "bitcoincash", "litecoin", "ethereum", "monero", "dogecoin", "dash", "zcash", "lightning", "nostr", "solana", "tron", "stellar",
          "tg", "whatsapp", "viber", "weixin", "wechat", "line", "signal", "sgnl", "threema", "zalo", "slack", "discord", "msteams", "zoommtg", "zoomus", "webex",
          "smsto", "mmsto", "mms", "imessage", "facetime-audio",
          "steam", "spotify", "market", "itms", "itms-apps", "itms-services", "intent", "maps", "geo", "vscode", "vscode-insiders", "obsidian", "notion",
          "ssh", "sftp", "git", "svn", "irc", "ircs", "telnet", "rdp", "vnc", "smb", "nfs", "afp", "ldap", "ldaps", "gopher", "news", "snews", "nntp", "tftp", "rtsp", "rtmp",
          "webcal", "webcals", "feed", "dict", "rsync",
          "search", "search-ms", "about", "chrome", "chrome-extension", "edge", "blob")
PREFIXED = ("ms-word", "ms-excel", "ms-powerpoint", "ms-msdt", "ms-settings", "ms-appinstaller", "ms-officecmd", "web+mastodon", "web+example")
ALL_APP_SCHEMES = LISTED + PREFIXED
OPEN_SCHEMES = ("http", "https", "ftp", "ftps", "ws", "wss", "skype", "sip", "sips", "xmpp", "magnet", "sms", "facetime", "callto", "view-source")

# 정의 줄 앞에 올 수 있는 표시(인용문·목록·들여쓰기)
PREFIXES = ("", "> ", "- ", "* ", "1. ", "   ", ">> - ")


# --- ⑧ 꺾쇠 없는 정의 줄의 영문 글머리 --------------------------------------------------------------------------------------------------------

class SameLineDefinitionTextTest(unittest.TestCase):
    def test_a_listed_word_before_prose_on_a_definition_line_is_text(self):
        """`[1]: News: BBC 2020`·`[Update]: Line: 12` — 값이 평범한 낱말·짧은 숫자인 같은 줄 정의는 영문 글머리로 본다(L6b 의 R-1 이 만든 오탐 면 닫기; 정의의 주소가 첫 토큰 하나라는 전제는 렌더러 확인 전 잠정, D-393)."""
        for scheme in ALL_APP_SCHEMES:
            word = scheme.capitalize()
            for prefix in PREFIXES:
                for rest in ("12", "BBC 2020", "Some note", "see below: this"):
                    text = f"{prefix}[1]: {word}: {rest}"
                    with self.subTest(text=text):
                        self.assertEqual(checks.external_links(text), set())

    def test_a_lead_in_line_after_an_empty_definition_is_text(self):
        """대상이 빈 정의 `[a]:` 바로 뒤(빈 줄이 끼어도)에 영문 글머리 줄이 오면 그 줄의 첫 토큰이 앞 정의의 대상이 되는데, 첫 토큰 뒤 글은 제목이 아니면 정의가 아니라 글로 본다(같은 ⑧ 부류 — 렌더러 확인 전 잠정)."""
        for scheme in ALL_APP_SCHEMES:
            word = scheme.capitalize()
            for gap in (NL, NL * 2):
                text = f"[a]:{gap}{word}: BBC 2020"
                with self.subTest(text=text):
                    self.assertEqual(checks.external_links(text), set())

    def test_the_normal_edits_that_were_rejected_pass_the_whole_check(self):
        """검증자 S 의 D2-R1 표본 `[1]: News: BBC 2020`·`[Update]: Line: 12` 를 원래 모양 그대로(L6b 의 시험은 `Fixed: yes` 로 바꿔 두어 이 면이 가려져 있었다)."""
        for line in ("[Update]: Line: 12", "[1]: News: BBC 2020", "[Note]: Search: some term", "[Source]: About: me", "[1]: Market: KOSPI 지수", "[Update]: Signal: weak", "[1]: Feed: weekly"):
            with self.subTest(line=line):
                self.assertEqual(verify(BASE, BASE + line + NL), [])
                self.assertEqual(verify(BASE, BASE + "> " + line + NL), [])

    def test_an_address_shaped_value_after_the_first_token_of_an_unangled_definition_is_still_read(self):
        """(B) 총괄 결정: 꺾쇠 없는 정의의 같은 줄 공백 뒤 값이 주소 모양(`resolve?x=1`)이면 M103 처럼 읽는다 — 정의의 주소가 첫 토큰이라 이 꼴이 링크 정의인지 렌더러로 확인하지 못했고(소스 기억이 갈린다) 근거 없이 막던 것을 풀지 않는다."""
        for scheme in ALL_APP_SCHEMES:
            for text in (f"[r]: {scheme}: resolve?x=1", f"[r]: {scheme}:" + TAB + "resolve?x=1", f"> [r]: {scheme}: resolve?x=1", f'[r]: {scheme}: resolve?x=1 "제목"', f"[r]: {scheme}:   resolve?x=1",
                         f"[r]:{NL}{scheme}: resolve?x=1", f"- [r]: {scheme}: resolve?x=1", f"[a]:{NL}{NL}{scheme}: resolve?x=1"):
                with self.subTest(text=text):
                    self.assertEqual(checks.external_links(text), {f"{scheme}://resolve?x=1"})

    def test_a_prose_value_after_the_first_token_of_an_unangled_definition_is_text(self):
        """평범한 낱말·짧은 숫자·날짜·버전은 영문 글머리다(주소 모양이 아니다). 값이 평범한 낱말인 꼴(`tg: resolve`·`slack: open`)은 처리기에 넘길 내용이 거의 없어 글로 두는 것이 남는 틈이다(D-393)."""
        for scheme in ALL_APP_SCHEMES:
            for value in PROSE_VALUES:
                for text in (f"[r]: {scheme}: {value}", f"> [r]: {scheme}: {value} 2020", f"[r]:{NL}{scheme}: {value}"):
                    with self.subTest(text=text):
                        self.assertEqual(checks.external_links(text), set())

    def test_any_blank_character_after_the_colon_is_read_like_a_space_in_an_unangled_definition(self):
        """M103 은 콜론 뒤 구분을 `\\s+`(VT·FF·NEL·NBSP·유니코드 공백·문자 참조로 쓴 공백 포함)로 읽었다 — 같은 줄 읽기도 그만큼 넓다(검증자 S 의 p24: 좁히면 M103 이 막던 것이 풀린다). 값이 주소 모양이면 읽고 낱말이면 글이다."""
        for scheme in ("tg", "bitcoin", "ms-msdt", "news", "web+example"):
            for blank in UNICODE_BLANKS:
                for text in (f"[r]: {scheme}:{blank}resolve?x=1", f"> [r]: {scheme}:{blank}{blank}resolve?x=1", f'[r]: {scheme}:{blank}resolve?x=1 "제목"', f"[r]:{NL}{scheme}:{blank}resolve?x=1"):
                    with self.subTest(text=text):
                        self.assertEqual(checks.external_links(text), {f"{scheme}://resolve?x=1"})
                with self.subTest(scheme=scheme, blank=blank, value="낱말"):
                    self.assertEqual(checks.external_links(f"[r]: {scheme}:{blank}12"), set())

    def test_any_blank_character_before_a_line_end_after_the_scheme_colon_still_lets_the_next_line_be_read(self):
        """주소 토큰이 줄 끝인 정의의 다음 줄 값 — 줄 끝 앞의 구분이 NBSP·유니코드 공백이어도 읽는다(M103 의 `\\s+` 와 같다)."""
        for scheme in ("tg", "bitcoin", "ms-msdt", "news"):
            for blank in UNICODE_BLANKS:
                text = f"[r]: {scheme}:{blank}{NL}resolve?x=1"
                with self.subTest(text=text):
                    self.assertEqual(checks.external_links(text), {f"{scheme}://resolve?x=1"})


    def test_the_boundary_of_the_address_shape(self):
        for value in ADDRESS_SHAPED_VALUES:
            with self.subTest(value=value, expected="읽힘"):
                self.assertNotEqual(checks.external_links(f"[r]: tg: {value}"), set())
        for value in PROSE_VALUES:
            with self.subTest(value=value, expected="글"):
                self.assertEqual(checks.external_links(f"[r]: tg: {value}"), set())

    def test_the_verifier_examples_for_option_b(self):
        """검증자 S 의 (B) 실험 표본: 주소 모양 9개는 거절, 영문 글머리 12개는 통과, 평범한 낱말 값 4개는 남는 틈으로 통과."""
        must_block = ("[r]: tg: resolve?domain=evil", "[r]: bitcoin: 1BoatSLRHtKNngkdXEeobR76b53LETtpyT", "[r]: ssh: user@host", "[r]: ms-msdt: /id PCWDiagnostic", "> [r]: steam: run/1",
                      "[r]: intent: #Intent;scheme=evil;end", "[r]: ethereum: 0x32Be343B94f860124dC4fEe278FDCBD38C102D88", '[r]: whatsapp: send?phone=1 "t"', "[r]: search-ms: query=x")
        must_pass = ("[Update]: Line: 12", "[1]: News: BBC 2020", "[2]: Market: KOSPI index", "[3]: Signal: strong", "[4]: About: me", "[5]: Search: result", "[1]: Maps: Google", "[6]: Git: repo",
                     "[7]: Feed: RSS", "[8]: Edge: browser", "[9]: Chrome: 120.0.6099.71", "[10]: News: 2026-11-22")
        known_gap = ("[r]: tg: resolve", "[r]: slack: open", "[r]: discord: invite", "[r]: ms-settings: network")
        for sample in must_block:
            with self.subTest(sample=sample):
                self.assertTrue(blocked(sample))
        for sample in must_pass + known_gap:
            with self.subTest(sample=sample):
                self.assertEqual(verify(BASE, BASE + sample + NL), [])


# 콜론 뒤에 올 수 있는 공백 글자들: VT·FF·FS·NEL·NBSP·EN/EM SPACE·표의 공백·줄·문단 구분·얇은 공백, 그리고 문자 참조로 쓴 공백(읽기 전에 풀린다 — 탭·줄바꿈 문자 참조는 읽기 전에 지워져 값이 콜론에 붙으므로 여기 없다)
UNICODE_BLANKS = (chr(11), chr(12), chr(0x1c), chr(0x85), chr(0xa0), chr(0x2002), chr(0x2003), chr(0x3000), chr(0x2028), chr(0x2029), chr(0x2009), "&nbsp;", "&#160;", "&#32;")



# 같은 줄 공백 뒤 값이 글인 것(주소 모양이 아님) — 낱말·짧은 숫자·날짜·버전·끝 문장부호·한글. `resolve`·`open`·`network` 는 남는 틈(평범한 낱말)을 못박는다.
PROSE_VALUES = ("12", "2020", "BBC", "Some", "strong", "yes", "resolve", "open", "network", "index", "2026-11-22", "120.0.6099.71", "1.5", "weekly", "BBC.", "me,", "(see", "연합뉴스", "KOSPI",
                "abcdefghijklmno", "123456", "1.2.3")
# 주소 모양: `/?=@%&#:+`·역슬래시, 글자로 시작하는 점이 든 호스트 꼴, 숫자 7개 이상, IPv4 꼴(점 셋·숫자 1–3자리 넷), ASCII 영숫자 16개 이상(15·6 은 글, 16·7 부터 주소 모양)
ADDRESS_SHAPED_VALUES = ("resolve?x=1", "evil.example/a", "evil.example", "alt.x", "user@host", "a%20b", "a&b", "a#b", "a+b", "a:b", "x=1", "/id", "//evil.example/a", "run/1", "1234567",
                         "0x32Be343B94f860124dC4fEe278FDCBD38C102D88", "1BoatSLRHtKNngkdXEeobR76b53LETtpyT", "abcdefghijklmnop", "a" + chr(92) + "b", "U.S", "10.0.0.1", "192.168.0.10")


# 막던 것은 계속 막는 꼴 — `{s}` 는 스킴, 값은 `resolve?x=1`
STILL_READ_SHAPES = (
    ("링크 대상의 콜론 뒤 공백", "[x]({s}: resolve?x=1)"),
    ("꺾쇠 링크 대상", "[x](<{s}: resolve?x=1>)"),
    ("꺾쇠 정의", "[r]: <{s}: resolve?x=1>"),
    ("꺾쇠 정의의 콜론 뒤 탭·여러 공백", "[r]: <{s}:" + TAB + "  resolve?x=1>"),
    ("꺾쇠 정의 안의 줄바꿈", "[r]: <{s}:" + NL + "resolve?x=1>"),
    ("꺾쇠 없는 정의의 같은 줄 공백(주소 모양 값)", "[r]: {s}: resolve?x=1"),
    ("같은 줄 탭(주소 모양 값)", "[r]: {s}:" + TAB + "resolve?x=1"),
    ("같은 줄 여러 공백(주소 모양 값)", "[r]: {s}:   resolve?x=1"),
    ("제목이 붙은 같은 줄 정의(주소 모양 값)", '[r]: {s}: resolve?x=1 "제목"'),
    ("대상이 다음 줄인 같은 줄 공백 정의(주소 모양 값)", "[r]:" + NL + "{s}: resolve?x=1"),
    ("콜론에 붙은 값의 정의", "[r]: {s}:resolve?x=1"),
    ("콜론에 붙은 값의 꺾쇠 정의", "[r]: <{s}:resolve?x=1>"),
    ("주소 토큰이 줄 끝인 정의", "[r]: {s}:" + NL + "resolve?x=1"),
    ("주소 토큰 뒤에 공백이 있고 줄 끝인 정의", "[r]: {s}:  " + NL + "resolve?x=1"),
    ("대상이 다음 줄인 정의", "[r]:" + NL + "{s}:resolve?x=1"),
)


class StillBlockedTest(unittest.TestCase):
    def test_every_shape_that_was_blocked_before_stays_blocked(self):
        for scheme in ALL_APP_SCHEMES:
            for prefix in ("", "> ", "- "):
                for name, template in STILL_READ_SHAPES:
                    with self.subTest(scheme=scheme, prefix=prefix, shape=name):
                        text = prefix + template.format(s=scheme)
                        self.assertEqual(checks.external_links(text), {f"{scheme}://resolve?x=1"})

    def test_the_reported_blocked_examples_are_still_rejected_by_the_whole_check(self):
        for payload in ("[x](tg: resolve?domain=evil)", "[x][r]" + NL + NL + "[r]: <tg: resolve?domain=evil>", "[x][r]" + NL + NL + "[r]: tg:resolve?domain=evil",
                        "[x][r]" + NL + NL + "[r]: bitcoin:1BoatSLRHtKNngkdXEeobR76b53LETtpyT", "[x][r]" + NL + NL + "[r]: tg:" + NL + "resolve?domain=evil"):
            with self.subTest(payload=payload):
                self.assertTrue(blocked(payload))

    def test_an_open_scheme_followed_by_text_on_a_definition_line_is_still_a_new_link(self):
        """열린 스킴(http·https·ftp·skype·magnet …)은 콜론만으로도 `스킴://` 키가 생겨 같은 줄 공백 뒤 글이 있어도 새 링크로 거절된다 — 영문 글머리로 쓰이는 낱말이 아니다."""
        for scheme in OPEN_SCHEMES:
            for text in (f"[r]: {scheme}: evil.example/a", f"[r]: {scheme}: some text", f"> [r]: {scheme}: x"):
                with self.subTest(text=text):
                    self.assertTrue(blocked(text))

    def test_the_head_of_the_next_definition_is_never_taken_as_the_value_after_a_line_end_scheme(self):
        for tail in ("[x]: //evil.example/a", "> [x]: //evil.example/a", "- [x]: //evil.example/a", "   [x]: //evil.example/a"):
            for scheme in ("tg", "news", "ms-word"):
                with self.subTest(scheme=scheme, tail=tail):
                    self.assertEqual(checks.external_links(f"[r]: {scheme}:" + NL + tail), {"//evil.example/a"})


# --- R2 꺾쇠 정의에서 `<` 바로 뒤의 공백·탭 ----------------------------------------------------------------------------------------------------

class AngleBlankTest(unittest.TestCase):
    def test_a_blank_after_the_opening_angle_does_not_hide_a_protocol_relative_address(self):
        """꺾쇠 정의의 주소는 `<` 와 `>` 사이 전부라 ` //evil.example/a`(앞 공백)가 되고 브라우저는 앞 공백을 지워 프로토콜 상대 외부 링크로 읽는다(검증자 S 의 L6c-R2 — 시작점부터 있던 틈)."""
        for label in ("r", "1", "a b", "^", "^a b", "^1"):
            for prefix in PREFIXES:
                for blank in (" ", TAB, "   ", " " + TAB + " ", NL):
                    text = f"{prefix}[{label}]: <{blank}//evil.example/a>"
                    with self.subTest(text=text):
                        self.assertEqual(checks.external_links(text), {"//evil.example/a"})

    def test_the_controls_next_to_the_angle_blank_are_unchanged(self):
        self.assertEqual(checks.external_links("[r]: <//evil.example/a>"), {"//evil.example/a"})
        for text in ("[1]: < /about/>", "[1]: <>", "[1]: < >", "[1]: News: BBC 2020", "[Update]: Line: 12", "[1]: <" + NL + "/about/>", "[^1]: < /about/>"):
            with self.subTest(text=text):
                self.assertEqual(checks.external_links(text), set())

    def test_an_empty_angle_does_not_hide_the_definition_after_it(self):
        for text in ("[a]: <" + NL + "[r]: //evil.example/a", "[a]: <" + NL + NL + "> [r]: //evil.example/a", "[a]: < " + NL + "- [r]: //evil.example/a", "[a]: <" + " " * 200 + NL + "[r]: //evil.example/a"):
            with self.subTest(text=text):
                self.assertEqual(checks.external_links(text), {"//evil.example/a"})

    def test_the_whole_check_rejects_a_blank_after_the_angle(self):
        for payload in ("[x][r]" + NL + NL + "[r]: < //evil.example/a>", "[x][r]" + NL + NL + "[r]: <" + TAB + "//evil.example/a>", "> [r]: < //evil.example/a>", "[^a b]: < //evil.example/a>"):
            with self.subTest(payload=payload):
                self.assertTrue(blocked(payload))


# --- ⑨ 빈 정의가 뒤따르는 정의를 삼키던 틈 ---------------------------------------------------------------------------------------------------

NEXT_DEFINITIONS = (
    ("//evil.example/a", {"//evil.example/a"}),
    ("tg://evil.example/a", {"tg://evil.example/a"}),
    ("tg:resolve?x=1", {"tg://resolve?x=1"}),
    ("<tg: resolve?x=1>", {"tg://resolve?x=1"}),
    ("https://evil.example/a", {"https://evil.example/a"}),
)


class EmptyDefinitionTest(unittest.TestCase):
    def test_an_empty_definition_does_not_hide_the_definition_after_it(self):
        for label in ("a", "1", "x y", "^", "a-b"):
            for gap in (NL, NL * 2, NL * 3, NL + "  ", NL + TAB, "   " + NL):
                for prefix in PREFIXES:
                    for body, keys in NEXT_DEFINITIONS:
                        text = f"[{label}]:{gap}{prefix}[r]: {body}"
                        with self.subTest(text=text):
                            self.assertEqual(checks.external_links(text), keys)

    def test_an_empty_footnote_definition_does_not_hide_the_footnote_after_it(self):
        for gap in (NL, NL * 2):
            for prefix in PREFIXES:
                for body in ("//evil.example/a", "tg://evil.example/a"):
                    with self.subTest(gap=gap, prefix=prefix, body=body):
                        self.assertEqual(checks.external_links(f"[^1]:{gap}{prefix}[^2]: {body}"), {body})
                with self.subTest(gap=gap, prefix=prefix, body="app value"):
                    self.assertEqual(checks.external_links(f"[^1]:{gap}{prefix}[^2]: Market:KOSPI"), set())      # 각주 본문의 앱 스킴은 글이다

    def test_the_whole_check_rejects_a_new_definition_that_follows_an_empty_one(self):
        for payload in ("[a]:" + NL + NL + "[r]: //evil.example/a", "[a]:" + NL + "[r]: //evil.example/a", "[a]:" + NL + "- [r]: tg://x", "[a]:" + NL + "> [r]: tg:resolve?x=1"):
            with self.subTest(payload=payload):
                self.assertTrue(blocked(payload))

    def test_a_target_on_the_next_line_or_after_blank_lines_is_still_read_as_before(self):
        """실패 닫힘: 줄바꿈 개수는 제한하지 않는다 — 대상이 다음 줄이거나 빈 줄 뒤여도 옛대로 읽어 시작점보다 덜 읽지 않는다."""
        for text in ("[a]:" + NL + "//evil.example/a", "[a]:" + NL * 2 + "//evil.example/a", "[a]:" + NL * 3 + "//evil.example/a", "[a]:" + NL + "    //evil.example/a", "[a]:" + " " * 50 + NL + "//evil.example/a"):
            with self.subTest(text=text):
                self.assertEqual(checks.external_links(text), {"//evil.example/a"})

    def test_an_ordinary_definition_and_its_title_are_read_as_before(self):
        self.assertEqual(checks.external_links("[r]: //evil.example/a " + chr(34) + "제목" + chr(34)), {"//evil.example/a"})
        self.assertEqual(checks.external_links("[r]: <//evil.example/a>"), {"//evil.example/a"})
        self.assertEqual(checks.external_links("[a]: /about/" + NL + "[b]: //evil.example/b"), {"//evil.example/b"})
        self.assertEqual(checks.external_links("[r]: [x]: //evil.example/a"), set())      # 같은 줄에 정의 머리가 둘 — 앞 정의의 대상은 `[x]:` 뿐이라 링크가 아니다(옛 판도 같다)


# --- ① CR 하나뿐인 줄바꿈 ---------------------------------------------------------------------------------------------------------------------

LINE_END_SHAPES = (
    ("[x][r]{n}{n}[r]: //evil.example/a{n}", {"//evil.example/a"}),
    ("{n}> [r]: //evil.example/a{n}", {"//evil.example/a"}),
    ("{n}- [r]: tg://evil.example/a{n}", {"tg://evil.example/a"}),
    ("[x][^]{n}{n}[^]: //evil.example/a{n}", {"//evil.example/a"}),
    ("[x][r]{n}{n}[r]: <tg: resolve?x=1>{n}", {"tg://resolve?x=1"}),
    ("[x][r]{n}{n}[r]: tg:{n}resolve?x=1{n}", {"tg://resolve?x=1"}),
    ("[a]:{n}{n}[r]: //evil.example/a{n}", {"//evil.example/a"}),
    ("text[^1]{n}{n}[^1]: note{n}[r]: //evil.example/a{n}", {"//evil.example/a"}),
    ("{n}   [r]: ftp://evil.example/a{n}", {"ftp://evil.example/a"}),
    ("[^1]: //evil.example/a{n}", {"//evil.example/a"}),
)
FRAGMENTS = (
    "[a]:" + NL, "[r]: //evil.example/a" + NL, "> [r]: tg:resolve?x=1" + NL, "- [r]: <tg: resolve?x=1>" + NL, "[1]: News: BBC 2020" + NL, "[^1]: Market:KOSPI" + NL,
    "[^2]: //evil.example/b" + NL, "문장입니다." + NL, NL, "[x](tg: resolve?x=1)" + NL, "<a href=" + chr(34) + "//evil.example/c" + chr(34) + ">x</a>" + NL,
    "[r]: tg:" + NL, "resolve?x=1" + NL, "   [q]: ftp://evil.example/d" + NL, "1. [z]: bitcoin:abc" + NL, "[w]:" + NL + NL,
)


class LineEndTest(unittest.TestCase):
    def test_a_definition_is_read_whichever_way_the_lines_are_ended(self):
        for shape, keys in LINE_END_SHAPES:
            for name, end in (("LF", NL), ("CRLF", CR + NL), ("CR", CR)):
                with self.subTest(shape=shape, line_end=name):
                    self.assertEqual(checks.external_links(shape.format(n=end)), keys)

    def test_a_new_definition_written_with_cr_line_ends_is_rejected_by_the_whole_check(self):
        for payload in (CR + "[x][r]" + CR + CR + "[r]: //evil.example/a" + CR, CR + "[r]: tg://evil.example/a" + CR, CR + "> [r]: //evil.example/a" + CR, CR + "[a]:" + CR + CR + "[r]: //evil.example/a" + CR):
            with self.subTest(payload=payload):
                self.assertEqual(len(link_reasons(verify(BASE, BASE + payload))), 1)

    def test_a_page_whose_lines_end_with_cr_keeps_its_own_links(self):
        before = BASE.replace(NL, CR) + CR + "[x][r]" + CR + CR + "[r]: //owner.example/a" + CR
        self.assertEqual(verify(before, before.replace("소개", "안내")), [])
        self.assertEqual(len(link_reasons(verify(before, before + "[r2]: //evil.example/a" + CR))), 1)

    def test_the_reading_does_not_depend_on_how_the_lines_are_ended(self):
        rng = random.Random(20261123)
        for _ in range(400):
            text = "".join(rng.choice(FRAGMENTS) for _ in range(rng.randint(1, 8)))
            reference = checks.external_links(text)
            with self.subTest(text=text):
                self.assertEqual(checks.external_links(text.replace(NL, CR)), reference)
                self.assertEqual(checks.external_links(text.replace(NL, CR + NL)), reference)


# --- ② url('…') 의 따옴표 안 글 전체 ----------------------------------------------------------------------------------------------------------

def in_style(value):
    """따옴표로 묶은 style 속성 안에 값을 넣는다(url 읽기는 속성 밖에서도 같지만 실제 모양에 가깝게)."""
    return "<div style=" + chr(34) + "background:" + value + chr(34) + ">x</div>"


class QuotedUrlTest(unittest.TestCase):
    def test_a_quoted_url_is_read_whole_even_with_blank_characters_inside(self):
        for name, value, key in (
            ("앞 공백", "url(' //evil.example/p.png')", "//evil.example/p.png"),
            ("스킴 안 탭", "url('ht" + TAB + "tps://evil.example/p.png')", "https://evil.example/p.png"),
            ("스킴 안 줄바꿈", "url('ht" + NL + "tps://evil.example/p.png')", "https://evil.example/p.png"),
            ("괄호 안 공백", "url(  ' //evil.example/p.png'  )", "//evil.example/p.png"),
            ("앱 스킴", "url(' bitcoin:abc')", "bitcoin://abc"),
        ):
            with self.subTest(name=name):
                self.assertEqual(checks.external_links(in_style(value)), {key})
        self.assertEqual(checks.external_links("<div style=" + chr(39) + "background:url(" + chr(34) + " //evil.example/p.png" + chr(34) + ")" + chr(39) + ">x</div>"), {"//evil.example/p.png"})

    def test_the_old_unquoted_and_unterminated_readings_are_kept(self):
        for value in ("url(//evil.example/p.png)", "url( //evil.example/p.png )", "url('//evil.example/p.png)", "url(" + chr(34) + "//evil.example/p.png)"):
            with self.subTest(value=value):
                self.assertEqual(checks.external_links("background:" + value), {"//evil.example/p.png"})

    def test_ordinary_style_urls_are_not_links(self):
        for value in ("url('/assets/a.png')", "url(" + chr(34) + "a b.png" + chr(34) + ")", "url('data:image/png;base64,AAAA')", "url(a.png)", "url(' /assets/a.png')"):
            with self.subTest(value=value):
                self.assertEqual(checks.external_links("background:" + value), set())

    def test_a_new_quoted_url_with_a_blank_in_front_is_rejected_by_the_whole_check(self):
        self.assertTrue(blocked(in_style("url(' //evil.example/p.png')")))
        self.assertTrue(blocked(in_style("url('ht" + TAB + "tps://evil.example/p.png')")))


# --- 읽는 시간(악성 입력에서 크기 두 배에 시간 세 배 미만) -----------------------------------------------------------------------------------

def best_cpu_time(text, repeat=3):
    """세 번 중 가장 짧은 CPU 시간(벽시계가 아니다 — 다른 프로세스가 CPU 를 나눠 써서 느려져도 값이 안 흔들린다)."""
    best = None
    for _ in range(repeat):
        started = time.process_time()
        checks.external_links(text)
        spent = time.process_time() - started
        best = spent if best is None else min(best, spent)
    return best


TIMING_SHAPES = {
    "반복 `[a]:` 줄": lambda n: ("[a]:" + NL) * n,
    "빈 정의 뒤 빈 줄 반복": lambda n: "[a]:" + NL * n,
    "`[a]:` 뒤 반복 공백": lambda n: "[a]:" + " " * n,
    "CR 만으로 나눈 반복 `[a]:`": lambda n: ("[a]:" + CR) * n,
    "CR 만으로 나눈 정의 줄": lambda n: ("[a]: x" + CR) * n,
    "줄 끝 스킴 정의 반복": lambda n: ("[a]: tg:" + NL) * n,
    "꺾쇠 정의 뒤 반복 공백": lambda n: "[a]: <" + " " * n,
    "정의 머리가 대상 자리에 반복": lambda n: ("[a]: [b]:" + NL) * n,
    "각주 정의 반복": lambda n: ("[^1]:" + NL) * n,
    "표시 글자가 길게 이어진 다음 줄": lambda n: "[a]:" + NL + "- " * n + "[r]: x",
    "반복 `url('`": lambda n: "url('" * n,
    "꺾쇠 뒤 공백 다음에 정의 머리": lambda n: "[a]: <" + " " * n + "[b]:",
    "반복 `[a]: < `": lambda n: "[a]: < " * n,
    "같은 줄 공백 값 정의 반복": lambda n: ("[a]: tg: x" + NL) * n,
    "아주 긴 값": lambda n: "[a]: tg: " + "x" * n,
    "점과 하이픈이 섞인 긴 값": lambda n: "[a]: tg: " + "a.b-" * n,
    "반복 `[`": lambda n: "[" * n,
    "반복 `(`": lambda n: "(" * n,
    "반복 `](`": lambda n: "](" * n,
    "닫는 괄호 없는 image-set 반복": lambda n: "image-set(" * n,
}


class ReadingTimeTest(unittest.TestCase):
    def test_reading_time_grows_in_proportion_to_the_text_for_every_malicious_shape(self):
        for name, make in TIMING_SHAPES.items():
            small, big = best_cpu_time(make(8000)), best_cpu_time(make(16000))
            with self.subTest(shape=name, small=round(small, 3), big=round(big, 3)):
                self.assertLess(big, 3 * small + 0.5)


class LongValueTimeTest(unittest.TestCase):
    def test_a_very_long_value_after_the_scheme_is_read_in_linear_time(self):
        """같은 줄 정의의 값이 아주 긴 글자 덩어리(점이 없거나 점 뒤에 영숫자가 안 오는 꼴)여도 주소 모양 판정이 선형이다 — 호스트 꼴 정규식이 글자마다 덩어리 끝까지 훑어 제곱 시간이던 것(2차 반영에서 찾음).
        여유를 0.3초로 줄이고 크기를 4만→8만으로 키워 제곱 시간이면 확실히 빨갛다(8천→1만 6천 번 되풀이 시험의 여유 0.5초에는 가려졌다)."""
        for name, make in (("긴 낱말", lambda n: "[a]: tg: " + "x" * n), ("긴 낱말 뒤 점과 하이픈", lambda n: "[a]: tg: " + "x" * n + ".-"), ("숫자와 하이픈", lambda n: "[a]: tg: " + "1-" * n),
                           ("낱말 사이 밑줄", lambda n: "[a]: tg: " + "a_" * n), ("점이 든 긴 낱말", lambda n: "[a]: tg: " + "x" * n + ".y")):
            small, big = best_cpu_time(make(40000), repeat=2), best_cpu_time(make(80000), repeat=2)
            with self.subTest(shape=name, small=round(small, 3), big=round(big, 3)):
                self.assertLess(big, 3 * small + 0.3)


class ReviewGapsTest(unittest.TestCase):
    """2차 검증(안전 S2·시험 Q)이 짚은 시험 틈: 같은 줄 정의 읽기의 스킴 대소문자 접기·`?` 하나뿐인 값·한글 긴 낱말, 그리고 결함 표 D-393 '남은 것' 이 열림으로 적은 글 통과 꼴을 지금 동작 그대로 못박는다."""

    def test_the_scheme_is_matched_without_regard_to_case_in_an_unangled_definition_on_one_line(self):
        for scheme in ("TG", "Tg", "BITCOIN", "Ms-Msdt", "WEB+Example"):
            text = f"[r]: {scheme}: resolve?domain=evil"
            with self.subTest(text=text):
                self.assertEqual(checks.external_links(text), {f"{scheme.lower()}://resolve?domain=evil"})
                self.assertTrue(blocked(text))

    def test_a_value_with_only_a_question_mark_is_address_shaped_and_a_long_hangul_word_is_text(self):
        self.assertEqual(checks.external_links("[r]: tg: ?"), {"tg://?"})
        hangul_word = "".join(chr(code) for code in range(0xAC00, 0xAC00 + 20))
        self.assertEqual(checks.external_links(f"[r]: tg: {hangul_word}"), set())

    def test_the_values_the_defect_table_lists_as_still_passing_as_text_are_pinned_as_they_are(self):
        """D-393 '남은 것' 이 열림으로 적은 꼴(첫 낱말이 평범한 뒤 주소·단일 라벨 호스트·숫자 약식과 16진 호스트·첫 라벨이 숫자뿐인 호스트·비 ASCII 호스트)은 지금 글로 통과한다.
        이 시험이 그 동작을 못박아 문서와 코드가 어긋나지 않게 한다 — 이 틈을 닫을 때는 이 시험과 D-393 을 함께 바꾼다."""
        full_stop = chr(0xFF0E)
        cyrillic = "".join(chr(code) for code in (0x43F, 0x440, 0x438, 0x43C, 0x435, 0x440)) + "." + "".join(chr(code) for code in (0x440, 0x444))
        values = ("go resolve?domain=evil", "localhost", "fileserver", "host-1", "127.1", "10.1", "192.168.1", "0x7f000001", "1.2.3.4.5", "123.example", "1.example", "12-34.example",
                  f"evil{full_stop}example", cyrillic)
        for value in values:
            for scheme in ("tg", "ssh", "irc"):
                text = f"[r]: {scheme}: {value}"
                with self.subTest(text=text):
                    self.assertEqual(checks.external_links(text), set())



if __name__ == "__main__":
    unittest.main()
