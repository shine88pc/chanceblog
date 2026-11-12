"""병합완료 확인(`kind: merged`)의 요청 파일 읽기(parse_request)·검증기 REQ-1(짝·중복)·알림 보내기(run_requests)·번호 도구 시험, 그리고 **다른 종류는 이 변경 전과 같다**는 골든 비교
(pipeline/operator_loop.py·scripts/validate_repo.py·인수인계/도구/work/next_notice_no.py — 운영자 요청 2026-11-12). 폰 글 자체의 시험은 test_merged_notice.py.
네트워크·실제 텔레그램·실제 GitHub 는 없다(가짜 git·가짜 HTTP).
"""
import hashlib
import random
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import _bootstrap
import merged_golden_data as golden
import merged_golden_tools as tools
import notice_helpers as nth
import operator_loop_helpers as oh
from merged_helpers import BLOB, SUMMARY_BAD, buttons_of, merge_text, merged_name, merged_text, req_errors, run_requests
from notice_helpers import name_of, notice_text, parse
from pipeline import notify
from pipeline import operator_loop as ol

ROOT = _bootstrap.ROOT
sys.path.insert(0, str(ROOT / "인수인계" / "도구" / "work"))
import next_notice_no as nn  # noqa: E402
import notice_tools as nt  # noqa: E402

OTHER_KINDS = ("info", "merge", "decision", "confirm", "run")
FOREIGN_LINES = {"urgency": "urgency: 보통", "pr": "pr: 57", "work": "work: R-160", "at": "at: 2026-11-12 08:00", "now": "now: 지금", "changed": "changed: 없음", "next": "next: 다음",
                 "eta": "eta: 곧", "waiting": "waiting: 없음", "check": "check: 이상 없음", "repo": "repo: a/b", "target": "target: 대상", "pr_title": "pr_title: [M050] 제목",
                 "verify": "verify: 검증", "state": "state: 승인 대기", "options": "options: 가 / 나", "default": "default: 1", "approve": "approve: 2"}


def problem(text, strict, number=266):
    """요청 파일 글 하나의 문제 코드 — strict=True 는 검증기(REQ-1)의 읽기, False 는 런타임의 읽기(알림 칸 문제는 notice_error 로 나온다). 문제가 없으면 빈 글."""
    try:
        request = ol.parse_request(name_of(number, "merged-m050"), text, strict=strict)
    except ol.RequestError as exc:
        return exc.code
    return request.notice_error


class ParseMergedTest(unittest.TestCase):
    def test_a_good_normal_file_reads_into_the_request_in_both_modes(self):
        for strict in (True, False):
            request = ol.parse_request(merged_name(), merged_text(), strict=strict)
            self.assertEqual(request, ol.Request("R-266", "merged", "[M050] 병합완료 확인 - 정상", "정상", "보통", None, "2026-11-12", merged_name(), "M050", "",
                                                 (("result", "정상"), ("summary", "정상")), ""), strict)

    def test_a_good_abnormal_file_keeps_the_reason_as_a_field(self):
        request = ol.parse_request(merged_name(), merged_text(result="이상"), strict=True)
        self.assertEqual((request.kind, request.no, request.work, request.notice_error), ("merged", "M050", "", ""))
        self.assertEqual(dict(request.fields), {"result": "이상", "summary": SUMMARY_BAD})
        self.assertEqual(request.title, "[M050] 병합완료 확인 - 이상")

    def test_the_created_date_is_optional_and_checked_like_the_others(self):
        self.assertEqual(ol.parse_request(merged_name(), merged_text(drop=("created",)), strict=True).created, "")
        for bad in ("x", "2026-13-40", "2026/11/12"):
            self.assertEqual(problem(merged_text(created=bad), True), "bad_created", bad)

    def test_the_number_must_be_the_standard_merge_request_number(self):
        for good in ("M001", "M050", "M999", "M1000", "M9999"):
            for strict in (True, False):
                self.assertEqual(problem(merged_text(no=good), strict), "", (good, strict))
        for bad in ("M50", "M0500", "M000", "M10000", "m050", "M 050", "M050 x", "M-050", "R-050", "①②③", "", "MM050", "M０５０"):
            for strict in (True, False):
                self.assertEqual(problem(merged_text(no=bad), strict), "bad_no", (bad, strict))

    def test_a_number_of_another_type_is_a_kind_mismatch_so_only_merge_and_merged_use_m(self):
        for wrong in ("P012", "012", "003", "1000", "P1000"):
            for strict in (True, False):
                self.assertEqual(problem(merged_text(no=wrong, title=f"[{wrong}] 병합완료 확인 - 정상"), strict), "no_kind_mismatch", (wrong, strict))
        for kind in ("info", "decision", "confirm", "run"):                                        # 거꾸로: 다른 종류가 M 을 쓰는 길은 그대로 막혀 있다
            for strict in (True, False):
                text = notice_text(no="M050", kind=kind, fields=nth.BODY_OF["M" if kind == "info" else ""])
                self.assertEqual(problem(text, strict, 166), "no_kind_mismatch", (kind, strict))

    def test_the_number_is_always_needed_whatever_the_request_number(self):
        for number in (1, 100, 172, 173, 266, 999):
            for strict in (True, False):
                self.assertEqual(problem(merged_text(number=number, drop=("no",)), strict, number), "no_required", (number, strict))

    def test_the_result_is_one_of_the_two_words(self):
        for good in ("정상", "이상"):
            self.assertEqual(problem(merged_text(result=good), True), "", good)
        for bad in ("OK", "ok", "정상 확인", "정상함", "Normal", "정", "0", "true", "이상 있음", "성공"):
            for strict in (True, False):
                self.assertEqual(problem(merged_text(result=bad, title="[M050] 병합완료 확인 - 정상"), strict), "bad_result", (bad, strict))
        for blank in ("", "   ", chr(0x200B)):
            for strict in (True, False):
                self.assertEqual(problem(merged_text(result=blank), strict), "missing_result", (repr(blank), strict))
                self.assertEqual(problem(merged_text(result=None), strict), "missing_result", strict)

    def test_the_title_must_be_exactly_what_the_number_and_the_result_make(self):
        bad_titles = ("[M051] 병합완료 확인 - 정상", "[M050] 병합완료 확인 - 이상", "[M050]  병합완료 확인 - 정상", "[M050] 병합완료 확인 – 정상", "[M050] 병합완료 확인 -정상",
                      "[m050] 병합완료 확인 - 정상", "[M050] 병합완료 - 정상", "[M050] 병합완료", "병합완료 확인 - 정상", "[M050] 병합완료 확인 - 정상 (M050)", "[R-266] 병합완료 확인 - 정상", "x")
        for title in bad_titles:
            for strict in (True, False):
                self.assertEqual(problem(merged_text(title=title), strict), "merged_title_mismatch", (title, strict))
        for result in ("정상", "이상"):
            self.assertEqual(problem(merged_text(result=result, title=f'"[M050] 병합완료 확인 - {result}"'), True), "", result)          # 제목의 따옴표는 다른 종류처럼 벗겨 읽는다
        self.assertEqual(problem(merged_text(drop=("title",)), True), "missing_title")

    def test_every_key_outside_the_seven_is_refused_even_with_a_valid_value(self):
        self.assertEqual(set(FOREIGN_LINES), set(ol.REQUEST_KEYS) - set(ol.MERGED_ALLOWED))                      # 일곱 칸 밖의 알려진 칸 18개 전부
        for key, line in FOREIGN_LINES.items():
            for strict in (True, False):
                self.assertEqual(problem(merged_text(extra=[line]), strict), "foreign_key", (key, strict))

    def test_unknown_keys_are_ignored_at_run_time_and_refused_by_the_validator_like_everywhere_else(self):
        text = merged_text(extra=["owner: x"])
        self.assertEqual(problem(text, True), "unknown_key")
        self.assertEqual(problem(text, False), "")
        self.assertEqual(problem(merged_text(extra=["result: 이상"]), True), "duplicate_key")

    def test_the_summary_limits_are_enforced_only_by_the_validator(self):
        for result, limit in (("정상", 60), ("이상", 100)):
            ok = merged_text(result=result, summary="가" * limit)
            over = merged_text(result=result, summary="가" * (limit + 1))
            self.assertEqual(problem(ok, True), "", (result, limit))
            self.assertEqual(problem(over, True), "long_merged_summary", (result, limit))
            self.assertEqual(problem(over, False), "", (result, limit))                      # 런타임은 받고 폰에 실을 때 줄인다
        self.assertEqual(problem(merged_text(summary="가" * 301), True), "long_summary")      # 모든 종류의 300자 상한이 먼저다
        self.assertEqual(problem(merged_text(summary=None), True), "")
        self.assertEqual(problem(merged_text(summary=""), True), "missing_summary")

    def test_a_bad_merged_part_is_read_at_run_time_as_a_request_that_carries_no_text(self):
        """칸이 틀린 병합완료 확인 파일도 런타임에서는 읽힌다(알림을 잃지 않으려고) — 다만 제목·요약·번호·결과를 담지 않는다. 폰에는 요청 번호만 든 고정 문구가 간다(D1)."""
        request = ol.parse_request(merged_name(), merged_text(extra=["urgency: 급함"]), strict=False)
        self.assertEqual((request.kind, request.no, request.work, request.fields, request.notice_error), ("merged", "", "", (), "foreign_key"))
        self.assertEqual((request.id, request.title, request.summary, request.urgency, request.name), ("R-266", "", "", "급함", merged_name()))
        for result, summary in (("이상", "main 검사가 빨강입니다"), ("정상", "정상")):                          # 제목이 어긋난 파일(`- 정상` 인데 result 가 이상)도 글이 비어 돌아온다
            wrong = ol.parse_request(merged_name(), merged_text(result=result, summary=summary, title="[M050] 병합완료 확인 - 정상" if result == "이상" else "[M051] 병합완료 확인 - 정상"), strict=False)
            self.assertEqual((wrong.title, wrong.summary, wrong.no, wrong.fields, wrong.notice_error), ("", "", "", (), "merged_title_mismatch"), result)
        good = ol.parse_request(merged_name(), merged_text(result="이상"), strict=False)                        # 맞는 파일은 그대로 글을 담는다
        self.assertEqual((good.title, good.summary, good.notice_error), ("[M050] 병합완료 확인 - 이상", SUMMARY_BAD, ""))

    def test_the_other_kinds_keep_their_text_when_they_fall_back_at_run_time(self):
        """다른 종류의 런타임 폴백은 예전 그대로다 — 제목·요약을 담아 옛 모양으로 보낸다(이 변경은 병합완료 확인만 바꾼다)."""
        for kind, no, fields in (("info", "P012", nth.PROGRESS), ("merge", "M012", nth.MERGE), ("decision", "012", nth.ASK)):
            text = notice_text(no=no, kind=kind, fields=fields, title="[R-166] 제목 글", summary="요약 글", extra="result: 정상")
            request = parse(text, strict=False)
            self.assertEqual((request.kind, request.title, request.summary, request.no, request.notice_error), (kind, "[R-166] 제목 글", "요약 글", "", "foreign_key"), kind)

    def test_a_reason_with_the_kind_label_is_refused_in_both_readings_whatever_the_result(self):
        """D6(독립 검증): 사유가 `[M050] 병합완료 확인 - 정상` 같은 제목 꼴이면 폰의 둘째 줄이 첫 줄과 어긋나 보인다 — 사유에 `병합완료 확인` 글자(공백 없이 비교)를 쓸 수 없다."""
        labelled = ("[M050] 병합완료 확인 - 정상", "병합완료 확인 결과가 이상합니다", "병합완료확인", "병합 완료  확인", "x 병합완료" + chr(0xA0) + "확인 x", "[M050]병합완료 확인-정상", "앞 병합완료 확인")
        for result in ("정상", "이상"):
            for summary in labelled:
                for strict in (True, False):
                    self.assertEqual(problem(merged_text(result=result, summary=summary), strict), "merged_summary_label", (result, summary, strict))
        for fine in ("main 검사가 빨강입니다", "병합완료 뒤 사이트 빌드가 실패했습니다", "병합 확인 중 실패", "병합완료", "확인", "병합 완료 후 이상", "정상"):
            for strict in (True, False):
                self.assertEqual(problem(merged_text(result="이상", summary=fine), strict), "", (fine, strict))
        for kind, no, fields in (("info", "P012", nth.PROGRESS), ("merge", "M012", nth.MERGE), ("decision", "012", nth.ASK)):   # 다른 종류의 요약에는 이 규칙이 없다(옛 `병합완료` 알림 글처럼)
            for strict in (True, False):
                self.assertEqual(problem(notice_text(no=no, kind=kind, fields=fields, summary="병합완료 확인 결과 정상"), strict, 166), "", (kind, strict))

    def test_the_result_key_is_refused_on_every_other_kind_now_that_it_is_a_known_key(self):
        """`result` 는 병합완료 확인이 쓰는 새 칸이다. 다른 종류에 쓰면 거절이다(예전에는 모르는 칸이라 검증기만 거절하고 런타임은 무시했다 — D-318). 옛 파일 265개에는 이 칸이 없다."""
        for kind in OTHER_KINDS:
            prefix = {"info": "P", "merge": "M"}.get(kind, "")
            text = notice_text(no={"P": "P012", "M": "M012", "": "012"}[prefix], kind=kind, fields=nth.BODY_OF[prefix], extra="result: 정상")
            for strict in (True, False):
                self.assertEqual(problem(text, strict, 166), "foreign_key", (kind, strict))
            old_shape = oh.request_text(id="R-001", kind=kind, extra="result: 정상")
            for strict in (True, False):
                self.assertEqual(problem(old_shape, strict, 1), "notice_keys_without_no", (kind, strict))

    def test_the_other_five_kinds_still_read_exactly_as_before_with_all_their_fields(self):
        for kind in OTHER_KINDS:
            prefix = {"info": "P", "merge": "M"}.get(kind, "")
            no = {"P": "P012", "M": "M012", "": "012"}[prefix]
            for strict in (True, False):
                request = parse(notice_text(no=no, kind=kind, fields=nth.BODY_OF[prefix], work="R-160", urgency="급함", pr="57"), strict=strict)
                self.assertEqual((request.kind, request.no, request.work, request.urgency, request.pr, request.notice_error), (kind, no, "R-160", "급함", 57, ""), (kind, strict))
                expected = tuple(nth.BODY_OF[prefix].items()) + ((("summary", "현황 알림입니다"),) if prefix == "" else ())
                self.assertEqual(dict(request.fields), dict(expected), (kind, strict))

    def test_random_damage_never_makes_the_reader_raise_anything_but_a_request_error(self):
        """모든 운영자 알림이 지나는 읽기 길이라 망가진 병합완료 확인 파일(줄 빠짐·겹침·값 바뀜·잘림·낯선 글자)이 어떤 값으로 와도 읽기는 Request 를 돌려주거나 RequestError 를 던질 뿐이다(그 밖의 예외가 알림 실행을 깨면 안 된다).
        무작위지만 씨앗이 정해져 있어 같은 표본이다."""
        rng = random.Random(1112)
        junk = ["", " ", "정상", "이상", "M050", "M0500", "[M050]", "result", ":", "--- ", "---", chr(0x200B), "\r", "\t", "가" * 120, '"', "'", "R-266", "~", "https://x", "no: M050", "kind: merge"]
        base = merged_text(result="이상")
        outcomes = {"ok": 0, "error": 0}
        for _ in range(1500):
            lines = base.split("\n")
            for _ in range(rng.randint(1, 4)):
                operation, index = rng.choice(("drop", "dup", "value", "truncate", "insert")), rng.randrange(len(lines))
                if operation == "drop":
                    del lines[index]
                elif operation == "dup":
                    lines.insert(index, lines[index])
                elif operation == "value":
                    key, separator, _old = lines[index].partition(":")
                    lines[index] = key + separator + " " + rng.choice(junk)
                elif operation == "truncate":
                    lines = lines[:index + 1]
                else:
                    lines.insert(index, rng.choice(junk))
                lines = lines or [""]
            for strict in (True, False):
                try:
                    ol.parse_request(merged_name(), "\n".join(lines), strict=strict)
                    outcomes["ok"] += 1
                except ol.RequestError:
                    outcomes["error"] += 1
        self.assertGreater(outcomes["ok"], 100)                    # 표본이 거의 다 거절이거나 거의 다 통과면 이 시험은 아무것도 못 본다
        self.assertGreater(outcomes["error"], 100)

    def test_a_file_with_crlf_lines_or_a_leading_bom_reads_the_same(self):
        text = merged_text()
        want = ol.parse_request(merged_name(), text, strict=True)
        for variant in (text.replace("\n", "\r\n"), chr(0xFEFF) + text, chr(0xFEFF) + text.replace("\n", "\r\n")):
            for strict in (True, False):
                self.assertEqual(ol.parse_request(merged_name(), variant, strict=strict), want, (repr(variant[:6]), strict))


class ValidatorMergedTest(unittest.TestCase):
    PAIR = {name_of(264, "merge-m050"): merge_text(264, "M050")}

    def files(self, **more):
        return {**self.PAIR, **more}

    def test_a_merged_file_with_its_merge_request_passes_and_so_do_many_pairs(self):
        self.assertEqual(req_errors(self.files(**{merged_name(266): merged_text(266)})), [])
        many = {}
        for index in range(1, 12):
            no = f"M{index:03d}"
            many[name_of(300 + index, f"merge-{no.lower()}")] = merge_text(300 + index, no)
            many[merged_name(400 + index, no)] = merged_text(400 + index, no, result="정상" if index % 2 else "이상")
        self.assertEqual(req_errors(many), [])

    def test_a_merged_file_without_a_merge_request_of_the_same_number_is_an_error(self):
        for no, files in (("M050", {merged_name(266): merged_text(266)}), ("M051", self.files(**{merged_name(266, "M051"): merged_text(266, "M051")}))):
            found = req_errors(files)
            self.assertEqual(len(found), 1, [f.line() for f in found])
            self.assertEqual((found[0].check, found[0].level, found[0].path), ("REQ-1", "ERROR", f"{ol.REQUEST_DIR}/{merged_name(266, no)}"))
            self.assertEqual(found[0].message, ol.problem_text("merged_unpaired") + f" (no: {no})")

    def test_the_partner_must_really_be_a_merge_request_not_another_kind_or_another_merged_file(self):
        wrong_partner = {name_of(264, "wrong"): notice_text(number=264, no="M050", kind="info", fields=nth.PROGRESS)}               # info 는 M 번호를 쓸 수 없어 그 파일도 오류
        found = req_errors({**wrong_partner, merged_name(266): merged_text(266)})
        self.assertEqual([(f.path.rsplit("/", 1)[-1], f.message.split(" (no:")[0]) for f in found],
                         [(name_of(264, "wrong"), ol.problem_text("no_kind_mismatch")), (merged_name(266), ol.problem_text("merged_unpaired"))])
        only_merged = {merged_name(266): merged_text(266), merged_name(267): merged_text(267)}
        self.assertEqual([f.message.split(" (no:")[0] for f in req_errors(only_merged)], [ol.problem_text("merged_unpaired"), ol.problem_text("merged_unpaired"), ol.problem_text("merged_duplicate")])

    def test_the_second_merged_file_of_one_merge_request_is_an_error_and_the_first_one_wins(self):
        found = req_errors(self.files(**{merged_name(266): merged_text(266), merged_name(267): merged_text(267, result="이상")}))
        self.assertEqual(len(found), 1)
        self.assertEqual((found[0].check, found[0].path), ("REQ-1", f"{ol.REQUEST_DIR}/{merged_name(267)}"))
        self.assertEqual(found[0].message, ol.problem_text("merged_duplicate") + " (no: M050)")
        self.assertEqual(len(found[0].line().splitlines()), 1)

    def test_a_merged_file_may_share_the_number_of_its_merge_request_without_the_same_number_error(self):
        found = req_errors(self.files(**{merged_name(266): merged_text(266)}))
        self.assertEqual([f.line() for f in found if "같습니다" in f.message], [])

    def test_two_merge_requests_with_one_number_are_still_the_old_same_number_error(self):
        found = req_errors({**self.PAIR, name_of(265, "other"): merge_text(265, "M050"), merged_name(266): merged_text(266)})
        self.assertEqual(len(found), 1)
        self.assertIn(f"알림 번호 M050 가 {ol.REQUEST_DIR}/{name_of(264, 'merge-m050')} 와 같습니다", found[0].message)
        self.assertIn("next_notice_no.py", found[0].message)

    def test_the_other_types_keep_their_own_independent_numbers_next_to_a_merged_file(self):
        files = self.files(**{merged_name(266): merged_text(266), name_of(267, "p"): notice_text(number=267, no="P050"), name_of(268, "ask"): notice_text(number=268, no="050", kind="decision", fields={}, summary="x")})
        self.assertEqual(req_errors(files), [])

    def test_every_new_problem_is_a_one_line_error_with_its_sentence(self):
        cases = {"bad_result": merged_text(result="OK", title="[M050] 병합완료 확인 - 정상"), "missing_result": merged_text(drop=("result",)), "merged_title_mismatch": merged_text(title="[M050] 병합완료"),
                 "long_merged_summary": merged_text(summary="가" * 61), "foreign_key": merged_text(extra=["pr: 5"]), "bad_no": merged_text(no="M50"), "no_required": merged_text(drop=("no",)),
                 "no_kind_mismatch": merged_text(no="P012", title="[P012] 병합완료 확인 - 정상"), "merged_summary_label": merged_text(result="이상", summary="[M050] 병합완료 확인 - 정상")}
        for code, text in cases.items():
            found = req_errors({merged_name(266): text})
            self.assertEqual(len(found), 1, (code, [f.line() for f in found]))
            self.assertEqual((found[0].check, found[0].level, found[0].message), ("REQ-1", "ERROR", ol.problem_text(code)), code)
            self.assertEqual(len(found[0].line().splitlines()), 1)
            self.assertNotIn("::", found[0].message)

    def test_the_pairing_function_reads_only_the_requests_it_is_given_in_order(self):
        def request(name, text):
            return name, ol.parse_request(name, text, strict=True)
        entries = [request(merged_name(266), merged_text(266)), request(name_of(264, "m"), merge_text(264)), request(merged_name(267), merged_text(267))]
        self.assertEqual(ol.merged_pairing_problems(entries), [(merged_name(267), "merged_duplicate")])
        self.assertEqual(ol.merged_pairing_problems(entries[:1]), [(merged_name(266), "merged_unpaired")])
        self.assertEqual(ol.merged_pairing_problems([]), [])
        self.assertEqual(ol.merged_pairing_problems(entries[1:2]), [])

    def test_the_old_request_branch_files_are_unaffected_by_the_pair_rules(self):
        old = {name_of(number, f"old-{number}"): oh.request_text(id=f"R-{number:03d}", kind=OTHER_KINDS[number % 5], title=f"[R-{number:03d}] 옛 요청", summary="옛 요약") for number in range(1, 60)}
        self.assertEqual(req_errors(old), [])


class RunMergedRequestsTest(unittest.TestCase):
    def test_a_normal_file_goes_out_as_one_line_with_no_buttons(self):
        code, lines, net, _ = run_requests({merged_name(266): merged_text(266)})
        self.assertEqual((code, net.calls), (0, 1))
        body = net.bodies()[0]
        self.assertEqual(body["text"], "[M050] 병합완료 확인 - 정상")
        self.assertEqual(body["parse_mode"], "HTML")
        self.assertNotIn("reply_markup", body)
        self.assertEqual(lines, ["AI 요청 알림: R-266 을 알렸습니다 (알림 번호 M050)"])
        self.assertEqual(oh.nh.leaks(*lines, body["text"], chat=False), [])

    def test_an_abnormal_file_adds_the_reason_line_and_one_open_button(self):
        code, lines, net, _ = run_requests({merged_name(267): merged_text(267, result="이상")})
        self.assertEqual((code, net.calls), (0, 1))
        self.assertEqual(net.bodies()[0]["text"], "[M050] 병합완료 확인 - 이상\n" + SUMMARY_BAD)
        buttons = buttons_of(net)
        self.assertEqual(buttons, [("요청 열기", ol.blob_url("ai/claude/operator-loop", f"{ol.REQUEST_DIR}/{merged_name(267)}"))])
        self.assertTrue(buttons[0][1].startswith(BLOB + "ai/claude/operator-loop/"))
        self.assertEqual(notify.allowed_url(buttons[0][1]), buttons[0][1])

    def test_the_buttons_function_gives_the_same_answer_without_a_network(self):
        for result, labels in (("정상", []), ("이상", ["요청 열기"])):
            request = ol.parse_request(merged_name(), merged_text(result=result), strict=True)
            self.assertEqual([label for label, _ in ol.request_buttons(request, "ai/claude/x", "main")], labels, result)
        unreadable = ol.Request("R-266", "merged", "", "", "보통", None, "", merged_name(), "", "", (), "foreign_key")        # 칸이 틀려 번호 없이 읽힌 병합완료 확인(D1)은 고정 문구 + '요청 열기' 하나
        self.assertEqual(ol.request_buttons(unreadable, "ai/claude/x", "main"), [("요청 열기", ol.blob_url("ai/claude/x", f"{ol.REQUEST_DIR}/{merged_name()}"))])
        other = ol.Request("R-266", "info", "t", "s", "보통", None, "", name_of(266, "x"))                          # 다른 종류의 번호 없는 옛 모양(폴백)은 그대로 옛 단추
        self.assertEqual([label for label, _ in ol.request_buttons(other, "ai/claude/x", "main")], ["요청 열기", "답하기", "사용법"])

    def test_no_clash_warning_and_no_search_for_a_merged_file_but_other_kinds_keep_theirs(self):
        holder = [("refs/remotes/origin/main", f"{oh.DIR}{name_of(264, 'merge-m050')}", "no: M050")]
        refs = ["refs/remotes/origin/HEAD", "refs/remotes/origin/main", "refs/remotes/origin/ai/claude/other-1"]
        files = {merged_name(266): merged_text(266)}
        git = nth.NoticeGit(tree=oh.paths(*files), files=files, refs=refs, holders=holder)
        code, lines, net, _ = run_requests(files, git=git)
        self.assertEqual((code, net.calls, lines), (0, 1, ["AI 요청 알림: R-266 을 알렸습니다 (알림 번호 M050)"]))
        self.assertEqual(git.grep_calls(), [])
        files = {name_of(265, "merge-twin"): merge_text(265, "M050")}                                               # 같은 상황의 병합 요청은 예전처럼 겹침을 알린다
        git = nth.NoticeGit(tree=oh.paths(*files), files=files, refs=refs, holders=holder)
        code, lines, net, _ = run_requests(files, git=git)
        self.assertEqual(len(git.grep_calls()), 1)
        self.assertEqual([line for line in lines if "겹쳤" in line], [ol.NOTICE_DUPLICATE_LINE.format(no="M050", names=name_of(264, "merge-m050")), ol.NOTICE_DUPLICATE_WARNING])

    def test_in_one_push_each_kind_keeps_its_own_message_shape(self):
        files = {name_of(264, "merge-m050"): merge_text(264), merged_name(266): merged_text(266), name_of(267, "ask"): notice_text(number=267, no="003", kind="decision", fields=nth.ASK, summary="무엇을 할까요")}
        code, lines, net, _ = run_requests(files)
        texts = [body["text"] for body in net.bodies()]
        self.assertEqual((code, net.calls), (0, 3))
        self.assertEqual(texts[0], notify.format_notice("M050", nth.MERGE))
        self.assertEqual(texts[1], "[M050] 병합완료 확인 - 정상")
        self.assertEqual(texts[2], notify.format_notice("003", {**nth.ASK, "summary": "무엇을 할까요"}))
        self.assertEqual([label for label, _ in buttons_of(net, 0)], ["요청 열기", "사용법"])
        self.assertEqual(buttons_of(net, 1), [])
        self.assertEqual([label for label, _ in buttons_of(net, 2)], ["답하기", "요청 열기", "사용법"])

    def test_the_overflow_line_is_added_to_the_last_message_even_when_that_is_a_merged_one(self):
        files = {name_of(166, "p1"): notice_text(number=166, no="P001"), name_of(167, "p2"): notice_text(number=167, no="P002"), merged_name(168): merged_text(168),
                 name_of(169, "p3"): notice_text(number=169, no="P003"), name_of(170, "p4"): notice_text(number=170, no="P004")}
        code, lines, net, _ = run_requests(files)
        texts = [body["text"] for body in net.bodies()]
        self.assertEqual(net.calls, 3)
        self.assertEqual(texts[2], "[M050] 병합완료 확인 - 정상\n\n… 외 2건 (저장소의 인수인계/요청함/ 폴더에서 확인하세요)")
        self.assertNotIn("… 외", texts[0] + texts[1])
        self.assertIn(f"AI 요청 알림: 한 푸시에 {ol.MAX_REQUEST_MESSAGES}통까지만 보내 2건은 마지막 통의 '… 외 2건' 한 줄로 알렸습니다", lines)

    def test_a_bad_merged_part_is_sent_as_the_fixed_line_with_the_reason_in_the_log_and_its_own_warning(self):
        files = {merged_name(266): merged_text(266, extra=["urgency: 급함"])}
        code, lines, net, _ = run_requests(files)
        self.assertEqual((code, net.calls), (0, 1))
        self.assertEqual(net.bodies()[0]["text"], notify.format_merged_unreadable("R-266"))               # 옛 모양(제목·요약)이 아니라 고정 문구(D1) — 파일의 글은 하나도 없다
        self.assertEqual(net.bodies()[0]["parse_mode"], "HTML")
        self.assertEqual([label for label, _ in buttons_of(net)], ["요청 열기"])
        self.assertEqual(lines, [ol.MERGED_UNREADABLE_LINE.format(name=merged_name(266), problem=ol.problem_text("foreign_key")), "AI 요청 알림: R-266 을 알렸습니다", ol.MERGED_UNREADABLE_WARNING])
        self.assertNotIn(ol.NOTICE_FALLBACK_WARNING, lines)                                               # 옛 모양 경고('파일을 고쳐 새 번호로 다시 보내세요')는 이 길에 맞지 않다(D3)
        self.assertIn("다른 알림(info)", ol.MERGED_UNREADABLE_WARNING)
        self.assertEqual(oh.nh.leaks(*lines, net.bodies()[0]["text"], chat=False), [])

    def test_a_merged_file_without_a_result_is_sent_as_the_fixed_line_and_the_others_still_go(self):
        files = {merged_name(266): merged_text(266, result=None), name_of(267, "p"): notice_text(number=267, no="P012")}
        code, lines, net, _ = run_requests(files)
        self.assertEqual((code, net.calls), (0, 2))                       # result 가 없어도 알림은 잃지 않는다 — 고정 문구로 보내고 다른 요청은 그대로 간다
        self.assertEqual([body["text"] for body in net.bodies()], [notify.format_merged_unreadable("R-266"), notify.format_notice("P012", nth.PROGRESS)])
        self.assertIn(ol.MERGED_UNREADABLE_LINE.format(name=merged_name(266), problem=ol.problem_text("missing_result")), lines)

    def test_the_run_time_does_not_check_the_pair_so_an_unpaired_notice_is_still_sent(self):
        """한계(D-313): 알림 실행은 요청 파일 하나만 읽는다. 짝 병합 부탁이 있는지는 검증기 REQ-1 과 만드는 도구가 막고, 이미 올라간 짝 없는 파일은 알림이 가되 CI 가 빨개진다."""
        code, lines, net, _ = run_requests({merged_name(266, "M777"): merged_text(266, "M777")})
        self.assertEqual((code, net.calls), (0, 1))
        self.assertEqual(net.bodies()[0]["text"], "[M777] 병합완료 확인 - 정상")

    def test_the_text_never_carries_a_progress_number_or_the_old_message_parts(self):
        for result in ("정상", "이상"):
            code, lines, net, _ = run_requests({merged_name(266): merged_text(266, result=result)})
            text = net.bodies()[0]["text"]
            for needle in ("📊", "🔀", "🔔", "🚨", "현재 진행", "직전 보고", "다음 계획", "예상 완료", "확인·승인 대기", "관련 PR", "작업 r", "병합 요청", "진행 현황", "AI 요청"):
                self.assertNotIn(needle, text, (result, needle))
            self.assertNotRegex(text, r"\bP[0-9]{3}\b")


class UnreadableMergedFileTest(unittest.TestCase):
    """D1(독립 검증 MDONEV, 2026-11-12): `kind: merged` 로 읽혔지만 칸이 맞지 않는 파일은 옛 모양(제목·요약)으로 보내지 않는다 — 틀린 파일의 제목이 그대로 나가 거짓 `정상` 이 폰에 가는 일을 막는다.
    불변식: 폰에 `정상`·`이상` 이 가는 길은 '읽기를 통과한 파일 + 코드가 만든 제목(merged_title)' 하나뿐이고, 그 밖의 병합완료 확인 파일은 요청 번호만 든 고정 문구 + `요청 열기` 단추 하나다."""

    FIXED = notify.format_merged_unreadable("R-266")
    WRONG = {"title 이 result 와 어긋남": merged_text(result="이상", title="[M050] 병합완료 확인 - 정상"), "result 값 아님": merged_text(result="OK"), "result 없음": merged_text(result=None),
             "no 없음": merged_text(drop=("no",)), "no 모양": merged_text(no="M50"), "no 유형": merged_text(no="P012", title="[P012] 병합완료 확인 - 정상"),
             "칸 하나 더(urgency)": merged_text(extra=["urgency: 급함"]), "칸 하나 더(pr)": merged_text(extra=["pr: 57"]), "칸 하나 더(work)": merged_text(extra=["work: R-160"]),
             "사유가 제목 꼴": merged_text(result="이상", summary="[M050] 병합완료 확인 - 정상"), "제목 번호 어긋남": merged_text(title="[M051] 병합완료 확인 - 정상")}

    def push(self, text, number=266):
        code, lines, net, _ = run_requests({merged_name(number): text})
        return code, lines, net

    def test_the_false_normal_case_of_the_verifier_sends_the_fixed_line_and_never_the_title(self):
        """검증에서 재현된 경우: 정상 파일을 복사해 result 와 summary 만 이상으로 고치고 제목은 `- 정상` 그대로 둔 파일 — 예전에는 폰에 `[M050] 병합완료 확인 - 정상` 이 그대로 갔다."""
        code, lines, net = self.push(merged_text(266, result="이상", title="[M050] 병합완료 확인 - 정상"))
        self.assertEqual((code, net.calls), (0, 1))
        body = net.bodies()[0]
        self.assertEqual(body["text"], self.FIXED)
        for word in ("정상", "이상", SUMMARY_BAD, "[M050]", "AI 요청", notify.BELL_MARK):
            self.assertNotIn(word, body["text"], word)
        self.assertEqual(buttons_of(net), [("요청 열기", ol.blob_url("ai/claude/operator-loop", f"{ol.REQUEST_DIR}/{merged_name(266)}"))])
        self.assertEqual(lines[0], ol.MERGED_UNREADABLE_LINE.format(name=merged_name(266), problem=ol.problem_text("merged_title_mismatch")))
        self.assertEqual(lines[-1], ol.MERGED_UNREADABLE_WARNING)
        self.assertNotIn(ol.NOTICE_FALLBACK_WARNING, lines)

    def test_every_kind_of_wrong_shape_goes_the_fixed_way_with_exactly_one_button(self):
        for label, text in self.WRONG.items():
            code, lines, net = self.push(text)
            self.assertEqual((code, net.calls), (0, 1), label)
            self.assertEqual(net.bodies()[0]["text"], self.FIXED, label)
            self.assertEqual([name for name, _url in buttons_of(net)], ["요청 열기"], label)
            self.assertEqual(sum(1 for line in lines if line.startswith("::warning::")), 1, label)

    def test_no_word_of_the_wrong_file_reaches_the_phone_or_the_log(self):
        marker = "고유표식문장"
        for label, text in {"제목": merged_text(266, result="이상", title=f"[M050] 병합완료 확인 - 정상 {marker}"), "사유": merged_text(266, result="OK", summary=f"{marker} 사유"),
                            "둘 다": merged_text(266, no="M50", title=f"{marker} 제목", summary=f"{marker} 사유")}.items():
            code, lines, net = self.push(text)
            self.assertEqual(net.bodies()[0]["text"], self.FIXED, label)
            self.assertNotIn(marker, "\n".join(lines + [net.bodies()[0]["text"]]), label)

    def test_a_right_file_still_goes_the_normal_way_next_to_a_wrong_one(self):
        files = {merged_name(266): merged_text(266, result="이상", title="[M050] 병합완료 확인 - 정상"), merged_name(267, "M051"): merged_text(267, "M051", result="이상"),
                 name_of(268, "p"): notice_text(number=268, no="P012")}
        code, lines, net, _ = run_requests(files)
        self.assertEqual((code, net.calls), (0, 3))
        self.assertEqual([body["text"] for body in net.bodies()], [self.FIXED, "[M051] 병합완료 확인 - 이상\n" + SUMMARY_BAD, notify.format_notice("P012", nth.PROGRESS)])
        self.assertEqual([[label for label, _url in buttons_of(net, index)] for index in range(3)], [["요청 열기"], ["요청 열기"], ["요청 열기", "사용법"]])
        self.assertEqual(lines.count(ol.MERGED_UNREADABLE_WARNING), 1)

    def test_the_overflow_line_goes_on_the_fixed_line_when_it_is_the_last_message(self):
        files = {name_of(166, "p1"): notice_text(number=166, no="P001"), name_of(167, "p2"): notice_text(number=167, no="P002"), merged_name(168): merged_text(168, result="OK"),
                 name_of(169, "p3"): notice_text(number=169, no="P003")}
        code, lines, net, _ = run_requests(files)
        self.assertEqual(net.calls, 3)
        self.assertEqual(net.bodies()[2]["text"], notify.format_merged_unreadable("R-168", more=1))
        self.assertTrue(net.bodies()[2]["text"].endswith("… 외 1건 (저장소의 인수인계/요청함/ 폴더에서 확인하세요)"))

    def test_the_old_shape_fallback_of_the_other_kinds_keeps_its_own_line_and_warning_next_to_the_new_ones(self):
        files = {merged_name(266): merged_text(266, result="OK"), name_of(267, "p"): notice_text(number=267, no="P012", extra="repo: a/b")}
        code, lines, net, _ = run_requests(files)
        self.assertEqual((code, net.calls), (0, 2))
        self.assertEqual(net.bodies()[0]["text"], self.FIXED)
        self.assertEqual(net.bodies()[1]["text"], notify.format_ai_request("R-267", "info", "[R-166] 진행 현황", "현황 알림입니다"))             # 다른 종류는 예전 그대로 옛 모양
        self.assertIn(f"AI 요청 알림: {name_of(267, 'p')} 의 알림 칸이 맞지 않아 옛 모양(제목·요약)으로 보냅니다 — {ol.problem_text('foreign_key')}", lines)
        warnings = [line for line in lines if line.startswith("::warning::")]
        self.assertEqual(warnings, [ol.NOTICE_FALLBACK_WARNING, ol.MERGED_UNREADABLE_WARNING])

    def test_the_messages_of_the_two_ways_are_different_texts_with_different_log_lines(self):
        self.assertNotEqual(ol.MERGED_UNREADABLE_WARNING, ol.NOTICE_FALLBACK_WARNING)
        self.assertNotIn("새 번호로 다시 보내세요", ol.MERGED_UNREADABLE_WARNING)                             # 파일을 고쳐도 다시 알리지 않는다(D3)
        self.assertNotIn("옛 모양", ol.MERGED_UNREADABLE_LINE)
        self.assertTrue(ol.MERGED_UNREADABLE_LINE.startswith("AI 요청 알림: {name} 은 병합완료 확인 파일의 칸이 맞지 않아"))
        for text in (ol.MERGED_UNREADABLE_LINE, ol.MERGED_UNREADABLE_WARNING):
            self.assertNotIn("~", text)
            self.assertNotRegex(text, r"https?://")

    def test_seeded_damage_never_lets_a_word_of_a_wrong_file_reach_the_phone(self):
        """무작위 훼손 파일(줄 빠짐·겹침·값 바뀜·잘림·낯선 글자·결과 맞바꿈·제목 번호 바꿈) 700개를 알림 실행에 통과시켜 불변식을 본다: 폰 글은 ① 런타임 읽기가 병합완료 확인으로 통과시킨 파일의
        `format_merged`(= 코드가 만든 제목 + 이상일 때 소독한 사유) ② 고정 문구 둘 중 하나이고, ②는 파일의 글(제목·사유·표식)이 어디에도 없다. 읽기가 거절한 파일은 한 통도 보내지 않는다. 씨앗이 정해져 같은 표본이다."""
        rng = random.Random(1112)
        marker = "고유표식문장"
        junk = ["", " ", "정상", "이상", "M050", "M0500", "[M050]", "result", ":", "---", chr(0x200B), "\r", "\t", "가" * 120, '"', "'", "R-266", "https://x", "no: M050", "kind: merge", marker,
                f"[M050] 병합완료 확인 - 정상 {marker}", "병합완료 확인"]
        base = merged_text(result="이상", summary=f"{marker} 사유")
        counts = {"normal": 0, "fixed": 0, "refused": 0, "other_kind": 0}
        for index in range(700):
            lines = base.split("\n")
            for _ in range(rng.randint(1, 4)):
                operation, at = rng.choice(("drop", "dup", "value", "truncate", "insert", "swap_result", "title_number")), rng.randrange(len(lines))
                if operation == "drop":
                    del lines[at]
                elif operation == "dup":
                    lines.insert(at, lines[at])
                elif operation == "value":
                    key, separator, _old = lines[at].partition(":")
                    lines[at] = key + separator + " " + rng.choice(junk)
                elif operation == "truncate":
                    lines = lines[:at + 1]
                elif operation == "swap_result":
                    lines = [("result: 정상" if line == "result: 이상" else "result: 이상" if line == "result: 정상" else line) for line in lines]
                elif operation == "title_number":
                    lines = [line.replace("[M050]", "[M051]") if line.startswith("title:") else line for line in lines]
                else:
                    lines.insert(at, rng.choice(junk))
                lines = lines or [""]
            text = "\n".join(lines)
            try:
                request = ol.parse_request(merged_name(), text, strict=False)
            except ol.RequestError:
                request = None
            code, log, net = self.push(text)
            self.assertEqual(code, 0, index)
            sent = [body["text"] for body in net.bodies()]
            if request is None:
                counts["refused"] += 1
                self.assertEqual(sent, [], (index, text))
            elif request.kind != "merged":
                counts["other_kind"] += 1                                        # 훼손이 kind 를 바꾼 표본 — 다른 종류의 글은 이 시험의 범위가 아니다
            elif request.notice_error:
                counts["fixed"] += 1
                self.assertEqual(sent, [self.FIXED], (index, text))
                self.assertNotIn(marker, "\n".join(sent + log), (index, text))
                self.assertNotIn("정상", sent[0], (index, text))
                self.assertNotIn("이상", sent[0], (index, text))
            else:
                counts["normal"] += 1
                self.assertEqual(sent, [notify.format_merged(request.no, dict(request.fields))], (index, text))
                self.assertEqual(sent[0].split("\n")[0], notify.merged_title(request.no, dict(request.fields)["result"]), (index, text))
        self.assertGreater(counts["fixed"], 100, counts)                         # 표본이 한쪽으로 쏠리면 이 시험은 아무것도 못 본다
        self.assertGreater(counts["normal"], 30, counts)
        self.assertGreater(counts["refused"], 30, counts)


class UnchangedForOtherKindsTest(unittest.TestCase):
    """다른 종류(진행 현황·병합 요청·확인 요청·옛 모양)의 폰 글·단추·요청 파일 판정·알림 보내기 끝에서 끝까지가 이 변경 전 코드(main 299fda3)의 출력과 바이트까지 같다."""

    def test_the_sample_sets_are_as_big_as_when_they_were_recorded(self):
        self.assertEqual(tools.case_counts(notify, ol), golden.COUNTS)
        self.assertGreaterEqual(sum(golden.COUNTS.values()), 9000)

    def test_the_outputs_of_every_sample_set_are_the_old_codes_outputs(self):
        digests = tools.all_digests(notify, ol)
        self.assertEqual(sorted(digests), sorted(golden.DIGESTS))
        for key, want in golden.DIGESTS.items():
            self.assertEqual(digests[key], want, f"{key}: 다른 종류의 알림·요청 파일 읽기가 옛 코드와 달라졌다(병합완료 확인 추가가 다른 종류를 바꾸면 안 된다)")

    def test_the_readable_goldens_are_exactly_the_old_texts(self):
        now = tools.text_goldens(notify, ol)
        self.assertEqual(sorted(now), sorted(golden.TEXT_GOLDENS))
        for key, want in golden.TEXT_GOLDENS.items():
            self.assertEqual(now[key], want, key)

    def test_the_digest_covers_the_constant_the_golden_was_recorded_with_not_the_current_one(self):
        saved = ol.NOTICE_NO_REQUIRED_FROM_R
        with mock.patch.object(ol, "NOTICE_NO_REQUIRED_FROM_R", saved + 50):
            self.assertEqual(tools.all_digests(notify, ol), golden.DIGESTS)
            self.assertEqual(ol.NOTICE_NO_REQUIRED_FROM_R, saved + 50)           # 표본이 끝나면 되돌려 놓는다(여기서는 시험의 mock 값)
        self.assertEqual(ol.NOTICE_NO_REQUIRED_FROM_R, saved)

    def test_the_samples_really_cover_every_old_kind_and_every_number_type(self):
        kinds = {ol.parse_request("R-001_x.md", tools.front(kind, "old", None, 1), strict=False).kind for kind in tools.KINDS}
        self.assertEqual(kinds, set(tools.KINDS))
        self.assertNotIn("merged", tools.KINDS)
        texts = tools.text_goldens(notify, ol)
        for needle in ("P012 · 진행 현황", "M007 · 병합 요청", "003 · 확인 요청", "AI 요청 r001 · 병합 부탁", "AI 요청 r001 · 알림"):
            self.assertTrue(any(needle in value for value in texts.values()), needle)


def real_request_files():
    """이 저장소의 모든 원격 가지(origin/main·origin/ai/*)의 요청함 파일 → {(이름, sha256 앞 12자리): 글}. git 이 없거나 가지가 없으면 빈 사전."""
    try:
        refs = nn.list_refs(ROOT)
        groups = {}
        for sha, kind, refname in refs:
            if kind == "commit":
                groups.setdefault(sha, []).append(refname)
        commits = list(groups)
        trees = nn.batch_read(ROOT, [f"{sha}:{nn.REQUEST_DIR}" for sha in commits])
        names = {}
        for sha, (kind, body) in zip(commits, trees, strict=True):
            if kind == "tree":
                for name, digest in nn.tree_files(body, len(sha) // 2):
                    if nn.NAME_RE.fullmatch(name):
                        names.setdefault((name, digest), None)
        digests = sorted({digest for _name, digest in names})
        blobs = {digest: body for digest, (kind, body) in zip(digests, nn.batch_read(ROOT, digests), strict=True) if kind == "blob"}
    except (nn.ScanError, OSError, ValueError):
        return {}
    found = {}
    for (name, digest) in names:
        raw = blobs.get(digest)
        if raw is None:
            continue
        try:
            found[(name, hashlib.sha256(raw).hexdigest()[:12])] = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
    return found


class OldRequestFilesTest(unittest.TestCase):
    def test_every_recorded_old_request_file_is_judged_exactly_as_before(self):
        """운영자 요청함의 실제 요청 파일(R-001 부터 R-267 까지, 모든 원격 가지)을 새 읽기에 넣어 이 변경 전 코드의 판정(엄격한 읽기 문제 코드·런타임 읽기 지문)과 하나씩 견준다. 이 시험은 **가변 외부 상태**(원격 가지)에
        기댄다 — 가지가 없거나 기록된 파일이 100개 미만으로 보이면(얕은 복제·가지 정리) 건너뛴다. 상수 NOTICE_NO_REQUIRED_FROM_R 은 기록할 때의 값으로 고정한다(올려도 이 시험이 깨지지 않게)."""
        real = real_request_files()
        recorded = {key: text for key, text in real.items() if key in golden.CORPUS}
        if len(recorded) < 100:
            self.skipTest(f"요청 가지가 이 저장소에 없거나 기록된 요청 파일이 {len(recorded)}개뿐이라 건너뛴다(100개 이상 보여야 뜻이 있다)")
        different = []
        with mock.patch.object(ol, "NOTICE_NO_REQUIRED_FROM_R", tools.CONSTANT_AT_RECORDING):
            for (name, sha), text in sorted(recorded.items()):
                if tools.verdict(ol, name, text) != golden.CORPUS[(name, sha)]:
                    different.append(name)
        self.assertEqual(different, [], "옛 요청 파일의 판정이 달라졌다")

    def test_no_real_request_file_uses_the_result_key_unless_it_is_a_merged_file(self):
        real = real_request_files()
        if len(real) < 100:
            self.skipTest("요청 가지가 이 저장소에 없다")
        offenders = []
        for (name, _sha), text in sorted(real.items()):
            front = nn.front_lines(text) or ()
            keys = [line.split(":", 1)[0].strip() for line in front if ":" in line]
            if "result" in keys and "merged" not in nn.front_values(text, "kind"):
                offenders.append(name)
        self.assertEqual(offenders, [])

    def test_the_recorded_table_is_what_the_old_code_said_all_files_were_fine(self):
        self.assertGreaterEqual(len(golden.CORPUS), 265)
        self.assertEqual({strict for strict, _fingerprint in golden.CORPUS.values()}, {""})                      # 기록된 파일은 모두 엄격한 읽기도 통과했다
        self.assertTrue(all(re.fullmatch(r"[0-9a-f]{8}", fingerprint) for _strict, fingerprint in golden.CORPUS.values()))
        self.assertTrue(all(ol.REQUEST_NAME_RE.fullmatch(name) for name, _sha in golden.CORPUS))


class NumberToolsTest(unittest.TestCase):
    """번호 도구(인수인계/도구/work)는 병합완료 확인의 `no` 를 번호로 세지 않는다 — 새 번호를 먹지 않고 다음 M 번호 계산에도 들어가지 않는다."""

    def test_a_merged_files_number_is_not_counted_even_when_it_is_the_biggest(self):
        self.assertEqual(nn.front_numbers(merge_text(264, "M050")), [("merge", 50)])
        self.assertEqual(nn.front_numbers(merged_text(266, "M050")), [])
        self.assertEqual(nn.front_numbers(merged_text(266, "M999")), [])
        self.assertEqual(nn.front_numbers(merged_text(266, "M050", result="이상")), [])
        self.assertEqual(nn.front_numbers(notice_text(number=267, no="P035")), [("progress", 35)])

    def test_the_scan_of_a_work_folder_gives_the_same_next_numbers_with_or_without_merged_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "인수인계" / "요청함"
            folder.mkdir(parents=True)
            files = {name_of(264, "merge-m050"): merge_text(264, "M050"), name_of(267, "p"): notice_text(number=267, no="P035"), name_of(268, "ask"): notice_text(number=268, no="012", kind="decision", fields={}, summary="x")}
            for name, text in files.items():
                (folder / name).write_text(text, encoding="utf-8", newline="\n")
            before = nn.next_numbers(nn.scan(None, dirs=[tmp]))
            for name, text in {merged_name(269): merged_text(269, "M050"), merged_name(270, "M999"): merged_text(270, "M999")}.items():
                (folder / name).write_text(text, encoding="utf-8", newline="\n")
            after = nn.scan(None, dirs=[tmp])
            self.assertEqual(nn.next_numbers(after), before)
            self.assertEqual(before, {"progress": "P036", "merge": "M051", "ask": "013"})
            self.assertEqual(after["merge"][0], 50)
            self.assertEqual(nt.folder_numbers(folder), [("merge", 50), ("progress", 35), ("ask", 12)])

    def test_the_request_number_tool_refuses_a_merged_draft_instead_of_taking_a_new_number(self):
        self.assertNotIn("merged", nt.NOTICE_TYPE_OF_KIND)
        self.assertEqual(set(nt.NOTICE_TYPE_OF_KIND), set(notify.NOTICE_KIND_TYPES) - {"merged"})
        self.assertIn("merged", nt.no_problem("M051", "merged"))
        self.assertTrue(nt.no_problem("M050", "merged", taken=[("merge", 50)]))
        self.assertTrue(nt.notice_front_problem({"kind": "merged", "no": "M051"}))
        for kind in OTHER_KINDS:                                                                                   # 다른 종류의 판정은 그대로
            self.assertEqual(nt.no_problem({"info": "P012", "merge": "M012"}.get(kind, "012"), kind), "", kind)


if __name__ == "__main__":
    unittest.main()
