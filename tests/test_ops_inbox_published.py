"""확인 필요 모음의 Blogger '초안 게시 대기' 게시 확인(이슈 #89) — 이미 게시한 글을 세지 않는다. 네트워크 없이 가짜 피드로 확인한다.

- 규칙(pipeline/inbox.py): Snapshot.published(블로그 key → 공개 피드에서 읽은 글 번호 집합 | None=읽지 못함)를 받아
  이미 게시한 초안을 빼고, 올린 직후(DRAFT_REMIND_AFTER_HOURS 미만)의 초안은 알림 항목으로 세지 않으며, 읽지 못했으면 새 항목을 만들지 않는다.
- 입출력(scripts/ops_inbox.py): 공개 피드 읽기(parse_feed_post_ids·fetch_feed_post_ids·fetch_published)와 run() 연결.
실제 일: 운영자가 게시한 초안 5건이 확인 필요 모음에 '게시 대기'로 남아 휴대폰 알림이 틀리게 오던 것(2026-11-02 확인).
"""
import json
import tempfile
import unittest
import urllib.error
from datetime import timedelta
from pathlib import Path
from unittest import mock

import _bootstrap
import ops_inbox_helpers as h
import ops_inbox as oi
from pipeline import inbox

NOW, ago = h.NOW, h.ago
URL = h.REPO_URL
BLOG_URL = "https://macat0722.blogspot.com/"


GOOD_SIGNALS = {"review_quality": "pass", "review_safety": "clear"}      # 2026-11-11 정리(요구 5): 이 두 신호가 이력에 적힌 초안만 '게시 검토' action 이 된다(없으면 참고) — 여기서는 늘 적어 두고 세는 규칙을 본다


def draft(hours, post_id="1001", **extra):
    return h.make_entry("draft_uploaded", ago(hours=hours), post_id=post_id, **dict(GOOD_SIGNALS, **extra))


def items_for(history, published, now=NOW, blog=None):
    blog = blog or h.make_blog(mode="draft", url=BLOG_URL)
    return inbox.blog_items([blog], {blog["key"]: history}, now, URL, published)


def feed_json(*post_ids, extra_entries=()):
    entries = [{"id": {"$t": f"tag:blogger.com,1999:blog-8140112233.post-{pid}"}, "title": {"type": "text", "$t": "제목"}} for pid in post_ids]
    return json.dumps({"version": "1.0", "encoding": "UTF-8", "feed": {"id": {"$t": "tag:blogger.com,1999:blog-8140112233"},
                                                                         "entry": entries + list(extra_entries)}})


class FakeResponse:
    def __init__(self, body):
        self._body = body if isinstance(body, bytes) else body.encode("utf-8")

    def read(self, size=-1):
        return self._body if size is None or size < 0 else self._body[:size]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeOpener:
    def __init__(self, outcome):
        self.outcome, self.requests, self.timeouts = outcome, [], []

    def __call__(self, request, timeout=None):
        self.requests.append(request)
        self.timeouts.append(timeout)
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return FakeResponse(self.outcome)


# ----------------------------------------------------------------------------
# 규칙: Snapshot.published 를 읽는 법
# ----------------------------------------------------------------------------
class PublishedStateTest(unittest.TestCase):
    def test_a_snapshot_without_a_check_is_unchecked(self):
        for value in (None, [], "x", 5, ("a",)):
            self.assertEqual(inbox._published_state(value, "k"), ("unchecked", frozenset()), repr(value))

    def test_a_key_that_is_absent_means_there_was_nothing_to_check(self):
        self.assertEqual(inbox._published_state({}, "k"), ("ok", frozenset()))
        self.assertEqual(inbox._published_state({"other": {"1"}}, "k"), ("ok", frozenset()))

    def test_none_or_an_unreadable_value_means_the_feed_could_not_be_read(self):
        for value in (None, "123", b"123", 5, 3.5, object()):
            self.assertEqual(inbox._published_state({"k": value}, "k")[0], "failed", repr(value))

    def test_ids_are_compared_as_text_and_junk_inside_the_set_is_ignored(self):
        state, ids = inbox._published_state({"k": {"101", 202, True, None, 3.5, " 303 "}}, "k")
        self.assertEqual(state, "ok")
        self.assertEqual(ids, frozenset({"101", "202", "303"}))


# ----------------------------------------------------------------------------
# 규칙: 게시 대기 항목
# ----------------------------------------------------------------------------
class ConfirmedDraftItemTest(unittest.TestCase):
    def test_the_real_case_every_recorded_draft_was_already_published(self):
        history = [draft(70, "4083806990162343742"), draft(60, "2480285108542104321"), draft(20, "3589268332908477760")]
        published = {"blogger_macat": frozenset({"4083806990162343742", "2480285108542104321", "3589268332908477760", "999"})}
        self.assertEqual(items_for(history, published), [])

    def test_without_a_feed_check_the_same_history_is_counted_but_only_as_unconfirmed(self):
        history = [draft(70, "1"), draft(60, "2"), draft(20, "3")]
        item = items_for(history, None)[0]
        self.assertEqual(item.level, "info")                     # 2026-11-11 정리: 공개 여부를 확인하지 못했으니 게시 검토 action 이 아니라 참고다
        self.assertIn("초안 3건 대기(검토 조건 미확인)", item.title)
        self.assertIn("이력으로는 게시했는지 알 수 없어", item.detail)

    def test_a_draft_that_is_still_not_public_after_the_grace_hours_is_reported_once(self):
        history = [draft(10, "1"), draft(40, "2")]
        [item] = items_for(history, {"blogger_macat": frozenset({"1"})})
        self.assertEqual(item.level, "action")
        self.assertIn("초안 1건 게시 검토", item.title)
        self.assertEqual(item.since, NOW - timedelta(hours=40))
        self.assertIn(f"{inbox.DRAFT_REMIND_AFTER_HOURS}시간", item.detail)
        self.assertIn("공개 주소", item.detail)
        self.assertNotIn("이력으로는 게시했는지 알 수 없어", item.detail)
        self.assertEqual(item.url, "https://www.blogger.com/")

    def test_a_draft_uploaded_just_now_is_not_announced_again_because_the_runner_already_did(self):
        history = [draft(0.5, "1"), draft(inbox.DRAFT_REMIND_AFTER_HOURS - 0.01, "2")]
        self.assertEqual(items_for(history, {"blogger_macat": frozenset()}), [])
        [item] = items_for([draft(inbox.DRAFT_REMIND_AFTER_HOURS, "2")], {"blogger_macat": frozenset()})        # 경계: 6시간이 되면 센다
        self.assertIn("초안 1건 게시 검토", item.title)

    def test_the_same_draft_becomes_an_item_only_after_the_grace_hours_pass(self):
        history = [draft(1, "1")]
        published = {"blogger_macat": frozenset()}
        self.assertEqual(items_for(history, published), [])
        later = NOW + timedelta(hours=inbox.DRAFT_REMIND_AFTER_HOURS)
        self.assertEqual(len(items_for(history, published, now=later)), 1)

    def test_an_entry_without_a_post_id_cannot_be_confirmed_so_it_is_counted_but_not_called_reviewable(self):
        history = [h.make_entry("draft_uploaded", ago(hours=30), **GOOD_SIGNALS), h.make_entry("draft_uploaded", ago(hours=30), post_id="", **GOOD_SIGNALS)]
        [item] = items_for(history, {"blogger_macat": frozenset({"1"})})
        self.assertEqual(item.level, "info")                     # 2026-11-11 정리: 글 번호가 없으면 공개 피드로 '아직 안 보임'을 확인할 수 없어 사람 검토 조건이 빠진다
        self.assertIn("초안 2건 대기(검토 조건 미확인)", item.title)
        self.assertIn(inbox.REVIEWABLE_GAP, item.detail)

    def test_integer_ids_from_the_feed_match_the_text_ids_in_the_history(self):
        self.assertEqual(items_for([draft(30, "4083806990162343742")], {"blogger_macat": {4083806990162343742}}), [])

    def test_a_blog_whose_feed_could_not_be_read_makes_no_new_draft_item(self):
        self.assertEqual(items_for([draft(30, "1")], {"blogger_macat": None}), [])

    def test_only_published_drafts_inside_the_week_window_matter_and_old_ones_still_fade_away(self):
        history = [draft(24 * 7 + 1, "1"), draft(24 * 2, "2")]
        [item] = items_for(history, {"blogger_macat": frozenset()})
        self.assertIn("초안 1건 게시 검토", item.title)

    def test_the_item_id_still_follows_the_newest_waiting_draft(self):
        base = items_for([draft(40, "1")], {"blogger_macat": frozenset()})[0].id
        newer = items_for([draft(40, "1"), draft(20, "2")], {"blogger_macat": frozenset()})[0].id
        gone = items_for([draft(40, "1"), draft(20, "2")], {"blogger_macat": frozenset({"2"})})[0].id
        self.assertNotEqual(base, newer)
        self.assertEqual(base, gone)                         # 새 초안을 게시하면 id 가 이전 초안(아직 미게시)의 것으로 돌아간다 — 그 초안은 실제로 게시 전이라 다시 알려도 오보가 아니다
        self.assertTrue(base.startswith("blogger:blogger_macat:drafts:"))

    def test_mode_off_still_makes_no_draft_item(self):
        blog = h.make_blog(mode="off", url=BLOG_URL)
        self.assertEqual([i.id for i in items_for([draft(30, "1")], {"blogger_macat": frozenset()}, blog=blog)], ["blog:blogger_macat:off"])


class FailedFeedNoticeTest(unittest.TestCase):
    def snapshot(self, published, failures=()):
        blog = h.make_blog(mode="draft", url=BLOG_URL)
        return inbox.Snapshot(now=NOW, repo=h.REPO, blogs=[blog], histories={blog["key"]: [draft(30, "1")]}, failures=list(failures), published=published)

    def test_a_failed_feed_read_is_a_check_item_and_never_a_waiting_action(self):
        items = inbox.build_items(self.snapshot({"blogger_macat": None}, failures=[("published", "blogger_macat: URLError 시험")]))
        ids = [i.id for i in items]
        self.assertIn("source:published", ids)
        self.assertFalse([i for i in ids if ":drafts:" in i])
        failure = next(i for i in items if i.id == "source:published")
        self.assertEqual(failure.level, "check")
        self.assertIn("Blogger 게시 확인", failure.title)

    def test_the_previously_announced_draft_id_is_carried_over_a_failed_read(self):
        readable = self.snapshot({"blogger_macat": frozenset()})                   # 30시간 된 초안이 피드에 안 보인다 → 알림 항목 1개
        announced = inbox.action_ids(inbox.build_items(readable))
        self.assertEqual(len(announced), 1)
        failed = self.snapshot({"blogger_macat": None}, failures=[("published", "x")])
        new, kept = inbox.plan_notice(inbox.build_items(failed), announced, failures=failed.failures)
        self.assertEqual(new, [])
        self.assertEqual(kept, sorted(announced))             # 표식이 이전 id 를 이어 간다 — 복구된 뒤 같은 항목이 새 알림이 되지 않는다
        self.assertEqual(inbox.plan_notice(inbox.build_items(readable), kept)[0], [])

    def test_a_failed_read_after_everything_was_published_announces_nothing_new(self):
        failed = self.snapshot({"blogger_macat": None}, failures=[("published", "x")])
        new, kept = inbox.plan_notice(inbox.build_items(failed), [], failures=failed.failures)
        self.assertEqual((new, kept), ([], []))               # 읽지 못한 것은 확인 항목(check)일 뿐 새 해야 할 일이 아니다

    def test_the_source_is_labelled_and_owns_the_blogger_prefix(self):
        self.assertIn("published", inbox.SOURCE_LABELS)
        self.assertEqual(inbox.SOURCE_PREFIXES["published"], ("blogger:",))


# ----------------------------------------------------------------------------
# 규칙: 초안 현황 표
# ----------------------------------------------------------------------------
class BoardWithConfirmationTest(unittest.TestCase):
    def snapshot(self, history, published, mode="draft"):
        blog = h.channel_blog("blogger_macat", "Blogger 영문", platform="blogger", mode=mode, url=BLOG_URL)
        return inbox.Snapshot(now=NOW, repo=h.REPO, blogs=[blog], histories={"blogger_macat": history}, published=published)

    def row(self, snap):
        rows, _links, _blogger = inbox.board_rows(snap)
        return rows[0]

    def test_published_drafts_are_not_counted_and_the_count_is_not_approximate(self):
        history = [draft(70, "1"), draft(60, "2"), draft(2, "3")]
        row = self.row(self.snapshot(history, {"blogger_macat": frozenset({"1", "2"})}))
        self.assertEqual(row[1], "1")                         # 올린 직후(2시간)의 초안도 표에는 센다 — 6시간 유예는 알림 항목에만 적용
        self.assertNotIn("대략", row[1])

    def test_everything_published_shows_zero(self):
        row = self.row(self.snapshot([draft(70, "1")], {"blogger_macat": frozenset({"1"})}))
        self.assertEqual(row, ["Blogger 영문", "0", "-", "-"])

    def test_a_feed_that_could_not_be_read_shows_lookup_failed_not_zero(self):
        row = self.row(self.snapshot([draft(70, "1")], {"blogger_macat": None}))
        self.assertEqual(row[1], "조회 실패")

    def test_without_a_check_the_old_approximate_count_is_kept(self):
        row = self.row(self.snapshot([draft(70, "1"), draft(60, "2")], None))
        self.assertEqual(row[1], "2 (대략)")

    def test_the_note_under_the_table_matches_whether_the_feed_was_checked(self):
        checked = inbox.draft_board(self.snapshot([draft(70, "1")], {"blogger_macat": frozenset()}))
        self.assertIn(inbox.BOARD_NOTE_BLOGGER_CHECKED, checked)
        self.assertNotIn(inbox.BOARD_NOTE_BLOGGER, checked)
        legacy = inbox.draft_board(self.snapshot([draft(70, "1")], None))
        self.assertIn(inbox.BOARD_NOTE_BLOGGER, legacy)
        self.assertNotIn(inbox.BOARD_NOTE_BLOGGER_CHECKED, legacy)

    def test_history_drafts_accepts_the_published_ids(self):
        history = [draft(70, "1"), draft(60, "2")]
        self.assertEqual(len(inbox.history_drafts(history, NOW)), 2)
        self.assertEqual(len(inbox.history_drafts(history, NOW, frozenset({"1"}))), 1)


# ----------------------------------------------------------------------------
# 입출력: 공개 피드 읽기
# ----------------------------------------------------------------------------
class ParseFeedTest(unittest.TestCase):
    def test_post_ids_are_read_from_the_feed_entries(self):
        self.assertEqual(oi.parse_feed_post_ids(feed_json("4083806990162343742", "2480285108542104321")),
                         frozenset({"4083806990162343742", "2480285108542104321"}))

    def test_a_feed_without_entries_is_an_empty_set(self):
        self.assertEqual(oi.parse_feed_post_ids(json.dumps({"feed": {"id": {"$t": "x"}}})), frozenset())
        self.assertEqual(oi.parse_feed_post_ids(feed_json()), frozenset())

    def test_pages_and_odd_entries_are_ignored(self):
        extra = [{"id": {"$t": "tag:blogger.com,1999:blog-1.page-555"}}, {"id": "문자열"}, {"id": {"$t": None}}, "x", None, {}]
        self.assertEqual(oi.parse_feed_post_ids(feed_json("77", extra_entries=extra)), frozenset({"77"}))

    def test_a_response_that_is_not_a_blogger_feed_is_an_error(self):
        for text in ("<html>blocked</html>", "[]", "null", json.dumps({"feed": []}), json.dumps({"nofeed": {}}), json.dumps({"feed": {"entry": {"id": 1}}}), ""):
            with self.assertRaises(ValueError, msg=text):
                oi.parse_feed_post_ids(text)


class FetchFeedTest(unittest.TestCase):
    def test_the_public_summary_feed_is_requested_without_any_credentials(self):
        opener = FakeOpener(feed_json("5"))
        self.assertEqual(oi.fetch_feed_post_ids(BLOG_URL, opener), frozenset({"5"}))
        [request] = opener.requests
        self.assertEqual(request.full_url, "https://macat0722.blogspot.com/feeds/posts/summary?alt=json&max-results=500")
        self.assertEqual(opener.timeouts, [oi.FEED_TIMEOUT_SECONDS])
        self.assertTrue(0 < oi.FEED_TIMEOUT_SECONDS <= 30)       # 응답이 없는 블로그가 점검을 오래 붙잡지 못한다
        self.assertFalse([name for name in request.headers if name.lower() in ("authorization", "cookie")])
        self.assertIsNone(request.data)                         # 읽기(GET)다

    def test_a_blog_address_without_the_trailing_slash_works(self):
        opener = FakeOpener(feed_json("5"))
        oi.fetch_feed_post_ids("https://macat0722.blogspot.com", opener)
        self.assertTrue(opener.requests[0].full_url.startswith("https://macat0722.blogspot.com/feeds/posts/summary"))

    def test_an_oversized_response_is_refused_even_when_it_is_valid_json(self):
        padded = feed_json("5").encode("utf-8") + b" " * oi.FEED_MAX_BYTES            # 올바른 JSON 이지만 한도를 넘는다
        with self.assertRaises(ValueError) as caught:
            oi.fetch_feed_post_ids(BLOG_URL, FakeOpener(padded))
        self.assertIn("너무 큽니다", str(caught.exception))
        self.assertEqual(oi.fetch_feed_post_ids(BLOG_URL, FakeOpener(feed_json("5").encode("utf-8") + b" " * 1000)), frozenset({"5"}))

    def test_network_errors_are_raised_to_the_caller(self):
        with self.assertRaises(urllib.error.URLError):
            oi.fetch_feed_post_ids(BLOG_URL, FakeOpener(urllib.error.URLError("연결 안 됨")))

    def test_the_default_reader_uses_the_urlopen_that_exists_at_call_time(self):
        """함수가 만들어질 때 urlopen 을 묶어 두면 시험이 네트워크를 바꿔 끼우지 못해 진짜 블로그로 나간다(검증이 잡은 일)."""
        fake = FakeOpener(feed_json("7"))
        with mock.patch("urllib.request.urlopen", fake):
            self.assertEqual(oi.fetch_feed_post_ids(BLOG_URL), frozenset({"7"}))
        self.assertEqual(len(fake.requests), 1)
        with mock.patch("urllib.request.urlopen", FakeOpener(urllib.error.URLError("연결 안 됨"))):
            with self.assertRaises(urllib.error.URLError):
                oi.fetch_feed_post_ids(BLOG_URL)


class FetchPublishedTest(unittest.TestCase):
    def blogs(self):
        return [h.make_blog("chance", "Chance", "auto", "jekyll-git", url="https://shine88pc.github.io/chanceblog/"),
                h.make_blog("blogger_macat", "영문", "draft", url="https://macat0722.blogspot.com/"),
                h.make_blog("blogger_kcyoon", "한글", "draft", url="https://kcyoon.blogspot.com/"),
                h.make_blog("blogger_off", "정지", "off", url="https://off.blogspot.com/")]

    def histories(self):
        return {"chance": [{"date": "2026-10-25"}], "blogger_macat": [draft(30, "1")], "blogger_kcyoon": [draft(30, "2")], "blogger_off": [draft(30, "3")]}

    def test_only_blogger_blogs_that_are_running_and_have_recent_drafts_are_read(self):
        calls, failures = [], []
        result = oi.fetch_published(self.blogs(), self.histories(), NOW, failures, lambda url: calls.append(url) or frozenset({"9"}))
        self.assertEqual(sorted(calls), ["https://kcyoon.blogspot.com/", "https://macat0722.blogspot.com/"])
        self.assertEqual(result, {"blogger_macat": frozenset({"9"}), "blogger_kcyoon": frozenset({"9"})})
        self.assertEqual(failures, [])

    def test_a_blog_without_recent_drafts_is_not_read_and_has_no_key(self):
        calls = []
        history = {"blogger_macat": [h.make_entry("posted", ago(hours=3), post_id="1"), draft(24 * 15, "2")]}
        result = oi.fetch_published([self.blogs()[1]], history, NOW, [], lambda url: calls.append(url) or frozenset())
        self.assertEqual((calls, result), ([], {}))

    def test_one_failing_blog_is_recorded_and_the_other_still_works(self):
        def fetch(url):
            if "macat" in url:
                raise urllib.error.URLError("연결 안 됨")
            return frozenset({"2"})
        failures = []
        result = oi.fetch_published(self.blogs(), self.histories(), NOW, failures, fetch)
        self.assertIsNone(result["blogger_macat"])
        self.assertEqual(result["blogger_kcyoon"], frozenset({"2"}))
        [(source, reason)] = failures
        self.assertEqual(source, "published")
        self.assertIn("blogger_macat", reason)
        self.assertIn("URLError", reason)
        self.assertNotIn("kcyoon", reason)

    def test_an_unexpected_exception_type_does_not_stop_the_check(self):
        failures = []
        result = oi.fetch_published(self.blogs()[1:2], self.histories(), NOW, failures, lambda url: (_ for _ in ()).throw(RuntimeError("boom")))
        self.assertEqual(result, {"blogger_macat": None})
        self.assertIn("RuntimeError", failures[0][1])

    def test_an_address_that_is_not_a_blogspot_blog_is_never_requested(self):
        for url in ("https://evil.example.com/", "http://macat0722.blogspot.com/", "https://macat0722.blogspot.com.evil.com/",
                    "https://macat0722.blogspot.com/x", "", "file:///etc/passwd", "https://-bad.blogspot.com/"):
            calls, failures = [], []
            blog = h.make_blog("blogger_macat", "영문", "draft", url=url)
            result = oi.fetch_published([blog], {"blogger_macat": [draft(30, "1")]}, NOW, failures, lambda u: calls.append(u) or frozenset())
            self.assertEqual(calls, [], url)
            self.assertEqual(result, {"blogger_macat": None}, url)
            self.assertEqual(failures[0][0], "published", url)

    def test_a_feed_without_any_public_post_is_treated_as_unreadable_not_as_nothing_published(self):
        failures = []
        calls = []
        result = oi.fetch_published(self.blogs()[1:2], self.histories(), NOW, failures, lambda url: calls.append(url) or frozenset())
        self.assertEqual(calls, ["https://macat0722.blogspot.com/"])
        self.assertEqual(result, {"blogger_macat": None})
        [(source, reason)] = failures
        self.assertEqual(source, "published")
        self.assertIn("공개 글이 하나도 없는 피드", reason)
        snap = inbox.Snapshot(now=NOW, repo=h.REPO, blogs=self.blogs()[1:2], histories=self.histories(), failures=failures, published=result)
        self.assertFalse([i for i in inbox.build_items(snap) if ":drafts:" in i.id])               # 게시한 초안이 6시간 뒤 다시 알려지지 않는다

    def test_a_naive_clock_does_not_break_the_check(self):
        naive = NOW.replace(tzinfo=None)
        result = oi.fetch_published(self.blogs()[1:2], self.histories(), naive, [], lambda url: frozenset({"9"}))
        self.assertEqual(result, {"blogger_macat": frozenset({"9"})})

    def test_malformed_blogs_and_histories_are_skipped_quietly(self):
        result = oi.fetch_published([None, "x", {"key": 5}, {"mode": "draft"}], {}, NOW, [], lambda url: frozenset())
        self.assertEqual(result, {})
        self.assertEqual(oi.fetch_published(self.blogs()[1:2], None, NOW, [], lambda url: frozenset()), {})


# ----------------------------------------------------------------------------
# 입출력: run() 연결
# ----------------------------------------------------------------------------
class RunWithConfirmationTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        registry = json.loads(h.CHANNEL_REGISTRY)
        for blog in registry["blogs"]:
            if blog["key"] == "blogger_macat":
                blog["url"] = BLOG_URL
        self.root = h.make_root(Path(self._tmp.name) / "repo", workflows=(), blogs_json=json.dumps(registry, ensure_ascii=False),
                                histories={"history.json": [], "blogger_history.json": [draft(70, "4083806990162343742"), draft(30, "2480285108542104321")]})

    def run_inbox(self, feed_fetcher):
        out = []
        code = oi.run({"GITHUB_REPOSITORY": h.REPO}, h.FakeGitHub(), NOW, self.root, out.append, sleep=lambda seconds: None, feed_fetcher=feed_fetcher)
        return code, "\n".join(out)

    def test_published_drafts_disappear_from_the_report(self):
        code, text = self.run_inbox(lambda url: frozenset({"4083806990162343742", "2480285108542104321"}))
        self.assertEqual(code, 0)
        self.assertNotIn("게시 대기", text)
        self.assertNotIn("게시 검토", text)                       # 2026-11-11 정리: 낱말이 바뀌었으니 새 낱말과 '검토 조건 미확인'도 없어야 한다
        self.assertNotIn("검토 조건 미확인", text)
        self.assertIn("공개 주소(피드)에서 아직 보이지 않는 글만", text)

    def test_the_draft_that_is_still_not_public_is_reported(self):
        code, text = self.run_inbox(lambda url: frozenset({"4083806990162343742"}))
        self.assertEqual(code, 0)
        self.assertIn("초안 1건 게시 검토", text)

    def test_a_feed_that_cannot_be_read_is_reported_as_a_lookup_failure_and_not_as_waiting(self):
        def broken(url):
            raise urllib.error.URLError("연결 안 됨")
        code, text = self.run_inbox(broken)
        self.assertEqual(code, 0)
        self.assertIn("조회 실패 — Blogger 게시 확인", text)
        for old_or_new in ("초안 2건 게시 대기", "초안 1건 게시 대기", "초안 2건 게시 검토", "초안 1건 게시 검토", "검토 조건 미확인"):
            self.assertNotIn(old_or_new, text)

    def test_without_a_fetcher_nothing_is_read_from_the_network_and_the_old_count_stays(self):
        code, text = self.run_inbox(None)
        self.assertEqual(code, 0)
        self.assertIn("초안 2건 대기(검토 조건 미확인)", text)                # 2026-11-11 정리: 게시 확인이 없으니 이력만 센 값은 게시 검토 action 이 아니라 참고다
        self.assertIn("이력으로는 게시했는지 알 수 없어", text)
        self.assertNotIn("건 게시 검토", text)                    # 설명 문장에는 '게시 검토' 낱말이 있다 — action 제목(초안 N건 게시 검토)만 없어야 한다

    def test_main_passes_the_real_feed_reader(self):
        with mock.patch.object(oi, "run", return_value=0) as fake_run, mock.patch.object(oi, "safe_output"):
            self.assertEqual(oi.main(), 0)
        fake_run.assert_called_once_with(feed_fetcher=oi.fetch_feed_post_ids)


class DocumentationTest(unittest.TestCase):
    def test_the_guide_describes_the_published_check_and_the_grace_hours(self):
        doc = (_bootstrap.ROOT / "docs" / "OPS_INBOX.md").read_text(encoding="utf-8")
        for phrase in ("게시 확인(2026-11-02, 이슈 #89)", "`DRAFT_REMIND_AFTER_HOURS`(6시간)", "공개 피드", "Blogger 게시 확인(블로그 공개 피드)",
                       "feeds/posts/summary?alt=json", "공개 글이 하나도 없는 피드", "예약 게시(SCHEDULED)"):
            self.assertIn(phrase, doc, phrase)
        self.assertEqual(inbox.DRAFT_REMIND_AFTER_HOURS, 6)

    def test_the_script_docstring_mentions_the_feed(self):
        source = (_bootstrap.ROOT / "scripts" / "ops_inbox.py").read_text(encoding="utf-8")
        self.assertIn("Blogger 초안 게시 확인", source)
        self.assertIn("feeds/posts/summary?alt=json", source)


if __name__ == "__main__":
    unittest.main()
