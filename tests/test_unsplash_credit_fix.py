"""공용 모듈(pipeline/unsplash_credit.py)의 시험 공백 메우기 — 독립 검증(U3)이 변이로 찾은 '현재 코드는 맞는데 시험이 안 지키는 곳' 가운데 이 모듈의 것과, 키가 가는 주소(`download_location`)의 모양 표.

기존 tests/test_unsplash_credit.py 는 그대로 두고, 그 시험이 지키지 못한 곳만 더한다. 순수 함수라 네트워크도 파일도 쓰지 않는다.

구성
  1) ixid 허용 문자: 대소문자를 무시하면 A-Za-z 와 같아지는 글자(켈빈 기호 등)는 받지 않는다(M006) · 빈 ixid 가 다른 ixid 곁에 있으면 '둘 이상'(M008).
  2) 주소의 나쁜 글자: 공백류·제어 문자·따옴표·꺾쇠·백틱·역슬래시가 질의·조각에 있으면 세 검사(사진·프로필·사용 알림 주소)가 모두 거절한다(M019·M020).
  3) 고정 목록 조회 번호의 자릿수 경계(M025).
  4) CRLF 로 줄이 끝나는 글의 출처 줄 검사(M072).
  5) 사용 알림 주소의 모양 표(키가 가는 주소 — 독립 검증 ②).
"""
import unittest
from urllib.parse import quote

import _bootstrap  # noqa: F401
from pipeline import unsplash_credit as uc

ESC = chr(92)                                   # 역슬래시 — 소스에 이스케이프를 쓰지 않으려고 코드 포인트로 만든다
BASE = "https://images.unsplash.com/photo-1507146426996-ef05306b995a"
PARAMS = "?auto=format&fit=crop&w=1000&q=80"
DOWNLOAD = "https://api.unsplash.com/photos/Abc123XyZ_k/download"
PROFILE = "https://unsplash.com/@janedoe"
UTM = "utm_source=chanceblog&utm_medium=referral"
LINE = f"*Photo by [Jane Doe]({PROFILE}?{UTM}) on [Unsplash](https://unsplash.com/?{UTM})*"
BAD_CHARACTERS = {                              # _BAD_URL_CHARS 의 구성원 하나하나(하나라도 빠지면 아래 시험이 깨진다)
    "공백": " ", "탭": "\t", "줄바꿈": "\n", "캐리지 리턴": "\r", "NUL": "\x00", "제어 문자(0x1f)": "\x1f", "DEL": "\x7f", "NBSP": " ", "전각 공백": "　", "EM 공백": " ",
    "꺾쇠 <": "<", "꺾쇠 >": ">", "큰따옴표": '"', "작은따옴표": "'", "백틱": "`", "역슬래시": ESC,
}


class IxidCharacterTest(unittest.TestCase):
    FOLDING = (chr(0x212A), chr(0x017F), chr(0x0131), chr(0x0130))        # 켈빈 기호 K·긴 s ſ·점 없는 i ı·점 있는 İ — re.IGNORECASE 로 읽으면 A-Za-z 와 같은 글자가 된다

    def test_letters_that_only_match_when_case_is_ignored_are_not_ixid_characters(self):
        for char in self.FOLDING:
            for value in (f"a{char}b", char, f"M3w{char}"):
                self.assertEqual(uc.ixid_from_query("ixid=" + value), "", hex(ord(char)))                    # 주소에 그대로 적힌 글자
                self.assertEqual(uc.ixid_from_query("ixid=" + quote(value, safe="")), "", hex(ord(char)))    # 퍼센트 부호화로 들어온 글자
                self.assertEqual(uc.with_ixid(BASE, "ixid=" + quote(value, safe=""), PARAMS), f"{BASE}{PARAMS}", hex(ord(char)))      # 그러면 ixid 없이 옛 주소다
        self.assertEqual(uc.ixid_from_query("ixid=aKs"), "aKs")                                                # 진짜 K·s 는 그대로 받는다

    def test_a_blank_ixid_next_to_a_real_one_makes_it_a_duplicate(self):
        for query in ("ixid=&ixid=M3w", "ixid=M3w&ixid=", "a=1&ixid=&b=2&ixid=M3w", "ixid&ixid=M3w"):
            self.assertEqual(uc.ixid_from_query(query), "", query)
        self.assertEqual(uc.with_ixid(BASE, "ixid=&ixid=M3w", PARAMS), f"{BASE}{PARAMS}")
        self.assertEqual(uc.ixid_from_query("ixid=M3w&iXid="), "M3w")                                          # 대소문자가 다른 키는 다른 키다


class BadUrlCharactersTest(unittest.TestCase):
    """세 검사(사진·프로필·사용 알림 주소)가 질의·조각에 든 나쁜 글자도 거절한다 — 호스트·경로 검사만으로는 이 글자들이 걸리지 않는다."""

    def addresses(self, tail):
        return {"사진": (uc.photo_url_ok, f"{BASE}{tail}"), "프로필": (uc.safe_profile_url, f"{PROFILE}{tail}"), "사용 알림": (uc.safe_download_url, f"{DOWNLOAD}{tail}")}

    def test_every_bad_character_in_the_query_or_fragment_is_refused_by_all_three_checks(self):
        for label, char in BAD_CHARACTERS.items():
            for where, tail in (("질의", f"?x=a{char}b"), ("조각", f"#a{char}b")):
                for kind, (check, url) in self.addresses(tail).items():
                    self.assertFalse(check(url), f"{kind} {where} {label}")

    def test_the_same_addresses_without_the_bad_character_are_accepted(self):
        for tail in ("?x=ab", "#ab", "?ixid=M3w&auto=format"):
            for kind, (check, url) in self.addresses(tail).items():
                self.assertTrue(check(url), f"{kind} {tail}")

    def test_the_length_limit_is_five_hundred_characters_for_all_three(self):
        for check, url in ((uc.photo_url_ok, BASE + "?x="), (uc.safe_profile_url, PROFILE + "?x="), (uc.safe_download_url, DOWNLOAD + "?x=")):
            exact = url + "a" * (uc.URL_MAX - len(url))
            self.assertEqual(len(exact), uc.URL_MAX)
            self.assertTrue(check(exact), check.__name__)
            self.assertFalse(check(exact + "a"), check.__name__)
        self.assertEqual(uc.URL_MAX, 500)

    def test_outer_whitespace_is_trimmed_but_inner_whitespace_is_not_allowed(self):
        self.assertTrue(uc.photo_url_ok(f"  {BASE}{PARAMS}\n"))
        self.assertFalse(uc.photo_url_ok(f"{BASE} {PARAMS}"))
        self.assertEqual(uc.safe_download_url(f" {DOWNLOAD}?ixid=M3w \n"), f"{DOWNLOAD}?ixid=M3w")
        self.assertEqual(uc.safe_download_url(f"{DOWNLOAD}?ixid=M3w x"), "")


class LookupIdBoundsTest(unittest.TestCase):
    def test_the_digit_part_takes_six_to_twenty_digits_and_the_tail_six_to_twenty_letters_or_digits(self):
        for number in ("123456-abcdef", "1" * 20 + "-" + "a" * 20, "123456-ABCDEF", "123456-a1B2c3", "1558494949-ef010cbdcc31"):
            self.assertEqual(uc.photo_lookup_id(number), "photo-" + number, number)
        for number in ("12345-abcdef", "1-a", "123456-abcde", "1234567-abcde", "1" * 21 + "-abcdef", "123456-" + "a" * 21, "1" * 5 + "-" + "a" * 20, "1" * 20 + "-" + "a" * 5, "0-0"):
            self.assertEqual(uc.photo_lookup_id(number), "", number)

    def test_the_tail_has_no_other_characters(self):
        for number in ("123456-abc_ef", "123456-abc-ef", "123456-abc.ef", "123456-abc ef", "123456-abc%20f", "123456-한글한글한글한글", "123456_abcdef", "123456abcdef", "a23456-abcdef"):
            self.assertEqual(uc.photo_lookup_id(number), "", number)


class CreditProblemsLineEndingTest(unittest.TestCase):
    URL = f"{BASE}?ixid=M3w&auto=format&fit=crop&w=1000&q=80"

    def crlf(self, text):
        return text.replace("\n", "\r\n")

    def test_a_crlf_post_with_the_line_right_after_the_image_line_has_no_problem(self):
        text = self.crlf(f'---\ntitle: "x"\nimage: "{self.URL}"\n---\n\n![설명]({self.URL})\n{LINE}\n\n본문 문장입니다.\n')
        self.assertEqual(uc.credit_problems(text, self.URL), [])
        self.assertEqual(uc.credit_problems(text.replace("\r\n", "\n"), self.URL), [])

    def test_a_crlf_post_is_still_checked(self):
        for text in (f"![설명]({self.URL})\n\n{LINE}\n", f"{LINE}\n![설명]({self.URL})\n", f"![설명]({self.URL})\n{LINE}\n{LINE}\n"):
            self.assertTrue(uc.credit_problems(self.crlf(text), self.URL), repr(text))
            self.assertEqual(uc.credit_problems(self.crlf(text), self.URL), uc.credit_problems(text, self.URL))     # 줄 끝 모양이 판정을 바꾸지 않는다

    def test_outer_spaces_around_the_image_line_do_not_matter(self):
        self.assertEqual(uc.credit_problems(f"  ![설명]({self.URL})  \r\n{LINE}\r\n", self.URL), [])


class DownloadLocationShapeTest(unittest.TestCase):
    """`links.download_location` 은 키가 실려 가는 주소다 — https·호스트가 정확히 api.unsplash.com·경로 `/photos/<id>/download` 만 받는다(질의는 어떤 값이든 같은 호스트의 것)."""
    MALICIOUS = ("https://evil.example/steal", "https://api.unsplash.com.evil.example/photos/Abc123XyZ_k/download", "http://api.unsplash.com/photos/Abc123XyZ_k/download",
                 "https://api.unsplash.com/search/photos?query=x", "file:///etc/passwd", "ftp://evil.example/x")

    def test_the_six_malicious_shapes_are_refused(self):
        for url in self.MALICIOUS:
            self.assertEqual(uc.safe_download_url(url), "", url)

    def test_real_looking_locations_are_accepted_as_they_are(self):
        for url in (f"{DOWNLOAD}?ixid=M3wxMjA3fDB8MXxzZWFyY2h8MXx8dGVzdA%3D%3D", DOWNLOAD, "https://api.unsplash.com/photos/6TXAcBpSAqE/download?ixid=M3w2NjQ5MDF8MHwxfHNlYXJjaA", "https://api.unsplash.com/photos/a-b_cdefghij/download"):
            self.assertEqual(uc.safe_download_url(url), url)

    def test_other_paths_on_the_same_host_are_refused(self):
        for path in ("/photos/Abc123XyZ_k", "/photos/Abc123XyZ_k/statistics", "/photos/Abc123XyZ_k/download/x", "/photos/download", "/photos//download", "/photos/a/download", "/photos/" + "A" * 41 + "/download",
                     "/users/janedoe/photos", "/me", "/photos/Abc123XyZ_k/download%2e", "/photos/../me/download", "//photos/Abc123XyZ_k/download"):
            self.assertEqual(uc.safe_download_url("https://api.unsplash.com" + path), "", path)

    def test_hosts_that_only_look_like_the_api_host_are_refused(self):
        for host in ("api.unsplash.com:443", "api.unsplash.com.", "API.unsplash.com", "user@api.unsplash.com", "api.unsplash.com@evil.example", "evil.example#@api.unsplash.com", "unsplash.com", "images.unsplash.com", "api.unsplash.co"):
            self.assertEqual(uc.safe_download_url(f"https://{host}/photos/Abc123XyZ_k/download"), "", host)


if __name__ == "__main__":
    unittest.main()
