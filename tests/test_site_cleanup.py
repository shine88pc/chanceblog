"""사이트 정리(2026-10-26 운영자 승인, 7번; D-08·SIT-02·SIT-03)가 풀려 나가지 않게 고정한다.

① `_config.yml` 의 `exclude` — 승인받은 운영 문서(AGENTS·AI_COLLAB·CLAUDE·GEMINI·HANDLER·WORKLOG·docs/·인수인계/)는 사이트(페이지·사이트맵·글 내비·정적 파일)로
   나가지 않고, 사이트가 쓰는 파일은 빠지지 않는다. 저장소 맨 위에 새 문서·폴더를 만들면 이 시험이 '내보낼 것인가 뺄 것인가'를 정하라고 실패한다.
② `index.html` — 글 목록을 Jekyll 반복문으로 미리 그려 JS 없이도 글 링크가 보이게 한다. 광고 코드와 JS 의 나머지는 그대로다.
Jekyll 을 돌리지는 않는다(설정과 홈 원본의 모양만 본다). 구문은 승인 작업 때 python-liquid 로 시험 렌더했고, 실제 GitHub Pages 빌드(`actions/jekyll-build-pages`)로
main 과 이 변경을 각각 빌드해 견주었다(2026-10-26, 운영 문서 52개가 빠지고 시험 파일 1개가 늘어 파일 157→106개·사이트맵 44→19건·홈 카드 12장).
"""
import fnmatch
import re
import subprocess
import sys
import unittest
from pathlib import Path

import _bootstrap
import yaml

sys.path.insert(0, str(_bootstrap.ROOT / "scripts"))
import validate_repo as vr  # noqa: E402

ROOT = Path(_bootstrap.ROOT)

# 사이트가 쓰는 맨 위 항목(내보내야 하는 것).
PUBLIC_ROOT = {
    "index.html", "about.md", "contact.md", "privacy.md", "categories.md",
    "posts.json", "feed.xml", "robots.txt", "assets",
    "googlee86895dfeddcdd45.html", "naver8e7a71b78d49e6f323e7ad60ffb862a8.html",
}
# 사이트에 내보내면 안 되는 것 — 운영자가 승인한 범위: 운영 문서(2026-10-26 "7. 진행": AGENTS·AI_COLLAB·CLAUDE·GEMINI·HANDLER·WORKLOG·docs/·인수인계/)와
# 코드·상태 파일(같은 날 "2. 추천대로": 생성기·pipeline/·scripts/·tests/·이력·페이지 목록·requirements 파일).
MUST_EXCLUDE = {
    "AGENTS.md", "AI_COLLAB.md", "CLAUDE.md", "GEMINI.md", "HANDLER.md", "WORKLOG.md",
    "docs", "인수인계",
    "generator.py", "blogger_generator.py", "pipeline", "scripts", "tests",
    "history.json", "blogger_history.json", "pages.json",
    "requirements-dev.txt", "requirements-edits.txt", "requirements-pipeline.txt",
}
# 사이트에 일부러 그대로 열어 두는 정적 파일(내보내지도 빼지도 않기로 한 것). README.md 는 문서라 운영자 승인 범위(운영 문서·코드·상태 파일) 밖이다.
# 뺄 때는 `_config.yml` exclude 에 더하고 MUST_EXCLUDE 로 옮긴다. 이 시험은 '뺐거나 여기 있거나' 둘 다 통과시킨다.
STATIC_EXPOSED = {
    "README.md",
}
AD_SCRIPT = ('<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-6035749437698387"\n'
             '     crossorigin="anonymous"></script>')


def config():
    return yaml.safe_load((ROOT / "_config.yml").read_text(encoding="utf-8"))


def home():
    return (ROOT / "index.html").read_text(encoding="utf-8").replace("\r\n", "\n")


def is_excluded(path, excluded):
    """Jekyll 3.10(GitHub Pages)의 exclude 판정: 소스 기준 경로가 항목과 글롭으로 맞거나 항목으로 **시작**하면 뺀다(entry_filter.rb).
    그래서 항목 `docs` 는 `docs-x.html` 도 뺀다 — 경로 구간 단위로만 보면 이런 우연한 제외를 놓친다."""
    return any(fnmatch.fnmatchcase(path, e) or path.startswith(e) for e in excluded)


def tracked_files():
    """저장소가 추적하는 파일(로컬에 있는 추적 안 된 폴더 — venv·임시 작업 폴더 — 는 세지 않는다)."""
    res = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True, timeout=60)
    return [n for n in res.stdout.decode("utf-8", "replace").split("\0") if n]


class ExcludeTest(unittest.TestCase):
    def test_internal_docs_are_excluded_from_the_site(self):
        excluded = set(config().get("exclude") or [])
        self.assertEqual(sorted(MUST_EXCLUDE - excluded), [])

    def test_nothing_the_site_needs_is_excluded(self):
        excluded = config().get("exclude") or []
        for path in sorted(PUBLIC_ROOT) + ["assets/chance-ideas-map.svg", "_layouts", "_includes", "_posts", "_config.yml"]:
            with self.subTest(path=path):
                self.assertFalse(is_excluded(path, excluded), f"{path} 는 사이트가 쓰는 파일인데 exclude 에 들어 있다")

    def test_every_tracked_public_file_survives_jekyll_prefix_matching(self):
        # 사이트가 쓰는 맨 위 항목 아래의 추적 파일 전부 — 항목 이름으로 시작한다는 이유만으로 빠지는 파일이 없어야 한다.
        excluded = config().get("exclude") or []
        for path in tracked_files():
            top = path.split("/")[0]
            if top in PUBLIC_ROOT:
                with self.subTest(path=path):
                    self.assertFalse(is_excluded(path, excluded), path)

    def test_every_entry_exists_so_a_typo_cannot_silently_exclude_nothing(self):
        for entry in config().get("exclude") or []:
            with self.subTest(entry=entry):
                self.assertTrue((ROOT / entry).exists(), f"exclude 의 {entry} 가 저장소에 없다")

    def test_every_top_level_tracked_item_is_public_or_excluded_or_a_known_static_one(self):
        excluded = config().get("exclude") or []
        unknown = set()
        for path in tracked_files():
            name = path.split("/")[0]
            if name.startswith((".", "_")):      # Jekyll 이 기본으로 내보내지 않는다
                continue
            if name in PUBLIC_ROOT or name in STATIC_EXPOSED or is_excluded(name, excluded):
                continue
            unknown.add(name)
        self.assertEqual(sorted(unknown), [],
                         "새 맨 위 파일·폴더는 사이트에 내보낼지(PUBLIC_ROOT) 뺄지(_config.yml exclude) 정해야 한다. 코드·상태 파일이면 STATIC_EXPOSED 에 적고 운영자에게 알린다")

    def test_the_static_exposed_list_does_not_go_stale(self):
        for name in sorted(STATIC_EXPOSED):
            with self.subTest(name=name):
                self.assertTrue((ROOT / name).exists(), f"STATIC_EXPOSED 의 {name} 가 저장소에 없다 — 목록에서 뺀다")
        self.assertFalse(STATIC_EXPOSED & PUBLIC_ROOT)
        self.assertFalse(STATIC_EXPOSED & MUST_EXCLUDE)

    def test_the_validator_no_longer_warns_about_exposed_internal_docs(self):
        self.assertEqual(vr.check_exposure(ROOT, vr.list_files(ROOT)), [])


class HomeTest(unittest.TestCase):
    def grid_region(self):
        text = home()
        start = text.index('<div id="post-grid"')
        end = text.index("</main>", start)
        return text[start:end]

    def test_the_post_list_is_rendered_by_jekyll_so_links_exist_without_javascript(self):
        region = self.grid_region()
        self.assertIn("{% for post in site.posts limit: 24 %}", region)
        self.assertIn("{% endfor %}", region)
        self.assertIn("{{ post.url | relative_url }}", region)
        self.assertIn("{{ post.title | escape }}", region)

    def test_each_prerendered_card_keeps_its_parts(self):
        # 카드 안의 일부를 지워도 문자열 존재 시험이 통과하던 빈틈(독립 검증 2026-10-26)을 막는다.
        region = self.grid_region()
        for needle in (
                "{% assign card_category = post.category | default: post.categories.first | default: 'General' %}",
                '<article class="group min-w-[84%] max-w-[84%] shrink-0 snap-start',
                '<a href="{{ post.url | relative_url }}" class="relative aspect-video',
                'aria-label="{{ post.title | escape }} 글 읽기"',
                '{% if post.image %}<img src="{{ post.image | escape }}" alt="{{ post.title | escape }}"',
                "{{ card_category | escape }}",
                '{{ post.date | date: "%Y-%m-%d" }}',
                '<h2 class="text-lg font-bold text-slate-100 line-clamp-2 leading-snug mb-2"><a href="{{ post.url | relative_url }}"',
                "{{ post.excerpt | strip_html | normalize_whitespace | truncate: 180 }}",
                "</article>"):
            with self.subTest(needle=needle[:60]):
                self.assertEqual(region.count(needle), 1, needle)

    def test_the_approval_note_is_a_liquid_comment_so_it_is_not_published(self):
        region = self.grid_region()
        self.assertIn("{% comment %}서버가 미리 그린 글 목록", region)
        self.assertIn("{% endcomment %}", region)
        self.assertNotIn("<!-- 서버가 미리 그린", region)

    def test_the_summary_line_shows_the_server_side_count(self):
        self.assertIn("{{ site.posts.size }}개의 글을 만나보세요", home())

    def test_javascript_keeps_prerendered_cards_until_the_new_list_is_ready(self):
        text = home()
        self.assertIn("const prerendered = Boolean(postGrid && postGrid.querySelector('article'));", text)
        self.assertIn("if (postGrid && !prerendered) postGrid.innerHTML = '';", text)
        self.assertIn("if (loadingEl && !prerendered) loadingEl.classList.remove('hidden');", text)
        self.assertIn("if (emptyEl && !prerendered) emptyEl.classList.remove('hidden');", text)
        self.assertIn("new URL('posts.json', document.baseURI)", text)             # 목록은 여전히 posts.json 으로 다시 그린다
        self.assertIn("grid.innerHTML = visiblePosts.map(", text)

    def test_the_spinner_starts_hidden_and_the_carousel_buttons_are_hidden_without_javascript(self):
        text = home()
        self.assertRegex(text, r'<div id="loading-indicator" class="hidden py-24 ')
        self.assertIn("<noscript><style>#post-carousel-controls { display: none; }</style></noscript>", text)

    def test_the_head_gets_only_the_noscript_style_and_the_ad_code_is_untouched(self):
        text = home()
        head = text[:text.index("</head>")]
        self.assertEqual(head.count("<noscript>"), 1)                               # 머리 부분의 변경은 이 한 줄뿐이다(PR 설명이 '머리 부분 불변'이라 쓰던 것을 바로잡음)
        self.assertEqual(text.count(AD_SCRIPT), 1)
        self.assertEqual(text.count("pagead2.googlesyndication.com"), 1)
        for needle in ('id="post-grid"', 'id="featured-post"', 'id="post-modal"', 'id="category-list"', 'id="daily-publishing-monitor"',
                       'id="visit-counter"', "function renderPosts()", "async function fetchPostList()"):
            with self.subTest(needle=needle):
                self.assertEqual(text.count(needle), 1)

    def test_liquid_blocks_are_balanced(self):
        text = home()
        opens = len(re.findall(r"{%-?\s*(?:if|for|unless|case|comment)\b", text))
        closes = len(re.findall(r"{%-?\s*end(?:if|for|unless|case|comment)\b", text))
        self.assertEqual(opens, closes)


if __name__ == "__main__":
    unittest.main()
