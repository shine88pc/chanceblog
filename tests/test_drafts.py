"""Chance 승인 흐름(pipeline/drafts.py)의 규칙 시험: 발행 흐름 읽기·레지스트리 검증, 초안 브랜치 이름, 슬롯 판정, 외부 문구 소독,
PR 제목·본문, GitHub REST 클라이언트(가짜 opener). 네트워크 없이 돈다. 설계 근거: docs/ARCHITECTURE.md §4-4.
"""
import copy
import io
import json
import re
import tempfile
import unittest
import urllib.error
from datetime import date
from pathlib import Path
from unittest import mock

import _bootstrap
import generator as g
from draft_helpers import LINK, REAL_PUBLISH_FLOW, REPO, post_text
from pipeline import drafts, registry

ROOT = _bootstrap.ROOT
ZW = "\u200b"


def real_registry():
    return registry.load_registry()


# ----------------------------------------------------------------------------
# 레지스트리 publish_flow
# ----------------------------------------------------------------------------
class PublishFlowRegistryTest(unittest.TestCase):
    def errors(self, mutate):
        reg = copy.deepcopy(real_registry())
        mutate(reg)
        return registry.validate_registry(reg)

    def assertHas(self, errors, fragment):
        self.assertTrue(any(fragment in e for e in errors), f"{fragment!r} 가 {errors} 에 없음")

    def test_the_real_registry_writes_direct_for_chance_and_is_valid(self):
        reg = real_registry()
        chance = next(b for b in reg["blogs"] if b["key"] == "chance")
        self.assertEqual(chance["publish_flow"], REAL_PUBLISH_FLOW)      # 지금 값을 파일에 적어 둔다(direct. 켜는 것은 T3 — draft_helpers.REAL_PUBLISH_FLOW)
        self.assertEqual(chance["mode"], "auto")                # mode 는 그대로
        self.assertEqual(registry.validate_registry(reg), [])
        self.assertEqual(registry.PUBLISH_FLOWS, ("direct", "pr"))

    def test_the_pr_title_prefix_and_the_channel_label_follow_the_registry_channel(self):
        """작업 A 가 정한 channel.label(워크플로 이름 맨 앞 `[라벨]`과 같은 글자)이 바뀌면 초안 PR 의 제목 접두와 `채널:` 라벨도 함께 바뀌어야 한다 —
        어긋나면 운영자가 같은 채널을 두 이름으로 보게 된다(상수와 레지스트리를 이 시험이 묶는다)."""
        label = registry.get_blog(real_registry(), "chance")["channel"]["label"]
        self.assertEqual(label, "Chance")
        self.assertEqual(drafts.PR_TITLE_PREFIX, f"[초안][{label}]")
        self.assertEqual(drafts.LABEL_CHANNEL, f"채널:{label}")
        self.assertTrue(drafts.build_pr_title("가", "a").startswith(f"[초안][{label}] "))

    def test_direct_and_pr_are_valid_for_chance(self):
        for flow in ("direct", "pr"):
            self.assertEqual(self.errors(lambda r, f=flow: r["blogs"][0].update(publish_flow=f)), [], flow)

    def test_the_key_may_be_left_out_and_means_direct(self):
        self.assertEqual(self.errors(lambda r: r["blogs"][0].pop("publish_flow")), [])

    def test_unknown_values_are_rejected(self):
        for bad in ("PR", "auto", "", "draft", 1, None, ["pr"], {"pr": 1}):
            with self.subTest(value=bad):
                self.assertHas(self.errors(lambda r, v=bad: r["blogs"][0].update(publish_flow=v)), "publish_flow는")

    def test_only_jekyll_git_may_use_it(self):
        for flow in ("direct", "pr"):
            errors = self.errors(lambda r, f=flow: r["blogs"][1].update(publish_flow=f))
            self.assertHas(errors, "jekyll-git 에서만")
            self.assertHas(errors, "blogger_macat")

    def test_a_default_in_defaults_reaches_blogger_and_is_rejected_there(self):
        self.assertHas(self.errors(lambda r: r["defaults"].update(publish_flow="pr")), "jekyll-git 에서만")

    def test_pr_requires_mode_auto(self):
        for mode in ("off", "draft"):
            def mutate(r, m=mode):
                r["blogs"][0].update(publish_flow="pr", mode=m)
            self.assertHas(self.errors(mutate), "mode 는 auto")

    def test_pr_with_a_missing_or_invalid_mode_reports_only_the_mode_error(self):
        """mode 를 적지 않았거나 올바르지 않은 값이면 기존 mode 오류가 원인을 알려 준다 — 같은 원인으로 'pr 이면 mode 는 auto' 오류를 또 내지 않는다
        (그래야 진짜 레지스트리를 쓰는 다른 시험이 `publish_flow: pr`을 켠 뒤에도 오류 개수를 그대로 센다)."""
        for bad in ("yolo", "", None, 3, ["auto"]):
            def mutate(r, v=bad):
                r["blogs"][0].update(publish_flow="pr", mode=v)
            errors = self.errors(mutate)
            self.assertHas(errors, "mode는")
            self.assertEqual([e for e in errors if "mode 는 auto" in e], [], bad)

        def drop_mode(r):
            r["blogs"][0].pop("mode")
            r["blogs"][0]["publish_flow"] = "pr"
        errors = self.errors(drop_mode)
        self.assertHas(errors, "mode를 이 항목에 직접 적어야")
        self.assertEqual([e for e in errors if "mode 는 auto" in e], [])

    def test_direct_does_not_constrain_mode(self):
        for mode in ("off", "draft", "auto"):
            def mutate(r, m=mode):
                r["blogs"][0].update(publish_flow="direct", mode=m)
            self.assertEqual(self.errors(mutate), [], mode)


class ChanceFlowTest(unittest.TestCase):
    def reg_file(self, mutate=None):
        reg = copy.deepcopy(real_registry())
        if mutate:
            mutate(reg)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "blogs.json"
        path.write_text(json.dumps(reg, ensure_ascii=False), encoding="utf-8")
        return path

    def test_the_real_registry_has_the_pinned_flow(self):
        """진짜 레지스트리의 값은 draft_helpers.REAL_PUBLISH_FLOW(지금 direct)와 같아야 한다 — 켜는 변경(T3)이 시험 없이 슬쩍 들어가지 못하게 하는 표지판."""
        self.assertEqual(drafts.chance_flow(), REAL_PUBLISH_FLOW)

    def test_reads_pr_and_defaults_to_direct_when_the_key_is_missing(self):
        self.assertEqual(drafts.chance_flow(self.reg_file(lambda r: r["blogs"][0].update(publish_flow="pr"))), "pr")
        self.assertEqual(drafts.chance_flow(self.reg_file(lambda r: r["blogs"][0].pop("publish_flow"))), "direct")

    def test_a_bad_value_stops_instead_of_falling_back_to_direct_publishing(self):
        for bad in ("PR", "yes", 7, None, ""):
            with self.subTest(value=bad):
                with self.assertRaises(drafts.DraftFlowError):
                    drafts.chance_flow(self.reg_file(lambda r, v=bad: r["blogs"][0].update(publish_flow=v)))

    def test_pr_with_a_wrong_mode_or_platform_stops(self):
        for fields in ({"mode": "draft"}, {"mode": "off"}, {"platform": "blogger"}):
            with self.subTest(fields=fields):
                with self.assertRaises(drafts.DraftFlowError):
                    drafts.chance_flow(self.reg_file(lambda r, f=fields: r["blogs"][0].update(publish_flow="pr", **f)))

    def test_an_unreadable_registry_or_a_missing_chance_entry_stops(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(drafts.DraftFlowError):
                drafts.chance_flow(Path(tmp) / "nope.json")
        with self.assertRaises(drafts.DraftFlowError):
            drafts.chance_flow(self.reg_file(lambda r: r["blogs"][0].update(key="other")))

    def test_the_cli_flow_command_prints_the_value_or_fails(self):
        from pipeline import draft_flow
        buf = io.StringIO()
        from contextlib import redirect_stdout
        with redirect_stdout(buf):
            self.assertEqual(draft_flow.main(["flow"]), 0)
        self.assertEqual(buf.getvalue().strip(), REAL_PUBLISH_FLOW)
        from contextlib import redirect_stderr
        with redirect_stderr(io.StringIO()):
            self.assertEqual(draft_flow.main(["nope"]), 2)


# ----------------------------------------------------------------------------
# 초안 브랜치 이름
# ----------------------------------------------------------------------------
class BranchNameTest(unittest.TestCase):
    def test_scheduled_and_manual_names(self):
        self.assertEqual(drafts.branch_name("2026-10-28", 9), "ai/draft/2026-10-28-s9")
        self.assertEqual(drafts.branch_name("2026-10-28", 18), "ai/draft/2026-10-28-s18")
        self.assertEqual(drafts.branch_name("2026-10-28", None, "091722"), "ai/draft/2026-10-28-m091722")
        self.assertEqual(drafts.branch_name("2026-10-28", 0), "ai/draft/2026-10-28-s0")   # 슬롯 0시도 슬롯이다(None 과 다르다)

    def test_two_slots_never_share_a_name_and_a_slot_never_shares_with_manual(self):
        names = {drafts.branch_name("2026-10-28", 9), drafts.branch_name("2026-10-28", 18), drafts.branch_name("2026-10-29", 9),
                 drafts.branch_name("2026-10-28", None, "090000")}
        self.assertEqual(len(names), 4)

    def test_bad_inputs_are_rejected(self):
        for args in (("2026-10-28", 24), ("2026-10-28", -1), ("2026-10-28", True), ("2026-10-28", "9"), ("28-10-2026", 9),
                     ("2026-10-28", None, ""), ("2026-10-28", None, "9172"), ("2026-10-28", None, None), ("2026-10-28 ", 9)):
            with self.subTest(args=args):
                with self.assertRaises(ValueError):
                    drafts.branch_name(*args)

    def test_parse_roundtrips_and_ignores_other_branches(self):
        info = drafts.parse_branch("ai/draft/2026-10-28-s18")
        self.assertEqual((info.day, info.slot, info.stamp), (date(2026, 10, 28), 18, None))
        info = drafts.parse_branch("ai/draft/2026-10-28-m091722")
        self.assertEqual((info.day, info.slot, info.stamp), (date(2026, 10, 28), None, "091722"))
        for other in ("main", "ai/claude/chance-approval-flow", "ai/draft/", "ai/draft/x", "ai/draft/2026-10-28-s24",
                      "ai/draft/2026-13-45-s9", "ai/draft/2026-10-28-s9/extra", "ai/draft/2026-10-28-s9 ", "xai/draft/2026-10-28-s9",
                      "ai/draft/2026-10-28-m09172", "", None):
            with self.subTest(name=other):
                self.assertIsNone(drafts.parse_branch(other))

    def test_entry_fields_for_slot_and_manual(self):
        fields = drafts.entry_fields("2026-10-28", 9, "091722", [Path("_posts/a/KR.md"), "_posts\\b\\EN.md".replace("\\", "/")])
        self.assertEqual(fields, {"flow": "pr", "branch": "ai/draft/2026-10-28-s9", "paths": ["_posts/a/KR.md", "_posts/b/EN.md"]})
        manual = drafts.entry_fields("2026-10-28", None, "091722", ["_posts/a.md"])
        self.assertEqual(manual["branch"], "ai/draft/2026-10-28-m091722")

    def test_post_path_validation(self):
        good = ["_posts/기술·미래/2026-10-28-KR-091722.md", "_posts/Technology & Future/2026-10-28-EN-091722.md"]
        for path in good:
            self.assertTrue(drafts.valid_post_path(path), path)
        for bad in ("posts/a.md", "_posts/a.txt", "_posts/../x.md", "/_posts/a.md", "_posts/a\\b.md", "_posts/a\nb.md", "_posts/.md", "", None, 5):
            with self.subTest(path=bad):
                self.assertFalse(drafts.valid_post_path(bad))


# ----------------------------------------------------------------------------
# 슬롯 판정
# ----------------------------------------------------------------------------
class RefineSlotStateTest(unittest.TestCase):
    DATE = "2026-10-28"

    def entry(self, **extra):
        item = {"date": self.DATE, "slot": 9, "topic": "t", **drafts.entry_fields(self.DATE, 9, None, ["_posts/a/KR.md", "_posts/b/EN.md"])}
        item.update(extra)
        return item

    def refine(self, state, history, branch_exists=False, present=()):
        return drafts.refine_slot_state(state, 9, history, self.DATE, branch_exists, exists=lambda p: p in present)

    def test_a_draft_whose_posts_are_not_on_main_is_pending(self):
        self.assertEqual(self.refine("ALREADY_PUBLISHED", [self.entry()]), "DRAFT_PENDING")

    def test_a_draft_whose_posts_are_all_on_main_is_already_published(self):
        both = {"_posts/a/KR.md", "_posts/b/EN.md"}
        self.assertEqual(self.refine("ALREADY_PUBLISHED", [self.entry()], present=both), "ALREADY_PUBLISHED")

    def test_one_missing_post_still_counts_as_pending(self):
        self.assertEqual(self.refine("ALREADY_PUBLISHED", [self.entry()], present={"_posts/a/KR.md"}), "DRAFT_PENDING")

    def test_direct_flow_entries_and_legacy_entries_are_already_published(self):
        direct = {"date": self.DATE, "slot": 9, "topic": "t"}
        self.assertEqual(self.refine("ALREADY_PUBLISHED", [direct]), "ALREADY_PUBLISHED")
        self.assertEqual(self.refine("ALREADY_PUBLISHED", [self.entry(flow="direct")]), "ALREADY_PUBLISHED")
        self.assertEqual(self.refine("ALREADY_PUBLISHED", ["옛 문자열 항목", direct]), "ALREADY_PUBLISHED")

    def test_a_pr_entry_with_broken_paths_is_pending_not_regenerated(self):
        for paths in (None, [], "x", ["../x.md", "_posts/a.md"], [5]):
            with self.subTest(paths=paths):
                self.assertEqual(self.refine("ALREADY_PUBLISHED", [self.entry(paths=paths)], present={"../x.md", "_posts/a.md"}), "DRAFT_PENDING")

    def test_due_with_an_existing_branch_is_pending(self):
        self.assertEqual(self.refine("DUE", [], branch_exists=True), "DRAFT_PENDING")

    def test_due_without_a_branch_stays_due(self):
        self.assertEqual(self.refine("DUE", [], branch_exists=False), "DUE")

    def test_due_with_an_unreadable_remote_is_a_check_failure(self):
        self.assertEqual(self.refine("DUE", [], branch_exists=None), "DRAFT_CHECK_FAILED")

    def test_out_of_window_is_left_alone_whatever_the_branch_says(self):
        for exists in (True, False, None):
            self.assertEqual(self.refine("OUT_OF_WINDOW", [], branch_exists=exists), "OUT_OF_WINDOW")

    def test_the_other_slot_and_other_days_do_not_interfere(self):
        other_slot = self.entry(slot=18)
        other_day = self.entry(date="2026-10-27")
        self.assertEqual(self.refine("ALREADY_PUBLISHED", [other_slot, other_day]), "ALREADY_PUBLISHED")   # 이 슬롯 항목이 없으면 그대로(slot_state 가 DUE 를 줬을 것)
        self.assertEqual(drafts.slot_entry([other_slot, other_day, self.entry()], self.DATE, 9)["slot"], 9)
        self.assertIsNone(drafts.slot_entry([other_slot, other_day], self.DATE, 9))


# ----------------------------------------------------------------------------
# 외부 문구 소독
# ----------------------------------------------------------------------------
class NeutralizeTest(unittest.TestCase):
    def test_mentions_lose_their_power(self):
        out = drafts.neutralize("@octocat @org/team hi me@example.com")
        self.assertNotRegex(out, r"@[A-Za-z0-9]")
        self.assertIn("@" + ZW + "octocat", out)

    def test_issue_references_and_gh_references_lose_their_power(self):
        out = drafts.neutralize("fixes #123, see owner/repo#45, GH-9, gh-10 and C#")
        self.assertNotRegex(out, r"#\d")
        self.assertNotRegex(out, r"(?i)GH-\d")
        self.assertNotRegex(out, r"# ")      # '# 제목' 도 머리글이 못 된다

    def test_html_comments_scripts_and_tags_are_removed_or_defused(self):
        text = "a <!-- hidden --> b <script>alert(1)</script> c <iframe src=x></iframe> d <img src=x onerror=y> e <b>bold</b> f"
        out = drafts.neutralize(text)
        for needle in ("<", ">", "hidden", "alert", "iframe", "script"):
            self.assertNotIn(needle, out)
        self.assertIn("bold", out)       # 일반 태그는 글자만 남기고 꺾쇠를 무력화한다(＜b＞bold＜/b＞)
        self.assertIn("＜img src=x onerror=y＞", out)

    def test_unterminated_comment_and_script_swallow_the_rest(self):
        self.assertEqual(drafts.neutralize("앞 <!-- 닫히지 않은 주석 뒤"), "앞")
        self.assertEqual(drafts.neutralize("앞 <script>alert(1) 뒤"), "앞")

    def test_nested_and_case_variants_are_removed(self):
        out = drafts.neutralize("<SCRIPT >x</ScRiPt> <ScRiPt src=//e.com/x.js></script> <STYLE>p{}</STYLE>")
        self.assertNotRegex(out, r"(?i)script|style|<|>")

    def test_markdown_links_images_and_code_spans_are_defused(self):
        out = drafts.neutralize("[x](http://evil.test) ![i](http://evil.test/a.png) `code` ```fence``` ~~~tilde~~~")
        for needle in ("[", "]", "`", "~~~", "](", "://"):
            self.assertNotIn(needle, out)

    def test_bare_urls_are_no_longer_autolinks(self):
        out = drafts.neutralize("방문: https://evil.test/x 또는 http://a.b ftp://c.d")
        self.assertNotIn("://", out)
        self.assertIn("evil.test", out)

    def test_entity_references_cannot_rebuild_a_mention(self):
        out = drafts.neutralize("&#64;octocat &#x40;octocat &commat;octocat &amp; 그리고 AT&T")
        self.assertEqual(re.findall(r"&(?!amp;)#?\w+;", out), [])    # 문자 참조는 '&amp;' 로 한 번 감싸 글자 그대로 보인다(우리 쪽 &amp; 만 남는다)
        self.assertNotIn("&#", out)
        self.assertIn("AT&T", out)                  # 참조가 아닌 & 는 그대로

    def test_www_addresses_are_not_autolinks_either(self):
        out = drafts.neutralize("www.evil.test/x 와 WWW.Evil.test 와 awww.x")
        self.assertNotRegex(out, r"(?i)\bwww\.")
        self.assertIn("evil.test/x", out)
        self.assertIn("awww.x", out)                # 낱말 가운데의 www. 는 주소가 아니다

    def test_invisible_and_bidi_characters_are_removed_before_neutralizing(self):
        out = drafts.neutralize("a\u200bb\u202ec\u2066d\ufeffe @\u200boctocat")
        for ch in ("\u202e", "\u2066", "\ufeff"):
            self.assertNotIn(ch, out)
        self.assertNotRegex(out, r"@(?!" + ZW + r")")

    def test_newlines_and_workflow_commands_are_folded(self):
        out = drafts.neutralize("첫 줄\n::error::가짜 명령\r\n##[group]x\u2028다음")
        self.assertNotIn("\n", out)
        self.assertNotIn("\r", out)
        self.assertNotIn("::", out)
        self.assertNotIn("##[", out)

    def test_secret_shapes_are_masked(self):
        out = drafts.neutralize("토큰 ghs_" + "a" * 36 + " 와 AIza" + "b" * 35 + " 와 key=abc123def")
        self.assertNotIn("ghs_", out)
        self.assertNotIn("AIza", out)
        self.assertNotIn("abc123def", out)

    def test_length_limit_adds_an_ellipsis_and_none_is_empty(self):
        out = drafts.neutralize("가" * 500, 50)
        self.assertEqual(len(out), 50)
        self.assertTrue(out.endswith("…"))
        self.assertEqual(drafts.neutralize(None), "")
        self.assertEqual(drafts.neutralize("  \n "), "")
        self.assertEqual(drafts.neutralize("짧은 글", 50), "짧은 글")
        self.assertEqual(len(drafts.neutralize("가" * 50, 50)), 50)         # 한도와 같으면 자르지 않는다

    def test_safe_url_accepts_only_plain_https(self):
        self.assertEqual(drafts.safe_url("https://www.reuters.com/a?b=1#c"), "https://www.reuters.com/a?b=1#c")
        for bad in ("http://x.test/a", "javascript:alert(1)", "https://x.test/a b", "https://x.test/a)b", "https://x.test/<a>",
                    "https://x.test/`a`", "https://x.test/a|b", "https://" + "a" * 600, "", None, "ftp://x.test/"):
            with self.subTest(url=bad):
                self.assertEqual(drafts.safe_url(bad), "")

    def test_owner_and_repo_validation(self):
        for good in ("shine88pc", "a", "A-b-1"):
            self.assertTrue(drafts.valid_owner(good), good)
        for bad in ("", "-x", "a b", "a/b", "x" * 40, "@x", None, "a\n", "a\n@evil"):
            self.assertFalse(drafts.valid_owner(bad), repr(bad))
        self.assertTrue(drafts.valid_repo("shine88pc/chanceblog"))
        for bad in ("shine88pc", "a/..", "a/b c", "../x", "a/b/c", "", "a/b\n", "a/b\n@evil"):
            self.assertFalse(drafts.valid_repo(bad), repr(bad))

    def test_trailing_newlines_never_pass_a_shape_check(self):
        """정규식의 `$` 는 끝의 줄바꿈 앞에서도 맞는다 — 모양 검사가 줄바꿈 하나를 통과시키면 멘션·링크 줄을 끼워 넣을 수 있다."""
        self.assertEqual(drafts.safe_url("https://x.test/a\n"), "")
        self.assertEqual(drafts.safe_url("https://x.test/a\n[x](http://e.test)"), "")
        self.assertFalse(drafts.valid_post_path("_posts/a/b.md\n"))
        self.assertIsNone(drafts.parse_branch("ai/draft/2026-10-28-s9\n"))
        with self.assertRaises(ValueError):
            drafts.branch_name("2026-10-28\n", 9)
        with self.assertRaises(ValueError):
            drafts.branch_name("2026-10-28", None, "091722\n")


# ----------------------------------------------------------------------------
# 글 파일에서 읽는 점검 값
# ----------------------------------------------------------------------------
class PostFactsTest(unittest.TestCase):
    def test_readable_length_matches_the_generators_gate_on_thin_posts(self):
        """분량을 재는 방식이 생성기의 본문 검증과 같다 — 같은 글에서 같은 숫자가 나와야 PR 본문의 '통과/미달'이 거짓말을 하지 않는다."""
        for repeats in (1, 5, 20, 60):
            text = post_text("제목", LINK, body_chars=repeats)
            _front, body = drafts.split_post(text)
            mine = drafts.readable_length(body)
            try:
                g._validate_editorial_body(text, "kr", LINK)
                self.fail("얇은 글인데 통과했습니다")
            except ValueError as exc:
                theirs = int(re.search(r":\s*(\d+)자", str(exc)).group(1))
            self.assertEqual(mine, theirs, repeats)

    def test_the_minimums_are_the_generators_minimums(self):
        self.assertEqual(drafts.MIN_BODY_CHARS, g.MIN_BODY_CHARS)

    def test_the_pr_body_marks_exactly_the_minimum_as_a_pass_and_one_less_as_a_shortfall(self):
        """'통과/미달' 표시의 경계: 기준과 같은 글자 수는 통과(생성기의 본문 검증도 같은 글자 수를 통과시킨다), 하나 모자라면 미달."""
        for language, minimum in drafts.MIN_BODY_CHARS.items():
            exact, short = "가" * minimum, "가" * (minimum - 1)
            self.assertEqual(drafts.readable_length(exact), minimum)
            self.assertIn("통과", drafts._facts(exact, LINK, minimum)[0], language)
            self.assertIn("미달(확인 필요)", drafts._facts(short, LINK, minimum)[0], language)

    def test_the_pass_boundary_is_the_same(self):
        outcomes = set()
        for repeats in range(78, 92):
            text = post_text("제목", LINK, body_chars=repeats)
            _front, body = drafts.split_post(text)
            passes = True
            try:
                g._validate_editorial_body(text, "kr", LINK)
            except ValueError:
                passes = False
            outcomes.add(passes)
            self.assertEqual(drafts.readable_length(body) >= drafts.MIN_BODY_CHARS["kr"], passes, repeats)
        self.assertEqual(outcomes, {True, False})      # 범위가 경계를 가로지르는지(한쪽만 보면 같은 값이어도 아무것도 증명하지 못한다)

    def test_split_post_and_front_value(self):
        front, body = drafts.split_post("\ufeff---\ntitle: \"가 나\"\ncategory: '분야'\nempty:\n---\n\n본문\n")
        self.assertEqual(drafts.front_value(front, "title"), "가 나")
        self.assertEqual(drafts.front_value(front, "category"), "분야")
        self.assertEqual(drafts.front_value(front, "empty"), "")
        self.assertEqual(drafts.front_value(front, "missing"), "")
        self.assertEqual(body.strip(), "본문")
        self.assertEqual(drafts.split_post("front matter 없음"), ("", "front matter 없음"))
        self.assertEqual(drafts.split_post(None), ("", ""))

    def test_source_list_citation_and_notice_detection(self):
        _front, body = drafts.split_post(post_text("제목", LINK))
        self.assertTrue(drafts.cites_source(body, LINK))
        self.assertTrue(drafts.has_source_list(body, LINK))
        self.assertTrue(drafts.has_notice(body))
        _front, plain = drafts.split_post(post_text("제목", LINK, notice=False))
        self.assertFalse(drafts.has_notice(plain))
        self.assertFalse(drafts.cites_source(body, "https://other.test/x"))
        self.assertFalse(drafts.has_source_list(body, "https://other.test/x"))
        self.assertFalse(drafts.cites_source(body, ""))
        # 출처 목록에만 있고 본문에는 없는 인용은 인용이 아니다(생성기의 본문 검증과 같은 기준)
        only_in_list = "본문 문단입니다.\n\n## 출처\n- [x](" + LINK + ")\n"
        self.assertFalse(drafts.cites_source(only_in_list, LINK))
        self.assertTrue(drafts.has_source_list(only_in_list, LINK))

    def test_a_short_italic_line_or_a_multiline_block_is_not_a_notice(self):
        self.assertFalse(drafts.has_notice("본문\n\n*짧음*\n"))
        self.assertFalse(drafts.has_notice("본문\n\n*" + "가" * 30 + "\n" + "나" * 30 + "*\n"))
        self.assertFalse(drafts.has_notice(""))

    def test_excerpt_skips_headings_images_and_links_and_cuts_long_paragraphs(self):
        body = ("# 제목\n\n![이미지](https://x.test/a.png)\n\n짧은 줄\n\n"
                + "이 문단은 [링크 글자](https://evil.test/x)와 **강조**와 `코드`를 담고 있고 충분히 깁니다. " * 8 + "\n\n## 출처\n- a\n")
        out = drafts.excerpt_of(body, 120)
        self.assertLessEqual(len(out), 120)
        self.assertTrue(out.endswith("…"))
        self.assertIn("링크 글자", out)
        for needle in ("evil.test", "**", "`", "![", "#"):
            self.assertNotIn(needle, out)
        self.assertEqual(drafts.excerpt_of("짧은 글\n\n## 출처\n- 긴 문단이 출처 목록에만 있어도 발췌하지 않는다 " * 5), "")


# ----------------------------------------------------------------------------
# PR 제목·본문
# ----------------------------------------------------------------------------
def entry(**extra):
    item = {"date": "2026-10-28", "slot": 9, "topic": "후보 기사", "kr_title": "한국어 제목", "en_title": "English Title", "lane": "technology",
            "source": "Reuters", "source_url": LINK}
    item.update(extra)
    return item


class PrTitleTest(unittest.TestCase):
    def test_format_and_prefix(self):
        self.assertEqual(drafts.build_pr_title("한국어 제목", "English Title"), "[초안][Chance] 한국어 제목 / English Title")
        self.assertTrue(drafts.build_pr_title("a", "b").startswith(drafts.PR_TITLE_PREFIX + " "))
        self.assertEqual(drafts.PR_TITLE_PREFIX, "[초안][Chance]")

    def test_each_title_is_clipped_and_the_whole_title_is_limited(self):
        title = drafts.build_pr_title("가" * 300, "b" * 300)
        self.assertLessEqual(len(title), drafts.TITLE_LIMIT)
        self.assertEqual(title.count("…"), 2)
        self.assertIn(" / ", title)
        self.assertEqual(len(drafts.build_pr_title("가" * 80, "b" * 80)), len("[초안][Chance] ") + 80 + 3 + 80)

    def test_the_whole_title_limit_is_enforced_even_when_each_title_fits(self):
        """제목마다 80자로 줄이므로 기본 한도(200자)에는 닿지 않는다. 한도를 낮추면 전체 제목을 줄이고 줄임표로 끝난다(GitHub 한도 256자 안쪽을 지키는 마지막 안전망)."""
        title = drafts.build_pr_title("가" * 80, "b" * 80, limit=60)
        self.assertLessEqual(len(title), 60)
        self.assertTrue(title.endswith("…"))
        self.assertTrue(title.startswith(drafts.PR_TITLE_PREFIX + " "))
        self.assertEqual(drafts.TITLE_LIMIT, 200)

    def test_titles_are_neutralized_and_never_empty(self):
        title = drafts.build_pr_title("@owner #5 <b>x</b> [l](http://e.test)", "AT&T `c`")
        self.assertTrue(title.startswith(drafts.PR_TITLE_PREFIX + " "))
        self.assertNotRegex(title[len(drafts.PR_TITLE_PREFIX):], r"@[A-Za-z0-9]|#\d|<|>|\[|\]|`|://")
        self.assertEqual(drafts.build_pr_title("", None), "[초안][Chance] (제목 없음) / (no title)")


class PrBodyTest(unittest.TestCase):
    def body(self, e=None, kr=None, en=None, owner="shine88pc"):
        e = e or entry()
        return drafts.build_pr_body(e, kr or post_text(e["kr_title"], LINK), en or post_text(e["en_title"], LINK), owner=owner)

    def test_required_sections_in_order(self):
        body = self.body()
        positions = [body.index(h) for h in ("## 요약", "## 제목", "## 첫 문단 발췌", "## 자동 점검 결과", "## 승인 체크리스트", "## 안내")]
        self.assertEqual(positions, sorted(positions))

    def test_the_approval_notice_and_the_checklist_are_exact(self):
        body = self.body()
        self.assertTrue(body.startswith("@shine88pc **승인 대기 초안**입니다. **병합(Merge)하면 공개**되고, **닫으면(Close) 폐기**됩니다."))
        for line in ("- [ ] 원문과 수치·사실을 대조했다", "- [ ] 제목·요약에 문제가 없다", "- [ ] 병합 = 공개(사람 검토 단계)"):
            self.assertIn("\n" + line + "\n", body + "\n")
        self.assertEqual(body.count("- [ ]"), 3)

    def test_summary_has_category_source_link_slot_and_titles(self):
        body = self.body()
        self.assertIn("- 분야: 기술·미래", body)
        self.assertIn(f"- 출처: Reuters — [원문 보기]({LINK})", body)
        self.assertIn("- 발행 슬롯: 2026-10-28 9시 슬롯", body)
        self.assertIn("- 한국어: 한국어 제목", body)
        self.assertIn("- English: English Title", body)
        self.assertIn("수동 실행(슬롯 없음)", self.body(entry(slot=None)))

    def test_the_excerpt_is_a_two_part_blockquote(self):
        body = self.body()
        quote = body.split("## 첫 문단 발췌\n", 1)[1].split("\n\n## ", 1)[0].split("\n")
        self.assertEqual(len(quote), 3)
        self.assertTrue(quote[0].startswith("> **한국어** 이 글은 시험용 본문입니다."))
        self.assertEqual(quote[1], ">")
        self.assertTrue(quote[2].startswith("> **English**"))

    def test_the_automatic_checks_report_real_numbers(self):
        body = self.body()
        self.assertRegex(body, r"- 본문 분량: 한국어 [\d,]+자\(최소 1,000자, 통과\) · 영어 [\d,]+자\(최소 1,500자, 통과\)")
        self.assertIn("- 원문 링크 인용: 한국어 있음 · 영어 있음", body)
        self.assertIn("- 글 끝 출처 목록: 한국어 있음 · 영어 있음", body)
        self.assertIn("- 출처 고지문(AI 작성·검토 안 받음 안내): 한국어 있음 · 영어 있음", body)

    def test_a_thin_post_or_missing_items_are_flagged_not_hidden(self):
        thin = post_text("제목", LINK, body_chars=3, notice=False)
        body = self.body(kr=thin)
        self.assertIn("미달(확인 필요)", body)
        self.assertIn("**없음(확인 필요)**", body)
        no_cite = post_text("제목", "https://other.test/x")
        self.assertIn("원문 링크 인용: 한국어 **없음(확인 필요)**", self.body(kr=no_cite))

    def test_the_owner_is_mentioned_only_when_it_is_a_valid_login(self):
        for owner in (None, "", "a b", "evil\n@x", "x" * 50):
            body = self.body(owner=owner)
            self.assertTrue(body.startswith("**승인 대기 초안**"), repr(owner))
        self.assertNotRegex(self.body(owner="bad name"), r"(?<![\w`])@[A-Za-z]")

    def test_ai_text_cannot_inject_mentions_references_html_links_or_fences(self):
        evil = "<script>alert(1)</script>@evil #123 [x](http://e.test) ```fence``` <!-- c --> &#64;evil2 ![i](http://e.test/a.png) https://evil.test/x"
        e = entry(kr_title=evil, en_title=evil, source=evil, topic=evil)
        text = post_text("제목", LINK).replace("이 글은 시험용 본문입니다.", evil, 1)
        body = self.body(e, kr=text, en=text)
        self.assertNotIn("<", body)
        quoted = [ln for ln in body.splitlines() if ">" in ln]
        self.assertEqual(len(quoted), 3)                                            # 우리가 붙인 인용 표시(`>`) 세 줄뿐이다
        for ln in quoted:
            self.assertEqual(ln.count(">"), 1)
            self.assertTrue(ln == ">" or ln.startswith("> **한국어** ") or ln.startswith("> **English** "), ln)
        self.assertNotIn("```", body)
        self.assertNotIn("](http", body.replace(f"]({LINK})", ""))
        self.assertNotRegex(body, r"(?<!shine88pc)(?<=[\s>])@[A-Za-z0-9]")
        self.assertEqual(re.findall(r"(?<![\w])@[A-Za-z0-9][\w-]*", body), ["@shine88pc"])
        self.assertNotRegex(body, r"#\d")
        self.assertNotIn("://", body.replace(LINK, ""))
        headings = [ln for ln in body.splitlines() if ln.startswith("#")]
        self.assertEqual(headings, ["## 요약", "## 제목", "## 첫 문단 발췌", "## 자동 점검 결과(저장 전에 이미 통과한 항목 — 사람의 확인을 대신하지 않습니다)",
                                    "## 승인 체크리스트", "## 안내"])

    def test_ai_text_cannot_add_checklist_items_or_extra_lines(self):
        evil = "제목\n- [x] 이미 확인함\n## 가짜 구역\n> 가짜 인용"
        body = self.body(entry(kr_title=evil, en_title=evil))
        self.assertEqual(body.count("- [ ]"), 3)
        self.assertNotIn("- [x]", body)
        self.assertNotIn("## 가짜 구역", body)

    def test_an_unsafe_source_url_gets_no_link(self):
        for url in ("javascript:alert(1)", "http://insecure.test/a", "https://x.test/a b", "https://x.test/a)(b", ""):
            body = self.body(entry(source_url=url))
            self.assertNotIn("[원문 보기]", body, url)
            self.assertIn("링크를 걸지 않았습니다(확인 필요)", body, url)

    def test_the_body_is_bounded(self):
        huge = post_text("제목", LINK).replace("이 글은 시험용 본문입니다.", "가나다라 " * 500, 1)
        body = self.body(entry(kr_title="가" * 5000, en_title="b" * 5000, source="s" * 5000), kr=huge, en=huge)
        self.assertLessEqual(len(body), drafts.BODY_LIMIT)

    def test_the_final_limit_is_a_safety_net_that_cuts_with_an_ellipsis(self):
        """항목마다 줄이므로 기본 한도(9,000자)에는 닿지 않는다. 한도를 낮추면 전체 본문을 줄임표로 자른다(GitHub 한도 65,536자 안쪽을 지키는 마지막 안전망)."""
        with mock.patch.object(drafts, "BODY_LIMIT", 400):
            body = self.body()
        self.assertEqual(len(body), 400)
        self.assertTrue(body.endswith("…"))
        self.assertEqual(drafts.BODY_LIMIT, 9000)

    def test_missing_entry_fields_fall_back_to_the_post_front_matter(self):
        body = drafts.build_pr_body({}, post_text("앞머리 제목", LINK), post_text("Front Title", LINK))
        self.assertIn("- 한국어: 앞머리 제목", body)
        self.assertIn("- English: Front Title", body)
        self.assertIn("분야: 기술·미래", body)
        self.assertIn("Reuters", body)
        self.assertIn("날짜 미상", body)

    def test_the_text_tells_how_to_approve_reject_and_what_happens_to_the_branch(self):
        body = self.body()
        self.assertIn("병합하기 전에는 사이트에 보이지 않습니다", body)
        self.assertIn(f"브랜치는 {drafts.RETENTION_DAYS}일 뒤 자동으로 지워지고", body)
        self.assertIn("같은 슬롯·같은 주제는 다시 만들지 않습니다", body)
        self.assertIn("검사(CI)는 봇이 만든 PR 에서는 자동으로 돌지 않습니다", body)


# ----------------------------------------------------------------------------
# GitHub REST 클라이언트
# ----------------------------------------------------------------------------
class FakeResponse:
    def __init__(self, body):
        self._body = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def http_error(code, body=None):
    payload = json.dumps(body if body is not None else {"message": "x"}).encode("utf-8")
    return urllib.error.HTTPError("https://api.github.com/x", code, "err", {}, io.BytesIO(payload))


class FakeOpener:
    def __init__(self, *responses):
        self.responses, self.requests = list(responses), []

    def __call__(self, request, timeout=None):
        self.requests.append((request, timeout))
        item = self.responses.pop(0)
        if isinstance(item, BaseException):
            raise item
        return FakeResponse(item)


TOKEN = "ghs_" + "T" * 36


class GitHubClientTest(unittest.TestCase):
    def client(self, *responses):
        self.opener = FakeOpener(*responses)
        return drafts.GitHubClient(REPO, TOKEN, opener=self.opener)

    def test_create_pull_request_sends_the_expected_request(self):
        client = self.client({"number": 12, "html_url": "https://evil.example/x"})
        number = client.create_pull_request("제목", "ai/draft/2026-10-28-s9", "main", "본문")
        self.assertEqual(number, 12)
        request, timeout = self.opener.requests[0]
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.full_url, f"https://api.github.com/repos/{REPO}/pulls")
        self.assertEqual(request.headers["Authorization"], f"Bearer {TOKEN}")
        self.assertEqual(request.headers["Accept"], "application/vnd.github+json")
        self.assertEqual(request.headers["X-github-api-version"], "2022-11-28")
        self.assertEqual(json.loads(request.data.decode("utf-8")), {"title": "제목", "head": "ai/draft/2026-10-28-s9", "base": "main", "body": "본문"})
        self.assertEqual(timeout, 20)

    def test_the_pull_url_is_built_from_the_number_not_from_the_api(self):
        self.assertEqual(drafts.pull_url(REPO, 12), f"https://github.com/{REPO}/pull/12")
        with self.assertRaises(ValueError):
            drafts.pull_url(REPO, "12; rm")

    def test_a_response_without_a_number_is_an_error(self):
        for body in ({}, {"number": "12"}, {"number": True}, [], None):
            client = self.client(body if body is not None else b"")
            with self.assertRaises(drafts.GitHubError):
                client.create_pull_request("t", "h", "main", "b")

    def test_http_errors_carry_status_and_a_clean_message(self):
        client = self.client(http_error(403, {"message": "GitHub Actions is not permitted to create or approve pull requests."}))
        with self.assertRaises(drafts.GitHubError) as ctx:
            client.create_pull_request("t", "h", "main", "b")
        self.assertEqual(ctx.exception.status, 403)
        self.assertIn("not permitted", ctx.exception.message)
        self.assertFalse(ctx.exception.retryable)

    def test_error_messages_never_contain_the_token_or_newlines(self):
        body = {"message": f"Bad credentials\n::error::{TOKEN} and {TOKEN[:20]}", "errors": [{"message": f"token {TOKEN}"}]}
        client = self.client(http_error(401, body))
        with self.assertRaises(drafts.GitHubError) as ctx:
            client.create_pull_request("t", "h", "main", "b")
        for text in (ctx.exception.message, str(ctx.exception), repr(ctx.exception)):
            self.assertNotIn(TOKEN, text)
            self.assertNotIn("\n", text)
            self.assertNotIn("::", text)

    def test_network_errors_have_no_status_and_are_retryable(self):
        for exc in (urllib.error.URLError("boom"), TimeoutError("slow"), OSError("reset")):
            client = self.client(exc)
            with self.assertRaises(drafts.GitHubError) as ctx:
                client.create_pull_request("t", "h", "main", "b")
            self.assertIsNone(ctx.exception.status)
            self.assertTrue(ctx.exception.retryable)

    def test_server_errors_are_retryable_and_client_errors_are_not(self):
        self.assertTrue(drafts.GitHubError("x", status=500).retryable)
        self.assertTrue(drafts.GitHubError("x", status=503).retryable)
        for status in (400, 401, 403, 404, 422):
            self.assertFalse(drafts.GitHubError("x", status=status).retryable, status)

    def test_already_exists_is_recognised_only_for_422(self):
        self.assertTrue(drafts.GitHubError("HTTP 422: A pull request already exists for x", status=422).already_exists)
        self.assertFalse(drafts.GitHubError("HTTP 422: Validation Failed", status=422).already_exists)
        self.assertFalse(drafts.GitHubError("already exists", status=409).already_exists)

    def test_a_non_json_body_is_an_error(self):
        client = self.client(b"<html>not json</html>")
        with self.assertRaises(drafts.GitHubError):
            client.create_pull_request("t", "h", "main", "b")

    def test_an_invalid_repository_name_is_refused(self):
        for bad in ("x", "a/../b", "a/b c", ""):
            with self.assertRaises(ValueError):
                drafts.GitHubClient(bad, TOKEN)

    def pr_json(self, number, ref, state="open", repo=REPO, merged_at=None):
        return {"number": number, "state": state, "merged_at": merged_at, "title": f"t{number}", "created_at": "2026-10-28T00:00:00Z",
                "head": {"ref": ref, "repo": {"full_name": repo}}}

    def test_list_keeps_only_this_repos_draft_branches(self):
        items = [self.pr_json(1, "ai/draft/2026-10-28-s9"), self.pr_json(2, "ai/claude/other"), self.pr_json(3, "ai/draft/2026-10-28-s18", repo="fork/chanceblog"),
                 self.pr_json(4, "ai/draft/2026-10-27-s18", state="closed", merged_at="2026-10-27T10:00:00Z"), "junk", {"head": None}]
        client = self.client(items)
        found = client.list_draft_pull_requests()
        self.assertEqual([(p["number"], p["state"], p["merged"]) for p in found], [(1, "open", False), (4, "closed", True)])
        request, _timeout = self.opener.requests[0]
        self.assertIn("state=all", request.full_url)
        self.assertIn("per_page=100", request.full_url)

    def test_list_pages_until_a_short_page(self):
        page1 = [self.pr_json(n, f"ai/draft/2026-10-{10 + n % 15:02d}-s9") for n in range(100)]
        client = self.client(page1, [self.pr_json(500, "ai/draft/2026-10-28-s18")])
        found = client.list_draft_pull_requests()
        self.assertEqual(len(found), 101)
        self.assertTrue(found.complete)                                   # 짧은 쪽을 만났다: 더 오래된 PR 은 없다
        self.assertEqual(len(self.opener.requests), 2)
        self.assertIn("page=2", self.opener.requests[1][0].full_url)

    def test_list_stops_at_max_pages(self):
        full = [self.pr_json(n, "ai/draft/2026-10-28-s9") for n in range(100)]
        client = self.client(full, full, full, full)
        found = client.list_draft_pull_requests(max_pages=2)
        self.assertEqual(len(self.opener.requests), 2)
        self.assertFalse(found.complete)                                  # 가득 찬 쪽만 만났다: 더 오래된 PR 이 목록 밖에 있을 수 있다

    def test_a_listing_filled_with_other_prs_is_also_incomplete(self):
        """목록이 가득 찬 것은 초안 PR 의 수가 아니라 읽은 쪽의 수로 판단한다(저장소의 다른 PR 이 섞여 있어도 잘림을 알아본다)."""
        other = [self.pr_json(n, "ai/claude/other") for n in range(100)]
        client = self.client(other, other, other)
        found = client.list_draft_pull_requests()
        self.assertEqual((len(found), found.complete, len(self.opener.requests)), (0, False, 3))

    def test_list_rejects_a_non_list_response(self):
        with self.assertRaises(drafts.GitHubError):
            self.client({"message": "x"}).list_draft_pull_requests()

    def test_find_pull_request_matches_the_exact_head(self):
        client = self.client([self.pr_json(7, "ai/draft/2026-10-28-s9-extra"), self.pr_json(8, "ai/draft/2026-10-28-s9")])
        found = client.find_pull_request("ai/draft/2026-10-28-s9")
        self.assertEqual(found["number"], 8)
        self.assertIn("head=shine88pc%3Aai%2Fdraft%2F2026-10-28-s9", self.opener.requests[0][0].full_url)
        self.assertIsNone(self.client([]).find_pull_request("ai/draft/x"))

    def test_ensure_label_tolerates_an_existing_label_only(self):
        self.client({"name": "초안"}).ensure_label("초안", "d4c5f9", "d")
        client = self.client(http_error(422, {"message": "Validation Failed", "errors": [{"code": "already_exists"}]}))
        client.ensure_label("초안", "d4c5f9", "d")                     # 이미 있음: 조용히 넘어간다
        with self.assertRaises(drafts.GitHubError):
            self.client(http_error(403)).ensure_label("초안", "d4c5f9", "d")

    def test_add_labels_posts_to_the_issue_endpoint(self):
        client = self.client([{"name": "초안"}])
        client.add_labels(12, ["초안", "채널:Chance"])
        request, _timeout = self.opener.requests[0]
        self.assertTrue(request.full_url.endswith(f"/repos/{REPO}/issues/12/labels"))
        self.assertEqual(json.loads(request.data.decode("utf-8")), {"labels": ["초안", "채널:Chance"]})

    def test_the_label_set_is_the_documented_one(self):
        self.assertEqual([name for name, _c, _d in drafts.LABELS], ["초안", "채널:Chance"])
        self.assertEqual((drafts.LABEL_DRAFT, drafts.LABEL_CHANNEL), ("초안", "채널:Chance"))
        for _name, color, description in drafts.LABELS:
            self.assertRegex(color, r"^[0-9a-f]{6}$")
            self.assertTrue(description)


class RetryTest(unittest.TestCase):
    def run_retry(self, errors, attempts=3):
        sleeps, calls = [], []

        def call():
            calls.append(1)
            error = errors.pop(0)
            if error is not None:
                raise error
            return "ok"
        try:
            return drafts.retry(call, attempts=attempts, sleep=sleeps.append), calls, sleeps
        except drafts.GitHubError as exc:
            return exc, calls, sleeps

    def test_server_errors_are_retried_with_growing_waits(self):
        value, calls, sleeps = self.run_retry([drafts.GitHubError("x", 500), drafts.GitHubError("x", 502), None])
        self.assertEqual((value, len(calls), sleeps), ("ok", 3, [2, 5]))

    def test_network_errors_are_retried(self):
        value, calls, _ = self.run_retry([drafts.GitHubError("net"), None])
        self.assertEqual((value, len(calls)), ("ok", 2))

    def test_client_errors_are_not_retried(self):
        for status in (401, 403, 404, 422):
            value, calls, sleeps = self.run_retry([drafts.GitHubError("x", status), None])
            self.assertIsInstance(value, drafts.GitHubError)
            self.assertEqual((len(calls), sleeps), (1, []), status)

    def test_gives_up_after_the_last_attempt_and_raises_the_last_error(self):
        value, calls, sleeps = self.run_retry([drafts.GitHubError("a", 500), drafts.GitHubError("b", 500), drafts.GitHubError("c", 500)])
        self.assertEqual((value.message, len(calls), len(sleeps)), ("c", 3, 2))

    def test_a_single_attempt_never_sleeps(self):
        value, calls, sleeps = self.run_retry([drafts.GitHubError("a", 500)], attempts=1)
        self.assertEqual((len(calls), sleeps), (1, []))
        self.assertIsInstance(value, drafts.GitHubError)


if __name__ == "__main__":
    unittest.main()
