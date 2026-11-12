"""소스 정책 모듈(pipeline/source_policy.py)의 순수 규칙 시험 — legacy 는 입력을 그대로(같은 객체) 돌려주고, allowlist 는 외부 텍스트를 걸러낸다.
생성기에 연결된 모습(호출 0·초록 종료·바이트 비교)은 tests/test_generator_source_policy.py 가 본다. 네트워크·시계를 쓰지 않는다."""
import ast
import dataclasses
import datetime
import json
import unittest
from unittest import mock

import _bootstrap  # noqa: F401
from pipeline import egress, source_policy as sp, source_registry as sr
from source_registry_helpers import GOOD_HOST, TODAY, good_provider, registry_data, with_cell

ROOT = _bootstrap.ROOT


def active():
    return sr.build_registry(registry_data(good_provider()), TODAY)


def none_active():
    return sr.build_registry(registry_data(good_provider(enabled=False)), TODAY)


class RegistryErrorsTest(unittest.TestCase):
    def test_absent_and_valid_values_have_no_error(self):
        self.assertEqual(sp.registry_errors({}, "블로그 'chance'", "jekyll-git"), [])
        self.assertEqual(sp.registry_errors({"source_policy": "legacy"}, "x", "jekyll-git"), [])
        self.assertEqual(sp.registry_errors({"source_policy": "allowlist"}, "x", "jekyll-git"), [])
        self.assertEqual(sp.registry_errors({}, "x", "blogger"), [])                        # 적지 않았으면 어느 플랫폼이든 문제 없음

    def test_bad_values_and_platforms_are_errors_naming_the_blog(self):
        for bad in ("ALLOWLIST", "", "on", None, 1, True, ["allowlist"], {"a": 1}, "a" * 500):
            errors = sp.registry_errors({"source_policy": bad}, "블로그 'chance'", "jekyll-git")
            self.assertEqual(len(errors), 1, bad)
            self.assertIn("블로그 'chance'", errors[0])
            self.assertIn("source_policy", errors[0])
            self.assertLess(len(errors[0]), 300)                                           # 값이 길어도 문구는 짧다
        for platform in ("blogger", "naver", "tistory", None):
            errors = sp.registry_errors({"source_policy": "allowlist"}, "x", platform)
            self.assertTrue(errors and "jekyll-git" in errors[0], platform)


class SwitchHelpersTest(unittest.TestCase):
    def test_news_registry_is_none_in_legacy_and_never_reads_the_file_or_the_clock(self):
        with mock.patch.object(sr, "load_registry", side_effect=AssertionError("읽었다")):
            self.assertIsNone(sp.news_registry("legacy", lambda: self.fail("시계를 불렀다")))
            self.assertIsNone(sp.news_registry("whatever", None))

    def test_news_registry_loads_in_allowlist_with_a_lazy_date(self):
        calls = []
        with mock.patch.object(sr, "load_registry", side_effect=lambda path, today: calls.append((path, today)) or "REG"):
            self.assertEqual(sp.news_registry("allowlist", lambda: datetime.date(2026, 11, 9)), "REG")
            self.assertEqual(sp.news_registry("allowlist", "2026-11-09", path="p.json"), "REG")
        self.assertEqual(calls, [(None, datetime.date(2026, 11, 9)), ("p.json", "2026-11-09")])

    def test_active_content_providers_are_the_active_data_providers(self):
        self.assertEqual([p.provider_id for p in sp.active_content_providers(active())], ["fixture_stats"])
        self.assertEqual(sp.active_content_providers(none_active()), [])
        self.assertEqual([p.provider_id for p in sp.active_content_providers(sr.load_registry(today=TODAY))], ["noaa_swpc_json"])      # 실제 파일: 켜는 변경(T3, 패치 02) 뒤 ACTIVE 하나(전에는 0)

    def test_idle_check(self):
        report, lines = {}, []
        self.assertFalse(sp.idle_check("legacy", report, None, lines.append, registry=none_active()))
        self.assertEqual((report, lines), ({}, []))                                         # legacy: 아무 일도 하지 않는다
        self.assertTrue(sp.idle_check("allowlist", report, None, lines.append, registry=none_active()))
        self.assertEqual(report, {"outcome": "SOURCE_POLICY_NO_ACTIVE_PROVIDER"})
        report = {}
        self.assertFalse(sp.idle_check("allowlist", report, None, lines.append, registry=active()))
        self.assertEqual(report, {})                                                        # ACTIVE 가 있으면 결과 코드를 적지 않는다(일반 흐름이 계속)

    def test_idle_check_reports_why_an_enabled_provider_is_not_active_and_stays_idle(self):
        failing = sr.build_registry(registry_data(with_cell(good_provider(), "ai_input", state="UNKNOWN", basis="NOT_READ")), TODAY)
        lines, report = [], {}
        self.assertTrue(sp.idle_check("allowlist", report, None, lines.append, registry=failing))
        self.assertTrue(lines and all("fixture_stats" in line and "ACTIVE" in line for line in lines))
        self.assertTrue(any("[A2]" in line and "ai_input" in line for line in lines))
        self.assertEqual(report["outcome"], "SOURCE_POLICY_NO_ACTIVE_PROVIDER")

    def test_idle_check_reads_the_file_with_a_lazy_date_only_in_allowlist(self):
        with mock.patch.object(sr, "load_registry", return_value=none_active()) as load:
            sp.idle_check("legacy", {}, lambda: self.fail("시계"), print)
            load.assert_not_called()
            sp.idle_check("allowlist", {}, lambda: "2026-11-09", lambda line: None)
            load.assert_called_once_with(None, "2026-11-09")

    def test_the_gate_is_a_no_op_in_legacy_and_enforced_in_allowlist(self):
        with mock.patch.object(sr, "load_registry", side_effect=AssertionError("legacy 가 읽었다")):
            self.assertIsNone(sp.egress_gate("http://evil.example/x?token=S", "feed", mode="legacy"))      # 막지도 읽지도 않는다
        self.assertIsNone(sp.egress_gate("https://api.telegram.org/bot123:ABC/sendMessage", "ops_notify", mode="allowlist", registry=none_active()))      # 운영 호스트는 자기 운영 목적·경로에서만 열린다
        for url, purpose in (("https://api.github.com/x", "ops"), ("https://api.telegram.org/bot123:ABC/sendMessage", "fact"), ("https://api.github.com/repos/o/r/readme", "ops_repo")):
            with self.assertRaises(egress.EgressDenied):                                                                                                    # 운영 호스트라도 모르는 목적·경로는 거부(P02)
                sp.egress_gate(url, purpose, mode="allowlist", registry=none_active())
        for purpose in ("feed", "page", "resolve"):
            with self.assertRaises(egress.EgressDenied):
                sp.egress_gate(f"https://{GOOD_HOST}/v1/x", purpose, mode="allowlist", registry=active())
        self.assertIsNone(sp.egress_gate(f"https://{GOOD_HOST}/v1/x", "fact", mode="allowlist", registry=active()))
        with self.assertRaises(egress.EgressDenied):
            sp.egress_gate("https://evil.example/x", "fact", mode="allowlist", registry=active())
        with mock.patch.object(sp, "chance_source_policy", return_value="allowlist"), mock.patch.object(sr, "load_registry", return_value=none_active()):
            with self.assertRaises(egress.EgressDenied):
                sp.egress_gate("https://evil.example/x", "fact", today="2026-11-09")
        with mock.patch.object(sp, "chance_source_policy", return_value="legacy"):
            self.assertIsNone(sp.egress_gate("https://evil.example/x", "fact"))


class OwnTitleTest(unittest.TestCase):
    def test_own_title(self):
        self.assertEqual(sp.own_title({"own_title": "  제목  "}), "제목")
        for bad in (None, "x", 5, [], {}, {"own_title": None}, {"own_title": ""}, {"own_title": "  "}, {"own_title": 7}, {"own_title": ["a"]}, {"title": "x"}):
            self.assertEqual(sp.own_title(bad), "", bad)

    def test_prompt_inputs_legacy_returns_the_same_objects(self):
        item, titles = {"title": "외부 제목", "summary": "요약"}, ["a", "b"]
        self.assertIs(sp.prompt_inputs("legacy", item, titles)[0], item)
        self.assertIs(sp.prompt_inputs("legacy", item, titles)[1], titles)
        self.assertEqual(sp.prompt_inputs("legacy", None, titles), (None, titles))

    def test_prompt_inputs_allowlist_keeps_only_the_own_title(self):
        item = {"title": "외부 제목", "summary": "요약", "source": "S", "link": "https://x.example/a", "published": object(), "prompt_rule": "규칙", "categories": ["태그"], "own_title": " 자체 "}
        got, titles = sp.prompt_inputs("allowlist", item, ["a"])
        self.assertEqual(got, {"title": "자체"})
        self.assertEqual(titles, ["a"])
        self.assertIn("summary", item)                                                      # 입력을 바꾸지 않는다
        for bad in (None, {}, {"title": "외부 제목", "summary": "요약"}, {"own_title": ""}, {"own_title": None}, "문자열", 5):
            self.assertIsNone(sp.prompt_inputs("allowlist", bad, [])[0], bad)

    def test_history_titles_from_external_articles_are_found_conservatively(self):
        history = [
            {"topic": "외부 기사 제목", "kr_title": "우리 한글 제목", "en_title": "Our English Title", "source_url": "https://x.example/a"},      # 외부 → topic 만 외부
            {"topic": "우리 한글 제목 둘", "kr_title": "우리 한글 제목 둘", "source_url": "https://x.example/b"},                                     # topic 이 자체 제목과 같다 → 외부 아님
            {"topic": "출처 주소 없는 주제", "kr_title": "다른 제목"},                                                                               # 출처 주소가 없어도 자체 제목과 다르면 외부로 본다(P11 — 안전한 쪽)
            {"topic": "자체 제목과 같은 주제", "kr_title": "자체 제목과 같은 주제", "en_title": "Own"},                                                    # 주소가 없어도 자체 제목과 같으면 외부 아님
            "문자열 항목(출처를 알 수 없는 옛 형식)", "  ",
            {"topic": "  ", "source_url": "https://x.example/c"}, {"topic": 5, "source_url": "https://x.example/d"}, {"source_url": "https://x.example/e"}, 7, None,
        ]
        self.assertEqual(sp.external_history_titles(history), {"외부 기사 제목", "출처 주소 없는 주제", "문자열 항목(출처를 알 수 없는 옛 형식)"})
        self.assertEqual(sp.external_history_titles(None), set())
        self.assertEqual(sp.external_history_titles([]), set())

    def test_the_two_old_history_entries_without_a_source_url_are_found_in_the_real_history(self):
        """P11: 실제 history.json 의 2026-10-19 옛 항목 두 건(외부 제목이 topic 인데 source_url 칸이 없다)이 '외부 제목'으로 걸러진다."""
        history = json.loads((ROOT / "history.json").read_text(encoding="utf-8"))
        old = [e for e in history if isinstance(e, dict) and e.get("date") == "2026-10-19" and not e.get("source_url")]
        self.assertEqual(len(old), 2)
        external = sp.external_history_titles(history)
        for entry in old:
            self.assertIn(entry["topic"].strip(), external)
            self.assertNotIn(entry["topic"].strip(), (entry.get("kr_title"), entry.get("en_title")))
        titles = [e["topic"] for e in old] + ["우리 제목"]
        self.assertEqual(sp.prompt_titles("allowlist", titles, history), ["우리 제목"])
        self.assertIs(sp.prompt_titles("legacy", titles, history), titles)

    def test_prompt_titles(self):
        history = [{"topic": "외부 기사 제목", "kr_title": "우리 제목", "en_title": "Our Title", "source_url": "https://x.example/a"}, "옛 문자열 항목"]
        titles = ["외부 기사 제목", "우리 제목", "Our Title", "옛 문자열 항목", "블로그 글 제목"]
        self.assertIs(sp.prompt_titles("legacy", titles, history), titles)                  # legacy: 같은 객체
        self.assertEqual(sp.prompt_titles("allowlist", titles, history), ["우리 제목", "Our Title", "블로그 글 제목"])
        self.assertEqual(titles[0], "외부 기사 제목")                                          # 입력을 바꾸지 않는다
        self.assertEqual(sp.prompt_titles("allowlist", [], history), [])
        self.assertEqual(sp.prompt_titles("allowlist", titles, []), titles)


class OwnTitleBatchesTest(unittest.TestCase):
    def batches(self):
        return [("science", [{"title": "EXT-A", "summary": "s"}, {"title": "EXT-B", "own_title": "자체 B", "link": "https://x.example/b"}]),
                ("economy", [{"title": "EXT-C"}]), ("society", [{"title": "EXT-D", "own_title": " 자체 D "}])]

    def test_legacy_returns_the_same_iterator(self):
        source = iter(self.batches())
        self.assertIs(sp.own_title_batches("legacy", source), source)
        data = self.batches()
        self.assertIs(sp.own_title_batches("legacy", data), data)

    def test_allowlist_drops_candidates_without_an_own_title_and_swaps_the_title(self):
        data = self.batches()
        drops = []
        got = list(sp.own_title_batches("allowlist", iter(data), drops.append))
        self.assertEqual([lane for lane, _ in got], ["science", "society"])                # 후보가 하나도 남지 않은 분야는 내보내지 않는다
        self.assertEqual(got[0][1], [{"title": "자체 B", "own_title": "자체 B", "link": "https://x.example/b"}])
        self.assertEqual(got[1][1][0]["title"], "자체 D")
        self.assertEqual(drops, [1, 1])                                                     # 분야별로 빠진 수만 알린다(economy 의 1건은 그 분야가 통째로 빠져 함께 센다)
        self.assertEqual(data[0][1][1]["title"], "EXT-B")                                   # 원본 후보를 바꾸지 않는다

    def test_the_other_candidate_fields_pass_through_untouched_so_the_producer_owns_them(self):
        """P10(D-175): 이 모듈은 제목만 자체 제목으로 바꾼다. source·publisher_domain·citation·link 등은 그대로 통과 — 후보를 만드는 쪽이 우리가 정한 문자열로만 채우는 것이 계약이다(docs 9절). 통과 동작을 못박는다."""
        item = {"title": "EXT", "own_title": "자체 제목", "source": "후보가 정한 이름", "publisher_domain": "host.fixture.example", "citation": "Source: Fixture", "link": "https://host.fixture.example/a", "extra": [1, 2]}
        (lane, kept), = list(sp.own_title_batches("allowlist", iter([("science", [item])])))
        self.assertEqual(kept[0], dict(item, title="자체 제목"))
        for key in ("source", "publisher_domain", "citation", "link", "extra"):
            self.assertIs(kept[0][key], item[key], key)
        doc = (ROOT / "docs" / "SOURCE_POLICY.md").read_text(encoding="utf-8")
        for needle in ("source", "publisher_domain", "citation", "자체 문자열"):
            self.assertIn(needle, doc.split("## 9.", 1)[1].split("## 10.", 1)[0], needle)      # 계약이 문서 9절에 의무로 적혀 있다

    def test_allowlist_is_lazy_and_ignores_a_missing_callback(self):
        consumed = []

        def source():
            for batch in self.batches():
                consumed.append(batch[0])
                yield batch
        stream = sp.own_title_batches("allowlist", source())
        self.assertEqual(consumed, [])                                                      # 만든 것만으로는 읽지 않는다(분야를 느리게 읽는 흐름이 그대로)
        self.assertEqual(next(stream)[0], "science")
        self.assertEqual(consumed, ["science"])
        self.assertEqual([lane for lane, _ in stream], ["society"])                         # on_drop 이 없어도 같다


class LegacyPolicyNoticeTest(unittest.TestCase):
    """P07: 코드는 AI 처리기 정책 파일을 실행 중에 읽지 않는다 — legacy 에서 정책(원문 외부 텍스트 입력 금지)과 어긋난 상태를 알릴 한 줄을 만들 뿐이다(부르는 곳은 FACT 2단계 몫)."""

    def test_legacy_with_the_real_policy_gets_a_notice_and_allowlist_does_not(self):
        text = sp.legacy_policy_notice("legacy")
        self.assertIsNotNone(text)
        for needle in ("legacy", "raw_source_text_allowed", "allowlist", "어긋"):
            self.assertIn(needle, text)
        self.assertIsNone(sp.legacy_policy_notice("allowlist"))
        self.assertEqual(text, sp.LEGACY_AI_NOTICE)

    def test_a_policy_that_allowed_raw_text_would_need_no_notice(self):
        policy = dataclasses.replace(sr.load_ai_policy(), raw_source_text_allowed=True)      # 검증기는 이런 파일을 거부하지만 한 줄 판정 자체를 시험한다
        self.assertIsNone(sp.legacy_policy_notice("legacy", policy))
        self.assertEqual(sp.legacy_policy_notice("legacy", sr.load_ai_policy()), sp.LEGACY_AI_NOTICE)

    def test_nothing_in_the_generator_calls_it_so_the_legacy_output_is_untouched(self):
        for rel in ("generator.py", "blogger_generator.py", "pipeline/run.py"):
            self.assertNotIn("legacy_policy_notice", (ROOT / rel).read_text(encoding="utf-8"), rel)


class HygieneTest(unittest.TestCase):
    def tree(self, name):
        return ast.parse((ROOT / "pipeline" / name).read_text(encoding="utf-8"))

    def imports(self, tree):
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names |= {a.name for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                names |= {f"{node.module}.{a.name}" if node.module else a.name for a in node.names}
        return names

    def test_source_policy_and_egress_import_only_what_they_need(self):
        self.assertEqual(self.imports(self.tree("source_policy.py")), {"pipeline.egress", "pipeline.source_registry", "pipeline.registry", "sys"})   # registry 는 순환을 피하려고 함수 안에서만(지연 import). sys 는 S2b 의 명령줄(`content-source`)이 쓴다 — 표준 라이브러리의 sys 하나뿐이고 아래 금지 모듈(os·subprocess·socket·ctypes·msvcrt) 시험은 그대로다
        self.assertEqual(self.imports(self.tree("egress.py")), {"collections.namedtuple", "pipeline.source_registry", "re", "urllib.error", "urllib.parse", "urllib.request"})   # 검사된 opener 가 urllib.request 를 쓴다
        top_level = [n for n in self.tree("source_policy.py").body if isinstance(n, (ast.Import, ast.ImportFrom))]
        self.assertEqual(sorted(alias.name for n in top_level for alias in n.names), ["egress", "source_registry", "sys"])

    def test_no_clock_randomness_or_forbidden_modules(self):
        banned = {"now", "utcnow", "today", "time", "monotonic", "random", "urandom", "uuid4"}
        for name in ("source_policy.py", "egress.py"):
            for node in ast.walk(self.tree(name)):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in banned:
                    self.fail(f"{name}: 시각·무작위 호출 .{node.func.attr}() (line {node.lineno})")
            self.assertTrue({"msvcrt", "ctypes", "subprocess", "socket", "os"}.isdisjoint({n.split(".")[0] for n in self.imports(self.tree(name))}), name)


if __name__ == "__main__":
    unittest.main()
