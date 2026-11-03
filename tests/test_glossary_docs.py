"""용어·관계 사전(docs/GLOSSARY.md)이 저장소의 실제 낱말과 어긋나지 않게 잡는 시험(표류 방지).

사전은 규칙을 새로 정하지 않는다 — 코드·레지스트리·정본 문서가 맞고 사전이 그것을 따라간다. 그래서 코드에 낱말이 늘거나 이름이 바뀌었는데
사전이 그대로면 여기서 실패해 같은 변경에서 사전을 고치게 한다. 설명 문장이 옳은지는 시험이 알 수 없으므로 사람이 본다.
네트워크 없이 파일만 읽는다.
"""
import re
import unittest

import _bootstrap  # noqa: F401

from pipeline import notify, registry

ROOT = _bootstrap.ROOT
GLOSSARY = (ROOT / "docs" / "GLOSSARY.md").read_text(encoding="utf-8")
RUNBOOK = (ROOT / "docs" / "AGENT_RUNBOOK.md").read_text(encoding="utf-8")
CIRCLED = "①②③④⑤⑥⑦⑧⑨"
WORKFLOW_DIR = ROOT / ".github" / "workflows"
# 같은 낱말이 곳마다 다른 뜻으로 쓰여 실제로 헷갈렸거나 헷갈릴 낱말 — §4 표에 한 줄씩 있어야 한다.
# 줄을 일부러 없애거나 이름을 바꿀 때는 이 목록도 같은 변경에서 고친다.
CONFUSING_WORDS = (
    "키", "번호", "요청", "초안", "게시·공개·업로드", "모드", "채널·블로그·플랫폼", "chance", "프로필", "상태",
    "실행(run)", "병합", "승인", "운영", "광고", "정지·중단", "알림·알람",
)
PATH_LIKE = re.compile(r"^[\w.\-/]+$")      # \w 는 한글도 포함한다
FILE_ENDINGS = (".md", ".json", ".py", ".yml", ".html", ".txt")
MIN_PATHS_CHECKED = 30                      # 경로 검사가 아무것도 안 보고 통과하는 일을 막는다


def section(prefix):
    """`## 5.` 처럼 번호로 시작하는 절 하나의 본문(다음 `## ` 앞까지). 절이 없거나 둘이면 실패한다."""
    found = [part for part in re.split(r"(?m)^## ", GLOSSARY) if part.startswith(prefix)]
    if len(found) != 1:
        raise AssertionError(f"docs/GLOSSARY.md 에 '## {prefix}…' 절이 정확히 하나여야 합니다(찾은 수 {len(found)})")
    return found[0]


def table_rows(text):
    """마크다운 표의 모든 줄(머리글 포함, 구분선 제외)을 셀 목록으로."""
    rows = []
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
            continue
        rows.append(cells)
    return rows


def backticked(text):
    return re.findall(r"`([^`\n]+)`", text)


def looks_like_repo_path(token):
    if token.startswith("/") or not PATH_LIKE.match(token):       # '/chanceblog/' 같은 주소 조각은 저장소 경로가 아니다
        return False
    return "/" in token or token.endswith(FILE_ENDINGS)


def exists_in_repo(token):
    if (ROOT / token).exists():
        return True
    return "/" not in token and (WORKFLOW_DIR / token).exists()   # 워크플로는 파일 이름만 적는 곳이 많다


class VocabularyTest(unittest.TestCase):
    def test_every_word_the_code_defines_is_in_the_glossary(self):
        ticks = set(backticked(GLOSSARY))
        for what, words in (
            ("모드", registry.MODES),
            ("플랫폼", registry.PLATFORMS),
            ("채널 라벨", registry.CHANNEL_LABELS),
            ("광고 선언", registry.ADS_STATES),
            ("게시 방식", registry.PUBLISH_FLOWS),
            ("요청 종류(kind)", notify.REQUEST_KIND_LABELS),
        ):
            missing = [word for word in words if word not in ticks]
            self.assertEqual(missing, [], f"{what}: 코드에 있는데 docs/GLOSSARY.md 에 `백틱` 으로 없는 낱말 — 같은 변경에서 사전에 한 줄을 더하세요")

    def test_request_kind_names_in_korean_are_in_the_glossary(self):
        for kind, label in notify.REQUEST_KIND_LABELS.items():
            self.assertIn(label, GLOSSARY, f"요청 종류 {kind} 의 한글 이름 '{label}' 이 사전에 없음")

    def test_procedure_numbers_match_the_runbook(self):
        numbers = [int(n) for n in re.findall(r"(?m)^### J(\d+)\.", RUNBOOK)]
        self.assertGreater(len(numbers), 5)
        self.assertIn(f"J1~J{max(numbers)}", GLOSSARY, "docs/AGENT_RUNBOOK.md 의 마지막 절차 번호와 사전의 'J1~J…' 가 다름")

    def test_the_seven_sections_exist(self):
        for prefix in ("1.", "2.", "3.", "4.", "5.", "6.", "7."):
            section(prefix)


class PathsTest(unittest.TestCase):
    def test_every_backticked_repo_path_exists(self):
        paths = sorted({token for token in backticked(GLOSSARY) if looks_like_repo_path(token)})
        self.assertGreaterEqual(len(paths), MIN_PATHS_CHECKED, "경로를 거의 못 찾음 — 경로 판정이 깨졌거나 사전이 줄었음")
        missing = [path for path in paths if not exists_in_repo(path)]
        self.assertEqual(missing, [], "사전에 적힌 경로가 저장소에 없음 — 이름이 바뀌었거나 지웠으면 사전도 고치세요")

    def test_path_detection_itself_is_sound(self):
        for token in ("docs/GLOSSARY.md", "pipeline/profiles/", "tistory.yml", "history.json", "인수인계/작업내용.md"):
            self.assertTrue(looks_like_repo_path(token), token)
        for token in ("/chanceblog/", "R-nnn", "mode: off", "--dry-run", "T0~T3", "ai/draft/<날짜>-s<슬롯>", "pipeline/profiles/*.json", "[Watchdog] …"):
            self.assertFalse(looks_like_repo_path(token), token)
        self.assertTrue(exists_in_repo("naver.yml"))
        self.assertFalse(exists_in_repo("no_such_workflow_file.yml"))
        self.assertFalse(exists_in_repo("docs/NO_SUCH_DOC.md"))


class MappingTableTest(unittest.TestCase):
    def test_blog_table_lists_exactly_the_registered_blogs_with_their_real_channel_and_platform(self):
        rows = table_rows(section("5."))[1:]
        blogs = {blog["key"]: blog for blog in registry.load_registry()["blogs"]}
        listed = {}
        for cells in rows:
            self.assertEqual(len(cells), 5, f"§5 표의 줄은 칸이 다섯이어야 합니다: {cells}")
            key = cells[0].strip("`")
            self.assertNotIn(key, listed, f"{key}: §5 표에 두 번 나옴")
            listed[key] = cells
        self.assertEqual(sorted(listed), sorted(blogs), "§5 표의 블로그 key 가 레지스트리와 다름 — 블로그를 더하거나 뺀 변경에서 한 줄을 고치세요")
        for key, cells in listed.items():
            channel = blogs[key]["channel"]
            self.assertIn(channel["key"], backticked(cells[1]), f"{key}: 채널 key")
            self.assertIn(channel["label"], backticked(cells[1]), f"{key}: 채널 라벨")
            self.assertIn(blogs[key]["platform"], backticked(cells[2]), f"{key}: 플랫폼")
            self.assertTrue(all(cells), f"{key}: 빈 칸이 있음")

    def test_every_history_file_and_content_folder_of_a_blog_is_named_in_the_glossary(self):
        ticks = set(backticked(GLOSSARY))
        for blog in registry.load_registry()["blogs"]:
            for field in ("history", "content_dir"):
                name = blog["state"][field]
                self.assertTrue(name in ticks or name + "/" in ticks, f"{blog['key']}: state.{field} '{name}' 이 사전에 없음")


class ConfusingWordsTableTest(unittest.TestCase):
    def test_the_words_that_mean_different_things_are_all_there_with_more_than_one_meaning(self):
        rows = table_rows(section("4."))[1:]
        words = [cells[0] for cells in rows]
        self.assertEqual(len(words), len(set(words)), "§4 표에 같은 낱말이 두 번 나옴")
        missing = [word for word in CONFUSING_WORDS if word not in words]
        self.assertEqual(missing, [], "§4 표에서 빠진 낱말 — 일부러 뺀 것이면 이 시험의 CONFUSING_WORDS 도 같은 변경에서 고치세요")
        for cells in rows:
            self.assertEqual(len(cells), 3, f"§4 표의 줄은 칸이 셋이어야 합니다: {cells[0]}")
            self.assertTrue(all(cells), f"{cells[0]}: 빈 칸이 있음")
            marks = sum(cells[1].count(ch) for ch in CIRCLED)
            self.assertGreaterEqual(marks, 2, f"{cells[0]}: 뜻이 둘 이상(① ② …)이어야 이 표에 있을 이유가 있습니다")


class EntryPointsTest(unittest.TestCase):
    def test_the_rules_file_and_the_readme_point_to_the_glossary(self):
        for name in ("AGENTS.md", "README.md"):
            text = (ROOT / name).read_text(encoding="utf-8")
            self.assertIn("docs/GLOSSARY.md", text, f"{name} 가 docs/GLOSSARY.md 를 가리키지 않음 — 새 세션의 AI 가 사전을 모르고 시작한다")


if __name__ == "__main__":
    unittest.main()
