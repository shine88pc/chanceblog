"""Chance(generator.py)의 Unsplash 사진 처리 시험 — ① 사진 주소의 ixid 를 남긴다 ② 글에 작가·Unsplash 출처 줄(utm 링크)을 넣는다 ③ 출처를 알 수 없는 사진은 쓰지 않는다. 네트워크 없이 가짜 Unsplash 로 돈다.

구성
  1) 검색 응답 읽기: 주소(ixid)·작가 출처·사용 알림 주소의 기록, 틀린 값 버리기, 낡은 기록 지우기, 이상한 응답 견디기, 키 없음·연습 실행.
  2) 사진 고르기(pick_images): 출처 없는 사진 건너뛰기, 고정 목록 대체(조회 성공·실패·연속 실패 중단·키 없음).
  3) 새 글 만들기(validate_post_data): 이미지 줄 바로 다음 출처 줄·KR/EN 같은 문구·모델이 흉내 낸 줄 덮어쓰기·설명에 섞이지 않음.
  4) 전체 흐름(generate_blog_posts): ixid 주소·출처 줄·사용 알림·이력 모양 그대로·머리말 검사 통과, 출처 없는 사진뿐이면 글을 저장하지 않고 멈춤.
  5) 기존 글 이미지 교체(fix_images·apply_image): 옛 줄 교체·멱등.
"""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import _bootstrap
import generator as g
from chance_credit_helpers import FAKE_KEY, PHOTO_RAW, ChanceBase, FakeApi, http_error, pool_photo_item
from main_image_helpers import FakeResponse, photo_item, results
from pipeline import unsplash_credit as uc
from test_generator_front_matter import legacy_validate_post_data
from test_generator_slots import at, candidate, long_post, run_captured

LINK = "https://www.reuters.com/a"
UTM = "utm_source=chanceblog&utm_medium=referral"
ALICE = photo_item("Aaa111bbb22", raw=PHOTO_RAW.format(pid="aaa111bbb22"), name="Alice Kim", username="alicekim")
BOB = photo_item("Ccc333ddd44", raw=PHOTO_RAW.format(pid="ccc333ddd44"), name="Bob Lee", username="boblee")
ALICE_URL = "https://images.unsplash.com/photo-1500000000000-aaa111bbb22?ixid=M3wxfDB8&auto=format&fit=crop&w=1000&q=80"
BOB_URL = "https://images.unsplash.com/photo-1500000000000-ccc333ddd44?ixid=M3wxfDB8&auto=format&fit=crop&w=1000&q=80"
ALICE_LINE = f"*Photo by [Alice Kim](https://unsplash.com/@alicekim?{UTM}) on [Unsplash](https://unsplash.com/?{UTM})*"
BOB_LINE = f"*Photo by [Bob Lee](https://unsplash.com/@boblee?{UTM}) on [Unsplash](https://unsplash.com/?{UTM})*"
POOL_FIRST, POOL_SECOND = g.IMAGE_POOL[0], g.IMAGE_POOL[1]


def lookup_id(pool_url):
    return "photo-" + pool_url.split("/photo-")[1].split("?")[0]


class SearchTest(ChanceBase):
    def search(self, *items, query="coffee", headers=None):
        self.use(FakeApi(searches=[results(*items)], headers=headers))
        return self.call(g.search_unsplash, query)

    def test_the_address_keeps_the_ixid_in_front_of_the_size_parameters(self):
        urls, _out = self.search(ALICE)
        self.assertEqual(urls, [ALICE_URL])

    def test_the_other_tracking_parameters_do_not_come_along(self):
        urls, _out = self.search(photo_item("Aaa111bbb22", raw="https://images.unsplash.com/photo-1-aaa?ixlib=rb-4.0.3&ixid=M3w&utm_source=x"))
        self.assertEqual(urls, ["https://images.unsplash.com/photo-1-aaa?ixid=M3w&auto=format&fit=crop&w=1000&q=80"])

    def test_the_author_the_download_address_and_the_key_of_the_photo_are_recorded(self):
        self.search(ALICE)
        key = g.image_key(ALICE_URL)
        self.assertEqual(key, "images.unsplash.com/photo-1500000000000-aaa111bbb22")
        self.assertEqual(g._credits[key], ("Alice Kim", "https://unsplash.com/@alicekim"))
        self.assertEqual(g._download_locations[key], "https://api.unsplash.com/photos/Aaa111bbb22/download?ixid=M3wxfDB8")
        self.assertEqual(g.credit_line_for(ALICE_URL), ALICE_LINE)

    def test_the_duplicate_key_does_not_depend_on_the_ixid(self):
        self.assertEqual(g.image_key(ALICE_URL), g.image_key(ALICE_URL.replace("?ixid=M3wxfDB8&", "?")))
        self.assertEqual(g.image_key(ALICE_URL), g.image_key(ALICE_URL.replace("M3wxfDB8", "OTHER")))

    def test_an_address_without_a_valid_ixid_is_still_returned_in_the_old_form(self):
        old = "https://images.unsplash.com/photo-1500000000000-aaa111bbb22?auto=format&fit=crop&w=1000&q=80"
        for raw in ("https://images.unsplash.com/photo-1500000000000-aaa111bbb22", "https://images.unsplash.com/photo-1500000000000-aaa111bbb22?ixlib=rb-4.0.3",
                    "https://images.unsplash.com/photo-1500000000000-aaa111bbb22?ixid=a%20b", "https://images.unsplash.com/photo-1500000000000-aaa111bbb22?ixid=a&ixid=b",
                    "https://images.unsplash.com/photo-1500000000000-aaa111bbb22?ixid=" + "A" * 201):
            urls, out = self.search(photo_item("Aaa111bbb22", raw=raw, name="Alice Kim", username="alicekim"))
            self.assertEqual(urls, [old], raw)
            self.assertIn("[IXID] 사진 1장은 주소에 올바른 ixid 가 없어 ixid 없이 씁니다", out)
            self.assertIn("Alice Kim", g._credits[g.image_key(old)][0])           # ixid 가 없어도 사진도 출처도 쓴다(글 발행을 막지 않는다)

    def test_no_note_is_printed_when_every_address_has_its_ixid(self):
        _urls, out = self.search(ALICE, BOB)
        self.assertNotIn("[IXID]", out)

    def test_photos_without_a_usable_author_are_returned_but_have_no_credit(self):
        bad_users = ({"name": "x"}, {"name": "x", "links": {"html": "https://evil.example/@x"}}, {"links": {"html": "https://unsplash.com/@x"}}, "x", None,
                     {"name": "\u200b", "links": {"html": "https://unsplash.com/@x"}}, {"name": "x", "links": {"html": "http://unsplash.com/@x"}})
        for user in bad_users:
            item = photo_item("Aaa111bbb22", raw=PHOTO_RAW.format(pid="aaa111bbb22"))
            item["user"] = user
            urls, _out = self.search(item)
            self.assertEqual(urls, [ALICE_URL], repr(user))
            self.assertNotIn(g.image_key(ALICE_URL), g._credits, repr(user))
            self.assertEqual(g.credit_line_for(ALICE_URL), "")

    def test_a_stale_credit_of_an_earlier_response_is_removed_when_the_new_one_has_none(self):
        self.search(ALICE)
        self.assertIn(g.image_key(ALICE_URL), g._credits)
        item = photo_item("Aaa111bbb22", raw=PHOTO_RAW.format(pid="aaa111bbb22"), remove=("user",))
        self.search(item)
        self.assertNotIn(g.image_key(ALICE_URL), g._credits)

    def test_a_newer_response_replaces_the_credit_of_the_same_photo(self):
        self.search(ALICE)
        self.search(photo_item("Aaa111bbb22", raw=PHOTO_RAW.format(pid="aaa111bbb22"), name="New Name", username="newname"))
        self.assertEqual(g._credits[g.image_key(ALICE_URL)], ("New Name", "https://unsplash.com/@newname"))

    def test_an_author_name_is_cleaned_before_it_is_kept(self):
        self.search(photo_item("Aaa111bbb22", raw=PHOTO_RAW.format(pid="aaa111bbb22"), name="Al\u200bice\n {{ x }}[k]", username="alicekim"))
        self.assertEqual(g._credits[g.image_key(ALICE_URL)][0], "Alice x [k]")
        line = g.credit_line_for(ALICE_URL)
        self.assertTrue(uc.is_credit_line(line))
        self.assertIn("Alice x " + chr(92) + "[k" + chr(92) + "]", line)

    def test_odd_items_do_not_break_the_search(self):
        junk = [None, 5, "x", [], {}, {"urls": None}, {"urls": "x"}, {"urls": {}}, {"urls": {"raw": None}}, {"urls": {"raw": ""}}, {"urls": {"raw": 5}}, {"urls": {"raw": ["x"]}}]
        urls, _out = self.search(*junk, ALICE)
        self.assertEqual(urls, [ALICE_URL])

    def test_an_address_that_cannot_be_read_is_skipped_instead_of_stopping_the_search(self):
        broken = photo_item("Zzz999yyy88", raw="https://[::1/photo-1")
        urls, _out = self.search(broken, ALICE)
        self.assertEqual(urls, [ALICE_URL])

    def test_a_non_dict_links_or_user_block_is_survived(self):
        item = photo_item("Aaa111bbb22", raw=PHOTO_RAW.format(pid="aaa111bbb22"))
        item["links"] = "x"
        urls, _out = self.search(item)
        self.assertEqual(urls, [ALICE_URL])
        self.assertNotIn(g.image_key(ALICE_URL), g._download_locations)

    def test_the_key_goes_in_the_header_and_never_in_the_output(self):
        api = self.use(FakeApi(searches=[results(ALICE)]))
        _urls, out = self.call(g.search_unsplash, "coffee")
        self.assertEqual(api.calls[0]["headers"]["Authorization"], f"Client-ID {FAKE_KEY}")
        self.assertNotIn(FAKE_KEY, out)
        self.assertNotIn(FAKE_KEY, api.calls[0]["url"])

    def test_http_errors_and_network_failures_still_give_an_empty_list(self):
        for failure in (http_error(403), http_error(429), OSError("연결 실패")):
            self.use(FakeApi(searches=[failure]))
            urls, _out = self.call(g.search_unsplash, "coffee")
            self.assertEqual(urls, [])

    def test_a_practice_run_without_a_key_gets_fake_photos_with_fake_credits(self):
        self.use(FakeApi(searches=[results(ALICE)]))
        with mock.patch.multiple(g, STUB_UNSPLASH=True, DRY_RUN=True):
            urls, out = self.call(g.search_unsplash, "coffee")
        self.assertEqual(len(urls), 3)
        for url in urls:
            self.assertRegex(url, r"^https://images\.unsplash\.com/photo-dry\d+[0-2]\?auto=format&fit=crop&w=1000&q=80$")      # 가짜 주소의 모양은 그대로(ixid 없음)
            line = g.credit_line_for(url)
            self.assertTrue(uc.is_credit_line(line), url)
            self.assertIn("Stub Photographer", line)
        self.assertEqual(self.api.calls, [])
        self.assertIn("[DRY_RUN] Unsplash 스텁 검색", out)

    def test_without_a_key_and_not_practising_nothing_is_searched(self):
        api = self.use(FakeApi(searches=[results(ALICE)]))
        with mock.patch.multiple(g, STUB_UNSPLASH=True, DRY_RUN=False):
            urls, out = self.call(g.search_unsplash, "coffee")
        self.assertEqual(urls, [])
        self.assertEqual(api.calls, [])
        self.assertIn("UNSPLASH_ACCESS_KEY 없음: 검색 생략", out)


class PickImagesTest(ChanceBase):
    def test_a_photo_without_a_credit_is_never_picked_and_the_next_one_is(self):
        no_credit = photo_item("Zzz999yyy88", raw=PHOTO_RAW.format(pid="zzz999yyy88"), remove=("user",))
        self.use(FakeApi(searches=[results(no_credit, BOB)]))
        picked, out = self.call(g.pick_images, ["coffee"], set(), 1)
        self.assertEqual(picked, [BOB_URL])
        self.assertNotIn("photo-1500000000000-zzz999yyy88", " ".join(picked))

    def test_when_no_photo_has_a_credit_nothing_is_picked_and_the_count_is_noted(self):
        items = [photo_item(f"Zzz99{n}yyy88", raw=PHOTO_RAW.format(pid=f"zzz99{n}yyy88"), remove=("user",)) for n in range(3)]
        self.use(FakeApi(searches=[results(*items)]))
        picked, out = self.call(g.pick_images, ["coffee", "tea"], set(), 1)
        self.assertEqual(picked, [])
        self.assertIn("[참고] 작가 출처 정보가 없어 쓰지 않은 사진: 6장", out)         # 검색어 두 개 × 3장

    def test_the_used_photos_are_skipped_by_host_and_path_even_when_the_ixid_differs(self):
        self.use(FakeApi(searches=[results(ALICE, BOB)]))
        used = {g.image_key(ALICE_URL)}
        picked, _out = self.call(g.pick_images, ["coffee"], used, 2)
        self.assertEqual(picked, [BOB_URL])
        self.assertIn(g.image_key(BOB_URL), used)

    def test_two_photos_are_picked_from_one_search_in_order(self):
        api = self.use(FakeApi(searches=[results(ALICE, BOB)]))
        picked, _out = self.call(g.pick_images, ["coffee", "tea"], set(), 2)
        self.assertEqual(picked, [ALICE_URL, BOB_URL])
        self.assertEqual(api.searched, ["coffee"])                 # 두 장을 얻으면 더 검색하지 않는다
        self.assertEqual(api.lookups, [])                          # 고정 목록 조회도 없다

    def test_the_fixed_list_is_not_used_when_the_search_is_enough_or_pool_is_off(self):
        api = self.use(FakeApi(searches=[results()]))
        picked, _out = self.call(g.pick_images, ["coffee"], set(), 1, allow_pool=False)
        self.assertEqual(picked, [])
        self.assertEqual(api.lookups, [])


class PoolLookupTest(ChanceBase):
    def photos_for(self, *pool_urls, **kwargs):
        return {lookup_id(url): pool_photo_item(url, **kwargs) for url in pool_urls}

    def test_a_pool_photo_is_used_only_after_a_successful_lookup_that_gives_ixid_author_and_download(self):
        api = self.use(FakeApi(searches=[results()], photos=self.photos_for(POOL_FIRST, POOL_SECOND)))
        picked, out = self.call(g.pick_images, ["coffee"], set(), 2, allow_pool=True)
        self.assertEqual(len(picked), 2)
        for url, pool in zip(picked, (POOL_FIRST, POOL_SECOND)):
            self.assertEqual(g.image_key(url), g.image_key(pool))
            self.assertIn("?ixid=POOL", url)                                         # 조회가 알려 준 ixid 를 남긴다
            self.assertTrue(url.endswith("&auto=format&fit=crop&w=1000&q=80"))
            self.assertTrue(uc.is_credit_line(g.credit_line_for(url)))
            self.assertIn("Pool Author", g.credit_line_for(url))
            self.assertIn(g.image_key(url), g._download_locations)
        self.assertEqual(api.lookups, [f"/photos/{lookup_id(POOL_FIRST)}", f"/photos/{lookup_id(POOL_SECOND)}"])   # 사진 하나당 한 번
        self.assertIn("검색 결과 없음, 폴백 풀 이미지 사용", out)

    def test_the_lookup_uses_the_same_key_header_and_keeps_it_off_redirects(self):
        api = self.use(FakeApi(searches=[results()], photos=self.photos_for(POOL_FIRST)))
        _picked, out = self.call(g.pick_images, [], set(), 1, allow_pool=True)
        call = next(c for c in api.calls if c["path"].startswith("/photos/") and not c["path"].endswith("/download"))
        self.assertEqual((call["host"], call["method"]), ("api.unsplash.com", "GET"))
        self.assertEqual(call["unredirected"]["Authorization"], f"Client-ID {FAKE_KEY}")
        self.assertNotIn("Authorization", call["redirectable"])                       # 리다이렉트를 따라가도 키가 다른 호스트로 가지 않는다
        self.assertEqual(call["headers"]["Accept-version"], "v1")
        self.assertNotIn(FAKE_KEY, out)

    def test_both_pool_photos_are_marked_used_by_the_lookup_key_and_the_pool_key(self):
        other = pool_photo_item(POOL_FIRST)
        other["urls"]["raw"] = "https://images.unsplash.com/photo-9999999999999-zzzzzzzzzzzz?ixid=M3wxfDB8"      # 조회가 알려 준 주소의 키가 고정 주소의 키와 다르다
        self.use(FakeApi(searches=[results()], photos={lookup_id(POOL_FIRST): other}))
        used = set()
        picked, _out = self.call(g.pick_images, [], used, 1, allow_pool=True)
        self.assertEqual(len(picked), 1)
        self.assertIn("photo-9999999999999-zzzzzzzzzzzz", picked[0])
        self.assertIn(g.image_key(picked[0]), used)
        self.assertIn(g.image_key(POOL_FIRST), used)             # 다음 실행·다음 글이 고정 주소로 같은 사진을 또 조회하지 않는다

    def test_used_pool_photos_are_skipped_without_a_call(self):
        api = self.use(FakeApi(searches=[results()], photos=self.photos_for(POOL_SECOND)))
        picked, _out = self.call(g.pick_images, [], {g.image_key(POOL_FIRST)}, 1, allow_pool=True)
        self.assertEqual(api.lookups, [f"/photos/{lookup_id(POOL_SECOND)}"])
        self.assertEqual(g.image_key(picked[0]), g.image_key(POOL_SECOND))

    def test_a_failed_lookup_skips_that_photo_and_the_next_candidate_is_tried(self):
        api = self.use(FakeApi(searches=[results()], photos={lookup_id(POOL_SECOND): pool_photo_item(POOL_SECOND)}))     # 첫 번호는 404
        picked, out = self.call(g.pick_images, [], set(), 1, allow_pool=True)
        self.assertEqual(g.image_key(picked[0]), g.image_key(POOL_SECOND))
        self.assertEqual(len(api.lookups), 2)
        self.assertIn("Unsplash API 오류 404 (사진 조회)", out)

    def test_three_failures_in_a_row_stop_the_lookups_and_nothing_is_picked(self):
        api = self.use(FakeApi(searches=[results()], photos={}))
        picked, out = self.call(g.pick_images, [], set(), 2, allow_pool=True)
        self.assertEqual(picked, [])
        self.assertEqual(len(api.lookups), g.POOL_LOOKUP_MAX_FAILS)
        self.assertEqual(g.POOL_LOOKUP_MAX_FAILS, 3)
        self.assertIn("고정 목록 사진 조회가 연달아 실패해 더 시도하지 않습니다", out)

    def test_failures_that_are_not_in_a_row_do_not_stop_the_lookups(self):
        pool = g.IMAGE_POOL
        photos = {lookup_id(pool[2]): pool_photo_item(pool[2]), lookup_id(pool[5]): pool_photo_item(pool[5])}          # 0,1 실패 → 2 성공 → 3,4 실패 → 5 성공
        api = self.use(FakeApi(searches=[results()], photos=photos))
        picked, _out = self.call(g.pick_images, [], set(), 2, allow_pool=True)
        self.assertEqual([g.image_key(u) for u in picked], [g.image_key(pool[2]), g.image_key(pool[5])])
        self.assertEqual(len(api.lookups), 6)

    def test_a_lookup_answer_that_cannot_be_trusted_counts_as_a_failure(self):
        good = pool_photo_item(POOL_FIRST)
        no_user = pool_photo_item(POOL_FIRST)
        no_user.pop("user")
        foreign = pool_photo_item(POOL_FIRST)
        foreign["urls"]["raw"] = "https://evil.example/photo-1500000000000-x?ixid=M3w"
        not_photo_path = pool_photo_item(POOL_FIRST)
        not_photo_path["urls"]["raw"] = "https://images.unsplash.com/uploads/1?ixid=M3w"
        no_raw = pool_photo_item(POOL_FIRST)
        no_raw["urls"] = {}
        for label, reply in (("작가 정보 없음", no_user), ("다른 호스트", foreign), ("photo- 경로 아님", not_photo_path), ("raw 없음", no_raw), ("목록 응답", [good]), ("문자열", "x"),
                             ("깨진 JSON", FakeResponse(b"{nope")), ("너무 큰 응답", FakeResponse(json.dumps(good).encode("utf-8") + b" " * 1_000_001)), ("연결 실패", OSError("연결 실패")), ("403", http_error(403)), ("429", http_error(429)), ("500", http_error(500))):
            with self.subTest(label):
                self.use(FakeApi(searches=[results()], photos={lookup_id(POOL_FIRST): reply}))
                value, _out = self.call(g.fetch_pool_photo, POOL_FIRST)
                self.assertIsNone(value)
                self.assertNotIn(g.image_key(POOL_FIRST), g._credits)

    def test_a_lookup_that_returns_a_photo_already_used_under_its_own_key_is_skipped(self):
        other = pool_photo_item(POOL_FIRST)
        other["urls"]["raw"] = "https://images.unsplash.com/photo-9999999999999-zzzzzzzzzzzz?ixid=M3wxfDB8"       # 조회가 알려 준 주소의 키가 고정 주소의 키와 다르다
        used = {"images.unsplash.com/photo-9999999999999-zzzzzzzzzzzz"}
        self.use(FakeApi(searches=[results()], photos={lookup_id(POOL_FIRST): other, lookup_id(POOL_SECOND): pool_photo_item(POOL_SECOND)}))
        picked, _out = self.call(g.pick_images, [], used, 1, allow_pool=True)
        self.assertEqual([g.image_key(url) for url in picked], [g.image_key(POOL_SECOND)])

    def test_the_rate_headers_of_a_lookup_are_recorded(self):
        self.use(FakeApi(searches=[results()], photos=self.photos_for(POOL_FIRST), headers={"X-Ratelimit-Remaining": "41", "X-Ratelimit-Limit": "50"}))
        self.call(g.pick_images, [], set(), 1, allow_pool=True)
        self.assertEqual(g.UNSPLASH_RATE, {"remaining": 41, "limit": 50})

    def test_without_a_key_the_fixed_list_cannot_be_used_and_no_network_is_touched(self):
        api = self.use(FakeApi(searches=[results(ALICE)], photos=self.photos_for(POOL_FIRST, POOL_SECOND)))      # 응답을 줄 수 있어도 키가 없으면 부르지 않는다
        for flags in (dict(STUB_UNSPLASH=True, DRY_RUN=False), dict(STUB_UNSPLASH=True, DRY_RUN=True)):
            with mock.patch.multiple(g, **flags):
                self.assertIsNone(g.fetch_pool_photo(POOL_FIRST))
        with mock.patch.multiple(g, STUB_UNSPLASH=True, DRY_RUN=False):
            picked, out = self.call(g.pick_images, ["coffee"], set(), 2, allow_pool=True)
        self.assertEqual(picked, [])
        self.assertEqual(api.calls, [])
        self.assertIn("고정 목록 사진 조회가 연달아 실패해", out)

    def test_a_pool_address_that_is_not_a_photo_number_is_never_looked_up(self):
        api = self.use(FakeApi(searches=[results()]))
        for url in ("https://images.unsplash.com/photo-bad", "https://images.unsplash.com/other", "https://images.unsplash.com/photo-../x?w=1", "", None):
            self.assertIsNone(g.fetch_pool_photo(url), repr(url))
        self.assertEqual(api.calls, [])


class ValidatePostDataTest(ChanceBase):
    BODY_LINK = LINK

    def data(self, **replace):
        data = long_post("주제", self.BODY_LINK)
        for key, value in replace.items():
            data[key] = value
        return data

    def register(self, url, line_name="Alice Kim", username="alicekim"):
        g._credits[g.image_key(url)] = (line_name, f"https://unsplash.com/@{username}")

    def validate(self, data, kr=ALICE_URL, en=BOB_URL):
        return g.validate_post_data(data, kr, en, verified_source_url=self.BODY_LINK)

    def lines(self, content):
        return content.split("\n")

    def test_the_credit_line_is_the_very_next_line_after_the_thumbnail_in_both_languages(self):
        self.register(ALICE_URL)
        self.register(BOB_URL, "Bob Lee", "boblee")
        out = self.validate(self.data())
        for key, image, line in (("kr_content", ALICE_URL, ALICE_LINE), ("en_content", BOB_URL, BOB_LINE)):
            lines = self.lines(out[key])
            at_thumbnail = lines.index(f"![Thumbnail]({image})")
            self.assertEqual(lines[at_thumbnail + 1], line, key)
            self.assertEqual(out[key].count("Photo by ["), 1)
            self.assertTrue(out[key].endswith("\n") and not out[key].endswith("\n\n"))

    def test_the_wording_is_the_same_english_phrase_in_korean_and_english_posts(self):
        self.register(ALICE_URL)
        self.register(BOB_URL)
        out = self.validate(self.data())
        kr_line = next(line for line in self.lines(out["kr_content"]) if uc.is_credit_line(line))
        en_line = next(line for line in self.lines(out["en_content"]) if uc.is_credit_line(line))
        self.assertEqual(kr_line, en_line)
        self.assertTrue(kr_line.startswith("*Photo by ["))
        self.assertNotRegex(kr_line, r"[가-힣]")

    def test_the_thumbnail_line_itself_is_unchanged(self):
        self.register(ALICE_URL)
        out = self.validate(self.data())
        self.assertEqual(self.lines(out["kr_content"]).count(f"![Thumbnail]({ALICE_URL})"), 1)

    def test_an_image_the_model_wrote_is_replaced_in_place_and_gets_the_credit_after_it(self):
        self.register(ALICE_URL)
        data = self.data()
        data["kr_content"] = data["kr_content"].replace("\n\n근거는", "\n\n![x](https://images.unsplash.com/photo-9?w=1)\n\n근거는", 1)
        out = self.validate(data)
        lines = self.lines(out["kr_content"])
        at_thumbnail = lines.index(f"![Thumbnail]({ALICE_URL})")
        self.assertEqual(lines[at_thumbnail + 1], ALICE_LINE)
        self.assertNotIn("photo-9", out["kr_content"])

    def test_a_credit_line_the_model_wrote_is_overwritten_by_ours(self):
        self.register(ALICE_URL)
        forged = uc.credit_markdown("Evil Name", "https://unsplash.com/@evil")
        data = self.data()
        data["kr_content"] = data["kr_content"].replace("\n\n근거는", f"\n\n{forged}\n\n근거는", 1) + f"\n{forged}\n"
        data["en_content"] = data["en_content"].replace("\n\nSee [source]", f"\n\n{forged}\n\nSee [source]", 1)
        out = self.validate(data)
        for key in ("kr_content", "en_content"):
            self.assertNotIn("Evil Name", out[key], key)
            self.assertNotIn("@evil", out[key], key)
        self.assertEqual(out["kr_content"].count(ALICE_LINE), 1)
        self.assertEqual(self.lines(out["kr_content"])[self.lines(out["kr_content"]).index(f"![Thumbnail]({ALICE_URL})") + 1], ALICE_LINE)

    def test_forged_lines_are_removed_even_when_the_photo_has_no_known_credit(self):
        forged = uc.credit_markdown("Evil Name", "https://unsplash.com/@evil")
        data = self.data()
        data["kr_content"] = data["kr_content"].replace("\n\n근거는", f"\n\n{forged}\n\n근거는", 1)
        out = self.validate(data)                                    # 기록부에 사진이 없다 → 줄을 넣지 못한다
        self.assertNotIn("Photo by [", out["kr_content"])

    def test_a_photo_with_no_known_credit_gets_no_line_and_the_output_is_byte_identical_to_the_old_one(self):
        for kr, en in ((ALICE_URL, BOB_URL), ("https://img.test/kr.jpg", "https://img.test/en.jpg"), ("https://example.invalid/kr.jpg", "https://example.invalid/en.jpg")):
            new = g.validate_post_data(self.data(), kr, en, verified_source_url=self.BODY_LINK)
            old = legacy_validate_post_data(self.data(), kr, en, verified_source_url=self.BODY_LINK)
            self.assertEqual((new["kr_content"], new["en_content"]), (old["kr_content"], old["en_content"]))
            self.assertNotIn("Photo by [", new["kr_content"])
        self.assertTrue(new["kr_content"].rstrip().endswith(f"![Thumbnail]({kr})"))

    def test_placeholder_images_of_the_candidate_check_pass_without_a_credit(self):
        out = g.validate_post_data(self.data(), "https://example.invalid/kr.jpg", "https://example.invalid/en.jpg", verified_source_url=self.BODY_LINK)
        g.check_final_front_matter(out, {"link": self.BODY_LINK, "source": "Reuters", "publisher_domain": "www.reuters.com", "title": "t"})
        self.assertNotIn("Photo by [", out["kr_content"])

    def test_the_final_post_passes_the_front_matter_check_with_the_credit_line(self):
        self.register(ALICE_URL)
        self.register(BOB_URL, "Bob Lee", "boblee")
        out = self.validate(self.data())
        source = {"link": self.BODY_LINK, "source": "Reuters", "publisher_domain": "www.reuters.com", "title": "원문 기사"}
        for key in ("kr_content", "en_content"):
            full = g.add_discovery_metadata(out[key], dict(source))
            self.assertEqual(g.front_matter_problems(full, source), [], key)

    def test_the_credit_line_never_becomes_the_description(self):
        long_name = "N" * 60
        line = uc.credit_markdown(long_name, "https://unsplash.com/@n")
        self.assertGreaterEqual(len(line.replace("*", "")), 60)
        content = f"---\ntitle: x\n---\n\n![Thumbnail](https://images.unsplash.com/photo-1)\n{line}\n\n" + ("본문 문장입니다. " * 12) + "\n"
        description = g._description_from_markdown(content)
        self.assertTrue(description.startswith("본문 문장입니다."), description)
        self.assertNotIn("Photo by", description)


class GenerationFlowTest(ChanceBase):
    """generate_blog_posts 전체 흐름: 가짜 기사·가짜 Gemini·가짜 Unsplash·임시 폴더."""

    def setUp(self):
        super().setUp()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        for patcher in (mock.patch.multiple(g, STUB_GEMINI=False, FIX_IMAGES=False, POSTS_DIR=self.root / "_posts", HISTORY_FILE=self.root / "history.json"),
                        mock.patch.object(g, "now_kst", return_value=at(10, 12)),
                        mock.patch.object(g, "get_client", side_effect=AssertionError("가짜 Gemini 만 쓴다"))):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.item = candidate("후보 기사", LINK)

    def generate(self, api=None, item=None):
        if api is not None:
            self.use(api)
        item = item or self.item

        def fake_fetch(editorial_lane=None, stats=None, deadline=None, clock=None):
            if stats is not None:
                stats.setdefault("sources", []).append({"name": "x", "fetched": 1, "kept": 1, "drops": {}})
            return [dict(item)]

        def fake_gemini(prompt):
            return SimpleNamespace(text=json.dumps(long_post(item["title"], item["link"]), ensure_ascii=False))

        report = {}
        with mock.patch.object(g, "fetch_news_items", fake_fetch), mock.patch.object(g, "call_gemini_with_fallback", fake_gemini):
            try:
                value, out = run_captured(g.generate_blog_posts, slot=9, allow_auto_topic=False, report=report)
            except RuntimeError as exc:
                value, out = exc, ""
        return value, report, out

    def posts(self):
        return {path.name: path.read_text(encoding="utf-8") for path in sorted((self.root / "_posts").rglob("*.md"))}

    def test_a_new_pair_gets_ixid_addresses_credit_lines_and_download_notices(self):
        api = FakeApi(searches=[results(ALICE, BOB)])
        value, report, out = self.generate(api)
        self.assertIsNotNone(value)
        self.assertEqual(report["outcome"], "PUBLISHED")
        posts = self.posts()
        self.assertEqual(len(posts), 2)
        kr = next(text for name, text in posts.items() if "-KR-" in name)
        en = next(text for name, text in posts.items() if "-EN-" in name)
        for text, image, line in ((kr, ALICE_URL, ALICE_LINE), (en, BOB_URL, BOB_LINE)):
            self.assertIn(f'image: "{image}"\n', text)                      # 머리말 image: ixid 가 든 주소
            lines = text.split("\n")
            self.assertEqual(lines[lines.index(f"![Thumbnail]({image})") + 1], line)
            self.assertEqual(g.front_matter_problems(text, self.item), [])
        self.assertEqual(api.downloads, ["/photos/Aaa111bbb22/download", "/photos/Ccc333ddd44/download"])      # 쓰기로 한 두 장에만 사용 알림
        self.assertNotIn(FAKE_KEY, out)

    def test_the_history_entry_keeps_its_shape_and_holds_the_addresses(self):
        value, _report, _out = self.generate(FakeApi(searches=[results(ALICE, BOB)]))
        self.assertIsNotNone(value)
        history = json.loads((self.root / "history.json").read_text(encoding="utf-8"))
        self.assertEqual(len(history), 1)
        self.assertEqual(sorted(history[0]), sorted(["date", "topic", "kr_title", "en_title", "kr_image", "en_image", "slot", "lane", "source", "source_url"]))
        self.assertEqual((history[0]["kr_image"], history[0]["en_image"]), (ALICE_URL, BOB_URL))
        self.assertFalse(any("Photo by" in str(value) for value in history[0].values()))      # 출처는 글에만 있다 — 이력에 새 칸이 없다

    def test_a_second_run_does_not_pick_the_same_photos_again(self):
        self.generate(FakeApi(searches=[results(ALICE, BOB)]))
        names = set(self.posts())
        other = candidate("Space telescope sends back the first pictures of a distant galaxy cluster", "https://www.reuters.com/b")
        with mock.patch.object(g, "now_kst", return_value=at(18, 5)):
            value, _report, _out = self.generate(FakeApi(searches=[results(ALICE, BOB)]), item=other)
        self.assertIsInstance(value, RuntimeError)                         # 검색이 같은 두 장뿐이라 쓸 사진이 없다 → 고정 목록 조회도 실패 → 저장하지 않고 멈춘다
        self.assertEqual(set(self.posts()), names)

    def test_one_search_photo_and_one_pool_photo_make_a_pair_with_both_credits(self):
        photos = {lookup_id(POOL_FIRST): pool_photo_item(POOL_FIRST, name="Pool Author")}
        api = FakeApi(searches=[results(ALICE)], photos=photos)
        value, report, out = self.generate(api)
        self.assertIsNotNone(value)
        kr = next(text for name, text in self.posts().items() if "-KR-" in name)
        en = next(text for name, text in self.posts().items() if "-EN-" in name)
        self.assertIn(ALICE_LINE, kr)
        self.assertIn("Photo by [Pool Author]", en)
        self.assertIn("?ixid=POOL", en)
        self.assertEqual(len(api.lookups), 1)
        self.assertEqual(len(api.downloads), 2)                            # 대체 사진도 쓰기로 했으니 사용 알림을 부른다

    def test_when_nothing_with_a_credit_can_be_found_no_post_and_no_history_are_written(self):
        no_credit = [photo_item(f"Zzz99{n}yyy88", raw=PHOTO_RAW.format(pid=f"zzz99{n}yyy88"), remove=("user",)) for n in range(4)]
        api = FakeApi(searches=[results(*no_credit)], photos={})
        value, report, _out = self.generate(api)
        self.assertIsInstance(value, RuntimeError)
        self.assertIn("대표 이미지를 2개 확보하지 못했습니다", str(value))
        self.assertEqual(self.posts(), {})
        self.assertFalse((self.root / "history.json").exists())
        self.assertEqual(api.downloads, [])

    def test_one_credited_photo_and_failing_lookups_also_stop_without_saving(self):
        api = FakeApi(searches=[results(ALICE)], photos={})
        value, _report, _out = self.generate(api)
        self.assertIsInstance(value, RuntimeError)
        self.assertEqual(self.posts(), {})
        self.assertFalse((self.root / "history.json").exists())
        self.assertEqual(api.downloads, [])                                # 글을 저장하지 않았으니 사용 알림도 없다

    def test_hostile_photo_addresses_never_reach_a_post_even_when_the_image_check_passes_anything(self):
        """독립 검증 ③: 검색 응답의 `urls.raw` 가 낯선 호스트·경로여도(이미지 확인 url_ok 가 무엇이나 통과시키는 최악) 글도 이력도 만들어지지 않는다."""
        raws = ("https://evil.example/photo-1500000000000-x?ixid=M3w", "https://images.unsplash.com.evil.example/photo-1", "http://images.unsplash.com/photo-1", "https://images.unsplash.com/uploads/1",
                "https://images.unsplash.com/photo-1)[evil](https://evil.example)", "javascript:alert(1)")
        hostile = [photo_item(f"Hos{n:03d}xxxxxx", raw=raw, name=f"Hostile {n}", username=f"hostile{n}") for n, raw in enumerate(raws)]
        api = FakeApi(searches=[results(*hostile)], photos={})
        value, _report, _out = self.generate(api)
        self.assertIsInstance(value, RuntimeError)
        self.assertIn("대표 이미지를 2개 확보하지 못했습니다", str(value))
        self.assertEqual(self.posts(), {})
        self.assertFalse((self.root / "history.json").exists())
        self.assertEqual(api.downloads, [])

    def test_a_photo_with_a_wrong_download_address_is_skipped_and_two_good_photos_make_the_pair(self):
        """독립 검증 ②a: 사용 알림 주소가 낯선 호스트인 사진은 쓰지 않는다 — 그 주소로는 어떤 요청도 가지 않고 글에도 그 작가가 없다."""
        evil = photo_item("Zzz999yyy88", raw=PHOTO_RAW.format(pid="zzz999yyy88"), name="Evil Name", username="evilname", download="https://evil.example/steal")
        carol = photo_item("Eee555fff66", raw=PHOTO_RAW.format(pid="eee555fff66"), name="Carol Ng", username="carolng")
        api = FakeApi(searches=[results(evil, BOB, carol)])
        value, report, out = self.generate(api)
        self.assertIsNotNone(value)
        self.assertEqual(report["outcome"], "PUBLISHED")
        text = "\n".join(self.posts().values())
        self.assertEqual(len(self.posts()), 2)
        self.assertNotIn("Evil Name", text)
        self.assertNotIn("zzz999yyy88", text)
        self.assertIn("Photo by [Bob Lee]", text)
        self.assertIn("Photo by [Carol Ng]", text)
        self.assertEqual(api.downloads, ["/photos/Ccc333ddd44/download", "/photos/Eee555fff66/download"])
        self.assertEqual({call["host"] for call in api.calls}, {"api.unsplash.com"})        # 낯선 호스트로 간 요청이 없다
        self.assertNotIn(FAKE_KEY, out)

    def test_the_last_line_of_defence_refuses_a_post_whose_photo_has_no_known_credit(self):
        """사진 고르기가 어떤 이유로든 출처 없는 사진을 돌려줘도(여기서는 고르기를 가짜로 바꿨다) 글도 이력도 저장하지 않는다 — 한글·영어 글 각각."""
        for label, images, language in (("한글 글의 사진", [ALICE_URL, BOB_URL], "KR"), ("영어 글의 사진", [BOB_URL, ALICE_URL], "EN")):
            with self.subTest(label):
                g._credits.clear()
                g._credits[g.image_key(images[1 if language == "KR" else 0])] = ("Known Person", "https://unsplash.com/@known")      # 다른 쪽 사진만 출처를 안다
                with mock.patch.object(g, "pick_images", lambda queries, used, count=1, allow_pool=False, images=images: list(images)):
                    value, _report, _out = self.generate(FakeApi())
                self.assertIsInstance(value, RuntimeError)
                self.assertIn(f"{language} 대표 이미지의 작가 출처를 알 수 없어 글을 저장하지 않습니다", str(value))
                self.assertEqual(self.posts(), {})
                self.assertFalse((self.root / "history.json").exists())

    def test_without_a_key_a_real_run_stops_instead_of_using_uncredited_pool_photos(self):
        photos = {lookup_id(url): pool_photo_item(url) for url in g.IMAGE_POOL[:4]}
        api = self.use(FakeApi(searches=[results(ALICE, BOB)], photos=photos))                # 응답을 줄 수 있어도 키가 없으면 부르지 않는다
        with mock.patch.multiple(g, STUB_UNSPLASH=True, DRY_RUN=False):
            value, _report, _out = self.generate()
        self.assertEqual(api.calls, [])
        self.assertIsInstance(value, RuntimeError)
        self.assertIn("대표 이미지를 2개 확보하지 못했습니다", str(value))
        self.assertEqual(self.posts(), {})
        self.assertFalse((self.root / "history.json").exists())

    def test_a_practice_run_without_a_key_still_works_and_saves_nothing(self):
        api = self.use(FakeApi(searches=[results(ALICE, BOB)]))
        with mock.patch.multiple(g, STUB_UNSPLASH=True, DRY_RUN=True):
            value, report, out = self.generate()
        self.assertEqual(api.calls, [])
        self.assertIsNotNone(value)
        self.assertEqual(report["outcome"], "PUBLISHED")
        self.assertEqual(self.posts(), {})                                 # DRY_RUN: 아무것도 저장하지 않는다
        self.assertIn("[DRY_RUN] Unsplash 스텁 검색", out)
        self.assertIn("photo-dry", out)


class ReplaceImageTest(ChanceBase):
    """기존 글의 이미지 교체(생성기 경로): apply_image 와 fix_images."""
    OLD = "https://images.unsplash.com/photo-1111111111111-aaaaaaaaaaaa?auto=format&fit=crop&w=1000&q=80"

    def post(self, image, credit=""):
        credit_line = f"\n{credit}" if credit else ""
        return f'---\nlayout: post\ntitle: "제목입니다"\ncategory: "기술"\nlang: ko\nimage: "{image}"\n---\n\n본문 문장입니다.\n\n![Thumbnail]({image}){credit_line}\n\n인용 한 줄.\n'

    def test_apply_image_swaps_the_address_and_the_credit_line(self):
        old_line = uc.credit_markdown("Old Person", "https://unsplash.com/@oldperson")
        g._credits[g.image_key(BOB_URL)] = ("Bob Lee", "https://unsplash.com/@boblee")
        out = g.apply_image(self.post(self.OLD, old_line), self.OLD, BOB_URL)
        self.assertEqual(out, self.post(BOB_URL, BOB_LINE))
        self.assertNotIn("Old Person", out)
        self.assertEqual(g.apply_image(out, self.OLD, BOB_URL), out)        # 다시 해도 같다(옛 주소가 이미 없으니 머리말 image 만 다시 쓰고 줄은 한 줄 그대로)

    def test_applying_the_same_swap_twice_is_stable(self):
        g._credits[g.image_key(BOB_URL)] = ("Bob Lee", "https://unsplash.com/@boblee")
        once = g.apply_image(self.post(self.OLD), self.OLD, BOB_URL)
        twice = g.apply_image(once, BOB_URL, BOB_URL)
        self.assertEqual(twice, once)
        self.assertEqual(once.count("Photo by ["), 1)

    def test_a_new_photo_without_a_known_credit_removes_the_old_line_and_adds_none(self):
        old_line = uc.credit_markdown("Old Person", "https://unsplash.com/@oldperson")
        out = g.apply_image(self.post(self.OLD, old_line), self.OLD, BOB_URL)
        self.assertEqual(out, self.post(BOB_URL))

    def test_a_forged_line_in_the_old_text_does_not_survive_a_swap(self):
        g._credits[g.image_key(BOB_URL)] = ("Bob Lee", "https://unsplash.com/@boblee")
        forged = uc.credit_markdown("Evil Name", "https://unsplash.com/@evil")
        text = self.post(self.OLD).replace("인용 한 줄.", f"{forged}\n\n인용 한 줄.")
        out = g.apply_image(text, self.OLD, BOB_URL)
        self.assertNotIn("Evil Name", out)
        self.assertEqual(out.count("Photo by ["), 1)

    def test_a_post_without_an_image_gets_the_front_matter_image_and_no_line(self):
        g._credits[g.image_key(BOB_URL)] = ("Bob Lee", "https://unsplash.com/@boblee")
        text = '---\nlayout: post\ntitle: "x"\n---\n\n본문입니다.\n'
        out = g.apply_image(text, "", BOB_URL)
        self.assertIn(f'image: "{BOB_URL}"', out)
        self.assertNotIn("Photo by", out)                              # 본문에 이미지 줄이 없으니 붙일 곳이 없다

    def test_when_the_old_address_is_not_in_the_text_only_the_front_matter_changes_but_old_lines_still_go(self):
        g._credits[g.image_key(BOB_URL)] = ("Bob Lee", "https://unsplash.com/@boblee")
        old_line = uc.credit_markdown("Old Person", "https://unsplash.com/@oldperson")
        text = self.post(self.OLD, old_line)
        out = g.apply_image(text, "https://images.unsplash.com/photo-0000000000000-notfound", BOB_URL)
        self.assertIn(f'image: "{BOB_URL}"', out)
        self.assertIn(f"![Thumbnail]({self.OLD})", out)                 # 본문의 옛 이미지 줄은 건드리지 않는다(옛 동작)
        self.assertNotIn("Old Person", out)                              # 그러나 우리 모양의 옛 출처 줄은 지운다
        self.assertEqual(out.count("Photo by ["), 0)                     # 새 주소의 이미지 줄이 본문에 없으니 새 줄도 붙이지 않는다

    def test_a_text_without_front_matter_is_returned_as_it_was(self):
        self.assertEqual(g.apply_image("그냥 글", "", BOB_URL), "그냥 글")

    def run_fix(self, api):
        self.use(api)
        with mock.patch.multiple(g, STUB_GEMINI=True, POSTS_DIR=self.posts_dir):
            return self.call(g.fix_images)

    def test_fix_images_replaces_a_duplicate_image_and_its_credit_line_and_a_second_run_changes_nothing(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.posts_dir = Path(tmp.name) / "_posts"
        old_line = uc.credit_markdown("Old Person", "https://unsplash.com/@oldperson")
        first, second = self.posts_dir / "a" / "2026-10-01-KR-000001.md", self.posts_dir / "a" / "2026-10-02-KR-000002.md"
        first.parent.mkdir(parents=True)
        first.write_text(self.post(self.OLD, old_line), encoding="utf-8")
        second.write_text(self.post(self.OLD, old_line), encoding="utf-8")
        api = FakeApi(searches=[results(BOB)])
        _value, out = self.run_fix(api)
        self.assertEqual(first.read_text(encoding="utf-8"), self.post(self.OLD, old_line))          # 먼저 쓴 글은 그대로
        self.assertEqual(second.read_text(encoding="utf-8"), self.post(BOB_URL, BOB_LINE))           # 중복 글만 교체: 주소와 출처 줄이 함께 바뀐다
        self.assertEqual(api.downloads, ["/photos/Ccc333ddd44/download"])
        self.assertIn("교체 1건", out)
        again = FakeApi(searches=[results(BOB)])
        _value, out = self.run_fix(again)
        self.assertEqual(second.read_text(encoding="utf-8"), self.post(BOB_URL, BOB_LINE))
        self.assertIn("교체 0건", out)
        self.assertEqual(again.searched, [])


class DocsTest(unittest.TestCase):
    """문서가 코드와 같은 말을 한다: 새 절·가드레일 행·운영 안내·작업 내용(한계를 정직하게 적었는지 포함)."""

    @staticmethod
    def read(rel):
        return (_bootstrap.ROOT / rel).read_text(encoding="utf-8")

    def test_the_architecture_doc_has_the_chance_credit_section_with_its_limits(self):
        text = self.read("docs/ARCHITECTURE.md")
        section = text[text.index("## 4-8. "):text.index("## 5. 상태·멱등성·동시성")]
        for needle in ("pipeline/unsplash_credit.py", "ixid", "CREDIT_MARKER", "IMAGE_POOL", "GET api.unsplash.com/photos/photo-", "STUB_CREDIT", "verify_image_change", "image_key",
                       "한계", "관측이 필요한 것", "index.html", "기본 썸네일", "되는지는 확인하지 못했다", "실패 닫힘"):
            self.assertIn(needle, section, needle)
        self.assertLess(text.index("## 4-7. "), text.index("## 4-8. "))
        blogger = text[text.index("## 4-7. "):text.index("## 4-8. ")]
        self.assertIn("ixid", blogger)                                  # Blogger 대표 사진 절도 ixid 유지를 말한다
        self.assertNotIn("버리고 크기 매개변수만 붙인다 — 이것이 Unsplash 지침에 맞는지는", blogger)      # 옛 '미확인' 문장은 해결됐다

    def test_the_security_rule_g_c7_covers_chance(self):
        row = next(line for line in self.read("docs/SECURITY_GUARDRAILS.md").splitlines() if line.startswith("| G-C7 |"))
        for needle in ("Chance도 같은 규칙", "ixid", "pipeline/unsplash_credit.py", "verify_image_change", "IMAGE_POOL", "한계", "tests/test_chance_credit.py"):
            self.assertIn(needle, row, needle)

    def test_the_actions_guide_tells_the_operator_what_changed_when_the_key_breaks(self):
        text = self.read("docs/ACTIONS_GUIDE.md")
        for needle in ("작가 정보를 조회하지 못할 때", "새 글 빨강", "이제 새 글이 멈춥니다", "ixid"):
            self.assertIn(needle, text, needle)
        self.assertNotIn("| 조용함(새 글은 예비 이미지", text)

    def test_the_work_file_records_the_job_and_its_open_decisions(self):
        text = self.read("인수인계/작업내용.md")
        self.assertIn("Unsplash 사진 출처·ixid(U3", text)
        for needle in ("홈페이지 기본 썸네일 4장", "기존 글"):
            self.assertIn(needle, text, needle)


if __name__ == "__main__":
    unittest.main()
