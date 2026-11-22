"""홈(`index.html`) 스크립트의 두 가지 손보기를 못박는다(확인 015 항목 1, F097 홈 제목 글자·F098 홈 자동 갱신).

① F097 — 홈 카드를 posts.json 으로 다시 그리는 `renderPosts()` 와 모달의 태그 줄은 글에서 온 글자(제목·분야·태그·주소·사진 주소·언어·날짜)를 이스케이프 없이 HTML 문자열(innerHTML)에
   넣어서, 제목에 따옴표나 꺾쇠가 든 글(지금 공개된 것 1편)은 속성이 일찍 닫혀 접근 이름·대체 글이 잘리고 꺾쇠는 태그로 섞였다. 이제 모두 `escapeHtml()` 을 거친다.
   단 `previewText` 는 Jekyll 이 이미 엔티티로 바꾼 글(strip_html 결과)이라 다시 바꾸면 이중 변환되므로 바꾸지 않는다.
   - 정적 시험(항상 돈다): 스크립트의 백틱 템플릿을 읽어 HTML 이 든 템플릿의 모든 풀이 자리가 escapeHtml 호출이거나 허용 목록(숫자 계산·상수·previewText)인지 본다. 새 필드가 생기면 빨강.
   - 실행 시험(Node 가 있을 때): 진짜 index.html 의 스크립트를 가짜 DOM 에 돌려 따옴표·꺾쇠·앰퍼샌드가 든 글을 그리고, 나온 HTML 을 브라우저처럼 읽어(파이썬 html.parser) 속성과 글이
     원문 그대로인지, 끼어든 태그가 없는지 본다. Node 가 없으면 이 부분만 건너뛴다.
② F098 — 홈이 보이는 동안 1분마다 본문이 든 큰 글 목록(posts.json)을 통째로 다시 받았다. 주기를 10분으로 늘렸고 화면 문구 두 곳이 같은 숫자를 말한다.
   문구와 코드가 어긋나는 사고, 옛 1분으로의 되돌림, 숨은 탭에서의 요청, 수동 새로고침 단추·탭 복귀 즉시 갱신의 끊김을 본다.
   Jekyll 이 이 PC 에도 CI 에도 없어 홈을 실제로 빌드하지는 않는다 — 스크립트 원문과 그 실행만 본다. `index.html` 은 광고 표면 파일이고 광고 줄(7–8행)과 head 는 이 변경이 닿지 않는다
   (그 보증은 기존 시험 test_site_cleanup 의 HomeTest 가 하고, 이 파일은 그 시험을 고치지 않았다).
"""
import json
import re
import shutil
import subprocess
import tempfile
import unittest
from collections import Counter
from html import unescape
from html.parser import HTMLParser
from pathlib import Path

import _bootstrap

ROOT = Path(_bootstrap.ROOT)
NODE = shutil.which("node")


def home():
    return (ROOT / "index.html").read_text(encoding="utf-8").replace("\r\n", "\n")


def app_script():
    text = home()
    start = text.index("<!-- Application Script -->")
    begin = text.index("<script>", start) + len("<script>")
    return text[begin:text.index("</script>", begin)]


def render_region():
    """글 카드·추천 글·모달 태그를 HTML 문자열로 만드는 구간: renderPosts() 부터 closePostModal() 앞까지."""
    script = app_script()
    return script[script.index("function renderPosts()"):script.index("function closePostModal()")]


# ---------------------------------------------------------------- 백틱 템플릿 읽기
class Template:
    def __init__(self, static, expressions):
        self.static = static                 # 풀이 자리를 뺀 고정 글자
        self.expressions = expressions       # [(풀이 글, 안쪽에 다른 템플릿이 든다)]

    def is_html(self):
        return "<" in self.static


def scan_templates(source):
    """소스 안의 모든 백틱 템플릿(풀이 안에 든 템플릿 포함)을 읽는다. 코드 칸에서는 백틱만 보고, 풀이 안에서는 따옴표 문자열·중괄호·안쪽 템플릿을 본다(정규식 글자는 못 읽는다)."""
    templates = []

    def read_template(i):
        static, expressions = [], []
        while i < len(source):
            ch = source[i]
            if ch == "\\":
                static.append(source[i:i + 2])
                i += 2
            elif ch == "`":
                templates.append(Template("".join(static), expressions))
                return i + 1
            elif ch == "$" and source[i + 1:i + 2] == "{":
                i, expression = read_expression(i + 2)
                expressions.append(expression)
            else:
                static.append(ch)
                i += 1
        raise ValueError("닫히지 않은 템플릿")

    def read_expression(i):
        start, depth, nested = i, 1, False
        while i < len(source):
            ch = source[i]
            if ch in "'\"":
                quote = ch
                i += 1
                while source[i] != quote:
                    i += 2 if source[i] == "\\" else 1
                i += 1
            elif ch == "`":
                nested = True
                i = read_template(i + 1)
            else:
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        return i + 1, (source[start:i], nested)
                i += 1
        raise ValueError("닫히지 않은 풀이")

    i = 0
    while i < len(source):
        if source[i] == "`":
            i = read_template(i + 1)
        else:
            i += 1
    return templates


def is_escape_call(expression):
    """풀이 글 전체가 escapeHtml( … ) 호출 하나인가 — `escapeHtml(a) + b` 처럼 호출 밖에 뭔가 붙으면 아니다."""
    text = expression.strip()
    if not text.startswith("escapeHtml("):
        return False
    depth, quote = 0, None
    for index, ch in enumerate(text):
        if quote:
            if ch == quote:
                quote = None
        elif ch in "'\"":
            quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return index == len(text) - 1
    return False


# 이스케이프 없이 HTML 에 들어가도 되는 풀이(이유와 함께). 새 필드를 여기에 더하려면 왜 안전한지 적는다.
ALLOWED_RAW = (
    (re.compile(r"defaultThumbnails\[0\]"), "코드 안의 고정 사진 주소(글에서 온 글자가 아니다)"),
    (re.compile(r"idx \+ \(featuredPost \? 1 : 0\)"), "카드 번호 계산(숫자)"),
    (re.compile(r"(?:featuredPost|post)\.previewText(?: \|\| '[^']*')?"), "previewText 는 Jekyll 이 이미 엔티티로 바꾼 글이라 다시 바꾸면 이중 변환된다(기본 문구를 잇는 모양까지만 허용)"),
)


def html_expressions(source):
    """HTML 을 담은 템플릿의 풀이들(안쪽 템플릿을 품은 바깥 풀이는 안쪽 풀이를 따로 보므로 뺀다)."""
    found = []
    for template in scan_templates(source):
        if template.is_html():
            found.extend(text.strip() for text, nested in template.expressions if not nested)
    return found


class TemplateScannerTest(unittest.TestCase):
    """스캐너 자체 점검 — 합성 소스로 안쪽 템플릿·따옴표 속 중괄호·HTML 아닌 템플릿을 제대로 가르는지."""

    SYNTHETIC = ("const a = `<p>${x}</p>`; const b = `<ul>${items.map(i => `<li>${escapeHtml(i)}</li>`).join('')}</ul>`; "
                 "const c = `plain ${n} ${m ? '}' : \"{\"}`; const d = `<i>${escapeHtml(a + ')') + b}</i>`;")

    def test_it_reads_nested_templates_and_ignores_text_templates(self):
        templates = scan_templates(self.SYNTHETIC)
        self.assertEqual(len(templates), 5)                                   # p · li · ul · plain · i
        html = [expression for t in templates if t.is_html() for expression in t.expressions]
        self.assertEqual([text for text, nested in html if not nested], ["x", "escapeHtml(i)", "escapeHtml(a + ')') + b"])
        self.assertEqual([text for text, nested in html if nested], ["items.map(i => `<li>${escapeHtml(i)}</li>`).join('')"])
        plain = [t for t in templates if not t.is_html()]
        self.assertEqual(len(plain), 1)
        self.assertEqual([text for text, _ in plain[0].expressions], ["n", "m ? '}' : \"{\""])

    def test_escape_call_must_cover_the_whole_expression(self):
        self.assertTrue(is_escape_call("escapeHtml(post.title)"))
        self.assertTrue(is_escape_call("escapeHtml(featuredPost.date || '최신 글')"))
        self.assertTrue(is_escape_call("escapeHtml(a + ')')"))
        self.assertFalse(is_escape_call("escapeHtml(post.title) + post.extra"))
        self.assertFalse(is_escape_call("post.title"))
        self.assertFalse(is_escape_call("escapeHtmlLater(post.title)"))
        self.assertFalse(is_escape_call("escapeHtml(post.title"))

    def test_the_real_region_is_read_to_the_end(self):
        region = render_region()
        self.assertEqual(region.count("`") % 2, 0)
        self.assertGreaterEqual(len([t for t in scan_templates(region) if t.is_html()]), 4)      # 추천 글·카드·카드 안 태그·모달 태그


class EscapeHelperStaticTest(unittest.TestCase):
    def test_the_helper_is_defined_once_and_maps_the_five_characters(self):
        script = app_script()
        self.assertEqual(script.count("function escapeHtml("), 1)
        start = script.index("function escapeHtml(")
        body = script[start:script.index("function ", start + 10)]
        for raw, entity in (("&", "&amp;"), ("<", "&lt;"), (">", "&gt;"), ('"', "&quot;"), ("'", "&#39;")):
            with self.subTest(raw=raw):
                self.assertRegex(body, r"""['"]""" + re.escape(raw) + r"""['"]\s*:\s*['"]""" + re.escape(entity) + r"""['"]""")
        self.assertIn("""[&<>"']""", body)                                    # 한 번에 바꾸는 글자 집합(차례로 바꾸면 &amp; 가 다시 바뀐다)
        self.assertEqual(body.count(".replace("), 1)

    def test_every_html_template_expression_is_escaped_or_on_the_allow_list(self):
        expressions = html_expressions(render_region())
        self.assertGreaterEqual(len(expressions), 26)                         # 스캐너가 아무것도 못 읽고 조용히 통과하는 일을 막는다(지금 26개: 감싼 21 + 허용 5)
        for expression in expressions:
            with self.subTest(expression=expression):
                allowed = any(pattern.fullmatch(expression) for pattern, _ in ALLOWED_RAW)
                self.assertTrue(is_escape_call(expression) or allowed,
                                f"HTML 문자열에 이스케이프 없이 들어가는 풀이: {expression} — escapeHtml() 로 감싸거나(글에서 온 글자) 안전한 이유와 함께 ALLOWED_RAW 에 더한다")

    def test_every_field_that_comes_from_a_post_is_wrapped_somewhere(self):
        escaped = [e for e in html_expressions(render_region()) if is_escape_call(e)]
        self.assertGreaterEqual(len(escaped), 21)                             # 14줄 21곳(추천 글 9 · 카드 11 · 모달 태그 1)
        fields = {name for e in escaped for name in re.findall(r"\b(?:featuredPost|post)\.(title|category|date|url|image|lang)\b", e)}
        self.assertEqual(fields, {"title", "category", "date", "url", "image", "lang"})
        self.assertIn("escapeHtml(tag)", escaped)                             # 카드 안 태그 두 개
        self.assertIn("escapeHtml(t)", escaped)                               # 모달 태그 줄

    def test_preview_text_is_never_wrapped_so_it_is_not_converted_twice(self):
        previews = [e for e in html_expressions(render_region()) if "previewText" in e]
        self.assertEqual(len(previews), 2)                                    # 추천 글·카드 하나씩
        for expression in previews:
            self.assertNotIn("escapeHtml", expression)

    def test_the_script_has_no_liquid_sequences(self):
        """index.html 은 front matter 가 있어 Liquid 를 거친다 — 스크립트에 중괄호 둘이나 중괄호-퍼센트가 생기면 빌드가 깨지거나 글자가 사라진다(기존 시험은 블록 낱말만 센다)."""
        script = app_script()
        self.assertNotIn("{{", script)
        self.assertNotIn("{%", script)


# ---------------------------------------------------------------- F098 정적
INTERVAL_RE = re.compile(r"window\.setInterval\(\s*\(\)\s*=>\s*\{(?P<body>.*?)\}\s*,\s*(?P<ms>\d+)\s*\)", re.S)
REFRESH_ON_VISIBLE = "if (document.visibilityState === 'visible') refreshDailyPublishingStats();"


def interval_minutes():
    found = INTERVAL_RE.findall(home())
    assert len(found) == 1, f"window.setInterval 이 정확히 하나여야 한다(지금 {len(found)}개)"
    body, milliseconds = found[0]
    return body, int(milliseconds)


class HomeRefreshStaticTest(unittest.TestCase):
    def test_there_is_exactly_one_timer_and_it_is_the_refresh(self):
        text = home()
        self.assertEqual(text.count("setInterval"), 1)
        body, _ = interval_minutes()
        self.assertIn("refreshDailyPublishingStats()", body)

    def test_the_two_screen_texts_and_the_timer_say_the_same_minutes(self):
        text = home()
        _, milliseconds = interval_minutes()
        self.assertEqual(milliseconds % 60000, 0, "주기는 분 단위여야 화면 문구가 맞을 수 있다")
        minutes = milliseconds // 60000
        label = re.findall(r"(\d+)분마다 갱신<", text)                        # 발행 현황 머리줄의 작은 글
        status = re.findall(r"(\d+)분마다 자동 갱신'", text)                  # 갱신 뒤 바뀌는 상태 줄
        self.assertEqual(label, [str(minutes)])
        self.assertEqual(status, [str(minutes)])
        self.assertEqual(len(re.findall(r"\d+분마다", text)), 2, "'N분마다' 문구가 이 두 곳뿐이어야 한다(다른 곳을 더하면 이 시험을 맞춘다)")

    def test_the_timer_is_not_faster_than_ten_minutes(self):
        """승인 항목(F098)은 '1분마다 본문이 든 큰 목록을 다시 받음' 을 줄이는 것 — 숫자와 문구를 함께 1분으로 되돌려도 여기서 걸린다."""
        _, milliseconds = interval_minutes()
        self.assertGreaterEqual(milliseconds, 10 * 60000)

    def test_the_timer_only_fetches_while_the_tab_is_visible(self):
        body, _ = interval_minutes()
        self.assertIn(REFRESH_ON_VISIBLE, " ".join(body.split()))

    def test_manual_button_and_tab_return_still_refresh_at_once(self):
        text = home()
        self.assertEqual(text.count("document.getElementById('daily-publishing-refresh')?.addEventListener('click', refreshDailyPublishingStats);"), 1)
        match = re.search(r"document\.addEventListener\('visibilitychange', \(\) => \{(.*?)\}\);", text, re.S)
        self.assertIsNotNone(match)
        self.assertIn(REFRESH_ON_VISIBLE, " ".join(match.group(1).split()))

    def test_the_refresh_still_reads_the_post_list_without_the_cache(self):
        """주기를 늘렸을 뿐 받는 방식은 그대로다(항목 범위 밖: 가벼운 목록 파일·조건부 요청은 AP2 몫)."""
        text = home()
        self.assertIn("indexUrl.searchParams.set('_monitor', String(Date.now()));", text)
        self.assertIn("await fetch(indexUrl, { cache: 'no-store' });", text)


# ---------------------------------------------------------------- 정적 보강(독립 검증 Q QP-3·QP-4·QP-9, S SP-4·SP-5·SP-6 반영)
# 위의 정적 시험은 renderPosts() 구간의 '꺾쇠가 든 백틱 템플릿' 풀이만 읽는다. 템플릿이 아닌 직접 대입(title.innerHTML = post.title)·꺾쇠 없는 템플릿·구간 밖의 새 함수·
# Node 가 없는 환경에서만 새는 곳(g 깃발·이중 감쌈)은 그 밖이므로, 스크립트 전체의 HTML 대입 지점과 도우미 사용을 못박는다. 새 대입이 생기면 이유를 적고 이 목록에 더한다(그것이 검토다).
SINK_RE = re.compile(r"\.(?:innerHTML|outerHTML)\s*\+?=(?!=)\s*(?P<right>[^;\n]*)")
EXPECTED_SINK_FORMS = Counter({"''": 4, "`": 2, "visiblePosts.map(": 1, "post.tags.map(": 1, "post.content": 1, "marked.parse(": 1})        # 지금 HTML 대입 열 곳
OTHER_SINKS = re.compile(r"insertAdjacentHTML|document\.write|\beval\(|new Function|createContextualFragment|\.srcdoc|DOMParser|\bsetHTML")


def sink_forms(script):
    """innerHTML·outerHTML 대입(+= 포함)의 오른쪽 첫 모양을 센다: '' · 백틱 템플릿 · 이름.메서드( · 이름.속성."""
    forms = Counter()
    for match in SINK_RE.finditer(script):
        right = match.group("right").strip()
        token = re.match(r"''|\"\"|`|[A-Za-z_$][\w$.]*\(?", right)
        forms[token.group(0) if token else right[:20]] += 1
    return forms


class WholeScriptSinkTest(unittest.TestCase):
    def test_every_html_looking_template_in_the_whole_script_is_escaped_or_allowed(self):
        """위의 같은 이름의 시험은 renderPosts() 부터 closePostModal() 앞까지만 읽는다 — 구간 밖에 새 템플릿 함수가 생겨도 못 본다. 스크립트 전체를 읽는다."""
        expressions = html_expressions(app_script())
        self.assertGreaterEqual(len(expressions), 26)
        for expression in expressions:
            with self.subTest(expression=expression):
                allowed = any(pattern.fullmatch(expression) for pattern, _ in ALLOWED_RAW)
                self.assertTrue(is_escape_call(expression) or allowed, f"이스케이프 없이 HTML 에 들어가는 풀이: {expression}")

    def test_the_html_assignments_are_the_known_ten_forms(self):
        """모달 제목을 innerText 에서 innerHTML 로 바꾸는 흔한 실수(title.innerHTML = post.title)나 꺾쇠 없는 템플릿은 템플릿 스캐너가 HTML 로 안 본다 — 대입 지점을 못박는다."""
        script = app_script()
        forms = sink_forms(script)
        self.assertEqual(forms, EXPECTED_SINK_FORMS)
        self.assertEqual(len(re.findall(r"\.(?:innerHTML|outerHTML)\b", script)), sum(forms.values()), "대입이 아닌 innerHTML 사용이 있다 — 읽는 정규식을 맞춘다")

    def test_there_is_no_other_way_to_put_html_into_the_page(self):
        self.assertEqual(OTHER_SINKS.findall(app_script()), [])

    def test_the_sink_reader_reads_direct_assignments_templates_and_plus_equals(self):
        """도우미 자체 점검 — 직접 대입·이어 붙이기·템플릿·메서드 결과를 읽고 비교(==)는 세지 않는다."""
        sample = "a.innerHTML = '';\nb.innerHTML = `x`;\nc.innerHTML += d.map(x => 1);\ne.innerHTML = f + g;\nh.innerHTML = post.title;\nif (i.innerHTML == j) {}"
        self.assertEqual(sink_forms(sample), Counter({"''": 1, "`": 1, "d.map(": 1, "f": 1, "post.title": 1}))
        self.assertEqual(OTHER_SINKS.findall("x.insertAdjacentHTML(a, b); document.write(c); eval(d)"), ["insertAdjacentHTML", "document.write", "eval("])

    def test_each_attribute_is_filled_from_its_own_field(self):
        """Node 가 없으면 감싸기는 있는데 필드가 틀린 변경(href 에 title 등)을 정적 시험이 못 본다 — 속성과 필드의 짝을 읽는다."""
        region = render_region()
        for attribute, field in (("href", "url"), ("src", "image"), ("alt", "title")):
            values = re.findall(attribute + r'="\$\{escapeHtml\(([^)]*)\)\}"', region)
            self.assertGreaterEqual(len(values), 2, attribute)
            for value in values:
                with self.subTest(attribute=attribute, value=value):
                    self.assertTrue(value.endswith("." + field), f"{attribute} 속성이 {value} 로 채워진다 — {field} 필드여야 한다")
        labels = re.findall(r'aria-label="[^"]*\$\{escapeHtml\(([^)]*)\)\}[^"]*"', region)
        self.assertEqual(len(labels), 2)
        for value in labels:
            self.assertTrue(value.endswith(".title"), value)


class EscapeHelperUseTest(unittest.TestCase):
    def test_the_helper_replaces_every_match_and_is_never_applied_twice(self):
        """Node 가 없는 환경에서 정적 시험이 못 잡던 셋 — g 깃발 삭제(첫 글자 하나만 바뀜)·이중 감쌈(&amp;amp;)·선언 뒤 재대입(아무것도 안 바꾸는 함수로 바꿔치기)."""
        script = app_script()
        start = script.index("function escapeHtml(")
        body = script[start:script.index("function ", start + 10)]
        self.assertIn("""/[&<>"']/g""", body)
        self.assertNotIn("escapeHtml(escapeHtml(", script)
        self.assertEqual(re.findall(r"\bescapeHtml\s*=(?!=)", script), [])


class RefreshWiringTest(unittest.TestCase):
    def test_the_timer_callback_is_exactly_the_guarded_refresh(self):
        """주기 안에 다른 요청(가드 없는 목록 받기 등)을 몰래 더하지 못하게 — 콜백은 '보이는 탭일 때만 갱신' 한 줄뿐이다."""
        body, _ = interval_minutes()
        self.assertEqual(" ".join(body.split()), REFRESH_ON_VISIBLE)

    def test_the_refresh_function_is_wired_to_exactly_the_three_known_triggers(self):
        """F098 은 요청을 줄이는 것이다 — 갱신 함수를 부르는 계기(단추·주기·탭 복귀)가 말없이 늘어나지 않게 낱말 개수를 못박는다(정의 1 + 연결 3)."""
        self.assertEqual(home().count("refreshDailyPublishingStats"), 4)

    def test_both_list_requests_skip_the_cache(self):
        """첫 로드의 받기와 새로고침의 받기 둘 다 no-store 다. 위의 assertIn 은 한쪽만 남아도 통과하므로 개수로 본다."""
        text = home()
        self.assertEqual(text.count("await fetch(indexUrl, { cache: 'no-store' });"), 2)
        self.assertEqual(text.count("indexUrl.searchParams.set('_monitor', String(Date.now()));"), 1)


# ---------------------------------------------------------------- 실행 시험(Node)
PROBE_JS = r"""
const fs = require('fs');
const vm = require('vm');

const input = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const html = fs.readFileSync(input.indexPath, 'utf8');
const marker = html.indexOf('<!-- Application Script -->');
const open = html.indexOf('<script>', marker);
const close = html.indexOf('</script>', open);
if (marker < 0 || open < 0 || close < 0) throw new Error('application script not found');
const appScript = html.slice(open + '<script>'.length, close);

const consoleLines = [];
process.on('unhandledRejection', (reason) => consoleLines.push('unhandledRejection: ' + String(reason)));

const elements = new Map();
function makeElement(id) {
  const handlers = {};
  const element = {
    id, handlers, innerHTML: '', textContent: '', innerText: '', value: '', className: '', scope: '', src: '', disabled: false,
    children: [], scrollLeft: 0, scrollWidth: 0, clientWidth: 0, style: {}, firstElementChild: null,
    classList: { add() {}, remove() {}, toggle() {}, contains() { return false; } },
    addEventListener(type, handler) { (handlers[type] = handlers[type] || []).push(handler); },
    appendChild(child) { element.children.push(child); return child; },
    replaceChildren() { element.children = []; },
    querySelector() { return null; },
    querySelectorAll() { return []; },
    scrollTo() {}, scrollBy() {}, setAttribute() {}, getAttribute() { return null; },
    getBoundingClientRect() { return { width: 0, top: 0 }; },
  };
  return element;
}
function byId(id) {
  if (!elements.has(id)) elements.set(id, makeElement(id));
  return elements.get(id);
}

const documentHandlers = {};
const documentStub = {
  getElementById: byId,
  addEventListener(type, handler) { (documentHandlers[type] = documentHandlers[type] || []).push(handler); },
  querySelectorAll() { return []; },
  querySelector() { return null; },
  createElement(tag) { return makeElement('<' + tag + '>'); },
  createDocumentFragment() { return makeElement('<fragment>'); },
  body: { style: {} },
  visibilityState: 'visible',
  baseURI: 'app://local/',
};
const timers = [];
const requests = [];
const windowStub = {
  addEventListener() {},
  setInterval(handler, delay) { timers.push({ handler, delay }); return timers.length; },
};
windowStub.document = documentStub;
const note = (...args) => consoleLines.push(args.map(String).join(' '));
const context = {
  console: { log() {}, info() {}, warn: note, error: note },
  document: documentStub,
  window: windowStub,
  setInterval(handler, delay) { return windowStub.setInterval(handler, delay); },
  setTimeout, clearTimeout, URL,
  fetch(address) { requests.push(String(address)); return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([]) }); },
};
vm.createContext(context);
vm.runInContext(appScript, context);
const settle = () => new Promise((resolve) => setImmediate(resolve));

async function renderMode() {
  const out = { featured: '', grid: '', modalTags: [], escapeCases: [] };
  vm.runInContext('allPosts = ' + JSON.stringify(input.posts) + '; currentCategory = "all"; currentLang = "all"; searchQuery = ""; renderPosts();', context);
  out.featured = byId('featured-post').innerHTML;
  out.grid = byId('post-grid').innerHTML;
  for (let index = 0; index < input.modalCount; index++) {
    vm.runInContext('openPostModal(' + index + ')', context);
    out.modalTags.push(byId('modal-tags').innerHTML);
  }
  try {
    const escapeHtml = vm.runInContext('escapeHtml', context);
    const mixed = '<b>' + '"' + 'x' + '"' + ' & ' + "'" + 'y' + "'" + '</b>';
    const cases = [['str', '&'], ['str', '<'], ['str', '>'], ['str', '"'], ['str', "'"], ['str', '&amp;'], ['str', mixed], ['str', ''], ['str', '평범한 글'],
                   ['null', null], ['undefined', undefined], ['number', 0], ['number', 12.5]];
    out.escapeCases = cases.map(([kind, value]) => ({ kind, input: kind === 'str' || kind === 'number' ? value : null, output: escapeHtml(value) }));
  } catch (error) {
    out.escapeError = String(error);
  }
  return out;
}

async function refreshMode() {
  documentHandlers.DOMContentLoaded.forEach((handler) => handler());
  await settle();
  await settle();
  const out = { delays: timers.map((item) => item.delay) };
  const tick = timers[0];
  async function requestsDuring(action) {
    const before = requests.length;
    action();
    await settle();
    await settle();
    return requests.length - before;
  }
  const returnEvent = () => (documentHandlers.visibilitychange || []).forEach((handler) => handler());
  documentStub.visibilityState = 'hidden';
  out.hiddenTick = await requestsDuring(() => tick.handler());
  out.hiddenReturn = await requestsDuring(returnEvent);
  documentStub.visibilityState = 'visible';
  out.visibleTick = await requestsDuring(() => tick.handler());
  out.statusText = byId('daily-publishing-status').textContent;
  out.visibleReturn = await requestsDuring(returnEvent);
  out.buttonClick = await requestsDuring(() => (byId('daily-publishing-refresh').handlers.click || []).forEach((handler) => handler()));
  out.lastRequests = requests.slice(-2);
  return out;
}

(async () => {
  try {
    const result = input.mode === 'render' ? await renderMode() : await refreshMode();
    result.consoleLines = consoleLines;
    process.stdout.write(JSON.stringify(result));
  } catch (error) {
    process.stdout.write(JSON.stringify({ error: String((error && error.stack) || error), consoleLines }));
  }
})();
"""


def run_probe(mode, **payload):
    with tempfile.TemporaryDirectory() as folder:
        script, data_file = Path(folder) / "probe.js", Path(folder) / "input.json"
        script.write_text(PROBE_JS, encoding="utf-8")
        data_file.write_text(json.dumps(dict(payload, mode=mode, indexPath=str(ROOT / "index.html"))), encoding="utf-8")
        done = subprocess.run([NODE, str(script), str(data_file)], capture_output=True, text=True, encoding="utf-8", timeout=120)
    if done.returncode != 0:
        raise AssertionError(f"Node 가 실패했다(종료 {done.returncode}): {(done.stderr or done.stdout)[-800:]}")
    return json.loads(done.stdout)


# 모든 필드에 따옴표·꺾쇠·앰퍼샌드·엔티티처럼 생긴 글을 넣는다 — 이스케이프가 하나라도 빠지면 그 자리의 값이 원문과 달라진다.
def make_post(**fields):
    base = dict(path="", absoluteUrl="", name="", url="/p/0/", title="평범한 제목", category="경제·일", lang="kr", date="2026-10-26", image="img-0",
                tags=[], content="<p>본문</p>", contentIsHtml=True, previewText="본문 요약")
    base.update(fields)
    return base


HOSTILE_POSTS = [
    make_post(title='"You Decide What’s Important": Mentorship & <b>Talent</b> &lt;i&gt;', category='Science & Environment "x" <u>', lang='en"><x', date='2026-10-28"<',
              url='/p/1/?q="1"&r=<2>', image='/img/p.jpg?auto=format&fit=crop&w=800&q="x"', tags=['a&b "q"', '<i>x</i>', "third"], previewText="R&amp;D &lt;b&gt; text"),
    make_post(title='Kp<5 and "quotes" & more &lt;', category="과학 &lt;x&gt; 환경", lang='kr"<x>&amp;', date="2026-10-27&lt;", url='/p/2/?x="y"', image='img-2"',
              tags=['x"y&lt;', "z<i>"], previewText="plain &amp; simple"),
    make_post(title="Korea's " + '"firefighters" <script>x</script> &amp;', category="경제 <b>일</b> 'quote'", lang="en&amp;", date="2026-10-26'", url="/p/3/?a='b'&c=<d>",
              image="img-3'<", tags=["it's", "&lt;b&gt;"], previewText="no entities here"),
    make_post(title="평범한 제목", category="일상·마음", lang="kr", date="2026-10-25", url="/p/4/", image="img-4", tags=["하나", "둘", "셋"], previewText="본문 요약 &lt;그대로&gt;"),
]
ALLOWED_TAGS = {"article", "div", "a", "img", "span", "i", "h2", "p", "button"}
VOID_TAGS = {"img", "br", "hr", "input", "meta", "link"}


class Element:
    def __init__(self, tag, attrs, parent):
        self.tag, self.attrs, self.parent, self.children = tag, dict(attrs), parent, []

    def text(self):
        return "".join(child if isinstance(child, str) else child.text() for child in self.children)

    def find_all(self, tag):
        found = []
        for child in self.children:
            if isinstance(child, Element):
                if child.tag == tag:
                    found.append(child)
                found.extend(child.find_all(tag))
        return found

    def all_tags(self):
        tags = set()
        for child in self.children:
            if isinstance(child, Element):
                tags.add(child.tag)
                tags |= child.all_tags()
        return tags


class Reader(HTMLParser):
    """브라우저가 HTML 을 읽는 것과 같은 방식으로(엔티티는 한 번 풀고 속성은 따옴표 안에서만) 조각을 요소 나무로 읽는다."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Element("#root", [], None)
        self.current = self.root

    def handle_starttag(self, tag, attrs):
        element = Element(tag, attrs, self.current)
        self.current.children.append(element)
        if tag not in VOID_TAGS:
            self.current = element

    def handle_startendtag(self, tag, attrs):
        self.current.children.append(Element(tag, attrs, self.current))

    def handle_endtag(self, tag):
        node = self.current
        while node is not None and node.tag != tag:
            node = node.parent
        if node is not None and node.parent is not None:
            self.current = node.parent

    def handle_data(self, data):
        self.current.children.append(data)


def read_html(fragment):
    reader = Reader()
    reader.feed(fragment)
    reader.close()
    return reader.root


def expected_escape(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;").replace("'", "&#39;")


@unittest.skipUnless(NODE, "Node 가 없으면 이 실행 시험만 건너뛴다(정적 시험은 항상 돈다)")
class HostileTitleRunTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = run_probe("render", posts=HOSTILE_POSTS, modalCount=len(HOSTILE_POSTS))

    def test_the_script_ran_without_an_error(self):
        self.assertNotIn("error", self.out, self.out.get("error"))
        self.assertEqual([line for line in self.out["consoleLines"] if "Error" in line or "unhandled" in line], [])

    def test_the_featured_post_keeps_every_field_exactly(self):
        self.assertNotIn("error", self.out, self.out.get("error"))
        post = HOSTILE_POSTS[0]
        root = read_html(self.out["featured"])
        self.assertLessEqual(root.all_tags(), ALLOWED_TAGS, "글에서 온 글자가 태그로 끼어들었다")
        links = root.find_all("a")
        self.assertEqual(links[0].attrs.get("href"), post["url"])
        self.assertEqual(links[0].attrs.get("aria-label"), "추천 글 읽기: " + post["title"])
        image = root.find_all("img")[0]
        self.assertEqual(image.attrs.get("alt"), post["title"])
        self.assertEqual(image.attrs.get("src"), post["image"])
        headline = root.find_all("h2")[0]
        self.assertEqual(headline.text().strip(), post["title"])
        self.assertEqual(headline.find_all("a")[0].attrs.get("href"), post["url"])
        spans = [span.text().strip() for span in root.find_all("span")]
        self.assertIn(post["category"], spans)
        self.assertIn(post["date"], spans)
        self.assertEqual(root.find_all("p")[0].text().strip(), unescape(post["previewText"]), "previewText 는 한 번만 풀려야 한다(이중 변환 금지)")
        self.assertEqual(links[-1].attrs.get("href"), post["url"])

    def test_each_grid_card_keeps_every_field_exactly(self):
        root = read_html(self.out["grid"])
        self.assertLessEqual(root.all_tags(), ALLOWED_TAGS, "글에서 온 글자가 태그로 끼어들었다")
        cards = root.find_all("article")
        self.assertEqual(len(cards), len(HOSTILE_POSTS) - 1)
        for offset, card in enumerate(cards):
            post = HOSTILE_POSTS[offset + 1]
            with self.subTest(title=post["title"]):
                links = card.find_all("a")
                self.assertEqual(links[0].attrs.get("href"), post["url"])
                self.assertEqual(links[0].attrs.get("aria-label"), post["title"] + " 글 읽기")
                image = card.find_all("img")[0]
                self.assertEqual(image.attrs.get("alt"), post["title"])
                self.assertEqual(image.attrs.get("src"), post["image"])
                spans = [span.text().strip() for span in card.find_all("span")]
                for value in (post["category"], post["lang"], post["date"]):
                    self.assertIn(value, spans)
                headline = card.find_all("h2")[0]
                self.assertEqual(headline.text().strip(), post["title"])
                self.assertEqual(headline.find_all("a")[0].attrs.get("href"), post["url"])
                self.assertEqual(card.find_all("p")[0].text().strip(), unescape(post["previewText"]), "previewText 는 한 번만 풀려야 한다(이중 변환 금지)")
                tag_texts = [text for text in (span.text().strip() for span in card.find_all("span")) if text.startswith("#")]      # 태그 줄의 칸들(분야·언어·날짜 칸은 #로 시작하지 않는다)
                self.assertEqual(tag_texts, ["#" + tag for tag in post["tags"][:2]])
                self.assertEqual(links[-1].attrs.get("href"), post["url"])
                button = card.find_all("button")[0]
                self.assertEqual(button.attrs.get("onclick"), f"openPostModal({offset + 1})")

    def test_the_modal_tag_line_keeps_the_tag_text(self):
        for index, fragment in enumerate(self.out["modalTags"]):
            post = HOSTILE_POSTS[index]
            with self.subTest(title=post["title"]):
                root = read_html(fragment)
                self.assertLessEqual(root.all_tags(), {"span"})
                self.assertEqual([span.text() for span in root.find_all("span")], ["#" + tag for tag in post["tags"]])

    def test_the_helper_changes_exactly_the_five_characters(self):
        self.assertNotIn("escapeError", self.out, self.out.get("escapeError"))
        self.assertEqual(len(self.out["escapeCases"]), 13)
        for case in self.out["escapeCases"]:
            with self.subTest(case=case):
                if case["kind"] == "str":
                    self.assertEqual(case["output"], expected_escape(case["input"]))
                elif case["kind"] == "number":
                    self.assertEqual(case["output"], str(case["input"]))
                else:
                    self.assertEqual(case["output"], "")


@unittest.skipUnless(NODE, "Node 가 없으면 이 실행 시험만 건너뛴다(정적 시험은 항상 돈다)")
class RefreshRunTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = run_probe("refresh")

    def test_the_script_ran_without_an_error(self):
        self.assertNotIn("error", self.out, self.out.get("error"))
        self.assertEqual([line for line in self.out["consoleLines"] if "unhandled" in line or "Daily publishing stats refresh failed" in line], [])

    def test_one_timer_is_set_with_the_delay_the_texts_promise(self):
        self.assertEqual(len(self.out["delays"]), 1)
        delay = self.out["delays"][0]
        self.assertGreaterEqual(delay, 10 * 60000)
        minutes = re.search(r"(\d+)분마다 자동 갱신", self.out["statusText"])
        self.assertIsNotNone(minutes, self.out["statusText"])
        self.assertEqual(int(minutes.group(1)) * 60000, delay)

    def test_a_hidden_tab_asks_for_nothing_and_a_visible_one_asks_once(self):
        self.assertEqual(self.out["hiddenTick"], 0)
        self.assertEqual(self.out["hiddenReturn"], 0)
        self.assertEqual(self.out["visibleTick"], 1)

    def test_coming_back_to_the_tab_and_the_manual_button_refresh_at_once(self):
        self.assertEqual(self.out["visibleReturn"], 1)
        self.assertEqual(self.out["buttonClick"], 1)
        for address in self.out["lastRequests"]:
            self.assertIn("posts.json?_monitor=", address)


if __name__ == "__main__":
    unittest.main()
