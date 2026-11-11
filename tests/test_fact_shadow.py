"""그림자 실행의 구조화 Fact 분기(S2b, `pipeline/shadow_run.py` 의 `run_facts`) 시험. 네트워크·시계·진짜 키 없음(가짜 transport·가짜 시계).

못박는 것: 레지스트리 content_source 가 facts 일 때만 이 분기로 간다(읽지 못하거나 이상한 값이면 이 분기로 가지 않는다) · AI 를 한 번도 부르지 않고 Gemini 키 없이 돈다 · 후보는 일반 실행과 같은 함수(`g.fact_prepare`)로 만든다 ·
결과는 일반 그림자 실행과 같은 모양(번호 폴더의 글 파일·result.json·run.json — 측정 도구가 읽는 이름)으로 SHADOW_OUT 아래에만 쓰고 저장소 작업 폴더의 바이트는 그대로다 · Gate 는 항상 돌린다 ·
시작 조건을 못 채우면 후보 0건으로 정상 종료한다(run.json 에 이유). 읽기 전용 구간의 방어 코드(쓰기·git 차단)는 그대로 감시한다."""
import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import _bootstrap  # noqa: F401
import fact_branch_helpers as FB
import generator as g

from pipeline import fact_supply, quality_gate, registry, shadow_run
from pipeline.adapters import noaa_swpc as N


def snapshot(folder):
    return {path.relative_to(folder).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(Path(folder).rglob("*")) if path.is_file()}


class ShadowFactsBase(FB.FactEnv):
    def setUp(self):
        super().setUp()
        out = tempfile.TemporaryDirectory()
        self.addCleanup(out.cleanup)
        self.out_dir = Path(out.name) / "shadow_out"

    def run_shadow(self, count="3", extra=None):
        environ = {"SHADOW_OUT": str(self.out_dir), "SHADOW_COUNT": count, "PIPELINE_PAUSE": ""}
        environ.update(extra or {})
        lines = []
        info = shadow_run.run(g, environ, out=lines.append)
        return info, lines

    def results(self):
        return {folder.name: json.loads((folder / "result.json").read_text(encoding="utf-8")) for folder in sorted(self.out_dir.iterdir()) if folder.is_dir()}

    def run_info(self):
        return json.loads((self.out_dir / "run.json").read_text(encoding="utf-8"))


class SwitchTest(ShadowFactsBase):
    def test_the_branch_follows_the_registry_value_and_never_fails_open(self):
        self.assertTrue(shadow_run.facts_branch_on())
        self.use(FB.facts_registry(content_source=None), FB.sources_registry())
        self.assertFalse(shadow_run.facts_branch_on())                                                    # 값이 없으면 feed
        self.use(FB.facts_registry(content_source="feed"), FB.sources_registry())
        self.assertFalse(shadow_run.facts_branch_on())
        self.use(FB.facts_registry(content_source="fact"), FB.sources_registry())                        # 이상한 값은 이 분기로 가지 않는다(뒤이은 registry.chance_settings 는 …)
        self.assertFalse(shadow_run.facts_branch_on())
        with mock.patch.object(registry, "load_registry", side_effect=registry.RegistryError("없음")):
            self.assertFalse(shadow_run.facts_branch_on())

    def test_a_feed_registry_never_enters_the_branch_and_the_old_path_asks_for_the_model_key(self):
        self.use(FB.facts_registry(content_source=None), FB.sources_registry())
        with mock.patch.object(shadow_run, "run_facts", side_effect=AssertionError("Fact 분기로 갔다")):
            with self.assertRaises(RuntimeError) as caught:
                self.run_shadow()
        self.assertIn("GEMINI_API_KEY", str(caught.exception))                                            # 기본(feed)은 이전과 같다 — 키가 없으면 멈춘다


class ShadowFactsRunTest(ShadowFactsBase):
    def test_it_runs_without_a_model_key_and_writes_results_in_the_standard_shape_only_under_the_out_folder(self):
        before = snapshot(self.work)
        info, lines = self.run_shadow("3")
        self.assertEqual(snapshot(self.work), before)                                                      # 저장소 작업 폴더의 바이트는 그대로(글·이력을 쓰지 않는다)
        self.assertEqual(info["attempts"], 3)
        self.assertEqual(info, self.run_info())
        self.assertEqual(self.run_info()["languages"], ["ko"])
        self.assertEqual(self.run_info()["lanes_tried"], [g.FACT_LANE_LABEL])
        results = self.results()
        self.assertEqual(sorted(results), ["01", "02", "03"])
        names = sorted(str(path.relative_to(self.out_dir)).replace("\\", "/") for path in self.out_dir.rglob("*") if path.is_file())
        self.assertEqual(names, ["01/2026-11-10-KR-101200.md", "01/result.json", "02/2026-11-10-KR-101201.md", "02/result.json", "03/2026-11-10-KR-101202.md", "03/result.json", "run.json"])
        self.assertTrue(any(line.startswith("SHADOW_DONE attempts=3") for line in lines), lines)
        self.assertFalse(any("EN" in name for name in names))
        for number, result in results.items():
            with self.subTest(attempt=number):
                self.assertEqual(result["schema"], 1)
                self.assertIn(result["outcome"], ("PASSED", "HELD"))
                self.assertEqual((result["model"], result["lane"], result["languages"]), ("rule", "facts", ["ko"]))
                self.assertEqual(result["gate"]["input"], "validated")
                self.assertEqual(result["source_domain"], N.HOST)
                self.assertTrue(result["title_ko"] and result["source_text_chars"] > 0)
                self.assertEqual(result["files"], {"ko": f"2026-11-10-KR-10120{int(number) - 1}.md"})
                self.assertEqual(result["passed"], result["outcome"] == "PASSED")
                text = (self.out_dir / number / result["files"]["ko"]).read_text(encoding="utf-8")
                self.assertEqual(g.front_matter_problems(text, allow_provenance=True), [])
                self.assertEqual(text.count('provenance: "facts"'), 1)

    def test_the_candidates_come_from_the_same_function_and_order_as_a_real_run(self):
        info, _lines = self.run_shadow("5")
        shadow_titles = [result["title_ko"] for result in self.results().values()]
        self.assertEqual(len(shadow_titles), 5)                                                            # 묶음마다 한 편 — 다섯 묶음
        real = FB.FactEnv.NOW
        titles = []
        prepared, _supplied = g.fact_prepare(real, [], *g.fact_context(real)[1:], limit=5)
        titles = [item.post.title for item in prepared]
        self.assertEqual(shadow_titles, titles)
        calls = []
        real_prepare = g.fact_prepare

        def spy(*args, **kwargs):
            calls.append(kwargs)
            return real_prepare(*args, **kwargs)
        self.out_dir = self.out_dir.parent / "second"
        with mock.patch.object(g, "fact_prepare", spy):
            self.run_shadow("2")
        self.assertEqual(len(calls), 1)
        self.assertEqual((calls[0]["limit"], calls[0]["gate_config"]), (2, None))

    def test_no_model_feed_page_or_photo_function_is_called_and_the_count_stays_zero(self):
        with mock.patch.dict(g.GEMINI_CALLS, {"attempts": 0, "failed": 0}), mock.patch("urllib.request.urlopen", side_effect=AssertionError("네트워크 직접 접속")):
            self.run_shadow("3")
            self.assertEqual(g.GEMINI_CALLS, {"attempts": 0, "failed": 0})
        for spy in self.spies.values():
            spy.assert_not_called()

    def test_the_gate_is_always_applied_and_its_verdict_decides_passed_or_held(self):
        seen, contents = [], []

        def spy(data, source, history=(), config=None, as_of=None):
            seen.append(source)
            contents.append(data["kr_content"])
            report = quality_gate.GateReport()
            if len(seen) == 2:
                report.holds.append(quality_gate.Hold("QG1-NUMBER", 1, "ko", "시험 보류"))
            return report
        with mock.patch.object(quality_gate, "check_candidate", spy):
            info, _lines = self.run_shadow("3")
        self.assertEqual((info["attempts"], info["passed"], info["held_or_rejected"]), (3, 2, 1))
        self.assertTrue(all(tuple(source) == fact_supply.GATE_SOURCE_KEYS for source in seen))
        self.assertEqual(len(contents), 3)
        self.assertTrue(all("provenance" not in text for text in contents))                                # Gate 에는 표식 전의 글이 간다(머리말 한 줄이 본문 규칙에 쓰이지 않게)
        results = self.results()
        self.assertEqual([results[number]["outcome"] for number in ("01", "02", "03")], ["PASSED", "HELD", "PASSED"])
        self.assertEqual(results["02"]["hold_codes"], ["QG1-NUMBER"])
        self.assertEqual([entry["passed"] for entry in self.run_info()["attempts_summary"]], [True, False, True])

    def test_the_count_limits_the_number_of_candidates(self):
        for count, expected in (("1", 1), ("2", 2), ("5", 5), ("9", 5), ("", 3)):
            with self.subTest(count=count):
                self.out_dir = self.out_dir.parent / f"count_{count or 'default'}"
                info, _lines = self.run_shadow(count)
                self.assertEqual(info["attempts"], expected)

    def test_a_history_with_fact_posts_changes_the_order_like_a_real_run(self):
        self.set_history([{"date": "2026-11-05", "content_source": "facts", "candidate_key": "space_weather.kp_weekly:2026-W45", "dedupe_key": "x", "topic": "지난 글"}])
        before = snapshot(self.work)
        info, _lines = self.run_shadow("5")
        self.assertEqual(snapshot(self.work), before)
        self.assertEqual(info["attempts"], 4)                                                              # Kp 를 읽은 글이 5일 전이라 Kp 묶음은 아직 막혀 있다 — 나머지 네 묶음
        titles = [result["title_ko"] for result in self.results().values()]
        self.assertIn("플레어", titles[0])                                                                  # 안 낸 글감 중 차례가 가장 앞선 플레어 글이 먼저다
        self.assertFalse(any("Kp" in title for title in titles))


class ShadowFactsNotReadyTest(ShadowFactsBase):
    def test_a_start_condition_not_met_means_zero_candidates_and_a_normal_end_with_the_reason_in_run_json(self):
        self.use(FB.facts_registry(), json.loads((FB.ROOT / "pipeline" / "source_registry.json").read_text(encoding="utf-8")))       # Provider 꺼짐 — 지금 저장소의 실제 상태
        before = snapshot(self.work)
        info, lines = self.run_shadow("3")
        self.assertEqual(snapshot(self.work), before)
        self.assertEqual((info["attempts"], info["passed"], info["outcome"]), (0, 0, "NO_CANDIDATES"))
        self.assertTrue(any("시작하지 않습니다" in line for line in lines), lines)
        self.assertTrue(any(FB.PROVIDER_ID in note for note in self.run_info()["notes"]), self.run_info()["notes"])
        self.assertEqual([path.name for path in self.out_dir.iterdir()], ["run.json"])
        self.assertTrue(any("평가할 후보가 없었습니다" in line for line in lines))
        self.assertEqual(self.noaa.factory_calls, 0)

    def test_the_read_only_guard_still_blocks_writes_inside_the_branch(self):
        """분기 안에서 쓰기 함수를 부르면 읽기 전용 구간의 방어 코드가 막는다(ShadowViolation) — 그림자 쓰기 방어 코드는 그대로다."""
        with mock.patch.object(g, "fact_prepare", lambda *args, **kwargs: g.write_history([{"x": 1}])):
            with self.assertRaises(shadow_run.ShadowViolation):
                self.run_shadow("3")
        self.assertFalse((self.work / "history.json").exists())


if __name__ == "__main__":
    unittest.main()
