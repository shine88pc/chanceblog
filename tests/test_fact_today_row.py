"""S2C0-b — 오늘(UTC) 행·이번 달 행을 버린 사실이 어댑터에서 공급 결과·생성기 요약·그림자 실행 기록까지 올라가는 길과, 그 행을 버려도 글이 달라지지 않는다는 것의 시험.

어댑터 자체(그 행만 쓰지 않음·엄격한 검사·내일 이후 행 거절·오늘 행이 없는 입력은 이전과 바이트까지 같음)는 `tests/test_space_adapter.py` 의 `TodayRowTest` 가 맡는다. 여기서는 위쪽 층을 본다:
① 공급 함수가 오늘 행이 든 일별 흑점수 응답으로도 글을 만들고(전에는 `ADAPTER:BAD_SHAPE` 로 그 글감이 통째로 건너뛰어졌다 — 그림자 1회차의 다섯째 글감) 버린 행의 기록을 `SupplyResult.notes` 로 올린다 ② 그 기록은 건너뜀(`skipped`)이 아니라
알림이라 글을 못 만든 날의 결과 코드를 바꾸지 않는다 ③ 같은 값에서 오늘 행이 있든 없든 글은 바이트까지 같다 ④ 생성기의 요약 줄(`fact_notes`)과 그림자 실행의 `run.json` 메모에 제품마다 한 줄이 남는다 ⑤ 내일 이후 행은 글감 하나가 건너뛰어진다(제품 전체 거절).
네트워크·시계 없음(가짜 transport)."""
import unittest

import _bootstrap  # noqa: F401
import fact_branch_helpers as FB
import generator as g
import hold_helpers as HH
import space_helpers as H
import test_fact_shadow as TS

from pipeline import fact_supply as S

setUpModule, tearDownModule = HH.module_fixtures()      # 이 모듈은 글감 여섯 전부를 읽는 흐름을 본다 — 임시 제외·처음 낼 글감 상수를 비워 돌린다(기본 상수의 동작은 tests/test_fact_hold.py)

DAY = "2026-11-10"
RETRIEVED = "2026-11-10T01:12:00Z"                                # 협정 세계시도 11월 10일 — 오늘(UTC)이 DAY 다
DAILY_NOTE = "ssn_daily: 오늘(UTC 2026-11-10) 날짜의 일별 값 1개는 끝나지 않은 날이라 쓰지 않았습니다"
MONTHLY_NOTE = "ssn_monthly: 이번 달(UTC 2026-11) 월평균 값 1개는 끝나지 않은 달이라 쓰지 않았습니다"
PROVIDER = H.provider(attribution_template=H.B_TEMPLATE)


def noaa_scene(today_row=False, current_month_row=False, tomorrow_row=False):
    """가상 응답 — 일별 흑점수는 어제까지가 보통이고, today_row 면 마지막 행이 오늘(UTC), tomorrow_row 면 내일. current_month_row 면 월별에 이번 달(2026-11) 행을 더한다."""
    noaa = FB.FakeNoaa(DAY)
    if today_row or tomorrow_row:
        noaa.by_product["ssn_daily"] = H.ssn_daily_rows("2026-11-11" if tomorrow_row else DAY, 71)
    if current_month_row:
        rows = H.ssn_monthly_rows("2026-10", 70)
        noaa.by_product["ssn_monthly"] = rows + [dict(rows[-1], **{"time-tag": "2026-11"})]
    return noaa


def supply(noaa, history=(), **kwargs):
    kwargs.setdefault("limit", 10)
    return S.supply(today=DAY, retrieved_at=RETRIEVED, history=list(history), provider=PROVIDER, opener=noaa.transport, **kwargs)


def ids(result):
    return [candidate.spec.spec_id for candidate in result.candidates]


class SupplyNotesTest(unittest.TestCase):
    def test_a_response_with_the_row_of_today_still_makes_the_daily_sunspot_post_and_the_dropped_row_is_reported(self):
        result = supply(noaa_scene(today_row=True))
        self.assertIn("sunspot_daily_monthly", ids(result))
        self.assertNotIn(("sunspot_daily_monthly", "ADAPTER:BAD_SHAPE"), result.skipped)                    # 전에는 제품 전체가 거절되어 이 글감이 건너뛰어졌다
        self.assertEqual(result.skipped, ())
        self.assertEqual(result.notes, (DAILY_NOTE,))

    def test_without_a_dropped_row_there_is_no_note_at_all(self):
        result = supply(noaa_scene())
        self.assertEqual(result.notes, ())
        self.assertEqual(len(result.posts), 5)
        self.assertEqual(result.skipped, ())

    def test_both_products_report_in_the_order_they_were_read_and_each_only_once(self):
        result = supply(noaa_scene(today_row=True, current_month_row=True))
        self.assertEqual(result.notes, (DAILY_NOTE, MONTHLY_NOTE))
        self.assertEqual(len(result.posts), 5)
        again = supply(noaa_scene(today_row=True, current_month_row=True), limit=1)                           # 그 제품을 읽지 않은 실행에는 기록도 없다
        self.assertEqual(again.notes, ())

    def test_a_row_after_today_still_skips_that_one_subject_with_a_fixed_reason_and_no_note(self):
        result = supply(noaa_scene(tomorrow_row=True))
        self.assertIn(("sunspot_daily_monthly", "ADAPTER:BAD_SHAPE"), result.skipped)
        self.assertEqual(result.notes, ())
        self.assertEqual(len(result.posts), 4)                                                              # 나머지 글감은 그대로 글이 된다

    def test_the_post_is_byte_for_byte_the_same_with_or_without_the_row_of_today(self):
        with_today, without = supply(noaa_scene(today_row=True)), supply(noaa_scene())
        key = {candidate.spec.spec_id: post for candidate, post in zip(with_today.candidates, with_today.posts)}
        other = {candidate.spec.spec_id: post for candidate, post in zip(without.candidates, without.posts)}
        self.assertEqual(sorted(key), sorted(other))
        for spec_id in key:
            self.assertEqual((key[spec_id].title, key[spec_id].body_markdown, key[spec_id].dedupe_key), (other[spec_id].title, other[spec_id].body_markdown, other[spec_id].dedupe_key), spec_id)
        self.assertEqual(key["sunspot_daily_monthly"].as_of, "2026-11-09")                                    # 마지막 기준일은 어제(UTC)다

    def test_a_note_is_not_a_skip_so_a_day_without_posts_keeps_its_outcome_reasons(self):
        result = supply(noaa_scene(today_row=True), accept=lambda post, candidate: "NO")
        self.assertEqual(result.posts, ())
        self.assertTrue(result.skipped)
        self.assertTrue(all(code == "REJECTED:NO" for _spec, code in result.skipped))                       # 건너뜀 사유는 거절뿐 — 기록이 사유 목록에 섞이지 않는다
        self.assertEqual(result.notes, (DAILY_NOTE,))

    def test_the_result_type_keeps_its_old_shape_and_defaults(self):
        self.assertEqual(S.SupplyResult(), S.SupplyResult(notes=()))
        self.assertEqual(S.SupplyResult().notes, ())
        old_style = S.SupplyResult((), (), (), "", ())
        self.assertEqual(old_style.notes, ())
        for bad in ("2026-13-01", None):                                                                    # 입력이 이상한 결과에도 기록 칸은 있다
            self.assertEqual(S.supply(today=bad, retrieved_at=RETRIEVED, history=[], provider=PROVIDER, opener=lambda *a, **k: b"").notes, ())


class GeneratorLinesTest(FB.FactEnv):
    """생성기의 Fact 분기 요약 줄(`fact_notes`)과 실제 실행: 처음 낼 글감을 일별 흑점수로 정해 그 글감이 먼저 읽히게 한다."""

    def test_the_summary_lines_name_the_dropped_row_once_and_the_post_is_made(self):
        self.noaa.by_product["ssn_daily"] = H.ssn_daily_rows(DAY, 71)
        with HH.policy((), ("sunspot_daily_monthly",)):
            value, report, out, error = self.run_branch()
        self.assertIsNone(error, error)
        self.assertIsNotNone(value, report)
        self.assertEqual(self.history()[-1]["candidate_key"], "space_weather.sunspot_daily_monthly:2026-11")
        self.assertEqual(report["fact_notes"], [f"Fact 제품 {DAILY_NOTE}"])
        self.assertIn(f"  Fact 제품 {DAILY_NOTE}", out)

    def test_a_normal_run_without_a_dropped_row_prints_no_such_line(self):
        with HH.policy((), ("sunspot_daily_monthly",)):
            value, report, out, error = self.run_branch()
        self.assertIsNone(error, error)
        self.assertIsNotNone(value, report)
        self.assertEqual(report["fact_notes"], [])
        self.assertNotIn("쓰지 않았습니다", out)

    def test_the_lines_come_after_the_skip_and_wait_lines_in_a_fixed_order(self):
        result = S.SupplyResult(skipped=(("kp_weekly", "INSUFFICIENT:NO_ANALYSIS"),), waiting="sunspot_daily_monthly", notes=(DAILY_NOTE, MONTHLY_NOTE))
        self.assertEqual(g.fact_notes(result), ["Fact 글감 kp_weekly 건너뜀: INSUFFICIENT:NO_ANALYSIS", "Fact 글감 sunspot_daily_monthly 은(는) 일별 제품의 협정 세계시 하한 때문에 기다림",
                                                   f"Fact 제품 {DAILY_NOTE}", f"Fact 제품 {MONTHLY_NOTE}"])
        self.assertEqual(g.fact_notes(S.SupplyResult()), [])


class ShadowNotesTest(TS.ShadowFactsBase):
    """그림자 1회차(한국 08:39 = 협정 세계시 23:39)에서 다섯째 글감이 통째로 건너뛰어진 일을 다시 만든다 — 이제 그 글감도 평가되고 run.json 의 메모에 버린 행이 남는다."""

    def test_the_daily_sunspot_subject_is_evaluated_and_the_run_notes_name_the_dropped_row(self):
        self.noaa.by_product["ssn_daily"] = H.ssn_daily_rows(DAY, 71)
        info, _lines = self.run_shadow("5")
        titles = [result["title_ko"] for result in self.results().values()]
        self.assertEqual(info["attempts"], 5)
        self.assertTrue(any("일별 흑점수" in title for title in titles), titles)                                 # 전에는 이 글감이 BAD_SHAPE 로 건너뛰어져 4편이었다
        self.assertEqual(self.run_info()["notes"], [f"Fact 제품 {DAILY_NOTE}"])
        self.assertEqual(info, self.run_info())

    def test_without_a_dropped_row_the_run_json_notes_stay_empty(self):
        info, _lines = self.run_shadow("5")
        self.assertEqual(info["attempts"], 5)
        self.assertEqual(self.run_info()["notes"], [])

    def test_a_row_after_today_still_makes_the_daily_subject_a_skip_with_the_reason_in_the_notes(self):
        self.noaa.by_product["ssn_daily"] = H.ssn_daily_rows("2026-11-11", 71)
        info, _lines = self.run_shadow("5")
        self.assertEqual(info["attempts"], 4)
        self.assertEqual(self.run_info()["notes"], ["Fact 글감 sunspot_daily_monthly 건너뜀: ADAPTER:BAD_SHAPE"])


if __name__ == "__main__":
    unittest.main()
