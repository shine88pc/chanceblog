"""워치독 주 단위 보완(결함 D-169 해소, 결정 D-220–D-224)의 문서가 코드와 같은 말을 한다 — 표류 방지 시험(선례: test_publish_paths 의 WeeklyCapDocumentTest).

본다: ① docs/PUBLISH_PATHS.md §7-22(옛 '워치독이 주간 상한을 모른다' 문장이 없고, 새 규칙·고르지 않은 대안 둘(한 줄씩)·한계가 있다)·§8 L-20·§9·쉬운 설명 표
② docs/DEFECT_REGISTER.md 의 D-169 해소와 D-220–D-224 행(칸 수·낱말·번호가 겹치지 않음) ③ docs/ARCHITECTURE.md §4-2 의 표와 새 문단 ④ docs/ACTIONS_GUIDE.md 3-22·6-5
⑤ 문서가 대는 숫자(204시간·7일·8.5일·66000칸·140번 중 110·90번)가 코드·시험의 실제 값과 같다 ⑥ 새로 쓴 부분에 물결표·웹 링크·Liquid 구문이 없다.
다른 가지가 쓰는 번호 대역(D-170–D-219·L-21 이후)의 값이나 전체 최댓값은 못박지 않는다. 파일만 읽는다(네트워크 없음).
"""
import re
import sys
import unittest

import _bootstrap
import test_health_weekly as weekly
from pipeline import health, publish_lock

sys.path.insert(0, str(_bootstrap.ROOT / "scripts"))
import watchdog  # noqa: E402

ROOT = _bootstrap.ROOT
DOCS = ROOT / "docs"
PATHS = (DOCS / "PUBLISH_PATHS.md").read_text(encoding="utf-8")
REGISTER = (DOCS / "DEFECT_REGISTER.md").read_text(encoding="utf-8")
ARCH = (DOCS / "ARCHITECTURE.md").read_text(encoding="utf-8")
GUIDE = (DOCS / "ACTIONS_GUIDE.md").read_text(encoding="utf-8")

SECTION_7 = PATHS[PATHS.index("## 7. 한계와 남은 위험"):PATHS.index("## 8. 설계 결정")]
SECTION_8 = PATHS[PATHS.index("## 8. 설계 결정"):PATHS.index("## 9. 켜는 변경이 일부러 깨뜨리는 시험 고정값")]
SECTION_9 = PATHS[PATHS.index("## 9. 켜는 변경이 일부러 깨뜨리는 시험 고정값"):]
EASY = PATHS[PATHS.index("## 쉬운 설명"):PATHS.index("## 1. 한눈에 보기")]
ITEM_22 = SECTION_7[SECTION_7.index("22. **켠 직후"):]
GUIDE_3_22 = GUIDE[GUIDE.index("### 3-22. 제한 재개 잠금"):GUIDE.index("## 4. 점검 루틴과 키 교체")]
GUIDE_6_5 = GUIDE[GUIDE.index("| `STALE` | 심각 | 마지막 글(또는 초안)"):GUIDE.index("| `RUN_FAIL_STREAK` | 심각 | 그 워크플로가 최근 3회 연속 빨강")]
ARCH_4_2 = ARCH[ARCH.index("## 4-2. 워치독 규칙과 알림 방식"):ARCH.index("### 4-2-1. 초안 모델과 초안 현황")]
ARCH_PARAGRAPH = ARCH_4_2[ARCH_4_2.index("**주 단위 기준 — 제한 재개 잠금 아래의 Chance"):].split("\n\n", 1)[0]


def row(text, start):
    lines = [line for line in text.splitlines() if line.startswith(start)]
    assert len(lines) == 1, "%r 로 시작하는 줄이 %d개" % (start, len(lines))
    return lines[0]


def d_row(number):
    return row(REGISTER, "| **D-%d** |" % number)


class PublishPathsDocumentTest(unittest.TestCase):
    def test_item_22_no_longer_says_the_watchdog_does_not_know_and_says_the_new_rule(self):
        self.assertNotIn("워치독이 주간 상한을 모른다", PATHS)
        self.assertNotIn("이 작업은 워치독을 바꾸지 않았다", PATHS)
        for needle in ("22. **켠 직후 일주일은 켜기 전의 글도 센다, 그리고 워치독은 주 단위 기준으로 바뀐다**", "(결함 D-169 해소, D-220–D-224)", "`weekly_cap`(기본 `None` = 이전과 같음, 키워드 전용)",
                       "`chance_weekly_cap`", "`lock_active`·`lock_key_problems`·`lock_errors`·`weekly_posts_limit`", "`WEEK_WINDOW_DAYS`(7일) × 24시간", "Chance 36 → 204시간", "'주 단위 기준(상한 N편)'",
                       "`NO_POSTS_DAY` 는 울리지 않는다", "`DRAFT_WAITING` 변환", "새 허용 시간 기준으로 `STALE` 이 울릴 때만 일어난다", "새 알림(정보 이슈)은 만들지 않는다", "바이트까지 같다",
                       "`pipeline/blogs.json`(`health.max_gap_hours` 포함)과 `.github/` 워크플로는 바꾸지 않았다"):
            self.assertIn(needle, ITEM_22, needle)

    def test_the_two_alternatives_and_the_limit_are_one_line_each(self):
        lines = ITEM_22.splitlines()
        alternatives = [line for line in lines if line.startswith("    - 고르지 않은 대안 (")]
        self.assertEqual([re.match(r"    - 고르지 않은 대안 \((가|나)\)", line).group(1) for line in alternatives], ["가", "나"])
        self.assertIn("설정값 `max_gap_hours` 만 204 로 올림", alternatives[0])
        self.assertIn("T3", alternatives[0])
        self.assertIn("잠금을 끄면 다시 되돌려야", alternatives[0])
        self.assertIn("경보를 그대로 두고 운영자가 무시", alternatives[1])
        self.assertIn("거짓 경보", alternatives[1])
        reason = next(line for line in lines if line.startswith("    - 이 방식을 고른 이유:"))
        for needle in ("코드가 잠금·상한에서 스스로 파생하므로 켜는 변경 하나로 끝나고", "잠금을 끄면 저절로 이전 기준으로 돌아가", "경보가 더 울리는 쪽", "바이트까지 같아 되돌리기 쉽다"):
            self.assertIn(needle, reason, needle)
        self.assertLess(lines.index(reason), lines.index(alternatives[0]))                                       # 고른 이유가 고르지 않은 대안 앞에 있다
        limit = next(line for line in lines if line.startswith("    - 한계:"))
        for needle in ("204시간(8.5일)", "미관측", "승인이 평소보다 밀려 마지막 병합 뒤 204시간을 넘기면 `DRAFT_WAITING`(경고)이 울리고", "`WeeklySimulationTest`"):
            self.assertIn(needle, limit, needle)

    def test_the_numbers_in_the_text_are_the_code_values(self):
        self.assertEqual(36 + health.WEEKLY_EXTRA_HOURS, 204)
        self.assertEqual(health.WEEKLY_EXTRA_HOURS, publish_lock.WEEK_WINDOW_DAYS * 24)
        self.assertEqual(204 / 24, 8.5)
        self.assertIn("7일", ITEM_22)

    def test_the_decision_row_l20_follows_the_numbering_and_has_three_cells(self):
        ids = re.findall(r"(?m)^\| (L-\d+) \|", SECTION_8)
        self.assertEqual(ids, ["L-%d" % number for number in range(1, len(ids) + 1)])
        self.assertIn("L-20", ids)
        decision = row(SECTION_8, "| L-20 |")
        self.assertEqual(decision.count("|"), 4)
        for needle in ("워치독은 제한 재개 잠금이 켜져 있고", "Chance 에만 주 단위 기준으로 점검한다", "`WEEK_WINDOW_DAYS` × 24시간(36 → 204)", "`NO_POSTS_DAY` 없음", "키워드를 넘기지 않아 지금과 바이트까지 같다",
                       "고르지 않았다(§7-22, D-220–D-224)"):
            self.assertIn(needle, decision, needle)

    def test_section_9_says_the_watchdog_question_is_resolved(self):
        self.assertNotIn("**켜기 전에 정할 것(주간 상한이 만드는 부수 효과)**", PATHS)
        paragraph = row(SECTION_9, "**워치독의 '글이 안 나옴' 알림(결함 D-169 — 해결)**")
        for needle in ("§7-22, D-220–D-224", "켜는 변경이 따로 할 일은 없다", "204시간", "`health.max_gap_hours` 값은 그대로"):
            self.assertIn(needle, paragraph, needle)

    def test_the_easy_explanation_table_has_the_watchdog_row(self):
        line = row(EASY, "| 워치독(`watchdog.yml`)은 Chance 만 **주 단위 기준**으로 본다")
        self.assertEqual(line.count("|"), 3)
        for needle in ("설정값 36시간에 7일을 더한 204시간", "`NO_POSTS_DAY`", "이전 기준 그대로(§7-22)"):
            self.assertIn(needle, line, needle)


class DefectRegisterTest(unittest.TestCase):
    def test_d169_is_resolved_and_keeps_its_words(self):
        line = d_row(169)
        self.assertEqual(line.count("|"), 7)
        self.assertIn("**해결**(2026-11-10", line)
        self.assertNotIn("**열림**", line)
        for needle in ("워치독", "STALE", "NO_POSTS_DAY", "max_gap_hours", "§7-22", "D-220–D-224", "`weekly_cap`"):
            self.assertIn(needle, line, needle)

    def test_the_new_rows_exist_once_with_six_cells_and_their_words(self):
        ids = re.findall(r"(?m)^\| \*\*(D-\d+)\*\* \|", REGISTER)
        self.assertEqual(len(ids), len(set(ids)))
        words = {220: ("`evaluate(..., weekly_cap=None)`", "`chance_weekly_cap(reg)`", "`tests/test_health_weekly.py`", "`tests/test_watchdog_weekly.py`", "**해결**"),
                 221: ("설정값 + 7일(Chance 36 → 204시간)", "고르지 않은 대안: (가)", "(나)", "T3", "**결정**"),
                 222: ("`NO_POSTS_DAY` 는 울리지 않는다", "`DRAFT_WAITING` 변환", "`WeeklyDifferentialTest`", "**결정**"),
                 223: ("주 단위로 읽지 않고 이전 기준 그대로 두는 경우", "바이트까지 같고", "레지스트리를 읽지 못함", "Chance 가 아닌 블로그", "**결정**"),
                 224: ("204시간(8.5일)", "미관측", "D-168", "**열림**", "승인이 평소보다 밀려 마지막 병합 뒤 204시간을 넘기면 `DRAFT_WAITING`(경고")}
        for number, needles in words.items():
            with self.subTest(row="D-%d" % number):
                self.assertEqual(ids.count("D-%d" % number), 1)
                line = d_row(number)
                self.assertEqual(line.count("|"), 7)
                for needle in needles:
                    self.assertIn(needle, line, needle)
                self.assertNotIn("LOCK_WEEKLY_CAP", line)                      # 이 이름을 가진 행은 다른 묶음(D-166–D-169)의 것이다 — test_publish_paths 가 D-170 이후 행에서 이 이름을 금지한다

    def test_the_header_names_the_new_rows(self):
        self.assertIn("> D-220–D-224 는 2026-11-10 에 추가했다(워치독 주 단위 보완 — D-169 해소, `docs/PUBLISH_PATHS.md` §7-22).", REGISTER)

    def test_the_numbers_in_the_rows_are_the_measured_values(self):
        """D-220 의 '6만 6천 칸'·'140번 가운데 상한 1 에서 110번·상한 2 에서 90번' 은 시험이 실제로 세는 값이다."""
        self.assertEqual(weekly.OFF_STATE_DIGEST[1], 66000)
        self.assertIn("같은 입력 격자(6만 6천 칸)", d_row(220))
        counts = {}
        for cap in (1, 2):
            runs, _ = weekly.simulate(cap, weekly=False)
            counts[cap] = (len(runs), sum(1 for _, found in runs if found))
        self.assertEqual(counts, {1: (140, 110), 2: (140, 90)})
        self.assertIn("점검 140번 가운데 상한 1 에서 110번·상한 2 에서 90번 울렸고 새 기준은 0번이다", d_row(220))
        self.assertIn("70일 치", d_row(220))

    def test_d221_numbers_are_what_the_simulation_shows(self):
        text = d_row(221)
        self.assertIn("약 183시간", text)
        self.assertIn("약 207시간", text)
        # 마지막 글(START 09:17 KST) 뒤 8일째·9일째 00:30 점검까지의 시간을 직접 잰다 — 문서의 숫자가 흉내가 만드는 값과 같다
        last_post = weekly.datetime(weekly.START.year, weekly.START.month, weekly.START.day, 9, 17, tzinfo=weekly.KST)
        for days_later, expected in ((8, 183), (9, 207)):
            check = weekly.datetime(weekly.START.year, weekly.START.month, weekly.START.day, 0, 30, tzinfo=weekly.KST) + weekly.timedelta(days=days_later)
            self.assertEqual(int((check - last_post).total_seconds() / 3600), expected)
        failed = weekly.timedelta(days=7)
        one_day, _ = weekly.simulate(1, failed={weekly.START + failed})
        two_days, _ = weekly.simulate(1, failed={weekly.START + failed, weekly.START + failed + weekly.timedelta(days=1)})
        self.assertEqual([found for _, found in one_day if found], [])                                         # 183시간은 허용 204시간 안이다
        self.assertEqual([(when.day, found) for when, found in two_days if found], [((weekly.START + weekly.timedelta(days=9)).day, ["STALE"])])


class ArchitectureDocumentTest(unittest.TestCase):
    def test_the_table_rows_and_the_intro_name_the_weekly_basis(self):
        self.assertIn("**제한 재개 잠금(§4-9)이 켜진 뒤의 Chance 는 주 단위 기준**으로 본다", ARCH_4_2)
        stale = row(ARCH_4_2, "| `STALE` | 심각 |")
        self.assertIn("**주 단위 기준**(제한 재개 잠금이 켜진 Chance): 허용 시간이 `max_gap_hours` + 7일(36 → 204시간)", stale)
        self.assertTrue(stale.endswith(" |"))
        self.assertEqual(stale.count("|"), 4)
        posts_day = row(ARCH_4_2, "| `NO_POSTS_DAY` | 경고 / 심각 |")
        self.assertIn("주 단위 기준(제한 재개 잠금이 켜진 Chance)에서는 울리지 않는다", posts_day)
        self.assertEqual(posts_day.count("|"), 4)
        self.assertIn("제한 재개 잠금이 켜진 Chance 는 `max_gap_hours` 에 7일을 더한 값으로 본다", row(ARCH, "| `health` | 워치독 기준:"))

    def test_the_new_paragraph_names_the_functions_that_exist(self):
        for needle in ("(결함 D-169 해소, D-220–D-224)", "`weekly_cap`(기본 `None` = 이전과 같음)", "`chance_weekly_cap`", "`WEEK_WINDOW_DAYS`(7일) × 24시간(Chance 36 → 204시간)", "`NO_POSTS_DAY` 없음",
                       "`DRAFT_WAITING` 변환(새 허용 시간 기준으로 `STALE` 이 울릴 때만)", "출력이 바이트까지 같다", "`[참고] chance: 주 단위 기준으로 점검합니다…`", "[`PUBLISH_PATHS.md`](./PUBLISH_PATHS.md) §7-22",
                       "`tests/test_health_weekly.py`", "`tests/test_watchdog_weekly.py`", "`tests/test_watchdog_weekly_docs.py`"):
            self.assertIn(needle, ARCH_PARAGRAPH, needle)
        self.assertTrue(callable(watchdog.chance_weekly_cap))
        self.assertTrue(callable(health.weekly_mode_cap))
        source = (ROOT / "scripts" / "watchdog.py").read_text(encoding="utf-8")
        self.assertIn("주 단위 기준으로 점검합니다", source)            # 문서가 말하는 실행 로그 줄이 코드에 실제로 있다
        self.assertEqual(ARCH_4_2.count("**주 단위 기준 — 제한 재개 잠금 아래의 Chance"), 1)

    def test_the_alert_path_table_is_untouched(self):
        """§4-5 의 '경로별 알림' 표 행(test_draft_followups 가 못박는다)은 이 일이 바꾸지 않는다."""
        line = row(ARCH, "| 워치독 이슈 |")
        self.assertIn("`STALE`(경고)이 함께 남는다(R2-2)", line)
        self.assertNotIn("주 단위", line)


class OperatorGuideTest(unittest.TestCase):
    def test_section_3_22_has_the_new_row_and_the_new_limit_sentence(self):
        line = row(GUIDE_3_22, "| 워치독의 '글이 안 나옴' 알림(Chance) |")
        self.assertEqual(line.count("|"), 4)
        for needle in ("마지막 글 36시간 뒤 `STALE`(심각)", "주 단위 기준 — 마지막 글 204시간(설정값 36시간에 7일을 더함) 뒤에야 `STALE`", "`NO_POSTS_DAY` 는 울리지 않음(6-5)"):
            self.assertIn(needle, line, needle)
        limit = row(GUIDE_3_22, "**알아 둘 한계**")
        self.assertNotIn("아직 그것을 모릅니다", GUIDE)
        self.assertNotIn("켜기 전에 정합니다(PUBLISH_PATHS §7-22", GUIDE)
        for needle in ("그래서 워치독은 켠 뒤 Chance 만 주 단위 기준으로 점검합니다", "설정값 36시간에 7일을 더한 204시간", "'어제 새 글이 없음'(`NO_POSTS_DAY`)은 알리지 않습니다", "잠금이 꺼져 있으면 이전 기준 그대로입니다",
                       "PUBLISH_PATHS §7-22, 결함 D-169·D-220", "8일 반"):
            self.assertIn(needle, limit, needle)

    def test_the_routine_check_lines_know_the_weekly_basis(self):
        routine = row(GUIDE, "| (선택) 매일 1분 | 사이트 최신 글 |")
        self.assertIn("마지막 글이 36시간 이내(제한 재개 잠금을 켠 뒤에는 주 1–2편이 정상이라 204시간 이내, 3-22)", routine)
        self.assertEqual(routine.count("|"), 5)
        sign = row(GUIDE, "- **이상 신호**: 빨강, 며칠째 같은 노란 경고")
        self.assertIn("마지막 글이 36시간을 넘음(제한 재개 잠금을 켠 뒤에는 204시간을 넘음, 3-22)", sign)

    def test_section_6_5_rows_and_section_3_2_say_the_same(self):
        for needle in ("제한 재개 잠금(3-22)을 켠 뒤의 Chance 는 주 단위 기준이라 마지막 글 204시간 뒤에 울립니다(설정값 36시간에 7일을 더함, 문구에 '주 단위 기준'이 붙음)",
                       "제한 재개 잠금(3-22)을 켠 뒤의 Chance 는 주 1–2편이 정상이라 이 알림이 울리지 않습니다"):
            self.assertIn(needle, GUIDE_6_5, needle)
        line = row(GUIDE, "- **할 일**: Summary의 결과 코드")
        self.assertIn("제한 재개 잠금(3-22)을 켠 뒤에는 Chance 가 주 단위 기준이라 마지막 글 204시간 뒤에야 `STALE` 이 울리고 `NO_POSTS_DAY` 는 울리지 않습니다(6-5). 급하면 3-1.", line)
        self.assertTrue(line.endswith("급하면 3-1."))


class NewTextRulesTest(unittest.TestCase):
    """새로 쓴 부분에는 물결표·웹 링크·Liquid 구문·내 PC 경로가 없다."""

    def chunks(self):
        stale_addition = row(ARCH_4_2, "| `STALE` | 심각 |").split("**주 단위 기준**(제한 재개 잠금이 켜진 Chance)", 1)[1]
        guide_stale = GUIDE_6_5.split("제한 재개 잠금(3-22)을 켠 뒤의 Chance 는 주 단위 기준이라", 1)[1].split(" | ", 1)[0]
        guide_posts_day = GUIDE_6_5.split("제한 재개 잠금(3-22)을 켠 뒤의 Chance 는 주 1–2편이 정상이라", 1)[1].split(" | ", 1)[0]
        return {"PUBLISH_PATHS 7-22": ITEM_22, "PUBLISH_PATHS L-20": row(SECTION_8, "| L-20 |"), "PUBLISH_PATHS 9": row(SECTION_9, "**워치독의 '글이 안 나옴' 알림(결함 D-169 — 해결)**"),
                "PUBLISH_PATHS easy": row(EASY, "| 워치독(`watchdog.yml`)은 Chance 만"), "ARCHITECTURE paragraph": ARCH_PARAGRAPH, "ARCHITECTURE STALE": stale_addition,
                "ARCHITECTURE NO_POSTS_DAY": row(ARCH_4_2, "| `NO_POSTS_DAY` | 경고 / 심각 |"), "ARCHITECTURE health": row(ARCH, "| `health` | 워치독 기준:"),
                "GUIDE 3-22 row": row(GUIDE_3_22, "| 워치독의 '글이 안 나옴' 알림(Chance) |"), "GUIDE 3-22 limit": row(GUIDE_3_22, "**알아 둘 한계**"), "GUIDE 6-5 STALE": guide_stale,
                "GUIDE 6-5 NO_POSTS_DAY": guide_posts_day, "GUIDE routine": row(GUIDE, "| (선택) 매일 1분 | 사이트 최신 글 |"), "GUIDE abnormal sign": row(GUIDE, "- **이상 신호**: 빨강, 며칠째 같은 노란 경고"), "DEFECT 169": d_row(169), "DEFECT 220": d_row(220), "DEFECT 221": d_row(221), "DEFECT 222": d_row(222), "DEFECT 223": d_row(223),
                "DEFECT 224": d_row(224)}

    def test_no_tilde_no_web_link_no_liquid_no_local_path(self):
        for name, chunk in self.chunks().items():
            with self.subTest(chunk=name):
                self.assertNotIn("~", chunk)
                self.assertIsNone(re.search(r"https?://", chunk))
                self.assertNotIn("{{", chunk)
                self.assertNotIn("{%", chunk)
                self.assertIsNone(re.search(r"[A-Za-z]:[\\/]", chunk))


if __name__ == "__main__":
    unittest.main()
