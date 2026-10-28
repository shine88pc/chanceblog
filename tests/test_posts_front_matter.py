"""저장소의 실제 글(`_posts/**/*.md`) 전체의 머리말(front matter)을 엄격히 검사하는 지킴이 시험(결함 D-80, 사용자 이슈 #59). 네트워크 없이 돈다.

봇이 글을 올리는 커밋은 시험 워크플로를 일으키지 않아(D-02·D-65), 머리말이 깨진 글이 올라와도 다음 PR 의 자동 검사 전까지 아무도 몰랐다 — 2026-10-27 18시·10-28 9시 슬롯의
글 세 편이 그랬고, 공개 사이트의 글 제목이 파일 이름으로 나왔다. 이 시험은 그런 글이 저장소에 있으면 **다음 PR 의 검사가 빨갛게** 되게 한다(D-65 와 같은 방식). 그래서
깨진 글을 고치는 PR 이 이 시험을 통과시켜야 하고, 생성기가 깨진 머리말을 만들지 않게 막는 것은 `test_generator_front_matter.py` 가 맡는다.

규칙은 생성기의 최종 검사(`generator.front_matter_problems`)와 같고(첫 줄 `---`·닫는 `---`·한 줄 한 키·키 중복 없음·title 은 한 줄 JSON 문자열·필수 키
layout·title·category·lang·image·본문이 `---`/머리말 줄로 시작하지 않음), 이 시험은 거기에 PyYAML(개발용 requirements-dev.txt 에만 있다 — 운영 코드는 쓰지 않는다)로
다시 읽어 값이 기대한 모양인지 한 번 더 확인한다.
"""
import re
import unittest

import yaml

import _bootstrap
import generator as g

POSTS = _bootstrap.ROOT / "_posts"

# 알려진 예외: 이름으로만 허용하고, 이 글이 고쳐졌거나 저장소에서 없어지면 `test_the_known_exceptions_are_still_needed` 가 알려 준다(그때 이 목록에서 지운다).
# D-65: 2026-10-26 18시 슬롯 글은 모델이 `layout` 줄을 빼먹어 `layout: post` 없이 올라갔다. 공개 글이고 렌더링이 정상이라 그대로 둔다.
KNOWN_EXCEPTIONS = {
    "2026-10-26-KR-182804.md": ["필수 키 `layout` 줄이 없음"],
    "2026-10-26-EN-182804.md": ["필수 키 `layout` 줄이 없음"],
}

# 깨졌다가 고친 세 편(이슈 #59). 제목은 엔진이 history.json 에 기록한 kr_title·en_title 이다.
REPAIRED = {
    "2026-10-27-KR-221527.md": ("기후변화 대응의 축 이동: 선제적·시스템적 위험 관리가 공동체와 경제에 의미하는 것", "사회·정책", "ko"),
    "2026-10-27-EN-221527.md": ("Shifting the Climate Defense: What Proactive Risk Management Means for European Communities", "Society & Policy", "en"),
    "2026-10-28-KR-111851.md": ('"너에게 무엇이 중요한지 결정하는 것": 우주 공학 현장에서 멘토링이 갖는 의미', "과학·환경", "ko"),
}


def all_posts():
    return sorted(POSTS.rglob("*.md"))


def read(path):
    return path.read_text(encoding="utf-8")        # 줄바꿈은 \n 으로 읽힌다(윈도우 작업 트리의 CRLF 도 같다)


def pyyaml_front(text):
    """PyYAML 로 읽은 머리말(사전). 읽을 수 없으면 예외가 그대로 올라온다."""
    match = re.match(r"\A---\n(.*?)\n---\n", text, re.S)
    if not match:
        raise AssertionError("머리말을 찾을 수 없다")
    loaded = yaml.safe_load(match.group(1))
    if not isinstance(loaded, dict):
        raise AssertionError("머리말이 사전이 아니다")
    return loaded


class EveryPostFrontMatterTest(unittest.TestCase):
    def test_there_are_posts_to_check(self):
        self.assertGreater(len(all_posts()), 10)

    def test_every_post_has_a_strictly_valid_front_matter(self):
        for path in all_posts():
            with self.subTest(post=path.relative_to(_bootstrap.ROOT).as_posix()):
                self.assertEqual(g.front_matter_problems(read(path)), KNOWN_EXCEPTIONS.get(path.name, []),
                                 "머리말이 깨졌다 — 공개 사이트에서 제목이 파일 이름으로, 분야가 General 로 나온다(이슈 #59). 생성기가 쓴 글이면 test_generator_front_matter.py 를 먼저 본다")

    def test_the_known_exceptions_are_still_needed(self):
        by_name = {path.name: path for path in all_posts()}
        for name, expected in KNOWN_EXCEPTIONS.items():
            with self.subTest(post=name):
                self.assertIn(name, by_name, f"{name} 이 저장소에 없다 — KNOWN_EXCEPTIONS 에서 지우세요")
                self.assertNotEqual(g.front_matter_problems(read(by_name[name])), [], f"{name} 이 고쳐졌다 — KNOWN_EXCEPTIONS 에서 지우세요")

    def test_pyyaml_reads_every_front_matter_to_the_values_the_site_needs(self):
        for path in all_posts():
            with self.subTest(post=path.name):
                front = pyyaml_front(read(path))
                for key in ("title", "category"):
                    self.assertIsInstance(front.get(key), str, key)
                    self.assertTrue(front[key].strip(), key)
                self.assertIn(front.get("lang"), ("ko", "en"))
                self.assertIsInstance(front.get("image"), str)
                self.assertTrue(front["image"].startswith("https://"), front["image"])
                self.assertIsInstance(front.get("tags") or [], list)
                if path.name not in KNOWN_EXCEPTIONS:
                    self.assertEqual(front.get("layout"), "post")
                pair = re.search(r"-(KR|EN)-\d{6}\.md\Z", path.name)
                if pair:
                    self.assertEqual(front["lang"], "ko" if pair.group(1) == "KR" else "en", "파일 이름의 KR/EN 과 lang 이 다르다")

    def test_no_title_is_a_file_name(self):
        """이슈 #59 의 증상: 제목이 `2026-10-28-KR-111851.md`·`Kr 221527` 처럼 파일 이름으로 나왔다."""
        for path in all_posts():
            with self.subTest(post=path.name):
                title = pyyaml_front(read(path))["title"]
                self.assertNotIn(title, (path.name, path.stem))
                self.assertIsNone(re.fullmatch(r"(?:Kr|En|KR|EN)[ -]\d{6}", title), title)
                self.assertIsNone(re.fullmatch(r"\d{4}-\d{2}-\d{2}-.*\.md", title), title)

    def test_no_body_starts_with_a_fence_or_a_second_header(self):
        for path in all_posts():
            with self.subTest(post=path.name):
                body = read(path).split("\n---\n", 1)[1]
                first = next((line for line in body.split("\n") if line.strip()), "")
                self.assertIsNone(re.fullmatch(r"-{3,}[ \t]*", first), "본문이 울타리 줄로 시작한다(이중 머리말 흔적)")
                self.assertIsNone(re.match(r"(?:layout|title|category|tags|lang|image)[ \t]*:", first), "본문이 머리말 줄로 시작한다")

    def test_the_three_repaired_posts_read_as_the_engine_wrote_them(self):
        by_name = {path.name: path for path in all_posts()}
        for name, (title, category, lang) in REPAIRED.items():
            with self.subTest(post=name):
                self.assertIn(name, by_name)
                front = pyyaml_front(read(by_name[name]))
                self.assertEqual((front["title"], front["category"], front["lang"], front["layout"]), (title, category, lang, "post"))
                self.assertIsInstance(front["tags"], list)
                self.assertTrue(front["tags"])
                for key in ("description", "source_name", "source_url", "source_domain"):
                    self.assertTrue(front.get(key), key)
                self.assertTrue(front["source_url"].startswith(f"https://{front['source_domain']}/"), front["source_url"])


class GuardCatchesTheRealBreakagesTest(unittest.TestCase):
    """지킴이가 실제로 깨졌던 모양을 잡는지(이 시험이 없으면 지킴이가 조용히 무뎌져도 모른다)."""

    BODY = "\n본문 문단입니다. " * 3 + "\n"
    BROKEN_QUOTE_TITLE = ('---\nlayout: post\ntitle: ""너에게 무엇이 중요한지 결정하는 것": 우주 공학 현장에서 멘토링이 갖는 의미"\ncategory: "과학·환경"\n'
                          'tags:\n  - 멘토링\nlang: ko\nimage: "https://images.unsplash.com/photo-1"\n---\n' + BODY)
    BROKEN_SIX_DASHES = ('------\nlayout: post\ntitle: "기후변화 대응"\ncategory: "사회·정책"\ntags: ["유럽연합"]\nlang: ko\nimage: "https://images.unsplash.com/photo-1"\n'
                         '---\n\n---\n\n' + BODY)

    def test_the_unescaped_quote_title_is_caught_by_both_checks(self):
        self.assertTrue(any("`title` 값이 한 줄 JSON 문자열" in p for p in g.front_matter_problems(self.BROKEN_QUOTE_TITLE)))
        with self.assertRaises(yaml.YAMLError):
            pyyaml_front(self.BROKEN_QUOTE_TITLE)

    def test_the_six_dash_double_header_is_caught(self):
        self.assertEqual(g.front_matter_problems(self.BROKEN_SIX_DASHES), ["첫 줄이 정확히 `---` 가 아님"])
        fixed = self.BROKEN_SIX_DASHES.replace("------\n", "---\n", 1)
        self.assertEqual(g.front_matter_problems(fixed), ["본문이 `---` 울타리 줄로 시작함(이중 머리말 흔적)"])
        self.assertEqual(g.front_matter_problems(fixed.replace("---\n\n---\n\n", "---\n\n", 1)), [])


if __name__ == "__main__":
    unittest.main()
