"""이슈 수정(pipeline/edits)의 게시글 이미지 교체에서 Unsplash 사진의 ixid 와 작가 출처 줄 — 옛 줄은 지우고 새 줄을 새 이미지 줄 바로 다음에 넣는다. 네트워크 없이 돈다.

구성
  1) 허용 주소 형식(checks.image_url_problem): 실제 ixid 값(영숫자·`-`·`_`·`=`·%3D)과 `?ixid=…&auto=format…` 순서를 받는다 — 허용 호스트·경로 제한은 그대로.
  2) 교체 결과(ops.apply_image·op_image): 옛 줄 교체·멱등·선택기가 줄을 주지 않을 때·위조 줄 제거.
  3) 사후 검증(checks.verify_image_change): 우리 줄의 교체만 허용하고 다른 글·둘 이상·엉뚱한 자리는 거부.
  4) 처리기 전체(runner.process_issue)와 운영 선택기(default_image_picker)가 출처 줄을 함께 다룬다.
"""
import os
import tempfile
import unittest
from unittest import mock

import _bootstrap  # noqa: F401
import generator
from chance_credit_helpers import FAKE_KEY, PHOTO_RAW, FakeApi
from edits_helpers import image_body, img, issue, make_edit_root, post_text, write
from main_image_helpers import photo_item, results
from pipeline import main_image, unsplash_credit as uc
from pipeline.edits import checks, ops, runner, scope_check
import test_edits_runner
from test_edits_runner import RunnerBase, Snapshot

UTM = "utm_source=chanceblog&utm_medium=referral"
OLD = img("111")
NEW = "https://images.unsplash.com/photo-1500000000000-ccc333ddd44?ixid=M3wxfDB8&auto=format&fit=crop&w=1000&q=80"
OLD_LINE = uc.credit_markdown("Old Person", "https://unsplash.com/@oldperson")
NEW_LINE = uc.credit_markdown("Bob Lee", "https://unsplash.com/@boblee")
REL = "_posts/KR - 테크/2026-10-18-KR-111111.md"
TITLE = "첫 번째 글 제목입니다"


def with_credit(text, url, line):
    return uc.place_credit(text, url, line)


def credited(url, line):
    picked = uc.Credited(url)
    picked.credit = line
    return picked


class AllowedAddressTest(unittest.TestCase):
    def test_real_ixid_addresses_are_accepted(self):
        base = "https://images.unsplash.com/photo-1507146426996-ef05306b995a"
        for url in (f"{base}?ixid=M3wxfDB8&auto=format&fit=crop&w=1000&q=80", f"{base}?ixid=M3wxfDB8&w=1080&q=80&fm=jpg&fit=max&auto=format",
                    f"{base}?ixid=aZ09_-==&auto=format&fit=crop&w=1000&q=80", f"{base}?ixid={'A' * 200}&auto=format&fit=crop&w=1000&q=80",
                    f"{base}?ixid=MXwxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHw%3D&auto=format&fit=crop&w=1000&q=80",
                    f"{base}?ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D&auto=format&fit=crop&w=1000&q=80"):
            self.assertIsNone(checks.image_url_problem(url), url)
            self.assertTrue(checks.is_safe_image_url(url))

    def test_the_limits_did_not_move(self):
        base = "https://images.unsplash.com/photo-1507146426996-ef05306b995a"
        for url in (f"{base}?ixid=a+b&w=1", f"{base}?ixid=a/b&w=1", f"{base}?ixid=a:b&w=1", f"{base}?ixid=a,b&w=1", f"{base}?ixid=a;b&w=1", f"{base}?ixid=a(b)&w=1", f"{base}?ixid=a b&w=1",
                    f"{base}?ixid=a%&w=1", f"{base}?ixid={'A' * 301}", f"{base}?ixid=a\n", f"{base}?ixid=a'b",
                    "https://evil.example/photo-1?ixid=M3w&auto=format", "https://images.unsplash.com.evil.example/photo-1?ixid=M3w", "http://images.unsplash.com/photo-1?ixid=M3w",
                    "https://images.unsplash.com/uploads/1?ixid=M3w", "https://plus.unsplash.com/photo-1?ixid=M3w", "https://user@images.unsplash.com/photo-1?ixid=M3w", f"{base}?ixid=M3w#frag"):
            self.assertFalse(checks.is_safe_image_url(url), repr(url))
        self.assertEqual(checks.IMAGE_HOSTS, ("images.unsplash.com",))

    def test_every_address_the_engines_make_from_real_looking_responses_is_accepted(self):
        raws = ("https://images.unsplash.com/photo-1507146426996-ef05306b995a?ixid=M3wxfDB8&ixlib=rb-4.0.3", "https://images.unsplash.com/photo-1507146426996-ef05306b995a?ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D",
                "https://images.unsplash.com/photo-1507146426996-ef05306b995a", "https://images.unsplash.com/photo-1507146426996-ef05306b995a?ixid=bad value", "https://images.unsplash.com/photo-1507146426996-ef05306b995a?ixid=a%20b",
                "https://images.unsplash.com/photo-1507146426996-ef05306b995a?ixid=" + "A" * 300)
        for raw in raws:
            for url in (generator.build_image_url(raw), main_image.normalize_image_url(raw)):
                if url:
                    self.assertTrue(checks.is_safe_image_url(url), url)


class ApplyImageTest(unittest.TestCase):
    BEFORE = post_text(TITLE, OLD)

    def test_the_old_line_is_replaced_by_the_new_one_right_after_the_new_image_line(self):
        before = with_credit(self.BEFORE, OLD, OLD_LINE)
        after = ops.apply_image(before, OLD, NEW, NEW_LINE)
        lines = after.split("\n")
        self.assertEqual(lines[lines.index(f"![설명]({NEW})") + 1], NEW_LINE)
        self.assertNotIn("Old Person", after)
        self.assertNotIn(OLD, after)
        self.assertEqual(after.count(NEW), 2)                                   # 머리말 image 와 본문 이미지 줄
        self.assertEqual(checks.verify_image_change(before, after), [])

    def test_doing_the_same_swap_again_changes_nothing(self):
        before = with_credit(self.BEFORE, OLD, OLD_LINE)
        once = ops.apply_image(before, OLD, NEW, NEW_LINE)
        self.assertEqual(ops.apply_image(once, NEW, NEW, NEW_LINE), once)
        self.assertEqual(ops.apply_image(ops.apply_image(once, OLD, NEW, NEW_LINE), OLD, NEW, NEW_LINE), once)

    def test_a_post_without_a_line_gets_one(self):
        after = ops.apply_image(self.BEFORE, OLD, NEW, NEW_LINE)
        self.assertEqual(after.count("Photo by ["), 1)
        self.assertEqual(checks.verify_image_change(self.BEFORE, after), [])
        self.assertEqual(after.replace(NEW_LINE + "\n", "").replace(NEW, OLD), self.BEFORE)      # 그 밖에는 한 글자도 다르지 않다

    def test_without_a_new_line_the_old_one_goes_away_and_no_other_text_changes(self):
        before = with_credit(self.BEFORE, OLD, OLD_LINE)
        after = ops.apply_image(before, OLD, NEW)
        self.assertEqual(after, self.BEFORE.replace(OLD, NEW))
        self.assertEqual(checks.verify_image_change(before, after), [])

    def test_a_forged_line_in_the_body_is_removed_by_a_swap(self):
        forged = uc.credit_markdown("Evil Name", "https://unsplash.com/@evil")
        before = self.BEFORE.replace("본문 문장입니다.", f"{forged}\n\n본문 문장입니다.")
        after = ops.apply_image(before, OLD, NEW, NEW_LINE)
        self.assertNotIn("Evil Name", after)
        self.assertEqual(after.count("Photo by ["), 1)
        self.assertEqual(checks.verify_image_change(before, after), [])

    def test_a_post_with_front_matter_image_only_changes_nothing_in_the_body(self):
        bare = '---\nlayout: post\ntitle: "이미지 없는 글"\ncategory: x\n---\n\n본문 문장입니다.\n'
        after = ops.apply_image(bare, "", NEW, NEW_LINE)
        self.assertIn(f'image: "{NEW}"', after)
        self.assertNotIn("Photo by", after)                                      # 본문에 이미지 줄이 없다 → 붙일 곳이 없다
        self.assertEqual(checks.verify_image_change(bare, after), [])


class VerifyImageChangeCreditTest(unittest.TestCase):
    BEFORE = with_credit(post_text(TITLE, OLD), OLD, OLD_LINE)
    SWAPPED = BEFORE.replace(OLD, NEW).replace(OLD_LINE, NEW_LINE)

    def reasons(self, after, before=None):
        return checks.verify_image_change(self.BEFORE if before is None else before, after)

    def test_a_proper_swap_is_accepted(self):
        self.assertEqual(self.reasons(self.SWAPPED), [])

    def test_adding_or_dropping_the_line_alongside_the_new_address_is_accepted(self):
        plain = post_text(TITLE, OLD)
        self.assertEqual(self.reasons(plain.replace(OLD, NEW).replace(f"![설명]({NEW})\n", f"![설명]({NEW})\n{NEW_LINE}\n"), before=plain), [])
        self.assertEqual(self.reasons(self.BEFORE.replace(OLD, NEW).replace(OLD_LINE + "\n", "")), [])

    def test_two_lines_are_rejected(self):
        after = self.SWAPPED.replace(NEW_LINE, NEW_LINE + "\n" + OLD_LINE)
        self.assertTrue(any("둘 이상" in r for r in self.reasons(after)), self.reasons(after))

    def test_a_line_that_is_not_right_after_the_new_image_line_is_rejected(self):
        for after in (self.SWAPPED.replace(NEW_LINE + "\n", "") + f"\n{NEW_LINE}\n", self.SWAPPED.replace(NEW_LINE + "\n", "\n" + NEW_LINE + "\n"),
                      self.SWAPPED.replace(f"![설명]({NEW})\n{NEW_LINE}\n", f"{NEW_LINE}\n![설명]({NEW})\n")):
            self.assertTrue(any("바로 다음" in r for r in self.reasons(after)), after)

    def test_any_other_change_next_to_a_good_swap_is_still_rejected(self):
        for after in (self.SWAPPED.replace("본문 문장입니다.", "본문을 고쳤습니다."), self.SWAPPED + "\n몰래 붙인 문장입니다.\n", self.SWAPPED.replace('title: "', 'title: "바뀐 ')):
            self.assertTrue(any("주소 외의 내용" in r for r in self.reasons(after)), after)

    def test_lines_that_only_look_like_ours_are_ordinary_text_and_count_as_a_change(self):
        near = NEW_LINE.replace("unsplash.com/@boblee", "evil.example/@boblee")
        for after in (self.SWAPPED.replace(NEW_LINE, near), self.SWAPPED.replace(NEW_LINE, NEW_LINE.replace(UTM, "utm_source=other")),
                      self.SWAPPED.replace(NEW_LINE, NEW_LINE + " 더 붙인 말"), self.SWAPPED.replace(NEW_LINE, "<a href=\"https://evil.example\">Photo by x on Unsplash</a>")):
            self.assertTrue(any("주소 외의 내용" in r for r in self.reasons(after)), after)

    def test_a_name_cannot_carry_markup_into_the_line_the_verifier_accepts(self):
        hostile = uc.credit_markdown("]( https://evil.example ) <script>alert(1)</script> {{ 7*7 }}", "https://unsplash.com/@evil")
        after = self.SWAPPED.replace(NEW_LINE, hostile)
        self.assertEqual(self.reasons(after), [])                       # 모양은 우리 줄(이스케이프된 이름)이고 링크는 unsplash.com 뿐이다
        self.assertNotIn("](https://evil.example", after.replace("\\]", ""))
        self.assertNotIn("{", hostile)

    def test_a_line_with_the_right_shape_but_raw_markup_in_the_name_is_not_accepted_as_our_credit(self):
        """PR 범위 검사는 믿을 수 없는 PR 도 본다 — 틀만 닮고 이름에 이스케이프되지 않은 HTML·마크다운·Liquid 가 든 줄을 '우리 줄 교체'로 통과시키지 않는다."""
        template = "*Photo by [{name}](https://unsplash.com/@boblee?" + UTM + ") on [Unsplash](https://unsplash.com/?" + UTM + ")*"
        for name in ('<a href="https://evil.example">click</a>', "<img src=x>", "**bold**", "`x`", "{{ site.title }}", "a" + chr(0x200B) + "b", "N" * 200, "Bob  Lee"):
            hostile = template.replace("{name}", name)
            after = self.SWAPPED.replace(NEW_LINE, hostile)
            self.assertTrue(any("주소 외의 내용" in r for r in self.reasons(after)), name)

    def test_the_address_rules_still_apply_with_a_credit_line(self):
        for bad in ("https://evil.example/photo-1", "https://images.unsplash.com/photo-1)", "javascript:alert(1)"):
            after = self.BEFORE.replace(OLD, bad)
            self.assertTrue(self.reasons(after), bad)
            self.assertFalse(any("evil.example" in r for r in self.reasons(after)))


class OpImageCreditTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = make_edit_root(self._tmp.name)
        self.text = with_credit((self.root / REL).read_bytes().decode("utf-8"), OLD, OLD_LINE)
        write(self.root, REL, self.text)

    def op(self, picker):
        return ops.op_image(self.text, {"user_prompt": "소방관"}, {"path": REL, "title": TITLE}, self.root, None, picker)

    def test_a_picker_that_hands_over_a_credit_gets_it_placed(self):
        new, how = self.op(lambda q, u: credited(NEW, NEW_LINE))
        lines = new.split("\n")
        self.assertEqual(lines[lines.index(f"![설명]({NEW})") + 1], NEW_LINE)
        self.assertNotIn("Old Person", new)
        self.assertTrue(how.startswith("대표 이미지 교체 ("), how)
        self.assertEqual(checks.verify_image_change(self.text, new), [])

    def test_a_plain_string_picker_changes_the_address_and_clears_the_old_line(self):
        new, _how = self.op(lambda q, u: NEW)
        self.assertEqual(new, self.text.replace(OLD, NEW).replace(OLD_LINE + "\n", ""))
        self.assertEqual(checks.verify_image_change(self.text, new), [])

    def test_a_credit_in_a_wrong_shape_is_not_used(self):
        for bad in ("*Photo by [x](https://evil.example/@y) on [Unsplash](https://evil.example/)*", "아무 글", "<script>x</script>", OLD_LINE + "\n" + NEW_LINE, ""):
            new, _how = self.op(lambda q, u, bad=bad: credited(NEW, bad))
            self.assertNotIn("evil.example", new)
            self.assertNotIn("<script>", new)
            self.assertNotIn("Old Person", new)
            self.assertEqual(new.count("Photo by ["), 0, bad)

    def test_an_unsafe_address_is_still_refused_whatever_the_credit(self):
        for url in ("https://evil.example/a.jpg", "https://images.unsplash.com/photo-1)"):
            with self.assertRaises(ops.EditError):
                self.op(lambda q, u, url=url: credited(url, NEW_LINE))

    def test_the_picker_result_is_turned_into_a_plain_string_in_the_text(self):
        new, _how = self.op(lambda q, u: credited(NEW, NEW_LINE))
        self.assertIn(f'image: "{NEW}"', new)


class RunnerCreditTest(RunnerBase):
    def go_image(self, picker, target=TITLE):
        return self.go(issue(image_body(target, "소방관 구조 활동"), labels=("blog-control", "edit:image"), title="[이미지 변경] x"), image_picker=picker)

    def test_the_whole_edit_swaps_the_address_and_the_credit_and_passes_the_checks(self):
        write(self.root, REL, with_credit(self.read(REL), OLD, OLD_LINE))
        before = self.read(REL)
        res = self.go_image(lambda q, u: credited(NEW, NEW_LINE))
        self.assertEqual((res.status, res.files), ("ok", [REL]), res.reasons)
        after = self.read(REL)
        self.assertEqual(after.count(NEW_LINE), 1)
        self.assertNotIn("Old Person", after)
        self.assertEqual(after.replace(NEW, OLD).replace(NEW_LINE, OLD_LINE), before)
        self.assertIn("Photo by [Bob Lee]", res.pr_body)                       # 변경 내용(diff)에 줄 교체가 보인다
        self.assertIn("-", res.pr_body)

    def test_an_edit_on_a_post_without_a_line_adds_one(self):
        before = self.read(REL)
        res = self.go_image(lambda q, u: credited(NEW, NEW_LINE))
        self.assertEqual(res.status, "ok", res.reasons)
        self.assertEqual(self.read(REL).replace(NEW_LINE + "\n", "").replace(NEW, OLD), before)

    def test_a_picker_that_returns_a_bad_address_is_refused_and_nothing_is_written(self):
        write(self.root, REL, with_credit(self.read(REL), OLD, OLD_LINE))
        before = self.read(REL)
        res = self.go_image(lambda q, u: credited("https://evil.example/photo-1", NEW_LINE))
        self.assertRejected(res, "새 이미지를 찾지 못했습니다")
        self.assertEqual(self.read(REL), before)

    def test_the_scope_check_shows_the_credit_swap_for_a_human_to_confirm_instead_of_passing_it(self):
        """독립 검증 지적 ①: 이름 칸 평문은 검사로 증명할 수 없다 — 출처 줄이 달라진 PR 은 ✅ 통과가 아니라 ⚠️ 확인 필요이고, 이전 → 이후 줄이 코멘트에 보인다(자세한 시험은 test_edits_credit_fix.py)."""
        snap_root = self.root
        write(snap_root, REL, with_credit(self.read(REL), OLD, OLD_LINE))
        snap = Snapshot(snap_root)
        text = snap.base[REL]
        after = text.replace(OLD, NEW).replace(OLD_LINE, NEW_LINE)
        iss = issue(image_body(TITLE, "소방관"), labels=("blog-control", "edit:image"))
        report = snap.check(snap_root, iss, snap.head(edits={REL: after}))
        self.assertEqual(report.verdict, "WARN", report.items)
        markdown = report.markdown()
        self.assertIn("작가 출처 줄이 함께 바뀌었습니다", markdown)
        self.assertIn("Old Person", markdown)
        self.assertIn("Bob Lee", markdown)
        sneaky = after.replace("본문 문장입니다.", "본문을 마음대로 고쳤습니다.")
        self.assertEqual(snap.check(snap_root, iss, snap.head(edits={REL: sneaky})).verdict, "FAIL")


class ProductionPickerTest(RunnerBase):
    """운영 선택기(default_image_picker → generator.pick_images)가 주소와 출처 줄을 함께 돌려주고, 처리기가 그것을 글에 반영한다."""
    PHOTO = photo_item("Ccc333ddd44", raw=PHOTO_RAW.format(pid="ccc333ddd44"), name="Bob Lee", username="boblee")
    NO_USER = photo_item("Ddd444eee55", raw=PHOTO_RAW.format(pid="ddd444eee55"), remove=("user",))

    def run_issue(self, api):
        patches = (mock.patch("urllib.request.urlopen", api),
                   mock.patch.multiple(generator, UNSPLASH_KEY=FAKE_KEY, STUB_UNSPLASH=False, DRY_RUN=False),
                   mock.patch.dict(os.environ, {"UNSPLASH_ACCESS_KEY": FAKE_KEY}), mock.patch.dict(generator._credits, clear=True),
                   mock.patch.dict(generator._download_locations, clear=True), mock.patch.object(generator, "url_ok", lambda url, timeout=10: True))
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)
        iss = issue(image_body(TITLE, "소방관 구조 활동"), labels=("blog-control", "edit:image"), title="[이미지 변경] x")
        return self.go(iss)

    def test_the_picker_gives_the_address_with_its_ixid_and_the_credit(self):
        write(self.root, REL, with_credit(self.read(REL), OLD, OLD_LINE))
        api = FakeApi(searches=[results(self.PHOTO)])
        res = self.run_issue(api)
        self.assertEqual(res.status, "ok", res.reasons)
        after = self.read(REL)
        self.assertIn(f'image: "{NEW}"', after)
        lines = after.split("\n")
        self.assertEqual(lines[lines.index(f"![설명]({NEW})") + 1], NEW_LINE)
        self.assertNotIn("Old Person", after)
        self.assertEqual(api.downloads, ["/photos/Ccc333ddd44/download"])      # 쓰기로 한 사진에 사용 알림

    def test_a_photo_without_a_credit_is_not_chosen_for_an_edit(self):
        before = self.read(REL)
        res = self.run_issue(FakeApi(searches=[results(self.NO_USER)]))
        self.assertRejected(res, "새 이미지를 찾지 못했습니다")
        self.assertEqual(self.read(REL), before)

    def test_the_picker_returns_a_credited_string_equal_to_the_address(self):
        with mock.patch.dict(os.environ, {"UNSPLASH_ACCESS_KEY": FAKE_KEY}), mock.patch.dict(generator._credits, {generator.image_key(NEW): ("Bob Lee", "https://unsplash.com/@boblee")}), \
                mock.patch.object(generator, "pick_images", lambda queries, used, count=1, allow_pool=False: [NEW]), mock.patch.object(generator, "trigger_download", lambda url: None):
            picked = runner.default_image_picker()(["q"], set())
        self.assertIsInstance(picked, uc.Credited)
        self.assertEqual(picked, NEW)
        self.assertEqual(picked.credit, NEW_LINE)

    def test_the_picker_returns_none_when_nothing_was_picked(self):
        with mock.patch.dict(os.environ, {"UNSPLASH_ACCESS_KEY": FAKE_KEY}), mock.patch.object(generator, "pick_images", lambda queries, used, count=1, allow_pool=False: []):
            self.assertIsNone(runner.default_image_picker()(["q"], set()))


if __name__ == "__main__":
    unittest.main()
