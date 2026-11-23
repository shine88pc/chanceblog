"""같은 날 거절이 이어질 때 NOAA 를 실행마다 다시 읽는 증폭의 크기를 못박는다(BP-S1-4, 결함 D-416 — 열린 한계의 문서화). 네트워크 없이 돈다(가짜 transport).

이 시험은 '고쳤다'를 보증하지 않고 '열려 있다'는 사실의 크기를 지킨다: 닫으려면 실행 사이를 잇는 영구 상태(새 파일·워크플로 변경 — T3)가 필요해 구현하지 않았다.
증폭을 닫는 변경이 들어오면 이 시험의 특성 단언이 빨개진다 — 그때 `docs/SOURCE_POLICY.md` 12절의 줄과 `docs/OPS_INBOX.md` §10-11 끝 점검표의 H8 행을 함께 고친다.
"""
import datetime
import json
import re
import unittest

import _bootstrap
import generator as g

ROOT = _bootstrap.ROOT
DOC = (ROOT / "docs" / "SOURCE_POLICY.md").read_text(encoding="utf-8")


def section_12():
    start = DOC.index("## 12. 한계와 남은 일")
    return DOC[start:DOC.index("\n## 13. ", start)]


class AmplificationCharacterizationTest(unittest.TestCase):
    def test_a_day_of_refused_runs_reads_noaa_many_times_more_than_the_approved_own_cap(self):
        now = datetime.datetime(2026, 11, 24, 10, 17, tzinfo=g.KST)
        problems, sources, provider, access = g.fact_context(now)
        self.assertEqual(problems, [], problems)
        own = access.rate_limit.own
        per_run = []
        for _run in range(30):
            calls = []

            def transport(url, *, timeout, max_bytes):
                calls.append(url)
                return b"<html>not json</html>"

            prepared, result = g.fact_prepare(now, [], sources, provider, access, 1, None, transport)
            self.assertEqual(prepared, [])
            self.assertTrue(result.skipped)
            per_run.append(len(calls))
        self.assertEqual(len(set(per_run)), 1, per_run)                          # 실행마다 똑같이 되풀이한다(상태가 없다)
        self.assertGreaterEqual(per_run[0], 2, per_run)
        self.assertGreater(sum(per_run), 5 * own.max_calls_per_day, (sum(per_run), own.max_calls_per_day))      # 하루 30번 실행이면 자체 상한(하루)의 다섯 배를 넘는다
        self.assertGreater(sum(per_run), own.max_calls_per_month, (sum(per_run), own.max_calls_per_month))      # 하루 만에 월 상한도 넘는다


class AmplificationDocTest(unittest.TestCase):
    def test_section_12_states_the_size_and_why_it_is_open(self):
        text = section_12()
        start = text.index("**같은 날 거절이 이어지면 예약 실행마다 NOAA 를 다시 읽는다**")
        bullet = text[start:text.index("\n", start)]
        for needle in ("BP-S1-4", "D-416", "`BAD_SHAPE`", "`BAD_JSON`", "한 실행 4번", "120번", "하루 8번·월 100번", "영구 상태", "T3", "tests/test_source_amplification_doc.py"):
            self.assertIn(needle, bullet, needle)
        self.assertNotIn(chr(126), bullet)                                       # 문서 규칙: ASCII 물결표 금지
        self.assertIsNone(re.search(r"https?://", bullet))                       # 문서 규칙: 링크 금지

    def test_the_numbers_in_the_doc_are_the_registry_numbers(self):
        data = json.loads((ROOT / "pipeline" / "source_registry.json").read_text(encoding="utf-8"))
        provider = next(p for p in data["providers"] if p.get("provider_id") == "noaa_swpc_json" or p.get("id") == "noaa_swpc_json")
        found = []

        def walk(node):
            if isinstance(node, dict):
                if "max_calls_per_day" in node:
                    found.append((node["max_calls_per_day"], node.get("max_calls_per_month")))
                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for value in node:
                    walk(value)

        walk(provider)
        self.assertEqual(found, [(8, 100)])                                      # 문서가 말하는 자체 상한 하루 8번·월 100번

    def test_the_open_limit_has_a_register_row_and_a_checklist_row(self):
        register = (ROOT / "docs" / "DEFECT_REGISTER.md").read_text(encoding="utf-8")
        row = next(line for line in register.splitlines() if line.startswith("| **D-416** |"))
        self.assertIn("**열림(문서화)**", row)
        self.assertIn("T3", row)
        ops = (ROOT / "docs" / "OPS_INBOX.md").read_text(encoding="utf-8")
        self.assertIn("| H8 증폭 한계 |", ops)


if __name__ == "__main__":
    unittest.main()
