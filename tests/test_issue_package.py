"""초안 패키지(GitHub 이슈) 어댑터 시험 — pipeline/publishers/issue_package.py.

① 소독(멘션·이슈 참조·펜스·HTML·길이·제목) ② 본문 모양(티스토리 HTML 상자·네이버 서식 있는 글·체크리스트·이미지·출처·게이트)
③ HTML → 마크다운 ④ GitHub REST 호출(가짜 서버): 멱등·라벨·적체·오류 분류·비밀 가림.
"""
import http.client
import json
import random
import re
import unittest
import urllib.error
from html.parser import HTMLParser

import _bootstrap  # noqa: F401
from package_helpers import REPO, FakeGitHub, FakeResponse, fake_token, http_error
from pipeline import gates
from pipeline.publishers import issue_package as ip
from pipeline.publishers.base import PublishError

ZW = ip.ZWSP
GOOD_HTML = ("<p>첫 문단입니다.</p><h3>1. 소제목</h3><p>둘째 문단 <strong>굵게</strong> 와 <em>기울임</em>.</p>"
             "<ul><li>하나</li><li>둘</li></ul><p><em>이 글은 AI의 도움을 받아 작성했습니다.</em></p>")
LABELS = {"tistory": "티스토리", "naver": "네이버"}


def make_draft(platform="tistory", **over):
    values = dict(blog_key=f"{platform}_test", platform=platform, channel_label=LABELS.get(platform, "블로그"), date="2026-10-21",
                  title="테스트 글 제목입니다", html=GOOD_HTML, tags=["생활습관", "루틴"])
    values.update(over)
    return ip.PackageDraft(**values)


# ----------------------------------------------------------------------------
# 마크다운 구조를 CommonMark 규칙으로 읽는 작은 도구(펜스 이스케이프가 '의미상' 지켜지는지 본다)
# ----------------------------------------------------------------------------
def fenced_blocks(markdown):
    """(info, 내용) 목록과 펜스 밖의 글. 열기: 들여쓰기 3칸 이하의 백틱 3개 이상(info 에 백틱 없음), 닫기: 같거나 더 긴 백틱 줄."""
    blocks, outside, lines, i = [], [], markdown.split("\n"), 0
    while i < len(lines):
        match = re.match(r"^ {0,3}(`{3,})([^`]*)$", lines[i])
        if not match:
            outside.append(lines[i])
            i += 1
            continue
        ticks, info, inner = match.group(1), match.group(2).strip(), []
        i += 1
        while i < len(lines) and not re.match(r"^ {0,3}`{%d,}\s*$" % len(ticks), lines[i]):
            inner.append(lines[i])
            i += 1
        blocks.append((info, "\n".join(inner)))
        i += 1        # 닫는 줄(없으면 문서 끝)
    return blocks, "\n".join(outside)


LIVE_MENTION = re.compile(r"(?<![A-Za-z0-9_])@(?=[A-Za-z0-9])")
LIVE_REF = re.compile(r"#(?=\d)|(?i:GH-)(?=\d)")


def without_urls(text):
    return re.sub(r"https?://[^\s<>\"'`]+", "", text)


class TagCollector(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags, self.attrs = [], []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        self.attrs += [name for name, _ in attrs]


# ----------------------------------------------------------------------------
# 1) 소독
# ----------------------------------------------------------------------------
class NeutralizeTest(unittest.TestCase):
    def test_a_mention_gets_a_zero_width_space_right_after_the_at_sign(self):
        for text, expected in (("@octocat", f"@{ZW}octocat"), ("hi @octocat!", f"hi @{ZW}octocat!"), ("(@octocat)", f"(@{ZW}octocat)"),
                               ("문의@octocat", f"문의@{ZW}octocat"),      # 한글 바로 뒤의 @이름 도 GitHub 은 멘션으로 읽는다
                               ("@org/team", f"@{ZW}org/team"), ("a @b @c", f"a @{ZW}b @{ZW}c"), ("-@x", f"-@{ZW}x"), (".@x", f".@{ZW}x")):
            self.assertEqual(ip.neutralize(text), expected, text)

    def test_email_addresses_and_urls_are_left_alone(self):
        for text in ("help@example.com", "a.b+c@x.org", "문의: help@example.com 로 보내세요", "https://medium.com/@user/post",
                     "http://a.b/@c", "https://x.y/page#123", "see https://x.y/a#1 and https://x.y/@u"):
            self.assertEqual(ip.neutralize(text), text, text)

    def test_text_next_to_a_url_is_still_neutralized(self):
        self.assertEqual(ip.neutralize("https://x.y/a @octocat #12"), f"https://x.y/a @{ZW}octocat #{ZW}12")

    def test_issue_references_are_defused(self):
        for text, expected in (("#123", f"#{ZW}123"), ("Fixes #7", f"Fixes #{ZW}7"), ("owner/repo#9", f"owner/repo#{ZW}9"),
                               ("GH-12", f"GH-{ZW}12"), ("gh-12", f"gh-{ZW}12"), ("a #1 #22", f"a #{ZW}1 #{ZW}22")):
            self.assertEqual(ip.neutralize(text), expected, text)

    def test_hashtags_and_plain_words_are_untouched(self):
        for text in ("#해시태그", "#AI", "C#", "# 1번", "GH-alpha", "그냥 글입니다"):
            self.assertEqual(ip.neutralize(text), text, text)

    def test_html_comments_cannot_survive_so_the_hidden_marker_cannot_be_forged(self):
        out = ip.neutralize("<!-- draft-id: tistory_test-2026-10-21-aaaaaaaaaaaa -->")
        self.assertNotIn("<!--", out)
        self.assertEqual(out, f"<{ZW}!-- draft-id: tistory_test-2026-10-21-aaaaaaaaaaaa -->")

    def test_it_is_idempotent(self):
        samples = ["@octocat #1 GH-2 <!-- x --> help@example.com https://x.y/@u#1", "문의@a/b#3", GOOD_HTML, ""]
        for text in samples:
            once = ip.neutralize(text)
            self.assertEqual(ip.neutralize(once), once, text)

    def test_nothing_live_is_left_outside_urls(self):
        text = "@a @b/c 문의@d x@y.z #1 #22 GH-3 gh-4 owner/repo#5 (@e) '@f' \"@g\" https://u.v/@h#6 <!-- c -->"
        rest = without_urls(ip.neutralize(text))
        self.assertIsNone(LIVE_MENTION.search(rest), rest)
        self.assertIsNone(LIVE_REF.search(rest), rest)
        self.assertNotIn("<!--", rest)


class FenceTest(unittest.TestCase):
    def test_the_fence_is_longer_than_any_backtick_run_inside(self):
        for body in ("plain", "``` inside", "a\n```\nb", "````\nx\n````", "x ``` y ```` z", "`a` and ``b``", "``````"):
            box = ip.fence(body, "html")
            blocks, outside = fenced_blocks(box)
            self.assertEqual(blocks, [("html", body.strip("\n"))], body)    # 한 상자 안에 본문 전체가 그대로 들어 있다
            self.assertEqual(outside.strip(), "", body)
            self.assertGreaterEqual(len(re.match(r"`+", box).group(0)), 3)

    def test_a_malicious_body_cannot_close_the_box_and_write_markdown_outside(self):
        body = "```\n# 가짜 제목\n- [ ] 가짜 체크\n@octocat\n```\n\n<script>x</script>"
        blocks, outside = fenced_blocks("앞\n\n" + ip.fence(body, "text") + "\n\n뒤")
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0][1], body)
        self.assertEqual(outside.split(), ["앞", "뒤"])          # 상자 밖에는 우리가 쓴 글뿐이고 가짜 제목·체크·멘션이 없다


class TitleTest(unittest.TestCase):
    def test_prefix_is_fixed_and_label_comes_from_the_channel(self):
        self.assertEqual(ip.issue_title("티스토리", "안녕 세상"), "[초안][티스토리] 안녕 세상")
        self.assertEqual(ip.issue_title("네이버", "안녕 세상"), "[초안][네이버] 안녕 세상")

    def test_title_part_is_cut_at_sixty_characters(self):
        title = ip.issue_title("티스토리", "가" * 100)
        shown = title[len("[초안][티스토리] "):]
        self.assertEqual(len(shown), 60)
        self.assertTrue(shown.endswith("…"))
        self.assertEqual(ip.issue_title("티스토리", "가" * 60)[len("[초안][티스토리] "):], "가" * 60)   # 정확히 60자는 자르지 않는다

    def test_newlines_tabs_cr_and_unicode_line_separators_fold_into_spaces(self):
        title = ip.issue_title("티스토리", "첫 줄\n::error::위조\r둘째 셋째\t넷째\u0085다섯")
        self.assertNotRegex(title, "[\n\r\t \u0085]")
        self.assertEqual(title, "[초안][티스토리] 첫 줄 ::error::위조 둘째 셋째 넷째다섯")

    def test_html_tags_comments_and_script_blocks_are_removed(self):
        self.assertEqual(ip.issue_title("티스토리", "<b>굵은</b> 제목<script>alert(1)</script> 끝"), "[초안][티스토리] 굵은 제목 끝")
        self.assertEqual(ip.issue_title("티스토리", "A<!-- 숨김 -->B"), "[초안][티스토리] A B")
        self.assertEqual(ip.issue_title("티스토리", "<iframe src=x>가</iframe><style>p{}</style>나"), "[초안][티스토리] 나")
        self.assertNotIn("<", ip.issue_title("티스토리", "<img src=x onerror=1>제목<object data=y>z</object>"))

    def test_mentions_and_issue_references_in_the_title_are_defused(self):
        title = ip.issue_title("티스토리", "@octocat 님 #12 GH-3 확인")
        self.assertEqual(title, f"[초안][티스토리] @{ZW}octocat 님 #{ZW}12 GH-{ZW}3 확인")

    def test_the_model_cannot_choose_the_prefix(self):
        title = ip.issue_title("티스토리", "[초안][네이버] 가짜 접두사")
        self.assertTrue(title.startswith("[초안][티스토리] "))

    def test_bidi_overrides_and_control_characters_are_dropped(self):
        title = ip.issue_title("티스토리", "정상‮뒤집힘⁦\x07\x1b[31m빨강")
        for char in ("‮", "⁦", "\x07", "\x1b"):
            self.assertNotIn(char, title)

    def test_zero_width_space_is_not_removed_so_neutralizing_survives_a_second_pass(self):
        self.assertEqual(ip.clean(f"a@{ZW}b"), f"a@{ZW}b")


# ----------------------------------------------------------------------------
# 2) HTML → 마크다운·평문
# ----------------------------------------------------------------------------
class MarkdownTest(unittest.TestCase):
    def md(self, html):
        return ip.to_markdown(gates.sanitize_html(html)[0])

    def test_blocks_and_inline_formatting(self):
        for html, expected in (
                ("<p>a</p><p>b</p>", "a\n\nb"),
                ("<h2>제목</h2>", "### 제목"), ("<h3>소제목</h3>", "#### 소제목"), ("<h4>더 작은</h4>", "##### 더 작은"),
                ("<p>a <strong>b</strong> <em>c</em></p>", "a **b** *c*"),
                ("<p><b>굵게</b>와<i>기울임</i></p>", "**굵게**와*기울임*"),
                ("<p>끝 <strong> 공백 </strong> 앞</p>", "끝  **공백**  앞".replace("  ", " ")),
                ("<ul><li>하나</li><li>둘</li></ul>", "- 하나\n- 둘"),
                ("<ol><li>하나</li><li>둘</li></ol>", "1. 하나\n2. 둘"),
                ("<ul><li>a<ul><li>b</li></ul></li><li>c</li></ul>", "- a\n  - b\n- c"),
                ("<ol><li>a<ol><li>b</li></ol></li></ol>", "1. a\n   1. b"),
                ("<blockquote><p>인용</p></blockquote>", "> 인용"),
                ("<p>줄1<br>줄2</p>", "줄1\\\n줄2"),
                ("<p>  앞뒤   공백\n줄바꿈   접기 </p>", "앞뒤 공백 줄바꿈 접기")):
            self.assertEqual(self.md(html), expected, html)

    def test_syntax_characters_in_the_text_are_escaped(self):
        for html, expected in (
                ("<p>1. 번호처럼 보이는 글</p>", "1\\. 번호처럼 보이는 글"),
                ("<p># 제목처럼 보이는 글</p>", "\\# 제목처럼 보이는 글"),
                ("<p>- 목록처럼 보이는 글</p>", "\\- 목록처럼 보이는 글"),
                ("<p>+ 더하기로 시작</p>", "\\+ 더하기로 시작"),
                ("<p>=== 밑줄처럼</p>", "\\=== 밑줄처럼"),
                ("<p>[ ] 체크칸처럼</p>", "\\[ \\] 체크칸처럼"),
                ("<p>a | b</p>", "a \\| b"),
                ("<p>$5 와 $10</p>", "\\$5 와 \\$10"),
                ("<p>`코드` 와 *별* 과 _밑줄_ 과 ~~취소~~</p>", "\\`코드\\` 와 \\*별\\* 과 \\_밑줄\\_ 과 \\~\\~취소\\~\\~"),
                ("<p>&lt;script&gt;alert(1)&lt;/script&gt;</p>", "\\<script\\>alert(1)\\</script\\>"),
                ("<p>![x](http://evil.example/x.png)</p>", "!\\[x\\](http://evil.example/x.png)"),
                ("<p>[클릭](javascript:alert(1))</p>", "\\[클릭\\](javascript:alert(1))"),
                ("<p>a &amp; b &#64;octocat</p>", f"a \\& b @{ZW}octocat"),
                ("<p>백슬래시 \\ 와 <b>굵은 # 해시</b></p>", "백슬래시 \\\\ 와 **굵은 # 해시**")):
            self.assertEqual(self.md(html), expected, html)

    def test_a_hard_break_followed_by_a_list_looking_line_is_still_escaped(self):
        self.assertEqual(self.md("<p>가<br>- 나<br>1. 다<br># 라</p>"), "가\\\n\\- 나\\\n1\\. 다\\\n\\# 라")

    def test_mentions_and_references_inside_the_text_are_defused(self):
        self.assertEqual(self.md("<p>@octocat 와 #12 와 GH-3</p>"), f"@{ZW}octocat 와 #{ZW}12 와 GH-{ZW}3")

    def test_links_are_kept_only_when_the_sanitizer_allowed_them(self):
        html = '<p><a href="https://example.com/a">링크</a></p>'
        self.assertEqual(ip.to_markdown(gates.sanitize_html(html, allow_links=True)[0]), "[링크](https://example.com/a)")
        self.assertEqual(ip.to_markdown(gates.sanitize_html(html)[0]), "링크")
        self.assertEqual(ip.to_markdown('<p><a href="https://e.com/x)y">t</a><a href="javascript:alert(1)">u</a></p>'), "tu")

    def test_headings_never_contain_a_hard_break_or_nest(self):
        self.assertEqual(self.md("<h3>가<br>나</h3>"), "#### 가 나")

    def test_empty_list_items_are_dropped_and_the_numbers_stay_consecutive(self):
        """빈 `<li>`가 마커만 남은 "1." 한 줄이 되거나 번호를 건너뛰게 하지 않는다(마크다운·평문 모두)."""
        for html, expected in (
                ("<ol><li></li><li>둘</li></ol>", "1. 둘"),
                ("<ol><li>가</li><li></li><li>나</li></ol>", "1. 가\n2. 나"),
                ("<ul><li> </li><li>a</li><li><p></p></li><li>b</li></ul>", "- a\n- b"),
                ("<ol><li></li></ol><p>끝</p>", "끝")):
            self.assertEqual(self.md(html), expected, html)
            self.assertEqual(ip.to_plain(gates.sanitize_html(html)[0]), expected, html)

    def test_a_paragraph_nested_in_a_paragraph_or_holding_a_list_is_split_into_blocks(self):
        """문단 안의 문단·목록이 앞뒤 글과 붙어("ab") 보이지 않게 따로 뗀다(마크다운·평문 모두)."""
        for html, expected in (
                ("<p>a<p>b</p></p>", "a\n\nb"),
                ("<p>a<p>b<p>c</p></p></p>", "a\n\nb\n\nc"),
                ("<p>앞<ul><li>x</li></ul>뒤</p>", "앞\n\n- x\n\n뒤")):
            self.assertEqual(self.md(html), expected, html)
            self.assertEqual(ip.to_plain(gates.sanitize_html(html)[0]), expected, html)

    def test_text_directly_inside_a_list_is_kept_as_an_item_in_both_forms(self):
        html = "<ul>글<li>항목</li></ul>"
        self.assertEqual(self.md(html), "- 글\n- 항목")
        self.assertEqual(ip.to_plain(gates.sanitize_html(html)[0]), "- 글\n- 항목")

    def test_plain_text_keeps_structure_without_markdown_characters(self):
        html = ("<h3>1. 소제목</h3><p>문단 <strong>굵게</strong><br>다음 줄</p><ul><li>하나</li><li>둘<ul><li>속</li></ul></li></ul>"
                "<ol><li>첫째</li><li>둘째</li></ol><blockquote><p>인용</p></blockquote>")
        self.assertEqual(ip.to_plain(gates.sanitize_html(html)[0]),
                         "1. 소제목\n\n문단 굵게\n다음 줄\n\n- 하나\n- 둘\n  - 속\n\n1. 첫째\n2. 둘째\n\n> 인용")

    def test_plain_text_defuses_mentions_and_keeps_literal_angle_brackets(self):
        plain = ip.to_plain(gates.sanitize_html("<p>@octocat #5 &lt;b&gt; &amp; 끝</p>")[0])
        self.assertEqual(plain, f"@{ZW}octocat #{ZW}5 <b> & 끝")


# ----------------------------------------------------------------------------
# 3) 본문 모양
# ----------------------------------------------------------------------------
class BodyTest(unittest.TestCase):
    def build(self, platform="tistory", **over):
        return ip.build_issue(make_draft(platform, **over))

    def headings(self, body):
        return re.findall(r"^## (\d+)\. (.+)$", body, re.M)

    def test_the_first_line_is_the_hidden_draft_id_and_it_appears_once(self):
        for platform in ("tistory", "naver"):
            spec = self.build(platform)
            self.assertEqual(spec.body.split("\n", 1)[0], f"<!-- draft-id: {spec.draft_id} -->")
            self.assertEqual(spec.body.count("<!-- draft-id:"), 1)
            self.assertRegex(spec.draft_id, rf"^{platform}_test-2026-10-21-[0-9a-f]{{12}}$")

    def test_draft_id_follows_the_blog_the_day_and_the_content(self):
        base = self.build().draft_id
        self.assertEqual(self.build().draft_id, base)                                               # 같은 글 = 같은 번호
        self.assertNotEqual(self.build(date="2026-10-22").draft_id, base)
        self.assertNotEqual(self.build(title="다른 제목입니다").draft_id, base)
        self.assertNotEqual(self.build(html=GOOD_HTML + "<p>덧붙임</p>").draft_id, base)
        self.assertNotEqual(self.build("naver").draft_id.split("-")[0], base.split("-")[0])
        self.assertNotEqual(self.build(blog_key="tistory_other").draft_id, base)
        self.assertEqual(self.build(tags=["다른", "태그"]).draft_id, base)                          # 태그·게이트 설명은 번호에 들어가지 않는다

    def test_labels_and_title_are_fixed_values(self):
        tistory, naver = self.build(), self.build("naver")
        self.assertEqual(tistory.labels, ["초안", "채널:티스토리"])
        self.assertEqual(naver.labels, ["초안", "채널:네이버"])
        self.assertEqual(tistory.title, "[초안][티스토리] 테스트 글 제목입니다")
        self.assertEqual(naver.title, "[초안][네이버] 테스트 글 제목입니다")

    def test_tistory_sections_are_in_order_and_the_html_box_holds_clean_html(self):
        spec = self.build()
        self.assertEqual([title for _, title in self.headings(spec.body)],
                         ["복사용 제목", "본문 — HTML 모드에 붙여넣기", "해시태그(쉼표로 구분, # 없음)", "이미지", "근거 출처", "게이트 점검 결과", "발행 체크리스트"])
        self.assertEqual([number for number, _ in self.headings(spec.body)], [str(n) for n in range(1, 8)])
        blocks, _ = fenced_blocks(spec.body)
        self.assertEqual([info for info, _ in blocks], ["text", "html", "text"])
        self.assertEqual(blocks[0][1], "테스트 글 제목입니다")
        self.assertEqual(blocks[1][1], gates.sanitize_html(GOOD_HTML)[0])
        self.assertEqual(blocks[2][1], "생활습관, 루틴")

    def test_naver_has_a_rendered_section_between_rules_and_a_plain_text_box(self):
        spec = self.build("naver")
        self.assertEqual([title for _, title in self.headings(spec.body)],
                         ["복사용 제목", "본문 — 서식 있는 글(이 화면에서 복사)", "본문 — 평문(서식이 깨질 때)", "해시태그(쉼표로 구분, # 없음)", "이미지", "근거 출처",
                          "게이트 점검 결과", "발행 체크리스트"])
        rendered = spec.body.split("\n---\n")[1]
        self.assertIn("#### 1. 소제목", rendered)
        self.assertIn("**굵게**", rendered)
        self.assertIn("- 하나\n- 둘", rendered)
        blocks, _ = fenced_blocks(spec.body)
        self.assertEqual([info for info, _ in blocks], ["text", "text", "text"])         # 제목·평문·태그. HTML 상자는 없다
        self.assertNotIn("<p>", spec.body)
        self.assertIn("첫 문단입니다.", blocks[1][1])

    def test_the_checklist_is_the_agreed_eight_items_for_tistory(self):
        spec = self.build()
        items = re.findall(r"^- \[ \] (.+)$", spec.body, re.M)
        self.assertEqual(items, ["제목 붙여넣기", "HTML 모드로 본문 붙여넣기", "대표 이미지 업로드(외부 링크 이미지는 목록 썸네일에 안 나온다)",
                                 "카테고리·홈주제 선택", "태그 붙여넣기", "직접 경험·판단 문단을 더했다(AI 글을 그대로 올리지 않는다)",
                                 "광고·협찬 표기 필요 여부 확인", "발행 후 주소 기록하고 이 이슈 닫기"])

    def test_the_naver_checklist_changes_only_what_does_not_apply(self):
        tistory = re.findall(r"^- \[ \] (.+)$", self.build().body, re.M)
        naver = re.findall(r"^- \[ \] (.+)$", self.build("naver").body, re.M)
        self.assertEqual(len(naver), 8)
        self.assertEqual([i for i, (a, b) in enumerate(zip(tistory, naver)) if a != b], [1, 2, 3])    # HTML 모드·외부 이미지 썸네일·홈주제는 티스토리 이야기
        self.assertNotIn("HTML", " ".join(naver))
        self.assertEqual((naver[0], naver[4], naver[5], naver[6], naver[7]), (tistory[0], tistory[4], tistory[5], tistory[6], tistory[7]))

    def test_the_draft_is_marked_as_unpublished_and_ai_made(self):
        for platform, service in (("tistory", "티스토리"), ("naver", "네이버 블로그")):
            body = self.build(platform).body
            self.assertIn(f"아직 {service}에 공개되지 않았습니다", body)
            self.assertIn("AI가 만든 초안", body)
            self.assertIn("사실 확인은 하지 않았습니다", body)
            self.assertIn("라벨 `폐기`", body)

    def test_tags_are_comma_separated_without_hash_marks_and_deduped(self):
        spec = self.build(tags=["#생활습관", " 루틴, ", "생활습관", "", "#", "AI 도구"])
        self.assertEqual(fenced_blocks(spec.body)[0][2][1], "생활습관, 루틴, AI 도구")
        self.assertEqual(len(re.findall(r"^[^\n]*,[^\n]*$", fenced_blocks(self.build(tags=[f"t{i}" for i in range(30)]).body)[0][2][1], re.M)), 1)
        self.assertEqual(fenced_blocks(self.build(tags=[f"t{i}" for i in range(30)]).body)[0][2][1].count(","), ip.TAGS_MAX - 1)
        self.assertIn("글에 라벨이 없습니다", self.build(tags=[]).body)

    def test_images_table_has_the_agreed_columns_and_the_ai_flag(self):
        images = [{"purpose": "대표", "url": "https://images.example/a.jpg", "source": "직접 촬영", "license": "저작권자 본인", "ai_generated": False},
                  {"purpose": "본문 1", "url": "https://images.example/b.png", "source": "AI 이미지 생성", "license": "서비스 약관", "ai_generated": True},
                  {"purpose": "본문 2", "url": "https://images.example/c.png"}]
        body = self.build(images=images).body
        self.assertIn("| 번호 | 용도 | 주소 | 출처 | 라이선스 | AI 생성 이미지 |", body)
        self.assertIn("| 1 | 대표 | `https://images.example/a.jpg` | 직접 촬영 | 저작권자 본인 | 아니오 |", body)
        self.assertIn("| 2 | 본문 1 | `https://images.example/b.png` | AI 이미지 생성 | 서비스 약관 | 예 |", body)
        self.assertIn("| 3 | 본문 2 | `https://images.example/c.png` | 출처 확인 필요 | 확인 필요 | 확인 필요 |", body)     # 모르면 '아니오' 가 아니라 확인 필요
        self.assertNotIn("Unsplash", body.split("## 이미지")[0] if "## 이미지" in body else "")

    def test_unsplash_images_get_the_attribution_text_with_both_links(self):
        images = [{"purpose": "대표", "url": "https://images.unsplash.com/photo-1", "source": "Unsplash", "author": "홍 길동",
                   "author_url": "https://unsplash.com/@gildong", "license": "Unsplash License", "ai_generated": False}]
        body = self.build(images=images).body
        self.assertIn("**Unsplash 이미지는 글 아래에 작가와 Unsplash 링크를 표기해야 합니다.**", body)
        self.assertIn("1번: Photo by [홍 길동](https://unsplash.com/@gildong?utm_source=chanceblog&utm_medium=referral) on "
                      "[Unsplash](https://unsplash.com/?utm_source=chanceblog&utm_medium=referral)", body)

    def test_image_rows_with_unsafe_urls_are_dropped(self):
        images = [{"url": "http://insecure.example/a.jpg"}, {"url": "javascript:alert(1)"}, {"url": "https://a.example/x y.jpg"},
                  {"url": "https://a.example/a|b.jpg"}, {"url": "https://a.example/a`b.jpg"}, "문자열", None, {"url": "https://ok.example/1.jpg"}]
        body = self.build(images=images).body
        self.assertIn("| 1 | - | `https://ok.example/1.jpg` |", body)
        self.assertEqual(body.count("| 1 |") + body.count("| 2 |"), 1)
        for bad in ("insecure", "javascript", "x y.jpg", "a|b", "a`b"):
            self.assertNotIn(bad, body)

    def test_no_images_says_so_and_tistory_warns_about_the_thumbnail(self):
        tistory, naver = self.build().body, self.build("naver").body
        for body in (tistory, naver):
            self.assertIn("자동으로 고른 이미지가 없습니다", body)
            self.assertNotIn("| 번호 |", body)
        self.assertIn("목록 썸네일에는 나오지 않습니다", tistory)
        self.assertNotIn("목록 썸네일에는 나오지 않습니다", naver)
        self.assertIn("(미확인)", naver)

    def test_sources_are_listed_as_links_and_unsafe_ones_dropped(self):
        sources = [{"title": "공식 문서", "url": "https://docs.example/guide"}, {"title": "나쁜 주소", "url": "http://x.example"},
                   {"title": "[제목](https://evil.example)", "url": "https://ok.example/p"}]
        body = self.build(sources=sources).body
        self.assertIn("- [공식 문서](https://docs.example/guide)", body)
        self.assertIn("- [\\[제목\\](https://evil.example)](https://ok.example/p)", body)      # 제목 안의 링크 문법은 글자가 된다(대괄호가 이스케이프됨)
        self.assertNotIn("나쁜 주소", body)
        self.assertIn("자동으로 모은 출처가 없습니다", self.build().body)

    def test_gate_section_reports_numbers_warnings_and_what_it_cannot_check(self):
        gate = {"attempts": 2, "model": "gemini-3.8-flash", "chars": 1234, "min_chars": 900, "max_chars": 3200, "title_chars": 20, "title_min": 8,
                "title_max": 60, "warnings": ["[SANITIZED] HTML 정화로 제거됨: {'dropped_blocks': 1}"], "removed": {"dropped_blocks": 1, "links_removed": 2, "zero": 0}}
        body = self.build(gate=gate).body
        section = body.split("## 6. 게이트 점검 결과")[1].split("## 7.")[0]
        self.assertIn("- 결과: **통과**(재작성 1회, 시도 2번째에 통과)", section)
        self.assertIn("- 모델: gemini-3.8-flash", section)
        self.assertIn("- 분량: 본문 1234자(기준 900~3200자) · 제목 20자(기준 8~60자)", section)
        self.assertIn("내용째 지운 블록(script·iframe 등) 1건, 지운 링크 2건", section)
        self.assertNotIn("zero", section)
        self.assertIn("- 참고: \\[SANITIZED\\] HTML 정화로 제거됨", section)             # 대괄호도 이스케이프된다
        self.assertIn("**사실 확인은 하지 않았습니다.**", section)
        self.assertIn("정화로 제거된 것: 없음", self.build().body)

    def test_a_missing_or_odd_gate_dict_still_builds(self):
        for gate in ({}, None, {"attempts": "x", "chars": True, "removed": [1], "warnings": "abc"}):
            self.assertIn("## 6. 게이트 점검 결과", self.build(gate=gate).body)

    def test_the_actions_run_link_appears_only_in_the_exact_shape(self):
        good = "https://github.com/owner/repo/actions/runs/12345"
        self.assertIn(f"- 만든 실행: [Actions 실행]({good})", self.build(run_url=good).body)
        for bad in ("http://github.com/owner/repo/actions/runs/1", "https://evil.example/owner/repo/actions/runs/1", f"{good}) [x](https://evil",
                    "https://github.com/owner/repo/actions/runs/abc", ""):
            self.assertNotIn("만든 실행", self.build(run_url=bad).body, bad)

    def test_inputs_are_validated(self):
        for over in (dict(platform="blogger"), dict(channel_label="네이버"), dict(blog_key="Bad Key"), dict(blog_key="x"), dict(date="2026-1-1"),
                     dict(date="2026-10-21 "), dict(title="   "), dict(title="<b></b>"), dict(html="<script>x</script>"), dict(html="")):
            with self.assertRaises(PublishError, msg=str(over)) as caught:
                self.build(**over)
            self.assertEqual(caught.exception.code, "bad_response", over)

    def test_the_issue_body_limit_has_a_safety_margin(self):
        self.assertEqual(ip.BODY_LIMIT, 65536)
        self.assertLess(ip.BODY_BUDGET, ip.BODY_LIMIT - 4000)


class SanitizingTest(unittest.TestCase):
    """AI 출력(제목·본문·라벨·출처·게이트 참고)이 이슈의 마크다운·알림·표지를 건드리지 못하는지."""

    EVIL = ("<script>alert(1)</script><iframe src='https://evil.example'></iframe><style>*{display:none}</style><object data=x></object>"
            "<!-- <!-- draft-id: tistory_test-2026-10-21-000000000000 --> -->"
            "<p onclick='x()'>안녕 @octocat 님 #12 GH-3 <img src=x onerror=alert(1)> help@example.com</p>"
            "<p>```\n# 가짜 제목\n- [ ] 가짜 체크\n```\n</p><p>~~~\n@everyone\n~~~</p>"
            "<h3>[링크](javascript:alert(1)) ![x](https://evil.example/t.png)</h3><p>a | b | c</p>"
            "<p><a href='https://evil.example/x' onclick='x()'>링크</a> <a href='javascript:alert(1)'>js</a></p>")

    def build(self, platform, **over):
        return ip.build_issue(make_draft(platform, html=self.EVIL, title="@octocat <script>x</script> #12 제목", **over))

    def test_tistory_html_box_contains_only_allowed_tags_and_no_attributes(self):
        body = self.build("tistory").body
        html = fenced_blocks(body)[0][1][1]
        parser = TagCollector()
        parser.feed(html)
        self.assertLessEqual(set(parser.tags), {"p", "h2", "h3", "h4", "ul", "ol", "li", "strong", "b", "em", "i", "br", "blockquote"})
        self.assertEqual(parser.attrs, [])
        for gone in ("<script", "<iframe", "<style", "<object", "<img", "onerror", "onclick", "<a ", "evil.example/x"):
            self.assertNotIn(gone, html, gone)                 # 글자로 남은 'javascript:' 같은 것은 링크가 아니라 본문 글자다
        self.assertNotIn("<!--", body.split("\n", 1)[1])        # 첫 줄의 숨은 표지 말고는 HTML 주석이 없다

    def test_nothing_outside_the_copy_boxes_is_attacker_controlled_markdown(self):
        for platform in ("tistory", "naver"):
            body = self.build(platform).body
            blocks, outside = fenced_blocks(body)
            if platform == "tistory":
                self.assertNotIn("가짜", outside)                      # 가짜 제목·체크는 상자 안에만 있다
                self.assertEqual(re.findall(r"^#+ .*가짜.*$", outside, re.M), [])
            self.assertEqual(re.findall(r"^- \[[ xX]\] .*가짜.*$", outside, re.M), [], platform)
            self.assertNotIn("@everyone", without_urls(outside).replace(f"@{ZW}everyone", ""), platform)

    def test_no_live_mention_or_reference_anywhere_in_the_body(self):
        for platform in ("tistory", "naver"):
            body = without_urls(self.build(platform).body)
            self.assertIsNone(LIVE_MENTION.search(body), (platform, LIVE_MENTION.search(body)))
            self.assertIsNone(LIVE_REF.search(body), (platform, LIVE_REF.search(body)))

    def test_the_title_is_clean(self):
        title = self.build("tistory").title
        self.assertEqual(title, f"[초안][티스토리] @{ZW}octocat #{ZW}12 제목")      # <script>…</script> 는 내용째 지워지고 멘션·참조는 풀린다
        self.assertNotIn("<", title)
        self.assertNotIn("script", title)

    def test_the_naver_rendered_part_has_no_raw_html_or_images_or_live_links(self):
        body = self.build("naver").body
        rendered = body.split("\n---\n")[1]
        self.assertIsNone(re.search(r"<[A-Za-z!/]", rendered), rendered)
        self.assertNotRegex(rendered, r"(?<!\\)!\[")
        self.assertNotRegex(rendered, r"(?<!\\)\]\(")
        self.assertNotRegex(rendered, r"(?m)^#{1,2} ")           # 이슈의 구역 제목(##)을 흉내 낼 수 없다
        self.assertNotRegex(rendered, r"(?m)^\s*(?:[-*+]|\d+[.)]) \[[ xX]\]")

    def test_a_forged_marker_inside_the_post_cannot_become_the_real_one(self):
        spec = self.build("tistory")                      # EVIL 에는 가짜 draft-id 표지가 들어 있다
        self.assertEqual(spec.body.count("<!--"), 1)
        self.assertEqual(ip._MARKER_RX.match(spec.body).group(1), spec.draft_id)
        self.assertNotEqual(spec.draft_id, "tistory_test-2026-10-21-000000000000")
        plain = fenced_blocks(self.build("naver").body)[0][1][1]       # 평문 상자에는 글자가 그대로 남지만 주석 시작 글자는 풀려 있다
        self.assertNotIn("<!--", plain)

    def test_backticks_and_tildes_in_the_post_cannot_break_the_boxes(self):
        html = "<p>" + "`" * 3 + "\n" + "`" * 7 + "\n```html\n~~~~\n</p>"
        for platform in ("tistory", "naver"):
            body = ip.build_issue(make_draft(platform, html=html)).body
            blocks, outside = fenced_blocks(body)
            self.assertNotIn("```", outside, platform)        # 열린 채로 남았거나 빠져나온 펜스가 없다
            self.assertEqual(len(blocks), 3, platform)         # 제목·본문(또는 평문)·태그 상자가 구조대로 모두 닫혔다
            self.assertTrue(any("`" * 7 in content for _, content in blocks), platform)

    def test_a_very_long_row_of_backticks_cannot_push_the_body_past_the_budget(self):
        body = ip.build_issue(make_draft("tistory", html="<p>" + "`" * 5000 + "</p>")).body
        self.assertLessEqual(len(body), ip.BODY_BUDGET)

    def test_zero_width_and_bidi_characters_in_the_title_do_not_hide_a_mention(self):
        title = ip.issue_title("티스토리", "정상‮ @octocat ‬ 끝")
        self.assertNotIn("‮", title)
        self.assertIsNone(LIVE_MENTION.search(title))


class FuzzTest(unittest.TestCase):
    """무작위로 섞은 위험한 조각을 제목·본문·라벨·출처·이미지·게이트 설명에 넣어도 불변식이 지켜지는지(고정 시드, 재현 가능)."""

    PIECES = ["@octocat", "@org/team", "#12", "GH-7", "owner/repo#3", "```", "````", "~~~", "<script>x</script>", "<!--", "-->", "<iframe>", "\n", "\r\n", " ",
              "|", "$", "&#64;octocat", "&lt;b&gt;", "[x](javascript:alert(1))", "![i](https://e.example/i.png)", "# 제목", "- [ ] 체크", "---", "***", "> 인용",
              "https://evil.example/@u#1", "help@example.com", "`", "\\", "한글 문장입니다.", "plain text", "‮", "\x07", "<b>굵게</b>", "<h3>소제목</h3>",
              "<ul><li>항목</li></ul>", "draft-id: x", "<p>단락</p>"]

    def test_invariants_hold_for_random_input(self):
        rng = random.Random(20261027)
        for round_number in range(120):
            def mix(count):
                return "".join(rng.choice(self.PIECES) + rng.choice([" ", "", "\n"]) for _ in range(count))
            platform = "tistory" if round_number % 2 == 0 else "naver"
            draft = make_draft(platform, title=mix(4) or "x", html=mix(25) or "<p>x</p>", tags=[mix(2), mix(1)],
                               sources=[{"title": mix(3), "url": "https://ok.example/a"}],
                               images=[{"purpose": mix(2), "url": "https://ok.example/i.png", "source": mix(1), "license": mix(1), "author": mix(1)}],
                               gate={"attempts": 1, "model": mix(2), "warnings": [mix(3)], "removed": {mix(1): 2}})
            try:
                spec = ip.build_issue(draft)
            except PublishError as exc:
                self.assertIn(exc.code, ("bad_response", "too_long"), (round_number, exc))     # 비었거나(정화 뒤) 너무 긴 것만 거절한다
                continue
            body = spec.body
            self.assertEqual(body.split("\n", 1)[0], f"<!-- draft-id: {spec.draft_id} -->", round_number)
            self.assertEqual(body.count("<!--"), 1, round_number)
            self.assertLessEqual(len(body), ip.BODY_BUDGET, round_number)
            self.assertTrue(spec.title.startswith(f"[초안][{LABELS[platform]}] "), round_number)
            self.assertLessEqual(len(spec.title), len(f"[초안][{LABELS[platform]}] ") + ip.TITLE_SHOWN, round_number)
            self.assertNotRegex(spec.title, "[\n\r ‮\x07]", round_number)
            self.assertIsNone(LIVE_MENTION.search(without_urls(body)), (round_number, LIVE_MENTION.search(without_urls(body))))
            self.assertIsNone(LIVE_REF.search(without_urls(body)), (round_number, LIVE_REF.search(without_urls(body))))
            blocks, outside = fenced_blocks(body)
            self.assertNotIn("```", outside, round_number)                  # 닫히지 않은·빠져나온 상자가 없다
            self.assertEqual(len(blocks), 2 if "글에 라벨이 없습니다" in body else 3, round_number)   # 제목·본문(또는 평문)·태그 상자
            if platform == "tistory":
                parser = TagCollector()
                parser.feed([content for info, content in blocks if info == "html"][0])
                self.assertLessEqual(set(parser.tags), {"p", "h2", "h3", "h4", "ul", "ol", "li", "strong", "b", "em", "i", "br", "blockquote"}, round_number)
                self.assertEqual(parser.attrs, [], round_number)
            else:
                rendered = body.split("\n---\n")[1]
                self.assertIsNone(re.search(r"(?<!\\)<[A-Za-z!/]", rendered), (round_number, rendered))      # 이스케이프하지 않은 HTML 시작이 없다


class SizeTest(unittest.TestCase):
    @staticmethod
    def big_html(chars):
        return "".join(f"<p>{'가' * 990}{i}</p>" for i in range(chars // 1000))

    def test_a_long_post_that_fits_keeps_every_section(self):
        for platform in ("tistory",):
            spec = ip.build_issue(make_draft(platform, html=self.big_html(20000)))
            self.assertLessEqual(len(spec.body), ip.BODY_BUDGET)
            self.assertIn("## 6. 게이트 점검 결과", spec.body)

    def test_naver_drops_the_plain_text_box_first_when_both_copies_do_not_fit(self):
        spec = ip.build_issue(make_draft("naver", html=self.big_html(40000)))
        self.assertLessEqual(len(spec.body), ip.BODY_BUDGET)
        self.assertIn("평문 상자를 생략했습니다", spec.body)
        self.assertIn("가" * 900, spec.body)                       # 서식 있는 글은 그대로다
        self.assertEqual([info for info, _ in fenced_blocks(spec.body)[0]], ["text", "text"])   # 제목·태그

    def test_tistory_drops_images_sources_and_gate_details_before_giving_up(self):
        images = [{"purpose": "p" * 100, "url": f"https://ok.example/{'a' * 400}{i}.png", "source": "s" * 100, "license": "l" * 100} for i in range(12)]
        sources = [{"title": "t" * 200, "url": f"https://ok.example/{'b' * 400}{i}"} for i in range(12)]
        spec = ip.build_issue(make_draft("tistory", html=self.big_html(51000), images=images, sources=sources))
        self.assertLessEqual(len(spec.body), ip.BODY_BUDGET)
        self.assertIn("이미지 표는 이슈 본문 한도 때문에 생략했습니다", spec.body)
        self.assertIn("출처 목록은 이슈 본문 한도 때문에 생략했습니다", spec.body)
        self.assertIn("가" * 900, spec.body)
        full = ip.build_issue(make_draft("tistory", html=self.big_html(51000)))
        self.assertNotIn("생략했습니다", full.body)                  # 줄이지 않아도 되면 줄이지 않는다

    def test_a_post_that_cannot_fit_fails_instead_of_being_cut(self):
        for platform in ("tistory", "naver"):
            with self.assertRaises(PublishError) as caught:
                ip.build_issue(make_draft(platform, html=self.big_html(80000)))
            self.assertEqual(caught.exception.code, "too_long")
            self.assertIn("length.max_chars", str(caught.exception))
            self.assertIn("만들지 않습니다", str(caught.exception))

    def test_the_title_box_is_capped(self):
        spec = ip.build_issue(make_draft(title="가" * 5000))
        self.assertEqual(fenced_blocks(spec.body)[0][0][1], "가" * ip.COPY_TITLE_MAX)


# ----------------------------------------------------------------------------
# 4) GitHub REST
# ----------------------------------------------------------------------------
def publisher(github=None, **kw):
    github = github or FakeGitHub()
    sleeps = []
    pub = ip.IssuePackagePublisher(kw.pop("repo", REPO), kw.pop("token", fake_token()), opener=github, sleep=sleeps.append, **kw)
    return pub, github, sleeps


class CreateIssueTest(unittest.TestCase):
    def test_creates_one_issue_with_the_fixed_title_body_and_labels(self):
        pub, github, _ = publisher()
        result = pub.publish_package(make_draft())
        spec = ip.build_issue(make_draft())
        self.assertEqual((result.post_id, result.url, result.draft), ("1", f"https://github.com/{REPO}/issues/1", True))
        created = github.calls("POST", r"^/issues$")
        self.assertEqual(len(created), 1)
        self.assertEqual(created[0]["payload"], {"title": spec.title, "body": spec.body, "labels": ["초안", "채널:티스토리"]})
        self.assertEqual(set(created[0]["payload"]), {"title", "body", "labels"})            # 담당자·마일스톤 같은 것을 정하지 않는다

    def test_call_sequence_is_search_then_labels_then_create(self):
        pub, github, _ = publisher()
        pub.publish_package(make_draft())
        self.assertEqual([r["method"] + " " + r["path"] for r in github.requests],
                         ["GET /issues", "GET /labels/초안", "POST /labels", "GET /labels/채널:티스토리", "POST /labels", "POST /issues"])

    def test_requests_carry_the_token_only_in_the_authorization_header(self):
        token = fake_token()
        pub, github, _ = publisher(token=token)
        pub.publish_package(make_draft())
        for request in github.requests:
            self.assertEqual(request["headers"]["authorization"], f"Bearer {token}")
            self.assertNotIn(token, request["url"])
            self.assertNotIn(token, json.dumps(request["payload"] or {}))
            self.assertTrue(request["url"].startswith(f"https://api.github.com/repos/{REPO}/"))

    def test_labels_are_created_with_fixed_colors_only_when_missing(self):
        pub, github, _ = publisher()
        pub.publish_package(make_draft())
        self.assertEqual(github.labels["초안"]["color"], "fbca04")
        self.assertEqual(github.labels["채널:티스토리"]["color"], "ff6a3d")
        self.assertEqual(github.labels["채널:티스토리"]["description"], "티스토리에 올릴 초안 패키지")
        github.requests.clear()
        pub.publish_package(make_draft(date="2026-10-22"))
        self.assertEqual(github.calls("POST", r"^/labels$"), [])                         # 이미 있으면 만들지 않는다

    def test_naver_uses_its_own_channel_label(self):
        pub, github, _ = publisher()
        pub.publish_package(make_draft("naver"))
        self.assertEqual(github.issues[0]["labels"], [{"name": "초안"}, {"name": "채널:네이버"}])
        self.assertEqual(github.labels["채널:네이버"]["color"], "03c75a")

    def test_a_label_creation_race_422_is_fine_but_other_errors_stop_before_the_issue(self):
        pub, github, _ = publisher()
        github.fail_next("POST", r"^/labels$", http_error(422, "already_exists"))
        pub.publish_package(make_draft())
        self.assertEqual(len(github.issues), 1)
        pub, github, _ = publisher()
        github.fail_next("POST", r"^/labels$", http_error(403, "Resource not accessible by integration"), times=None)
        with self.assertRaises(PublishError) as caught:
            pub.publish_package(make_draft())
        self.assertEqual(caught.exception.code, "auth_failed")
        self.assertEqual(github.issues, [])

    def test_too_long_fails_before_any_http_call(self):
        pub, github, _ = publisher()
        with self.assertRaises(PublishError) as caught:
            pub.publish_package(make_draft(html="".join(f"<p>{'가' * 990}{i}</p>" for i in range(80))))
        self.assertEqual(caught.exception.code, "too_long")
        self.assertEqual(github.requests, [])


class IdempotencyTest(unittest.TestCase):
    def test_the_same_draft_twice_makes_one_issue_and_returns_the_same_one(self):
        pub, github, _ = publisher()
        first = pub.publish_package(make_draft())
        pub2, _, _ = publisher(github)
        second = pub2.publish_package(make_draft())
        self.assertEqual((first.post_id, first.url), (second.post_id, second.url))
        self.assertEqual(len(github.issues), 1)
        self.assertEqual(len(github.calls("POST", r"^/issues$")), 1)
        self.assertIn("이미 있어 새로 만들지 않았습니다", pub2.notes[0])
        self.assertIn("#1", pub2.notes[0])

    def test_a_closed_issue_with_the_same_marker_still_blocks_a_duplicate(self):
        pub, github, _ = publisher()
        pub.publish_package(make_draft())
        github.issues[0]["state"] = "closed"                   # 운영자가 발행하고 닫았다
        again = pub.publish_package(make_draft())
        self.assertEqual(again.post_id, "1")
        self.assertEqual(len(github.issues), 1)

    def test_a_different_draft_makes_a_new_issue(self):
        pub, github, _ = publisher()
        pub.publish_package(make_draft())
        pub.publish_package(make_draft(title="다른 글 제목입니다"))
        self.assertEqual(len(github.issues), 2)

    def test_the_marker_must_be_on_the_first_line_not_somewhere_in_the_body(self):
        spec = ip.build_issue(make_draft())
        github = FakeGitHub()
        github.add_issue(labels=spec.labels, body="잡담\n" + spec.body)                              # 첫 줄이 아니다
        github.add_issue(labels=spec.labels, body=f"본문 속 <!-- draft-id: {spec.draft_id} --> 인용")
        pub, _, _ = publisher(github)
        pub.publish_package(make_draft())
        self.assertEqual(len(github.issues), 3)

    def test_the_marker_must_be_exactly_this_draft(self):
        spec = ip.build_issue(make_draft())
        github = FakeGitHub()
        github.add_issue(labels=spec.labels, body=spec.body.replace(spec.draft_id, spec.draft_id[:-1] + "0"))
        github.add_issue(labels=spec.labels, body=spec.body.replace(spec.draft_id, spec.draft_id + "0"))
        pub, _, _ = publisher(github)
        pub.publish_package(make_draft())
        self.assertEqual(len(github.issues), 3)

    def test_pull_requests_and_other_channels_do_not_count_as_the_same_draft(self):
        spec = ip.build_issue(make_draft())
        github = FakeGitHub()
        github.add_issue(labels=spec.labels, body=spec.body, pull_request=True)
        github.add_issue(labels=["초안", "채널:네이버"], body=spec.body)
        github.add_issue(labels=["초안"], body=spec.body)
        pub, _, _ = publisher(github)
        pub.publish_package(make_draft())
        self.assertEqual(len(github.issues), 4)

    def test_the_search_window_starts_the_day_before_in_kst_and_asks_for_all_states(self):
        pub, github, _ = publisher()
        pub.publish_package(make_draft(date="2026-10-21"))
        search = github.calls("GET", r"^/issues$")[0]["query"]
        self.assertEqual(search["state"], "all")
        self.assertEqual(search["labels"], "초안,채널:티스토리")
        self.assertEqual(search["since"], "2026-10-19T15:00:00Z")                 # 2026-10-20 00:00 KST
        self.assertEqual((search["per_page"], search["sort"], search["direction"]), ("100", "created", "desc"))

    def test_old_issues_outside_the_window_are_not_looked_at(self):
        spec = ip.build_issue(make_draft())
        github = FakeGitHub()
        old = github.add_issue(labels=spec.labels, body=spec.body)
        old["updated_at"] = "2026-10-01T00:00:00Z"
        pub, _, _ = publisher(github)
        pub.publish_package(make_draft())
        self.assertEqual(len(github.issues), 2)

    def test_a_timeout_after_the_server_created_the_issue_does_not_make_a_second_one(self):
        github = FakeGitHub()

        def lost_response(record):
            github._route(record)                                   # 서버는 만들었다
            return OSError("timed out")                            # 응답만 잃었다
        github.fail_next("POST", r"^/issues$", lost_response)
        pub, _, sleeps = publisher(github)
        result = pub.publish_package(make_draft())
        self.assertEqual(result.post_id, "1")
        self.assertEqual(len(github.issues), 1)                      # 같은 요청을 그대로 다시 보내지 않고 표지로 찾아 쓴다
        self.assertEqual(len(github.calls("POST", r"^/issues$")), 1)
        self.assertEqual(sleeps, [])
        self.assertIn("이미 만들어져 있어 그것을 씁니다", pub.notes[-1])

    def test_a_server_error_after_creation_is_also_checked_before_retrying(self):
        github = FakeGitHub()

        def created_then_502(record):
            github._route(record)
            return http_error(502, "Bad Gateway")
        github.fail_next("POST", r"^/issues$", created_then_502, times=None)
        pub, _, _ = publisher(github)
        self.assertEqual(pub.publish_package(make_draft()).post_id, "1")
        self.assertEqual(len(github.issues), 1)
        self.assertEqual(len(github.calls("POST", r"^/issues$")), 1)     # 이슈 만들기 요청은 호출 안에서 자동 재시도하지 않는다

    def test_a_response_without_number_or_url_is_not_retried_and_the_marker_is_checked(self):
        github = FakeGitHub()

        def created_but_empty(record):
            github._route(record)
            return FakeResponse({"id": 1})
        github.fail_next("POST", r"^/issues$", created_but_empty, times=None)
        pub, _, sleeps = publisher(github)
        self.assertEqual(pub.publish_package(make_draft()).post_id, "1")            # 표지로 찾아 쓴다
        self.assertEqual(len(github.issues), 1)
        github = FakeGitHub()
        github.fail_next("POST", r"^/issues$", FakeResponse({"id": 1}), times=None)   # 정말 만들어지지 않은 경우
        pub, _, sleeps = publisher(github)
        with self.assertRaises(PublishError) as caught:
            pub.publish_package(make_draft())
        self.assertEqual(caught.exception.code, "bad_response")
        self.assertEqual(len(github.calls("POST", r"^/issues$")), 1)               # 응답이 이상하면 다시 만들지 않는다
        self.assertEqual(sleeps, [])


class FailureTest(unittest.TestCase):
    def failing(self, method, pattern, error, times=None, **kw):
        github = FakeGitHub()
        github.fail_next(method, pattern, error, times=times)
        pub, _, sleeps = publisher(github, **kw)
        return pub, github, sleeps

    def code_of(self, pub, action=None):
        with self.assertRaises(PublishError) as caught:
            (action or (lambda: pub.publish_package(make_draft())))()
        return caught.exception.code, str(caught.exception)

    def test_permission_and_access_errors_are_auth_failed_and_not_retried(self):
        for status in (401, 403, 404, 410):
            pub, github, sleeps = self.failing("GET", r"^/issues$", http_error(status, "Resource not accessible by integration"))
            code, _ = self.code_of(pub)
            self.assertEqual(code, "auth_failed", status)
            self.assertEqual(len(github.calls()), 1, status)
            self.assertEqual(sleeps, [], status)

    def test_rate_limits_and_server_errors_are_retried_with_backoff_then_api_error(self):
        for status in (429, 500, 502, 503, 504):
            pub, github, sleeps = self.failing("GET", r"^/issues$", http_error(status, "boom"))
            code, _ = self.code_of(pub)
            self.assertEqual(code, "api_error", status)
            self.assertEqual(len(github.calls()), 3, status)
            self.assertEqual(sleeps, [3, 6], status)

    def test_a_forbidden_rate_limit_is_api_error_not_a_permission_error(self):
        for error in (http_error(403, "API rate limit exceeded for user", {"x-ratelimit-remaining": "0"}),
                      http_error(403, "You have exceeded a secondary rate limit")):
            pub, _, _ = self.failing("GET", r"^/issues$", error)
            self.assertEqual(self.code_of(pub)[0], "api_error")

    def test_a_transient_error_that_clears_is_just_retried(self):
        pub, github, sleeps = self.failing("GET", r"^/issues$", http_error(503, "later"), times=2)
        self.assertEqual(pub.publish_package(make_draft()).post_id, "1")
        self.assertEqual(sleeps, [3, 6])

    def test_validation_errors_are_api_error(self):
        pub, _, _ = self.failing("POST", r"^/issues$", http_error(422, "Validation Failed"))
        self.assertEqual(self.code_of(pub)[0], "api_error")

    def test_connection_failures_are_network_errors_after_retries(self):
        for error in (OSError("connection reset"), TimeoutError("timed out"), urllib.error.URLError("dns"), http.client.RemoteDisconnected("closed")):
            pub, github, sleeps = self.failing("GET", r"^/issues$", error)
            self.assertEqual(self.code_of(pub)[0], "network", repr(error))
            self.assertEqual(sleeps, [3, 6], repr(error))

    def test_bad_json_and_non_list_responses_are_bad_response(self):
        pub, _, _ = self.failing("GET", r"^/issues$", FakeResponse(b"<html>nope</html>"))
        self.assertEqual(self.code_of(pub)[0], "bad_response")
        pub, _, _ = self.failing("GET", r"^/issues$", FakeResponse({"message": "x"}))
        self.assertEqual(self.code_of(pub)[0], "bad_response")
        pub, _, _ = self.failing("POST", r"^/issues$", FakeResponse({"number": 0, "html_url": "https://github.com/o/r/issues/0"}))
        self.assertEqual(self.code_of(pub)[0], "bad_response")
        pub, _, _ = self.failing("POST", r"^/issues$", FakeResponse({"number": 5, "html_url": "https://evil.example/o/r/issues/5"}))
        self.assertEqual(self.code_of(pub)[0], "bad_response")
        pub, _, _ = self.failing("POST", r"^/issues$", FakeResponse({"number": True, "html_url": "https://github.com/o/r/issues/1"}))
        self.assertEqual(self.code_of(pub)[0], "bad_response")

    def test_a_network_failure_on_create_retries_the_create_only_after_checking_for_a_duplicate(self):
        pub, github, sleeps = self.failing("POST", r"^/issues$", OSError("reset"), times=None)
        self.assertEqual(self.code_of(pub)[0], "network")
        self.assertEqual(len(github.calls("POST", r"^/issues$")), 3)               # 만들기는 모두 3번(처음 + 재시도 2번), 한 번에 한 요청씩
        self.assertEqual(len(github.calls("GET", r"^/issues$")), 4)                # 처음 찾기 1번 + 실패할 때마다 같은 표지가 있는지 3번
        self.assertEqual(sleeps, [3, 6])
        self.assertEqual(github.issues, [])

    def test_error_text_never_contains_the_token(self):
        token = fake_token()
        for error in (http_error(401, f"Bad credentials {token}"), http_error(500, f"Server said {token}"), OSError(f"failed with {token}")):
            github = FakeGitHub()
            github.fail_next("GET", r"^/issues$", error, times=None)
            pub, _, _ = publisher(github, token=token)
            _, text = self.code_of(pub)
            self.assertNotIn(token, text)
            self.assertNotIn(token, " ".join(pub.notes))

    def test_a_bad_repository_name_stops_before_any_call(self):
        for repo in ("", "no-slash", "a/b/c", "a b/c", "../x", "owner/repo?x=1", "owner/repo#1"):
            github = FakeGitHub()
            pub, _, _ = publisher(github, repo=repo)
            self.assertEqual(self.code_of(pub, lambda p=pub: p.count_open_drafts("티스토리"))[0], "auth_failed", repo)
            self.assertEqual(github.requests, [], repo)

    def test_the_fake_server_really_sees_the_percent_encoded_label_names(self):
        pub, github, _ = publisher()
        pub.publish_package(make_draft())
        raw_urls = [r["url"] for r in github.requests if "/labels/" in r["url"]]
        self.assertTrue(all("%" in url and "초안" not in url for url in raw_urls))


class BacklogTest(unittest.TestCase):
    def test_counts_only_open_issues_with_both_labels_and_no_pull_requests(self):
        github = FakeGitHub()
        github.add_issue(labels=["초안", "채널:티스토리"])
        github.add_issue(labels=["초안", "채널:티스토리"], state="closed")
        github.add_issue(labels=["초안", "채널:네이버"])
        github.add_issue(labels=["초안"])
        github.add_issue(labels=["채널:티스토리"])
        github.add_issue(labels=["초안", "채널:티스토리"], pull_request=True)
        github.add_issue(labels=["초안", "채널:티스토리", "폐기"])
        pub, _, _ = publisher(github)
        self.assertEqual(pub.count_open_drafts("티스토리"), 2)
        self.assertEqual(pub.count_open_drafts("네이버"), 1)
        self.assertEqual(pub.count_open_drafts("Chance"), 0)

    def test_pages_of_one_hundred_are_followed_up_to_the_limit_of_three_pages(self):
        github = FakeGitHub()
        for _ in range(250):
            github.add_issue(labels=["초안", "채널:티스토리"])
        pub, _, _ = publisher(github)
        self.assertEqual(pub.count_open_drafts("티스토리"), 250)
        self.assertEqual(len(github.calls("GET", r"^/issues$")), 3)
        for _ in range(100):
            github.add_issue(labels=["초안", "채널:티스토리"])
        self.assertEqual(pub.count_open_drafts("티스토리"), 300)                        # 4쪽부터는 읽지 않는다(상한 3건을 넘으면 충분하다)

    def test_the_limit_is_three(self):
        self.assertEqual(ip.OPEN_DRAFT_LIMIT, 3)


class SourceShapeTest(unittest.TestCase):
    def test_the_adapter_uses_only_the_standard_library_and_the_gates(self):
        text = (_bootstrap.ROOT / "pipeline" / "publishers" / "issue_package.py").read_text(encoding="utf-8")
        imported = set(re.findall(r"^(?:from|import) ([\w.]+)", text, re.M))
        allowed_std = {"hashlib", "http.client", "json", "re", "time", "unicodedata", "urllib.error", "urllib.parse", "urllib.request", "dataclasses", "datetime",
                       "html.parser"}
        self.assertLessEqual(imported, allowed_std | {"pipeline", "pipeline.publishers.base", "pipeline.state"})

    def test_there_is_no_shell_or_subprocess_in_the_adapter(self):
        text = (_bootstrap.ROOT / "pipeline" / "publishers" / "issue_package.py").read_text(encoding="utf-8")
        for word in ("subprocess", "os.system", "shell=True", "eval(", "exec("):
            self.assertNotIn(word, text)

    def test_the_adapter_never_reads_or_writes_account_information(self):
        text = (_bootstrap.ROOT / "pipeline" / "publishers" / "issue_package.py").read_text(encoding="utf-8")
        code = "\n".join(line.split("#", 1)[0] for line in text.splitlines())
        for word in ("password", "cookie", "session", "login", "refresh_token", "client_secret"):
            self.assertNotIn(word, code.lower())


if __name__ == "__main__":
    unittest.main()
