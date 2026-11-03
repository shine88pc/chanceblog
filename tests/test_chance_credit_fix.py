"""Chance(generator.py)의 독립 검증(U3) 지적 반영 시험 — 가짜 Unsplash 로 돌고 네트워크를 쓰지 않는다.

구성
  1) 사용 알림 주소(`links.download_location`) — 키가 가는 주소라서 호스트·경로가 맞는 것만 받는다. 악성 6종이면 그 사진을 쓰지 않고 어떤 요청도 보내지 않는다(지적 ②a).
  2) 사진 주소(`urls.raw`) — 'HEAD 확인이 무엇이나 통과'라고 가정해도 낯선 호스트·경로는 글에 못 들어간다(지적 ③).
  3) 고정 목록 조회 총 횟수 상한(지적 ④).
  4) 키가 가는 길(지적 ②b·시험 공백 M126·M128·M129·M130): 세 요청 모두 키는 리다이렉트가 복사하지 않는 머리글에만 있고, 진짜 urllib 리다이렉트도 새 요청에 키를 안 싣고,
     주소·로그에 키가 없고, 시간 초과가 있다.
  5) 응답 상한 읽기(M083) — 조회 응답은 상한까지만 읽는다.
  6) 고정 목록을 쓰지 않는 경로: 기존 글 이미지 교체(repair)(M119)·기본값.
"""
import email.message
import json
import unittest
import urllib.request
from unittest import mock

import _bootstrap  # noqa: F401
import generator as g
from chance_credit_helpers import FAKE_KEY, PHOTO_RAW, ChanceBase, FakeApi, http_error, pool_photo_item
from main_image_helpers import FakeResponse, photo_item, results
from pipeline import unsplash_credit as uc

ALICE = photo_item("Aaa111bbb22", raw=PHOTO_RAW.format(pid="aaa111bbb22"), name="Alice Kim", username="alicekim")
ALICE_URL = "https://images.unsplash.com/photo-1500000000000-aaa111bbb22?ixid=M3wxfDB8&auto=format&fit=crop&w=1000&q=80"
ALICE_KEY = "images.unsplash.com/photo-1500000000000-aaa111bbb22"
POOL_FIRST = g.IMAGE_POOL[0]
SKIPPED_URL_LINE = "[참고] 사진 주소가 허용된 형식이 아니어서 쓰지 않은 사진: {n}장"
SKIPPED_NOTIFY_LINE = "[참고] 사용 알림 주소가 올바르지 않은 사진은 쓰지 않습니다"
CAP_LINE = "[경고] 고정 목록 사진 조회가 한 번에 허용한 횟수에 닿아 더 시도하지 않습니다"


def lookup_id(pool_url):
    return "photo-" + pool_url.split("/photo-")[1].split("?")[0]


def alice(**fields):
    return photo_item("Aaa111bbb22", raw=fields.pop("raw", PHOTO_RAW.format(pid="aaa111bbb22")), name="Alice Kim", username="alicekim", **fields)


def all_pool_photos():
    return {lookup_id(url): pool_photo_item(url) for url in g.IMAGE_POOL}


class DownloadLocationTest(ChanceBase):
    """지적 ②a: 응답의 `links.download_location` 은 키가 실려 가는 주소다. 검사에 걸리면 그 사진을 쓰지 않는다."""
    MALICIOUS = (("타 호스트", "https://evil.example/steal"), ("호스트 흉내", "https://api.unsplash.com.evil.example/photos/Aaa111bbb22/download"),
                 ("http", "http://api.unsplash.com/photos/Aaa111bbb22/download?ixid=M3wxfDB8"), ("같은 호스트 다른 경로", "https://api.unsplash.com/search/photos?query=x"),
                 ("file", "file:///etc/passwd"), ("ftp", "ftp://evil.example/x"))

    def search(self, *items, api=None):
        self.use(api or FakeApi(searches=[results(*items)]))
        return self.call(g.search_unsplash, "coffee")

    def test_a_photo_with_a_malicious_download_location_is_not_used_and_nothing_is_called(self):
        for label, location in self.MALICIOUS:
            with self.subTest(label):
                api = FakeApi(searches=[results(alice(download=location))])
                urls, out = self.search(api=api)
                self.assertEqual(urls, [])                                                    # 그 사진은 쓰지 않는다
                self.assertEqual((g._credits, g._download_locations), ({}, {}))               # 아무것도 남기지 않는다
                self.assertIn(SKIPPED_NOTIFY_LINE, out.splitlines())                          # 고정 문구 한 줄
                self.assertNotIn(location, out)                                               # 응답의 값은 로그에 싣지 않는다
                picked, _out = self.call(g.pick_images, ["coffee"], set(), 1)
                self.assertEqual(picked, [])
                g.trigger_download(ALICE_URL)                                                 # 어떻게든 불러 봐도
                self.assertEqual({call["path"] for call in api.calls}, {"/search/photos"})    # 검색 말고는 어떤 요청도 없었다
                self.assertEqual({call["host"] for call in api.calls}, {"api.unsplash.com"})
                self.assertEqual(api.downloads, [])

    def test_the_line_is_printed_once_per_search_however_many_photos_were_dropped(self):
        items = [alice(download="https://evil.example/x"), photo_item("Ccc333ddd44", raw=PHOTO_RAW.format(pid="ccc333ddd44"), download="ftp://evil.example/y"), alice(download="file:///z")]
        _urls, out = self.search(*items)
        self.assertEqual(out.splitlines().count(SKIPPED_NOTIFY_LINE), 1)

    def test_a_normal_location_is_kept_in_its_checked_form_and_called_once_after_the_pick(self):
        api = FakeApi(searches=[results(alice(download="  https://api.unsplash.com/photos/Aaa111bbb22/download?ixid=M3wxfDB8 "))])
        urls, out = self.search(api=api)
        self.assertEqual(urls, [ALICE_URL])
        self.assertNotIn(SKIPPED_NOTIFY_LINE, out)
        self.assertEqual(g._download_locations[ALICE_KEY], "https://api.unsplash.com/photos/Aaa111bbb22/download?ixid=M3wxfDB8")      # 바깥 공백은 뗀 값
        g.trigger_download(ALICE_URL)
        self.assertEqual(api.downloads, ["/photos/Aaa111bbb22/download"])
        self.assertEqual(api.calls[-1]["host"], "api.unsplash.com")

    def test_a_response_without_a_location_is_still_used_but_nothing_is_called(self):
        missing_key, links_text = alice(), alice()
        missing_key["links"].pop("download_location")
        links_text["links"] = "x"
        for label, item in (("links 없음", alice(remove=("links",))), ("칸 없음", missing_key), ("값 None", alice(download=None)), ("빈 글", alice(download="")), ("links 가 글", links_text)):
            with self.subTest(label):
                api = FakeApi(searches=[results(item)])
                urls, out = self.search(api=api)
                self.assertEqual(urls, [ALICE_URL])
                self.assertEqual(g._credits[ALICE_KEY], ("Alice Kim", "https://unsplash.com/@alicekim"))
                self.assertNotIn(ALICE_KEY, g._download_locations)
                self.assertNotIn(SKIPPED_NOTIFY_LINE, out)
                g.trigger_download(ALICE_URL)
                self.assertEqual(api.downloads, [])
                self.assertEqual([call["path"] for call in api.calls], ["/search/photos"])

    def test_a_location_that_is_present_but_is_not_a_good_address_is_refused(self):
        for value in (5, ["x"], {"a": 1}, True, 0, [], "   ", "x", "https://api.unsplash.com/photos/Aaa111bbb22/download\n/../x"):
            with self.subTest(repr(value)):
                urls, out = self.search(alice(download=value))
                self.assertEqual(urls, [], repr(value))
                self.assertIn(SKIPPED_NOTIFY_LINE, out)

    def test_an_old_value_of_the_same_photo_does_not_survive_a_newer_response(self):
        self.search(alice())
        self.assertIn(ALICE_KEY, g._download_locations)
        urls, _out = self.search(alice(download=None))                                      # 새 응답에 알림 주소가 없다 → 낡은 값을 지운다(사진은 쓴다)
        self.assertEqual(urls, [ALICE_URL])
        self.assertNotIn(ALICE_KEY, g._download_locations)
        self.assertIn(ALICE_KEY, g._credits)
        self.search(alice())
        urls, _out = self.search(alice(download="https://evil.example/steal"))               # 새 응답의 알림 주소가 틀렸다 → 둘 다 지운다(사진도 안 쓴다)
        self.assertEqual(urls, [])
        self.assertEqual((g._credits, g._download_locations), ({}, {}))

    def test_trigger_download_checks_the_stored_address_again_before_it_calls(self):
        api = self.use(FakeApi())
        for label, location in self.MALICIOUS:
            with self.subTest(label):
                g._download_locations[ALICE_KEY] = location                                  # 어떤 경로로든 기록부에 나쁜 값이 들어와 있어도
                g.trigger_download(ALICE_URL)
                self.assertEqual(api.calls, [], label)
        g._download_locations[ALICE_KEY] = "https://api.unsplash.com/photos/Aaa111bbb22/download"
        g.trigger_download(ALICE_URL)
        self.assertEqual(api.downloads, ["/photos/Aaa111bbb22/download"])

    def test_no_call_in_a_practice_run_or_without_a_key(self):
        api = self.use(FakeApi())
        g._download_locations[ALICE_KEY] = "https://api.unsplash.com/photos/Aaa111bbb22/download"
        for flags in (dict(DRY_RUN=True), dict(STUB_UNSPLASH=True)):
            with mock.patch.multiple(g, **flags):
                g.trigger_download(ALICE_URL)
        g.trigger_download("")
        g.trigger_download(None)
        self.assertEqual(api.calls, [])

    def test_a_failing_download_call_is_ignored_and_never_prints_the_key(self):
        api = self.use(FakeApi(download_error=OSError("연결 실패")))
        g._download_locations[ALICE_KEY] = "https://api.unsplash.com/photos/Aaa111bbb22/download"
        _value, out = self.call(g.trigger_download, ALICE_URL)
        self.assertEqual(len(api.downloads), 1)
        self.assertNotIn(FAKE_KEY, out)


class CheckOrderTest(ChanceBase):
    """한 사진을 읽는 차례는 '주소를 만든다 → 주소가 맞는지 → 알림 주소가 맞는지 → 작가를 읽는다 → 기록한다' 이고, 앞의 검사에 걸리면 뒤로 가지 않으며 기록은 모든 검사를 지난 사진에만 남는다."""

    def search(self, *items):
        self.use(FakeApi(searches=[results(*items)]))
        return self.call(g.search_unsplash, "coffee")

    def test_a_bad_address_is_counted_before_the_notice_address_is_looked_at(self):
        urls, out = self.search(alice(raw="https://evil.example/photo-1?ixid=M3w", download="https://evil.example/steal"))
        self.assertEqual(urls, [])
        self.assertIn(SKIPPED_URL_LINE.format(n=1), out.splitlines())
        self.assertNotIn(SKIPPED_NOTIFY_LINE, out)
        self.assertEqual((g._credits, g._download_locations), ({}, {}))

    def test_a_bad_notice_address_is_refused_before_the_author_is_read_and_nothing_is_recorded(self):
        no_author = photo_item("Zzz999yyy88", raw=PHOTO_RAW.format(pid="zzz999yyy88"), download="ftp://evil.example/x", remove=("user",))
        urls, out = self.search(no_author)
        self.assertEqual(urls, [])
        self.assertIn(SKIPPED_NOTIFY_LINE, out.splitlines())
        self.assertEqual((g._credits, g._download_locations), ({}, {}))

    def test_nothing_is_recorded_for_a_photo_until_all_the_checks_pass(self):
        recorded = []
        for item in (alice(raw="https://evil.example/photo-1"), alice(download="http://api.unsplash.com/photos/Aaa111bbb22/download"), alice(remove=("user",), download="file:///x")):
            self.search(item)
            recorded.append((dict(g._credits), dict(g._download_locations)))
        self.assertEqual(recorded, [({}, {})] * 3)

    def test_the_old_record_of_the_same_key_goes_away_when_a_lookalike_address_is_refused(self):
        self.search(alice())
        self.assertIn(ALICE_KEY, g._credits)
        urls, out = self.search(alice(raw="https://IMAGES.UNSPLASH.COM/photo-1500000000000-aaa111bbb22?ixid=M3wxfDB8"))      # 키(호스트+경로 소문자)는 같고 주소 모양은 틀리다
        self.assertEqual(urls, [])
        self.assertIn(SKIPPED_URL_LINE.format(n=1), out.splitlines())
        self.assertEqual((g._credits, g._download_locations), ({}, {}))

    def test_the_record_is_made_for_good_photos_next_to_refused_ones(self):
        bob = photo_item("Ccc333ddd44", raw=PHOTO_RAW.format(pid="ccc333ddd44"), name="Bob Lee", username="boblee")
        urls, out = self.search(alice(download="https://evil.example/x"), bob, alice(raw="javascript:alert(1)"))
        self.assertEqual(urls, [g.build_image_url(PHOTO_RAW.format(pid="ccc333ddd44"))])
        self.assertEqual(set(g._credits), {"images.unsplash.com/photo-1500000000000-ccc333ddd44"})
        self.assertIn(SKIPPED_URL_LINE.format(n=1), out.splitlines())
        self.assertIn(SKIPPED_NOTIFY_LINE, out.splitlines())


class PhotoAddressTest(ChanceBase):
    """지적 ③: `urls.raw` 의 호스트·경로도 검사한다. ChanceBase 가 이미지 확인(HEAD, url_ok)을 무엇이나 통과시키므로 '확인이 허술한 최악'에서도 막히는지 본다."""
    HOSTILE = ("https://images.unsplash.com/photo-1)[evil](https://evil.example)", "https://images.unsplash.com/photo-1\n\n[evil](https://evil.example)", 'https://images.unsplash.com/photo-1 "title"',
               "https://images.unsplash.com/photo-{{ 7*7 }}", 'https://images.unsplash.com/photo-1"\nlayout: evil', "https://images.unsplash.com/photo-1'x", "javascript:alert(1)", "//evil.example/photo-1",
               "http://images.unsplash.com/photo-1", "https://images.unsplash.com.evil.example/photo-1", "https://evil.example/photo-1?ixid=ok", "https://user@images.unsplash.com/photo-1",
               "https://images.unsplash.com:444/photo-1", "https://images.unsplash.com/uploads/1", "https://images.unsplash.com/photo-1<script>", "https://images.unsplash.com/photo-1" + chr(92) + "x")
    LOOKALIKE = ("https://IMAGES.unsplash.com/photo-1", "https://images.unsplash.com./photo-1", "https://images.unsplash.com//photo-1", "https://images.unsplash.com/photos/photo-1",
                 "https://images.unsplash.com/PHOTO-1", "https://images.unsplash.com/photo-", "https://images.unsplash.com/photo-%31", "https://images.unsplash.com/photo-" + "a" * 65,
                 "https://images.unsplash.com/photo-1/", "https://images.unsplash.com/photo-1/../x", "https://images.unsplash.com/photo-1 x", "https://plus.unsplash.com/photo-1",
                 "https://images.unsplash.com@evil.example/photo-1", "ftp://images.unsplash.com/photo-1", "data:text/html,x", "", "photo-1")
    SAFE = (("https://images.unsplash.com/photo-1?ixid=M3w&w=9#frag", "https://images.unsplash.com/photo-1?ixid=M3w&auto=format&fit=crop&w=1000&q=80"),     # 조각·나머지 질의는 버리고 ixid 만 남긴다
            ("https://images.unsplash.com/photo-1?ixid=" + "A" * 201, "https://images.unsplash.com/photo-1?auto=format&fit=crop&w=1000&q=80"),               # 모양이 틀린 ixid 는 빼고 계속
            ("HTTPS://images.unsplash.com/photo-1", "https://images.unsplash.com/photo-1?auto=format&fit=crop&w=1000&q=80"),                               # 스킴 대소문자는 정규형으로
            ("https://images.unsplash.com/photo-1?ixid=M3w&note=a b<c>'d" + chr(92) + "e#frag", "https://images.unsplash.com/photo-1?ixid=M3w&auto=format&fit=crop&w=1000&q=80"))   # 버려지는 질의에 나쁜 글자가 있어도, 검사는 다시 만든 주소에 한다

    def one(self, raw):
        self.use(FakeApi(searches=[results(alice(raw=raw))]))
        return self.call(g.search_unsplash, "coffee")

    def test_hostile_addresses_never_come_out_of_the_search_and_leave_no_record(self):
        for raw in self.HOSTILE + self.LOOKALIKE:
            with self.subTest(repr(raw)):
                urls, out = self.one(raw)
                self.assertEqual(urls, [])
                self.assertEqual((g._credits, g._download_locations), ({}, {}))
                if raw:
                    self.assertIn(SKIPPED_URL_LINE.format(n=1), out.splitlines())

    def test_the_picker_never_hands_over_a_hostile_address_even_when_the_image_check_passes_anything(self):
        for raw in self.HOSTILE + self.LOOKALIKE:
            with self.subTest(repr(raw)):
                self.use(FakeApi(searches=[results(alice(raw=raw))]))
                picked, _out = self.call(g.pick_images, ["coffee"], set(), 1)
                self.assertEqual(picked, [])
                self.assertEqual(g.credit_line_for(raw), "")

    def test_the_safe_shapes_come_out_in_their_clean_form(self):
        for raw, expected in self.SAFE:
            with self.subTest(raw[:50]):
                urls, out = self.one(raw)
                self.assertEqual(urls, [expected])
                self.assertTrue(uc.photo_url_ok(urls[0]))
                self.assertNotIn("쓰지 않은 사진", out)

    def test_every_address_that_comes_out_passes_the_shape_check(self):
        raws = [raw for raw, _ in self.SAFE] + list(self.HOSTILE + self.LOOKALIKE)
        self.use(FakeApi(searches=[results(*[alice(raw=raw) for raw in raws])]))
        urls, _out = self.call(g.search_unsplash, "coffee")
        self.assertTrue(urls)
        for url in urls:
            self.assertTrue(uc.photo_url_ok(url), url)

    def test_the_lookup_of_the_fixed_list_gets_the_same_check(self):
        for raw in self.HOSTILE + self.LOOKALIKE:
            with self.subTest(repr(raw)):
                reply = pool_photo_item(POOL_FIRST)
                reply["urls"]["raw"] = raw
                self.use(FakeApi(searches=[results()], photos={lookup_id(POOL_FIRST): reply}))
                value, _out = self.call(g.fetch_pool_photo, POOL_FIRST)
                self.assertIsNone(value)
                self.assertEqual((g._credits, g._download_locations), ({}, {}))

    def test_the_lookup_of_the_fixed_list_gets_the_notice_address_check_too(self):
        for label, location in DownloadLocationTest.MALICIOUS:
            with self.subTest(label):
                reply = pool_photo_item(POOL_FIRST)
                reply["links"]["download_location"] = location
                self.use(FakeApi(searches=[results()], photos={lookup_id(POOL_FIRST): reply}))
                value, out = self.call(g.fetch_pool_photo, POOL_FIRST)
                self.assertIsNone(value)
                self.assertIn(SKIPPED_NOTIFY_LINE, out.splitlines())
                self.assertEqual((g._credits, g._download_locations), ({}, {}))


class PoolTotalCapTest(ChanceBase):
    """지적 ④: 고정 목록 조회는 한 번의 pick_images 호출에서 총 POOL_LOOKUP_MAX_TOTAL 번까지만 부른다(성공·실패·주소 확인 실패·이미 쓴 사진을 가리지 않고 '조회를 부른 횟수')."""

    def pick(self, api, used=None, count=2, head=lambda url, timeout=10: False):
        self.use(api)
        with mock.patch.object(g, "url_ok", head):
            return self.call(g.pick_images, [], set() if used is None else used, count, allow_pool=True)

    def test_the_numbers(self):
        self.assertEqual(g.POOL_LOOKUP_MAX_TOTAL, 6)
        self.assertEqual(g.POOL_LOOKUP_MAX_FAILS, 3)
        self.assertGreater(g.POOL_LOOKUP_MAX_TOTAL, g.POOL_LOOKUP_MAX_FAILS)
        self.assertGreater(len(g.IMAGE_POOL), 2 * g.POOL_LOOKUP_MAX_TOTAL)            # 고정 목록은 상한보다 훨씬 길다 — 이 시험들이 상한에 닿을 수 있다

    def test_every_lookup_succeeds_and_every_image_check_fails_the_lookups_stop_at_the_cap(self):
        api = FakeApi(searches=[results()], photos=all_pool_photos())
        picked, out = self.pick(api)
        self.assertEqual(picked, [])
        self.assertEqual(len(api.lookups), 6)                                             # 32 → 6 (독립 검증 재현 H6)
        self.assertEqual(len(api.lookups), g.POOL_LOOKUP_MAX_TOTAL)
        self.assertEqual(api.lookups, [f"/photos/{lookup_id(url)}" for url in g.IMAGE_POOL[:6]])
        self.assertEqual(out.count(CAP_LINE), 1)                                         # 한 줄만(들여쓰기는 pick_images 의 다른 [경고]·[참고] 줄과 같다)
        self.assertNotIn("연달아 실패", out)                                              # 연속 실패 규칙이 아니라 총 횟수 규칙이 멈췄다

    def test_the_cap_is_per_call(self):
        api = FakeApi(searches=[results()], photos=all_pool_photos())
        self.pick(api)
        self.pick(api)
        self.assertEqual(len(api.lookups), 2 * g.POOL_LOOKUP_MAX_TOTAL)

    def test_failed_lookups_count_toward_the_total_without_triggering_the_in_a_row_rule(self):
        photos = {lookup_id(url): pool_photo_item(url) for index, url in enumerate(g.IMAGE_POOL) if index % 2 == 0}          # 짝수 번째만 성공(홀수는 404)
        api = FakeApi(searches=[results()], photos=photos)
        picked, out = self.pick(api)
        self.assertEqual(picked, [])
        self.assertEqual(len(api.lookups), g.POOL_LOOKUP_MAX_TOTAL)
        self.assertIn(CAP_LINE, out)
        self.assertNotIn("연달아 실패", out)

    def test_photos_that_turn_out_to_be_used_already_count_toward_the_total(self):
        other = pool_photo_item(POOL_FIRST)
        other["urls"]["raw"] = "https://images.unsplash.com/photo-9999999999999-zzzzzzzzzzzz?ixid=M3wxfDB8"
        api = FakeApi(searches=[results()], photos={lookup_id(url): other for url in g.IMAGE_POOL})
        picked, out = self.pick(api, used={"images.unsplash.com/photo-9999999999999-zzzzzzzzzzzz"}, head=lambda url, timeout=10: True)
        self.assertEqual(picked, [])
        self.assertEqual(len(api.lookups), g.POOL_LOOKUP_MAX_TOTAL)
        self.assertIn(CAP_LINE, out)

    def test_candidates_used_before_the_lookup_are_skipped_without_counting(self):
        used = {g.image_key(url) for url in g.IMAGE_POOL[:3]}
        api = FakeApi(searches=[results()], photos=all_pool_photos())
        picked, out = self.pick(api, used=used)
        self.assertEqual(picked, [])
        self.assertEqual(api.lookups, [f"/photos/{lookup_id(url)}" for url in g.IMAGE_POOL[3:3 + g.POOL_LOOKUP_MAX_TOTAL]])         # 건너뛴 셋은 세지 않는다
        self.assertIn(CAP_LINE, out)

    def test_the_sixth_lookup_may_still_give_the_second_photo_and_then_no_warning_is_printed(self):
        heads = []

        def head(url, timeout=10):
            heads.append(url)
            return len(heads) > 4                                                         # 앞의 넷은 확인 실패, 다섯째·여섯째는 통과

        api = FakeApi(searches=[results()], photos=all_pool_photos())
        picked, out = self.pick(api, head=head)
        self.assertEqual(len(picked), 2)
        self.assertEqual(len(api.lookups), g.POOL_LOOKUP_MAX_TOTAL)
        self.assertNotIn(CAP_LINE, out)

    def test_a_normal_run_needs_two_lookups_and_no_warning(self):
        api = FakeApi(searches=[results()], photos=all_pool_photos())
        picked, out = self.pick(api, head=lambda url, timeout=10: True)
        self.assertEqual(len(picked), 2)
        self.assertEqual(len(api.lookups), 2)
        self.assertNotIn(CAP_LINE, out)
        self.assertNotIn("연달아 실패", out)

    def test_the_in_a_row_rule_is_still_the_one_that_stops_a_run_of_failures(self):
        api = FakeApi(searches=[results()], photos={})
        picked, out = self.pick(api)
        self.assertEqual(picked, [])
        self.assertEqual(len(api.lookups), g.POOL_LOOKUP_MAX_FAILS)
        self.assertIn("연달아 실패해 더 시도하지 않습니다", out)
        self.assertNotIn(CAP_LINE, out)

    def test_nothing_is_looked_up_when_the_fixed_list_is_off_or_the_search_was_enough(self):
        api = self.use(FakeApi(searches=[results(alice())], photos=all_pool_photos()))
        picked, _out = self.call(g.pick_images, ["coffee"], set(), 1, allow_pool=True)
        self.assertEqual(picked, [ALICE_URL])
        self.assertEqual(api.lookups, [])
        api = self.use(FakeApi(searches=[results()], photos=all_pool_photos()))
        picked, _out = self.call(g.pick_images, ["coffee"], set(), 2)                    # 기본값은 고정 목록을 쓰지 않는다
        self.assertEqual((picked, api.lookups), ([], []))


class KeyRouteTest(ChanceBase):
    """지적 ②b: 세 요청(검색·고정 목록 조회·사용 알림) 모두 키(Authorization)는 리다이렉트가 복사하지 않는 머리글에만 있다 + 시험 공백 M126·M128·M129·M130."""

    def make_all_calls(self):
        api = self.use(FakeApi(searches=[results(alice())], photos={lookup_id(POOL_FIRST): pool_photo_item(POOL_FIRST)}))
        self.call(g.search_unsplash, "coffee")
        self.call(g.trigger_download, ALICE_URL)
        self.call(g.fetch_pool_photo, POOL_FIRST)
        kinds = {"search": [c for c in api.calls if c["path"] == "/search/photos"], "download": [c for c in api.calls if c["path"].endswith("/download")],
                 "lookup": [c for c in api.calls if c["path"].startswith("/photos/") and not c["path"].endswith("/download")]}
        for kind, calls in kinds.items():
            self.assertEqual(len(calls), 1, kind)
        return api, {kind: calls[0] for kind, calls in kinds.items()}

    def test_the_key_is_only_in_the_header_that_redirects_do_not_copy(self):
        _api, calls = self.make_all_calls()
        for kind, call in calls.items():
            self.assertEqual(call["unredirected"], {"Authorization": f"Client-ID {FAKE_KEY}"}, kind)
            self.assertEqual([name for name in call["redirectable"] if name.lower() == "authorization"], [], kind)
            self.assertEqual(call["headers"]["Authorization"], f"Client-ID {FAKE_KEY}", kind)       # 보낼 때는 실린다
            self.assertEqual(call["host"], "api.unsplash.com", kind)

    def test_the_key_is_never_in_an_address(self):
        api, _calls = self.make_all_calls()
        for call in api.calls:
            self.assertNotIn(FAKE_KEY, call["url"])
            self.assertNotIn("client_id", call["url"].lower())
            self.assertFalse([name for name in call["query"] if "key" in name.lower() or "client" in name.lower() or "auth" in name.lower()], call["url"])

    def test_the_new_request_of_a_redirect_gets_no_key(self):
        _api, calls = self.make_all_calls()
        for kind, call in calls.items():
            new = urllib.request.HTTPRedirectHandler().redirect_request(call["request"], None, 302, "Found", {}, "https://evil.example/steal")
            self.assertEqual(new.full_url, "https://evil.example/steal")
            self.assertEqual(new.get_header("User-agent"), g.UA, kind)                          # 복사할 머리글은 복사됐다(이 시험이 빈 그릇이 아니다)
            self.assertEqual([name for name, _value in new.header_items() if name.lower() == "authorization"], [], kind)
            self.assertNotIn(FAKE_KEY, repr(new.header_items()))

    def test_a_real_urllib_redirect_does_not_carry_the_key_to_the_new_host(self):
        """진짜 urllib 의 오류·리다이렉트 처리를 거친다(소켓 없이): api.unsplash.com 이 낯선 호스트로 302 를 보내도 새 요청에는 키가 없다."""
        for kind, run in (("search", lambda: g.search_unsplash("coffee")), ("download", lambda: (g._download_locations.update({ALICE_KEY: "https://api.unsplash.com/photos/Aaa111bbb22/download"}), g.trigger_download(ALICE_URL))),
                          ("lookup", lambda: g.fetch_pool_photo(POOL_FIRST))):
            with self.subTest(kind):
                seen = []
                opener = urllib.request.OpenerDirector()
                for handler in (urllib.request.HTTPRedirectHandler(), urllib.request.HTTPErrorProcessor(), _FakeHttps(seen)):
                    opener.add_handler(handler)
                with mock.patch.object(urllib.request, "_opener", opener):
                    self.call(run)
                self.assertEqual([request["host"] for request in seen], ["api.unsplash.com", "evil.example"], kind)           # 리다이렉트를 실제로 따라갔다
                self.assertEqual(seen[0]["headers"]["authorization"], f"Client-ID {FAKE_KEY}")                              # 첫 요청에는 키가 있고
                self.assertNotIn("authorization", seen[1]["headers"], kind)                                                 # 새 호스트로 간 요청에는 없다
                self.assertNotIn(FAKE_KEY, repr(seen[1]))

    def test_the_key_appears_in_no_log_line_whatever_fails(self):
        failures = (http_error(403), http_error(429), http_error(404), http_error(500), OSError("연결 실패"), TimeoutError("시간 초과"), FakeResponse(b"{nope"))
        for failure in failures:
            with self.subTest(repr(failure)[:40]):
                api = self.use(FakeApi(searches=[failure], photos={lookup_id(POOL_FIRST): failure}, download_error=OSError("알림 실패")))
                outputs = [self.call(g.search_unsplash, "coffee")[1], self.call(g.fetch_pool_photo, POOL_FIRST)[1]]
                g._download_locations[ALICE_KEY] = "https://api.unsplash.com/photos/Aaa111bbb22/download"
                outputs.append(self.call(g.trigger_download, ALICE_URL)[1])
                outputs.append(self.call(g.pick_images, ["coffee"], set(), 2, allow_pool=True)[1])
                for output in outputs:
                    self.assertNotIn(FAKE_KEY, output)
                for call in api.calls:
                    self.assertNotIn(FAKE_KEY, call["url"])

    def test_the_failure_lines_of_the_lookup_say_what_failed_without_the_key(self):
        for failure, expected in ((http_error(429), "Unsplash API 오류 429 (사진 조회)"), (http_error(403), "Unsplash API 오류 403 (사진 조회)"), (OSError("연결 실패"), "Unsplash 호출 실패 (사진 조회): 연결 실패")):
            self.use(FakeApi(searches=[results()], photos={lookup_id(POOL_FIRST): failure}))
            value, out = self.call(g.fetch_pool_photo, POOL_FIRST)
            self.assertIsNone(value)
            self.assertIn(expected, out)
            self.assertNotIn(FAKE_KEY, out)
            self.assertNotIn("Client-ID", out)

    def test_every_request_has_a_time_limit(self):
        _api, calls = self.make_all_calls()
        for kind, call in calls.items():
            self.assertIsInstance(call["timeout"], (int, float), kind)
            self.assertTrue(0 < call["timeout"] <= 30, f"{kind}: {call['timeout']}")


class BoundedReadTest(ChanceBase):
    """시험 공백 M083: 고정 목록 조회의 응답은 POOL_LOOKUP_MAX_BODY + 1 바이트까지만 읽는다."""

    class Spy(FakeResponse):
        def __init__(self, body):
            super().__init__(body)
            self.amounts = []

        def read(self, amt=None):
            self.amounts.append(amt)
            return super().read(amt)

    def lookup(self, response):
        self.use(FakeApi(searches=[results()], photos={lookup_id(POOL_FIRST): response}))
        return self.call(g.fetch_pool_photo, POOL_FIRST)

    def test_the_body_is_read_with_a_limit_never_whole(self):
        spy = self.Spy(json.dumps(pool_photo_item(POOL_FIRST)).encode("utf-8"))
        value, _out = self.lookup(spy)
        self.assertIsNotNone(value)
        self.assertEqual(spy.amounts, [g.POOL_LOOKUP_MAX_BODY + 1])

    def test_a_body_of_exactly_the_limit_is_accepted_and_one_byte_more_is_not(self):
        payload = json.dumps(pool_photo_item(POOL_FIRST)).encode("utf-8")
        exact = payload + b" " * (g.POOL_LOOKUP_MAX_BODY - len(payload))
        self.assertEqual(len(exact), g.POOL_LOOKUP_MAX_BODY)
        value, _out = self.lookup(FakeResponse(exact))
        self.assertIsNotNone(value)
        value, _out = self.lookup(FakeResponse(exact + b" "))
        self.assertIsNone(value)

    def test_a_reader_that_ignores_the_limit_is_still_refused(self):
        class Greedy(FakeResponse):
            def read(self, amt=None):
                return self._body                                                     # 상한을 무시하고 통째로 준다

        payload = json.dumps(pool_photo_item(POOL_FIRST)).encode("utf-8")
        value, _out = self.lookup(Greedy(payload + b" " * (g.POOL_LOOKUP_MAX_BODY + 10)))
        self.assertIsNone(value)

    def test_a_body_that_is_not_bytes_is_refused(self):
        class Texty(FakeResponse):
            def read(self, amt=None):
                return "{}"

        value, _out = self.lookup(Texty())
        self.assertIsNone(value)


class FixedListIsOffTest(ChanceBase):
    """시험 공백 M119: 기존 글의 이미지 교체(repair)와 기본 호출은 고정 목록을 쓰지 않는다 — 검색이 비면 '후보 없음'이고 조회는 한 번도 없다."""
    POST = {"title": "제목입니다", "tags": "a, b", "category": "기술"}

    def test_repair_returns_nothing_when_the_search_is_empty_and_never_looks_up_the_fixed_list(self):
        api = self.use(FakeApi(searches=[results()], photos=all_pool_photos()))
        with mock.patch.object(g, "STUB_GEMINI", True):
            value, _out = self.call(g.repair, dict(self.POST), set())
        self.assertIsNone(value)
        self.assertEqual(api.lookups, [])
        self.assertTrue(api.searched)

    def test_repair_uses_a_search_photo_when_there_is_one(self):
        api = self.use(FakeApi(searches=[results(alice())], photos=all_pool_photos()))
        with mock.patch.object(g, "STUB_GEMINI", True):
            value, _out = self.call(g.repair, dict(self.POST), set())
        self.assertEqual(value, ALICE_URL)
        self.assertEqual(api.lookups, [])

    def test_fix_images_without_a_search_result_skips_the_post_and_looks_nothing_up(self):
        import tempfile
        from pathlib import Path
        api = self.use(FakeApi(searches=[results()], photos=all_pool_photos()))
        with tempfile.TemporaryDirectory() as tmp:
            posts = Path(tmp) / "_posts"
            first = posts / "a" / "2026-10-01-KR-000001.md"
            first.parent.mkdir(parents=True)
            old = "https://images.unsplash.com/photo-1111111111111-aaaaaaaaaaaa?auto=format&fit=crop&w=1000&q=80"
            text = f'---\nlayout: post\ntitle: "제목입니다"\ncategory: "기술"\nlang: ko\nimage: "{old}"\n---\n\n본문입니다.\n\n![Thumbnail]({old})\n'
            first.write_text(text, encoding="utf-8")
            second = posts / "a" / "2026-10-02-KR-000002.md"
            second.write_text(text, encoding="utf-8")                                       # 같은 이미지 → 둘째 글이 '중복'
            with mock.patch.multiple(g, STUB_GEMINI=True, POSTS_DIR=posts):
                _value, out = self.call(g.fix_images)
            self.assertEqual(second.read_text(encoding="utf-8"), text)                      # 교체 후보가 없어 그대로
            self.assertIn("교체 후보 없음", out)
            self.assertEqual(api.lookups, [])


class RecordPhotoDirectTest(ChanceBase):
    """`_record_photo` 를 직접 부를 때(집계 딕셔너리 없이)도 검사에 걸린 사진은 None 이고 기록이 없으며 고정 문구가 그 자리에서 한 줄 나온다.
    반복문(search_unsplash·fetch_pool_photo)이 집계를 넘기면 줄은 그쪽이 묶어서 한 번 낸다."""

    def test_a_photo_with_a_wrong_notice_address_gives_none_nothing_recorded_and_the_fixed_line(self):
        for label, location in DownloadLocationTest.MALICIOUS:
            with self.subTest(label):
                value, out = self.call(g._record_photo, alice(download=location))
                self.assertIsNone(value)
                self.assertEqual((g._credits, g._download_locations), ({}, {}))
                self.assertEqual(out.splitlines(), [SKIPPED_NOTIFY_LINE])

    def test_a_photo_with_a_wrong_address_gives_none_nothing_recorded_and_the_count_line(self):
        value, out = self.call(g._record_photo, alice(raw="https://evil.example/photo-1?ixid=M3w"))
        self.assertIsNone(value)
        self.assertEqual((g._credits, g._download_locations), ({}, {}))
        self.assertEqual(out.splitlines(), [SKIPPED_URL_LINE.format(n=1)])

    def test_a_good_photo_prints_nothing_and_is_recorded(self):
        value, out = self.call(g._record_photo, alice())
        self.assertEqual((value, out), (ALICE_URL, ""))
        self.assertIn(ALICE_KEY, g._credits)
        self.assertIn(ALICE_KEY, g._download_locations)

    def test_with_a_collector_nothing_is_printed_and_the_counts_go_to_it(self):
        skipped = {}
        for item in (alice(download="ftp://evil.example/x"), alice(raw="javascript:alert(1)"), alice(raw="https://evil.example/photo-1"), alice()):
            _value, out = self.call(g._record_photo, item, skipped)
            self.assertEqual(out, "")
        self.assertEqual(skipped, {"ping": 1, "url": 2})
        self.assertIsNone(g._record_photo({}, skipped))
        self.assertEqual(skipped, {"ping": 1, "url": 2})                          # 주소가 아예 없는 항목은 세지 않는다(이미 있던 동작)

    def test_not_a_dict_or_without_an_address_is_none_without_a_line(self):
        for item in (None, 5, "x", [], {}, {"urls": None}, {"urls": {"raw": ""}}, {"urls": {"raw": 5}}):
            value, out = self.call(g._record_photo, item)
            self.assertEqual((value, out), (None, ""), repr(item))


class DocsFixTest(unittest.TestCase):
    """문서가 고친 동작과 같은 말을 한다(독립 검증이 '문서가 덜 적은 것'으로 꼽은 곳): 이름 칸 평문은 증명할 수 없어 ⚠️·키 길과 주소 검사가 Chance 도 같다·새 글 사진 주소 검사·조회 총 상한·틱마다 재시도 한계·남은 한계."""

    @staticmethod
    def read(rel):
        return (_bootstrap.ROOT / rel).read_text(encoding="utf-8")

    def section(self):
        text = self.read("docs/ARCHITECTURE.md")
        return text[text.index("## 4-8. "):text.index("## 5. 상태·멱등성·동시성")]

    def test_the_architecture_section_describes_each_fixed_behaviour(self):
        section = self.section()
        for needle in ("photo_url_ok", "safe_download_url", "`_api_request`", "add_unredirected_header", "POOL_LOOKUP_MAX_TOTAL", "⚠️ 확인 필요", "이름이 진짜",
                       "독립 검증", "이스케이프·길이 제한은 링크·코드 주입을 막을 뿐"):
            self.assertIn(needle, section, needle)

    def test_the_architecture_section_is_honest_about_the_retry_every_tick_and_the_low_items(self):
        section = self.section()
        for needle in ("매시 17분·47분", "하루 최대 약 30번", "운영자가 정할 일", "재시도 간격을 늘릴지", "실행 요약에는 '사진 문제'라는 말이 없고", "코드 펜스", "`$$…$$`", "파이썬 3.10", "3.12",
                       "`ixid` 허용 문자", "주소만 바꾸고 옛 줄을 그대로 둔 PR"):
            self.assertIn(needle, section, needle)

    def test_the_security_rule_says_the_same_for_chance_and_names_the_new_tests(self):
        row = next(line for line in self.read("docs/SECURITY_GUARDRAILS.md").splitlines() if line.startswith("| G-C7 |"))
        for needle in ("검색·고정 목록 조회·사용 알림 세 요청 모두 키를 리다이렉트를 따라가지 않는 머리글로만", "photo_url_ok", "safe_download_url", "⚠️ 확인 필요", "이름이 진짜", "POOL_LOOKUP_MAX_TOTAL",
                       "tests/test_unsplash_credit_fix.py", "tests/test_chance_credit_fix.py", "tests/test_edits_credit_fix.py", "처음 판에서는"):
            self.assertIn(needle, row, needle)

    def test_the_operator_guides_tell_what_changed(self):
        guide = self.read("docs/ACTIONS_GUIDE.md")
        for needle in ("재시도 한계", "하루 최대 약 30번", "사진이 실패했을 때 재시도 간격을 늘릴지", "한 번에 허용한 횟수에 닿아", "작가 출처 줄이 이전 글과 달라졌을 때도 ⚠️"):
            self.assertIn(needle, guide, needle)
        edits = self.read("docs/ISSUE_EDITS.md")
        for needle in ("작가 이름 칸의 평문", "⚠️ 확인 필요", "이름이 진짜", "주소만 바꾸고 옛 줄을 그대로 둔 PR"):
            self.assertIn(needle, edits, needle)
        work = self.read("인수인계/작업내용.md")
        for needle in ("수정분 재검증", "재시도 간격을 늘릴지", "1차 독립 검증"):
            self.assertIn(needle, work, needle)
        self.assertIn("1차 독립 검증", self.read("HANDLER.md"))


class _Reply:
    """urlopen 이 돌려주는 응답 흉내(상태 번호·머리글·본문) — 진짜 urllib 의 오류·리다이렉트 처리를 거치게 한다."""

    def __init__(self, code, headers=None, body=b""):
        self.code = self.status = code
        self.msg = "OK" if code == 200 else "Found"
        self.headers = headers if headers is not None else email.message.Message()
        self._body = body

    def info(self):
        return self.headers

    def geturl(self):
        return ""

    def read(self, amt=None):
        return self._body if amt is None else self._body[:amt]

    def close(self):
        return None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _FakeHttps(urllib.request.HTTPSHandler):
    """api.unsplash.com 으로 가는 요청에는 낯선 호스트(evil.example)로 보내는 302 를, 그 밖의 호스트에는 `{"results": []}` 200 을 돌려준다. 받은 요청은 모두 seen 에 적는다."""

    def __init__(self, seen):
        super().__init__()
        self.seen = seen

    def https_open(self, req):
        self.seen.append({"host": req.host, "url": req.full_url, "headers": {name.lower(): value for name, value in req.header_items()}})
        if req.host == "api.unsplash.com":
            headers = email.message.Message()
            headers["Location"] = "https://evil.example/steal"
            return _Reply(302, headers)
        return _Reply(200, body=b'{"results": []}')


if __name__ == "__main__":
    unittest.main()
