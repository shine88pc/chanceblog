"""확인 필요 모음의 정책 데이터와 오래된 항목 규칙(pipeline/inbox_policy.py) 테스트 — 파일·네트워크 없이 순수 함수만 확인한다.

- 정책 파일 검증(parse_policy): 모르는 칸·길이·날짜 모양·결정 종류·키 모양·비밀 모양·물결표·주소가 하나라도 있으면 파일 전체를 거절한다.
- 결정 찾기(decision_for): 항목 id 의 앞부분으로 맞고 가장 구체적인 키가 이긴다.
- 계절·행사 철 표(season_review·in_season): 달력 구간·유예 일수·해를 넘기는 구간·경계일.
- Blogger 초안의 검토 신호(unconfirmed_review_conditions).
- 실제 정책 파일(pipeline/ops_inbox_policy.json)이 올바르고 운영자 결정 일곱 가지를 담고 있다.
"""
import copy
import json
import re
import unittest
from datetime import date
from unittest import mock

import _bootstrap
from pipeline import inbox_policy as ip

ROOT = _bootstrap.ROOT
REAL_PATH = ROOT / ip.POLICY_FILE

GOOD = {
    "schema_version": 1,
    "planned_pause": {"active": True, "since": "2026-11-09", "reason": "의도된 정지", "decision_ref": "운영자 결정 2026-11-09",
                      "resume_conditions": ["조건 하나", "조건 둘"], "resume_gate_passed": False},
    "item_decisions": {
        "draft:88": {"decision": "discard_close", "date": "2026-11-11", "reason": "폐기 권장"},
        "blogger:blogger_macat:drafts:202611081745": {"decision": "keep", "date": "2026-11-11", "reason": "유지"},
        "approve:7f2dfdf": {"decision": "ignore", "date": "2026-11-11", "reason": "무시"},
    },
}


def good(**changes):
    data = copy.deepcopy(GOOD)
    for key, value in changes.items():
        if value is KeyError:
            data.pop(key, None)
        else:
            data[key] = value
    return data


def pause(**changes):
    data = copy.deepcopy(GOOD["planned_pause"])
    for key, value in changes.items():
        if value is KeyError:
            data.pop(key, None)
        else:
            data[key] = value
    return data


def decision(**changes):
    data = {"decision": "keep", "date": "2026-11-11", "reason": "유지"}
    for key, value in changes.items():
        if value is KeyError:
            data.pop(key, None)
        else:
            data[key] = value
    return data


class ParsePolicyTest(unittest.TestCase):
    def bad(self, data, needle=None):
        with self.assertRaises(ip.PolicyError) as caught:
            ip.parse_policy(data)
        if needle:
            self.assertIn(needle, str(caught.exception))

    def test_the_smallest_valid_policy_declares_nothing(self):
        policy = ip.parse_policy({"schema_version": 1})
        self.assertEqual((policy.planned_pause, policy.decisions), (None, ()))
        self.assertIsNone(ip.parse_policy({"schema_version": 1, "planned_pause": None, "item_decisions": None}).planned_pause)
        self.assertEqual(ip.parse_policy({"schema_version": 1, "item_decisions": {}}).decisions, ())

    def test_a_full_policy_is_read_field_by_field(self):
        policy = ip.parse_policy(GOOD)
        plan = policy.planned_pause
        self.assertEqual((plan.active, plan.since, plan.reason, plan.decision_ref, plan.resume_conditions, plan.resume_gate_passed),
                         (True, "2026-11-09", "의도된 정지", "운영자 결정 2026-11-09", ("조건 하나", "조건 둘"), False))
        self.assertTrue(plan.declared)
        self.assertEqual([d.key for d in policy.decisions], ["approve:7f2dfdf", "blogger:blogger_macat:drafts:202611081745", "draft:88"])      # 키 순
        self.assertEqual([d.kind for d in policy.decisions], ["ignore", "keep", "discard_close"])
        self.assertEqual(policy.decisions[2], ip.Decision("draft:88", "discard_close", "2026-11-11", "폐기 권장"))

    def test_the_resume_gate_flag_defaults_to_false_and_must_be_a_real_boolean(self):
        self.assertFalse(ip.parse_policy(good(planned_pause=pause(resume_gate_passed=KeyError))).planned_pause.resume_gate_passed)
        self.assertTrue(ip.parse_policy(good(planned_pause=pause(resume_gate_passed=True))).planned_pause.resume_gate_passed)
        for value in ("true", 1, 0, None, "false"):
            self.bad(good(planned_pause=pause(resume_gate_passed=value)), "resume_gate_passed")

    def test_unknown_fields_are_rejected_at_every_level(self):
        self.bad(good(extra=1), "알 수 없는 칸")
        self.bad(good(planned_pause=pause(extra=1)), "알 수 없는 칸")
        self.bad(good(item_decisions={"draft:1": decision(extra=1)}), "알 수 없는 칸")
        self.bad(good(planned_pause=pause(resumeGatePassed=True)), "알 수 없는 칸")             # 오타가 조용히 '꺼짐'으로 남지 않는다

    def test_the_schema_version_must_be_the_integer_one(self):
        for value in (0, 2, "1", True, None, 1.0, 1.5):
            self.bad(good(schema_version=value), "schema_version")
        self.bad({"item_decisions": {}}, "schema_version")

    def test_the_top_level_must_be_an_object(self):
        for value in (None, [], "x", 3):
            self.bad(value, "객체")

    def test_the_doc_note_is_optional_text_with_a_length_limit(self):
        self.assertIsNotNone(ip.parse_policy(good(_doc="설명")))
        self.bad(good(_doc=""), "_doc")
        self.bad(good(_doc="가" * (ip.DOC_MAX + 1)), "_doc")
        self.bad(good(_doc=5), "_doc")
        ip.parse_policy(good(_doc="가" * ip.DOC_MAX))

    def test_a_declared_pause_needs_reason_ref_since_and_conditions(self):
        for name in ("since", "reason", "decision_ref", "resume_conditions"):
            self.bad(good(planned_pause=pause(**{name: KeyError})), name)
        self.bad(good(planned_pause=pause(active=KeyError)), "active")
        for value in ("true", 1, None):
            self.bad(good(planned_pause=pause(active=value)), "active")
        self.bad(good(planned_pause="x"), "planned_pause")
        self.bad(good(planned_pause=[]), "planned_pause")

    def test_pause_text_lengths_have_exact_boundaries(self):
        ip.parse_policy(good(planned_pause=pause(reason="가" * ip.REASON_MAX)))
        self.bad(good(planned_pause=pause(reason="가" * (ip.REASON_MAX + 1))), "reason")
        self.bad(good(planned_pause=pause(reason="  ")), "reason")
        ip.parse_policy(good(planned_pause=pause(decision_ref="가" * ip.REF_MAX)))
        self.bad(good(planned_pause=pause(decision_ref="가" * (ip.REF_MAX + 1))), "decision_ref")
        self.bad(good(planned_pause=pause(decision_ref="")), "decision_ref")
        for value in (5, None, ["a"]):
            self.bad(good(planned_pause=pause(reason=value)), "reason")

    def test_the_resume_conditions_are_a_short_list_of_short_texts(self):
        self.bad(good(planned_pause=pause(resume_conditions=[])), "하나 이상")
        self.bad(good(planned_pause=pause(resume_conditions="조건")), "목록")
        self.bad(good(planned_pause=pause(resume_conditions=[5])), "resume_conditions[0]")
        self.bad(good(planned_pause=pause(resume_conditions=["가" * (ip.CONDITION_MAX + 1)])), "resume_conditions[0]")
        self.bad(good(planned_pause=pause(resume_conditions=["좋은 조건", ""])), "resume_conditions[1]")
        ip.parse_policy(good(planned_pause=pause(resume_conditions=["가" * ip.CONDITION_MAX])))
        ip.parse_policy(good(planned_pause=pause(resume_conditions=["조건"] * ip.MAX_RESUME_CONDITIONS)))
        self.bad(good(planned_pause=pause(resume_conditions=["조건"] * (ip.MAX_RESUME_CONDITIONS + 1))), "개 이하")

    def test_dates_must_be_real_iso_days(self):
        for value in ("2026-13-01", "2026-02-30", "26-11-09", "2026-11-09T00:00", "2026/11/09", "20261109", " 2026-11-09", 20261109, None):
            self.bad(good(planned_pause=pause(since=value)), "since")
            self.bad(good(item_decisions={"draft:1": decision(date=value)}), "date")
        ip.parse_policy(good(planned_pause=pause(since="2028-02-29")))          # 윤일은 있는 날짜
        self.bad(good(planned_pause=pause(since="2027-02-29")), "since")

    def test_an_inactive_pause_may_leave_the_other_fields_out_but_what_is_there_must_be_valid(self):
        plan = ip.parse_policy(good(planned_pause={"active": False})).planned_pause
        self.assertEqual((plan.active, plan.declared, plan.reason, plan.resume_conditions), (False, False, "", ()))
        plan = ip.parse_policy(good(planned_pause=pause(active=False))).planned_pause
        self.assertFalse(plan.declared)                         # 꺼 둔 선언은 '의도된 정지'로 보이지 않는다
        self.bad(good(planned_pause={"active": False, "since": "x"}), "since")
        self.bad(good(planned_pause={"active": False, "reason": chr(126)}), "reason")
        self.bad(good(planned_pause={"active": False, "resume_conditions": "x"}), "resume_conditions")
        ip.parse_policy(good(planned_pause={"active": False, "resume_conditions": []}))

    def test_decision_keys_must_name_a_kind_the_policy_may_decide(self):
        for key in ("draft:88", "approve:7f2dfdf", "pr:176", "blogger:blogger_macat:drafts:202611081745", "draft:1", "pr:1234567", "approve:0000000"):
            self.assertEqual(ip.parse_policy(good(item_decisions={key: decision()})).decisions[0].key, key)
        for key in ("watchdog:9", "run:chanceblog:failed", "pause", "source:issues", "draft", "draft:", "Draft:88", "draft:88 ", "draft:8 8", "draft::88",
                    "pr", "blogger", "draft:a:b:c:d:e", "draft:" + "a" * 61, "", "draft:한글", "approve:AB",
                    # 넓은 키·실제로 쓰지 않는 모양은 받지 않는다(D8 — 앞으로 올 항목까지 가리지 않게)
                    "approve:more", "approve:7f2dfd", "approve:7f2dfdf0", "approve:7F2DFDF", "approve:7f2dfdf:more", "draft:88:wait", "draft:1.2_x", "draft:12345678", "pr:176:ready", "pr:abc",
                    "blogger:blogger_macat:drafts", "blogger:blogger_macat:drafts:20261108174", "blogger:blogger_macat:drafts:2026110817451", "blogger:blogger_macat:drafts:20261108174x",
                    "blogger:blogger_macat:posts:202611081745", "blogger:Blogger_x:drafts:202611081745", "blogger:x:drafts:202611081745", "blogger:" + "a" * 32 + ":drafts:202611081745"):
            self.bad(good(item_decisions={key: decision()}), "항목 키")

    def test_each_decision_needs_kind_date_and_reason(self):
        for name in ("decision", "date", "reason"):
            self.bad(good(item_decisions={"draft:1": decision(**{name: KeyError})}), name)
        for kind in ("keep", "discard_close", "ignore"):
            self.assertEqual(ip.parse_policy(good(item_decisions={"draft:1": decision(decision=kind)})).decisions[0].kind, kind)
        for kind in ("Keep", "discard", "close", "", None, 3, "ignore "):
            self.bad(good(item_decisions={"draft:1": decision(decision=kind)}), "decision")
        for body in ("x", None, [], 5):
            self.bad(good(item_decisions={"draft:1": body}), "객체")
        self.bad(good(item_decisions=[]), "item_decisions")
        self.bad(good(item_decisions="x"), "item_decisions")

    def test_decision_reason_length_has_an_exact_boundary(self):
        ip.parse_policy(good(item_decisions={"draft:1": decision(reason="가" * ip.DECISION_REASON_MAX)}))
        self.bad(good(item_decisions={"draft:1": decision(reason="가" * (ip.DECISION_REASON_MAX + 1))}), "reason")
        self.bad(good(item_decisions={"draft:1": decision(reason="")}), "reason")

    def test_the_number_of_decisions_is_capped(self):
        many = {f"draft:{n}": decision() for n in range(1, ip.MAX_DECISIONS + 1)}
        self.assertEqual(len(ip.parse_policy(good(item_decisions=many)).decisions), ip.MAX_DECISIONS)
        many[f"draft:{ip.MAX_DECISIONS + 1}"] = decision()
        self.bad(good(item_decisions=many), "개 이하")

    def test_text_fields_refuse_tilde_mentions_links_control_characters_and_secrets(self):
        secret = "ghp_" + "a" * 36
        for text in ("물결" + chr(126) + "표", "누구@예시", "주소 http://x", "주소 HTTPS://x", "www.예시.kr", "줄\n바꿈", "탭\t문자", "제어" + chr(7), secret, "앞 " + secret):
            self.bad(good(planned_pause=pause(reason=text)), "reason")
            self.bad(good(planned_pause=pause(decision_ref=text)), "decision_ref")
            self.bad(good(planned_pause=pause(resume_conditions=[text])), "resume_conditions[0]")
            self.bad(good(item_decisions={"draft:1": decision(reason=text)}), "reason")
            self.bad(good(_doc=text), "_doc")

    def test_ordinary_korean_punctuation_and_numbers_are_fine(self):
        ip.parse_policy(good(planned_pause=pause(reason="주 1–2편(코드 상한) · 3일 · 「따옴표」 — 쉼표, 마침표.")))

    def test_the_error_message_never_repeats_the_offending_text(self):
        secret = "ghp_" + "a" * 36
        with self.assertRaises(ip.PolicyError) as caught:
            ip.parse_policy(good(planned_pause=pause(reason=secret)))
        self.assertNotIn(secret, str(caught.exception))


class DocumentedLimitsTest(unittest.TestCase):
    """docs/OPS_INBOX.md §10-7 에 적힌 한도가 코드와 같은지 — 값을 바꾸면 문서와 이 표를 함께 고친다(경계 시험은 상수 자체를 쓰므로 값은 여기서 글자로 못박는다)."""

    def test_the_limits_are_the_documented_numbers(self):
        self.assertEqual((ip.REASON_MAX, ip.REF_MAX, ip.CONDITION_MAX, ip.DECISION_REASON_MAX, ip.DOC_MAX), (240, 200, 160, 200, 400))
        self.assertEqual((ip.MAX_DECISIONS, ip.MAX_RESUME_CONDITIONS, ip.MAX_POLICY_BYTES, ip.SCHEMA_VERSION), (100, 12, 65536, 1))
        self.assertEqual(ip.DECISION_KINDS, ("keep", "discard_close", "ignore"))
        self.assertEqual(ip.DECISION_KEY_PREFIXES, ("approve", "draft", "blogger", "pr"))
        self.assertEqual(ip.SEASON_GRACE_DAYS, 14)


class ParsePolicyTextTest(unittest.TestCase):
    def test_a_valid_file_text_is_parsed(self):
        policy = ip.parse_policy_text(json.dumps(GOOD, ensure_ascii=False))
        self.assertTrue(policy.planned_pause.declared)

    def test_broken_json_is_a_policy_error_that_names_only_the_line(self):
        with self.assertRaises(ip.PolicyError) as caught:
            ip.parse_policy_text('{"schema_version": 1,\n  "x": }')
        message = str(caught.exception)
        self.assertIn("2번째 줄", message)
        self.assertNotIn('"x"', message)

    def test_non_text_and_oversized_files_are_refused(self):
        for value in (None, b"{}", 5, ["a"]):
            with self.assertRaises(ip.PolicyError):
                ip.parse_policy_text(value)
        filler = "가" * (ip.MAX_POLICY_BYTES // 3 + 10)
        with self.assertRaises(ip.PolicyError):
            ip.parse_policy_text(json.dumps({"schema_version": 1, "_doc": filler}, ensure_ascii=False))

    def test_a_file_right_at_the_size_limit_is_still_read(self):
        head = '{"schema_version": 1, "_doc": "x"}'
        padded = head + " " * (ip.MAX_POLICY_BYTES - len(head.encode("utf-8")))
        self.assertEqual(len(padded.encode("utf-8")), ip.MAX_POLICY_BYTES)
        ip.parse_policy_text(padded)
        with self.assertRaises(ip.PolicyError):
            ip.parse_policy_text(padded + " ")

    def test_the_json_top_level_must_still_be_an_object(self):
        for text in ("[]", "null", "5", '"x"', ""):
            with self.assertRaises(ip.PolicyError):
                ip.parse_policy_text(text)


class DecisionForTest(unittest.TestCase):
    def setUp(self):
        def made(key, kind="keep"):
            return ip.Decision(key, kind, "2026-11-11", "사유")
        # 파서는 서로 겹치는 넓은 키를 받지 않으므로(D8) 결정 찾기 규칙(항목 id 의 앞부분을 마디째로·가장 긴 키 우선)은 직접 만든 Policy 로 본다
        self.policy = ip.Policy(decisions=(made("draft:88", "discard_close"), made("draft:880"), made("approve:7f2dfdf", "ignore"), made("blogger:blogger_macat:drafts"),
                                           made("blogger:blogger_macat:drafts:202611081745", "ignore"), made("pr:176", "ignore")))

    def kind(self, item_id):
        found = ip.decision_for(self.policy, item_id)
        return found.kind if found else None

    def test_a_key_matches_the_item_id_and_every_state_of_it(self):
        self.assertEqual(self.kind("draft:88:wait"), "discard_close")
        self.assertEqual(self.kind("draft:88:stale"), "discard_close")
        self.assertEqual(self.kind("draft:88"), "discard_close")
        self.assertEqual(self.kind("pr:176:ready"), "ignore")
        self.assertEqual(self.kind("approve:7f2dfdf"), "ignore")

    def test_matching_is_by_whole_segments_not_by_text_prefix(self):
        self.assertEqual(self.kind("draft:880:wait"), "keep")
        self.assertIsNone(self.kind("draft:8:wait"))
        self.assertIsNone(self.kind("draft:8800:wait"))
        self.assertIsNone(self.kind("approve:7f2dfd"))
        self.assertIsNone(self.kind("approve:7f2dfdf0"))
        self.assertIsNone(self.kind("pr:1760:ready"))

    def test_the_most_specific_key_wins(self):
        self.assertEqual(self.kind("blogger:blogger_macat:drafts:202611081746"), "keep")
        self.assertEqual(self.kind("blogger:blogger_macat:drafts:202611081745"), "ignore")

    def test_other_kinds_of_items_never_match(self):
        for item_id in ("watchdog:9", "run:x:failed", "pause", "pause:planned", "source:pulls", "blog:blogger_macat:off", "stat:chance", "note:x"):
            self.assertIsNone(self.kind(item_id), item_id)

    def test_no_policy_or_a_non_text_id_never_matches(self):
        self.assertIsNone(ip.decision_for(None, "draft:88:wait"))
        for value in (None, 5, b"draft:88", ["draft:88"]):
            self.assertIsNone(ip.decision_for(self.policy, value))
        self.assertEqual(self.policy.decision_for("draft:88:wait").key, "draft:88")


class SeasonTableTest(unittest.TestCase):
    def test_the_table_is_well_formed_and_every_window_is_a_real_calendar_range(self):
        names = [term[0] for term in ip.SEASON_TERMS]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(ip.SEASON_GRACE_DAYS, 14)
        for name, pattern, start, end in ip.SEASON_TERMS:
            self.assertTrue(pattern.pattern, name)
            date(2027, start[0], start[1])
            date(2028, end[0], end[1])
            self.assertTrue(ip.season_window_text(name), name)

    def test_the_four_seasons_cover_the_month_groups_the_topic_picker_uses(self):
        from pipeline import topics            # 같은 계절 정의(봄 3–5월 …)에서 벗어나지 않게 지킨다
        labels = {"spring": "봄", "summer": "여름", "autumn": "가을", "winter": "겨울"}
        table = {term[0]: term for term in ip.SEASON_TERMS}
        for season, months in topics.SEASON_MONTHS.items():
            _name, _pattern, start, end = table[labels[season]]
            for year in (2027, 2028):
                for month in months:
                    for day in (1, 15, 28):
                        self.assertTrue(ip.in_season(date(year, month, day), start, end, 0), (season, year, month, day))

    def test_the_season_words_are_the_topic_pickers_words(self):
        from pipeline import topics
        sample = {"spring": "벚꽃 구경", "summer": "무더위 대비", "autumn": "단풍 여행", "winter": "한파 대비"}
        for season, text in sample.items():
            self.assertIn(season, topics.mentioned_seasons(text, "ko"))
        labels = {"spring": "봄", "summer": "여름", "autumn": "가을", "winter": "겨울"}
        for season, text in sample.items():
            matched = [term[0] for term in ip.SEASON_TERMS if term[1].search(text)]
            self.assertEqual(matched, [labels[season]], text)


class InSeasonBoundaryTest(unittest.TestCase):
    spring = ((2, 1), (5, 31))
    winter = ((11, 1), (2, 29))

    def test_a_window_inside_one_year_has_exact_edges_and_a_fourteen_day_grace(self):
        start, end = self.spring
        for day, wanted in ((date(2027, 1, 31), False), (date(2027, 2, 1), True), (date(2027, 5, 31), True), (date(2027, 6, 1), True),
                            (date(2027, 6, 14), True), (date(2027, 6, 15), False), (date(2027, 12, 31), False)):
            self.assertEqual(ip.in_season(day, start, end), wanted, day)

    def test_grace_days_can_be_changed_by_the_caller_and_zero_means_the_last_day_only(self):
        start, end = self.spring
        self.assertTrue(ip.in_season(date(2027, 5, 31), start, end, 0))
        self.assertFalse(ip.in_season(date(2027, 6, 1), start, end, 0))
        self.assertTrue(ip.in_season(date(2027, 6, 1), start, end, 1))

    def test_a_window_that_crosses_the_new_year_works_on_both_sides(self):
        start, end = self.winter
        for day, wanted in ((date(2026, 10, 31), False), (date(2026, 11, 1), True), (date(2026, 12, 31), True), (date(2027, 1, 1), True),
                            (date(2027, 2, 28), True), (date(2027, 3, 14), True), (date(2027, 3, 15), False), (date(2027, 7, 1), False)):
            self.assertEqual(ip.in_season(day, start, end), wanted, day)

    def test_february_29_in_the_table_is_the_last_day_of_february_in_any_year(self):
        start, end = self.winter
        self.assertTrue(ip.in_season(date(2028, 2, 29), start, end, 0))          # 윤년
        self.assertTrue(ip.in_season(date(2027, 2, 28), start, end, 0))          # 평년: 28일이 마지막 날
        self.assertFalse(ip.in_season(date(2027, 3, 1), start, end, 0))
        self.assertFalse(ip.in_season(date(2028, 3, 1), start, end, 0))
        self.assertTrue(ip.in_season(date(2028, 3, 14), start, end))             # 윤년 유예: 2월 29일 + 14일
        self.assertFalse(ip.in_season(date(2028, 3, 15), start, end))

    def test_every_day_of_a_year_is_decided_without_error(self):
        day = date(2027, 1, 1)
        seen = 0
        while day.year == 2027:
            for _name, _pattern, start, end in ip.SEASON_TERMS:
                self.assertIsInstance(ip.in_season(day, start, end), bool)
            day = date.fromordinal(day.toordinal() + 1)
            seen += 1
        self.assertEqual(seen, 365)


class SeasonReviewTest(unittest.TestCase):
    NOV = date(2026, 11, 11)

    def review(self, title, today=None):
        return ip.season_review(title, today or self.NOV)

    def test_the_real_spring_draft_is_out_of_season_in_november(self):
        self.assertEqual(self.review("봄맞이 대청소를 방별로 나눠 끝내는 분할 계획표 만들기"), ("봄",))

    def test_the_real_autumn_draft_is_still_in_season_on_that_day_by_the_calendar(self):
        self.assertIsNone(self.review("가을 여행 전 집을 비울 때 확인하는 가전과 가스 쓰레기 정돈법"))

    def test_titles_without_season_words_are_never_out_of_season(self):
        for title in ("사철 쓰는 서랍 정리법", "", None, 5, "돌봄 서비스 신청 방법", "모기지 대출 구정물 처리", "English only title"):
            self.assertIsNone(self.review(title), repr(title))

    def test_a_season_word_only_counts_at_the_start_of_a_word(self):
        self.assertIsNone(self.review("돌봄 계획"))
        self.assertEqual(self.review("올봄 정리"), ("봄",))
        self.assertEqual(self.review("초여름 점검"), ("여름",))
        self.assertEqual(self.review("한여름 준비"), ("여름",))
        self.assertIsNone(self.review("모기지 상환 계획"))
        self.assertIsNone(self.review("모기업 소식"))
        self.assertEqual(self.review("모기 퇴치"), ("여름",))
        self.assertIsNone(self.review("구정물 처리"))
        self.assertEqual(self.review("구정 준비", date(2026, 7, 1)), ("설·정월",))

    def test_the_same_title_flips_exactly_on_the_edges_of_its_window(self):
        title = "봄맞이 정리"
        self.assertEqual(self.review(title, date(2027, 1, 31)), ("봄",))
        self.assertIsNone(self.review(title, date(2027, 2, 1)))
        self.assertIsNone(self.review(title, date(2027, 5, 31)))
        self.assertIsNone(self.review(title, date(2027, 6, 14)))
        self.assertEqual(self.review(title, date(2027, 6, 15)), ("봄",))

    def test_one_word_that_is_in_season_saves_the_title(self):
        self.assertIsNone(self.review("겨울이 오기 전에 봄맞이 준비", self.NOV))                # 겨울 철 안
        self.assertEqual(self.review("봄맞이와 여름 준비", self.NOV), ("봄", "여름"))
        self.assertIsNone(self.review("봄맞이와 여름 준비", date(2027, 3, 1)))
        self.assertIsNone(self.review("봄맞이와 여름 준비", date(2027, 7, 1)))

    def test_events_have_their_own_narrow_windows(self):
        self.assertIsNone(self.review("추석 연휴 집 비우기", date(2026, 9, 1)))
        self.assertIsNone(self.review("추석 선물 정리", date(2026, 11, 3)))                      # 10월 20일 + 14일
        self.assertEqual(self.review("추석 선물 정리", date(2026, 11, 4)), ("추석",))
        self.assertEqual(self.review("추석 선물 정리", date(2026, 7, 31)), ("추석",))
        self.assertIsNone(self.review("김장 준비", date(2026, 12, 20)))
        self.assertIsNone(self.review("김장 준비", date(2027, 1, 3)))
        self.assertEqual(self.review("김장 준비", date(2027, 1, 4)), ("김장",))
        self.assertIsNone(self.review("설날 대청소", date(2027, 1, 20)))
        self.assertEqual(self.review("설날 대청소", date(2026, 11, 11)), ("설·정월",))
        self.assertIsNone(self.review("연말 모임 장소 정하기", date(2026, 12, 25)))
        self.assertEqual(self.review("연말 모임 장소 정하기", date(2026, 6, 1)), ("연말·성탄",))
        self.assertEqual(self.review("어버이날 선물", date(2026, 11, 11)), ("어린이날·어버이날",))
        self.assertIsNone(self.review("어버이날 선물", date(2027, 5, 1)))

    def test_the_result_lists_the_words_in_the_order_of_the_table(self):
        title = "연말 준비와 가을 정리와 봄 계획"
        self.assertEqual(self.review(title, date(2026, 7, 1)), ("봄", "가을", "연말·성탄"))

    def test_the_window_text_is_readable_and_has_no_tilde(self):
        self.assertEqual(ip.season_window_text("봄"), "2월 1일–5월 31일")
        self.assertEqual(ip.season_window_text("겨울"), "11월 1일–2월 29일")
        self.assertEqual(ip.season_window_text("없는 이름"), "")
        self.assertNotIn(chr(126), "".join(ip.season_window_text(term[0]) for term in ip.SEASON_TERMS))


class ReviewSignalTest(unittest.TestCase):
    def test_both_signals_must_be_explicit_and_exactly_positive(self):
        self.assertEqual(ip.unconfirmed_review_conditions({"review_quality": "pass", "review_safety": "clear"}), [])
        self.assertEqual(ip.unconfirmed_review_conditions({"review_quality": "pass"}), ["건강·안전 차단 없음"])
        self.assertEqual(ip.unconfirmed_review_conditions({"review_safety": "clear"}), ["품질 Gate 통과"])
        self.assertEqual(ip.unconfirmed_review_conditions({}), ["품질 Gate 통과", "건강·안전 차단 없음"])

    def test_anything_that_is_not_exactly_the_positive_value_is_unconfirmed(self):
        for value in ("PASS", "Pass", "ok", "passed", True, 1, None, "", ["pass"]):
            self.assertEqual(ip.unconfirmed_review_conditions({"review_quality": value, "review_safety": "clear"}), ["품질 Gate 통과"], repr(value))
        for value in ("CLEAR", "ok", "none", False, 0, None, "", ["clear"]):
            self.assertEqual(ip.unconfirmed_review_conditions({"review_quality": "pass", "review_safety": value}), ["건강·안전 차단 없음"], repr(value))

    def test_a_non_dict_entry_confirms_nothing(self):
        for entry in (None, "x", 5, [], ["review_quality"]):
            self.assertEqual(ip.unconfirmed_review_conditions(entry), ["품질 Gate 통과", "건강·안전 차단 없음"])

    def test_the_names_and_values_are_single_constants_the_guide_can_quote(self):
        self.assertEqual((ip.REVIEW_QUALITY_KEY, ip.REVIEW_QUALITY_OK, ip.REVIEW_SAFETY_KEY, ip.REVIEW_SAFETY_OK), ("review_quality", "pass", "review_safety", "clear"))
        self.assertEqual([label for label, _key, _value in ip.REVIEW_LABELS], ["품질 Gate 통과", "건강·안전 차단 없음"])


class RealPolicyFileTest(unittest.TestCase):
    def setUp(self):
        self.text = REAL_PATH.read_text(encoding="utf-8")
        self.policy = ip.parse_policy_text(self.text)

    def test_the_real_file_is_valid_and_small(self):
        self.assertLess(len(self.text.encode("utf-8")), 16000)
        self.assertNotIn(chr(126), self.text)
        self.assertNotRegex(self.text, r"https?://")

    def test_the_planned_pause_is_declared_with_reason_conditions_and_basis_but_the_gate_is_not_passed(self):
        plan = self.policy.planned_pause
        self.assertTrue(plan.declared)
        self.assertEqual(plan.since, "2026-11-09")
        self.assertFalse(plan.resume_gate_passed)          # 켜는 변경은 사람이 검토하는 별도 병합이다
        self.assertGreaterEqual(len(plan.resume_conditions), 5)
        for word in ("2026-11-09", "확인 요청 008"):
            self.assertIn(word, plan.decision_ref)

    def test_the_seven_operator_decisions_of_2026_11_11_are_in_the_data(self):
        decisions = {d.key: d for d in self.policy.decisions}
        blogger = ("blogger:blogger_macat:drafts:202611081745", "blogger:blogger_kcyoon:drafts:202611081938")      # 가장 새 대기 초안의 시각까지 — 그 초안에만 걸린다(새 초안이 오면 풀린다)
        self.assertEqual(set(decisions), {*blogger, "draft:88", "draft:103", "approve:87fc678", "approve:b27b3fb", "approve:8076dcf", "approve:7f2dfdf", "pr:176"})
        self.assertEqual([decisions[k].kind for k in blogger], ["keep", "keep"])
        self.assertEqual([decisions[k].kind for k in ("draft:88", "draft:103")], ["discard_close", "discard_close"])
        for key in ("approve:87fc678", "approve:b27b3fb", "approve:8076dcf", "approve:7f2dfdf", "pr:176"):
            self.assertEqual(decisions[key].kind, "ignore", key)
        for decision_ in decisions.values():
            self.assertEqual(decision_.date, "2026-11-11")

    def test_each_approval_decision_names_the_merged_branch_it_stands_for(self):
        decisions = {d.key: d.reason for d in self.policy.decisions}
        for key, branch in (("approve:87fc678", "M029"), ("approve:b27b3fb", "M034"), ("approve:8076dcf", "M038"), ("approve:7f2dfdf", "M048")):
            self.assertIn(branch, decisions[key], key)

    def test_the_documents_the_basis_points_at_exist(self):
        for rel in ("docs/ARCHITECTURE.md", "docs/PUBLISH_PATHS.md", "docs/OPS_INBOX.md"):
            self.assertTrue((ROOT / rel).is_file(), rel)
        architecture = (ROOT / "docs" / "ARCHITECTURE.md").read_text(encoding="utf-8")
        self.assertIn("## 4-9. 제한 재개 잠금", architecture)
        self.assertIn("4-9", self.policy.planned_pause.decision_ref)

    def test_the_file_is_plain_data_with_a_trailing_newline_and_no_secrets(self):
        self.assertTrue(self.text.endswith("\n"))
        self.assertEqual(json.loads(self.text)["schema_version"], 1)
        self.assertEqual(ip.POLICY_FILE, "pipeline/ops_inbox_policy.json")
        self.assertIsNone(re.search(r"[0-9]{9,}", re.sub(r"drafts:[0-9]{12}", "drafts:", self.text)))      # 계정·채팅 번호처럼 보이는 긴 숫자 없음(Blogger 결정 키 끝의 12자리 시각만 예외)


class StrictPolicyTest(unittest.TestCase):
    """독립 검증 D8·D3(D-287·D-282): 같은 칸이 두 번 있거나·광고·전화 번호 모양이 있거나·오늘보다 뒤의 날짜가 있거나·너무 깊게 중첩된 파일은 전체를 거절한다."""
    TODAY = date(2026, 11, 11)

    def bad(self, data, needle=None):
        with self.assertRaises(ip.PolicyError) as caught:
            ip.parse_policy(data)
        if needle:
            self.assertIn(needle, str(caught.exception))

    def bad_text(self, text, needle=None, today=None):
        with self.assertRaises(ip.PolicyError) as caught:
            ip.parse_policy_text(text, today)
        if needle:
            self.assertIn(needle, str(caught.exception))
        return str(caught.exception)

    def test_a_field_written_twice_is_refused_wherever_it_is(self):
        body = '{"decision": "keep", "date": "2026-11-11", "reason": "a"}'
        texts = ('{"schema_version": 1, "schema_version": 1}',
                 '{"schema_version": 1, "planned_pause": null, "planned_pause": null}',
                 '{"schema_version": 1, "item_decisions": {"draft:1": ' + body + ', "draft:1": ' + body.replace("keep", "ignore") + '}}',
                 '{"schema_version": 1, "item_decisions": {"draft:1": {"decision": "keep", "decision": "ignore", "date": "2026-11-11", "reason": "a"}}}',
                 '{"schema_version": 1, "planned_pause": {"active": true, "active": false}}')
        for text in texts:
            self.assertTrue(self.bad_text(text).startswith("같은 칸이 두 번 있습니다("), text)
        message = self.bad_text(texts[2])
        self.assertIn("draft:1", message)
        for value in ("keep", "ignore"):
            self.assertNotIn(value, message)                                                  # 칸 이름만 싣고 값은 싣지 않는다

    def test_a_repeated_field_is_not_taken_for_a_json_format_error(self):
        self.assertNotIn("JSON 형식 오류", self.bad_text('{"schema_version": 1,\n "schema_version": 1}'))

    def test_a_long_repeated_key_is_cut_in_the_message(self):
        key = "k" * 100
        message = self.bad_text('{"%s": 1, "%s": 2}' % (key, key))
        self.assertIn("k" * 40, message)
        self.assertNotIn("k" * 41, message)

    def test_text_that_looks_like_an_ad_account_or_a_phone_number_is_refused_in_every_text_field(self):
        shapes = ("ca-pub-1234567890123456", "pub-1234567", "CA-PUB-1234567", "ca-app-pub-1234567890123456", "계정 123456789", "채팅 1234567890", "010-1234-5678", "02-123-4567",
                  "031.123.4567", "+82 10 1234 5678", "전화 010 1234 5678")
        for text in shapes:
            self.bad(good(planned_pause=pause(reason=text)), "reason")
            self.bad(good(planned_pause=pause(decision_ref=text)), "decision_ref")
            self.bad(good(planned_pause=pause(resume_conditions=[text])), "resume_conditions[0]")
            self.bad(good(item_decisions={"draft:1": decision(reason=text)}), "reason")
            self.bad(good(_doc=text), "_doc")

    def test_dates_section_numbers_and_short_numbers_are_not_mistaken_for_account_numbers(self):
        for text in ("2026-11-09 결정", "docs/ARCHITECTURE.md 4-9절", "숫자 12345678", "주 1–2편", "하루 1편 · 3일", "v1.2.3", "운영자 승인 2026-11-10(확인 요청 008)", "100%·3.5배"):
            ip.parse_policy(good(planned_pause=pause(reason=text, decision_ref=text, resume_conditions=[text])))
            ip.parse_policy(good(item_decisions={"draft:1": decision(reason=text)}, _doc=text))

    def test_the_error_for_a_number_shape_never_repeats_it(self):
        with self.assertRaises(ip.PolicyError) as caught:
            ip.parse_policy(good(planned_pause=pause(reason="계정 123456789012")))
        self.assertNotIn("123456789", str(caught.exception))

    def test_a_date_after_today_is_refused_when_today_is_given(self):
        data = good(planned_pause=pause(since="2026-11-11"), item_decisions={"draft:1": decision(date="2026-11-11")})
        ip.parse_policy(data, self.TODAY)                                                     # 오늘과 같은 날은 된다
        with self.assertRaises(ip.PolicyError) as caught:
            ip.parse_policy(good(planned_pause=pause(since="2026-11-12")), self.TODAY)
        self.assertIn("planned_pause.since", str(caught.exception))
        self.assertIn("2026-11-11", str(caught.exception))                                    # 오늘 날짜는 알려 준다
        with self.assertRaises(ip.PolicyError) as caught:
            ip.parse_policy(good(item_decisions={"draft:1": decision(date="2026-11-12")}), self.TODAY)
        self.assertIn("item_decisions.draft:1.date", str(caught.exception))
        with self.assertRaises(ip.PolicyError):
            ip.parse_policy(good(planned_pause={"active": False, "since": "2026-11-12"}), self.TODAY)      # 꺼 둔 선언의 시작일도 같다

    def test_without_today_no_date_is_called_a_future_date(self):
        ip.parse_policy(good(planned_pause=pause(since="2999-01-01"), item_decisions={"draft:1": decision(date="2999-01-01")}))
        ip.parse_policy(good(planned_pause=pause(since="2999-01-01")), None)
        ip.parse_policy_text(json.dumps(good(planned_pause=pause(since="2999-01-01")), ensure_ascii=False))

    def test_the_text_entry_point_hands_today_on(self):
        text = json.dumps(good(planned_pause=pause(since="2026-11-12")), ensure_ascii=False)
        self.bad_text(text, "since", self.TODAY)
        ip.parse_policy_text(text, date(2026, 11, 12))

    def test_the_real_file_is_valid_from_its_own_day_on_and_refused_before_its_start(self):
        text = REAL_PATH.read_text(encoding="utf-8")
        ip.parse_policy_text(text, date(2026, 11, 11))
        ip.parse_policy_text(text, date(2030, 1, 1))
        self.bad_text(text, "오늘", date(2026, 11, 8))

    def test_deeply_nested_json_is_a_policy_error_and_never_a_crash(self):
        for text in ("[" * 30000 + "]" * 30000, '{"a":' * 10000 + "1" + "}" * 10000, '{"schema_version": 1, "x": ' + "[" * 20000 + "]" * 20000 + "}"):
            self.assertLessEqual(len(text.encode("utf-8")), ip.MAX_POLICY_BYTES)
            self.assertIn("너무 깊게 중첩", self.bad_text(text))

    def test_a_recursion_or_memory_error_from_the_parser_is_also_a_policy_error(self):
        for error, word in ((RecursionError, "너무 깊게 중첩"), (MemoryError, "메모리가 모자랍니다")):
            with mock.patch.object(ip.json, "loads", side_effect=error()):
                self.assertIn(word, self.bad_text("{}"))

    def test_a_policy_error_from_the_hook_is_not_swallowed_by_the_value_error_branch(self):
        self.assertTrue(issubclass(ip.PolicyError, ValueError))
        self.assertTrue(self.bad_text('{"a": 1, "a": 2}').startswith("같은 칸이 두 번"))


class SeasonFalsePositiveTest(unittest.TestCase):
    """독립 검증 D6(D-285): 사철 쓰는 말과 고유 이름은 철 낱말이 아니다. 남은 오탐·미탐은 한계(docs/OPS_INBOX.md 10-9)."""
    EVERYDAY = ("연말정산 환급 팁", "연말 정산 서류 정리", "보일러 교체 비용", "난방비 아끼는 법", "새 학기 준비물", "새학기 증후군 이겨내기", "겨울왕국 신작 정리", "한여름밤의 꿈 리뷰", "한여름 밤의 꿈 리뷰")

    def test_everyday_titles_are_not_out_of_season_on_any_day_of_the_year(self):
        for title in self.EVERYDAY:
            for ordinal in range(date(2026, 1, 1).toordinal(), date(2027, 1, 1).toordinal()):
                self.assertIsNone(ip.season_review(title, date.fromordinal(ordinal)), (title, date.fromordinal(ordinal)))

    def test_the_words_that_were_taken_out_or_fenced_are_gone_from_the_table(self):
        table = {term[0]: term[1] for term in ip.SEASON_TERMS}
        for word in ("새 학기", "새학기"):
            self.assertIsNone(table["봄"].search(word), word)
        for word in ("보일러", "난방", "난방비"):
            self.assertIsNone(table["겨울"].search(word), word)
        for word in ("연말정산", "연말 정산"):
            self.assertIsNone(table["연말·성탄"].search(word), word)
        self.assertIsNone(table["겨울"].search("겨울왕국"))
        self.assertIsNone(table["여름"].search("한여름밤의 꿈"))
        for name, word in (("연말·성탄", "연말 파티"), ("연말·성탄", "연말"), ("겨울", "겨울"), ("겨울", "한파"), ("여름", "한여름 밤 야식"), ("여름", "여름밤 산책")):
            self.assertIsNotNone(table[name].search(word), (name, word))

    def test_real_season_words_next_to_the_exceptions_are_still_caught(self):
        for title, day in (("한여름 밤 야식 레시피", date(2026, 12, 25)), ("여름밤 산책 코스", date(2026, 12, 25)), ("겨울 이불 정리", date(2026, 7, 1)), ("올겨울 한파 대비", date(2026, 7, 1)),
                           ("연말 모임 장소", date(2026, 7, 1)), ("연말과 연말정산 준비", date(2026, 7, 1)), ("한여름 밤의 꿈과 한여름 냉방", date(2026, 12, 25))):
            self.assertIsNotNone(ip.season_review(title, day), (title, day))

    def test_the_exam_window_runs_through_january(self):
        title = "수능 이후 정시 지원 전략"
        for day in (date(2026, 10, 1), date(2026, 12, 25), date(2027, 1, 31), date(2027, 2, 14)):
            self.assertIsNone(ip.season_review(title, day), day)
        for day in (date(2026, 9, 30), date(2027, 2, 15), date(2027, 7, 1)):
            self.assertEqual(ip.season_review(title, day), ("수능",), day)
        self.assertEqual(ip.season_window_text("수능"), "10월 1일–1월 31일")


if __name__ == "__main__":
    unittest.main()
