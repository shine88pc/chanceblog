"""광고 표면 검사가 '바뀐 파일' 을 읽는 방식(결함 D-350): 이름만 바꿔 옮긴 보호 파일, 한글 같은 비 ASCII 이름, 따옴표·8진수로 나오는 이름.

옛 읽기(`git diff --name-only`)는 두 군데가 틀렸다. ① 이름 바꿈 감지가 켜져 있으면 옮겨 간 파일은 새 경로 하나만 나와서, 보호 파일(ads.txt 등)을 다른 이름·폴더로 옮겨 치우는 변경이
보호 경로에 걸리지 않았다. ② 리눅스 CI 의 기본값(core.quotepath=true)에서는 한글 같은 비 ASCII 경로가 따옴표와 8진수 이스케이프로 나와 `_includes/` 로 시작하는지 비교가 틀렸다.
이 시험은 임시 저장소의 로컬 설정을 CI 기본값으로 고정해(이 PC 의 전역 설정에 기대지 않는다) 두 길이 모두 닫혔는지 본다. 가짜 비밀은 쓰지 않는다.
"""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import _bootstrap

sys.path.insert(0, str(_bootstrap.ROOT / "scripts"))
import validate_repo as vr  # noqa: E402

PROTECTED = ["index.html", "ads.txt", "_layouts/", "_includes/"]
REGISTRY = json.dumps({"schema_version": 1, "defaults": {}, "blogs": [{"key": "chance", "ad_surface": True, "protected_paths": PROTECTED}]})
HANGUL = "".join(chr(code) for code in (0xD55C, 0xAE00))      # 소스에 한글 파일 이름을 직접 쓰지 않고 코드 값으로 만든다(어느 편집기에서도 같은 글자)
NEWLINE_NAME = "_includes/a\nb.html"


class Repo:
    """진짜 git 의 임시 저장소. 이름 바꿈 감지·경로 따옴표 설정은 리눅스 CI 의 기본값(켜짐·켜짐)으로 저장소 안에 고정한다."""

    def __init__(self, root, template=None):
        self.root = Path(root)
        if template is not None:        # 진짜 git 은 이 PC 에서 한 번 부르는 데 수 초가 걸려, 시험마다 처음부터 만들지 않고 한 번 만든 저장소를 폴더째 복사한다
            shutil.copytree(template.root, self.root, dirs_exist_ok=True)
            self.base = template.base
            return
        self.git("init", "-q")
        self.git("config", "core.quotepath", "true")
        self.git("config", "diff.renames", "true")
        self.write("pipeline/blogs.json", REGISTRY)
        self.write("index.html", "<html>" + "랜딩 페이지 줄\n" * 20 + "</html>\n")
        self.write("ads.txt", "ads line one\nads line two\nads line three\n")
        self.write("_includes/head.html", "<head></head>\n" * 6)
        self.write("notes.md", "n1\n")
        self.commit("base")
        self.base = self.git("rev-parse", "HEAD").strip()

    def git(self, *args):
        proc = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", "-c", "commit.gpgsign=false", "-c", "core.autocrlf=false", *args],
                              cwd=self.root, capture_output=True)
        if proc.returncode:
            raise AssertionError(f"git {' '.join(args)} 실패: {proc.stderr.decode('utf-8', 'replace').strip()}")
        return proc.stdout.decode("utf-8", "replace")

    def write(self, rel, text):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def commit(self, message):
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)

    def add_odd_path(self, name):
        """작업 폴더에 만들 수 없는 이름(줄바꿈)도 색인에 직접 넣어 커밋한다(윈도 보호 설정은 이 명령에만 끈다)."""
        proc = subprocess.run(["git", "hash-object", "-w", "--stdin"], cwd=self.root, capture_output=True, input=b"odd name\n", check=True)
        blob = proc.stdout.decode().strip()
        self.git("-c", "core.protectNTFS=false", "update-index", "--add", "--cacheinfo", f"100644,{blob},{name}")
        self.git("-c", "core.protectNTFS=false", "commit", "-q", "-m", "add an oddly named file")


class AdSurfacePathReadingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._template_tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls._template_tmp.cleanup)
        cls.template = Repo(cls._template_tmp.name)

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.repo = Repo(self._tmp.name, template=self.template)

    def findings(self, check="AD-1"):
        return [f for f in vr.check_ad_surface(self.repo.root, self.repo.base) if f.check == check]

    def assertCaught(self, *names):
        found = self.findings()
        self.assertEqual(len(found), 1, [f.line() for f in vr.check_ad_surface(self.repo.root, self.repo.base)])
        self.assertEqual(found[0].level, "ERROR")
        for name in names:
            self.assertIn(name, found[0].message)

    # -- ① 이름 바꿈 ---------------------------------------------------------------------------------------------------------------------------------------
    def test_a_protected_file_renamed_away_is_caught_by_its_old_path(self):
        self.repo.git("mv", "ads.txt", "ads.txt.bak")
        self.repo.commit("move ads.txt away")
        self.assertEqual(self.repo.git("diff", "--name-only", f"{self.repo.base}..HEAD").split(), ["ads.txt.bak"], "시험 전제: 옛 읽기는 새 이름 하나만 낸다")
        self.assertCaught("ads.txt")

    def test_a_protected_file_moved_into_an_unprotected_folder_is_caught(self):
        self.repo.git("mv", "_includes/head.html", "notes_head.html")
        self.repo.commit("move the include out of the protected folder")
        self.assertCaught("_includes/head.html")

    def test_the_old_path_is_reported_whatever_the_rename_setting_is(self):
        self.repo.git("mv", "index.html", "landing_old.html")
        self.repo.commit("move the landing page away")
        for setting in ("true", "copies", "false"):
            with self.subTest(diff_renames=setting):
                self.repo.git("config", "diff.renames", setting)
                self.assertCaught("index.html")

    def test_moving_a_file_onto_a_protected_name_is_still_caught(self):
        self.repo.git("mv", "notes.md", "ads_new.txt")
        self.repo.commit("rename to a harmless name")
        self.assertEqual(self.findings(), [], "대조: 보호 이름이 아니면 걸리지 않는다")
        self.repo.git("mv", "ads_new.txt", "_layouts_unused.html")
        self.repo.git("mv", "ads.txt", "ads_old.txt")
        self.repo.git("mv", "_layouts_unused.html", "ads.txt")
        self.repo.commit("put a different file under the protected name")
        self.assertCaught("ads.txt")

    def test_an_approved_rename_passes_and_the_approval_must_come_from_a_person(self):
        self.repo.git("mv", "ads.txt", "ads.txt.bak")
        self.repo.commit("move ads.txt away\n\nAd-Surface-Approved: 운영자가 채팅으로 승인")
        self.assertEqual(vr.check_ad_surface(self.repo.root, self.repo.base), [])

    # -- ② 비 ASCII·따옴표 이름 ----------------------------------------------------------------------------------------------------------------------------
    def test_a_non_ascii_file_in_a_protected_folder_is_caught_even_though_git_quotes_the_name(self):
        name = f"_includes/{HANGUL}.html"
        self.repo.write(name, "<script>x</script>\n")
        self.repo.commit("add a non-ascii include")
        quoted = self.repo.git("diff", "--name-only", f"{self.repo.base}..HEAD").strip()
        self.assertTrue(quoted.startswith('"') and "\\355" in quoted, f"시험 전제: 옛 읽기는 따옴표와 8진수로 낸다({quoted!r})")
        self.assertCaught(name)

    def test_a_non_ascii_file_outside_the_protected_paths_is_not_reported(self):
        self.repo.write(f"docs/{HANGUL}.md", "문서\n")
        self.repo.commit("add a non-ascii document")
        self.assertEqual(vr.check_ad_surface(self.repo.root, self.repo.base), [])

    def test_a_non_ascii_name_that_looks_like_a_protected_prefix_only_in_the_middle_is_not_reported(self):
        self.repo.write(f"docs/_includes/{HANGUL}.html", "문서\n")
        self.repo.commit("a nested folder with the same name is a different path")
        self.assertEqual(vr.check_ad_surface(self.repo.root, self.repo.base), [])

    def test_a_name_with_a_line_break_in_a_protected_folder_is_caught_and_the_message_stays_on_one_line(self):
        """줄바꿈이 든 이름은 git 이 늘 따옴표로 감싸 내므로 줄 단위로 읽으면 놓친다(-z 만 푼다). 경로는 저장소 글자라 오류 줄에 그대로 넣으면 여러 줄이 되어 워크플로 명령을 흉내 낼 수 있다."""
        self.repo.add_odd_path(NEWLINE_NAME + "\n::error::forged")
        found = self.findings()
        self.assertEqual(len(found), 1)
        for text in (found[0].message, found[0].line()):
            self.assertEqual(len(text.splitlines()), 1, text)
            self.assertNotIn("::", text)
        self.assertIn("_includes/a", found[0].message)

    # -- 대조: 옛 동작이 그대로인 것 -----------------------------------------------------------------------------------------------------------------------
    def test_ordinary_edits_behave_as_before(self):
        self.repo.write("_includes/head.html", "<head><meta></head>\n")
        self.repo.commit("edit an ascii include")
        self.assertCaught("_includes/head.html")
        self.assertEqual(self.findings("AD-2"), [])

    def test_a_change_outside_the_protected_paths_is_not_reported(self):
        self.repo.write("notes.md", "n2\n")
        self.repo.commit("notes")
        self.assertEqual(vr.check_ad_surface(self.repo.root, self.repo.base), [])

    def test_a_missing_base_is_still_skipped(self):
        self.assertEqual(vr.check_ad_surface(self.repo.root, ""), [])
        self.assertEqual(vr.check_ad_surface(self.repo.root, "0" * 40), [])
        self.assertEqual([f.check for f in vr.check_ad_surface(self.repo.root, "deadbeef" * 5)], ["AD-0"])


class SafeReadFlagsTest(unittest.TestCase):
    """위 행동 시험이 한 가지 깃발만 빠져도 우연히 통과하지 못하게(깃발은 서로 겹쳐 막는다) 읽는 명령 자체를 못박는다."""

    def test_the_changed_paths_are_read_without_rename_detection_and_without_quoting(self):
        calls = []

        def fake(root, *args):
            calls.append(args)
            return "ads.txt\0_includes/a b.html\0"

        with mock.patch.object(vr, "_git", fake):
            self.assertEqual(vr._changed_paths("root", "abc123"), ["ads.txt", "_includes/a b.html"])
        self.assertEqual(len(calls), 1)
        args = calls[0]
        self.assertEqual(args[:2], ("-c", "core.quotepath=false"))
        self.assertEqual(args[2:4], ("diff", "--no-renames"))
        self.assertIn("--name-only", args)
        self.assertIn("-z", args)
        self.assertEqual(args[-1], "abc123..HEAD")

    def test_empty_pieces_are_dropped(self):
        with mock.patch.object(vr, "_git", lambda root, *args: ""):
            self.assertEqual(vr._changed_paths("root", "abc"), [])
        with mock.patch.object(vr, "_git", lambda root, *args: "a.txt\0\0b.txt\0"):
            self.assertEqual(vr._changed_paths("root", "abc"), ["a.txt", "b.txt"])

    def test_check_ad_surface_reads_through_the_helper(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Repo(tmp)
            seen = []
            real = vr._changed_paths

            def spy(root, base):
                seen.append(base)
                return real(root, base)

            with mock.patch.object(vr, "_changed_paths", spy):
                vr.check_ad_surface(repo.root, repo.base)
            self.assertEqual(seen, [repo.base])


if __name__ == "__main__":
    unittest.main()
