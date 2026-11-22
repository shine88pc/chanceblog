"""글 페이지 레이아웃(`_layouts/post.html`)의 두 가지 손보기를 못박는다(확인 015 항목 1, F103 글 표·F099 글 사진).

① F103 글 표 — 글 카드 배경(어두운 남색) 위에서 테마(minima)의 기본 표 색(옅은 회색 글자·거의 흰 짝수 줄)이 그대로 먹으면 줄마다 보였다 안 보였다 하고,
   표를 감싸는 요소가 없어 휴대폰에서 표가 페이지를 옆으로 넓혔다. 그래서 `<style>` 에 표 규칙을 더했고, 이 시험은 규칙을 읽어
   '글자와 바탕의 대비가 모든 칸에서 4.5 이상' 임을 계산으로 보고(안 보이는 줄이 없다), 표가 자기 안에서 가로로 스크롤되고, 규칙이 테마의 표 선택자보다 세게 먹는지 본다.
② F099 글 사진 — 본문 사진이 `loading="lazy"` 없이 글을 열자마자 모두 내려받아졌다. 본문 출력이 `content` 를 바로 찍지 않고
   `assign post_body = content | replace: …` 를 거치게 했고, 이 시험은 레이아웃에 적힌 필터 사슬을 읽어 표본 글에 직접 돌려
   (모든 사진에 lazy 가 붙고 · 그 밖은 한 글자도 안 바뀌고 · 코드 글자 속의 이스케이프된 `<img` 는 그대로) 보인다.
이 PC 에도 CI 에도 Jekyll 이 없어서 실제 렌더는 못 한다 — 규칙과 사슬을 읽는 정적 시험이고, 실제 화면은 병합 전 임시 가지 빌드와 병합 뒤 점검으로 본다.
`_layouts/` 는 광고 표면 경로라 이 파일은 안전 장치 낱말을 이름에 넣지 않았고, 기존 시험(`test_site_cleanup`·`test_fact_docs`)은 고치지 않았다.
"""
import re
import unittest
from pathlib import Path

import _bootstrap

ROOT = Path(_bootstrap.ROOT)
SCOPE = ".chance-post .post-content"
MIN_CONTRAST = 4.5


def layout():
    return (ROOT / "_layouts" / "post.html").read_text(encoding="utf-8").replace("\r\n", "\n")


# ---------------------------------------------------------------- CSS 읽기
def css_rules():
    """`<style>` 안의 '선택자 { 선언 }' 규칙을 (선택자 목록, {속성: 값}) 으로 읽는다. 미디어 쿼리 안의 규칙도 안쪽 규칙으로 읽힌다."""
    blocks = re.findall(r"<style>(.*?)</style>", layout(), re.S)
    assert len(blocks) == 1, "post.html 에 <style> 블록이 하나여야 한다"
    rules = []
    for selector_text, body in re.findall(r"([^{}]+)\{([^{}]*)\}", blocks[0]):
        declarations = {}
        for part in body.split(";"):
            if ":" in part:
                name, value = part.split(":", 1)
                declarations[name.strip().lower()] = value.strip()
        rules.append(([s.strip() for s in selector_text.split(",") if s.strip()], declarations))
    return rules


def declared(selector, prop):
    """그 선택자가 선언한 속성의 값(뒤의 규칙이 이긴다). 없으면 None."""
    value = None
    for selectors, declarations in css_rules():
        if selector in selectors and prop in declarations:
            value = declarations[prop]
    return value


def hex_color(selector, prop):
    value = declared(selector, prop)
    assert value is not None, f"{selector} 에 {prop} 가 없다"
    assert re.fullmatch(r"#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})", value), f"{selector} 의 {prop} 가 단색 16진수가 아니다: {value}"
    return value


def _channel(value):
    c = value / 255
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def luminance(color):
    text = color.lstrip("#")
    if len(text) == 3:
        text = "".join(ch * 2 for ch in text)
    r, g, b = (int(text[i:i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)


def contrast(first, second):
    high, low = sorted((luminance(first), luminance(second)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def specificity(selector):
    """(아이디, 클래스·속성·가상 클래스, 요소) 개수. 이 시험의 선택자는 단순해서 이 정도 읽기로 충분하다."""
    ids = len(re.findall(r"#[\w-]+", selector))
    classes = len(re.findall(r"\.[\w-]+|\[[^\]]*\]|(?<!:):[\w-]+(?:\([^)]*\))?", selector))
    elements = len(re.findall(r"(?:^|[\s>+])[a-zA-Z][\w-]*", selector))
    return ids, classes, elements


TABLE = f"{SCOPE} table"
CELLS = [f"{SCOPE} th", f"{SCOPE} td"]
HEAD_CELL = f"{SCOPE} th"
EVEN_ROW = f"{SCOPE} tr:nth-child(even)"
CARD = ".chance-post"
LINK = ".chance-post a"


class TableStyleTest(unittest.TestCase):
    def test_the_table_rules_exist_and_stay_inside_the_post_body(self):
        selectors = [s for group, _ in css_rules() for s in group if re.search(r"\b(table|th|td|tr)\b", s)]
        self.assertGreaterEqual(len(selectors), 5, selectors)                       # table · th · td · th(머리 칸 색) · 짝수 줄
        for selector in selectors:
            with self.subTest(selector=selector):
                self.assertTrue(selector.startswith(SCOPE + " "), "표 규칙은 글 본문 안(.chance-post .post-content)으로 한정한다 — 다른 쪽 표에 번지지 않게")
        for needed in (TABLE, CELLS[0], CELLS[1], HEAD_CELL, EVEN_ROW):
            self.assertIn(needed, selectors)

    def test_every_text_and_background_pair_inside_a_table_reads_at_four_and_a_half_or_more(self):
        """'일부 줄이 안 보인다' 를 의미로 못박는다: 칸 글자색과 그 칸의 바탕(카드·짝수 줄·머리 칸)의 대비, 링크 색과 같은 바탕들의 대비."""
        card = hex_color(CARD, "background")
        even = hex_color(EVEN_ROW, "background")
        head_bg = hex_color(HEAD_CELL, "background")
        body_text = hex_color(TABLE, "color")
        head_text = hex_color(HEAD_CELL, "color")
        link = hex_color(LINK, "color")
        for selector in CELLS:                                                       # 칸이 따로 글자색을 덮어쓰면 아래 계산이 틀리므로 막는다(머리 칸 th 는 아래에서 따로 잰다)
            if selector != HEAD_CELL:
                self.assertIsNone(declared(selector, "color"), f"{selector} 가 글자색을 따로 정하면 이 시험의 계산을 고쳐야 한다")
        pairs = {
            "본문 글자 / 카드(홀수 줄)": (body_text, card),
            "본문 글자 / 짝수 줄": (body_text, even),
            "머리 칸 글자 / 머리 칸 바탕": (head_text, head_bg),
            "링크 / 카드(홀수 줄)": (link, card),
            "링크 / 짝수 줄": (link, even),
            "링크 / 머리 칸 바탕": (link, head_bg),
        }
        for name, (foreground, background) in pairs.items():
            with self.subTest(pair=name, foreground=foreground, background=background):
                self.assertGreaterEqual(contrast(foreground, background), MIN_CONTRAST)

    def test_the_theme_default_colors_would_fail_the_same_check(self):
        """계산기 자체 점검 — 고치기 전에 먹던 테마 기본 색(글자 #3f3f3f 쯤)은 이 카드 위에서 4.5 에 못 미치고, 같은 계산이 새 색은 통과시킨다."""
        card = hex_color(CARD, "background")
        self.assertLess(contrast("#3f3f3f", card), 2.0)
        self.assertGreater(contrast(hex_color(TABLE, "color"), card), 10.0)
        self.assertAlmostEqual(contrast("#000000", "#ffffff"), 21.0, places=6)
        self.assertAlmostEqual(contrast("#ffffff", "#ffffff"), 1.0, places=6)

    def test_a_wide_table_scrolls_inside_itself_instead_of_widening_the_page(self):
        self.assertEqual(declared(TABLE, "display"), "block")
        self.assertEqual(declared(TABLE, "overflow-x"), "auto")
        self.assertEqual(declared(TABLE, "max-width"), "100%")

    def test_the_table_has_no_frame_of_its_own_so_the_theme_light_border_cannot_show(self):
        """테마(minima)의 표는 옅은 회색 테두리를 가진다 — 표가 block 이 되면 그 테두리가 어두운 카드 위에 옅은 틀로 보이므로 표 자신의 테두리는 없애고 칸 테두리만 쓴다."""
        self.assertIn(declared(TABLE, "border"), ("0", "none", "0 none"))
        for selector in CELLS:
            self.assertRegex(declared(selector, "border") or "", r"^1px solid #[0-9a-fA-F]{3,6}$")

    def test_even_rows_get_their_own_background_that_differs_from_the_card(self):
        self.assertNotEqual(hex_color(EVEN_ROW, "background").lower(), hex_color(CARD, "background").lower())
        self.assertNotEqual(hex_color(HEAD_CELL, "background").lower(), hex_color(CARD, "background").lower())

    def test_each_table_selector_beats_the_theme_selector_it_replaces(self):
        """테마(minima)의 표 선택자는 table · table tr:nth-child(even) · table th · table td(기억으로 적은 값 — 이 PC 에 테마가 없다).
        우리 규칙이 글 안의 위치(순서)와 상관없이 이기려면 레이아웃 파일에 실제로 적힌 선택자의 명시도가 그보다 커야 한다."""
        theme = {"table": "table", "tr:nth-child(even)": "table tr:nth-child(even)", "th": "table th", "td": "table td"}
        self.assertEqual(specificity("table tr:nth-child(even)"), (0, 1, 2))      # 계산기 자체 점검
        self.assertEqual(specificity(EVEN_ROW), (0, 3, 1))
        written = [selector for group, _ in css_rules() for selector in group]
        for ending, theirs in theme.items():
            ours = [selector for selector in written if selector.endswith(" " + ending)]
            with self.subTest(ending=ending):
                self.assertTrue(ours, f"레이아웃에 {ending} 로 끝나는 표 규칙이 없다")
                for selector in ours:
                    self.assertGreater(specificity(selector), specificity(theirs), selector)

    def test_specificity_helper_reads_simple_selectors(self):
        self.assertEqual(specificity(".a .b c"), (0, 2, 1))
        self.assertEqual(specificity("#x .y:hover z"), (1, 2, 1))
        self.assertEqual(specificity("a"), (0, 0, 1))

    def test_other_rules_of_the_layout_are_still_there(self):
        """표 규칙을 더하다 옆 규칙을 지우는 사고를 막는 최소 점검 — 카드 배경·링크 색·사진 규칙·코드 블록·미디어 쿼리."""
        self.assertEqual(declared(CARD, "background"), "#0f172a")
        self.assertEqual(declared(LINK, "color"), "#60a5fa")
        self.assertEqual(declared(".chance-post img", "max-width"), "100%")
        self.assertEqual(declared(".chance-post pre", "overflow-x"), "auto")
        self.assertEqual(declared(".site-title", "font-size"), "1.1rem")


# ---------------------------------------------------------------- Liquid 사슬 읽기
ASSIGN_RE = re.compile(r"\{%-?\s*assign\s+post_body\s*=\s*content\s*((?:\|[^%]*?)?)\s*-?%\}")
OUTPUT_RE = re.compile(r"\{\{-?\s*post_body\s*-?\}\}")
CONTENT_OUTPUT_RE = re.compile(r"\{\{-?\s*content\s*(?:\|[^}]*)?-?\}\}")
POST_CONTENT_OPEN = '<div class="post-content">'


def split_outside_quotes(text, separator):
    parts, current, quote = [], [], None
    for ch in text:
        if quote:
            current.append(ch)
            if ch == quote:
                quote = None
        elif ch in "'\"":
            quote = ch
            current.append(ch)
        elif ch == separator:
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
    parts.append("".join(current))
    return parts


def parse_filters(chain):
    """`| replace: 'a', 'b' | replace_first: 'c', 'd'` → [("replace", ["a", "b"]), ("replace_first", ["c", "d"])]. 따옴표 문자열 인자만 읽는다."""
    filters = []
    for segment in split_outside_quotes(chain, "|"):
        segment = segment.strip()
        if not segment:
            continue
        name, _, argument_text = segment.partition(":")
        arguments = []
        for raw in split_outside_quotes(argument_text, ","):
            raw = raw.strip()
            if not raw:
                continue
            if len(raw) < 2 or raw[0] not in "'\"" or raw[-1] != raw[0]:
                raise AssertionError(f"이 시험은 따옴표 문자열 인자만 읽는다: {raw}")
            arguments.append(raw[1:-1])
        filters.append((name.strip(), arguments))
    return filters


def run_filters(filters, text):
    for name, arguments in filters:
        if name == "replace" and len(arguments) == 2:
            text = text.replace(arguments[0], arguments[1])
        elif name == "replace_first" and len(arguments) == 2:
            text = text.replace(arguments[0], arguments[1], 1)
        else:
            raise AssertionError(f"이 시험이 계산하지 못하는 필터: {name} {arguments} — 사슬을 바꿨다면 이 시험의 계산기도 맞춰야 한다")
    return text


def body_filters():
    found = ASSIGN_RE.findall(layout())
    assert len(found) == 1, f"post_body 를 정하는 줄이 정확히 하나여야 한다(지금 {len(found)}개)"
    return parse_filters(found[0])


SAMPLE = "\n".join([
    "<p>소개 문단</p>",
    '<p><img src="https://img.example/a.jpg?auto=format&amp;fit=crop" alt="A &amp; B" /></p>',
    "<pre><code>&lt;img src=&quot;x.png&quot;&gt; 와 &lt;img alt=&quot;y&quot;&gt; 는 글자로 보이는 코드다</code></pre>",
    '<p>속성 순서가 다른 사진 <img alt="C" src="c.png" title="t"> 도 있다</p>',
    '<table><thead><tr><th>머리</th></tr></thead><tbody><tr><td>칸</td></tr></tbody></table>',
    "<p>끝 <em>강조</em></p>",
])


class LazyPhotoTest(unittest.TestCase):
    def test_the_body_goes_through_post_body_and_content_is_never_printed_directly(self):
        text = layout()
        self.assertEqual(CONTENT_OUTPUT_RE.findall(text), [], "본문을 content 로 바로 찍으면 lazy 사슬을 우회한다")
        self.assertEqual(len(OUTPUT_RE.findall(text)), 1)
        start = text.index(POST_CONTENT_OPEN)
        block = text[start:text.index("</div>", start)]
        self.assertEqual(len(OUTPUT_RE.findall(block)), 1, "post_body 출력은 글 본문 칸(post-content) 안에 있어야 한다")

    def test_post_body_is_assigned_before_it_is_printed(self):
        """정하기 전에 찍으면 post_body 가 비어 모든 글의 본문이 사라진다."""
        text = layout()
        assign = ASSIGN_RE.search(text)
        output = OUTPUT_RE.search(text)
        self.assertIsNotNone(assign, "post_body 를 정하는 줄이 없다")
        self.assertIsNotNone(output, "post_body 를 찍는 줄이 없다")
        self.assertLess(assign.start(), output.start())

    def test_every_photo_gets_lazy_loading_and_nothing_else_changes(self):
        result = run_filters(body_filters(), SAMPLE)
        photos = re.findall(r"<img\b[^>]*>", result)
        self.assertEqual(len(photos), 2)
        self.assertEqual(len(re.findall(r"<img\b", SAMPLE)), 2)
        for tag in photos:
            with self.subTest(tag=tag):
                self.assertEqual(tag.count('loading="lazy"'), 1)
                self.assertNotIn('loading="eager"', tag)
        self.assertEqual(result.replace('loading="lazy" ', ""), SAMPLE, "lazy 속성을 빼면 원문과 한 글자도 다르지 않아야 한다")

    def test_escaped_code_text_that_looks_like_a_photo_tag_is_left_alone(self):
        result = run_filters(body_filters(), SAMPLE)
        self.assertIn("&lt;img src=&quot;x.png&quot;&gt; 와 &lt;img alt=&quot;y&quot;&gt;", result)
        self.assertEqual(result.count("loading="), 2)

    def test_a_body_without_photos_is_returned_unchanged(self):
        plain = "<p>사진이 없는 글</p>\n<table><tr><td>x</td></tr></table>"
        self.assertEqual(run_filters(body_filters(), plain), plain)

    def test_the_chain_reader_runs_replace_first_and_refuses_what_it_cannot_run(self):
        """계산기 자체 점검 — 사슬에 replace_first 가 끼면 첫 사진만 되돌려져 시험이 잡아야 하고, 모르는 필터는 조용히 넘기지 않는다."""
        self.assertEqual(run_filters(parse_filters("| replace: 'a', 'b' | replace_first: 'b', 'c'"), "aa"), "cb")
        self.assertEqual(parse_filters("| replace: '<img ', '<img loading=\"lazy\" '"), [("replace", ["<img ", '<img loading="lazy" '])])
        with self.assertRaises(AssertionError):
            run_filters(parse_filters("| upcase"), "x")
        with self.assertRaises(AssertionError):
            parse_filters("| replace: foo, 'b'")

    def test_the_layout_never_names_the_post_image_variable(self):
        """tests/test_fact_docs.py 가 레이아웃에 그 글자가 없다고 못박는다(대표 사진은 레이아웃이 쓰지 않는다) — 새 줄이 그 글자를 만들지 않게."""
        self.assertNotIn("post." + "image", layout())


class LayoutLiquidTest(unittest.TestCase):
    def test_liquid_tags_in_the_post_layout_are_balanced(self):
        """Jekyll 이 이 PC 에 없어 레이아웃의 Liquid 문법 오류(빌드 실패 = 사이트 배포 중단)를 잡을 길이 없다 — 열고 닫는 짝이 맞는지만이라도 본다."""
        text = layout()
        self.assertEqual(text.count("{%"), text.count("%}"))
        self.assertEqual(text.count("{{"), text.count("}}"))
        opens = len(re.findall(r"\{%-?\s*(?:if|for|unless|case|comment|capture)\b", text))
        closes = len(re.findall(r"\{%-?\s*end(?:if|for|unless|case|comment|capture)\b", text))
        self.assertEqual(opens, closes)
        self.assertEqual(len(re.findall(r"\{%-?\s*comment\b", text)), len(re.findall(r"\{%-?\s*endcomment\b", text)))

    def test_the_layout_keeps_its_front_matter_and_article_shell(self):
        text = layout()
        self.assertTrue(text.startswith("---\nlayout: default\n---\n"))
        for needle in ('<article class="chance-post">', "</article>", POST_CONTENT_OPEN, 'id="reading-progress"', 'id="share-post"'):
            with self.subTest(needle=needle):
                self.assertEqual(text.count(needle), 1)


if __name__ == "__main__":
    unittest.main()
