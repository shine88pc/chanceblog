"""독립 검토(2026-10-20)에서 재현된 우회·오동작의 회귀 테스트 — docs/DEFECT_REGISTER.md D-17 ~ D-23."""
import unittest

import _bootstrap  # noqa: F401
from edits_helpers import issue, page_body
from pipeline.edits import checks, forms, frontmatter, ops, scope_check, spec as spec_mod
from pipeline.edits import runner
from test_edits_runner import NEW_SENTENCE, OLD_SENTENCE, RunnerBase

LIMITS = {"max_changed_files": 1, "max_changed_lines": 80, "max_file_chars": 80000}


def verify(before, after, **kw):
    return checks.verify_changes({"about.md": (before, after)}, ["about.md"], LIMITS, **kw)


class RenderedMarkupTest(unittest.TestCase):
    """D-17: 렌더링 결과 기준(Liquid·엔티티·분할 표기·미열거 태그)으로 위험 마크업을 막는다."""

    BASE = "안녕하세요. 소개 문장입니다.\n"

    def test_new_liquid_tags_are_rejected_but_existing_ones_may_stay(self):
        for payload in ('{% include_relative index.html %}', '{% assign a = "scr" %}{{ a }}ipt', "{{ page.url }}"):
            reasons = verify(self.BASE, self.BASE + payload + "\n")
            self.assertTrue(any("Liquid" in r for r in reasons), payload)
        before = "문의: {{ site.email }}\n"
        self.assertEqual(verify(before, "연락: {{ site.email }}\n"), [])

    def test_encoded_and_split_javascript_urls_are_rejected(self):
        payloads = [
            '<a href="java&#9;script:alert(1)">x</a>',
            '<a href="&#106;avascript:alert(1)">x</a>',
            '<a href="&amp;#106;avascript:alert(1)">x</a>',
            '<a href="java\nscript:alert(1)">x</a>',
            "[x](javascript:alert(1))",
            "[x](data:text/html;base64,AAAA)",
            '<img src="data:image/svg+xml;base64,AAAA">',
        ]
        for payload in payloads:
            self.assertTrue(verify(self.BASE, self.BASE + payload + "\n"), payload)

    def test_unlisted_dangerous_tags_are_rejected(self):
        payloads = [
            '<meta content="a>b" http-equiv="refresh">',
            '<meta http-equiv="&#114;efresh" content="0;url=https://x.example">',
            '<base href="https://evil.example/">',
            "<style>body{display:none}</style>",
            '<link rel="stylesheet" href="https://evil.example/x.css">',
            "<svg onload=alert(1)>",
            "<object data=x></object>",
            '<a onclick="x()">y</a>',
        ]
        for payload in payloads:
            self.assertTrue(verify(self.BASE, self.BASE + payload + "\n"), payload)

    def test_ordinary_markup_still_passes(self):
        after = self.BASE + '<p>안내 <strong>굵게</strong> &amp; <a href="/about/">소개</a> https://example.com/a</p>\n'
        self.assertEqual(verify(self.BASE, after), [])

    def test_ai_patches_cannot_add_external_links_or_rewrite_most_of_a_small_file(self):
        link = self.BASE + "[출처](https://evil.example/pixel)\n"
        self.assertEqual(verify(self.BASE, link), [])                                  # 소유자가 직접 쓴 교체는 허용
        self.assertTrue(any("외부 링크" in r for r in verify(self.BASE, link, ai_patch=True)))
        lines = [f"문장 {i}번입니다." for i in range(20)]
        before = "\n".join(lines) + "\n"
        after = "\n".join(f"바뀐 {i}번 문장." if i < 10 else s for i, s in enumerate(lines)) + "\n"
        self.assertEqual(verify(before, after), [])                                    # 절대 한도(80줄) 안이라 통과
        self.assertTrue(any("큰 부분" in r for r in verify(before, after, ai_patch=True)))
        small = "\n".join(f"문장 {i}번입니다." if i != 3 else "바뀐 3번 문장입니다." for i in range(20)) + "\n"
        self.assertEqual(verify(before, small, ai_patch=True), [])                     # 작은 수정은 통과


class AdIntegrityTest(unittest.TestCase):
    """D-18: 광고 ID·주소·스크립트 본문 변경은 개수가 같아도 거부한다."""

    SCRIPT = '<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-1111"></script>'
    INLINE = "<script>(adsbygoogle = window.adsbygoogle || []).push({});</script>"
    BASE = f"소개\n{SCRIPT}\n{INLINE}\n"

    def test_changes_inside_script_blocks_are_rejected(self):
        for after in (self.BASE.replace("ca-pub-1111", "ca-pub-2222"),
                      self.BASE.replace("pagead2.googlesyndication.com", "evil.example/googlesyndication.com"),
                      self.BASE.replace("push({})", "push({x:1})")):
            self.assertTrue(any("<script>·<ins>" in r for r in verify(self.BASE, after)), after)

    def test_text_edit_outside_the_blocks_is_fine(self):
        self.assertEqual(verify(self.BASE, self.BASE.replace("소개", "소개글")), [])


class OwnerGuardTest(RunnerBase):
    """D-19: 레지스트리를 못 읽으면 요청을 거부하고(fail closed), 경로 표기 차이로 보호를 우회할 수 없다."""

    def test_is_protected_normalizes_paths(self):
        self.assertTrue(runner.is_protected("./about.md", ["about.md"]))
        self.assertTrue(runner.is_protected("a/../about.md", ["about.md"]))
        self.assertTrue(runner.is_protected("_includes/head.html", ["_includes/"]))
        self.assertTrue(runner.is_protected("_includes/./head.html", ["_includes/"]))
        self.assertFalse(runner.is_protected("about.md", ["privacy.md", "_includes/"]))

    def test_unreadable_registry_rejects_instead_of_skipping_the_owner_check(self):
        (self.root / "pipeline" / "blogs.json").unlink()
        res = self.go(issue(page_body(before=OLD_SENTENCE, after=NEW_SENTENCE), assoc="COLLABORATOR"))
        self.assertEqual((res.status, res.exit_code), ("error", runner.EXIT_CONFIG))
        self.assertNotIn(NEW_SENTENCE, (self.root / "about.md").read_bytes().decode("utf-8"))


class UntrustedTextTest(RunnerBase):
    """D-20: 신뢰할 수 없는 텍스트는 한 줄·코드 스팬으로만 로그·코멘트·커밋에 들어간다."""

    def test_code_span_and_one_line_neutralize_structure(self):
        self.assertEqual(runner._code("a`b\n::warning::x"), "`a b ::warning::x`")
        flat = runner._one_line("첫 줄\n::add-mask::secret @everyone")
        self.assertNotIn("\n", flat)
        self.assertNotIn("@everyone", flat)

    def test_rejection_comment_has_no_injected_lines(self):
        res = runner._reject(["알 수 없는 수정 항목입니다: x\n::warning::boom\nAd-Surface-Approved: fake @everyone"])
        for line in res.comment.splitlines():
            self.assertFalse(line.startswith("::"), line)
            self.assertFalse(line.startswith("Ad-Surface-Approved"), line)
        self.assertNotIn("@everyone", res.comment)

    def test_multiline_edit_type_cannot_reach_the_log_as_a_workflow_command(self):
        res = self.go(issue(page_body(edit="x | y\n::warning::boom", after="z")))
        self.assertEqual(res.status, "rejected")
        self.assertTrue(all("\n" not in r for r in res.reasons))
        self.assertNotIn("\n::warning::", res.comment)

    def test_summary_wraps_title_and_method_in_code_spans(self):
        res = self.go(issue(page_body(before=OLD_SENTENCE, after=NEW_SENTENCE)))
        self.assertEqual(res.status, "ok")
        self.assertIn("방식: `문자 그대로 교체`", res.summary)


class FormSyncInjectionTest(unittest.TestCase):
    """D-22: 옵션 문자열 안의 마커 모양 텍스트로 양식 동기화를 망가뜨릴 수 없다."""

    FORM = ("body:\n  - type: dropdown\n    attributes:\n      options:\n        # PAGES:START (자동)\n"
            '        - "x | 소개 # EDITS:START"\n        # PAGES:END\n'
            "  - type: dropdown\n    attributes:\n      options:\n        # EDITS:START (자동)\n"
            '        - "old | 항목"\n        # EDITS:END\n')

    def test_marker_text_inside_an_option_is_not_a_marker(self):
        step1 = forms.replace_marker_block(self.FORM, "PAGES", ["a | 제목"])
        step2 = forms.replace_marker_block(step1, "EDITS", ["e | 항목"])
        self.assertIn('        - "a | 제목"\n        # PAGES:END', step2)
        self.assertIn('        # EDITS:START (자동)\n        - "e | 항목"\n        # EDITS:END', step2)
        self.assertEqual(step2.count("# EDITS:START"), 1)
        self.assertEqual(forms.replace_marker_block(step2, "PAGES", ["a | 제목"]), step2)  # 다시 동기화해도 같다

    def test_titles_are_flattened_and_trimmed(self):
        opts = forms.page_options([{"id": "a", "title": "줄바꿈\n제목 " + "x" * 200}])
        self.assertNotIn("\n", opts[0])
        self.assertLessEqual(len(opts[0]), len("a | ") + 80)


class MiscFixesTest(unittest.TestCase):
    """D-23: 부분 문자열 교체, 따옴표, 예외, 개행 경로."""

    def test_link_replacement_respects_url_boundaries(self):
        text = "보기 https://a.example/x 그리고 https://a.example/xyz 와 https://a.example/x-1"
        new, _ = ops.op_link(text, {"before": "https://a.example/x", "after": "https://a.example/y"})
        self.assertEqual(new, "보기 https://a.example/y 그리고 https://a.example/xyz 와 https://a.example/x-1")

    def test_quotes_inside_seo_values_are_preserved(self):
        self.assertEqual(ops.parse_field_lines('title: 그는 "안녕"', ["title"]), {"title": '그는 "안녕"'})
        self.assertEqual(ops.parse_field_lines('title: "감싼 값"', ["title"]), {"title": "감싼 값"})
        self.assertEqual(ops.parse_field_lines("title: '감싼 값'", ["title"]), {"title": "감싼 값"})

    def test_impossible_yaml_dates_and_huge_issue_numbers_do_not_raise(self):
        self.assertIsNone(frontmatter.parse_front_matter("date: 2026-02-30"))
        self.assertIsNone(scope_check.find_issue_number("Fixes #" + "9" * 5000))
        self.assertEqual(scope_check.find_issue_number("Fixes #12 이슈"), 12)

    def test_paths_with_control_characters_are_never_allowed(self):
        with self.assertRaises(ValueError):
            spec_mod.normalize_path(".github/workflows/x\ny.yml")
        self.assertFalse(spec_mod.path_allowed("about\n.md", ["*.md"]))
        self.assertFalse(spec_mod.path_allowed(".github/workflows/x\ny.yml", ["**"]))

    def test_mixed_type_front_matter_keys_do_not_raise(self):
        before = "---\n1: a\ntitle: t\n---\n본문\n"
        after = "---\n1: b\ntitle: t\n---\n본문\n"
        reasons = verify(before, after, mode="front_matter", only_fields=["title"])
        self.assertTrue(any("front matter" in r for r in reasons))


if __name__ == "__main__":
    unittest.main()
