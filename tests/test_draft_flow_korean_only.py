"""국문 전용 초안(레지스트리 chance.languages = ["ko"])의 승인 흐름: 글 파일이 하나인 초안을 올리고(deliver) PR 을 다시 여는(reopen) 일.

기본(국문·영문 두 개)의 PR 제목·본문이 글자 하나도 달라지지 않았다는 증거는 이 파일이 아니라 기존 시험(test_drafts.py·test_draft_flow.py — 문구를 그대로 단정한다)과
저장소 밖 비교 도구(옛 코드와 새 코드가 같은 입력으로 만든 제목·본문을 바이트 단위로 견줌)다. 여기서는 두 가지를 더한다: ① 국문 전용 제목·본문에 영어 칸이 없다 ② 기본 모양의 해시를 못박는다.
"""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import _bootstrap  # noqa: F401
from draft_helpers import LINK, REPO, FakeGit, FakeGitHub, post_text
from pipeline import draft_flow, drafts

OWNER = REPO.split("/")[0]       # 승인 흐름 시험 공용 도구(draft_helpers)의 저장소 값을 그대로 쓴다 — 이 파일에는 저장소 이름을 따로 적지 않는다
ENV = {"GITHUB_REPOSITORY": REPO, "GITHUB_REPOSITORY_OWNER": OWNER, "GITHUB_TOKEN": "ghs_" + "T" * 36}
BRANCH = "ai/draft/2026-10-28-s9"
KR_PATH = "_posts/기술·미래/2026-10-28-KR-090000.md"


def write_ko_draft(root, title="국문 초안 제목", link=LINK, slot=9, date="2026-10-28"):
    """generator 가 국문 전용 승인 흐름에서 하는 일: 글 하나를 쓰고 이력 항목(flow·branch·paths 하나)을 덧붙인다. 영문 칸(en_title·en_image)은 없다."""
    root = Path(root)
    target = root / KR_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(post_text(title, link).encode("utf-8"))
    history_file = root / "history.json"
    history = json.loads(history_file.read_text(encoding="utf-8")) if history_file.exists() else []
    entry = {"date": date, "topic": "후보 기사", "kr_title": title, "kr_image": "https://images.unsplash.com/photo-090000k", "slot": slot, "lane": "technology",
             "source": "Reuters", "source_url": link, "languages": ["ko"]}
    entry.update(drafts.entry_fields(date, slot, None, [KR_PATH]))
    history.append(entry)
    history_file.write_bytes((json.dumps(history, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    return entry


class KoreanOnlyDeliverTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / "history.json").write_bytes(b"[]\n")
        self.git, self.gh, self.out, self.sleeps = FakeGit(self.root), FakeGitHub(), [], []

    def deliver(self):
        return draft_flow.deliver(self.git, self.gh, dict(ENV), out=self.out.append, sleep=self.sleeps.append)

    def test_a_one_file_draft_is_delivered_with_only_that_file_added(self):
        write_ko_draft(self.root)
        result = self.deliver()
        self.assertEqual((result.status, result.code), ("opened", 0))
        self.assertIn(("add", "--", KR_PATH), self.git.calls)
        self.assertEqual([call for call in self.git.calls if call[0] == "add"], [("add", "--", KR_PATH)])
        self.assertEqual(self.git.calls[3], ("add", "--", KR_PATH))
        self.assertIn(BRANCH, self.git.remote)

    def test_the_pr_title_and_body_have_no_english_part(self):
        write_ko_draft(self.root, title="국문 초안 제목")
        result = self.deliver()
        pr = self.gh.prs[result.number]
        self.assertEqual(pr["title"], "[초안][Chance] 국문 초안 제목")
        body = pr["body"]
        for needle in ("English", "영어", "(no title)", "두 개"):
            self.assertNotIn(needle, body, needle)
        for needle in ("**승인 대기 초안**", "- 한국어: 국문 초안 제목", "> **한국어**", "- 본문 분량: 한국어 ", "- 원문 링크 인용: 한국어 ", "- 글 끝 출처 목록: 한국어 ",
                       "- 출처 고지문(AI 작성·검토 안 받음 안내): 한국어 ", "`_posts/` 파일 하나(한국어)입니다", "## 승인 체크리스트"):
            self.assertIn(needle, body, needle)
        self.assertNotIn("·", "\n".join(line for line in body.splitlines() if line.startswith("- 본문 분량")))

    def test_the_checks_still_use_the_korean_minimum_and_the_notice(self):
        write_ko_draft(self.root)
        body = self.gh.prs[self.deliver().number]["body"]
        self.assertIn("최소 1,000자", body)

    def test_a_draft_with_three_files_is_still_refused(self):
        entry = write_ko_draft(self.root)
        entry["paths"] = [KR_PATH, KR_PATH + "2", KR_PATH + "3"]
        history = json.loads((self.root / "history.json").read_text(encoding="utf-8"))
        history[-1]["paths"] = entry["paths"]
        (self.root / "history.json").write_bytes(json.dumps(history, ensure_ascii=False).encode("utf-8"))
        with self.assertRaises(draft_flow.DeliveryError):
            self.deliver()

    def test_a_draft_with_no_file_is_still_refused(self):
        write_ko_draft(self.root)
        history = json.loads((self.root / "history.json").read_text(encoding="utf-8"))
        history[-1]["paths"] = []
        (self.root / "history.json").write_bytes(json.dumps(history, ensure_ascii=False).encode("utf-8"))
        with self.assertRaises(draft_flow.DeliveryError):
            self.deliver()

    def test_check_entry_accepts_one_or_two_valid_paths_only(self):
        base = {"branch": BRANCH}
        draft_flow.check_entry({**base, "paths": [KR_PATH]})
        draft_flow.check_entry({**base, "paths": [KR_PATH, "_posts/Technology & Future/2026-10-28-EN-090000.md"]})
        for paths in ([], [KR_PATH] * 3, ["../x.md"], ["_posts/a.txt"], None, "문자열", [KR_PATH, "../x.md"]):
            with self.subTest(paths=paths):
                with self.assertRaises(draft_flow.DeliveryError):
                    draft_flow.check_entry({**base, "paths": paths})


class KoreanOnlyReopenTest(unittest.TestCase):
    def test_a_missing_pr_is_reopened_from_the_branch_for_a_one_file_draft(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "history.json").write_bytes(b"[]\n")
            entry = write_ko_draft(root)
            git, gh = FakeGit(root, branch="main"), FakeGitHub()
            git.branch_files[KR_PATH] = post_text("국문 초안 제목")
            out, sleeps = [], []
            number = draft_flow.reopen_pull_request(git, gh, BRANCH, entry, dict(ENV), sleeps.append, out.append)
            pr = gh.prs[number]
            self.assertEqual(pr["title"], "[초안][Chance] 국문 초안 제목")
            self.assertNotIn("English", pr["body"])
            self.assertEqual(git.calls_of("show"), [("show", f"FETCH_HEAD:{KR_PATH}")])


class BuildersTest(unittest.TestCase):
    ENTRY = {"date": "2026-10-28", "slot": 9, "kr_title": "한국어 제목", "en_title": "English Title", "source": "Reuters", "source_url": LINK, "lane": "technology"}

    def test_the_title_builder_keeps_the_pair_form_by_default(self):
        self.assertEqual(drafts.build_pr_title("한국어 제목", "English Title"), "[초안][Chance] 한국어 제목 / English Title")
        self.assertEqual(drafts.build_pr_title("한국어 제목", None, ko_only=True), "[초안][Chance] 한국어 제목")
        self.assertEqual(drafts.build_pr_title("", None, ko_only=True), "[초안][Chance] (제목 없음)")
        self.assertEqual(drafts.build_pr_title("", None), "[초안][Chance] (제목 없음) / (no title)")
        self.assertLessEqual(len(drafts.build_pr_title("가" * 400, None, ko_only=True)), drafts.TITLE_LIMIT)

    def test_the_pair_body_is_pinned_byte_for_byte(self):
        body = drafts.build_pr_body(self.ENTRY, post_text("한국어 제목"), post_text("English Title"), owner=OWNER)
        # 이 해시는 이 변경 전의 pipeline/drafts.py(origin/main 611b2d2)가 같은 입력으로 만든 본문의 해시다. 문구를 일부러 바꾸면 이 값도 함께 바꾼다.
        self.assertEqual(hashlib.sha256(body.encode("utf-8")).hexdigest(), PAIR_BODY_SHA256)
        self.assertIn("파일 두 개(한국어·영어)", body)
        self.assertIn("- English: English Title", body)

    def test_the_korean_only_body_has_the_same_sections_without_english(self):
        pair = drafts.build_pr_body(self.ENTRY, post_text("한국어 제목"), post_text("English Title"), owner=OWNER)
        solo = drafts.build_pr_body(self.ENTRY, post_text("한국어 제목"), None, owner=OWNER)
        headings = lambda text: [line for line in text.splitlines() if line.startswith("## ")]     # noqa: E731
        self.assertEqual(headings(solo), headings(pair))
        self.assertLess(len(solo), len(pair))
        self.assertNotIn("English", solo)


PAIR_BODY_SHA256 = "27b50b793d5c3b4d344452701d1080b9d93c0c8dcd708f5e074e03da2c2b542e"


if __name__ == "__main__":
    unittest.main()
