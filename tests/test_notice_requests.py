"""번호 있는 요청 파일(앞머리 `no`·유형별 칸)의 읽기·검증기 REQ-1·알림 보내기 시험(pipeline/operator_loop.py·scripts/validate_repo.py, TG-STD 운영자 승인 2026-11-06 R-165).

핵심: ① 새 칸은 `no` 가 있는 파일에만 적용되고 R-165 까지의 옛 파일은 옛 모양 그대로 읽히고 REQ-1 을 통과한다 ② 유형(P·M·숫자)과 kind 가 맞아야 하고 유형별 필수 칸이 있어야 한다
③ 같은 알림 번호를 가진 파일이 둘이면 검증기가 오류 ④ 런타임은 새 칸이 틀려도 알림을 잃지 않고 옛 모양(제목·요약)으로 보낸다 ⑤ 병합 요청의 PR 제목은 파일에서 폰 글까지 글자 그대로다.
네트워크·실제 텔레그램·실제 GitHub 는 없다(가짜 git·가짜 HTTP).
"""
import html
import random
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import _bootstrap
import notice_helpers as nth
import notify_helpers as nh
import operator_loop_helpers as oh
from notice_helpers import PROGRESS, MERGE, ASK, code_of, name_of, notice_text, parse
from operator_loop_helpers import RequestGit, request_text, requests_env
from pipeline import notify
from pipeline import operator_loop as ol

ROOT = _bootstrap.ROOT
sys.path.insert(0, str(ROOT / "scripts"))
import validate_repo as vr  # noqa: E402

BLOB = "https://github.com/shine88pc/chanceblog/blob/"


class ParseNoticeTest(unittest.TestCase):
    def test_each_number_type_reads_its_own_fields_and_the_summary_stays_for_the_ask(self):
        request = parse(notice_text(no="P012", work="R-160", urgency="급함", pr="57"))
        self.assertEqual((request.id, request.kind, request.no, request.work, request.urgency, request.pr, request.notice_error), ("R-166", "info", "P012", "R-160", "급함", 57, ""))
        self.assertEqual(dict(request.fields), PROGRESS)
        request = parse(notice_text(no="M007"))
        self.assertEqual((request.kind, request.no, dict(request.fields)), ("merge", "M007", MERGE))
        request = parse(notice_text(no="003", kind="decision", summary="무엇을 할까요"))
        self.assertEqual((request.kind, request.no, dict(request.fields)), ("decision", "003", {**ASK, "summary": "무엇을 할까요"}))
        self.assertEqual(request.title, "[R-166] 진행 현황")

    def test_every_ask_kind_and_only_the_matching_pairs_are_accepted(self):
        accepted = {("info", "P"), ("merge", "M"), ("decision", ""), ("confirm", ""), ("run", "")}
        for kind in ("info", "merge", "decision", "confirm", "run"):
            for prefix, no in (("P", "P012"), ("M", "M012"), ("", "012")):
                text = notice_text(no=no, kind=kind, fields=nth.BODY_OF[prefix])
                for strict in (True, False):
                    if (kind, prefix) in accepted:
                        found = parse(text, strict=strict)
                        self.assertEqual((found.no, found.notice_error), (no, ""), (kind, no, strict))
                    elif strict:
                        self.assertEqual(code_of(text, strict=True), "no_kind_mismatch", (kind, no))
                    else:
                        found = parse(text)
                        self.assertEqual((found.no, found.notice_error), ("", "no_kind_mismatch"), (kind, no))

    def test_the_number_may_be_quoted_but_the_pr_title_is_never_unquoted(self):
        for raw in ('"003"', "'003'", "003"):
            self.assertEqual(parse(notice_text(no=raw, kind="decision")).no, "003", raw)
        title = '"따옴표로 시작하고 끝나는 제목"'
        request = parse(notice_text(no="M007", fields={**MERGE, "pr_title": title}))
        self.assertEqual(dict(request.fields)["pr_title"], title)
        self.assertEqual(dict(parse(notice_text(no="M007", fields={**MERGE, "pr_title": "'a'"})).fields)["pr_title"], "'a'")
        self.assertEqual(parse(notice_text(no="M007", title='"제목"')).title, "제목")             # 다른 칸은 옛 규칙대로 따옴표를 벗긴다

    def test_old_files_are_read_exactly_as_before(self):
        request = parse(request_text(id="R-001", kind="decision", title="두 가지 중 고르기", summary="A 와 B", urgency="급함", pr="57", created="2026-10-28"), number=1)
        self.assertEqual(request, ol.Request("R-001", "decision", "두 가지 중 고르기", "A 와 B", "급함", 57, "2026-10-28", name_of(1)))
        self.assertEqual((request.no, request.work, request.fields, request.notice_error), ("", "", (), ""))
        for number in (1, 22, 100, 164, 165):
            for strict in (True, False):
                self.assertEqual(ol.parse_request(name_of(number), request_text(id=f"R-{number:03d}"), strict=strict).no, "", number)

    def test_the_new_keys_are_known_and_the_strict_unknown_key_rule_still_stands(self):
        for key in ("no", "work", "at", "now", "changed", "next", "eta", "waiting", "check", "repo", "target", "pr_title", "verify", "state", "options", "default", "approve"):
            self.assertIn(key, ol.REQUEST_KEYS, key)
        self.assertEqual(ol.REQUEST_KEYS[:7], ("id", "kind", "title", "summary", "urgency", "pr", "created"))
        self.assertEqual(len(ol.REQUEST_KEYS), len(set(ol.REQUEST_KEYS)))
        self.assertEqual(code_of(notice_text(extra="owner: x"), strict=True), "unknown_key")
        self.assertEqual(parse(notice_text(extra="owner: x")).no, "P001")

    def test_the_title_and_summary_stay_required_in_new_files_for_older_readers(self):
        for key in ("title", "summary"):
            for strict in (True, False):
                self.assertEqual(code_of(notice_text(**{key: None}), strict=strict), f"missing_{key}", (key, strict))

    def test_a_number_that_is_not_a_notice_number_is_bad_no(self):
        for bad in ("P1", "P12", "12", "P000", "000", "P10000", "p001", "R-001", "P-001", "①②③", "0 01", "P 001", "", "P001 x"):
            for strict in (True, False):
                text = notice_text(no=bad, kind="info")
                if strict:
                    self.assertEqual(code_of(text, strict=True), "bad_no", repr(bad))
                else:
                    self.assertEqual(parse(text).notice_error, "bad_no", repr(bad))

    def test_every_required_field_of_each_type_is_required(self):
        """수정 1차(V3 M2): 필수 칸 목록을 **글자 그대로** 적고 코드의 `NOTICE_REQUIRED` 와 같은지 먼저 대조한다 — 예전에는 코드의 상수를 스스로 순회해서 목록에서 `waiting`·`verify` 를 빼도
        시험이 그대로 통과했다(그러면 칸이 빠진 진행 현황·병합 요청이 REQ-1·런타임을 통과하고 `format_*` 가 ValueError 를 내 알림이 조용히 안 나간다)."""
        required = {"progress": ("at", "now", "changed", "next", "eta", "waiting"), "merge": ("repo", "target", "pr_title", "verify"), "ask": ()}
        self.assertEqual(ol.NOTICE_REQUIRED, required)
        for optional_no, optional_kind, optional_key in (("P012", "info", "check"), ("M012", "merge", "state")):                          # 선택 칸은 없어도 된다
            self.assertEqual(code_of(notice_text(no=optional_no, kind=optional_kind, drop=(optional_key,)), strict=True), "", optional_key)
        for prefix, no, kind in (("P", "P012", "info"), ("M", "M012", "merge")):
            for key in required[{"P": "progress", "M": "merge"}[prefix]]:
                text = notice_text(no=no, kind=kind, drop=(key,))
                self.assertEqual(code_of(text, strict=True), f"missing_{key}", key)
                self.assertEqual(parse(text).notice_error, f"missing_{key}", key)
                for blank in ("", "   ", chr(0x200B)):
                    if key == "pr_title" and blank == chr(0x200B):
                        continue                                                                    # PR 제목은 글자 그대로라 보이지 않는 글자는 '비었음'이 아니라 pr_title_control 이다
                    self.assertEqual(code_of(notice_text(no=no, kind=kind, fields={**nth.BODY_OF[prefix], key: blank}), strict=True), f"missing_{key}", (key, blank))
        self.assertEqual(ol.NOTICE_REQUIRED["ask"], ())
        self.assertEqual(code_of(notice_text(no="003", kind="decision", fields={}), strict=True), "")      # 확인 요청은 summary 만으로 된다

    def test_fields_of_another_type_are_refused(self):
        cases = ((("P012", "info"), "repo", "x/y"), (("P012", "info"), "options", "가 / 나"), (("M012", "merge"), "now", "x"), (("M012", "merge"), "at", "2026-11-06 12:07"),
                 (("012", "decision"), "now", "x"), (("012", "decision"), "pr_title", "x"), (("012", "decision"), "state", "x"))
        for (no, kind), key, value in cases:
            prefix = no[:1] if no[:1] in "PM" else ""
            text = notice_text(no=no, kind=kind, fields={**nth.BODY_OF[prefix], key: value})
            self.assertEqual(code_of(text, strict=True), "foreign_key", (no, key))
            self.assertEqual(parse(text).notice_error, "foreign_key", (no, key))

    def test_notice_fields_without_a_number_are_refused_even_in_an_old_numbered_file(self):
        text = request_text(id="R-001", extra="now: 진행 중")
        self.assertEqual(code_of(text, number=1, strict=True), "notice_keys_without_no")
        self.assertEqual(parse(text, number=1).notice_error, "notice_keys_without_no")                  # 런타임은 옛 모양으로 보내고 이유를 남긴다
        self.assertEqual(code_of(request_text(id="R-001", extra="work: R-160"), number=1, strict=True), "notice_keys_without_no")

    def test_from_the_start_number_on_a_file_needs_a_notice_number_in_strict_mode_only(self):
        start = ol.NOTICE_NO_REQUIRED_FROM_R
        self.assertGreaterEqual(start, 166)
        for number in (start, start + 1, 999):
            text = request_text(id=f"R-{number:03d}")
            self.assertEqual(code_of(text, number=number, strict=True), "no_required", number)
            self.assertEqual(parse(text, number=number).no, "", number)                  # 런타임은 옛 모양 그대로 보낸다
        for number in (1, 22, 100, 165, start - 1):
            self.assertEqual(code_of(request_text(id=f"R-{number:03d}"), number=number, strict=True), "", number)
        self.assertEqual(code_of(notice_text(number=start, no="P001"), number=start, strict=True), "")

    def test_the_work_number_must_be_the_canonical_request_number(self):
        for good in ("R-001", "R-160", "R-999"):
            self.assertEqual(parse(notice_text(work=good)).work, good)
        for bad in ("r160", "R160", "R-16", "R-0160", "160", "R-160 x", ""):
            self.assertEqual(code_of(notice_text(work=bad), strict=True), "bad_work", repr(bad))

    def test_the_progress_time_must_be_a_real_kst_time_in_the_fixed_shape(self):
        for bad in ("2026-11-06", "2026-11-06T12:07", "2026-13-06 12:07", "2026-11-31 12:07", "2026-11-06 24:00", "11-06 12:07", "2026-11-06 12:7", "２０２６-11-06 12:07"):
            text = notice_text(no="P012", fields={**PROGRESS, "at": bad})
            self.assertEqual(code_of(text, strict=True), "bad_at", repr(bad))
            self.assertEqual(parse(text).notice_error, "bad_at", repr(bad))

    def test_the_repository_name_must_be_owner_slash_name(self):
        for good in ("shine88pc/chanceblog", "a/b", "shine88pc/chanceblog-desktop", "o/r.name_1"):
            self.assertEqual(code_of(notice_text(no="M007", fields={**MERGE, "repo": good}), strict=True), "", good)
        for bad in ("chanceblog", "shine88pc/", "/chanceblog", "a/b/c", "a/..", "a/.", "-a/b", "a b/c", "shine88pc/chance blog", "https://github.com/a/b", "a/b\u200b"):
            self.assertEqual(code_of(notice_text(no="M007", fields={**MERGE, "repo": bad}), strict=True), "bad_repo", repr(bad))

    def test_the_ask_options_default_and_approve_rules(self):
        def code(**fields):
            return code_of(notice_text(no="003", kind="decision", fields=fields), strict=True)
        self.assertEqual(code(options="가 / 나"), "")
        self.assertEqual(code(options="가 / 나", default="1", approve="2"), "")
        self.assertEqual(code(options="가 / 나 / 다 / 라 / 마", default="5", approve="4"), "")
        for options in ("", "하나", "가 / ", "가 /  / 나", "가 / 나 / 다 / 라 / 마 / 바", "가" * 61 + " / 나"):
            self.assertEqual(code(options=options), "bad_options", repr(options))
        self.assertEqual(code(options="가" * 60 + " / 나"), "")
        for key in ("default", "approve"):
            for value in ("0", "6", "3", "①", "01", "x", "", " ", "1 2"):
                self.assertEqual(code(options="가 / 나", **{key: value}), f"bad_{key}", (key, value))
            self.assertEqual(code(**{key: "1"}), f"bad_{key}", key)                            # 보기가 없는데 번호가 있다
        self.assertEqual(code(options="가 / 나", default="1", approve="1"), "approve_is_default")
        self.assertEqual(code(options="가 / 나", default="2", approve="2"), "approve_is_default")

    def test_lengths_are_enforced_only_in_strict_mode(self):
        for key, limit in ol.NOTICE_LIMITS.items():
            prefix = "P" if key in ("now", "changed", "next", "eta", "waiting", "check") else "M"
            no, kind = ("P012", "info") if prefix == "P" else ("M012", "merge")
            base = nth.BODY_OF[prefix]
            ok = notice_text(no=no, kind=kind, fields={**base, key: "가" * limit})
            over = notice_text(no=no, kind=kind, fields={**base, key: "가" * (limit + 1)})
            self.assertEqual(code_of(ok, strict=True), "", key)
            self.assertEqual(code_of(over, strict=True), f"long_{key}", key)
            self.assertEqual(parse(over).notice_error, "", key)                                  # 런타임은 받고 보낼 때 줄인다
            self.assertEqual(ol.problem_text(f"long_{key}"), f"`{key}` 가 {limit}자를 넘습니다")
        self.assertEqual(ol.NOTICE_LIMITS, {"now": 200, "changed": 200, "next": 200, "waiting": 200, "eta": 100, "check": 60, "target": 100, "verify": 120, "state": 40})

    def test_the_pr_title_rules_strict_and_at_run_time(self):
        def title_code(title, strict=True):
            return code_of(notice_text(no="M007", fields={**MERGE, "pr_title": title}), strict=strict)
        self.assertEqual(title_code("[R-160] " + "가" * (notify.PR_TITLE_LIMIT - 8)), "")
        self.assertEqual(title_code("[R-160] " + "가" * (notify.PR_TITLE_LIMIT - 7)), "long_pr_title")
        self.assertEqual(title_code("[R-1] a\u200bb"), "pr_title_control")
        self.assertEqual(title_code("[R-1] a\u202eb"), "pr_title_control")
        self.assertEqual(title_code("[R-1] " + "AIza" + "x" * 35), "pr_title_secret")
        self.assertEqual(title_code(""), "missing_pr_title")
        for title in ("[R-1] " + "AIza" + "x" * 35, "[R-160] " + "가" * 400, "[R-1] a\u200bb"):
            self.assertEqual(title_code(title, strict=False), "", repr(title[:12]))           # 런타임은 읽고, 보낼 때 notify 가 글자 그대로 보낼 수 없으면 보내지 않는다
        self.assertEqual(notify.PR_TITLE_LIMIT, 200)

    def test_at_run_time_a_bad_notice_part_falls_back_to_the_old_shape_and_says_why(self):
        for text, code in ((notice_text(no="P012", drop=("now",)), "missing_now"), (notice_text(no="P012", kind="merge"), "no_kind_mismatch"), (notice_text(no="X1"), "bad_no"),
                           (notice_text(no="M007", fields={**MERGE, "repo": "x"}), "bad_repo")):
            request = parse(text)
            self.assertEqual((request.no, request.work, request.fields, request.notice_error), ("", "", (), code), code)
            self.assertEqual((request.id, request.title, request.summary), ("R-166", "[R-166] 진행 현황", "현황 알림입니다"))

    def test_every_problem_code_has_a_fixed_sentence_without_outside_values(self):
        codes = ["bad_no", "no_kind_mismatch", "no_required", "notice_keys_without_no", "foreign_key", "bad_work", "bad_at", "bad_repo", "bad_options", "bad_default", "bad_approve",
                 "approve_is_default", "pr_title_control", "pr_title_secret", "long_pr_title"]
        codes += [f"missing_{key}" for key in ("at", "now", "changed", "next", "eta", "waiting", "repo", "target", "pr_title", "verify")] + [f"long_{key}" for key in ol.NOTICE_LIMITS]
        for code in codes:
            self.assertIn(code, ol.PROBLEMS, code)
            text = ol.problem_text(code)
            self.assertTrue(text and "\n" not in text and "알 수 없는 문제" not in text, code)
        self.assertIn(f"R-{ol.NOTICE_NO_REQUIRED_FROM_R}", ol.problem_text("no_required"))


class ValidatorNoticeTest(unittest.TestCase):
    def errors(self, files):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, text in files.items():
                path = root / ol.REQUEST_DIR / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8", newline="\n")
            return vr.check_request_files(root, sorted(f"{ol.REQUEST_DIR}/{name}" for name in files))

    def test_good_files_of_all_three_types_pass(self):
        files = {name_of(166): notice_text(number=166, no="P001"), name_of(167): notice_text(number=167, no="M001"),
                 name_of(168): notice_text(number=168, no="001", kind="decision", summary="무엇을 할까요"), name_of(169): notice_text(number=169, no="002", kind="run", fields={})}
        self.assertEqual(self.errors(files), [])

    def test_the_same_notice_number_in_two_files_is_an_error_even_with_different_request_numbers(self):
        for no, kind in (("P012", "info"), ("M012", "merge"), ("012", "decision")):
            found = self.errors({name_of(166): notice_text(number=166, no=no, kind=kind), name_of(167, "b"): notice_text(number=167, no=no, kind=kind)})
            self.assertEqual(len(found), 1, no)
            self.assertEqual((found[0].check, found[0].level, found[0].path), ("REQ-1", "ERROR", f"{ol.REQUEST_DIR}/{name_of(167, 'b')}"))
            self.assertIn(f"알림 번호 {no} 가 {ol.REQUEST_DIR}/{name_of(166)} 와 같습니다", found[0].message)
            self.assertIn("next_notice_no.py", found[0].message)

    def test_the_three_types_count_independently_so_p012_m012_and_012_may_coexist(self):
        files = {name_of(166): notice_text(number=166, no="P012"), name_of(167): notice_text(number=167, no="M012"),
                 name_of(168): notice_text(number=168, no="012", kind="decision", summary="x")}
        self.assertEqual(self.errors(files), [])

    def test_a_request_number_clash_is_still_an_error_and_is_separate_from_the_notice_number(self):
        found = self.errors({name_of(166): notice_text(number=166, no="P001"), name_of(166, "b"): notice_text(number=166, no="P002")})
        self.assertEqual(len(found), 1)
        self.assertIn("요청 번호 R-166 가", found[0].message)

    def test_zero_padded_four_digit_numbers_are_a_shape_error_so_they_cannot_dodge_the_duplicate_rule(self):
        """수정 1차(V2 M1): `P0012`·`0003` 은 `P012`·`003` 과 같은 값이라 통과시키면 문자열 비교인 '유형별 중복 금지'를 피해 간다 — 번호 모양 오류로 거절한다."""
        for no, kind in (("P0012", "info"), ("M0007", "merge"), ("0003", "decision"), ("0003", "confirm"), ("0003", "run"), ("P0001", "info"), ("0999", "decision"), ("M0100", "merge")):
            found = self.errors({name_of(170): notice_text(number=170, no=no, kind=kind)})
            self.assertEqual([(f.check, f.level, f.message) for f in found], [("REQ-1", "ERROR", ol.problem_text("bad_no"))], (no, kind))
        found = self.errors({name_of(170): notice_text(number=170, no="P012"), name_of(171): notice_text(number=171, no="P0012")})
        self.assertEqual([(f.check, f.path) for f in found], [("REQ-1", f"{ol.REQUEST_DIR}/{name_of(171)}")])
        found = self.errors({name_of(172): notice_text(number=172, no="003"), name_of(173): notice_text(number=173, no="0003")})
        self.assertEqual([(f.check, f.path) for f in found], [("REQ-1", f"{ol.REQUEST_DIR}/{name_of(173)}")])
        self.assertIn("앞에 0 을 더 붙인", ol.problem_text("bad_no"))
        request = ol.parse_request(name_of(170), notice_text(number=170, no="P0012"), strict=False)       # 런타임은 알림을 잃지 않으려고 옛 모양(제목·요약)으로 보낸다
        self.assertEqual((request.no, request.notice_error), ("", "bad_no"))

    def test_files_before_the_start_number_pass_in_their_old_shape_and_after_it_need_the_number(self):
        start = ol.NOTICE_NO_REQUIRED_FROM_R
        self.assertEqual(self.errors({name_of(1): request_text(id="R-001"), name_of(165): request_text(id="R-165", kind="decision")}), [])
        found = self.errors({name_of(start): request_text(id=f"R-{start:03d}")})
        self.assertEqual([(f.check, f.level) for f in found], [("REQ-1", "ERROR")])
        self.assertEqual(found[0].message, ol.problem_text("no_required"))
        self.assertEqual(found[0].path, f"{ol.REQUEST_DIR}/{name_of(start)}")

    def test_every_new_problem_is_a_one_line_error_with_its_sentence(self):
        cases = {"bad_no": notice_text(no="P1"), "no_kind_mismatch": notice_text(no="M001", kind="info"), "missing_now": notice_text(drop=("now",)),
                 "foreign_key": notice_text(fields={**PROGRESS, "repo": "a/b"}), "bad_at": notice_text(fields={**PROGRESS, "at": "x"}), "bad_work": notice_text(work="r1"),
                 "long_now": notice_text(fields={**PROGRESS, "now": "가" * 201}), "pr_title_control": notice_text(no="M001", fields={**MERGE, "pr_title": "a\u200bb"}),
                 "long_pr_title": notice_text(no="M001", fields={**MERGE, "pr_title": "가" * 201}), "bad_options": notice_text(no="001", kind="decision", fields={"options": "하나"}),
                 "approve_is_default": notice_text(no="001", kind="decision", fields={"options": "가 / 나", "default": "1", "approve": "1"})}
        for code, text in cases.items():
            found = self.errors({name_of(166): text})
            self.assertEqual(len(found), 1, (code, [f.line() for f in found]))
            self.assertEqual((found[0].check, found[0].level, found[0].message), ("REQ-1", "ERROR", ol.problem_text(code)), code)
            self.assertEqual(len(found[0].line().splitlines()), 1)
            self.assertNotIn("::", found[0].message)

    def test_the_real_repository_request_folder_passes(self):
        self.assertEqual([f.line() for f in vr.check_request_files(ROOT, vr.list_files(ROOT))], [])

    def test_a_hundred_and_sixty_five_old_shaped_files_all_pass_unchanged(self):
        """R-001~R-165 의 옛 모양(kind 다섯 가지·urgency·pr·created 조합)을 그대로 만들어 검증기에 넣는다 — 하나도 걸리지 않는다."""
        files, kinds = {}, ("merge", "info", "decision", "run", "confirm")
        for number in range(1, 166):
            kind = kinds[number % 5]
            files[name_of(number, f"old-{number}")] = request_text(id=f"R-{number:03d}", kind=kind, title=f"[R-{number:03d}] 옛 요청 {number}", summary="옛 모양의 요약입니다",
                                                                  urgency=("급함" if number % 7 == 0 else None), pr=(str(number) if number % 11 == 0 else None), created="2026-10-28")
        self.assertEqual(self.errors(files), [])

    def test_the_old_files_of_the_request_branch_all_pass_when_the_branch_is_available(self):
        """요청 전용 가지(`origin/ai/claude/desktop-bootstrap-merge`)가 이 저장소에 있으면 그 가지의 옛 요청 파일(번호가 상수 `NOTICE_NO_REQUIRED_FROM_R` 미만인 것)을 전부 새 REQ-1 에 넣는다.
        이 시험은 **가변 외부 상태**(원격 가지의 내용)에 기댄다 — 가지가 없거나 옛 파일이 100개 이하로 적으면(얕은 복제·가지 정리) 실패시키지 않고 **건너뛴다**(수정 1차, V2 L7).
        주의: CI(`guardrails.yml`)의 checkout 이 `fetch-depth: 0` 이라 그 가지가 원격에 있으면 CI 에서도 돈다(건너뛰는 것은 가지가 없거나 줄었을 때뿐이다)."""
        ref = "origin/ai/claude/desktop-bootstrap-merge"
        probe = subprocess.run(["git", "rev-parse", "--verify", "--quiet", ref], cwd=str(ROOT), capture_output=True)
        if probe.returncode != 0:
            self.skipTest("요청 전용 가지가 이 저장소에 없다")
        listing = subprocess.run(["git", "ls-tree", "-r", "-z", "--name-only", ref, "--", ol.REQUEST_DIR], cwd=str(ROOT), capture_output=True).stdout.decode("utf-8").split("\0")
        names = [path.rsplit("/", 1)[-1] for path in listing if path and ol.REQUEST_NAME_RE.fullmatch(path.rsplit("/", 1)[-1])]
        wanted = [name for name in names if int(name[2:5]) < ol.NOTICE_NO_REQUIRED_FROM_R]
        if len(wanted) <= 100:
            self.skipTest(f"요청 전용 가지의 옛 요청 파일이 {len(wanted)}개뿐이라 건너뛴다(100개 넘게 있어야 이 시험이 뜻이 있다 — 가지가 잘렸거나 정리됐다)")
        batch = "".join(f"{ref}:{ol.REQUEST_DIR}/{name}\n" for name in wanted).encode("utf-8")
        done = subprocess.run(["git", "cat-file", "--batch"], cwd=str(ROOT), input=batch, capture_output=True).stdout
        files, position = {}, 0
        for name in wanted:
            header_end = done.index(b"\n", position)
            size = int(done[position:header_end].split()[2])
            files[name] = done[header_end + 1:header_end + 1 + size].decode("utf-8")
            position = header_end + 1 + size + 1
        found = self.errors(files)
        self.assertEqual([f.line() for f in found], [], "옛 요청 파일이 새 REQ-1 에서 걸렸다")


class RunNoticeRequestsTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.summary = self.tmp / "summary.md"

    def run_requests(self, files, **kwargs):
        env = requests_env(GITHUB_STEP_SUMMARY=str(self.summary))
        return oh.run_cli("requests", environ=env, runner=RequestGit.with_requests(files), root=self.tmp, **kwargs)

    def buttons(self, net, index=0):
        return [(item["text"], item["url"]) for item in net.bodies()[index]["reply_markup"]["inline_keyboard"][0]]

    def test_a_progress_file_is_sent_as_the_five_item_message_with_two_buttons(self):
        text = notice_text(no="P012", work="R-160", fields=dict(PROGRESS, check="이상 없음"))
        code, lines, net, _ = self.run_requests({name_of(166): text})
        self.assertEqual((code, net.calls), (0, 1))
        body = net.bodies()[0]
        self.assertEqual(body["parse_mode"], "HTML")
        self.assertEqual(body["text"], notify.format_notice("P012", dict(PROGRESS, check="이상 없음"), work="R-160"))
        self.assertEqual([label for label, _ in self.buttons(net)], ["요청 열기", "사용법"])
        self.assertEqual(lines, ["AI 요청 알림: R-166 을 알렸습니다 (알림 번호 P012)"])
        self.assertEqual(self.summary.read_text(encoding="utf-8").strip(), "### AI 요청 텔레그램 알림\n\n- R-166: 알렸습니다 (알림 번호 P012)")
        self.assertEqual(nh.leaks(*lines, body["text"], chat=False), [])

    def test_a_merge_file_is_sent_as_the_five_item_message_and_only_blog_pull_requests_get_a_pr_button(self):
        for repo, pr, labels in (("shine88pc/chanceblog-desktop", "57", ["요청 열기", "사용법"]), ("shine88pc/chanceblog", "57", ["요청 열기", "PR 열기", "사용법"]),
                                 ("shine88pc/chanceblog", None, ["요청 열기", "사용법"])):
            code, lines, net, _ = self.run_requests({name_of(166): notice_text(no="M007", pr=pr, fields={**MERGE, "repo": repo})})
            self.assertEqual((code, net.calls), (0, 1), repo)
            self.assertIn(notify.MERGE_MARK + " <b>M007 · 병합 요청</b>", net.bodies()[0]["text"])
            self.assertEqual([label for label, _ in self.buttons(net)], labels, (repo, pr))
            if "PR 열기" in labels:
                self.assertEqual(dict(self.buttons(net))["PR 열기"], "https://github.com/shine88pc/chanceblog/pull/57")

    def test_an_ask_file_gets_the_answer_button_first_and_it_opens_the_new_form(self):
        text = notice_text(no="003", kind="decision", summary="무엇을 할까요", fields=ASK, pr="57")
        code, lines, net, _ = self.run_requests({name_of(166): text})
        self.assertEqual((code, net.calls), (0, 1))
        buttons = self.buttons(net)
        self.assertEqual([label for label, _ in buttons], ["답하기", "요청 열기", "PR 열기", "사용법"])
        self.assertEqual(buttons[0][1], notify.NEW_ANSWER_URL)
        self.assertEqual(buttons[0][1], "https://github.com/shine88pc/chanceblog/issues/new?template=ai-answer.yml")
        for label, url in buttons:
            self.assertEqual(notify.allowed_url(url), url, label)
        self.assertEqual(net.bodies()[0]["text"], notify.format_notice("003", {**ASK, "summary": "무엇을 할까요"}, pr=57))

    def test_old_and_new_files_in_one_push_each_keep_their_own_message_shape(self):
        files = {name_of(165): request_text(id="R-165", kind="decision", title="옛 결정", summary="옛 요약"), name_of(166): notice_text(number=166, no="P012"),
                 name_of(167): notice_text(number=167, no="M007")}
        code, lines, net, _ = self.run_requests(files)
        self.assertEqual((code, net.calls), (0, 3))
        texts = [body["text"] for body in net.bodies()]
        self.assertEqual(texts[0], notify.format_ai_request("R-165", "decision", "옛 결정", "옛 요약"))
        self.assertTrue(texts[0].splitlines()[0].startswith(f"{notify.BELL_MARK} <b>AI 요청 r165 · 결정 부탁</b>"))
        self.assertIn("진행 현황", texts[1])
        self.assertIn("병합 요청", texts[2])
        self.assertEqual([label for label, _ in self.buttons(net, 0)], ["요청 열기", "답하기", "사용법"])               # 옛 파일의 버튼은 옛 그대로
        self.assertEqual(dict(self.buttons(net, 0))["답하기"], notify.NEW_ISSUE_URL)

    def test_the_overflow_line_goes_on_the_last_message_in_the_new_shape_too(self):
        files = {name_of(166 + index): notice_text(number=166 + index, no=f"P{index + 1:03d}") for index in range(5)}
        code, lines, net, _ = self.run_requests(files)
        self.assertEqual(net.calls, 3)
        texts = [body["text"] for body in net.bodies()]
        self.assertIn("… 외 2건", texts[2])
        self.assertNotIn("… 외", texts[0] + texts[1])

    def test_a_bad_notice_part_is_sent_in_the_old_shape_with_the_reason_in_the_log_and_a_warning(self):
        files = {name_of(166): notice_text(number=166, no="P012", drop=("now",), title="[R-166] 진행 현황", summary="요약 글")}
        code, lines, net, _ = self.run_requests(files)
        self.assertEqual((code, net.calls), (0, 1))
        self.assertEqual(net.bodies()[0]["text"], notify.format_ai_request("R-166", "info", "[R-166] 진행 현황", "요약 글"))
        self.assertEqual([label for label, _ in self.buttons(net)], ["요청 열기", "답하기", "사용법"])
        self.assertIn(f"AI 요청 알림: {name_of(166)} 의 알림 칸이 맞지 않아 옛 모양(제목·요약)으로 보냅니다 — {ol.problem_text('missing_now')}", lines)
        self.assertIn("AI 요청 알림: R-166 을 알렸습니다", lines)
        self.assertEqual(lines[-1], ol.NOTICE_FALLBACK_WARNING)
        self.assertTrue(ol.NOTICE_FALLBACK_WARNING.startswith("::warning::"))

    def test_a_pr_title_that_cannot_be_shown_exactly_is_not_sent_and_the_rest_still_go(self):
        files = {name_of(166): notice_text(number=166, no="M001", fields={**MERGE, "pr_title": "[R-1] " + "AIza" + "x" * 35}), name_of(167): notice_text(number=167, no="M002")}
        code, lines, net, _ = self.run_requests(files)
        self.assertEqual((code, net.calls), (0, 1))
        self.assertIn("M002", net.bodies()[0]["text"])
        failed = [line for line in lines if "R-166 을 보내지 못했습니다" in line]
        self.assertEqual(len(failed), 1)
        self.assertIn("PR 제목", failed[0])
        self.assertEqual(lines[-1], ol.REQUEST_WARNING_LINE)
        self.assertIn("보내지 못했습니다(refused)", self.summary.read_text(encoding="utf-8"))
        self.assertNotIn("AIza", "\n".join(lines) + net.bodies()[0]["text"])

    def test_the_pr_title_arrives_on_the_phone_exactly_as_it_was_written_in_the_file(self):
        rng = random.Random(1106)
        alphabet = list("abcXYZ019 []()'\"<>&@#:/._-—·+*=%$!?,;~^|") + list("한글제목병합") + ["😀", "✅", "→", "R-160", "https://", "[R-1] ", "@", "://", " — ", "&amp;", "<code>"]
        checked = 0
        while checked < 60:
            title = "[R-160] " + "".join(rng.choice(alphabet) for _ in range(rng.randint(1, 50)))
            title = title.strip()
            if notify.pr_title_problem(title, limit=notify.PR_TITLE_LIMIT) or title[0] in "\"'":
                continue
            code, lines, net, _ = self.run_requests({name_of(166): notice_text(no="M007", fields={**MERGE, "pr_title": title})})
            text = net.bodies()[0]["text"]
            inner = re.search(r"^PR 제목: <code>(.*)</code>$", text, re.M | re.S).group(1)
            self.assertEqual(html.unescape(inner), title, repr(title))
            checked += 1

    def test_a_title_the_ai_wrote_with_a_trailing_hash_comment_look_stays_a_title(self):
        title = "[R-160] 제목 # 이것도 제목"
        code, lines, net, _ = self.run_requests({name_of(166): notice_text(no="M007", fields={**MERGE, "pr_title": title})})
        self.assertIn(f"<code>{title}</code>", net.bodies()[0]["text"])

    def test_without_secrets_nothing_is_sent_and_new_files_change_nothing_about_that(self):
        def refuse(*args, **kwargs):
            raise AssertionError("시크릿이 없으면 git 도 부르지 않는다")
        code, lines, net, _ = oh.run_cli("requests", environ=requests_env(telegram=False), runner=refuse, root=self.tmp)
        self.assertEqual((code, lines, net.calls), (0, [ol.REQUESTS_SKIP_LINE], 0))


class DuplicateNoticeNumberTest(unittest.TestCase):
    """알림 실행이 새 파일의 알림 번호를 다른 원격 가지의 **다른** 요청 파일이 쓰고 있으면 로그에 한 줄과 경고를 남긴다(알림은 그대로 간다 — 막지 않는다)."""

    REFS = ["refs/remotes/origin/HEAD", "refs/remotes/origin/main", "refs/remotes/origin/ai/claude/other-1", "refs/remotes/origin/ai/claude/operator-loop"]

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def run_with(self, files, **git_kwargs):
        git = nth.NoticeGit(tree=oh.paths(*files), files=files, **git_kwargs)
        code, lines, net, _ = oh.run_cli("requests", environ=requests_env(), runner=git, root=self.tmp)
        return code, lines, net, git

    def test_the_same_number_in_another_file_on_another_branch_is_logged_but_the_alert_goes(self):
        files = {name_of(170, "mine"): notice_text(number=170, no="P012")}
        holders = [("refs/remotes/origin/ai/claude/other-1", f"{ol.REQUEST_DIR}/{name_of(169, 'theirs')}", "no: P012")]
        code, lines, net, git = self.run_with(files, refs=self.REFS, holders=holders)
        self.assertEqual((code, net.calls), (0, 1))
        self.assertEqual(lines[0], "AI 요청 알림: R-170 을 알렸습니다 (알림 번호 P012)")
        self.assertEqual(lines[1], ol.NOTICE_DUPLICATE_LINE.format(no="P012", names=name_of(169, "theirs")))
        self.assertEqual(lines[2], ol.NOTICE_DUPLICATE_WARNING)
        self.assertTrue(ol.NOTICE_DUPLICATE_WARNING.startswith("::warning::"))

    def test_the_same_file_on_another_branch_and_other_numbers_are_not_a_clash(self):
        files = {name_of(170, "mine"): notice_text(number=170, no="P012")}
        holders = [("refs/remotes/origin/ai/claude/other-1", f"{ol.REQUEST_DIR}/{name_of(170, 'mine')}", "no: P012"),      # 같은 파일(이 가지에서 만든 가지)
                   ("refs/remotes/origin/ai/claude/other-1", f"{ol.REQUEST_DIR}/{name_of(168, 'x')}", "no: P0123"),        # 다른 번호(앞부분만 같다)
                   ("refs/remotes/origin/main", f"{ol.REQUEST_DIR}/{name_of(167, 'y')}", "no: M012")]                      # 다른 유형
        code, lines, net, git = self.run_with(files, refs=self.REFS, holders=holders)
        self.assertEqual(lines, ["AI 요청 알림: R-170 을 알렸습니다 (알림 번호 P012)"])

    def test_quoted_forms_and_every_clash_are_found_up_to_the_name_limit(self):
        files = {name_of(170, "mine"): notice_text(number=170, no="003", kind="decision", summary="x", fields={})}
        ref = "refs/remotes/origin/ai/claude/other-1"
        holders = [(ref, f"{ol.REQUEST_DIR}/{name_of(100 + index, 'dup')}", line) for index, line in enumerate(['no: "003"', "no: '003'", "no: 003", 'no:  "003"  ', 'no: "003"', "no: 003", "no: 003"])]
        code, lines, net, git = self.run_with(files, refs=self.REFS, holders=holders)
        shown = lines[1].split("(", 1)[1].rsplit(")", 1)[0].split(", ")
        self.assertEqual(len(shown), ol.MAX_DUPLICATE_NAMES)
        self.assertEqual(shown, sorted(shown))

    def test_the_search_pattern_matches_exactly_the_front_matter_value(self):
        files = {name_of(170, "mine"): notice_text(number=170, no="M007")}
        code, lines, net, git = self.run_with(files, refs=self.REFS)
        [call] = git.grep_calls()
        self.assertEqual(call[:5], ["git", "grep", "-l", "-z", "-E"])
        pattern = call[call.index("-e") + 1]
        for line in ("no: M007", 'no: "M007"', "no: 'M007'", "no:  M007 "):
            self.assertIsNotNone(re.search(pattern, line), line)
        for line in ("no: M0070", "no: M07", "no: P007", "now: M007", "my no: M007", "no: M007 x"):
            self.assertIsNone(re.search(pattern, line), line)
        self.assertEqual(call[call.index("--") - 3:], ["refs/remotes/origin/main", "refs/remotes/origin/ai/claude/other-1", "refs/remotes/origin/ai/claude/operator-loop"] + ["--", ol.REQUEST_DIR])
        self.assertNotIn("refs/remotes/origin/HEAD", call)

    def test_many_branches_are_searched_in_groups(self):
        refs = [f"refs/remotes/origin/ai/claude/b{index}" for index in range(95)]
        files = {name_of(170, "mine"): notice_text(number=170, no="P012")}
        code, lines, net, git = self.run_with(files, refs=refs)
        self.assertEqual(len(git.grep_calls()), 3)
        self.assertEqual(sum(call.index("--") - call.index("-e") - 2 for call in git.grep_calls()), 95)

    def test_a_git_failure_is_silent_and_never_blocks_the_alert(self):
        files = {name_of(170, "mine"): notice_text(number=170, no="P012")}
        for broken in ("for-each-ref", "grep"):
            holders = [("refs/remotes/origin/main", f"{ol.REQUEST_DIR}/{name_of(169, 'theirs')}", "no: P012")]
            code, lines, net, git = self.run_with(files, refs=self.REFS, holders=holders, broken={broken})
            self.assertEqual((code, net.calls, lines), (0, 1, ["AI 요청 알림: R-170 을 알렸습니다 (알림 번호 P012)"]), broken)

    def test_a_clash_is_checked_for_every_numbered_file_and_never_for_old_files(self):
        files = {name_of(165): request_text(id="R-165", kind="decision"), name_of(170, "a"): notice_text(number=170, no="P012"), name_of(171, "b"): notice_text(number=171, no="M003")}
        holders = [("refs/remotes/origin/main", f"{ol.REQUEST_DIR}/{name_of(160, 'old')}", "no: M003")]
        code, lines, net, git = self.run_with(files, refs=self.REFS, holders=holders)
        self.assertEqual(len(git.grep_calls()), 2)                                  # 번호 있는 두 파일만
        self.assertEqual([line for line in lines if "겹쳤" in line], [ol.NOTICE_DUPLICATE_LINE.format(no="M003", names=name_of(160, "old")), ol.NOTICE_DUPLICATE_WARNING])
        self.assertEqual(net.calls, 3)

    def test_a_request_with_only_old_files_runs_no_extra_git_command(self):
        git = nth.NoticeGit.with_requests({name_of(1): request_text(id="R-001")})
        code, lines, net, _ = oh.run_cli("requests", environ=requests_env(), runner=git, root=self.tmp)
        self.assertEqual(lines, ["AI 요청 알림: R-001 을 알렸습니다"])
        self.assertEqual([args[1] for args, _ in git.calls if args[1] in ("for-each-ref", "grep")], [])


class NoticeButtonsTest(unittest.TestCase):
    def request(self, no, kind, pr=None, repo=None):
        fields = {"repo": repo} if repo else {}
        return ol.Request("R-166", kind, "t", "s", "보통", pr, "", name_of(166), no, "", tuple(fields.items()), "")

    def labels(self, request):
        return [label for label, _ in ol.request_buttons(request, "ai/claude/x", "main")]

    def test_the_buttons_of_each_type(self):
        self.assertEqual(self.labels(self.request("P012", "info")), ["요청 열기", "사용법"])
        self.assertEqual(self.labels(self.request("M007", "merge", repo=ol.BLOG_REPO)), ["요청 열기", "사용법"])
        self.assertEqual(self.labels(self.request("003", "decision")), ["답하기", "요청 열기", "사용법"])
        self.assertEqual(self.labels(self.request("003", "run", pr=5)), ["답하기", "요청 열기", "PR 열기", "사용법"])
        self.assertEqual(self.labels(ol.Request("R-001", "merge", "t", "s", "보통", 5, "", name_of(1))), ["요청 열기", "PR 열기", "답하기", "사용법"])         # 옛 모양 그대로

    def test_a_pr_button_for_a_merge_request_exists_only_for_this_blog_repository(self):
        self.assertIn("PR 열기", self.labels(self.request("M007", "merge", pr=5, repo=ol.BLOG_REPO)))
        for repo in ("shine88pc/chanceblog-desktop", "other/chanceblog", "shine88pc/chanceblog2", ""):
            self.assertNotIn("PR 열기", self.labels(self.request("M007", "merge", pr=5, repo=repo)), repo)
        self.assertEqual(ol.BLOG_REPO, "shine88pc/chanceblog")

    def test_the_answer_button_of_an_ask_is_the_new_form_and_the_old_chooser_is_for_old_files_only(self):
        buttons = dict(ol.request_buttons(self.request("003", "decision"), "ai/claude/x", "main"))
        self.assertEqual(buttons["답하기"], notify.NEW_ANSWER_URL)
        self.assertEqual(notify.allowed_url(notify.NEW_ANSWER_URL), notify.NEW_ANSWER_URL)
        old = dict(ol.request_buttons(ol.Request("R-001", "decision", "t", "s", "보통", None, "", name_of(1)), "ai/claude/x", "main"))
        self.assertEqual(old["답하기"], notify.NEW_ISSUE_URL)
        self.assertNotIn("ai-answer", notify.NEW_ISSUE_URL)


def code_blocks(text, language):
    return re.findall(r"```" + language + r"\n(.*?)```", text, re.S)


def plain_phone(message):
    return html.unescape(re.sub(r"</?(?:b|code)>", "", message))


class DocsAgreeWithCodeTest(unittest.TestCase):
    """문서의 예시·표가 코드와 어긋나지 않는지 — 요청함 README 의 번호 있는 예시는 검증기를 그대로 통과하고, 문서에 실린 폰 글은 notify.format_notice 의 출력과 글자 그대로 같다."""

    def read(self, rel):
        return (ROOT / rel).read_text(encoding="utf-8")

    def numbered_examples(self):
        readme = self.read(ol.REQUEST_DIR + "/README.md")
        found = []
        for example in code_blocks(readme, "markdown"):
            if not example.startswith("---\n"):
                continue
            number = re.search(r"^id: (R-[0-9]{3})$", example, re.M).group(1)
            request = ol.parse_request(f"{number}_example.md", example, strict=True)
            found.append(request)
        return found

    def test_every_request_file_example_in_the_readme_passes_the_strict_parser(self):
        examples = self.numbered_examples()
        self.assertGreaterEqual(len(examples), 4)
        self.assertEqual(sorted(request.no for request in examples if request.no), ["003", "M007", "P012"])
        self.assertEqual(sorted(request.kind for request in examples if request.no), ["decision", "info", "merge"])

    def test_the_phone_texts_in_the_readme_and_in_the_guide_are_what_the_code_sends(self):
        readme_blocks = code_blocks(self.read(ol.REQUEST_DIR + "/README.md"), "text")
        guide_blocks = code_blocks(self.read(ol.GUIDE_PATH), "text")
        for request in self.numbered_examples():
            if not request.no:
                continue
            message = plain_phone(notify.format_notice(request.no, dict(request.fields), urgency=request.urgency, work=request.work, pr=request.pr))
            self.assertIn(message + "\n", readme_blocks, request.no)
            self.assertIn(message + "\n", guide_blocks, request.no)

    def test_the_documents_name_the_new_rules_where_the_operator_and_the_ai_look(self):
        security = self.read("docs/SECURITY_GUARDRAILS.md")
        row = next(line for line in security.splitlines() if line.startswith("| G-S9 |"))
        for needle in ("대상번호", "`approve`", "확인함", "`ai-answer.yml`", "폰으로도 회신"):
            self.assertIn(needle, row, needle)
        req = next(line for line in security.splitlines() if line.startswith("| REQ-1 |"))
        for needle in ("`no`", "`pr_title`", "같은 알림 번호의 파일이 둘이면 오류", "`NOTICE_NO_REQUIRED_FROM_R`", "`default`≠`approve`", "`P0012`"):
            self.assertIn(needle, req, needle)
        form = next(line for line in security.splitlines() if line.startswith("| FORM-1 |"))
        for needle in ("`ai-answer.yml`", "(이전 R 번호용)", "`선택 안 함`"):
            self.assertIn(needle, form, needle)
        for rel in ("docs/AGENT_RUNBOOK.md", ol.REQUEST_DIR + "/README.md", "인수인계/도구/README.md"):
            self.assertIn("next_notice_no.py", self.read(rel), rel)
        self.assertIn("알림 번호(TG-STD", self.read("인수인계/작업내용.md"))

    def test_the_architecture_section_lists_every_design_decision_in_order(self):
        architecture = self.read("docs/ARCHITECTURE.md")
        section = architecture[architecture.index("## 4-6-2."):architecture.index("## 4-7.")]
        numbers = [int(match) for match in re.findall(r"^\| TS-([0-9]+) \|", section, re.M)]
        self.assertEqual(numbers, list(range(1, 26)))
        for needle in ("`NOTICE_NO_REQUIRED_FROM_R`", "REFUSED", "NOTICE_FALLBACK_WARNING", "next_notice_no.py", "대상번호만 올린 답은 '확인함'이고 승인이 아니다", "강제 푸시"):
            self.assertIn(needle, section, needle)

    def test_the_documents_point_at_the_start_number_constant_by_name_and_never_state_its_number(self):
        """수정 1차(TS-23)·수정 2차(V2 N1): 상수 `NOTICE_NO_REQUIRED_FROM_R` 의 숫자는 코드(`operator_loop.py` 한 줄)에만 있다. 병합 직전에 코디네이터가 값을 올릴 때 문서 여러 곳을 같이 고치다 틀리지 않게
        문서는 이름으로만 가리킨다. 값을 올린 뒤에는 `test_notice_requests`·`test_operator_loop_docs` 만 다시 돌리면 된다. 이 시험이 보는 것은 두 가지로 나뉜다:
        ① **상수 이름 바로 뒤의 숫자**(`NOTICE_NO_REQUIRED_FROM_R`=169·`(171)` 꼴 — 낡은 값)는 규칙을 설명하는 문서와 AI 가 늘 고쳐 쓰는 문서(작업내용·WORKLOG) **모두** 없어야 한다.
        ② **낡은 경계 표기**(`R-168 부터`·`R-170 이상`·`R-001~R-168`)는 **규칙을 설명하는 문서(README·ARCHITECTURE·AGENT_RUNBOOK·SECURITY_GUARDRAILS)와 코드**에만 적용한다 —
        `작업내용.md`·WORKLOG 에는 적용하지 않는다: 거기에는 '새 체계는 R-171 부터'·'R-165~R-168 은 기본값으로 진행'·'R-170 이상 파일' 같은 자연스러운 글이 늘 들어가므로 상수 값과 무관하게
        그런 글이 걸려 CI 가 빨개지면 안 된다(재검증 V2 N1 — 상수를 171 로 올린 복사본에 그 문장을 붙이면 예전 시험은 실패했다)."""
        names = (ol.REQUEST_DIR + "/README.md", "docs/ARCHITECTURE.md", "docs/AGENT_RUNBOOK.md", "docs/SECURITY_GUARDRAILS.md")       # 규칙을 설명하는 문서
        code = {rel: self.read(rel) for rel in ("scripts/validate_repo.py", "pipeline/operator_loop.py")}
        rules = {rel: self.read(rel) for rel in names}
        worklog = self.read("WORKLOG.md")
        head = worklog.index("## [2026-11-06] Claude – TG-STD")
        living = {"인수인계/작업내용.md": self.read("인수인계/작업내용.md"), "WORKLOG.md(TG-STD 항목)": worklog[head:worklog.index("\n## [", head + 1)]}                # 늘 고쳐 쓰는 문서
        for rel, text in {**rules, **living, "scripts/validate_repo.py": code["scripts/validate_repo.py"]}.items():
            self.assertEqual(re.findall(r"NOTICE_NO_REQUIRED_FROM_R[`)\s=(]*[0-9]{3}", text), [], f"{rel}: 상수 이름 뒤에 숫자를 적지 않는다")
        for rel, text in {**rules, **code}.items():
            self.assertEqual(re.findall(r"R-1[6-9][0-9](?:~|\s*부터|\s*이상)", text), [], f"{rel}: 낡은 경계 표기")
            self.assertEqual(re.findall(r"R-001~R-1[5-9][0-9]", text), [], f"{rel}: 낡은 옛 파일 범위 표기")
        for rel in names:
            self.assertIn("NOTICE_NO_REQUIRED_FROM_R", rules[rel], rel)
        source = self.read("pipeline/operator_loop.py")
        self.assertEqual(len(re.findall(r"^NOTICE_NO_REQUIRED_FROM_R\s*=\s*[0-9]+", source, re.M)), 1)       # 코드에서도 정의는 한 곳

    def test_the_workflows_still_run_the_same_one_line_commands(self):
        """워크플로 파일은 이 변경의 범위 밖이다(S0) — 실행 한 줄이 그대로 `python -m pipeline.operator_loop requests|ack` 이다."""
        self.assertIn("run: python -m pipeline.operator_loop requests", self.read(".github/workflows/ai-request.yml"))
        self.assertIn("run: python -m pipeline.operator_loop ack", self.read(".github/workflows/operator-reply.yml"))
        self.assertEqual(notify.ALLOWED_URLS, (("shine88pc.github.io", "/"), ("github.com", "/shine88pc/chanceblog"), ("www.blogger.com", "/")))


if __name__ == "__main__":
    unittest.main()
