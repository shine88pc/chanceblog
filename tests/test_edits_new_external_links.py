"""AI 수정이 원문에 없던 외부 링크를 몰래 넣는 길(결함 D-353).

옛 검사(`checks._hosts`)는 `http`·`https` 스킴 주소의 **호스트 집합**만 견줬다. 그래서 프로토콜 상대 주소(`//host`)·같은 호스트의 새 경로·`host:80@evil` 처럼 ':' 에서 호스트가 끊겨 읽히는 주소·
참조식 정의·srcset·탭이나 줄바꿈으로 쪼갠 스킴(브라우저는 주소 안의 탭·줄바꿈을 지운다)이 지나갔다. 이제 링크 대상(마크다운·HTML 속성·참조식 정의·자동 링크·글 속의 주소)을 모아 정규화한 주소를
견주고, AI 수정으로 **원문에 없던 외부 주소**가 생기면 거절한다. 원문에 이미 있던 주소(허용 목록)는 위치를 옮기거나 되풀이해도 괜찮고, 사이트 안 경로·`#앵커`·`mailto:`·`tel:` 은 외부 링크가 아니다.
소유자가 직접 쓴 교체(`ai_patch=False`)는 옛 그대로다.
"""
import json
import time
import unittest

import _bootstrap  # noqa: F401
from edits_helpers import ABOUT, issue, page_body
from pipeline.edits import checks
from test_edits_runner import RunnerBase

LIMITS = {"max_changed_files": 1, "max_changed_lines": 80, "max_file_chars": 80000}
BASE = "안녕하세요. 소개 문장입니다.\n문의는 [GitHub](https://github.com/owner/repo) 로 주세요. 사이트 [소개](/about/) 도 있습니다.\n"
LAYOUT = "layout | 섹션/레이아웃 변경 (해당 페이지 안에서만)"


def verify(before, after, **kw):
    return checks.verify_changes({"about.md": (before, after)}, ["about.md"], LIMITS, **kw)


def link_reasons(reasons):
    return [reason for reason in reasons if "외부 링크" in reason]


BLOCKED = {
    "새 호스트(옛 검사도 잡던 것)": "[x](https://evil.example/a)",
    "스킴·호스트 대문자": "[x](HTTPS://EVIL.example/a)",
    "프로토콜 상대 마크다운": "[x](//evil.example/a)",
    "프로토콜 상대 HTML": '<a href="//evil.example/a">x</a>',
    "프로토콜 상대 따옴표 없는 HTML": "<a href=//evil.example/a>x</a>",
    "프로토콜 상대 홑따옴표 HTML": "<a href='//evil.example/a'>x</a>",
    "슬래시 세 개": "[x](///evil.example/a)",
    "역슬래시 둘": "[x](https:" + "\\" * 2 + "evil.example/a)",
    "슬래시 하나": "[x](http:/evil.example/a)",
    "슬래시 없음": "[x](http:evil.example/a)",
    "같은 호스트의 새 경로": "[x](https://github.com/attacker/phish)",
    "같은 호스트의 바뀐 질의": "[GitHub](https://github.com/owner/repo?ref=x)",
    "같은 호스트의 끝 슬래시": "[GitHub](https://github.com/owner/repo/)",
    "포트로 호스트를 끊어 읽히게 한 userinfo": "[x](https://github.com:80@evil.example/a)",
    "userinfo": "[x](https://github.com@evil.example/a)",
    "ftp": "[x](ftp://evil.example/a)",
    "다른 스킴": "[x](slack://evil/a)",
    "참조식 정의": "[x][1]\n\n[1]: //evil.example/a",
    "참조식 정의(꺾쇠와 제목)": '[x][1]\n\n[1]: <//evil.example/a> "제목"',
    "참조식 정의(스킴)": "[x][1]\n\n[1]: https://evil.example/a",
    "srcset": '<img srcset="/a.png 1x, //evil.example/a.png 2x" src="/a.png">',
    "그림": "![x](//evil.example/a.png)",
    "꺾쇠 자동 링크": "<https://evil.example/a>",
    "글 속의 주소": "참고: https://evil.example/a 를 보세요",
    "글 속의 ftp 주소": "내려받기: ftp://evil.example/a 에서",
    "글 속의 슬래시 하나 주소": "참고: http:/evil.example/a 를 보세요",
    "탭으로 쪼갠 스킴(마크다운 링크)": "[x](ht&#9;tps://evil.example/a)",
    "줄바꿈으로 쪼갠 스킴(마크다운 링크)": "[x](ht&#10;tps://evil.example/a)",
    "탭으로 쪼갠 프로토콜 상대 주소(마크다운 링크)": "[x](/&#9;/evil.example/a)",
    "탭으로 쪼갠 스킴(따옴표 없는 속성)": "<a href=ht&#9;tps://evil.example/a>x</a>",
    "탭으로 쪼갠 스킴(참조식 정의)": "[x][1]\n\n[1]: ht&#9;tps://evil.example/a",
    "탭으로 쪼갠 스킴(문자 참조)": '<a href="ht&#9;tps://evil.example/a">x</a>',
    "탭으로 쪼갠 스킴(16진 문자 참조)": '<a href="ht&#x9;tps://evil.example/a">x</a>',
    "줄바꿈으로 쪼갠 스킴": '<a href="ht&#10;tps://evil.example/a">x</a>',
    "이름 있는 문자 참조": '<a href="ht&Tab;tps://evil.example/a">x</a>',
    "겹쳐 쓴 문자 참조": '<a href="ht&amp;#9;tps://evil.example/a">x</a>',
    "진짜 탭": '<a href="ht\ttps://evil.example/a">x</a>',
    "문자 참조로 쓴 스킴 글자": '<a href="&#104;ttps://evil.example/a">x</a>',
    "속성 이름 대문자와 공백": '<A HREF = " //evil.example/a ">x</A>',
}

ALLOWED = {
    "링크는 그대로 두고 글만 고침": BASE.replace("소개 문장", "소개 문구"),
    "링크 글자만 고침": BASE.replace("[GitHub]", "[깃허브]"),
    "링크 위치만 옮김": "안녕하세요. 소개 문장입니다.\n[GitHub](https://github.com/owner/repo) 문의는 여기로. 사이트 [소개](/about/) 도 있습니다.\n",
    "원문의 같은 주소를 한 번 더": BASE + "다시 [GitHub](https://github.com/owner/repo) 입니다.\n",
    "스킴·호스트 대소문자만 다른 같은 주소": BASE + "[GitHub](HTTPS://GitHub.com/owner/repo)\n",
    "링크를 지움": "안녕하세요. 소개 문장입니다.\n",
    "사이트 안 링크": BASE + "[연락처](/contact/) [위로](#top) [질의](?page=2) [상대](about.html) [상대2](../x/)\n",
    "메일과 전화": BASE + "[메일](mailto:someone@example.com) [전화](tel:+82101234567)\n",
    "글 속의 슬래시 둘": BASE + "경로 A//B 와 `// 주석` 은 링크가 아니다\n",
    "스킴 이름만 쓴 글": BASE + "http: 라고만 쓰고 주소는 없다. https: 도 마찬가지. 주소는 https:// 로 시작한다.\n",
    "시각·비율·윈도 경로": BASE + "회의는 10:30 에 시작, 비율 3:2, 경로 C:" + "\\" + "Users 는 링크가 아니다\n",
}


class NewExternalLinkTest(unittest.TestCase):
    def test_every_new_external_address_is_rejected_in_an_ai_patch(self):
        for name, payload in BLOCKED.items():
            with self.subTest(name=name):
                reasons = verify(BASE, BASE + payload + "\n", ai_patch=True)
                self.assertEqual(len(link_reasons(reasons)), 1, reasons)

    def test_the_reason_shows_the_address_in_a_code_span_and_never_the_surrounding_text(self):
        reasons = link_reasons(verify(BASE, BASE + "[x](//evil.example/a)\n", ai_patch=True))
        self.assertEqual(reasons, ["about.md: AI 수정은 새 외부 링크를 넣을 수 없습니다(`//evil.example/a`)."])
        reasons = link_reasons(verify(BASE, BASE + "[GitHub](https://github.com/attacker/phish)\n", ai_patch=True))
        self.assertEqual(reasons, ["about.md: AI 수정은 새 외부 링크를 넣을 수 없습니다(`https://github.com/attacker/phish`)."])

    def test_a_new_host_keeps_the_old_reason_text(self):
        self.assertEqual(link_reasons(verify(BASE, BASE + "[x](https://evil.example/a)\n", ai_patch=True)),
                         ["about.md: AI 수정은 새 외부 링크를 넣을 수 없습니다(`evil.example`)."])

    def test_changes_that_keep_the_existing_links_are_allowed(self):
        for name, after in ALLOWED.items():
            with self.subTest(name=name):
                self.assertEqual(verify(BASE, after, ai_patch=True), [])

    def test_an_edited_existing_address_counts_as_a_new_one(self):
        after = BASE.replace("https://github.com/owner/repo", "https://github.com/owner/other")
        self.assertEqual(len(link_reasons(verify(BASE, after, ai_patch=True))), 1)

    def test_a_link_hidden_inside_a_changed_line_next_to_an_existing_one_is_found(self):
        after = BASE.replace("[GitHub](https://github.com/owner/repo)", "[GitHub](https://github.com/owner/repo) [더](//evil.example/a)")
        self.assertEqual(len(link_reasons(verify(BASE, after, ai_patch=True))), 1)

    def test_the_owner_s_own_replacement_is_not_an_ai_patch_and_is_unchanged(self):
        for name, payload in BLOCKED.items():
            with self.subTest(name=name):
                self.assertEqual(link_reasons(verify(BASE, BASE + payload + "\n")), [])

    def test_a_page_that_already_has_many_links_is_not_blamed_for_them(self):
        links = "\n".join(f"[링크 {n}](//cdn{n}.example/a) [쪽 {n}](https://site{n}.example/p?x={n})" for n in range(30))
        before = "소개\n" + links + "\n"
        self.assertEqual(verify(before, before.replace("소개", "소개글"), ai_patch=True), [])


class ExternalLinksFunctionTest(unittest.TestCase):
    def test_addresses_are_normalised_with_lower_case_scheme_and_host_only(self):
        self.assertEqual(checks.external_links("[x](HTTPS://Evil.Example/Path?Q=1#Top)"), {"https://evil.example/Path?Q=1#Top"})
        self.assertEqual(checks.external_links("<a href=//Evil.Example/A>x</a>"), {"//evil.example/A"})
        self.assertEqual(checks.external_links("[x](http:Evil.example/a)"), {"http://evil.example/a"})
        self.assertEqual(checks.external_links('<a href = "  //evil.example/a  ">x</a>'), {"//evil.example/a"})
        self.assertEqual(checks.external_links("[x](https:" + "\\" * 2 + "Evil.example/a)"), {"https://evil.example/a"})        # 역슬래시는 슬래시로(브라우저가 그렇게 읽는다)
        self.assertEqual(checks.external_links("[x](" + "\\" * 2 + "evil.example/a)"), {"//evil.example/a"})
        self.assertEqual(checks.external_links("[x](ht&#9;tps://Evil.example/a) <a href=//e.example/&#10;b>y</a>"), {"https://evil.example/a", "//e.example/b"})

    def test_the_userinfo_stays_inside_the_authority_so_it_cannot_hide_the_target(self):
        self.assertEqual(checks.external_links("[x](https://github.com:80@Evil.example/a)"), {"https://github.com:80@evil.example/a"})

    def test_internal_addresses_and_contact_schemes_are_not_external(self):
        text = "[a](/x) [b](#y) [c](?z=1) [d](rel.html) [e](../up) [f](mailto:a@b.example) [g](tel:+8210) [h](javascript:void(0)) [i](data:text/plain;base64,AAAA) [j](VBScript:x)"
        self.assertEqual(checks.external_links(text), set())

    def test_every_place_a_link_can_be_written_is_read(self):
        text = ("[inline](//a.example/1) ![img](//b.example/2.png)\n\n[ref]: //c.example/3\n"
                '<a href="//d.example/4">x</a> <img src=\'//e.example/5.png\'> <img srcset="/x.png 1x, //f.example/6.png 2x"> <https://g.example/7> plain https://h.example/8 end')
        self.assertEqual(checks.external_links(text), {"//a.example/1", "//b.example/2.png", "//c.example/3", "//d.example/4", "//e.example/5.png", "//f.example/6.png",
                                                       "https://g.example/7", "https://h.example/8"})

    def test_the_same_address_written_twice_is_one_address(self):
        self.assertEqual(checks.external_links("[a](https://x.example/1) [b](HTTPS://X.example/1) https://x.example/1"), {"https://x.example/1"})

    def test_empty_and_plain_text(self):
        self.assertEqual(checks.external_links(""), set())
        self.assertEqual(checks.external_links("그냥 글입니다. 링크가 없습니다."), set())

    def test_a_long_unterminated_attribute_list_is_read_in_reasonable_time(self):
        text = 'href="x ' * 9000                                                                 # 닫는 따옴표가 없는 속성이 아주 많다(약 7만 자)
        started = time.monotonic()
        checks.external_links(text)
        self.assertLess(time.monotonic() - started, 20.0)                                         # 느린 PC·병렬 실행에서도 안 흔들리는 넉넉한 상한


class IssueEditFlowTest(RunnerBase):
    def go_patch(self, new_text):
        payload = {"patches": [{"old": "두 번째 문단입니다.", "new": new_text}]}
        calls = []

        def llm(*args):
            calls.append(args)
            return json.dumps(payload, ensure_ascii=False), "m"

        res = self.go(issue(page_body(edit=LAYOUT, after="둘째 문단 아래에 안내를 넣어 주세요"), assoc="OWNER"), llm=llm)
        return res, calls

    def test_a_patch_that_adds_a_protocol_relative_link_is_rejected_and_nothing_is_written(self):
        res, calls = self.go_patch("두 번째 문단입니다. [더 보기](//evil.example/x)")
        self.assertEqual(len(calls), 1)
        self.assertRejected(res, "외부 링크")
        self.assertEqual(self.read("about.md"), ABOUT)

    def test_a_patch_that_adds_a_new_path_on_an_existing_host_is_rejected(self):
        res, _calls = self.go_patch("두 번째 문단입니다. [더 보기](https://old.example.com/phish)")
        self.assertRejected(res, "외부 링크")
        self.assertEqual(self.read("about.md"), ABOUT)

    def test_a_patch_that_adds_a_tab_split_scheme_is_rejected(self):
        res, _calls = self.go_patch('두 번째 문단입니다. <a href="ht&#9;tps://evil.example/x">더 보기</a>')
        self.assertRejected(res, "외부 링크")

    def test_a_patch_that_reuses_a_link_the_page_already_has_is_accepted(self):
        res, _calls = self.go_patch("두 번째 문단입니다. 자세한 내용은 [소개 링크](https://old.example.com/a) 를 보세요.")
        self.assertEqual(res.status, "ok", res.reasons)
        self.assertIn("https://old.example.com/a", self.read("about.md"))

    def test_a_patch_that_adds_a_site_internal_link_is_accepted(self):
        res, _calls = self.go_patch("두 번째 문단입니다. [문의](/contact/) 도 보세요.")
        self.assertEqual(res.status, "ok", res.reasons)

    def test_the_comment_does_not_make_the_address_a_live_link(self):
        res, _calls = self.go_patch("두 번째 문단입니다. [더 보기](//evil.example/x)")
        self.assertIn("`//evil.example/x`", res.comment)
        for line in res.comment.splitlines():
            if "evil.example" in line:
                self.assertIn("`//evil.example/x`", line)


if __name__ == "__main__":
    unittest.main()
