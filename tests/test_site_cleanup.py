"""사이트 정리(2026-10-26 운영자 승인, 7번; D-08·SIT-02·SIT-03)가 풀려 나가지 않게 고정한다.

① `_config.yml` 의 `exclude` — 운영 문서·코드·상태 파일은 사이트(페이지·사이트맵·정적 파일)로 나가지 않고, 사이트가 쓰는 파일은 빠지지 않는다.
   저장소 맨 위에 새 문서·폴더를 만들면 이 시험이 '내보낼 것인가 뺄 것인가'를 정하라고 실패한다.
② `index.html` — 글 목록을 Jekyll 반복문으로 미리 그려 JS 없이도 글 링크가 보이게 한다. 광고 코드와 JS 의 나머지는 그대로다.
Jekyll 을 돌리지는 않는다(설정과 홈 원본의 모양만 본다). 구문은 승인 작업 때 Liquid 렌더러로 따로 시험 렌더했다.
"""
import re
import sys
import unittest
from pathlib import Path

import _bootstrap
import yaml

sys.path.insert(0, str(_bootstrap.ROOT / "scripts"))
import validate_repo as vr  # noqa: E402

ROOT = Path(_bootstrap.ROOT)

# 사이트가 쓰는 맨 위 항목(내보내야 하는 것). 나머지 맨 위 항목은 모두 exclude 에 있어야 한다.
PUBLIC_ROOT = {
    "index.html", "about.md", "contact.md", "privacy.md", "categories.md",
    "posts.json", "feed.xml", "robots.txt", "assets",
    "googlee86895dfeddcdd45.html", "naver8e7a71b78d49e6f323e7ad60ffb862a8.html",
}
# 사이트에 내보내면 안 되는 운영 문서·코드·상태 파일(승인 범위 + 같은 성격의 코드·상태 파일)
MUST_EXCLUDE = {
    "AGENTS.md", "AI_COLLAB.md", "CLAUDE.md", "GEMINI.md", "HANDLER.md", "README.md", "WORKLOG.md",
    "docs", "인수인계", "pipeline", "scripts", "tests",
    "generator.py", "blogger_generator.py", "history.json", "blogger_history.json", "pages.json",
    "requirements-dev.txt", "requirements-edits.txt", "requirements-pipeline.txt",
}
AD_SCRIPT = ('<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-6035749437698387"\n'
             '     crossorigin="anonymous"></script>')


def config():
    return yaml.safe_load((ROOT / "_config.yml").read_text(encoding="utf-8"))


def home():
    return (ROOT / "index.html").read_text(encoding="utf-8").replace("\r\n", "\n")


def is_excluded(path, excluded):
    return any(path == e or path.startswith(e.rstrip("/") + "/") for e in excluded)


class ExcludeTest(unittest.TestCase):
    def test_internal_docs_code_and_state_files_are_excluded_from_the_site(self):
        excluded = set(config().get("exclude") or [])
        self.assertEqual(sorted(MUST_EXCLUDE - excluded), [])

    def test_nothing_the_site_needs_is_excluded(self):
        excluded = config().get("exclude") or []
        for path in sorted(PUBLIC_ROOT) + ["assets/chance-ideas-map.svg", "_layouts", "_includes"]:
            with self.subTest(path=path):
                self.assertFalse(is_excluded(path, excluded), f"{path} 는 사이트가 쓰는 파일인데 exclude 에 들어 있다")

    def test_every_entry_exists_so_a_typo_cannot_silently_exclude_nothing(self):
        for entry in config().get("exclude") or []:
            with self.subTest(entry=entry):
                self.assertTrue((ROOT / entry).exists(), f"exclude 의 {entry} 가 저장소에 없다")

    def test_every_top_level_item_is_either_a_known_public_one_or_excluded(self):
        excluded = config().get("exclude") or []
        unknown = []
        for item in ROOT.iterdir():
            name = item.name
            if name.startswith((".", "_")):      # Jekyll 이 기본으로 내보내지 않는다
                continue
            if name in PUBLIC_ROOT or is_excluded(name, excluded):
                continue
            unknown.append(name)
        self.assertEqual(sorted(unknown), [], "새 맨 위 파일·폴더는 사이트에 내보낼지(PUBLIC_ROOT) 뺄지(_config.yml exclude) 정해야 한다")

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

    def test_the_summary_line_shows_the_server_side_count(self):
        self.assertIn("{{ site.posts.size }}개의 글을 만나보세요", home())

    def test_javascript_keeps_prerendered_cards_until_the_new_list_is_ready(self):
        text = home()
        self.assertIn("const prerendered = Boolean(postGrid && postGrid.children.length > 0);", text)
        self.assertIn("if (postGrid && !prerendered) postGrid.innerHTML = '';", text)
        self.assertIn("if (loadingEl && !prerendered) loadingEl.classList.remove('hidden');", text)
        self.assertIn("if (emptyEl && !prerendered) emptyEl.classList.remove('hidden');", text)
        self.assertIn("new URL('posts.json', document.baseURI)", text)             # 목록은 여전히 posts.json 으로 다시 그린다
        self.assertIn("grid.innerHTML = visiblePosts.map(", text)

    def test_the_spinner_starts_hidden_and_the_carousel_buttons_are_hidden_without_javascript(self):
        text = home()
        self.assertRegex(text, r'<div id="loading-indicator" class="hidden py-24 ')
        self.assertIn("<noscript><style>#post-carousel-controls { display: none; }</style></noscript>", text)

    def test_the_ad_code_and_the_page_structure_are_untouched(self):
        text = home()
        self.assertEqual(text.count(AD_SCRIPT), 1)
        self.assertEqual(text.count("pagead2.googlesyndication.com"), 1)
        for needle in ('id="post-grid"', 'id="featured-post"', 'id="post-modal"', 'id="category-list"', 'id="daily-publishing-monitor"',
                       'id="visit-counter"', "function renderPosts()", "async function fetchPostList()"):
            with self.subTest(needle=needle):
                self.assertEqual(text.count(needle), 1)

    def test_liquid_blocks_are_balanced(self):
        text = home()
        opens = len(re.findall(r"{%-?\s*(?:if|for|unless|case)\b", text))
        closes = len(re.findall(r"{%-?\s*end(?:if|for|unless|case)\b", text))
        self.assertEqual(opens, closes)


if __name__ == "__main__":
    unittest.main()
