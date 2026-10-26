"""Pages 배포 후 확인(scripts/verify_pages_deploy.py): 확인할 글 선정과 공개 주소 계산 테스트. 네트워크 없이 돈다.

- 선정: 저장소 `_posts`의 가장 새 글. `published: false`·미래 날짜인 글은 사이트에 올라오지 않으므로 건너뛰고 그다음 새 글을 본다
  (실제 `_posts` 20건 중 5건이 `published: false`이고 공개 posts.json에는 정확히 그 5건만 없다).
- 주소: `_config.yml` permalink 와 파일명(글 자신의 front matter permalink·slug·date 포함)으로 계산한다.
"""
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import _bootstrap  # noqa: F401
from verify_pages_helpers import BASE, KR, EN, KST, NOW, SITE_CONFIG, make_repo, post_of, v

# 2026-10-25 공개 사이트 posts.json 에서 옮겨 온 (path -> absoluteUrl) 15건 중 10건(MIT TR 쌍 2건·IEEE Spectrum 쌍 2건·Ars Technica 1편은 2026-10-26에 비공개로 돌려 아래 PUBLIC_MISSING으로 옮겼다)(로컬 사본. 이 테스트는 사이트에 접속하지 않는다).
PUBLIC_SNAPSHOT = {
    "_posts/일상·마음/2026-10-20-KR-141500.md": "https://shine88pc.github.io/chanceblog/posts/2026/10/20/korean-food-date-labels/",
    "_posts/Everyday Life/2026-10-20-EN-141500.md": "https://shine88pc.github.io/chanceblog/posts/2026/10/20/south-korea-food-date-labels/",
    "_posts/과학 환경/2026-10-20-KR-125000.md": "https://shine88pc.github.io/chanceblog/posts/2026/10/20/KR-125000/",
    "_posts/EN - Science & Environment/2026-10-20-EN-125000.md": "https://shine88pc.github.io/chanceblog/posts/2026/10/20/EN-125000/",
    "_posts/산업 AI/2026-10-19-KR-195755.md": "https://shine88pc.github.io/chanceblog/posts/2026/10/19/KR-195755/",
    "_posts/KR - 테크 인사이트/2026-10-19-KR-103939.md": "https://shine88pc.github.io/chanceblog/posts/2026/10/19/KR-103939/",
    "_posts/Industrial AI/2026-10-19-EN-195755.md": "https://shine88pc.github.io/chanceblog/posts/2026/10/19/EN-195755/",
    "_posts/EN - Tech Insights/2026-10-19-EN-103939.md": "https://shine88pc.github.io/chanceblog/posts/2026/10/19/EN-103939/",
    "_posts/EN - Space & Robotics/2026-10-18-EN-233513.md": "https://shine88pc.github.io/chanceblog/posts/2026/10/18/EN-233513/",
    "_posts/2026-10-18-AI.md": "https://shine88pc.github.io/chanceblog/posts/2026/10/18/AI/",
}
# 저장소에는 있으나 `published: false`라 공개 posts.json에 없는 14건(2026-10-25 사본의 5건 + 2026-10-26에 비공개로 돌린 9건).
PUBLIC_MISSING = [
    # 2026-10-26 운영자 승인으로 비공개 전환(약관이 금지하는 매체 출처: MIT Technology Review 쌍 2026-10-21, AI타임스 쌍 2026-10-25)
    "_posts/기술·미래/2026-10-21-KR-135226.md",
    "_posts/Technology & Future/2026-10-21-EN-135226.md",
    "_posts/기술·미래/2026-10-25-KR-203740.md",
    "_posts/Technology & Future/2026-10-25-EN-203740.md",
    # 2026-10-26 운영자 승인으로 비공개 전환(robots.txt 가 AI 크롤러를 막아 접근하지 않기로 한 매체 출처: Ars Technica 2026-10-19, IEEE Spectrum 쌍 2026-10-25)
    "_posts/2026-10-19-AI.md",
    "_posts/기술·미래/2026-10-25-KR-101307.md",
    "_posts/Technology & Future/2026-10-25-EN-101307.md",
    # 2026-10-26 운영자 승인으로 비공개 전환(콘텐츠 이용에 정식 계약·사용료가 필요해 접근하지 않기로 한 매체 출처: 전자신문 쌍 2026-10-26)
    "_posts/기술·미래/2026-10-26-KR-101652.md",
    "_posts/Technology & Future/2026-10-26-EN-101652.md",
    "_posts/2026-10-18-EN-225949.md",
    "_posts/2026-10-18-KR-225949.md",
    "_posts/EN - Tech Geopolitics/2026-10-18-EN-161948.md",
    "_posts/KR - 테크 이야기/2026-10-18-KR-233513.md",
    "_posts/KR - 하드웨어 인사이트/2026-10-18-KR-161948.md",
]
REAL_BASE = "https://shine88pc.github.io/chanceblog/"


def key_of(post):
    tail = v.TIME_TAIL.search(post.slug)
    return post.file_date.isoformat(), tail.group(1) if tail else "000000"


class TempDirCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def write(self, name, data, binary=False):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if binary:
            path.write_bytes(data)
        else:
            path.write_text(data, encoding="utf-8", newline="")
        return path


class FrontMatterTest(TempDirCase):
    def read(self, text, newline="\n"):
        return v.read_front_matter(self.write("p.md", text.replace("\n", newline)))

    def test_reads_only_the_four_keys_the_check_needs(self):
        front = self.read("---\nlayout: post\ntitle: t\npublished: false\ndate: 2026-10-20 08:20:00 +0900\n"
                          "permalink: /a/b/\nslug: s\ntags: [x]\n---\n본문\n")
        self.assertEqual(front, {"published": "false", "date": "2026-10-20 08:20:00 +0900", "permalink": "/a/b/", "slug": "s"})

    def test_published_false_variants_are_unpublished(self):
        for line in ("published: false", "published: False", "published: FALSE", 'published: "false"', "published: 'False'",
                     "published: no", "published: No", "published: off", "published: false # 초안", "published:   false   ",
                     'published: "FALSE" # note', "published:", "published:   ", "published: ~", "published: null",
                     "published: NULL", "published: # 주석만", "published: Null # 비움", 'published: "null"', "published: '~'"):
            with self.subTest(line=line):
                self.assertTrue(v.is_unpublished(self.read(f"---\n{line}\n---\n")))

    def test_quoted_keys_and_spaces_before_the_colon_are_the_same_key(self):
        """N-4: YAML 은 `published : false`·`"published": false`·`'published': false` 도 같은 키로 읽는다. Jekyll 은 그 글을 공개하지 않는다."""
        for line in ("published : false", "published  : false", "published\t: false", '"published": false', "'published': false",
                     '"published" : false', "'published' : no", '"published":   off # c', '"published":', "published :",
                     "'published' : null", '"published": "FALSE"', "'published': False"):
            with self.subTest(line=line):
                self.assertTrue(v.is_unpublished(self.read(f"---\n{line}\n---\n")), line)

    def test_other_keys_accept_the_same_key_forms(self):
        front = self.read('---\n"permalink": /a/\n\'slug\' : s\ndate : 2026-10-20 08:20:00 +0900\n"published" : true\n---\n')
        self.assertEqual(front, {"permalink": "/a/", "slug": "s", "date": "2026-10-20 08:20:00 +0900", "published": "true"})

    def test_mismatched_or_unterminated_key_quotes_are_not_keys(self):
        for line in ('"published\': false', "'published\": false", '"published: false', 'published": false', "'published: false",
                     '""published": false', '"published"": false', '"pub lished": false', "published false"):
            with self.subTest(line=line):
                self.assertEqual(self.read(f"---\n{line}\n---\n"), {}, line)

    def test_anything_else_stays_published(self):
        for text in ("---\npublished: true\n---\n", '---\npublished: "true"\n---\n', "---\npublished: yes\n---\n",
                     "---\npublished: 0\n---\n", "---\npublished: falsey\n---\n", "---\ntitle: t\n---\n",
                     "---\npublished: [false]\n---\n", "---\ndraft: true\n---\n",
                     "---\npublished: |\n---\n",
                     "---\npublished:false\n---\n", "no front matter\npublished: false\n", ""):
            with self.subTest(text=text):
                self.assertFalse(v.is_unpublished(self.read(text)))

    def test_scalars_quotes_comments_and_escapes(self):
        cases = (("permalink: /a/b/", "/a/b/"), ('permalink: "/a/b/"', "/a/b/"), ("permalink: '/a/b/'", "/a/b/"),
                 ("permalink: /a/b/ # 주석", "/a/b/"), ('permalink: "/a/\\"q\\"/"', '/a/"q"/'),
                 ("permalink: '/it''s/'", "/it's/"), ('permalink: "/한글/" # c', "/한글/"), ("slug: my-slug", "my-slug"))
        for line, expected in cases:
            with self.subTest(line=line):
                key = line.split(":")[0]
                self.assertEqual(self.read(f"---\n{line}\n---\n")[key], expected)

    def test_unreadable_shapes_are_none_not_guessed(self):
        for line in ("permalink: |", "permalink: >", "permalink: [a]", "permalink: {a: b}", "permalink: &x /a/",
                     "permalink: *x", 'permalink: "unterminated', "permalink: 'unterminated", "permalink:", "permalink: # only comment",
                     "permalink: !tag x"):
            with self.subTest(line=line):
                self.assertEqual(self.read(f"---\n{line}\n---\n"), {"permalink": None})

    def test_indented_keys_and_body_text_are_ignored(self):
        front = self.read("---\nextra:\n  published: false\n  permalink: /x/\ntitle: t\n---\npublished: false\npermalink: /body/\n")
        self.assertEqual(front, {})

    def test_front_matter_end_markers_and_duplicates(self):
        self.assertEqual(self.read("---\nslug: a\n...\nslug: b\n"), {"slug": "a"})
        self.assertEqual(self.read("---\nslug: a\nslug: b\n---\n"), {"slug": "b"})  # 같은 키는 뒤의 것(YAML 과 같다)
        self.assertEqual(self.read("---\nslug: a\n"), {"slug": "a"})  # 닫는 줄이 없어도 읽은 만큼은 쓴다

    def test_crlf_bom_and_trailing_spaces(self):
        self.assertEqual(self.read("---\npublished: false\n---\n", "\r\n"), {"published": "false"})
        self.assertEqual(self.read(chr(0xFEFF) + "---\npublished: false\n---\n"), {"published": "false"})
        self.assertEqual(self.read("---   \npublished: false\n---  \n"), {"published": "false"})

    def test_no_front_matter_or_missing_file_is_empty(self):
        self.assertEqual(self.read("본문만 있음\n"), {})
        self.assertEqual(self.read(" ---\npublished: false\n---\n"), {})  # 첫 줄은 정확히 ---
        self.assertEqual(v.read_front_matter(self.root / "nope.md"), {})

    def test_only_the_top_of_the_file_is_read(self):
        text = "---\n" + "x: y\n" * (v.FRONT_MATTER_BYTES // 4) + "published: false\n---\n"
        self.assertEqual(self.read(text), {})

    def test_undecodable_bytes_do_not_crash(self):
        path = self.write("b.md", b"---\npublished: false\ntitle: \xff\xfe\n---\n", binary=True)
        self.assertEqual(v.read_front_matter(path), {"published": "false"})


class ParseWhenTest(unittest.TestCase):
    def test_formats_with_and_without_a_zone(self):
        cases = (
            ("2026-10-20 08:20:00 +0900", datetime(2026, 10, 20, 8, 20, tzinfo=KST)),
            ("2026-10-20T08:20:00+09:00", datetime(2026, 10, 20, 8, 20, tzinfo=KST)),
            ("2026-10-20 08:20:00 +09:00", datetime(2026, 10, 20, 8, 20, tzinfo=KST)),
            ("2026-10-20 08:20:00 +9", datetime(2026, 10, 20, 8, 20, tzinfo=KST)),
            ("2026-10-20 08:20:00 -0500", datetime(2026, 10, 20, 8, 20, tzinfo=timezone(timedelta(hours=-5)))),
            ("2026-10-20 08:20:00 +0530", datetime(2026, 10, 20, 8, 20, tzinfo=timezone(timedelta(hours=5, minutes=30)))),
            ("2026-10-20 08:20:00 UTC", datetime(2026, 10, 20, 8, 20, tzinfo=timezone.utc)),
            ("2026-10-20 08:20:00Z", datetime(2026, 10, 20, 8, 20, tzinfo=timezone.utc)),
            ("2026-10-20 08:20", datetime(2026, 10, 20, 8, 20, tzinfo=KST)),  # 시간대 표기가 없으면 사이트 시간대
            ("2026-10-20", datetime(2026, 10, 20, tzinfo=KST)),
            ("2026-10-20 08:20:00.123 +0900", datetime(2026, 10, 20, 8, 20, tzinfo=KST)),
            ("  2026-10-20  ", datetime(2026, 10, 20, tzinfo=KST)),
        )
        for text, expected in cases:
            with self.subTest(text=text):
                parsed = v.parse_when(text, KST)
                self.assertEqual(parsed, expected)
                self.assertEqual(parsed.utcoffset(), expected.utcoffset())

    def test_seconds_without_a_zone_mean_utc_like_jekyll_but_without_seconds_the_site_zone(self):
        parsed = v.parse_when("2026-10-20 08:20:00", KST)  # SafeYAML 은 이것을 UTC 시각으로 읽는다
        self.assertEqual(parsed, datetime(2026, 10, 20, 8, 20, tzinfo=timezone.utc))
        self.assertEqual(parsed.utcoffset(), timedelta(0))
        self.assertEqual(v.parse_when("2026-10-20 08:20", KST).utcoffset(), timedelta(hours=9))
        self.assertEqual(v.parse_when("2026-10-20", KST).utcoffset(), timedelta(hours=9))

    def test_site_zone_is_used_only_when_the_text_has_none(self):
        utc = v.parse_when("2026-10-20 08:20", timezone.utc)
        self.assertEqual(utc.utcoffset(), timedelta(0))
        self.assertEqual(v.parse_when("2026-10-20 08:20 +0900", timezone.utc).utcoffset(), timedelta(hours=9))

    def test_unreadable_dates_are_none(self):
        for text in ("", None, "tomorrow", "2026-13-45", "2026-10-20 25:00:00", "2026-10-20 08:20:00 +9999", "20261020",
                     "2026-10-20 08:20:00 KST"):
            with self.subTest(text=text):
                self.assertIsNone(v.parse_when(text, KST))


class FindCandidatesTest(TempDirCase):
    def names(self, now=NOW):
        return [p.name for p in v.select_newest(self.root, now, KST).posts]

    def test_returns_the_kr_en_pair_made_at_the_same_time(self):
        make_repo(self.root, [KR, EN, "기술·미래/2026-10-21-KR-135226.md"])
        selection = v.select_newest(self.root, NOW, KST)
        self.assertEqual([p.rel for p in selection.posts],
                         ["_posts/Technology & Future/2026-10-25-EN-101307.md", "_posts/기술·미래/2026-10-25-KR-101307.md"])
        self.assertEqual(selection.skipped, [])
        self.assertEqual(selection.total, 3)

    def test_date_beats_time_and_time_breaks_ties_within_a_day(self):
        make_repo(self.root, ["a/2026-10-24-KR-235959.md", "a/2026-10-25-KR-000100.md", "a/2026-10-25-KR-090000.md"])
        self.assertEqual(self.names(), ["2026-10-25-KR-090000.md"])

    def test_files_without_a_time_tail_count_as_midnight(self):
        make_repo(self.root, ["2026-10-19-AI.md", "2026-10-19-KR-000001.md"])
        self.assertEqual(self.names(), ["2026-10-19-KR-000001.md"])

    def test_time_is_read_from_the_end_of_the_name(self):
        make_repo(self.root, ["a/2026-10-25-999999-foo-000100.md", "a/2026-10-25-000001-bar-090000.md"])
        self.assertEqual(self.names(), ["2026-10-25-000001-bar-090000.md"])

    def test_only_markdown_posts_with_a_valid_date_prefix_count(self):
        make_repo(self.root, ["a/2025-01-01-KR-000001.md"])  # 가장 오래된 진짜 글. 아래 이름들이 글로 인정되면 이 글을 밀어낸다
        for ignored in ("README.md", "notes.txt", "a/2026-10-25-KR-101307.txt", "a/2026-10-25-KR-101307.md.bak",
                        "a/2026-1-5-short-date.md", "a/2026-10-5-short-day.md", "a/abcdefghij-KR-1.md",
                        "a/2026-13-45-bad-date.md", "a/2026-10-25-.md", "a/20261025-KR-1.md"):
            path = self.root / "_posts" / ignored
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("---\n---\n", encoding="utf-8")
        self.assertEqual(self.names(), ["2025-01-01-KR-000001.md"])

    def test_directories_and_special_names_are_ignored(self):
        make_repo(self.root, ["a/2026-10-20-KR-000001.md"])
        (self.root / "_posts" / "a" / "2026-10-26-KR-000009.md").mkdir()  # 이름이 .md 인 폴더
        for ignored in ("_drafts/2026-10-26-KR-000002.md", ".hidden/2026-10-26-KR-000003.md", "#tmp/2026-10-26-KR-000004.md",
                        "~old/2026-10-26-KR-000005.md", "a/_2026-10-26-KR-000006.md", "a/.2026-10-26-KR-000007.md",
                        "a/2026-10-26-KR-000008.md~"):
            path = self.root / "_posts" / ignored
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("---\n---\n", encoding="utf-8")
        self.assertEqual(self.names(now=datetime(2026, 12, 1, tzinfo=timezone.utc)), ["2026-10-20-KR-000001.md"])

    def test_result_order_does_not_depend_on_the_file_system(self):
        make_repo(self.root, ["z/2026-10-25-EN-101307.md", "a/2026-10-25-KR-101307.md", "m/2026-10-25-XX-101307.md"])
        real_rglob = Path.rglob
        with mock.patch.object(Path, "rglob", lambda self_, pattern: iter(reversed(sorted(real_rglob(self_, pattern))))):
            rels = [p.rel for p in v.select_newest(self.root, NOW, KST).posts]
        self.assertEqual(rels, sorted(rels))
        self.assertEqual(len(rels), 3)

    def test_missing_posts_folder_is_a_configuration_error_but_an_empty_one_is_not(self):
        with self.assertRaises(v.ConfigError) as ctx:
            v.select_newest(self.root, NOW, KST)
        self.assertIn("_posts", str(ctx.exception))
        (self.root / "_posts").mkdir()
        self.assertEqual(v.select_newest(self.root, NOW, KST), v.Selection([], [], 0))
        make_repo(self.root, ["README.md"])  # 글이 아닌 파일만 있어도 건너뜀(설정 오류 아님)
        self.assertEqual(v.select_newest(self.root, NOW, KST).posts, [])

    def test_a_file_named_posts_is_not_the_posts_folder(self):
        (self.root / "_posts").write_text("not a folder", encoding="utf-8")
        with self.assertRaises(v.ConfigError):
            v.select_newest(self.root, NOW, KST)

    def test_relative_root_works(self):
        make_repo(self.root, [KR])
        previous = os.getcwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, previous)
        self.assertEqual([p.rel for p in v.select_newest(".", NOW, KST).posts], ["_posts/" + KR])


class EligibilityTest(TempDirCase):
    def select(self, names, fronts, now=NOW):
        make_repo(self.root, names, fronts=fronts)
        return v.select_newest(self.root, now, KST)

    def test_an_unpublished_newest_pair_is_skipped_for_the_next_pair(self):
        old = ["기술·미래/2026-10-21-KR-135226.md", "Technology & Future/2026-10-21-EN-135226.md"]
        selection = self.select([KR, EN] + old, {KR: "published: false\n", EN: "published: false\n"})
        self.assertEqual([p.name for p in selection.posts], ["2026-10-21-EN-135226.md", "2026-10-21-KR-135226.md"])
        self.assertEqual({(p.name, reason) for p, reason in selection.skipped},
                         {("2026-10-25-KR-101307.md", "published: false"), ("2026-10-25-EN-101307.md", "published: false")})
        self.assertEqual(selection.total, 4)

    def test_only_the_unpublished_half_of_a_pair_is_dropped(self):
        selection = self.select([KR, EN, "a/2026-10-21-KR-000001.md"], {EN: "published: False\n"})
        self.assertEqual([p.name for p in selection.posts], ["2026-10-25-KR-101307.md"])
        self.assertEqual([p.name for p, _ in selection.skipped], ["2026-10-25-EN-101307.md"])

    def test_quoted_false_is_treated_as_unpublished_on_purpose(self):
        selection = self.select([KR, "a/2026-10-21-KR-000001.md"], {KR: 'published: "false"\n'})
        self.assertEqual([p.name for p in selection.posts], ["2026-10-21-KR-000001.md"])

    def test_published_false_written_with_a_quoted_key_or_a_space_still_skips_the_post(self):
        """N-4: 이런 표기를 '공개'로 읽으면 사이트에 없는 글의 주소를 열어 404 로 빨강이 된다."""
        for line in ("published : false", '"published": false', "'published': no", '"published" : off'):
            with self.subTest(line=line):
                with tempfile.TemporaryDirectory() as tmp:
                    make_repo(tmp, [KR, "a/2026-10-21-KR-000001.md"], fronts={KR: line + "\n"})
                    selection = v.select_newest(tmp, NOW, KST)
                self.assertEqual([p.name for p in selection.posts], ["2026-10-21-KR-000001.md"])
                self.assertEqual([(p.name, reason) for p, reason in selection.skipped], [("2026-10-25-KR-101307.md", "published: false")])

    def test_everything_unpublished_means_nothing_to_check(self):
        selection = self.select([KR, EN], {KR: "published: false\n", EN: "published: no\n"})
        self.assertEqual(selection.posts, [])
        self.assertEqual(len(selection.skipped), 2)
        self.assertEqual(selection.total, 2)

    def test_published_true_and_unreadable_front_matter_are_checked(self):
        selection = self.select([KR, EN], {KR: "published: true\n", EN: "permalink: |\n"})
        self.assertEqual(len(selection.posts), 2)

    def test_a_future_date_in_front_matter_is_skipped(self):
        # NOW 는 한국 시간 2026-10-25 21:00
        names = [KR, "a/2026-10-21-KR-000001.md"]
        for date_text, expected in (("2026-10-26 09:00:00 +0900", "2026-10-21-KR-000001.md"),
                                    ("2026-10-25 21:00:01 +0900", "2026-10-21-KR-000001.md"),
                                    ("2026-10-25 21:00:00 +0900", "2026-10-25-KR-101307.md"),  # 지금 시각과 같으면 공개
                                    ("2026-10-25 20:59:59 +0900", "2026-10-25-KR-101307.md"),
                                    ("2026-10-25 12:00:01 UTC", "2026-10-21-KR-000001.md"),
                                    ("2026-10-24", "2026-10-25-KR-101307.md"),
                                    ("2026-10-27", "2026-10-21-KR-000001.md")):
            with self.subTest(date=date_text):
                with tempfile.TemporaryDirectory() as tmp:
                    make_repo(tmp, names, fronts={KR: f"date: {date_text}\n"})
                    selection = v.select_newest(tmp, NOW, KST)
                    self.assertEqual([p.name for p in selection.posts], [expected])
                    if expected != "2026-10-25-KR-101307.md":
                        self.assertIn("미래", selection.skipped[0][1])

    def test_a_future_filename_date_is_skipped_in_the_site_time_zone(self):
        names = ["a/2026-10-26-KR-000001.md", "a/2026-10-25-KR-000001.md"]
        make_repo(self.root, names)
        # 2026-10-26 자정(한국)은 2026-10-25 15:00 UTC: 그 전에는 미래, 그 뒤에는 공개
        before = v.select_newest(self.root, datetime(2026, 10, 25, 14, 59, tzinfo=timezone.utc), KST)
        self.assertEqual([p.name for p in before.posts], ["2026-10-25-KR-000001.md"])
        after = v.select_newest(self.root, datetime(2026, 10, 25, 15, 0, tzinfo=timezone.utc), KST)
        self.assertEqual([p.name for p in after.posts], ["2026-10-26-KR-000001.md"])

    def test_the_site_time_zone_changes_the_answer(self):
        make_repo(self.root, ["a/2026-10-26-KR-000001.md", "a/2026-10-25-KR-000001.md"])
        now = datetime(2026, 10, 25, 16, 0, tzinfo=timezone.utc)  # 한국 시간으로는 이미 10-26
        self.assertEqual([p.name for p in v.select_newest(self.root, now, KST).posts], ["2026-10-26-KR-000001.md"])
        self.assertEqual([p.name for p in v.select_newest(self.root, now, timezone.utc).posts], ["2026-10-25-KR-000001.md"])

    def test_front_matter_date_overrides_the_filename_date_for_the_future_test(self):
        # 파일명은 과거지만 date 가 미래면 Jekyll 은 빼 버린다
        selection = self.select([KR, "a/2026-10-21-KR-000001.md"], {KR: "date: 2030-01-01\n"})
        self.assertEqual([p.name for p in selection.posts], ["2026-10-21-KR-000001.md"])
        # 반대로 파일명이 미래여도 date 가 과거면 공개
        with tempfile.TemporaryDirectory() as tmp:
            make_repo(tmp, ["a/2026-11-30-KR-000001.md"], fronts={"a/2026-11-30-KR-000001.md": "date: 2026-10-01\n"})
            self.assertEqual(len(v.select_newest(tmp, NOW, KST).posts), 1)

    def test_an_unreadable_date_falls_back_to_the_filename_date(self):
        selection = self.select([KR], {KR: "date: someday\n"})
        self.assertEqual(len(selection.posts), 1)


class SiteConfigTest(TempDirCase):
    def config(self, text):
        self.write("_config.yml", text)
        return v.read_site_config(self.root)

    def test_reads_top_level_permalink_and_timezone(self):
        self.assertEqual(self.config(SITE_CONFIG), {"timezone": "Asia/Seoul", "permalink": "/posts/:year/:month/:day/:title/"})

    def test_quotes_comments_and_bom(self):
        self.assertEqual(self.config(chr(0xFEFF) + 'timezone: "Asia/Seoul" # 한국\npermalink: \'/p/:title/\'\n'),
                         {"timezone": "Asia/Seoul", "permalink": "/p/:title/"})

    def test_nested_and_commented_permalinks(self):
        self.assertEqual(self.config("permalink: /a/\ndefaults:\n  - values:\n      permalink: /b/\n"),
                         {"permalink": "/a/", "nested_permalink": True})
        self.assertEqual(self.config("collections:\n  posts:\n    permalink: /c/\n"), {"nested_permalink": True})
        self.assertEqual(self.config("# permalink: /a/\n  # permalink: /b/\ntitle: t\n"), {})

    def test_quoted_keys_and_spaces_before_the_colon(self):
        self.assertEqual(self.config('"permalink": /p/\n\'timezone\' : Asia/Seoul\n'), {"permalink": "/p/", "timezone": "Asia/Seoul"})
        self.assertEqual(self.config("permalink : /p/\ntimezone  : UTC\n"), {"permalink": "/p/", "timezone": "UTC"})
        self.assertEqual(self.config('defaults:\n  - values:\n      "permalink": /b/\n'), {"nested_permalink": True})
        self.assertEqual(self.config("collections:\n  posts:\n    permalink : /c/\n"), {"nested_permalink": True})
        self.assertEqual(self.config("defaults:\n  - values:\n      'permalink' : /b/\n"), {"nested_permalink": True})
        self.assertEqual(self.config('"permalink\': /x/\n\'timezone": UTC\n'), {})

    def test_keyword_permalink_is_kept_as_text(self):
        self.assertEqual(self.config("permalink: pretty\n"), {"permalink": "pretty"})

    def test_missing_file_is_empty(self):
        self.assertEqual(v.read_site_config(self.root / "nope"), {})

    def test_site_timezone(self):
        for config, hours in (({"timezone": "Asia/Seoul"}, 9), ({"timezone": "asia/seoul"}, 9), ({"timezone": "UTC"}, 0),
                              ({"timezone": "Etc/UTC"}, 0), ({"timezone": "America/New_York"}, 0), ({}, 0), ({"timezone": None}, 0)):
            with self.subTest(config=config):
                self.assertEqual(v.site_timezone(config).utcoffset(None), timedelta(hours=hours))


class JekyllSlugTest(unittest.TestCase):
    def test_pretty_cased_slugs(self):
        for text, expected in (("KR-101307", "KR-101307"), ("AI", "AI"), ("My Post", "My-Post"), ("a  b", "a-b"),
                               (" lead trail ", "lead-trail"), ("Hello, World!", "Hello,-World!"), ("한글 제목", "한글-제목"),
                               ("a/b", "a-b"), ("a%b", "a-b"), ("100%", "100"), ("x.y_z~w", "x.y_z~w"), ("a---b", "a-b"),
                               ("-a-", "a"), ("", ""), ("%%%", ""), ("café", "café"), ("a?b#c", "a-b-c"), ("a" + chr(0x200B) + "b", "a-b"), ("cafe" + chr(0x301), "cafe"), ("Ⅳ장", "Ⅳ장")):
            with self.subTest(text=text):
                self.assertEqual(v.jekyll_slug(text), expected)


class ExpectedUrlTest(unittest.TestCase):
    CONFIG = {"timezone": "Asia/Seoul", "permalink": "/posts/:year/:month/:day/:title/"}

    def url(self, post, config=None, base=BASE):
        return v.expected_url(base, post, self.CONFIG if config is None else config, KST)

    def test_default_pattern_from_the_file_name(self):
        self.assertEqual(self.url(post_of()), (BASE + "posts/2026/10/25/KR-101307/", ""))
        self.assertEqual(self.url(post_of("2026-01-02-AI.md"))[0], BASE + "posts/2026/01/02/AI/")

    def test_front_matter_date_wins_and_is_converted_to_the_site_time_zone_like_jekyll(self):
        cases = (("2026-10-20 00:30:00 +0900", "2026/10/20"),  # 사이트 시간대와 같은 오프셋: UTC 로는 19일이어도 20일
                 ("2026-10-20 23:30:00 -0500", "2026/10/21"),  # 한국 시간으로는 21일 13:30
                 ("2026-10-20 20:00:00", "2026/10/21"),  # 시간대 없이 초까지 있으면 UTC 20:00 = 한국 21일 05:00
                 ("2026-10-20 20:00", "2026/10/20"),  # 초가 없으면 사이트 시간대 그대로
                 ("2025-01-02", "2025/01/02"), ("nonsense", "2026/10/25"))
        for text, day in cases:
            with self.subTest(date=text):
                self.assertEqual(self.url(post_of(front={"date": text}))[0], BASE + f"posts/{day}/KR-101307/")

    def test_front_matter_slug_replaces_the_file_name_slug(self):
        self.assertEqual(self.url(post_of(front={"slug": "My Custom Slug"}))[0], BASE + "posts/2026/10/25/My-Custom-Slug/")
        self.assertEqual(self.url(post_of(front={"slug": None}))[0], BASE + "posts/2026/10/25/KR-101307/")

    def test_a_posts_own_permalink_wins_over_the_site_pattern(self):
        post = post_of(front={"permalink": "/posts/2026/10/20/korean-food-date-labels/"})
        self.assertEqual(self.url(post), (BASE + "posts/2026/10/20/korean-food-date-labels/", ""))
        self.assertEqual(self.url(post, config={})[0], BASE + "posts/2026/10/20/korean-food-date-labels/")  # 사이트 설정이 없어도
        post = post_of(front={"permalink": "/news/:year/:title/"})
        self.assertEqual(self.url(post)[0], BASE + "news/2026/KR-101307/")

    def test_unreadable_or_unsupported_own_permalink_cannot_be_computed(self):
        for front in ({"permalink": None}, {"permalink": "/x/:categories/"}, {"permalink": "pretty"}, {"permalink": "x/y/"}):
            with self.subTest(front=front):
                url, why = self.url(post_of(front=front))
                self.assertIsNone(url)
                self.assertTrue(why)

    def test_site_patterns_that_are_not_computed(self):
        for config in ({"permalink": "pretty"}, {"permalink": "date"}, {"permalink": "/:categories/:year/:title/"},
                       {"permalink": "/:year/:month/:day/:title:output_ext"}, {"permalink": "/:year/:slug/"},
                       {"permalink": "/:short_year/:title/"}, {"permalink": "/:year_x/:title/"}, {"permalink": "/:title_x/"}, {"permalink": ""}, {"permalink": None}, {}, {"timezone": "UTC"},
                       {"permalink": "/posts/:year/:title/", "nested_permalink": True}):
            with self.subTest(config=config):
                url, why = self.url(post_of(), config=config)
                self.assertIsNone(url)
                self.assertTrue(why)

    def test_own_permalink_is_used_even_when_the_site_config_is_nested(self):
        post = post_of(front={"permalink": "/p/"})
        self.assertEqual(self.url(post, config={"permalink": "/a/:title/", "nested_permalink": True})[0], BASE + "p/")

    def test_non_ascii_slugs_are_percent_encoded(self):
        post = post_of("2026-10-25-한글 제목.md")
        self.assertEqual(self.url(post)[0], BASE + "posts/2026/10/25/%ED%95%9C%EA%B8%80-%EC%A0%9C%EB%AA%A9/")
        self.assertTrue(self.url(post)[0].isascii())

    def test_dot_sequences_and_slashes_are_cleaned_like_jekyll(self):
        for permalink in ("/a/../b/", "/a/./b/", "/a//b///", "/a/b/"):
            with self.subTest(permalink=permalink):
                self.assertEqual(self.url(post_of(front={"permalink": permalink}))[0], BASE + "a/b/")
        self.assertEqual(self.url(post_of("2026-10-25-a..b.md"))[0], BASE + "posts/2026/10/25/a/b/")
        self.assertEqual(self.url(post_of("2026-10-25-end..md"))[0], BASE + "posts/2026/10/25/end")  # "./" 와 함께 끝 슬래시도 지워진다
        self.assertIsNone(self.url(post_of("2026-10-25-%%%.md"))[0])  # slug 가 비면 계산하지 않는다

    def test_base_is_joined_without_a_double_slash(self):
        self.assertEqual(self.url(post_of(), base="https://x.github.io/")[0], "https://x.github.io/posts/2026/10/25/KR-101307/")
        self.assertNotIn("//posts", self.url(post_of())[0])

    def test_reserved_characters_follow_jekyll_escaping(self):
        url = self.url(post_of(front={"permalink": "/a b/c?d/e#f/"}))[0]
        self.assertEqual(url, BASE + "a%20b/c%3Fd/e%23f/")
        self.assertEqual(self.url(post_of(front={"permalink": "/a,b;c=d/"}))[0], BASE + "a,b;c=d/")


class RealRepositoryTest(unittest.TestCase):
    """실제 저장소의 `_posts`·`_config.yml`을 공개 사이트 사본(PUBLIC_SNAPSHOT)과 대조한다. 사이트에는 접속하지 않는다."""

    ROOT = _bootstrap.ROOT

    def setUp(self):
        self.config = v.read_site_config(self.ROOT)
        self.tz = v.site_timezone(self.config)
        self.posts = {c.rel: v.Post(c.rel, c.name, c.file_date, c.slug, v.read_front_matter(c.path))
                      for c in v.find_candidates(self.ROOT)}

    def test_computed_addresses_match_the_public_site_for_every_published_post(self):
        present = [rel for rel in PUBLIC_SNAPSHOT if rel in self.posts]
        if not present:
            self.skipTest("스냅샷의 글이 저장소에 더 이상 없다")
        for rel in present:
            with self.subTest(rel=rel):
                post = self.posts[rel]
                self.assertIsNone(v.ineligible_reason(post, NOW, self.tz))
                url, why = v.expected_url(REAL_BASE, post, self.config, self.tz)
                self.assertEqual(url, PUBLIC_SNAPSHOT[rel], f"주소 계산이 공개 사이트와 다르다({why}). _config.yml permalink 가 바뀌었다면 스냅샷을 갱신한다")

    def test_exactly_the_posts_missing_from_the_public_site_are_unpublished(self):
        present = [rel for rel in PUBLIC_MISSING if rel in self.posts]
        if not present:
            self.skipTest("스냅샷에 없던 글이 저장소에 더 이상 없다")
        for rel in present:
            with self.subTest(rel=rel):
                self.assertEqual(v.ineligible_reason(self.posts[rel], NOW, self.tz), "published: false")

    def test_config_is_a_pattern_the_script_can_compute(self):
        self.assertIn("permalink", self.config)
        self.assertFalse(self.config.get("nested_permalink"))
        post = next(iter(self.posts.values()))
        self.assertIsNotNone(v.expected_url(REAL_BASE, post, self.config, self.tz)[0])

    def test_the_newest_posts_of_the_real_repository_get_a_computed_address(self):
        selection = v.select_newest(self.ROOT, datetime.now(timezone.utc), self.tz)
        self.assertTrue(selection.posts)
        for post in selection.posts:
            url, why = v.expected_url(REAL_BASE, post, self.config, self.tz)
            self.assertTrue(url and url.startswith(REAL_BASE) and url.endswith("/"), f"{post.rel}: {url} {why}")

    def test_unpublished_newest_pair_scenario_on_a_copy_of_the_real_posts(self):
        """가장 새 KR/EN 쌍을 published: false 로 바꾸면(정상 사이트) 그다음 쌍을 확인 대상으로 삼는다."""
        with tempfile.TemporaryDirectory() as tmp:
            shutil.copytree(self.ROOT / "_posts", Path(tmp) / "_posts")
            first = v.select_newest(tmp, datetime.now(timezone.utc), self.tz).posts
            self.assertTrue(first)
            for post in first:
                path = Path(tmp) / post.rel
                text = path.read_text(encoding="utf-8")
                # 글마다 front matter 줄이 다르다(봇 글은 layout 줄이 없을 수 있다 — 2026-10-26 18시 글). 맨 위 `---` 바로 아래에 넣는다
                head, sep, rest = text.partition("\n")  # read_text 가 줄바꿈을 \n 으로 읽는다
                self.assertEqual(head, "---", post.rel)
                path.write_text(head + sep + "published: false\n" + rest, encoding="utf-8", newline="")
            second = v.select_newest(tmp, datetime.now(timezone.utc), self.tz)
            self.assertTrue(second.posts)
            self.assertFalse({p.rel for p in first} & {p.rel for p in second.posts})
            self.assertTrue({p.rel for p in first} <= {p.rel for p, _ in second.skipped})
            self.assertLess(key_of(second.posts[0]), key_of(first[0]))


if __name__ == "__main__":
    unittest.main()
