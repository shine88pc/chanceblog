"""글 근거 보강(D-77) 시험 — 글 작성 지침(`generator.build_post_prompt`)에 '요약에 없는 것을 채우지 않는' 공통 규칙이 모든 소스의 프롬프트에 들어가는지 고정한다.

배경: 2026-10-27 9시 슬롯 글 한 쌍(DG Energy 항목)이 RSS 요약 한 문장(194자)만 받고 약 5,000자를 쓰면서, 핵심 수치는 맞았지만 한국어 글에만 원문에 없는 원화 환산
("한화 약 4조 2천억 원")이, 두 글에 원문에 없는 평가 기준·절차 서술이 섞였다. 본문 전문 수집 금지(원문 발췌 읽기는 운영자 결정, 기본값 변경 없음)는 그대로 두고
지침으로만 막는다(`generator.GROUNDING_RULES`). 소스별 약관 규칙(`prompt_rule`)은 그 소스 고유 문장만 남기고 같은 말을 두 곳에 적지 않는다.

이 시험이 지키는 것: ① 공통 규칙 세 문장이 비어 있지 않고 각자 막으려는 말을 담는다 ② 소스 목록(`NEWS_SOURCES`, 보류 소스 포함)을 코드에서 읽어 모든 소스의 프롬프트에 규칙이
한 번씩 들어간다 — 소스를 더해도 빠지지 않는다 ③ 소스별 규칙의 고유 문장이 그대로 남고 순서(공통 → 소스별)가 지켜진다 ④ 같은 말이 공통 규칙과 소스 규칙에 겹쳐 적히지 않는다
⑤ 출처가 없는 글감의 건너뜀 안내는 그대로다 ⑥ 엔진이 실제로 모델에 보내는 프롬프트에도 들어간다. 네트워크는 쓰지 않는다.
"""
import json
import tempfile
import unittest
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import _bootstrap  # noqa: F401
import generator as g
from test_generator_slots import FakeResponse, at, long_post, rss, run_captured

# 소스 이름 앞부분 → 그 소스 규칙에만 있는 문장(2026-10-27 main 의 글자 그대로). 지침을 정리하면서 이 문장들이 그대로 남았는지 고정한다.
HEALTH = "건강·의료 정보는 정책과 통계 사실만 전하고 진단·치료·복용·예방 효과를 조언하지 마세요."
EC_SENTENCES = ("집행위원회의 제안·협의·계획과 이미 확정된 법·결정을 구분하세요.",
                "원문의 의미를 왜곡하지 말고, 집행위원회가 이 글을 검토하거나 보증한 것처럼 쓰지 마세요.", HEALTH)
SOURCE_OWN_SENTENCES = {
    "European Commission": EC_SENTENCES,
    "EU Digital Strategy": EC_SENTENCES + ("요약 앞머리의 'Anonymous (not verified)'와 날짜는 사이트가 붙인 잡음이니 글에 쓰지 마세요.",),
    "Statistics Canada": ("통계청 발표 요약의 수치·단위·기준 시점(월·분기·연도)을 그대로 쓰세요.",
                          "통계청이 이 글을 보증하는 것처럼 쓰지 마세요.",
                          "원문 링크의 글자는 '통계청 발표'처럼 설명 문구로 쓰고 주소(statcan.gc.ca)를 글자로 보이게 쓰지 마세요.", HEALTH),
    "GOV.UK": ("영국 정부(부처)가 발표한 내용임을 분명히 하고, 정부의 계획·주장과 확인된 사실을 구분하세요.",
               "정당·선거·장관 개인에 대한 평가는 쓰지 말고, 영국 정부나 해당 부처가 이 글을 검토·보증했거나 정부의 공식 입장·문서인 것처럼 쓰지 마세요.", HEALTH),
    "NASA": ("NASA의 AI 이용 안내에 따라 정보를 NASA가 직접 말하거나 보증한 것처럼 쓰지 마세요.",
             "'NASA에 따르면'·'NASA는 밝혔다'(영어 글은 'according to NASA'·'NASA said') 같은 직접 귀속 표현을 쓰지 말고 ",
             "'공개된 자료에 따르면'(영어 글은 'according to the published material')처럼 자료를 가리키세요."),
    "Pew Research Center": ("Pew Research Center의 조사 결과를 전하되, Pew가 특정 정책·정당·견해를 지지하거나 주장하는 것처럼 쓰지 마세요.",
                            "조사 결과와 이 사이트의 해석을 구분하세요."),
}

# 공통 규칙 앞뒤의 이웃 줄(기존 문장 그대로): 규칙은 '출처를 추정해 만들지 마세요' 줄 바로 뒤, 소스별 규칙(있으면)과 '본문은 충분한…' 줄 앞에 온다.
LINE_BEFORE = "- 제목·저자·학술지명·DOI·통계·인용문이나 출처를 추정해 만들지 마세요. 근거가 부족하면 skip을 반환하세요.\n"
LINE_AFTER = "- 본문은 충분한 설명과 분석을 포함하고 Markdown으로 작성하세요.\n"
NO_SOURCE_LINE = "- 검증된 출처가 없으면 글을 만들지 말고 skip을 반환하세요.\n"
# 소스 필터(제외·주제 정규식)를 떼어 내고 엔진이 읽게 할 때 덜어 내는 키 — 후보를 만드는 데 쓰이지 않는 것들
FILTER_KEYS = ("exclude_title", "exclude_link", "exclude_tags", "topic_regex")


def direct_item(src):
    """엔진(fetch_news_items)이 이 소스의 기사로 만드는 후보와 같은 키의 후보. 소스 목록 전체(보류 소스 포함)를 훑는 시험이 쓴다."""
    host = g._host(src["url"])
    return {"title": f"{src['name']} 시험 발표", "source": src.get("display_name") or src["name"],
            "link": f"https://{host}/news/sample", "publisher_domain": host, "summary": "요약 문장입니다. " * 20,
            "published": datetime(2026, 10, 26, 8, 0, tzinfo=timezone.utc),
            "notice": src.get("notice"), "citation": src.get("citation"), "prompt_rule": src.get("prompt_rule")}


def fetched_item(src):
    """진짜 `fetch_news_items` 로 이 소스의 가짜 피드 기사 한 건을 읽어 온 후보(제외·주제 정규식은 떼고 피드 호스트는 그대로 둔다 — 그 호스트는 자기 분야에서 신뢰된다).
    보류(pending) 소스는 엔진이 읽지 않으므로 None."""
    probe = {key: value for key, value in src.items() if key not in FILTER_KEYS}
    host = g._host(src["url"])
    feed = rss([("시험 발표", f"https://{host}/news/sample", datetime.now(timezone.utc) - timedelta(hours=3), "요약 문장입니다. " * 20, "")])
    with mock.patch.object(g, "NEWS_SOURCES", [probe]), mock.patch.object(g.urllib.request, "urlopen", lambda req, timeout=0: FakeResponse(feed)):
        merged, _out = run_captured(g.fetch_news_items, src["lane"])
    return merged[0] if merged else None


def prompt_for(src, **kwargs):
    return g.build_post_prompt(direct_item(src), ["최근 글 제목"], editorial_lane=src["lane"], **kwargs)


def instruction_lines(prompt):
    """프롬프트의 '[중요 지침]' 구간(다음 '[편집 템플릿]' 머리글 전까지)의 줄."""
    start = prompt.index("[중요 지침]\n") + len("[중요 지침]\n")
    return prompt[start:prompt.index("\n\n[편집 템플릿]\n", start)].split("\n")


class GroundingRulesTextTest(unittest.TestCase):
    """공통 규칙 세 문장 각각이 막으려는 말을 담는다 — 문장이 비거나 핵심 낱말이 빠지면 실패한다."""

    def test_there_are_exactly_three_rules_and_none_is_blank_or_repeated(self):
        rules = g.GROUNDING_RULES
        self.assertIsInstance(rules, tuple)
        self.assertEqual(len(rules), 3)
        for rule in rules:
            with self.subTest(rule=rule[:20]):
                self.assertIsInstance(rule, str)
                self.assertEqual(rule, rule.strip())
                self.assertGreater(len(rule), 20)                      # 낱말 몇 개가 아니라 문장이다
                self.assertNotIn("\n", rule)                           # 한 규칙 = 한 줄(프롬프트가 '- 규칙\n' 로 붙인다)
                self.assertTrue(rule.endswith("."), rule)
        self.assertEqual(len(set(rules)), 3)

    def assert_terms(self, rule, terms):
        for term in terms:
            with self.subTest(term=term):
                self.assertIn(term, rule)

    def test_the_first_rule_forbids_converting_and_rounding_and_keeps_the_announced_figures(self):
        self.assert_terms(g.GROUNDING_RULES[0], ("환산", "반올림", "추정", "원화", "킬로미터", "수치·단위·기준 시점", "그대로"))

    def test_the_second_rule_lists_what_may_not_be_invented_and_how_background_is_marked(self):
        self.assert_terms(g.GROUNDING_RULES[1], ("평가 기준", "심사 절차", "일정", "시행 시기", "금액", "예산 대비 배수", "참여 국가 수", "법적 효력",
                                                "요약에 없는", "일반적으로", "일반론", "구체적인 수치", "고유명사"))

    def test_the_third_rule_forbids_putting_unsupported_content_in_the_sources_mouth(self):
        self.assert_terms(g.GROUNDING_RULES[2], ("출처에 없는 내용", "원인", "전망", "절차", "출처 기관", "말하거나 밝힌", "하기로 한 일"))

    def test_the_rules_are_commands_in_the_prompts_polite_form(self):
        # 기존 지침의 말투('~하세요'·'~마세요')에 맞춘다: 모든 규칙이 금지('마세요')를 담고 명령형으로 끝난다
        for rule in g.GROUNDING_RULES:
            with self.subTest(rule=rule[:20]):
                self.assertIn("마세요", rule)
                self.assertRegex(rule, r"(?:세요|마세요)\.$")


class EverySourcePromptTest(unittest.TestCase):
    """소스 목록을 코드에서 읽어 순회한다(보류 소스 포함) — 소스를 더해도 규칙이 빠지지 않는다."""

    def test_the_loop_covers_every_family_the_task_names_including_the_held_source(self):
        names = [src["name"] for src in g.NEWS_SOURCES]
        for family in ("European Commission", "EU Digital Strategy", "Statistics Canada", "GOV.UK", "NASA", "Pew Research Center", "Federal Reserve", "UN News"):
            with self.subTest(family=family):
                self.assertTrue(any(name.startswith(family) for name in names), names)
        self.assertGreaterEqual(len(names), 14)
        self.assertIn("pending", {src["terms"]["status"] for src in g.NEWS_SOURCES})     # 보류 소스(UN News)도 훑는다

    def test_every_source_prompt_has_every_rule_exactly_once_as_its_own_line(self):
        for src in g.NEWS_SOURCES:
            for allow_skip in (False, True):
                for hint in ("", "경제"):
                    prompt = prompt_for(src, allow_skip=allow_skip, category_hint=hint)
                    for number, rule in enumerate(g.GROUNDING_RULES, 1):
                        with self.subTest(source=src["name"], allow_skip=allow_skip, hint=hint, rule=number):
                            self.assertEqual(prompt.count(f"- {rule}\n"), 1)

    def test_the_rules_follow_the_generic_source_lines_in_order_and_precede_the_sources_own_rule(self):
        for src in g.NEWS_SOURCES:
            with self.subTest(source=src["name"]):
                lines = [line + "\n" for line in instruction_lines(prompt_for(src))]
                positions = [lines.index(f"- {rule}\n") for rule in g.GROUNDING_RULES]
                self.assertEqual(positions, [positions[0], positions[0] + 1, positions[0] + 2])        # 세 규칙은 붙어서 이 순서로
                self.assertEqual(lines[positions[0] - 1], LINE_BEFORE)
                own = src.get("prompt_rule")
                self.assertEqual(lines[positions[2] + 1], f"- {own}\n" if own else LINE_AFTER)
                if own:
                    self.assertEqual(lines[positions[2] + 2], LINE_AFTER)

    def test_a_source_without_its_own_rule_still_gets_the_rules_and_no_empty_rule_line(self):
        bare = [src for src in g.NEWS_SOURCES if not src.get("prompt_rule")]
        self.assertTrue({"Federal Reserve", "UN News"} <= {src["name"] for src in bare}, [src["name"] for src in bare])
        for src in bare:
            with self.subTest(source=src["name"]):
                prompt = prompt_for(src)
                for rule in g.GROUNDING_RULES:
                    self.assertIn(f"- {rule}\n", prompt)
                self.assertNotIn("- None", prompt)
                self.assertNotIn("- \n", prompt)

    def test_the_candidate_the_engine_builds_for_each_readable_source_carries_the_rules_and_the_sources_own_rule(self):
        readable = [src for src in g.NEWS_SOURCES if src["terms"]["status"] != "pending"]
        self.assertGreaterEqual(len(readable), 13)
        for src in readable:
            with self.subTest(source=src["name"]):
                item = fetched_item(src)
                self.assertIsNotNone(item, "엔진이 이 소스에서 후보를 만들지 못했다 — 시험용 가짜 피드가 이 소스 설정과 맞지 않는다")
                self.assertEqual(item["prompt_rule"], src.get("prompt_rule"))
                self.assertEqual(set(item), set(direct_item(src)))              # 위 순회가 쓰는 후보 모양이 엔진의 모양과 같다
                prompt = g.build_post_prompt(item, [], editorial_lane=src["lane"])
                for rule in g.GROUNDING_RULES:
                    self.assertIn(f"- {rule}\n", prompt)
                if src.get("prompt_rule"):
                    self.assertIn(f"- {src['prompt_rule']}\n", prompt)

    def test_the_held_source_is_never_read_by_the_engine_but_its_prompt_still_carries_the_rules(self):
        held = [src for src in g.NEWS_SOURCES if src["terms"]["status"] == "pending"]
        self.assertEqual([src["name"] for src in held], ["UN News"])
        self.assertIsNone(fetched_item(held[0]))
        for rule in g.GROUNDING_RULES:
            self.assertIn(f"- {rule}\n", prompt_for(held[0]))

    def test_no_instruction_line_appears_twice_in_any_sources_prompt(self):
        for src in g.NEWS_SOURCES:
            with self.subTest(source=src["name"]):
                lines = [line for line in instruction_lines(prompt_for(src, allow_skip=True)) if line.startswith("- ")]
                repeated = [line for line, count in Counter(lines).items() if count > 1]
                self.assertEqual(repeated, [])


class SourceOwnRulesStayTest(unittest.TestCase):
    """소스별 규칙의 고유 문장은 지침을 정리한 뒤에도 그대로 남는다(약관 조건·보증 암시 금지·링크 글자 등)."""

    def test_each_sources_own_rule_is_in_its_prompt_once_and_unchanged(self):
        for src in g.NEWS_SOURCES:
            if src.get("prompt_rule"):
                with self.subTest(source=src["name"]):
                    self.assertEqual(prompt_for(src).count(f"- {src['prompt_rule']}\n"), 1)

    def test_the_sentences_only_a_source_can_say_are_still_in_that_sources_prompt(self):
        covered = set()
        for prefix, sentences in SOURCE_OWN_SENTENCES.items():
            sources = [src for src in g.NEWS_SOURCES if src["name"].startswith(prefix)]
            self.assertTrue(sources, prefix)
            for src in sources:
                covered.add(src["name"])
                prompt = prompt_for(src)
                for sentence in sentences:
                    with self.subTest(source=src["name"], sentence=sentence[:24]):
                        self.assertIn(sentence, prompt)
        # 규칙이 있는 소스는 모두 위 표에 걸려 있다 — 새 소스가 규칙을 가지면 고유 문장을 여기에 적는다
        self.assertEqual({src["name"] for src in g.NEWS_SOURCES if src.get("prompt_rule")}, covered)

    def test_the_source_rules_the_three_families_share_are_built_from_the_same_health_sentence(self):
        self.assertEqual(g.HEALTH_RULE, HEALTH)
        for name in ("_EC_PROMPT_RULE", "_STATCAN_PROMPT_RULE", "_GOVUK_PROMPT_RULE"):
            with self.subTest(rule=name):
                self.assertTrue(getattr(g, name).endswith(HEALTH))


class OneCopyOfTheCommonSayingsTest(unittest.TestCase):
    """같은 말을 두 곳에 적지 않는다: 공통 규칙이 말하는 것은 소스별 규칙에서 뺐다."""

    def test_no_source_rule_repeats_what_the_common_rules_say(self):
        for src in g.NEWS_SOURCES:
            for marker in ("요약에 없는", "환산", "반올림"):
                with self.subTest(source=src["name"], marker=marker):
                    self.assertNotIn(marker, src.get("prompt_rule") or "",
                                     f"{src['name']} 의 prompt_rule 이 공통 규칙(generator.GROUNDING_RULES)과 같은 말을 한다 — 소스 규칙에는 그 소스 고유 조건만 쓴다")

    def test_the_common_rules_still_say_everything_the_commission_govuk_and_statcan_rules_used_to_say(self):
        rule_one, rule_two, rule_three = g.GROUNDING_RULES
        for term in ("시행 시기", "금액", "법적 효력"):           # 집행위원회·GOV.UK 규칙에서 옮긴 것
            with self.subTest(term=term):
                self.assertIn("요약에 없는", rule_two)
                self.assertIn(term, rule_two)
        for term in ("반올림", "환산", "추정"):                   # 통계청 규칙에서 옮긴 것
            with self.subTest(term=term):
                self.assertIn(term, rule_one)
        for term in ("원인", "전망", "출처 기관"):
            with self.subTest(term=term):
                self.assertIn(term, rule_three)


class WithoutAVerifiedSourceTest(unittest.TestCase):
    def test_a_topic_without_a_verified_source_is_still_told_to_skip_and_gets_no_source_rules(self):
        weak = (None, {"title": "출처 없는 글감"}, {"title": "링크만 있는 글감", "link": "https://www.reuters.com/a"},
                {"title": "출처 이름만 있는 글감", "source": "Reuters"})
        for item in weak:
            with self.subTest(item=item):
                prompt = g.build_post_prompt(item, [])
                self.assertIn(NO_SOURCE_LINE, prompt)
                self.assertNotIn("제공된 검증 게시자 원문만 사실 근거로 쓰세요", prompt)


class DocsTest(unittest.TestCase):
    """코드와 문서가 같은 말을 한다: 공통 규칙은 ARCHITECTURE 의 소스 절에, 결함은 결함 레지스터(D-77)에 있다."""

    def test_the_architecture_describes_the_common_rules_and_where_they_live(self):
        text = (_bootstrap.ROOT / "docs" / "ARCHITECTURE.md").read_text(encoding="utf-8")
        start = text.index("- **공통 작성 지침(글 근거 보강, D-77)**")
        bullet = text[start:text.index("\n- ", start + 3)]
        for word in ("GROUNDING_RULES", "build_post_prompt", "prompt_rule", "환산", "반올림", "평가 기준", "심사 절차", "일반적으로", "출처 기관",
                     "원문 발췌", "운영자 결정", "tests/test_prompt_grounding.py"):
            with self.subTest(word=word):
                self.assertIn(word, bullet)

    def test_the_defect_register_has_the_d77_row_with_the_agreed_status_and_plan(self):
        text = (_bootstrap.ROOT / "docs" / "DEFECT_REGISTER.md").read_text(encoding="utf-8")
        rows = [line for line in text.splitlines() if line.startswith("| **D-77** |")]
        self.assertEqual(len(rows), 1)
        cells = [cell.strip() for cell in rows[0].strip().strip("|").split(" | ")]
        self.assertEqual(len(cells), 6, cells)                       # ID | 심각도 | 결함 | 근거 | 상태 | 해결 계획
        self.assertIn("완화", cells[4])
        self.assertIn("프롬프트", cells[4])
        self.assertIn("원문 발췌 읽기는 사용자 결정, 기본값 변경 없음", cells[5])
        for word in ("한화 약 4조 2천억 원", "평가 기준", "194자", "GROUNDING_RULES"):
            with self.subTest(word=word):
                self.assertIn(word, rows[0])


class SentPromptTest(unittest.TestCase):
    """엔진이 실제로 모델에 보내는 프롬프트(generate_blog_posts → call_gemini_with_fallback)에도 규칙이 들어간다."""

    LINK = "https://www.reuters.com/a"

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        for name, value in (("DRY_RUN", True), ("STUB_GEMINI", False), ("STUB_UNSPLASH", True), ("POSTS_DIR", root / "_posts"),
                            ("HISTORY_FILE", root / "history.json")):
            patcher = mock.patch.object(g, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = mock.patch.object(g, "now_kst", return_value=at(10, 12))
        patcher.start()
        self.addCleanup(patcher.stop)

    def sent_prompts(self, src):
        sent = []

        class Response:
            text = json.dumps(long_post("시험 글", self.LINK), ensure_ascii=False)

        def fake_gemini(prompt):
            sent.append(prompt)
            return Response()

        item = dict(direct_item(src), link=self.LINK)
        with mock.patch.object(g, "fetch_news_items", lambda editorial_lane=None, stats=None, deadline=None, clock=None: [item] if editorial_lane == src["lane"] else []), \
                mock.patch.object(g, "call_gemini_with_fallback", fake_gemini), \
                mock.patch.object(g, "editorial_lane_order", lambda slot, history: [src["lane"]]):
            value, _out = run_captured(g.generate_blog_posts, slot=9, allow_auto_topic=False, report={})
        self.assertIsNotNone(value)
        return sent

    def test_the_prompt_the_engine_sends_for_each_source_has_the_rules_and_the_sources_own_rule(self):
        for src in g.NEWS_SOURCES:
            with self.subTest(source=src["name"]):
                sent = self.sent_prompts(src)
                self.assertEqual(len(sent), 1)
                for rule in g.GROUNDING_RULES:
                    self.assertIn(f"- {rule}\n", sent[0])
                if src.get("prompt_rule"):
                    self.assertIn(f"- {src['prompt_rule']}\n", sent[0])


if __name__ == "__main__":
    unittest.main()
