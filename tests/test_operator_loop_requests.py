"""운영자 요청함 — AI 의 요청 파일을 텔레그램으로 알리는 쪽(python -m pipeline.operator_loop requests) 시험.

요청 파일 파서(경계·악의적 앞머리·길이·슬러그·id 불일치) · 새 요청 파일 고르기(BEFORE 0·수정만 된 파일·merge·rebase·다른 브랜치에 있던 파일, 가짜 git 과 진짜 git) ·
메시지 모양(소독·HTML 이스케이프·버튼 주소 허용 목록·경로 인코딩) · 명령 줄(시크릿 없음 건너뜀·3통 상한·실패 격리·토큰 비노출).
텔레그램은 가짜 HTTP(FakeNet)이고 토큰·채팅 ID 는 런타임에 조합한 가짜 값이다. 실제 GitHub·텔레그램 호출은 없다.
"""
import contextlib
import io
import shutil
import subprocess
import tempfile
import unittest
import urllib.parse
from pathlib import Path

import _bootstrap
import notify_helpers as nh
import operator_loop_helpers as oh
from notify_helpers import CHAT, TOKEN, FakeNet, http_error, leaks
from operator_loop_helpers import SHA_A, SHA_B, SHA_C, ZERO, RequestGit, request_text, requests_env
from pipeline import notify
from pipeline import operator_loop as ol

ROOT = _bootstrap.ROOT
GOOD_NAME = "R-001_merge-pr57.md"
FOLDER = "%EC%9D%B8%EC%88%98%EC%9D%B8%EA%B3%84/%EC%9A%94%EC%B2%AD%ED%95%A8"
GUIDE = "%EC%9D%B8%EC%88%98%EC%9D%B8%EA%B3%84/%EC%9A%B4%EC%98%81%EC%9E%90_%EC%9A%94%EC%B2%AD%ED%95%A8_%EC%82%AC%EC%9A%A9%EB%B2%95.md"
BLOB = "https://github.com/shine88pc/chanceblog/blob/"


class ParseRequestTest(unittest.TestCase):
    def test_the_default_root_is_the_repository_root_and_the_folder_is_the_one_the_docs_name(self):
        self.assertEqual(ol.ROOT, ROOT)
        self.assertEqual((ol.REQUEST_DIR, ol.GUIDE_PATH), ("인수인계/요청함", "인수인계/운영자_요청함_사용법.md"))

    def parse(self, text, name=GOOD_NAME, strict=False):
        return ol.parse_request(name, text, strict=strict)

    def code(self, text, name=GOOD_NAME, strict=False):
        with self.assertRaises(ol.RequestError) as caught:
            self.parse(text, name, strict)
        return caught.exception.code

    def test_a_full_request_file_is_read_field_by_field(self):
        request = self.parse(request_text(kind="decision", title="두 가지 중 고르기", summary="A 와 B 중 하나를 골라 주세요", urgency="급함", pr="57", created="2026-10-28"))
        self.assertEqual(request, ol.Request("R-001", "decision", "두 가지 중 고르기", "A 와 B 중 하나를 골라 주세요", "급함", 57, "2026-10-28", GOOD_NAME))

    def test_optional_fields_default_and_the_body_is_not_read(self):
        request = self.parse(request_text(body="### 아무 말\nid: R-999\nkind: info\n"))
        self.assertEqual((request.urgency, request.pr, request.created), ("보통", None, ""))
        self.assertEqual((request.id, request.kind), ("R-001", "merge"))              # 본문 속 `key: value` 는 앞머리가 아니다

    def test_every_kind_is_accepted_and_others_are_not(self):
        for kind in ("merge", "run", "confirm", "decision", "info"):
            self.assertEqual(self.parse(request_text(kind=kind)).kind, kind)
        for kind in ("Merge", "병합", "", "deploy", "merge,run", "merge run"):
            self.assertEqual(self.code(request_text(kind=kind)), "bad_kind", repr(kind))
        self.assertEqual(self.parse(request_text(kind="merge  ")).kind, "merge")                    # 값의 앞뒤 공백은 자른다

    def test_each_required_key_is_required(self):
        for key in ("id", "kind", "title", "summary"):
            text = request_text(**{key: None})
            self.assertEqual(self.code(text), f"missing_{key}", key)

    def test_empty_or_invisible_only_title_and_summary_are_missing(self):
        for key in ("title", "summary"):
            for value in ("", "   ", chr(0x200B), chr(0x200B) + chr(0x2060) + chr(0xFEFF), chr(0x202E)):
                self.assertEqual(self.code(request_text(**{key: value})), f"missing_{key}", (key, value))

    def test_the_id_must_have_the_request_number_shape_and_match_the_file_name(self):
        for bad in ("R-1", "R-0001", "r-001", "R_001", "R-00a", "001", "R-001x", ""):
            self.assertEqual(self.code(request_text(id=bad)), "bad_id", bad)
        self.assertEqual(self.code(request_text(id="R-002")), "id_mismatch")

    def test_file_names_must_be_the_request_number_and_an_ascii_slug(self):
        good = ["R-001_a.md", "R-123_merge-pr57.md", "R-010_x1-y2-z3.md", "R-999_" + "a" * ol.SLUG_MAX + ".md"]
        for name in good:
            number = name[:5]
            self.assertEqual(self.parse(request_text(id=number), name).name, name)
        bad = ["r-001_a.md", "R-1_a.md", "R-0001_a.md", "R-001_A.md", "R-001_한글.md", "R-001_.md", "R-001_a--b.md", "R-001_a_b.md", "R-001_-a.md", "R-001_a-.md",
               "R-001-a.md", "R-001_a.txt", "R-001_a.md.md", "R-001 a.md", "x/R-001_a.md", "R-001_" + "a" * (ol.SLUG_MAX + 1) + ".md", "R-001_a\n.md", "README.md", ""]
        for name in bad:
            self.assertEqual(self.code(request_text(), name), "bad_name", repr(name))

    def test_the_front_matter_must_open_on_the_first_line_and_close_within_the_limit(self):
        self.assertEqual(self.code("id: R-001\n---\n"), "no_front_matter")
        self.assertEqual(self.code("\n" + request_text()), "no_front_matter")
        self.assertEqual(self.code("title: x\n" + request_text()), "no_front_matter")
        self.assertEqual(self.code("---\nid: R-001\nkind: merge\ntitle: t\nsummary: s\n"), "unclosed")
        self.assertEqual(self.code(""), "no_front_matter")
        padding = "\n".join("# comment" for _ in range(ol.MAX_FRONT_LINES))
        late = "---\n" + padding + "\nid: R-001\nkind: merge\ntitle: t\nsummary: s\n---\n"
        self.assertEqual(self.code(late), "unclosed")                                  # 닫는 줄이 첫 40줄 밖이면 읽지 않는다
        edge = "---\n" + "\n".join(["id: R-001", "kind: merge", "title: t", "summary: s"] + ["# c"] * (ol.MAX_FRONT_LINES - 5)) + "\n---\n"
        self.assertEqual(self.parse(edge).id, "R-001")                                # 닫는 줄이 40번째 줄이면 된다

    def test_a_byte_order_mark_and_windows_line_ends_are_accepted(self):
        text = request_text(title="제목")
        self.assertEqual(self.parse(chr(0xFEFF) + text).title, "제목")
        self.assertEqual(self.parse(text.replace("\n", "\r\n")).title, "제목")
        self.assertEqual(self.parse("---   \n" + text.split("\n", 1)[1].replace("\n---\n", "\n---  \n")).id, "R-001")     # 구분선 뒤 공백은 봐준다

    def test_lines_that_are_not_key_value_pairs_are_rejected_strictly(self):
        for bad in ("just words", "  title: indented", "\ttitle: tab", "title", "- list item", "title = x", ": nokey", "1abc: x"):
            self.assertEqual(self.code(request_text(extra=bad)), "bad_line", repr(bad))

    def test_comments_and_blank_lines_in_the_front_matter_are_skipped(self):
        self.assertEqual(self.parse(request_text(extra="# 메모\n\n   \n# 또 메모")).id, "R-001")

    def test_a_block_scalar_is_not_read_so_a_multi_line_summary_is_an_error(self):
        text = "---\nid: R-001\nkind: merge\ntitle: t\nsummary: |\n  첫 줄\n  둘째 줄\n---\n"
        self.assertEqual(self.code(text), "bad_line")

    def test_a_key_given_twice_is_rejected_even_when_the_values_agree(self):
        self.assertEqual(self.code(request_text(extra="title: 두 번째")), "duplicate_key")
        self.assertEqual(self.code(request_text(extra="id: R-001")), "duplicate_key")

    def test_unknown_keys_are_ignored_at_run_time_but_rejected_by_the_validator(self):
        text = request_text(extra="owner: shine88pc\nx-extra: 1")
        self.assertEqual(self.parse(text).id, "R-001")
        self.assertEqual(self.code(text, strict=True), "unknown_key")

    def test_a_forged_second_key_inside_a_value_cannot_split_the_line(self):
        """U+2028·U+0085 같은 줄 바꿈 문자나 한 줄 안의 가짜 `summary:` 가 키를 위조하지 못한다(줄은 `\\n` 으로만 나눈다)."""
        text = request_text(title="진짜 제목" + chr(0x2028) + "summary: 위조", summary="진짜 요약")
        request = self.parse(text)
        self.assertEqual(request.summary, "진짜 요약")
        self.assertIn("위조", request.title)
        also = request_text(title="제목" + chr(0x85) + "kind: info")
        self.assertEqual(self.parse(also).kind, "merge")

    def test_quotes_around_a_value_are_removed_but_nothing_is_unescaped(self):
        self.assertEqual(self.parse(request_text(title='"따옴표 제목"')).title, "따옴표 제목")
        self.assertEqual(self.parse(request_text(title="'작은 따옴표'")).title, "작은 따옴표")
        self.assertEqual(self.parse(request_text(title='"한쪽만')).title, '"한쪽만')
        self.assertEqual(self.parse(request_text(title='"a\\nb"')).title, 'a\\nb')              # 이스케이프는 풀지 않는다
        self.assertEqual(self.parse(request_text(title="콜론: 이 들어간 제목")).title, "콜론: 이 들어간 제목")

    def test_urgency_pr_and_created_are_checked(self):
        for urgency in ("보통", "급함"):
            self.assertEqual(self.parse(request_text(urgency=urgency)).urgency, urgency)
        for urgency in ("긴급", "high", ""):
            self.assertEqual(self.code(request_text(urgency=urgency)), "bad_urgency", repr(urgency))
        self.assertEqual(self.parse(request_text(pr="1")).pr, 1)
        self.assertEqual(self.parse(request_text(pr="9999999")).pr, 9999999)
        for pr in ("0", "-1", "abc", "1.5", "10000000", "01", "#57", ""):
            self.assertEqual(self.code(request_text(pr=pr)), "bad_pr", repr(pr))
        for created in ("2026-13-40", "yesterday", "2026-1-1", "20261028", "2026-02-30"):
            self.assertEqual(self.code(request_text(created=created)), "bad_created", created)
        self.assertEqual(self.parse(request_text(created="2026-02-28")).created, "2026-02-28")

    def test_lengths_are_enforced_only_in_strict_mode_and_reading_is_bounded_in_both(self):
        long_title, long_summary = "가" * (ol.TITLE_MAX + 1), "나" * (ol.SUMMARY_MAX + 1)
        self.assertEqual(self.parse(request_text(title=long_title, summary=long_summary)).title, long_title)          # 런타임은 받고 보낼 때 줄인다
        self.assertEqual(self.code(request_text(title=long_title), strict=True), "long_title")
        self.assertEqual(self.code(request_text(summary=long_summary), strict=True), "long_summary")
        self.assertEqual(self.parse(request_text(title="가" * ol.TITLE_MAX, summary="나" * ol.SUMMARY_MAX), strict=True).id, "R-001")
        self.assertEqual(self.code(request_text(title="x" * (ol.MAX_LINE_CHARS + 1))), "long_line")
        self.assertEqual(self.code(request_text(title="x" * (ol.MAX_LINE_CHARS + 1)), strict=True), "long_line")
        huge = "---\nid: R-001\n" + "x" * 5_000_000 + "\n---\n"
        self.assertEqual(self.code(huge), "long_line")                                  # 수 MB 한 줄도 바로 거절한다

    def test_hostile_values_are_accepted_as_data_and_defanged_when_sent(self):
        """파서는 값을 믿지 않고 그대로 두며(소독은 보낼 때), 워크플로 명령·HTML·멘션·비밀 모양이 든 값도 앞머리를 깨뜨리지 못한다."""
        text = request_text(title="<script>alert(1)</script>", summary="::set-output name=x::1 @owner #12 $(rm -rf /) `id` https://evil.example/x")
        request = self.parse(text)
        self.assertIn("<script>", request.title)
        message = notify.format_ai_request(request.id, request.kind, request.title, request.summary)
        for needle in ("<script>", "::", "https://", "@"):
            self.assertNotIn(needle, message.replace("<b>", "").replace("</b>", ""), needle)


class SelectionTest(unittest.TestCase):
    def names(self, git, before=SHA_B, after=SHA_A, default="main", ref="ai/claude/work"):
        return ol.new_request_names("ROOT", before, after, default, ref, runner=git)

    def test_a_normal_push_uses_the_before_commit_and_excludes_other_branches(self):
        git = RequestGit(tree=oh.paths("R-001_a.md"))
        self.assertEqual(self.names(git), ["R-001_a.md"])
        self.assertEqual([args[1] for args, _ in git.calls], ["diff", "log"])                      # 얕은 복제 확인·merge-base 는 BEFORE 가 0 일 때만
        diff, log = git.names("diff")[0], git.names("log")[0]
        self.assertEqual(diff, ["git", "diff", "--name-only", "--diff-filter=A", "-M", "-z", SHA_B, SHA_A, "--", ol.REQUEST_DIR + "/"])
        self.assertEqual(log, ["git", "log", "--diff-filter=A", "--name-only", "-M", "-z", "--format=", SHA_A, "^" + SHA_B,
                               "--not", "--exclude=origin/ai/claude/work", "--remotes=origin", "--", ol.REQUEST_DIR + "/"])

    def test_the_first_push_of_a_new_branch_uses_the_merge_base_with_the_default_branch(self):
        git = RequestGit(tree=oh.paths("R-001_a.md"), merge_base=SHA_C)
        self.assertEqual(self.names(git, before=ZERO), ["R-001_a.md"])
        self.assertEqual([args[1] for args, _ in git.calls], ["rev-parse", "merge-base", "diff", "log"])
        self.assertEqual(git.names("rev-parse")[0], ["git", "rev-parse", "--is-shallow-repository"])
        self.assertEqual(git.names("merge-base")[0], ["git", "merge-base", "origin/main", SHA_A])
        self.assertEqual(git.names("diff")[0][6:8], [SHA_C, SHA_A])                                  # 기준 = merge-base
        self.assertNotIn("^" + SHA_C, git.names("log")[0])
        self.assertNotIn("^" + ZERO, git.names("log")[0])

    def test_the_default_branch_name_is_used_for_the_merge_base(self):
        git = RequestGit(tree=oh.paths("R-001_a.md"))
        self.names(git, before=ZERO, default="develop")
        self.assertEqual(git.names("merge-base")[0][2], "origin/develop")

    def test_a_shallow_clone_cannot_tell_where_a_new_branch_starts_so_nothing_is_sent(self):
        git = RequestGit(tree=oh.paths("R-001_a.md"), shallow=True)
        with self.assertRaises(notify.GitError):
            self.names(git, before=ZERO)
        self.assertEqual([args[1] for args, _ in git.calls], ["rev-parse"])                          # diff·log 는 부르지도 않는다

    def test_anything_but_a_clear_false_from_the_shallow_check_is_refused(self):
        for output in ("", "maybe", "TRUE", "true"):
            def runner(args, output=output, **kwargs):
                return subprocess.CompletedProcess(args, 0, stdout=output.encode(), stderr=b"")
            with self.assertRaises(notify.GitError, msg=output):
                ol.new_request_names("ROOT", ZERO, SHA_A, "main", "ai/claude/work", runner=runner)

    def test_only_files_in_both_the_tree_difference_and_the_commit_difference_count(self):
        git = RequestGit(tree=oh.paths("R-001_a.md", "R-002_b.md"), log=oh.paths("R-002_b.md", "R-003_c.md"))
        self.assertEqual(self.names(git), ["R-002_b.md"])
        self.assertEqual(self.names(RequestGit(tree=oh.paths("R-001_a.md"), log=[])), [])            # main·다른 브랜치가 가져온 파일(트리 차이에만 있음)
        self.assertEqual(self.names(RequestGit(tree=[], log=oh.paths("R-001_a.md"))), [])            # 리베이스로 복사된 파일(BEFORE 트리에 이미 있음)

    def test_the_selection_also_tells_which_files_other_branches_already_had(self):
        """트리 차이에는 있지만 커밋 차이로 걸러진 파일 = '다른 브랜치에도 있어 알리지 않는' 파일 — 로그에 남기려고 따로 돌려준다(독립 검증 N-1)."""
        def select(tree, log):
            return ol.request_name_selection("ROOT", SHA_B, SHA_A, "main", "ai/claude/work", runner=RequestGit(tree=tree, log=log))
        self.assertEqual(select(oh.paths("R-001_a.md", "R-002_b.md", "README.md"), oh.paths("R-002_b.md")), (["R-002_b.md"], ["R-001_a.md"]))
        self.assertEqual(select(oh.paths("R-001_a.md"), []), ([], ["R-001_a.md"]))
        self.assertEqual(select([], oh.paths("R-001_a.md")), ([], []))                                  # 리베이스: 걸러진 것이 아니라 BEFORE 트리에 이미 있던 것
        self.assertEqual(select(oh.paths("R-001_a.md", "R-002_b.md"), oh.paths("R-001_a.md", "R-002_b.md")), (["R-001_a.md", "R-002_b.md"], []))
        self.assertEqual(self.names(RequestGit(tree=oh.paths("R-001_a.md", "R-002_b.md"), log=oh.paths("R-002_b.md"))), ["R-002_b.md"])      # 새 파일 목록은 예전과 같다
        many = oh.paths(*[f"R-{index:03d}_x.md" for index in range(1, ol.MAX_CANDIDATES + 15)])
        self.assertEqual(len(select(many, [])[1]), ol.MAX_CANDIDATES)

    def test_the_skipped_log_line_names_only_request_numbers_sorted_and_capped(self):
        self.assertEqual(ol.skipped_line(["R-001_a.md"]), "AI 요청 알림: 다른 브랜치에도 있어 알리지 않은 요청 파일: R-001")
        self.assertEqual(ol.skipped_line(["R-010_z.md", "R-002_b.md", "R-002_c.md"]), "AI 요청 알림: 다른 브랜치에도 있어 알리지 않은 요청 파일: R-002, R-010")
        line = ol.skipped_line([f"R-{index:03d}_x.md" for index in range(1, ol.MAX_SKIPPED_IDS + 4)])
        self.assertTrue(line.endswith(", ".join(f"R-{index:03d}" for index in range(1, ol.MAX_SKIPPED_IDS + 1)) + " 외 3건"), line)
        twelve = ol.skipped_line([f"R-{index:03d}_x.md" for index in range(1, 13)])                      # 한도 값 자체도 글자 그대로 고정한다(번호 10개까지, 나머지는 '외 N건')
        self.assertEqual(twelve, "AI 요청 알림: 다른 브랜치에도 있어 알리지 않은 요청 파일: R-001, R-002, R-003, R-004, R-005, R-006, R-007, R-008, R-009, R-010 외 2건")
        self.assertNotIn("::", line)
        self.assertEqual(len(line.splitlines()), 1)

    def test_only_exact_request_file_paths_in_the_folder_are_kept_and_the_result_is_sorted(self):
        listed = oh.paths("R-010_z.md", "R-002_b.md", "README.md", "R-003_Bad.md", "r-004_x.md", "sub/R-005_x.md", "R-006_x.txt") + [
            "R-007_x.md", "인수인계/R-008_x.md", "인수인계/요청함/R-009_x.md/extra", "other/인수인계/요청함/R-011_x.md", "", "인수인계/요청함"]
        self.assertEqual(self.names(RequestGit(tree=listed)), ["R-002_b.md", "R-010_z.md"])

    def test_the_candidates_are_capped(self):
        many = [f"R-{index:03d}_x.md" for index in range(1, ol.MAX_CANDIDATES + 15)]
        found = self.names(RequestGit(tree=oh.paths(*many)))
        self.assertEqual(len(found), ol.MAX_CANDIDATES)
        self.assertEqual(found, sorted(many)[:ol.MAX_CANDIDATES])

    def test_invalid_commit_numbers_and_branch_names_are_refused_without_calling_git(self):
        for before, after in (("", SHA_A), ("xyz", SHA_A), ("-h", SHA_A), (SHA_B, ""), (SHA_B, "main"), (SHA_B, SHA_A.upper()), (SHA_B, ZERO), (SHA_B, "a" * 39), (SHA_B, "--output=x"),
                              (None, SHA_A), (SHA_B, None), ("0" * 39, SHA_A)):
            git = RequestGit(tree=oh.paths("R-001_a.md"))
            with self.assertRaises(notify.GitError, msg=(before, after)):
                self.names(git, before=before, after=after)
            self.assertEqual(git.calls, [], (before, after))
        for default, ref in (("--upload-pack=x", "ai/claude/a"), ("main", "main"), ("main", "feature/x"), ("main", "ai/claude/../x"), ("main", "ai/claude/a b"),
                             ("main", "ai/claude/.hidden"), ("main", "ai/claude/x.lock"), ("m*", "ai/claude/a"), ("main", "ai/claude/a*"), ("", "ai/claude/a"), ("main", "ai/claude/" + "x" * 120),
                             ("main", "ai/claude/a;rm"), ("main", "ai/claude/$HOME"), ("main", "ai/claude/a..b"), ("a..b", "ai/claude/a"), ("main", "ai/claude/a/"),
                             ("main", "ai/claude//a")):
            git = RequestGit(tree=oh.paths("R-001_a.md"))
            with self.assertRaises(notify.GitError, msg=(default, ref)):
                self.names(git, default=default, ref=ref)
            self.assertEqual(git.calls, [], (default, ref))

    def test_valid_branch_accepts_normal_names_only(self):
        for name in ("main", "ai/claude/a", "ai/claude/operator-loop", "ai/claude/x.y_z-1", "release/1.2"):
            self.assertTrue(ol.valid_branch(name), name)
        self.assertFalse(ol.valid_branch("-main"))
        self.assertFalse(ol.valid_branch("a..b"))                       # 점 둘은 git 이름 규칙 위반 — 점으로 시작하는 조각 검사로는 못 잡는다
        self.assertFalse(ol.valid_branch("a/b.lock"))
        self.assertFalse(ol.valid_branch("a/.b"))
        self.assertFalse(ol.valid_branch("x" * 121))
        self.assertTrue(ol.valid_branch("x" * 120))
        self.assertFalse(ol.valid_branch("main", "ai/claude/"))
        self.assertFalse(ol.valid_branch(5))
        self.assertTrue(ol.valid_branch("ai/claude/a", "ai/claude/"))

    def test_a_failing_git_command_stops_the_search_instead_of_sending_everything(self):
        for broken in ("diff", "log"):
            git = RequestGit(tree=oh.paths("R-001_a.md"), broken={broken})
            with self.assertRaises(notify.GitError, msg=broken):
                self.names(git)
        for broken in ("rev-parse", "merge-base", "diff", "log"):
            git = RequestGit(tree=oh.paths("R-001_a.md"), broken={broken})
            with self.assertRaises(notify.GitError, msg=broken):
                self.names(git, before=ZERO)

    def test_a_merge_base_that_is_not_a_commit_number_is_refused(self):
        git = RequestGit(tree=oh.paths("R-001_a.md"), merge_base="not-a-sha")
        with self.assertRaises(notify.GitError):
            self.names(git, before=ZERO)
        self.assertEqual([args[1] for args, _ in git.calls], ["rev-parse", "merge-base"])

    def test_sha256_object_names_are_accepted_too(self):
        wide_a, wide_b = "a" * 64, "b" * 64
        git = RequestGit(tree=oh.paths("R-001_a.md"))
        self.assertEqual(ol.new_request_names("ROOT", wide_b, wide_a, "main", "ai/claude/a", runner=git), ["R-001_a.md"])
        self.assertEqual(ol.new_request_names("ROOT", "0" * 64, wide_a, "main", "ai/claude/a", runner=RequestGit(tree=oh.paths("R-001_a.md"), merge_base="c" * 64)), ["R-001_a.md"])


class RealGitSelectionTest(unittest.TestCase):
    """진짜 git 으로 한 새 요청 파일 고르기 — 가짜 git 이 흉내 낸 출력 모양(`-z`·한글 경로·`--not --exclude --remotes`)이 실제 git 과 같은지, 그리고 실제 작업 흐름
    (이어 push·새 브랜치·main 합치기·리베이스·다른 브랜치 합치기)에서 같은 요청을 다시 알리지 않는지.

    Actions 의 알림 단계는 push 직후, 그때까지 push 된 브랜치만 있는 상태에서 돈다. 그래서 저장소를 한 번 만들면서 **각 push 직후에** 찾기를 돌려 결과를 모아 두고
    (`cls.found`), 시험은 그 결과를 본다(나중에 만든 브랜치가 앞 커밋을 가져가도 그 시점의 결과가 바뀌지 않는다). 원격 추적 참조는 `git update-ref` 로 checkout 이 fetch 한 상태를 흉내 낸다."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.mkdtemp(prefix="oltest_")
        cls.root = Path(cls._tmp) / "repo"
        cls.root.mkdir()
        cls.refs, cls.found, cls.skipped, cls.cli_runs = {}, {}, {}, {}
        git = cls.git
        git("init", "-q", "-b", "main")
        cls.commit({"README.md": "x\n"}, "base")
        cls.push("main")
        git("switch", "-q", "-c", "ai/claude/a")
        cls.refs["a1"] = cls.commit({oh.DIR + "README.md": "folder readme\n"}, "a1")
        cls.push("ai/claude/a")
        cls.search("readme_first_push", ZERO, "a1", "ai/claude/a")
        cls.refs["a2"] = cls.commit({oh.DIR + "R-001_x.md": request_text()}, "a2")
        cls.push("ai/claude/a")
        cls.search("second_push_adds", "a1", "a2", "ai/claude/a")
        cls.refs["a3"] = cls.commit({oh.DIR + "R-001_x.md": request_text(body="수정\n")}, "a3")
        cls.push("ai/claude/a")
        cls.search("modify_only", "a2", "a3", "ai/claude/a")
        git("switch", "-q", "main")
        git("switch", "-q", "-c", "ai/claude/first")
        cls.commit({oh.DIR + "R-030_first.md": request_text(id="R-030"), "code.txt": "1\n"}, "f1")
        cls.refs["f2"] = cls.commit({oh.DIR + "R-031_second.md": request_text(id="R-031")}, "f2")
        cls.push("ai/claude/first")
        cls.search("first_push_two_files", ZERO, "f2", "ai/claude/first")
        git("switch", "-q", "ai/claude/a")
        git("switch", "-q", "-c", "ai/claude/b")
        cls.refs["b1"] = cls.commit({oh.DIR + "R-002_y.md": request_text(id="R-002")}, "b1")
        cls.push("ai/claude/b")
        cls.search("cut_from_announced", ZERO, "b1", "ai/claude/b")
        git("switch", "-q", "main")
        cls.commit({oh.DIR + "R-005_z.md": request_text(id="R-005")}, "m1")
        cls.push("main")
        git("switch", "-q", "ai/claude/a")
        git("merge", "-q", "--no-ff", "-m", "merge main", "main")
        cls.refs["a4"] = git("rev-parse", "HEAD")
        cls.push("ai/claude/a")
        cls.search("merge_main_in", "a3", "a4", "ai/claude/a")
        git("switch", "-q", "main")
        git("switch", "-q", "-c", "ai/claude/c")
        cls.refs["c1"] = cls.commit({oh.DIR + "R-010_c.md": request_text(id="R-010")}, "c1")
        cls.push("ai/claude/c")
        git("switch", "-q", "main")
        cls.commit({"other.txt": "o\n"}, "m2")
        cls.push("main")
        git("switch", "-q", "ai/claude/c")
        git("rebase", "-q", "main")
        cls.refs["c1b"] = git("rev-parse", "HEAD")
        cls.push("ai/claude/c")
        cls.search("rebase_force_push", "c1", "c1b", "ai/claude/c")
        git("switch", "-q", "main")
        git("switch", "-q", "-c", "ai/claude/d")
        git("merge", "-q", "--no-ff", "-m", "merge a", "ai/claude/a")
        cls.refs["d1"] = cls.commit({oh.DIR + "R-020_d.md": request_text(id="R-020")}, "d1")
        cls.push("ai/claude/d")
        cls.search("integration_first_push", ZERO, "d1", "ai/claude/d")
        cls.refs["d2"] = cls.commit({oh.DIR + "R-021_e.md": "x\n", oh.DIR + "R-022_f.md": "x\n", oh.DIR + "sub/R-023_g.md": "x\n", "R-024_h.md": "x\n",
                                     oh.DIR + "r-025_i.md": "x\n"}, "d2")
        cls.push("ai/claude/d")
        cls.search("odd_names", "d1", "d2", "ai/claude/d")
        # 요청 파일을 가진 커밋이 든 두 브랜치를 한꺼번에 push 한 경우(독립 검증 N-1): 둘 다 '다른 브랜치에도 있다'고 보고 아무도 알리지 않는다 — 대신 로그에 이유가 남는다
        git("switch", "-q", "main")
        git("switch", "-q", "-c", "ai/claude/p")
        cls.refs["p1"] = cls.commit({oh.DIR + "R-050_p.md": request_text(id="R-050")}, "p1")
        git("switch", "-q", "-c", "ai/claude/q")
        cls.refs["q1"] = cls.commit({"q.txt": "q\n"}, "q1")
        cls.push("ai/claude/p")
        cls.push("ai/claude/q")                                                                     # git push origin p q 와 같다
        cls.search("together_p", ZERO, "p1", "ai/claude/p")
        cls.run_cli_now("together_p", ZERO, "p1", "ai/claude/p")
        cls.search("together_q", ZERO, "q1", "ai/claude/q")
        # 시간 차를 두고 push 하면(r 을 먼저 올려 알림 실행이 끝난 뒤 s) 첫 브랜치는 알려지고 둘째는 다시 알리지 않는다
        git("switch", "-q", "main")
        git("switch", "-q", "-c", "ai/claude/r")
        cls.refs["r1"] = cls.commit({oh.DIR + "R-051_r.md": request_text(id="R-051")}, "r1")
        cls.push("ai/claude/r")
        cls.search("alone_r", ZERO, "r1", "ai/claude/r")
        git("switch", "-q", "-c", "ai/claude/s")
        cls.refs["s1"] = cls.commit({"s.txt": "s\n"}, "s1")
        cls.push("ai/claude/s")
        cls.search("later_s", ZERO, "s1", "ai/claude/s")
        git("switch", "-q", "ai/claude/d")                                                         # 뒤의 시험이 기대는 작업 트리(R-001 파일이 있는 브랜치)로 돌아간다

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._tmp, ignore_errors=True)

    @classmethod
    def git(cls, *args):
        done = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", "-c", "commit.gpgsign=false", "-c", "core.autocrlf=false", *args],
                              cwd=str(cls.root), capture_output=True)
        if done.returncode != 0:
            raise AssertionError(f"git {' '.join(args)}: {done.stderr.decode('utf-8', 'replace')}")
        return done.stdout.decode("utf-8", "replace").strip()

    @classmethod
    def commit(cls, files, message):
        for rel, text in files.items():
            path = cls.root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8", newline="\n")
        cls.git("add", "-A")
        cls.git("commit", "-q", "-m", message)
        return cls.git("rev-parse", "HEAD")

    @classmethod
    def push(cls, branch):
        cls.git("update-ref", f"refs/remotes/origin/{branch}", cls.git("rev-parse", branch))

    @classmethod
    def search(cls, key, before, after, ref):
        """push 직후에 찾기를 돌려 결과(이름 목록 또는 예외)를 모아 둔다. before·after 는 refs 의 키이거나 ZERO."""
        try:
            cls.found[key], cls.skipped[key] = ol.request_name_selection(cls.root, ZERO if before == ZERO else cls.refs[before], cls.refs[after], "main", ref)
        except notify.GitError as exc:
            cls.found[key] = cls.skipped[key] = exc

    @classmethod
    def run_cli_now(cls, key, before, after, ref):
        """같은 시점에 `python -m pipeline.operator_loop requests` 를 진짜 git·가짜 텔레그램으로 돌려 (종료 코드, 로그 줄, 보낸 통 수)를 모아 둔다."""
        env = requests_env(before=ZERO if before == ZERO else cls.refs[before], after=cls.refs[after], ref_name=ref)
        code, lines, net, _ = oh.run_cli("requests", environ=env, root=cls.root)
        cls.cli_runs[key] = (code, lines, net.calls)

    def test_two_branches_pushed_together_with_the_same_new_request_commit_announce_nothing_but_the_log_says_why(self):
        self.assertEqual((self.found["together_p"], self.skipped["together_p"]), ([], ["R-050_p.md"]))
        self.assertEqual((self.found["together_q"], self.skipped["together_q"]), ([], ["R-050_p.md"]))
        self.assertEqual(self.cli_runs["together_p"], (0, [ol.skipped_line(["R-050_p.md"]), ol.REQUESTS_NONE_LINE], 0))

    def test_pushed_one_after_the_other_the_first_branch_announces_and_the_second_is_not_announced_again(self):
        self.assertEqual((self.found["alone_r"], self.skipped["alone_r"]), (["R-051_r.md"], []))
        self.assertEqual((self.found["later_s"], self.skipped["later_s"]), ([], ["R-051_r.md"]))

    def test_the_names_function_and_the_selection_function_agree_on_the_new_files(self):
        for key, before, after, ref in (("second_push_adds", "a1", "a2", "ai/claude/a"), ("first_push_two_files", ZERO, "f2", "ai/claude/first")):
            names = ol.new_request_names(self.root, ZERO if before == ZERO else self.refs[before], self.refs[after], "main", ref)
            self.assertEqual(names, ol.request_name_selection(self.root, ZERO if before == ZERO else self.refs[before], self.refs[after], "main", ref)[0], key)

    def test_a_first_push_with_only_the_folder_readme_finds_nothing(self):
        self.assertEqual(self.found["readme_first_push"], [])

    def test_a_later_push_that_adds_a_request_file_finds_it(self):
        self.assertEqual(self.found["second_push_adds"], ["R-001_x.md"])

    def test_editing_an_existing_request_file_is_not_a_new_request(self):
        self.assertEqual(self.found["modify_only"], [])

    def test_a_first_push_that_already_holds_request_files_finds_all_of_them(self):
        self.assertEqual(self.found["first_push_two_files"], ["R-030_first.md", "R-031_second.md"])

    def test_a_branch_cut_from_an_announced_branch_does_not_announce_its_files_again(self):
        self.assertEqual(self.found["cut_from_announced"], ["R-002_y.md"])                        # R-001 은 이미 알린 브랜치 a 에 있다

    def test_merging_the_default_branch_in_does_not_announce_the_files_it_brought(self):
        self.assertEqual(self.found["merge_main_in"], [])

    def test_the_skipped_list_also_names_files_that_ordinary_pushes_bring_from_other_branches(self):
        """'다른 브랜치에도 있어 알리지 않은 요청 파일' 줄은 동시 push 만이 아니라 main 을 합치거나 이미 알린 브랜치에서 새 브랜치를 만든 평범한 push 에도 남는다(문서가 그렇게 말한다) — 알림은 잃지 않았다."""
        self.assertEqual(self.skipped["merge_main_in"], ["R-005_z.md"])
        self.assertEqual(self.skipped["cut_from_announced"], ["R-001_x.md"])
        self.assertEqual(self.skipped["second_push_adds"], [])                                   # 이어 push 로 더한 새 파일은 걸러지지 않고 알린다
        self.assertEqual(self.skipped["first_push_two_files"], [])

    def test_a_rebase_with_a_forced_push_does_not_announce_the_rebased_files_again(self):
        self.assertEqual(self.found["rebase_force_push"], [])

    def test_an_integration_branch_announces_only_what_no_other_branch_has(self):
        self.assertEqual(self.found["integration_first_push"], ["R-020_d.md"])

    def test_odd_names_and_other_folders_are_ignored_by_real_git_too(self):
        self.assertEqual(self.found["odd_names"], ["R-021_e.md", "R-022_f.md"])

    def test_the_same_push_looked_at_again_later_is_not_lost_when_a_branch_that_has_it_appears(self):
        """주의(문서의 한계): 같은 push 를 나중에 다시 찾으면 그사이 다른 브랜치가 그 커밋을 가져간 경우 빈 결과가 된다 — 찾기는 push 직후에만 의미가 있다(알림 단계가 그 시점에 돈다).
        그래서 이 시험은 '지금 다시 찾으면 빈다'는 사실을 못 박아, 시점이 결과에 들어가는 설계임을 잊지 않게 한다."""
        self.assertEqual(ol.new_request_names(self.root, self.refs["a1"], self.refs["a2"], "main", "ai/claude/a"), [])

    def test_a_before_commit_that_no_longer_exists_stops_the_search(self):
        with self.assertRaises(notify.GitError):
            ol.new_request_names(self.root, "1" * 40, self.refs["d2"], "main", "ai/claude/d")

    def test_a_shallow_clone_of_the_repository_refuses_the_new_branch_case(self):
        shallow = Path(self._tmp) / "shallow"
        subprocess.run(["git", "clone", "-q", "--depth", "1", self.root.as_uri(), str(shallow)], check=True, capture_output=True)
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(shallow), capture_output=True, check=True).stdout.decode().strip()
        with self.assertRaises(notify.GitError):
            ol.new_request_names(shallow, ZERO, head, "main", "ai/claude/d")

    def test_the_request_file_is_read_from_the_commit_not_the_working_tree(self):
        working = self.root / ol.REQUEST_DIR / "R-001_x.md"
        original = working.read_text(encoding="utf-8")
        working.write_text("작업 트리에서만 고친 글\n", encoding="utf-8", newline="\n")
        try:
            text = notify.read_blob(self.root, self.refs["a2"], oh.DIR + "R-001_x.md")                      # 작업 트리의 파일은 읽지 않는다(심볼릭 링크로 밖의 파일을 읽지 않게)
            self.assertIn("id: R-001", text)
            self.assertNotIn("작업 트리에서만", text)
        finally:
            working.write_text(original, encoding="utf-8", newline="\n")
        with self.assertRaises(notify.GitError):
            notify.read_blob(self.root, self.refs["a1"], oh.DIR + "R-001_x.md")                             # 그 커밋에 없는 파일


class MessageTest(unittest.TestCase):
    def fmt(self, **kwargs):
        base = {"request_id": "R-001", "kind": "merge", "title": "PR 병합 부탁", "summary": "아래 PR 을 병합해 주세요."}
        base.update(kwargs)
        return notify.format_ai_request(**base)

    def test_the_header_names_the_request_number_and_the_kind_in_korean(self):
        labels = {"merge": "병합 부탁", "run": "실행 부탁", "confirm": "확인 부탁", "decision": "결정 부탁", "info": "알림"}
        self.assertEqual(notify.REQUEST_KIND_LABELS, labels)
        for kind, label in labels.items():
            first = self.fmt(kind=kind).splitlines()[0]
            self.assertEqual(first, f"{notify.BELL_MARK} <b>AI 요청 R-001 · {label}</b>", kind)

    def test_the_body_is_title_then_summary(self):
        self.assertEqual(self.fmt().splitlines()[1:3], ["PR 병합 부탁", "아래 PR 을 병합해 주세요."])

    def test_an_urgent_request_is_marked_in_the_header_and_a_normal_one_is_not(self):
        self.assertTrue(self.fmt(urgency="급함").splitlines()[0].endswith(f"</b> {notify.SIREN_MARK} 급함"))
        for urgency in ("보통", "", "높음", None):
            self.assertNotIn(notify.SIREN_MARK, self.fmt(urgency=urgency), urgency)

    def test_the_related_pr_number_is_a_line_only_when_there_is_one(self):
        self.assertIn("관련 PR: #57", self.fmt(pr=57).splitlines())
        self.assertNotIn("관련 PR", self.fmt())
        for bad in (0, -3, True, "57", 5.5):
            with self.assertRaises(ValueError, msg=bad):
                self.fmt(pr=bad)

    def test_the_how_to_answer_line_is_only_for_kinds_that_need_an_answer(self):
        for kind in ("confirm", "decision"):
            self.assertIn("답하는 법: 아래 [답하기] → 양식에서 R-001 선택", self.fmt(kind=kind).splitlines(), kind)
        for kind in ("merge", "run", "info"):
            self.assertNotIn("답하는 법", self.fmt(kind=kind), kind)
        self.assertIn("양식에서 R-042 선택", self.fmt(kind="decision", request_id="R-042"))

    def test_the_overflow_line_counts_the_requests_that_did_not_fit(self):
        self.assertIn("… 외 2건 (저장소의 인수인계/요청함/ 폴더에서 확인하세요)", self.fmt(more=2).splitlines())
        self.assertNotIn("… 외", self.fmt(more=0))
        with self.assertRaises(ValueError):
            self.fmt(more=-1)

    def test_a_bad_request_number_or_kind_is_refused(self):
        for request_id in ("R-1", "R-0001", "r-001", "R-001\n", "", None, "R-00a"):
            with self.assertRaises(ValueError, msg=request_id):
                self.fmt(request_id=request_id)
        for kind in ("", "Merge", None, "병합"):
            with self.assertRaises(ValueError, msg=kind):
                self.fmt(kind=kind)

    def test_html_in_the_title_and_summary_is_escaped(self):
        text = self.fmt(title="<b>굵게</b> & <i>x</i>", summary='<a href="https://e.example">링크</a> <script>')
        body = text.split("\n", 1)[1]
        self.assertNotIn("<", body)
        self.assertIn("&lt;b&gt;굵게&lt;/b&gt; &amp; &lt;i&gt;x&lt;/i&gt;", body)

    def test_urls_in_the_text_are_defanged_and_mentions_do_not_become_links(self):
        text = self.fmt(title="@owner 확인 https://evil.example/t", summary="https://evil.example/x tg://resolve?domain=bot ftp://a.example @everyone @owner")
        title_line, summary_line = text.split("\n")[1:3]
        for part in (title_line, summary_line):                          # 제목과 요약 둘 다(AI 가 쓴 글 둘)
            for needle in ("https://", "tg://", "ftp://", "@"):
                self.assertNotIn(needle, part, needle)
        self.assertIn("https" + chr(0xFF1A) + "//evil.example/x", summary_line)
        self.assertIn(chr(0xFF20) + "owner", summary_line)
        self.assertTrue(title_line.startswith(chr(0xFF20) + "owner 확인"), title_line)
        self.assertIn("https" + chr(0xFF1A) + "//evil.example/t", title_line)

    def test_secret_shaped_text_is_masked_and_invisible_or_control_characters_are_removed(self):
        text = self.fmt(title="키 " + nh.TOKEN + " 끝", summary="AIza" + "B" * 35 + " " + chr(0x200B) + "a" + chr(0x202E) + "b" + chr(0xFEFF) + "c\x00d\x07e")
        self.assertEqual(leaks(text), [])
        self.assertNotIn("AIza", text)
        for char in (chr(0x200B), chr(0x202E), chr(0xFEFF), "\x00", "\x07"):
            self.assertNotIn(char, text)
        self.assertIn("abc", text)

    def test_line_breaks_and_workflow_commands_in_the_text_are_folded_into_one_line(self):
        text = self.fmt(title="첫 줄\n::error::가짜\r\n##[warning]둘째", summary="a\n\n\nb\t\tc")
        lines = text.splitlines()
        self.assertEqual(len(lines), 3)                                                       # 머리·제목·요약 한 줄씩
        for line in lines:
            self.assertFalse(line.startswith("::"))
            self.assertNotIn("##[", line)
        self.assertEqual(lines[2], "a b c")

    def test_the_title_and_summary_are_cut_to_their_limits(self):
        text = self.fmt(title="가" * 500, summary="나" * 2000)
        title, summary = text.splitlines()[1:3]
        self.assertEqual((len(title), len(summary)), (notify.REQUEST_TITLE_LIMIT, notify.REQUEST_SUMMARY_LIMIT))
        self.assertTrue(title.endswith("…") and summary.endswith("…"))
        self.assertEqual((notify.REQUEST_TITLE_LIMIT, notify.REQUEST_SUMMARY_LIMIT), (80, 300))

    def test_the_whole_message_stays_far_under_the_telegram_limit(self):
        text = self.fmt(kind="decision", title="가" * 500, summary="나" * 2000, pr=1234567, urgency="급함", more=9)
        self.assertLess(notify.utf16_len(text), notify.TEXT_LIMIT)


class ButtonsTest(unittest.TestCase):
    REQUEST = ol.Request("R-001", "merge", "제목", "요약", "보통", 57, "", GOOD_NAME)

    def buttons(self, request=None, ref="ai/claude/operator-loop", default="main"):
        return ol.request_buttons(request or self.REQUEST, ref, default)

    def test_four_buttons_in_the_promised_order(self):
        labels = [label for label, _ in self.buttons()]
        self.assertEqual(labels, ["요청 열기", "PR 열기", "답하기", "사용법"])

    def test_the_request_button_opens_the_file_on_the_pushed_branch_with_an_encoded_path(self):
        url = self.buttons()[0][1]
        self.assertEqual(url, f"{BLOB}ai/claude/operator-loop/{FOLDER}/{GOOD_NAME}")
        self.assertEqual(urllib.parse.unquote(url.split("/blob/")[1]), "ai/claude/operator-loop/인수인계/요청함/R-001_merge-pr57.md")

    def test_the_pr_button_needs_a_pr_number_and_points_at_this_repository(self):
        self.assertEqual(self.buttons()[1], ("PR 열기", "https://github.com/shine88pc/chanceblog/pull/57"))
        labels = [label for label, _ in self.buttons(self.REQUEST._replace(pr=None))]
        self.assertEqual(labels, ["요청 열기", "답하기", "사용법"])

    def test_the_answer_button_opens_the_issue_form_chooser(self):
        self.assertEqual(dict(self.buttons())["답하기"], "https://github.com/shine88pc/chanceblog/issues/new/choose")

    def test_the_guide_button_uses_the_default_branch(self):
        self.assertEqual(dict(self.buttons())["사용법"], f"{BLOB}main/{GUIDE}")
        self.assertEqual(dict(self.buttons(default="develop"))["사용법"], f"{BLOB}develop/{GUIDE}")

    def test_every_button_passes_the_alert_address_allow_list(self):
        for label, url in self.buttons():
            self.assertEqual(notify.allowed_url(url), url, label)


class ReceivedMessageTest(unittest.TestCase):
    """접수 확인 문구(평문 두 가지)의 모양과 방어. 값은 접수 코드가 이미 검증하지만 이 함수들도 외부 글을 믿지 않는다."""

    def test_the_reply_confirmation_has_the_promised_shape(self):
        self.assertEqual(notify.format_reply_received("R-001", "승인", 12), f"{notify.OK_MARK} 답변 접수 R-001 → 승인(이슈 #12)")
        self.assertEqual(notify.format_reply_received("R-001", "승인", 12, choice="B"), f"{notify.OK_MARK} 답변 접수 R-001 → 승인 · 선택 B(이슈 #12)")

    def test_the_task_confirmation_has_the_promised_shape(self):
        self.assertEqual(notify.format_task_received(13, "급함", True), f"{notify.OK_MARK} 새 일 요청 접수(이슈 #13) · 긴급도 급함 · 진행 범위 구현까지(T3 제외)")
        for old_phrase in ("T3 포함", "승인 범위", "있음("):                                                          # `[요청]` 이 T3 를 승인한 것처럼 읽히는 옛 문구가 없다(독립 검증 B-1)
            self.assertNotIn(old_phrase, notify.format_task_received(13, "급함", True), old_phrase)
        self.assertEqual(notify.format_task_received(13, "보통", False), f"{notify.OK_MARK} 새 일 요청 접수(이슈 #13) · 긴급도 보통 · 논의·준비까지만")

    def test_unvalidated_words_are_folded_into_one_line_cut_and_never_a_workflow_command(self):
        hostile = "승인\n::set-output name=x::y @everyone " + chr(0x202E)
        for text in (notify.format_reply_received("R-001", hostile, 3, choice="B\n@x"), notify.format_task_received(5, hostile, True)):
            self.assertEqual(len(text.splitlines()), 1, text)
            self.assertNotIn("::", text)
            self.assertNotIn(chr(0x202E), text)
        self.assertLessEqual(len(notify.format_reply_received("R-001", "승" * 500, 3)), 80)
        self.assertLessEqual(len(notify.format_task_received(5, "급" * 500, False)), 80)

    def test_numbers_must_be_positive_integers_and_the_request_number_and_answer_must_be_real(self):
        for bad in (0, -1, True, "3", None, 2.5):
            with self.assertRaises(ValueError, msg=bad):
                notify.format_reply_received("R-001", "승인", bad)
            with self.assertRaises(ValueError, msg=bad):
                notify.format_task_received(bad, "보통", False)
        for bad_id in ("R-1", "r-001", "R-0001", None, ""):
            with self.assertRaises(ValueError, msg=bad_id):
                notify.format_reply_received(bad_id, "승인", 3)
        with self.assertRaises(ValueError):
            notify.format_reply_received("R-001", chr(0x200B), 3)                       # 지우고 나면 빈 답


class NotifierRequestTest(unittest.TestCase):
    def test_a_request_is_one_html_message_with_the_four_buttons(self):
        notifier, net, _ = nh.make_notifier()
        buttons = ol.request_buttons(ol.Request("R-001", "decision", "t", "s", "보통", 57, "", GOOD_NAME), "ai/claude/x", "main")
        result = notifier.notify_ai_request("R-001", "decision", "결정할 것", "A 와 B 중 하나", pr=57, buttons=buttons)
        self.assertTrue(result.sent)
        body = net.bodies()[0]
        self.assertEqual(body["parse_mode"], "HTML")
        self.assertEqual(body["chat_id"], int(CHAT))
        self.assertTrue(body["text"].startswith(f"{notify.BELL_MARK} <b>AI 요청 R-001 · 결정 부탁</b>\n결정할 것\nA 와 B 중 하나\n관련 PR: #57\n\n답하는 법"))
        row = body["reply_markup"]["inline_keyboard"][0]
        self.assertEqual([button["text"] for button in row], ["요청 열기", "PR 열기", "답하기", "사용법"])
        self.assertEqual(body["link_preview_options"], {"is_disabled": True})

    def test_a_button_address_outside_the_allow_list_is_dropped_not_sent(self):
        notifier, net, _ = nh.make_notifier()
        buttons = [("요청 열기", "https://evil.example/R-001"), ("답하기", notify.NEW_ISSUE_URL), ("사칭", "https://github.com.evil.example/shine88pc/chanceblog/x"),
                   ("다른 저장소", "https://github.com/someone/else/blob/main/x.md")]
        notifier.notify_ai_request("R-001", "merge", "t", "s", buttons=buttons)
        self.assertEqual([button["text"] for button in net.bodies()[0]["reply_markup"]["inline_keyboard"][0]], ["답하기"])

    def test_without_the_secrets_nothing_is_sent(self):
        notifier, net, _ = nh.make_notifier(environ={})
        result = notifier.notify_ai_request("R-001", "merge", "t", "s")
        self.assertEqual((result.ok, result.sent, result.reason, net.calls), (True, False, notify.DISABLED, 0))

    def test_bad_values_become_an_internal_error_result_and_never_raise(self):
        notifier, net, _ = nh.make_notifier()
        for kwargs in ({"request_id": "R-1"}, {"kind": "zzz"}, {"pr": -1}):
            base = {"request_id": "R-001", "kind": "merge", "title": "t", "summary": "s"}
            base.update(kwargs)
            result = notifier.notify_ai_request(**base)
            self.assertEqual((result.ok, result.sent, result.reason), (False, False, notify.INTERNAL_ERROR), kwargs)
        self.assertEqual(net.calls, 0)

    def test_a_telegram_failure_is_a_result_and_the_token_is_not_in_it(self):
        notifier, net, _ = nh.make_notifier(net=FakeNet(http_error(401, "Unauthorized")))
        result = notifier.notify_ai_request("R-001", "merge", "t", "s")
        self.assertEqual((result.ok, result.sent, result.reason), (False, False, notify.UNAUTHORIZED))
        self.assertEqual(leaks(notify.describe(result), repr(result)), [])

    def test_the_module_level_wrapper_uses_the_given_notifier(self):
        notifier, net, _ = nh.make_notifier()
        self.assertTrue(notify.notify_ai_request("R-001", "info", "t", "s", notifier=notifier).sent)
        self.assertEqual(net.calls, 1)


class RequestsCliTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.summary = self.tmp / "summary.md"

    def run_requests(self, git, **env_kwargs):
        env = requests_env(GITHUB_STEP_SUMMARY=str(self.summary), **env_kwargs)
        return oh.run_cli("requests", environ=env, runner=git, root=self.tmp)

    def test_without_secrets_it_prints_one_line_and_never_touches_git(self):
        def refuse(*args, **kwargs):
            raise AssertionError("시크릿이 없으면 git 도 부르지 않는다")
        for env in ({}, {"TELEGRAM_BOT_TOKEN": TOKEN}, {"TELEGRAM_CHAT_ID": CHAT}):
            code, lines, net, _ = oh.run_cli("requests", environ=dict(requests_env(telegram=False), **env), runner=refuse, root=self.tmp)
            self.assertEqual((code, lines, net.calls), (0, [ol.REQUESTS_SKIP_LINE], 0))

    def test_no_new_request_file_means_one_plain_line_no_message_and_no_annotation(self):
        code, lines, net, _ = self.run_requests(RequestGit(tree=[]))
        self.assertEqual((code, lines, net.calls), (0, [ol.REQUESTS_NONE_LINE], 0))
        self.assertFalse(any(line.startswith("::") for line in lines))
        self.assertFalse(self.summary.exists())

    def test_files_that_another_branch_already_has_are_named_in_one_plain_log_line(self):
        code, lines, net, _ = self.run_requests(RequestGit(tree=oh.paths("R-001_a.md"), log=[]))
        self.assertEqual((code, net.calls), (0, 0))
        self.assertEqual(lines, [ol.skipped_line(["R-001_a.md"]), ol.REQUESTS_NONE_LINE])
        self.assertFalse(any(line.startswith("::") for line in lines))                              # 경고가 아니라 알림 한 줄(main 을 합친 정상 push 에서도 나온다)
        self.assertFalse(self.summary.exists())

    def test_the_skipped_line_comes_first_and_a_skipped_file_is_neither_read_nor_sent(self):
        git = RequestGit(tree=oh.paths("R-001_a.md", "R-002_b.md"), log=oh.paths("R-002_b.md"), files={"R-002_b.md": request_text(id="R-002")})
        code, lines, net, _ = self.run_requests(git)
        self.assertEqual(lines, [ol.skipped_line(["R-001_a.md"]), "AI 요청 알림: R-002 을 알렸습니다"])
        self.assertEqual(net.calls, 1)
        self.assertEqual([args[3].split(":", 1)[1].rsplit("/", 1)[-1] for args in git.names("cat-file")], ["R-002_b.md"])

    def test_nothing_is_logged_about_skipped_files_when_there_are_none(self):
        code, lines, net, _ = self.run_requests(RequestGit.with_requests({GOOD_NAME: request_text()}))
        self.assertEqual(lines, ["AI 요청 알림: R-001 을 알렸습니다"])

    def test_one_new_request_is_sent_as_one_message_and_logged(self):
        git = RequestGit.with_requests({GOOD_NAME: request_text(kind="decision", title="고를 것", summary="A 와 B", pr="57")})
        code, lines, net, _ = self.run_requests(git)
        self.assertEqual((code, net.calls), (0, 1))
        self.assertEqual(lines, ["AI 요청 알림: R-001 을 알렸습니다"])
        body = net.bodies()[0]
        self.assertIn("AI 요청 R-001 · 결정 부탁", body["text"])
        self.assertEqual([b["text"] for b in body["reply_markup"]["inline_keyboard"][0]], ["요청 열기", "PR 열기", "답하기", "사용법"])
        self.assertIn(f"{BLOB}ai/claude/operator-loop/{FOLDER}/{GOOD_NAME}", body["reply_markup"]["inline_keyboard"][0][0]["url"])
        self.assertEqual(self.summary.read_text(encoding="utf-8").strip(), "### AI 요청 텔레그램 알림\n\n- R-001: 알렸습니다")
        self.assertEqual(leaks(*lines, self.summary.read_text(encoding="utf-8")), [])

    def test_the_file_is_read_from_the_pushed_commit(self):
        git = RequestGit.with_requests({GOOD_NAME: request_text()})
        self.run_requests(git)
        reads = git.names("cat-file")
        self.assertEqual(reads, [["git", "cat-file", "blob", f"{SHA_A}:{ol.REQUEST_DIR}/{GOOD_NAME}"]])

    def test_at_most_three_messages_per_push_and_the_rest_are_counted_on_the_last(self):
        files = {f"R-{index:03d}_x.md": request_text(id=f"R-{index:03d}", title=f"요청 {index}") for index in range(1, 6)}
        code, lines, net, _ = self.run_requests(RequestGit.with_requests(files))
        self.assertEqual((code, net.calls), (0, 3))
        texts = [body["text"] for body in net.bodies()]
        self.assertEqual([("AI 요청 R-00%d" % n) in text for n, text in zip((1, 2, 3), texts)], [True, True, True])
        self.assertNotIn("… 외", texts[0] + texts[1])
        self.assertIn("… 외 2건", texts[2])
        self.assertIn("한 푸시에 3통까지만 보내 2건은", "\n".join(lines))
        self.assertEqual(ol.MAX_REQUEST_MESSAGES, 3)

    def test_an_invalid_file_is_reported_and_the_valid_ones_are_still_sent(self):
        files = {"R-001_good.md": request_text(), "R-002_bad.md": "제목 없는 파일\n", "R-003_ok.md": request_text(id="R-003")}
        code, lines, net, _ = self.run_requests(RequestGit.with_requests(files))
        self.assertEqual((code, net.calls), (0, 2))
        joined = "\n".join(lines)
        self.assertIn("R-002_bad.md 을 알리지 못했습니다 — 파일 맨 앞이 `---` 한 줄로 시작하는 앞머리가 아닙니다", joined)
        self.assertIn(ol.REQUEST_PROBLEM_WARNING, lines)
        self.assertTrue(ol.REQUEST_PROBLEM_WARNING.startswith("::warning::"))

    def test_a_file_git_cannot_read_is_reported(self):
        git = RequestGit(tree=oh.paths("R-001_x.md"), files={})
        code, lines, net, _ = self.run_requests(git)
        self.assertEqual((code, net.calls), (0, 0))
        self.assertIn("R-001_x.md 을 알리지 못했습니다 — git 에서 파일 내용을 읽지 못했습니다", "\n".join(lines))

    def test_when_git_cannot_find_the_new_files_nothing_is_sent_and_a_warning_is_left(self):
        for broken in ("diff", "log"):
            git = RequestGit.with_requests({GOOD_NAME: request_text()}, broken={broken})
            code, lines, net, _ = self.run_requests(git)
            self.assertEqual((code, net.calls), (0, 0), broken)
            self.assertIn("새 요청 파일을 찾지 못해 보내지 않았습니다 — git 명령이 실패했습니다", "\n".join(lines))
            self.assertEqual(lines[-1], ol.GIT_WARNING)
            self.assertTrue(lines[-1].startswith("::warning::"))

    def test_a_shallow_clone_on_the_first_push_of_a_branch_sends_nothing(self):
        git = RequestGit.with_requests({GOOD_NAME: request_text()}, shallow=True)
        code, lines, net, _ = self.run_requests(git, before=ZERO)
        self.assertEqual((code, net.calls), (0, 0))
        self.assertIn("얕은 복제", "\n".join(lines))
        self.assertEqual(lines[-1], ol.GIT_WARNING)

    def test_a_bad_environment_sends_nothing_and_says_so(self):
        git = RequestGit.with_requests({GOOD_NAME: request_text()})
        for kwargs in ({"before": "zz"}, {"after": ""}, {"after": ZERO}, {"ref_name": "main"}, {"ref_name": ""}, {"default_branch": "--x"}):
            code, lines, net, _ = self.run_requests(git, **kwargs)
            self.assertEqual((code, net.calls), (0, 0), kwargs)
            self.assertEqual(lines[-1], ol.GIT_WARNING, kwargs)

    def test_a_missing_default_branch_value_falls_back_to_main(self):
        git = RequestGit.with_requests({GOOD_NAME: request_text()})
        env = requests_env(before=ZERO)
        del env["DEFAULT_BRANCH"]
        code, lines, net, _ = oh.run_cli("requests", environ=env, runner=git, root=self.tmp)
        self.assertEqual(net.calls, 1)
        self.assertEqual(git.names("merge-base")[0][2], "origin/main")

    def test_a_telegram_failure_is_a_warning_and_the_exit_code_stays_zero(self):
        git = RequestGit.with_requests({GOOD_NAME: request_text()})
        env = requests_env(GITHUB_STEP_SUMMARY=str(self.summary))
        for outcome, reason in ((http_error(401, "Unauthorized: bot " + TOKEN), "unauthorized"), (http_error(403, "Forbidden"), "forbidden")):
            code, lines, net, _ = oh.run_cli("requests", environ=env, runner=git, root=self.tmp, net=FakeNet(outcome))
            self.assertEqual(code, 0)
            self.assertTrue(any("R-001 을 보내지 못했습니다" in line for line in lines), lines)
            self.assertEqual(lines[-1], ol.REQUEST_WARNING_LINE)
            self.assertEqual(leaks(*lines), [], reason)
            self.assertIn("보내지 못했습니다(" + reason + ")", self.summary.read_text(encoding="utf-8"))

    def test_the_token_is_in_no_output_even_when_the_request_text_contains_it(self):
        text = request_text(title="토큰 " + TOKEN, summary="토큰 전체 " + TOKEN + " 와 또 " + TOKEN)
        code, lines, net, _ = self.run_requests(RequestGit.with_requests({GOOD_NAME: text}))
        self.assertEqual(code, 0)
        self.assertEqual(leaks(net.bodies()[0]["text"], chat=False), [])                   # 보내는 글에서도 토큰 모양은 가려진다(채팅 ID 는 비밀이 아니라 글에 있어도 된다)
        self.assertEqual(leaks(*lines), [])

    def test_an_unexpected_error_is_a_class_name_and_a_warning_with_exit_code_zero(self):
        def boom(args, **kwargs):
            raise RuntimeError("비밀 " + TOKEN)
        code, lines, net, _ = oh.run_cli("requests", environ=requests_env(), runner=lambda a, **k: boom(a), root=self.tmp)
        self.assertEqual(code, 0)
        self.assertTrue(any("예기치 않은 오류(RuntimeError)" in line for line in lines), lines)
        self.assertEqual(leaks(*lines), [])

    def test_the_command_line_takes_no_values_and_a_wrong_command_is_a_fixed_usage_error(self):
        for argv in ([], ["bogus"], ["requests", "--commit", "HEAD"], ["ack", "R-001"], ["requests", TOKEN]):
            sink = io.StringIO()
            with contextlib.redirect_stderr(sink), self.assertRaises(SystemExit) as caught:
                ol.main(argv, environ={}, out=lambda text: None)
            self.assertEqual(caught.exception.code, 2, argv)
            self.assertIn(ol.USAGE_ERROR_LINE, sink.getvalue())
            self.assertEqual(leaks(sink.getvalue()), [], argv)


if __name__ == "__main__":
    unittest.main()
