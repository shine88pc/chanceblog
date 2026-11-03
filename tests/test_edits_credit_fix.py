"""독립 검증(U3) 지적 ① 반영 시험 + 이슈 수정 쪽 시험 공백(M107·M112·M116) — 네트워크 없이 돈다.

지적 ①: 작가 이름 칸은 Unsplash 응답에서 온 외부 글이다. 마크다운 이스케이프·80자 제한은 '링크·코드 주입 방지'일 뿐 '이름이 진짜'라는 증명이 아니라서(평문이면 영어 스팸·한국어 사기 문구·평문 주소·이모지도
우리 줄 모양이다), PR 범위 검사(scope_check.check_pull)는 작가 출처 줄이 이전 글과 달라진 이미지 교체를 ✅ 통과로 보이지 않고 ⚠️ 확인 필요로 보이며 이전 → 이후 줄을 코멘트에 싣는다.
`verify_image_change`(생성 직후 검증·이슈 수정 경로가 쓴다)는 그대로다 — 거절 기준을 좁히지 않았다.

구성
  1) PR 범위 검사 이미지 갈래: 줄이 달라지면 WARN(바뀜·생김·사라짐) · 줄이 그대로이거나 둘 다 없으면 PASS · 평문 이름 5종(V05·V06·V07·V09·V31)과 V08 은 ✅ 가 없다 · 코드 블록이 안전하다.
  2) verify_image_change 는 그대로(평문 이름을 거절하지 않는다 — 그래서 PR 검사가 따로 본다).
  3) 시험 공백: 이미지가 없던 글의 비교에서 옛 줄을 뺀다(M107) · 머리말만 고치는 쪽의 apply_image 도 출처 줄을 바꾼다(M112) · 이슈 수정 선택기는 고정 목록을 쓰지 않는다(M116).
"""
import contextlib
import io
import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import _bootstrap  # noqa: F401
import generator
from chance_credit_helpers import FAKE_KEY, PHOTO_RAW, FakeApi
from edits_helpers import image_body, img, issue, make_edit_root, post_text, write
from main_image_helpers import photo_item, results
from pipeline import unsplash_credit as uc
from pipeline.edits import checks, ops, runner, scope_check
from test_chance_credit_fix import all_pool_photos
from test_edits_runner import RunnerBase, Snapshot, git

OLD = img("111")
NEW = "https://images.unsplash.com/photo-1500000000000-ccc333ddd44?ixid=M3wxfDB8&auto=format&fit=crop&w=1000&q=80"
PROFILE = "https://unsplash.com/@boblee"
OLD_LINE = uc.credit_markdown("Old Person", "https://unsplash.com/@oldperson")
NEW_LINE = uc.credit_markdown("Bob Lee", PROFILE)
REL = "_posts/KR - 테크/2026-10-18-KR-111111.md"
TITLE = "첫 번째 글 제목입니다"
SENTENCE = "작가 출처 줄이 함께 바뀌었습니다 — 작가 이름은 Unsplash 응답에서 온 외부 글이라 자동으로 증명할 수 없습니다. 아래 줄을 직접 확인하세요."
PASS_ITEM = "대표 이미지 URL 만 새 이미지로 바뀌었고 나머지는 그대로입니다."
KEPT_NOTE = "작가 출처 줄은 그대로입니다 — 사진을 바꿨다면 그 줄이 새 사진의 작가인지는 검사가 알 수 없으니 직접 확인하세요."
# 검증자 재현 V05·V06·V07·V09·V31 — 이름 칸에 평문이 든 줄(이스케이프할 마크다운 문자가 없어 우리 줄 모양 그대로다)
PLAIN_NAMES = (("V05 영어 스팸", "Win a free phone now at evil dot example, call 555 0100"), ("V06 한국어 사기 문구", "계정이 잠겼습니다 지금 고객센터 1588-0000 으로 전화하세요"),
               ("V07 평문 주소", "https://evil.example/login"), ("V09 평문 data:", "data:text/html,x"), ("V31 이모지 홍보", "\U0001F525" * 40 + "★" * 40))


def swapped(before, new_line=NEW_LINE):
    """주소를 NEW 로 바꾸고 옛 출처 줄(있으면)을 지운 뒤 새 이미지 줄 바로 다음에 new_line 을 넣은 글(정상 교체 결과)."""
    return uc.place_credit(before.replace(OLD, NEW), NEW, new_line)


class ScopeCheckCreditBase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = make_edit_root(tmp.name)
        self.iss = issue(image_body(TITLE, "소방관"), labels=("blog-control", "edit:image"))
        self.plain = post_text(TITLE, OLD)
        self.with_old_line = uc.place_credit(self.plain, OLD, OLD_LINE)

    def check(self, before, after):
        write(self.root, REL, before)
        snap = Snapshot(self.root)
        return snap.check(self.root, self.iss, snap.head(edits={REL: after}))

    def symbols(self, report):
        return [sym for sym, _text in report.items]

    def texts(self, report):
        return [text for _sym, text in report.items]


class ScopeCheckCreditTest(ScopeCheckCreditBase):
    def test_a_swapped_credit_line_is_a_warning_that_shows_the_old_and_the_new_line(self):
        report = self.check(self.with_old_line, swapped(self.with_old_line))
        self.assertEqual(report.verdict, "WARN", report.items)
        self.assertIn(("⚠️", SENTENCE), report.items)
        self.assertNotIn(PASS_ITEM, self.texts(report))                         # ✅ 로 증명했다는 문장이 없다
        self.assertNotIn("✅", [sym for sym, text in report.items if "이미지" in text and "대표" in text])
        self.assertEqual(len(report.details), 1)
        diff = report.details[0].splitlines()
        self.assertIn("-" + OLD_LINE, diff)
        self.assertIn("+" + NEW_LINE, diff)
        markdown = report.markdown()
        self.assertIn("⚠️ **확인 필요**", markdown)
        self.assertNotIn("✅ **통과**", markdown)
        self.assertIn("~~~~diff", markdown)
        self.assertIn(OLD_LINE, markdown)
        self.assertIn(NEW_LINE, markdown)

    def test_a_credit_line_that_appears_or_disappears_alongside_the_address_is_a_warning_too(self):
        added = self.check(self.plain, swapped(self.plain))
        self.assertEqual(added.verdict, "WARN", added.items)
        self.assertEqual([line for line in added.details[0].splitlines() if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))], ["+" + NEW_LINE])
        dropped = self.check(self.with_old_line, swapped(self.with_old_line, ""))
        self.assertEqual(dropped.verdict, "WARN", dropped.items)
        self.assertEqual([line for line in dropped.details[0].splitlines() if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))], ["-" + OLD_LINE])

    def test_the_address_alone_changing_still_passes_with_no_credit_line_anywhere(self):
        report = self.check(self.plain, self.plain.replace(OLD, NEW))
        self.assertEqual(report.verdict, "PASS", report.items)
        self.assertIn(("✅", PASS_ITEM), report.items)
        self.assertEqual(report.details, [])
        self.assertNotIn("작가 출처 줄이 함께", report.markdown())

    def test_the_address_alone_changing_passes_when_the_same_credit_line_is_there_before_and_after(self):
        report = self.check(self.with_old_line, self.with_old_line.replace(OLD, NEW))
        self.assertEqual(report.verdict, "PASS", report.items)
        self.assertIn(("✅", PASS_ITEM), report.items)
        self.assertIn(("ℹ️", KEPT_NOTE), report.items)                           # 통과이지만 '줄이 새 사진의 작가인지는 검사가 모른다'고 덧붙인다
        self.assertEqual(report.details, [])
        self.assertEqual(report.markdown().count(OLD_LINE), 0)                  # 줄이 그대로이니 코멘트에 싣지 않는다

    def test_the_kept_line_note_is_only_for_posts_that_have_a_line(self):
        plain = self.check(self.plain, self.plain.replace(OLD, NEW))
        self.assertNotIn(KEPT_NOTE, self.texts(plain))
        warned = self.check(self.with_old_line, swapped(self.with_old_line))
        self.assertNotIn(KEPT_NOTE, self.texts(warned))
        refused = self.check(self.with_old_line, self.with_old_line.replace(OLD, NEW).replace("본문 문장입니다.", "고쳤습니다."))
        self.assertEqual(refused.verdict, "FAIL")
        self.assertNotIn(KEPT_NOTE, self.texts(refused))

    def test_plain_text_names_are_never_shown_as_passed(self):
        for label, name in PLAIN_NAMES:
            with self.subTest(label):
                line = uc.credit_markdown(name, PROFILE)
                self.assertTrue(uc.is_credit_line(line), label)                  # 우리 줄 모양이다(이스케이프·길이 제한을 모두 지켰다)
                for before in (self.plain, self.with_old_line):
                    report = self.check(before, swapped(before, line))
                    self.assertEqual(report.verdict, "WARN", (label, report.items))
                    self.assertNotIn("✅", [sym for sym, text in report.items if text == PASS_ITEM])
                    self.assertNotIn(PASS_ITEM, self.texts(report))
                    self.assertIn(line, report.details[0].splitlines()[-1].lstrip("+"))     # 사람이 볼 수 있게 이름이 코멘트에 실린다
                    self.assertIn("⚠️ **확인 필요**", report.markdown())

    def test_a_plain_javascript_name_is_stopped_by_another_check_and_is_never_a_pass(self):
        line = uc.credit_markdown("javascript:alert(1)", PROFILE)
        report = self.check(self.plain, swapped(self.plain, line))
        self.assertIn(report.verdict, ("WARN", "FAIL"))
        self.assertNotEqual(report.verdict, "PASS")

    def test_only_the_line_changing_without_the_address_is_refused(self):
        spam = uc.credit_markdown("Win a free phone now", PROFILE)
        report = self.check(self.with_old_line, self.with_old_line.replace(OLD_LINE, spam))      # 주소가 그대로면 이미지 교체가 아니다(V26)
        self.assertEqual(report.verdict, "FAIL", report.items)

    def test_an_image_added_to_a_post_without_one_with_a_credit_line_is_a_warning_with_matching_words(self):
        """머리말에 image 가 없던 글(본문에는 이미지 줄이 있다)에 대표 이미지를 더하며 출처 줄도 넣으면 ⚠️ — '이미지가 없던 글에' 문장이 쓰인다. 주소만 더하면 지금처럼 ✅."""
        with_image_line = f'---\nlayout: post\ntitle: "{TITLE}"\ncategory: x\n---\n\n본문 문장입니다.\n\n![설명]({NEW})\n'
        with_address = with_image_line.replace("category: x\n", f'category: x\nimage: "{NEW}"\n')
        report = self.check(with_image_line, with_address.replace(f"![설명]({NEW})\n", f"![설명]({NEW})\n{NEW_LINE}\n"))
        self.assertEqual(report.verdict, "WARN", report.items)
        self.assertTrue(any("이미지가 없던 글에" in text and "작가 출처 줄 외의 내용은 그대로입니다" in text for text in self.texts(report)), report.items)
        self.assertIn(("⚠️", SENTENCE), report.items)
        only_address = self.check(with_image_line, with_address)
        self.assertEqual(only_address.verdict, "PASS", only_address.items)
        self.assertTrue(any("이미지가 없던 글에" in text for text in self.texts(only_address)))

    def test_a_refusal_stays_a_refusal_and_does_not_show_the_credit_block(self):
        two_lines = swapped(self.plain).replace(NEW_LINE, NEW_LINE + "\n" + OLD_LINE)
        for after in (two_lines, swapped(self.plain).replace("본문 문장입니다.", "본문을 마음대로 고쳤습니다.")):
            report = self.check(self.plain, after)
            self.assertEqual(report.verdict, "FAIL")
            self.assertNotIn("작가 출처 줄이 함께", report.markdown())
            self.assertEqual(report.details, [])

    def test_the_credit_block_cannot_be_closed_from_inside(self):
        for name in ("~" * 40 + " end", "~~~~ diff", "```" + " x"):
            line = uc.credit_markdown(name, PROFILE)
            self.assertTrue(uc.is_credit_line(line), name)
            report = self.check(self.plain, swapped(self.plain, line))
            self.assertEqual(report.verdict, "WARN")
            lines = report.markdown().splitlines()
            opening = next(i for i, text in enumerate(lines) if text.startswith("~~~~") and text.endswith("diff"))
            fence = lines[opening][:-len("diff")]
            self.assertGreater(len(fence), max((len(run) for run in re.findall(r"~+", line)), default=0))          # 펜스는 줄 속 어떤 틸드 연속보다 길다
            closing = [i for i, text in enumerate(lines) if i > opening and text == fence]
            self.assertEqual(len(closing), 1)
            self.assertTrue(any(line in text for text in lines[opening + 1:closing[0]]))        # 줄은 펜스 안에 있다

    def test_the_comment_says_nothing_about_the_name_outside_the_code_block(self):
        line = uc.credit_markdown("Bob Lee", PROFILE)
        report = self.check(self.plain, swapped(self.plain, line))
        outside = [text for _sym, text in report.items]
        self.assertFalse(any("Bob" in text for text in outside))               # 이름은 코드 블록(details)에만 있다


class ScopeCheckGitCreditTest(unittest.TestCase):
    """실제 git 과 명령줄(워크플로가 하는 방식: 두 커밋의 파일을 `git show` 로 읽는다)을 거쳐도 같은 판정이 나온다 — 느려서 시나리오 몇 개만."""

    def run_cli(self, before, after, crlf=False):
        put = (lambda text: text.replace("\n", "\r\n")) if crlf else (lambda text: text)
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = make_edit_root(tmp)
            write(root, REL, put(before))
            git(root, "init", "-q")
            git(root, "add", "-A")
            git(root, "commit", "-q", "-m", "base")
            base = git(root, "rev-parse", "HEAD")
            git(root, "switch", "-q", "-c", "work")
            write(root, REL, put(after))
            git(root, "add", "-A")
            git(root, "commit", "-q", "-m", "pr")
            head = git(root, "rev-parse", "HEAD")
            git(root, "switch", "-q", "-")
            meta = Path(tmp) / "meta"
            meta.mkdir()
            (meta / "pr.json").write_text(json.dumps({"title": "t", "body": "Fixes #12", "base": {"sha": base}, "head": {"sha": head}}), encoding="utf-8")
            (meta / "issue.json").write_text(json.dumps(issue(image_body(TITLE, "소방관"), labels=("blog-control", "edit:image"))), encoding="utf-8")
            out = meta / "scope"
            with contextlib.redirect_stdout(io.StringIO()):
                code = scope_check.main(["--pr-file", str(meta / "pr.json"), "--issue-file", str(meta / "issue.json"), "--out", str(out), "--root", str(root)])
            return code, (out / "verdict.txt").read_text(encoding="utf-8").strip(), (out / "report.md").read_text(encoding="utf-8")

    def test_a_swapped_credit_line_is_a_warning_with_the_lines_in_the_comment_and_the_run_stays_green(self):
        before = uc.place_credit(post_text(TITLE, OLD), OLD, OLD_LINE)
        code, verdict, report = self.run_cli(before, swapped(before))
        self.assertEqual((code, verdict), (0, "WARN"))                            # 확인 필요는 실행을 빨강으로 만들지 않는다
        self.assertIn("⚠️ **확인 필요**", report)
        self.assertIn(SENTENCE, report)
        self.assertIn("-" + OLD_LINE, report.splitlines())
        self.assertIn("+" + NEW_LINE, report.splitlines())
        self.assertIn("~~~~diff", report)

    def test_a_plain_text_name_in_crlf_files_is_a_warning_through_the_real_git_too(self):
        plain = post_text(TITLE, OLD)
        line = uc.credit_markdown(PLAIN_NAMES[0][1], PROFILE)
        code, verdict, report = self.run_cli(plain, swapped(plain, line), crlf=True)
        self.assertEqual((code, verdict), (0, "WARN"))
        self.assertIn(line, report)

    def test_the_address_alone_still_passes_through_the_real_git(self):
        before = uc.place_credit(post_text(TITLE, OLD), OLD, OLD_LINE)
        code, verdict, report = self.run_cli(before, before.replace(OLD, NEW))
        self.assertEqual((code, verdict), (0, "PASS"))
        self.assertIn(KEPT_NOTE, report)


class CreditDiffTest(unittest.TestCase):
    PATH = "_posts/a.md"

    def test_no_difference_gives_nothing(self):
        for before, after in (("", ""), ("본문", "본문 다름"), (OLD_LINE, OLD_LINE), (f"x\n{OLD_LINE}\ny", f"z\n{OLD_LINE}\nw")):
            self.assertIsNone(scope_check.credit_diff(before, after, self.PATH), (before, after))

    def test_a_difference_gives_a_diff_that_names_the_file_and_shows_both_lines(self):
        diff = scope_check.credit_diff(f"x\n{OLD_LINE}\ny", f"x\n{NEW_LINE}\ny", self.PATH)
        lines = diff.splitlines()
        self.assertEqual(lines[:2], [f"--- a/{self.PATH} (작가 출처 줄: 이전 → 이후)", f"+++ b/{self.PATH} (작가 출처 줄: 이전 → 이후)"])
        self.assertIn("-" + OLD_LINE, lines)
        self.assertIn("+" + NEW_LINE, lines)
        self.assertFalse([line for line in lines[2:] if line[:1] in "+-" and line[1:] not in (OLD_LINE, NEW_LINE)])      # 본문은 싣지 않고 출처 줄만 싣는다

    def test_only_lines_of_our_shape_are_compared(self):
        near = OLD_LINE.replace("unsplash.com/@oldperson", "evil.example/@oldperson")
        self.assertIsNone(scope_check.credit_diff(near, "", self.PATH))          # 우리 모양이 아닌 줄은 '출처 줄'이 아니다(다른 검사가 본다)


class VerifyImageChangeIsUnchangedTest(ScopeCheckCreditBase):
    def test_the_function_still_accepts_plain_text_names_so_the_pr_check_must_look_at_them_itself(self):
        for label, name in PLAIN_NAMES:
            line = uc.credit_markdown(name, PROFILE)
            self.assertEqual(checks.verify_image_change(self.plain, swapped(self.plain, line)), [], label)


class UnchangedBeforeTextTest(unittest.TestCase):
    """시험 공백 M107: 이미지가 없던 글(front matter 에 image 가 없다)의 비교에서도 옛 출처 줄은 뺀다."""
    BEFORE = f'---\nlayout: post\ntitle: "x"\ncategory: x\n---\n\n본문 문장입니다.\n\n![설명]({NEW})\n{OLD_LINE}\n'

    def test_a_post_without_a_front_matter_image_may_swap_its_credit_line_while_gaining_the_image(self):
        after = self.BEFORE.replace("category: x\n", f'category: x\nimage: "{NEW}"\n').replace(OLD_LINE, NEW_LINE)
        self.assertEqual(checks.verify_image_change(self.BEFORE, after), [])
        dropped = self.BEFORE.replace("category: x\n", f'category: x\nimage: "{NEW}"\n').replace(OLD_LINE + "\n", "")
        self.assertEqual(checks.verify_image_change(self.BEFORE, dropped), [])

    def test_the_comparison_is_still_strict_about_everything_else(self):
        gained = self.BEFORE.replace("category: x\n", f'category: x\nimage: "{NEW}"\n')
        for after in (gained.replace("본문 문장입니다.", "본문을 고쳤습니다."), gained + "\n몰래 붙인 문장입니다.\n", gained.replace('title: "x"', 'title: "y"')):
            self.assertTrue(any("주소 외의 내용" in reason for reason in checks.verify_image_change(self.BEFORE, after)), after)


class ApplyImageHeaderOnlyBranchTest(unittest.TestCase):
    """시험 공백 M112: 옛 주소가 글에 없어 머리말 image 만 쓰는 쪽의 ops.apply_image 도 옛 출처 줄을 지우고 새 줄을 새 이미지 줄 바로 다음에 넣는다."""
    BODY = f"\n본문 문장입니다.\n\n![설명]({NEW})\n{OLD_LINE}\n\n마지막 문장입니다.\n"
    NO_IMAGE = f'---\nlayout: post\ntitle: "x"\ncategory: x\n---\n{BODY}'
    OTHER_IMAGE = f'---\nlayout: post\ntitle: "x"\ncategory: x\nimage: "{OLD}"\n---\n{BODY}'

    def test_the_new_line_replaces_the_old_one_in_both_header_only_forms(self):
        for label, text, old_url in (("머리말에 image 가 없다", self.NO_IMAGE, ""), ("옛 주소가 글에 없다", self.NO_IMAGE, "https://images.unsplash.com/photo-0000000000000-notfound"),
                                     ("머리말 image 는 있으나 옛 주소가 다르다", self.OTHER_IMAGE.replace(OLD, "https://images.unsplash.com/photo-2222222222222-other"), OLD)):
            with self.subTest(label):
                after = ops.apply_image(text, old_url, NEW, NEW_LINE)
                lines = after.split("\n")
                self.assertEqual(lines[lines.index(f"![설명]({NEW})") + 1], NEW_LINE)
                self.assertNotIn("Old Person", after)
                self.assertEqual(after.count("Photo by ["), 1)
                self.assertIn(f'image: "{NEW}"', after)

    def test_without_a_new_line_the_old_one_still_goes_away(self):
        after = ops.apply_image(self.NO_IMAGE, "", NEW)
        self.assertNotIn("Old Person", after)
        self.assertEqual(after.count("Photo by ["), 0)
        self.assertIn(f'image: "{NEW}"', after)


class NoFixedListInIssueEditsTest(RunnerBase):
    """시험 공백 M116: 이슈 수정의 이미지 선택기는 검색이 비어도 고정 목록(IMAGE_POOL)으로 대신하지 않는다 — 조회는 한 번도 없고 '새 이미지를 찾지 못했습니다'로 거절한다."""
    TITLE_TEXT = "첫 번째 글 제목입니다"

    def run_issue(self, api):
        patches = (mock.patch("urllib.request.urlopen", api), mock.patch.multiple(generator, UNSPLASH_KEY=FAKE_KEY, STUB_UNSPLASH=False, DRY_RUN=False),
                   mock.patch.dict(os.environ, {"UNSPLASH_ACCESS_KEY": FAKE_KEY}), mock.patch.dict(generator._credits, clear=True),
                   mock.patch.dict(generator._download_locations, clear=True), mock.patch.object(generator, "url_ok", lambda url, timeout=10: True))
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)
        return self.go(issue(image_body(self.TITLE_TEXT, "소방관 구조 활동"), labels=("blog-control", "edit:image"), title="[이미지 변경] x"))

    def test_an_empty_search_ends_in_a_refusal_and_never_looks_up_the_fixed_list(self):
        before = self.read(REL)
        api = FakeApi(searches=[results()], photos=all_pool_photos())
        res = self.run_issue(api)
        self.assertRejected(res, "새 이미지를 찾지 못했습니다")
        self.assertEqual(api.lookups, [])
        self.assertEqual(api.downloads, [])
        self.assertEqual(self.read(REL), before)

    def test_the_picker_asks_for_the_search_only(self):
        seen = {}

        def spy(queries, used, count=1, allow_pool=False):
            seen.update(allow_pool=allow_pool, count=count)
            return []

        with mock.patch.dict(os.environ, {"UNSPLASH_ACCESS_KEY": FAKE_KEY}), mock.patch.object(generator, "pick_images", spy):
            self.assertIsNone(runner.default_image_picker()(["q"], set()))
        self.assertEqual(seen, {"allow_pool": False, "count": 1})

    def test_a_search_photo_is_still_used(self):
        photo = photo_item("Ccc333ddd44", raw=PHOTO_RAW.format(pid="ccc333ddd44"), name="Bob Lee", username="boblee")
        api = FakeApi(searches=[results(photo)], photos=all_pool_photos())
        res = self.run_issue(api)
        self.assertEqual(res.status, "ok", res.reasons)
        self.assertEqual(api.lookups, [])
        self.assertEqual(api.downloads, ["/photos/Ccc333ddd44/download"])


if __name__ == "__main__":
    unittest.main()
