import copy
import re
import unittest

import _bootstrap  # noqa: F401
from pipeline import gates, registry, stubs

PROFILE = registry.load_profile("blogger_practical_ko")


def good_post(topic="출근 전 10분 가볍게 몸 깨우는 아침 루틴"):
    parsed = gates.parse_labeled_post(stubs.stub_post(topic))
    clean, stats = gates.sanitize_html(parsed["content"])
    return {"title": parsed["title"], "labels": parsed["labels"], "content": clean}, stats


def run_check(post, stats=None, recent=(), other=(), profile=PROFILE):
    return gates.check_post(post, profile, recent, other, stats)


class ParseTest(unittest.TestCase):
    def test_parses_labeled_response(self):
        parsed = gates.parse_labeled_post("제목: 테스트 제목입니다\n라벨: 수면, 생활습관, 수면\n내용:\n<p>본문</p>")
        self.assertEqual(parsed["title"], "테스트 제목입니다")
        self.assertEqual(parsed["labels"], ["수면", "생활습관"])  # 중복 제거
        self.assertEqual(parsed["content"], "<p>본문</p>")

    def test_hash_labels_and_markdown_title(self):
        parsed = gates.parse_labeled_post("제목: **굵은 제목**\n라벨: #수면 #건강\n내용:\n<p>x</p>")
        self.assertEqual(parsed["title"], "굵은 제목")
        self.assertEqual(parsed["labels"], ["수면", "건강"])

    def test_code_fences_are_stripped(self):
        parsed = gates.parse_labeled_post("```html\n제목: 제목입니다 정말로\n라벨: 가\n내용:\n<p>x</p>\n```")
        self.assertEqual(parsed["content"], "<p>x</p>")

    def test_missing_sections_raise(self):
        for raw in ("", "제목: a\n내용:\n<p>x</p>", "라벨: a\n내용:\n<p>x</p>", "제목: a\n라벨: b"):
            with self.assertRaises(gates.GateError):
                gates.parse_labeled_post(raw)

    def test_empty_title_or_body_raises(self):
        with self.assertRaises(gates.GateError):
            gates.parse_labeled_post("제목: ***\n라벨: a\n내용:\n<p>x</p>")


class SanitizeTest(unittest.TestCase):
    PAYLOADS = [
        "<script>alert(1)</script><p>ok</p>",
        "<SCRIPT SRC=//evil.example/x.js></SCRIPT>",
        "<scr<script>ipt>alert(1)</scr</script>ipt>",
        "<img src=x onerror=alert(1)>",
        "<p onclick=\"alert(1)\">hi</p>",
        "<a href=\"javascript:alert(1)\">x</a>",
        "<a href=\" javascript:alert(1)\">x</a>",
        "<a href=\"data:text/html;base64,PHNjcmlwdD4=\">x</a>",
        "<iframe src=\"https://evil.example\"></iframe>",
        "<svg onload=alert(1)><circle/></svg>",
        "<style>body{display:none}</style>",
        "<form action=\"https://evil.example\"><input></form>",
        "<object data=x></object><embed src=x>",
        "<p style=\"background:url(javascript:alert(1))\">x</p>",
        "<!--<script>alert(1)</script>-->",
        "<math><mtext></mtext></math>",
        "<noscript><p title=\"</noscript><img src=x onerror=alert(1)>\">",
    ]

    def test_no_dangerous_markup_survives(self):
        for payload in self.PAYLOADS:
            for allow_links in (False, True):
                clean, _ = gates.sanitize_html(payload, allow_links=allow_links)
                lowered = clean.lower()
                self.assertNotIn("<script", lowered, payload)
                self.assertNotIn("javascript:", lowered, payload)
                self.assertNotIn("<iframe", lowered, payload)
                self.assertNotIn("<svg", lowered, payload)
                self.assertNotIn("<img", lowered, payload)
                self.assertNotIn("<style", lowered, payload)
                self.assertNotIn("<form", lowered, payload)
                self.assertNotRegex(lowered, r"\son\w+\s*=", payload)
                self.assertNotIn("style=", lowered, payload)

    def test_script_content_is_dropped(self):
        clean, stats = gates.sanitize_html("<p>앞</p><script>alert(1)</script><p>뒤</p>")
        self.assertEqual(clean, "<p>앞</p><p>뒤</p>")
        self.assertEqual(stats["dropped_blocks"], 1)

    def test_text_is_escaped(self):
        clean, _ = gates.sanitize_html("<p>1 < 2 &lt;script&gt;alert(1)&lt;/script&gt;</p>")
        self.assertIn("&lt;script&gt;", clean)
        self.assertNotIn("<script", clean.lower())

    def test_unknown_tags_are_unwrapped_and_open_tags_closed(self):
        clean, stats = gates.sanitize_html("<div><p>안녕<strong>굵게")
        self.assertEqual(clean, "<p>안녕<strong>굵게</strong></p>")
        self.assertGreaterEqual(stats["unwrapped_tags"], 1)

    def test_links_removed_by_default_and_kept_text(self):
        clean, stats = gates.sanitize_html('<p><a href="https://example.com">링크</a></p>')
        self.assertEqual(clean, "<p>링크</p>")
        self.assertEqual(stats["links_removed"], 1)

    def test_links_allowed_only_for_https_and_allowlisted_hosts(self):
        html = '<a href="https://good.example/x?a=1&b=2">g</a><a href="https://bad.example">b</a><a href="http://good.example">h</a>'
        clean, _ = gates.sanitize_html(html, allow_links=True, allowed_hosts=("good.example",))
        self.assertIn('href="https://good.example/x?a=1&amp;b=2"', clean)
        self.assertIn('rel="nofollow noopener"', clean)
        self.assertNotIn("bad.example", clean)
        self.assertNotIn("http://good.example", clean)

    def test_attributes_are_removed(self):
        clean, _ = gates.sanitize_html('<p class="a" id="b">x</p>')
        self.assertEqual(clean, "<p>x</p>")

    def test_idempotent(self):
        once, _ = gates.sanitize_html("<div><p>a<script>x</script><b>b</p>")
        twice, _ = gates.sanitize_html(once)
        self.assertEqual(once, twice)


class CheckPostTest(unittest.TestCase):
    def test_stub_post_passes(self):
        post, stats = good_post()
        result = run_check(post, stats)
        self.assertTrue(result.ok, result.reasons)

    def mutate(self, **changes):
        post, stats = good_post()
        post = {**copy.deepcopy(post), **changes}
        return run_check(post, stats)

    def test_short_body(self):
        self.assertIn("LEN_SHORT", self.mutate(content="<h3>a</h3><h3>b</h3><h3>c</h3><ul><li>x</li></ul>").codes())

    def test_long_body(self):
        post, stats = good_post()
        post["content"] += "<p>" + "가나다라마바사 " * 600 + "</p>"
        self.assertIn("LEN_LONG", run_check(post, stats).codes())

    def test_title_rules(self):
        self.assertIn("TITLE_LEN", self.mutate(title="짧아").codes())
        self.assertIn("TITLE_BANNED", self.mutate(title="충격 이것만 알면 잠이 솔솔 옵니다").codes())

    def test_banned_medical_claims(self):
        post, stats = good_post()
        post["content"] += "<p>이 방법으로 불면증이 완치됩니다.</p>"
        self.assertIn("BANNED", run_check(post, stats).codes())
        post, stats = good_post()
        post["content"] += "<p>꾸준히 하면 근육통을 예방할 수 있습니다.</p>"
        self.assertIn("BANNED", run_check(post, stats).codes())

    def test_hedged_language_is_allowed(self):
        post, stats = good_post()
        post["content"] += "<p>일반적으로 도움이 될 수 있어요. 불편이 계속되면 전문가와 상담하세요.</p>"
        self.assertTrue(run_check(post, stats).ok)

    def test_leaks(self):
        for leak in ("<p>**강조**</p>", "<p>AI로서 말씀드리면</p>", "<p>{topic} 자리표시자</p>", "<p>죄송합니다</p>"):
            post, stats = good_post()
            post["content"] += leak
            self.assertIn("LEAK", run_check(post, stats).codes(), leak)

    def test_structure(self):
        post, stats = good_post()
        post["content"] = re.sub(r"<h3>", "<p>", post["content"]).replace("</h3>", "</p>")
        self.assertIn("STRUCT_H3", run_check(post, stats).codes())
        post, stats = good_post()
        post["content"] = re.sub(r"</?(ul|li)>", "", post["content"])
        self.assertIn("STRUCT_LIST", run_check(post, stats).codes())

    def test_language_gate(self):
        post, stats = good_post()
        post["content"] = "<h3>a</h3><h3>b</h3><h3>c</h3><ul><li>x</li></ul><p>" + "This is plain English text. " * 80 + "</p>"
        self.assertIn("LANG", run_check(post, stats).codes())

    def test_labels(self):
        self.assertIn("LABELS", self.mutate(labels=[]).codes())
        self.assertIn("LABELS", self.mutate(labels=["a", "b", "c", "d", "e", "f"]).codes())
        self.assertIn("LABELS", self.mutate(labels=["치료법"]).codes())

    def test_duplicates(self):
        post, stats = good_post()
        self.assertIn("DUP_SAME", run_check(post, stats, recent=[post["title"]]).codes())
        self.assertIn("DUP_OTHER", run_check(post, stats, other=[post["title"]]).codes())
        self.assertTrue(run_check(post, stats, recent=["전혀 다른 주제의 오래된 글 제목입니다"]).ok)

    def test_duplicate_reasons_fold_the_compared_title_into_one_safe_line(self):
        """비교 대상 제목은 이력 파일(다른 블로그는 피드·LLM 유래)에서 온다. 개행·단독 CR·U+2028 로 줄을 바꾸거나
        '::' 로 워크플로 명령을 흉내 내도 사유는 한 줄이고, 길이도 제한된다."""
        post, stats = good_post()
        evil = post["title"] + "\n::error::위조\r::notice::x\u2028##[error]y"
        result = run_check(post, stats, recent=[evil], other=[evil])
        self.assertTrue({"DUP_SAME", "DUP_OTHER"} <= set(result.codes()), result.reasons)  # 전제: 사유에 제목이 실제로 들어간다
        for reason in result.reasons:
            self.assertEqual(reason.splitlines(), [reason])   # 한 줄(개행·CR·U+2028·U+0085 모두 없음)
            self.assertNotIn("::", reason)
            self.assertNotIn("##[", reason)
        loose = copy.deepcopy(PROFILE)
        loose["similarity"] = {"same_blog": 0.01, "other_blogs": 0.01}  # 아주 긴 제목도 '비슷함'으로 잡히게 문턱을 낮춘다
        reasons = run_check(post, stats, other=[post["title"] + " " + "가" * 500], profile=loose).reasons
        dup = [r for r in reasons if r.startswith("[DUP_OTHER]")]
        self.assertEqual(len(dup), 1)
        self.assertLess(len(dup[0]), 200)
        self.assertTrue(dup[0].endswith("…"))

    def test_long_history_titles_are_compared_in_full_and_only_displayed_folded(self):
        """사유에 넣는 제목만 한 줄·100자로 접는다. 유사도 계산은 원문 전체로 한다(접힌 제목으로 계산하면 꼬리가 잘려
        거의 같은 제목으로 오판한다 — 독립 검증의 변이)."""
        post, stats = good_post()
        loose = copy.deepcopy(PROFILE)
        loose["similarity"] = {"same_blog": 0.4, "other_blogs": 0.4}
        other = post["title"] + " " + "가" * 250
        self.assertNotIn("DUP_OTHER", run_check(post, stats, other=[other], profile=loose).codes())

    def test_sanitize_warning_is_reported_but_not_blocking(self):
        post, _ = good_post()
        result = run_check(post, {"dropped_blocks": 1, "unwrapped_tags": 0, "links_removed": 0})
        self.assertTrue(result.ok)
        self.assertTrue(any("SANITIZED" in w for w in result.warnings))

    def test_disclosure_is_appended(self):
        out = gates.append_disclosure("<p>본문</p>", PROFILE)
        self.assertTrue(out.startswith("<p>본문</p>"))
        self.assertIn("AI의 도움", out)


class TopicAllowedTest(unittest.TestCase):
    def test_banned_topics(self):
        for topic in ("임신 중 안전한 운동", "혈압 약 복용 시간", "암 예방 식단", "다이어트 약 후기", "우울증 치료 습관"):
            self.assertFalse(gates.topic_allowed(topic, PROFILE), topic)

    def test_allowed_topics_including_word_boundary_cases(self):
        for topic in ("암막 커튼으로 수면 환경 만들기", "집에서 쉽게 하는 스트레칭 루틴", "암기가 잘 되는 공부 환경 만들기"):
            self.assertTrue(gates.topic_allowed(topic, PROFILE), topic)


class SimilarityTest(unittest.TestCase):
    def test_similarity_bounds(self):
        self.assertEqual(gates.similarity("", "abc"), 0.0)
        self.assertAlmostEqual(gates.similarity("같은 제목", "같은 제목"), 1.0)
        self.assertLess(gates.similarity("아침 루틴 만들기", "저녁 식단 구성하기"), 0.5)


if __name__ == "__main__":
    unittest.main()
