"""게시글 이미지 URL 검증의 회귀 테스트 — docs/DEFECT_REGISTER.md D-38.

접두사(https://images.unsplash.com/)만 보던 검사를 엄격한 주소 형식 + 허용 호스트 + '주소 외 내용 불변'으로 바꿨고,
생성 직후 검증(runner)과 PR 범위 검사(scope_check)가 같은 함수(checks.verify_image_change)를 쓴다.
"""
import re
import tempfile
import unittest
from unittest import mock

import _bootstrap  # noqa: F401
from edits_helpers import REAL, image_body, img, issue, make_edit_root, post_text, write
from pipeline.edits import checks, frontmatter, ops
import test_edits_runner
from test_edits_runner import RunnerBase, Snapshot

REAL_STYLE = "https://images.unsplash.com/photo-1614728894747-a83421e2b9c9?auto=format&fit=crop&w=1000&q=80"
NEW = img("777")
BAD_URLS = [
    "https://images.unsplash.com/photo-1) [x](https://evil.example/a",       # 접두사만 맞고 뒤에 마크다운 링크가 붙은 값(검증자 재현)
    "https://images.unsplash.com/photo-1)",
    "https://images.unsplash.com@evil.example/photo-1",                      # userinfo 로 호스트 위장
    "https://user:pw@images.unsplash.com/photo-1",
    "https://images.unsplash.com/photo-1\"onerror=\"x",
    "https://images.unsplash.com/photo-1'x",
    "https://images.unsplash.com/photo-1 x",
    "https://images.unsplash.com/photo-1\nx",
    "https://images.unsplash.com/photo-1\n",                                 # 끝 개행(정규식 $ 는 이를 통과시킨다)
    "https://images.unsplash.com/photo-1]", "https://images.unsplash.com/photo-1<", "https://images.unsplash.com/photo-1>",
    "https://images.unsplash.com/photo-1`", "https://images.unsplash.com/photo-1\\x", "(https://images.unsplash.com/photo-1",
    "http://images.unsplash.com/photo-1",
    "https://evil.example/photo-1", "https://images.unsplash.com.evil.example/photo-1",
    "https://evil.example/images.unsplash.com/photo-1", "https://IMAGES.UNSPLASH.COM/photo-1", "//images.unsplash.com/photo-1",
    "https://images.unsplash.com:443/photo-1", "https://images.unsplash.com/photo-1#frag",
    "https://images.unsplash.com/other/photo-1", "https://images.unsplash.com/photo-1/extra", "https://images.unsplash.com/photo-",
    "https://images.unsplash.com/photo-1?", "https://images.unsplash.com/photo-1?x=%zz", "https://images.unsplash.com/photo-1?x=<script>",
    "https://images.unsplash.com/../photo-1", "https://images.unsplash.com/photo-1?a=b c",
    "https://images.unsplash.com/photo-" + "1" * 65, "https://images.unsplash.com/photo-1?" + "a" * 301,
    # 'unsplash.com 으로 끝나는 호스트'가 아니라 images.unsplash.com 하나만 허용한다(검증자 V09)
    "https://plus.unsplash.com/photo-1", "https://unsplash.com/photo-1", "https://api.unsplash.com/photo-1", "https://evilunsplash.com/photo-1",
    "https://ximages.unsplash.com/photo-1", "https://images.unsplash.com.evil.example/photo-1",
    # 질의에는 영숫자와 _ . = & - 와 %XX 만(검증자 V10): 경로·사용자 정보·쉼표·세미콜론으로 이어 붙이는 값은 거부
    "https://images.unsplash.com/photo-1?a=b:c", "https://images.unsplash.com/photo-1?a=b/c", "https://images.unsplash.com/photo-1?a=b@c",
    "https://images.unsplash.com/photo-1?a=b+c", "https://images.unsplash.com/photo-1?a=b,c", "https://images.unsplash.com/photo-1?a=b;c",
    "https://images.unsplash.com/photo-1?a=b(c)", "https://images.unsplash.com/photo-1?a=b%", "https://images.unsplash.com/photo-1?a=b%4",
    "", None, 123, ["https://images.unsplash.com/photo-1"],
]


class UrlFormatTest(unittest.TestCase):
    def test_generated_and_real_style_urls_pass(self):
        for url in (img("111"), REAL_STYLE, "https://images.unsplash.com/photo-1614728894747-a83421e2b9c9",
                    "https://images.unsplash.com/photo-1506744038136-46273834b3fb?ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D&auto=format&fit=crop&w=1000&q=80"):
            self.assertIsNone(checks.image_url_problem(url), url)
            self.assertTrue(checks.is_safe_image_url(url))

    def test_hostile_or_malformed_urls_are_rejected(self):
        for url in BAD_URLS:
            self.assertFalse(checks.is_safe_image_url(url), repr(url))
            self.assertTrue(checks.image_url_problem(url), repr(url))

    def test_reasons_never_echo_the_value_and_host_is_reported_separately(self):
        self.assertNotIn("evil.example", checks.image_url_problem("https://evil.example/photo-1"))
        self.assertIn("호스트", checks.image_url_problem("https://evil.example/photo-1"))
        self.assertNotIn("evil.example", checks.image_url_problem(BAD_URLS[0]))
        self.assertIn("형식", checks.image_url_problem(BAD_URLS[0]))

    def test_only_the_unsplash_image_host_is_allowed(self):
        self.assertEqual(checks.IMAGE_HOSTS, ("images.unsplash.com",))      # 호스트 추가는 T3 — 늘리면 이 테스트가 알려 준다


class RealPostsTest(unittest.TestCase):
    """저장소의 실제 글: 기존 이미지 주소가 모두 새 검증을 통과하고, 교체·추가 결과도 통과한다."""

    @classmethod
    def setUpClass(cls):
        cls.posts = {p.relative_to(REAL).as_posix(): frontmatter.read_file(p)[0] for p in sorted((REAL / "_posts").rglob("*.md"))}

    def test_every_existing_image_url_passes(self):
        urls = [u for text in self.posts.values() for u in re.findall(r"https://images\.unsplash\.com/[^\s\"')]+", text)]
        self.assertGreaterEqual(len(urls), 18)           # 작성 시점에 글 18편(주소 24건 이상)이었다 — 글은 늘기만 한다
        bad = [u for u in urls if not checks.is_safe_image_url(u)]
        self.assertEqual(bad, [])

    def test_every_real_post_accepts_replacement_or_addition(self):
        checked = 0
        for rel, text in self.posts.items():
            old_url, data = checks.front_matter_image(text)
            if data is None:
                continue
            after = ops.apply_image(text, old_url, NEW)
            self.assertEqual(checks.verify_image_change(text, after), [], rel)
            checked += 1
        self.assertGreaterEqual(checked, 10)


class VerifyImageChangeTest(unittest.TestCase):
    BASE = post_text("첫 번째 글 제목입니다", img("111"))

    def reasons(self, after, before=None):
        return checks.verify_image_change(self.BASE if before is None else before, after)

    def test_replacing_the_url_everywhere_passes(self):
        self.assertEqual(self.reasons(self.BASE.replace(img("111"), NEW)), [])

    def test_front_matter_only_or_body_only_replacement_is_rejected(self):
        fm_only = self.BASE.replace(f'image: "{img("111")}"', f'image: "{NEW}"')
        self.assertTrue(self.reasons(fm_only))          # 본문 이미지가 옛 주소로 남음
        body_only = self.BASE.replace(f"![설명]({img('111')})", f"![설명]({NEW})")
        self.assertTrue(any("바뀌지 않았습니다" in r for r in self.reasons(body_only)))

    def test_any_other_change_alongside_the_url_is_rejected(self):
        swapped = self.BASE.replace(img("111"), NEW)
        for after in (swapped.replace("본문 문장입니다.", "본문을 마음대로 고쳤습니다."), swapped + "\n![몰래](https://evil.example/pixel.png)\n",
                      swapped.replace('title: "첫 번째 글 제목입니다"', 'title: "바뀐 제목"'), swapped.replace("lang: ko", "lang: en")):
            self.assertTrue(any("주소 외의 내용" in r for r in self.reasons(after)), after)

    def test_invalid_new_urls_are_rejected_without_echoing_them(self):
        for bad in (BAD_URLS[0], BAD_URLS[2], "https://evil.example/photo-1", "javascript:alert(1)"):
            reasons = self.reasons(self.BASE.replace(img("111"), bad))
            self.assertTrue(reasons, bad)
            self.assertFalse(any("evil.example" in r or "javascript" in r for r in reasons), reasons)

    def test_removing_the_image_or_duplicating_the_key_is_rejected(self):
        removed = self.BASE.replace(f'image: "{img("111")}"\n', "").replace(f"![설명]({img('111')})\n", "")
        self.assertTrue(self.reasons(removed))
        duplicated = self.BASE.replace(img("111"), NEW).replace(f'image: "{NEW}"', f'image: "{img("222")}"\nimage: "{NEW}"', 1)
        self.assertTrue(any("image 줄이 둘 이상" in r for r in self.reasons(duplicated)))

    def test_adding_an_image_to_a_post_without_one_is_fine_but_nothing_else(self):
        bare = "---\nlayout: post\ntitle: \"이미지 없는 글\"\ncategory: x\n---\n\n본문 문장입니다.\n"
        added = bare.replace("category: x\n", f'category: x\nimage: "{NEW}"\n')
        self.assertEqual(checks.verify_image_change(bare, added), [])
        self.assertEqual(checks.verify_image_change(bare, ops.apply_image(bare, "", NEW)), [])
        self.assertTrue(checks.verify_image_change(bare, added.replace("본문 문장입니다.", "본문 변경")))
        self.assertTrue(checks.verify_image_change(bare, added + f"\n![x]({NEW})\n"))        # 본문에 이미지를 끼워 넣는 것은 범위 밖
        self.assertTrue(checks.verify_image_change(bare, added.replace("category: x", "category: y")))

    def test_a_front_matter_line_that_merely_mentions_image_is_still_compared(self):
        """검증자 V11: 이미지 줄을 빼고 비교할 때 `image:` 로 시작하는 줄만 뺀다 — 줄 중간에 `image:` 가 든 다른 항목(description 등)의 변경은 잡아야 한다."""
        bare = '---\nlayout: post\ntitle: "이미지 없는 글"\ndescription: "see image: a"\ncategory: x\n---\n\n본문 문장입니다.\n'
        added = bare.replace("category: x\n", f'category: x\nimage: "{NEW}"\n')
        self.assertEqual(checks.verify_image_change(bare, added), [])
        changed = added.replace("see image: a", "see image: CHANGED")
        self.assertTrue(any("주소 외의 내용" in r for r in checks.verify_image_change(bare, changed)))

    def test_front_matter_must_be_readable(self):
        self.assertTrue(checks.verify_image_change("front matter 없음\n", f"---\nimage: {NEW}\n---\n"))
        self.assertTrue(checks.verify_image_change(self.BASE, "front matter 없음\n"))

    def test_placeholder_lookalike_text_cannot_hide_a_body_change(self):
        marker = "\0IMAGE-URL\0"
        before = f'---\ntitle: t\nimage: "{img("111")}"\n---\n\n그림: {img("111")}\n'
        after = f'---\ntitle: t\nimage: "{NEW}"\n---\n\n그림: {marker}\n'
        self.assertTrue(checks.verify_image_change(before, after))


class OpImageUsesStrictCheckTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = make_edit_root(self._tmp.name)
        self.rel = "_posts/KR - 테크/2026-10-18-KR-111111.md"
        self.text = (self.root / self.rel).read_bytes().decode("utf-8")

    def test_picker_output_with_a_matching_prefix_but_a_bad_tail_is_rejected(self):
        post = {"path": self.rel, "title": "t"}
        for bad in BAD_URLS[:12] + [REAL_STYLE.replace("photo-", "x-")]:
            with self.assertRaises(ops.EditError, msg=bad):
                ops.op_image(self.text, {"user_prompt": "x"}, post, self.root, None, lambda q, u, b=bad: b)
        new, _how = ops.op_image(self.text, {"user_prompt": "x"}, post, self.root, None, lambda q, u: REAL_STYLE)
        self.assertIn(REAL_STYLE, new)


class RunnerVerifiesImageChangeTest(RunnerBase):
    def test_runner_rejects_an_image_edit_that_also_touches_the_body(self):
        """apply_image 가 잘못 만든 결과(주소 외 변경)도 사후 검증이 막는다 — 같은 verify_image_change 를 쓴다."""
        iss = issue(image_body(test_edits_runner.ImageEditTest.URL, "소방관"), labels=("blog-control", "edit:image"), title="[이미지 변경] x")
        before = self.read(test_edits_runner.ImageEditTest.REL)
        with mock.patch.object(ops, "apply_image", side_effect=lambda t, o, n: t.replace(o, n) + "\n몰래 붙인 문장입니다.\n"):
            res = self.go(iss, image_picker=lambda q, u: NEW)
        self.assertRejected(res, "주소 외의 내용")
        self.assertEqual(self.read(test_edits_runner.ImageEditTest.REL), before)


class ScopeCheckImageTest(unittest.TestCase):
    NO_IMAGE_REL = "_posts/2026-10-21-KR-777777.md"
    NO_IMAGE = "---\nlayout: post\ntitle: \"이미지 없는 글 제목입니다\"\ncategory: x\n---\n\n본문 문장입니다.\n"

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = make_edit_root(self._tmp.name)
        write(self.root, self.NO_IMAGE_REL, self.NO_IMAGE)
        self.snap = Snapshot(self.root)
        self.rel = "_posts/KR - 테크/2026-10-18-KR-111111.md"

    def check(self, target, rel, after):
        iss = issue(image_body(target, "소방관"), labels=("blog-control", "edit:image"))
        return self.snap.check(self.root, iss, self.snap.head(edits={rel: after}))

    def test_replacement_passes(self):
        text = self.snap.base[self.rel]
        report = self.check("첫 번째 글 제목입니다", self.rel, text.replace(img("111"), NEW))
        self.assertEqual(report.verdict, "PASS", report.items)
        self.assertIn("대표 이미지 URL 만", report.markdown())

    def test_adding_an_image_to_a_post_without_one_passes_with_accurate_wording(self):
        after = self.NO_IMAGE.replace("category: x\n", f'category: x\nimage: "{NEW}"\n')
        report = self.check("이미지 없는 글 제목입니다", self.NO_IMAGE_REL, after)
        text = report.markdown()
        self.assertEqual(report.verdict, "PASS", report.items)
        self.assertIn("이미지가 없던 글에", text)
        self.assertNotIn("Unsplash 주소가 아닙니다", text)          # 예전의 부정확한 FAIL 문구

    def test_prefix_only_match_and_other_hosts_fail(self):
        text = self.snap.base[self.rel]
        for bad in (BAD_URLS[0], "https://evil.example/a.jpg", "https://images.unsplash.com@evil.example/photo-1"):
            report = self.check("첫 번째 글 제목입니다", self.rel, text.replace(img("111"), bad))
            self.assertEqual(report.verdict, "FAIL", bad)
            self.assertNotIn("evil.example", report.markdown(), bad)
            self.assertNotIn("이미지 교체 외의 변경이 있거나", report.markdown())

    def test_body_edit_alongside_the_image_fails(self):
        text = self.snap.base[self.rel]
        sneaky = text.replace(img("111"), NEW).replace("본문 문장입니다.", "본문을 마음대로 고쳤습니다.")
        self.assertEqual(self.check("첫 번째 글 제목입니다", self.rel, sneaky).verdict, "FAIL")


if __name__ == "__main__":
    unittest.main()
