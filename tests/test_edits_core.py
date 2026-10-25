import copy
import tempfile
import unittest
from pathlib import Path

import _bootstrap  # noqa: F401
from edits_helpers import REAL, issue, make_edit_root, page_body, write
from pipeline.edits import forms, pages, runner, spec as spec_mod, targets


def real_spec():
    return spec_mod.load_spec(REAL)


class SpecTest(unittest.TestCase):
    def errors(self, mutate):
        spec = copy.deepcopy(real_spec())
        mutate(spec)
        return spec_mod.validate_spec(spec)

    def assertHas(self, errors, fragment):
        self.assertTrue(any(fragment in e for e in errors), f"{fragment!r} not in {errors}")

    def test_real_spec_is_valid(self):
        self.assertEqual(spec_mod.validate_spec(real_spec()), [])

    def test_never_allowed_patterns_are_rejected(self):
        for pattern in ("_layouts/**", "_includes/**", ".github/**", "*.py", "**", "scripts/x.py", "index.html",
                        "pipeline/**", "docs/**", "_config.yml", "*.json", "**/*.yml"):
            errors = self.errors(lambda s, p=pattern: s["edit_types"]["text_change"].update(allowed_paths=["{page.path}", p]))
            self.assertHas(errors, "절대 금지 경로")

    def test_safe_extra_patterns_are_accepted(self):
        errors = self.errors(lambda s: s["edit_types"]["text_change"].update(allowed_paths=["{page.path}", "assets/img/*.svg"]))
        self.assertEqual(errors, [])

    def test_main_direct_push_is_not_allowed(self):
        self.assertHas(self.errors(lambda s: s["output"].update(mode="direct_push")), "pull_request")

    def test_target_path_placeholder_is_required(self):
        self.assertHas(self.errors(lambda s: s["edit_types"]["image_change"].update(allowed_paths=["_posts/**"])), "{post.path}")

    def test_unknown_placeholder_method_and_fields(self):
        self.assertHas(self.errors(lambda s: s["edit_types"]["text_change"].update(allowed_paths=["{page.path}", "{evil}"])), "자리표시자")
        self.assertHas(self.errors(lambda s: s["edit_types"]["text_change"].update(method="shell")), "method")
        self.assertHas(self.errors(lambda s: s["edit_types"]["seo_meta"].update(only_fields=["title", "layout"])), "only_fields")
        self.assertHas(self.errors(lambda s: s["edit_types"]["text_change"].update(required=["target_page", "bogus"])), "required")
        self.assertHas(self.errors(lambda s: s["edit_types"]["text_change"].update(required=["after"])), "target_page")

    def test_limits_and_label_format(self):
        self.assertHas(self.errors(lambda s: s["limits"].update(max_changed_lines=0)), "max_changed_lines")
        self.assertHas(self.errors(lambda s: s["edit_types"]["text_change"].update(issue_label="page")), "issue_label")

    def test_image_method_requires_post_target(self):
        self.assertHas(self.errors(lambda s: s["edit_types"]["text_change"].update(method="image")), "게시글 대상")

    def test_output_rejects_keys_the_code_does_not_read(self):
        """D-23: 코드가 읽지 않는 스위치(예: comment_on_reject: false)는 조용한 실패를 부르므로 명세에 둘 수 없다."""
        for key in ("comment_on_reject", "reviewers", "auto_merge"):
            for value in (True, False):
                errors = self.errors(lambda s, k=key, v=value: s["output"].update({k: v}))
                self.assertHas(errors, "지원하지 않는 키")
                self.assertHas(errors, key)
        self.assertHas(self.errors(lambda s: s.update(output=["pull_request"])), "output 은 객체")

    def test_output_rejects_keys_that_are_not_even_strings(self):
        """검증자 V02: YAML 은 `1: x`·`true: x`·`null: x` 같은 문자열이 아닌 키도 만든다. 그것도 지원하지 않는 키다."""
        for key in (1, True, None, 3.5):
            errors = self.errors(lambda s, k=key: s["output"].update({k: "x"}))
            self.assertHas(errors, "지원하지 않는 키")

    def test_real_spec_has_exactly_the_keys_the_code_reads(self):
        self.assertEqual(set(real_spec()["output"]), spec_mod.OUTPUT_KEYS)
        self.assertEqual(spec_mod.validate_spec(real_spec()), [])


class SpecOutputRuntimeTest(unittest.TestCase):
    """런타임도 같은 검증을 쓴다: 지원하지 않는 output 키가 들어간 명세로는 아무것도 수정하지 않는다(fail closed)."""

    def test_runner_refuses_to_run_with_a_dead_switch_in_the_spec(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_edit_root(tmp)
            spec_file = Path(root) / ".github" / "editorial" / "edit-spec.yml"
            text = spec_file.read_bytes().decode("utf-8")
            spec_file.write_bytes((text.rstrip("\n") + "\n  comment_on_reject: false\n").encode("utf-8"))
            before = (Path(root) / "about.md").read_bytes()
            res = runner.process_issue(issue(page_body(before="문의는 old@example.com 으로 보내 주세요.", after="x")), root, env={})
            self.assertEqual((res.status, res.exit_code), ("error", runner.EXIT_CONFIG))
            self.assertIn("comment_on_reject", res.message)
            self.assertEqual((Path(root) / "about.md").read_bytes(), before)


class PathRulesTest(unittest.TestCase):
    def test_normalize_path(self):
        self.assertEqual(spec_mod.normalize_path("./a\\b/c.md"), "a/b/c.md")
        for bad in ("../x", "a/../../x", "/etc/passwd", "C:\\x", "", "   ", None):
            with self.assertRaises(ValueError):
                spec_mod.normalize_path(bad)

    def test_never_allowed(self):
        for path in ("_layouts/info.html", "_includes/head.html", "index.html", "INDEX.HTML", ".github/workflows/x.yml",
                     "scripts/a.py", "pipeline/run.py", "pages.json", "posts.json", "_config.yml", "HANDLER.md",
                     "googlee86895dfeddcdd45.html", "requirements-dev.txt", "docs/a.md"):
            self.assertTrue(spec_mod.is_never_allowed(path), path)
        for path in ("about.md", "_posts/2026-10-18-KR-1.md", "categories.md", "privacy.md"):
            self.assertFalse(spec_mod.is_never_allowed(path), path)

    def test_path_allowed(self):
        self.assertTrue(spec_mod.path_allowed("about.md", ["about.md"]))
        self.assertFalse(spec_mod.path_allowed("contact.md", ["about.md"]))
        self.assertFalse(spec_mod.path_allowed("index.html", ["index.html"]))   # 명세가 허용해도 금지 경로
        self.assertFalse(spec_mod.path_allowed("../about.md", ["**"]))
        self.assertTrue(spec_mod.path_allowed("_posts/a/b.md", ["_posts/**"]))
        self.assertTrue(spec_mod.path_allowed("_posts/b.md", ["_posts/**"]))
        self.assertFalse(spec_mod.path_allowed("_posts/a/b.md", ["_posts/*"]))  # * 는 / 를 넘지 않는다

    def test_resolve_allowed_substitutes_placeholders(self):
        cfg = real_spec()["edit_types"]["text_change"]
        self.assertEqual(spec_mod.resolve_allowed(cfg, "about.md"), ["about.md"])


class PagesTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def root(self, **kw):
        return make_edit_root(self._tmp.name, **kw)

    def test_registry_lists_included_pages_sorted(self):
        root = self.root()
        got = pages.load_registry(root)
        self.assertEqual([p["id"] for p in got], ["about", "categories", "contact", "privacy"])
        self.assertEqual(got[0], {"id": "about", "title": "소개와 편집 원칙", "path": "about.md", "url": "/about/"})

    def test_editable_front_matter_adds_new_page_automatically(self):
        root = self.root(extra_pages={"faq.md": "---\nlayout: info\ntitle: 자주 묻는 질문\neditable: true\npermalink: /faq/\n---\n본문\n",
                                      "notes.md": "---\ntitle: 편집 불가\n---\n본문\n"})
        write(root, "extra.html", "---\ntitle: x\neditable: false\n---\n")
        spec = spec_mod.load_spec(root)
        ids = [p["id"] for p in pages.discover_pages(root, spec)]
        self.assertIn("faq", ids)
        self.assertNotIn("notes", ids)    # editable 표시가 없으면 목록에 오르지 않는다
        self.assertNotIn("extra", ids)

    def test_exclude_wins_and_never_allowed_pages_fail_closed(self):
        root = self.root(extra_pages={"README.md": "---\ntitle: r\neditable: true\n---\n"})
        spec = spec_mod.load_spec(root)
        # README.md 는 discover.exclude 에 있어 제외된다
        self.assertNotIn("README", [p["id"] for p in pages.discover_pages(root, spec)])
        spec["targets"]["page"]["discover"]["exclude"] = []
        with self.assertRaises(pages.PagesError):
            pages.discover_pages(root, spec)

    def test_bad_ids_and_duplicates(self):
        root = self.root()
        spec = spec_mod.load_spec(root)
        write(root, "한글.md", "---\ntitle: t\neditable: true\n---\n")
        with self.assertRaises(pages.PagesError):
            pages.discover_pages(root, spec)
        (Path(root) / "한글.md").unlink()
        write(root, "a1.md", "---\ntitle: t\neditable: true\nedit_id: about\n---\n")
        with self.assertRaises(pages.PagesError):
            pages.discover_pages(root, spec)

    def test_missing_include_is_an_error(self):
        root = self.root()
        (Path(root) / "contact.md").unlink()
        with self.assertRaises(pages.PagesError):
            pages.discover_pages(root, spec_mod.load_spec(root))

    def test_check_detects_stale_registry_and_is_deterministic(self):
        root = self.root()
        spec = spec_mod.load_spec(root)
        self.assertEqual(pages.check_registry(root, spec), [])
        a = pages.render_registry(pages.discover_pages(root, spec))
        self.assertEqual(a, pages.render_registry(pages.discover_pages(root, spec)))
        write(root, "faq.md", "---\ntitle: t\neditable: true\n---\n")
        self.assertEqual(len(pages.check_registry(root, spec)), 1)

    def test_real_repository_registry_is_current(self):
        self.assertEqual(pages.check_registry(REAL, real_spec()), [])


class FormsTest(unittest.TestCase):
    def setUp(self):
        self.templates = forms.load_templates(REAL)
        self.labels = forms.label_map(self.templates)

    def test_templates_and_labels(self):
        files = {t["file"] for t in forms.control_templates(self.templates)}
        self.assertEqual(files, {"blog_control.yml", "page-edit.yml"})
        self.assertEqual(self.labels["대상 페이지"], "target_page")
        self.assertEqual(self.labels["게시글 주소 또는 제목"], "target_post")
        self.assertEqual(forms.field_labels(self.templates)["after"], "변경 후 / 요청 내용")

    def test_parse_crlf_body_and_no_response(self):
        fields, dups = forms.parse_issue_body(page_body(after="새 문구"), self.labels)
        self.assertEqual(dups, [])
        self.assertEqual(fields["target_page"], "about | 소개와 편집 원칙")
        self.assertEqual(fields["before"], "")          # _No response_ → 빈 값
        self.assertEqual(fields["after"], "새 문구")

    def test_unknown_headings_stay_inside_the_value(self):
        body = page_body(after="첫 줄\n### 내가 만든 제목\n둘째 줄", crlf=False)
        fields, dups = forms.parse_issue_body(body, self.labels)
        self.assertEqual(dups, [])
        self.assertEqual(fields["after"], "첫 줄\n### 내가 만든 제목\n둘째 줄")

    def test_duplicate_known_heading_is_detected(self):
        body = page_body(after="x\n### 대상 페이지\nprivacy | 개인정보처리방침", crlf=False)
        _fields, dups = forms.parse_issue_body(body, self.labels)
        self.assertEqual(dups, ["대상 페이지"])

    def test_option_id(self):
        self.assertEqual(forms.option_id("about | 소개와 편집 원칙"), "about")
        self.assertEqual(forms.option_id(" text_change|문구 수정 "), "text_change")
        self.assertEqual(forms.option_id(None), "")

    def test_identify_issue_label(self):
        spec = real_spec()
        ident = lambda issue: forms.identify_issue_label(issue, spec, self.templates, self.labels)  # noqa: E731
        self.assertEqual(ident({"labels": [{"name": "blog-control"}, {"name": "edit:page"}]})[0], "edit:page")
        self.assertEqual(ident({"labels": ["edit:image"]})[0], "edit:image")
        self.assertIsNone(ident({"labels": [{"name": "edit:page"}, {"name": "edit:image"}]})[0])
        self.assertEqual(ident({"labels": [], "title": "[이미지 변경] 아무거나"})[0], "edit:image")   # 라벨이 없으면 제목 접두사
        self.assertEqual(ident({"labels": [], "title": "무제", "body": page_body(after="x")})[0], "edit:page")  # 라벨·제목이 없으면 항목 구성
        self.assertIsNone(ident({"labels": [], "title": "무제", "body": "아무 내용"})[0])

    def test_marker_replace_is_idempotent_and_validates(self):
        text = "a:\n  opts:\n    # X:START note\n    - old\n    # X:END\nb: 1"
        once = forms.replace_marker_block(text, "X", ["a | A", "b | B"])
        self.assertIn('    - "a | A"\n    - "b | B"\n    # X:END', once)
        self.assertEqual(forms.replace_marker_block(once, "X", ["a | A", "b | B"]), once)
        with self.assertRaises(forms.FormError):
            forms.replace_marker_block(text, "Y", ["a"])
        with self.assertRaises(forms.FormError):
            forms.replace_marker_block(text, "X", [])

    def test_real_form_is_in_sync(self):
        spec = real_spec()
        self.assertFalse(forms.sync_page_form(REAL, spec, pages.load_registry(REAL), write=False))


class TargetsTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = make_edit_root(self._tmp.name)
        self.index = targets.load_post_index(self.root)

    def paths(self, query):
        hits, how = targets.match_post(query, self.index)
        return [h["path"] for h in hits], how

    def test_url_paths_follow_jekyll_permalink(self):
        entry = next(e for e in self.index if e["path"].endswith("2026-10-18-KR-111111.md"))
        self.assertEqual(entry["url_path"], "/chanceblog/posts/2026/10/18/kr-111111")

    def test_match_by_url_variants(self):
        want = (["_posts/KR - 테크/2026-10-18-KR-111111.md"], "url")
        for q in ("https://shine88pc.github.io/chanceblog/posts/2026/10/18/kr-111111/",
                  "https://shine88pc.github.io/chanceblog/posts/2026/10/18/kr-111111",
                  "https://SHINE88PC.github.io/chanceblog/posts/2026/10/18/KR-111111/?utm=x#top",
                  "/chanceblog/posts/2026/10/18/kr-111111/"):
            self.assertEqual(self.paths(q), want, q)

    def test_match_by_filename_and_title(self):
        self.assertEqual(self.paths("2026-10-19-KR-222222.md"), (["_posts/2026-10-19-KR-222222.md"], "filename"))
        self.assertEqual(self.paths("두 번째 글 제목입니다"), (["_posts/2026-10-19-KR-222222.md"], "title"))
        self.assertEqual(self.paths("“First post title”"), (["_posts/EN - Tech/2026-10-18-EN-111111.md"], "title"))

    def test_partial_title_needs_enough_characters(self):
        self.assertEqual(self.paths("두 번째 글 제목")[1], "contains")
        self.assertEqual(self.paths("두 번째")[1], "none")        # 8자 미만 부분 일치는 쓰지 않는다

    def test_ambiguous_and_unknown(self):
        paths, how = self.paths("같은 제목의 글입니다")
        self.assertEqual((len(paths), how), (2, "title"))
        self.assertEqual(self.paths("존재하지 않는 글 제목입니다"), ([], "none"))

    def test_unpublished_posts_are_not_reachable_by_url(self):
        self.assertEqual(self.paths("https://shine88pc.github.io/chanceblog/posts/2026/10/20/kr-555555/"), ([], "none"))
        self.assertEqual(self.paths("비공개 글 제목입니다")[1], "title")  # 제목으로는 지정 가능

    def test_invalid_queries(self):
        for q in ("", "   ", "줄\n바꿈", "x" * 400):
            self.assertEqual(targets.match_post(q, self.index)[1], "invalid")

    def test_addresses_urlsplit_cannot_parse_are_invalid_not_exceptions(self):
        """검증자 F-6: `http://[::1`·`https://[` 는 urlsplit 이 ValueError 를 낸다(전각 슬래시 같은 NFKC 문제도 같다). 예외가 새면 러너가 죽는다."""
        for q in ("http://[::1", "https://[", "http://[", "HTTPS://[::1", "https://example.com\N{FULLWIDTH SOLIDUS}path",
                  "http://\N{ACCOUNT OF}/", "http://a\N{FULLWIDTH COMMERCIAL AT}b/x"):
            self.assertEqual(targets.match_post(q, self.index), ([], "invalid"), q)
        self.assertEqual(targets.match_post("/[::1", self.index)[1], "none")        # 상대 경로는 urlsplit 을 쓰지 않는다


if __name__ == "__main__":
    unittest.main()
